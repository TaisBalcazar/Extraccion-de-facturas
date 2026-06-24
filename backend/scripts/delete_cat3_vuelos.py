"""Elimina registros de vuelos (cat-3) de Firestore.

Modo simulación (sin borrar nada):
    python scripts/delete_cat3_vuelos.py --dry-run

Borrado real:
    python scripts/delete_cat3_vuelos.py --execute

Filtrar por año:
    python scripts/delete_cat3_vuelos.py --year 2025 --execute

Filtrar por tipo (nacional / internacional):
    python scripts/delete_cat3_vuelos.py --tipo nacional --execute
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from google.cloud.firestore_v1.base_query import FieldFilter


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.firebase import get_firestore_client  # noqa: E402


DEFAULT_COLLECTION = "facturas"
BATCH_SIZE = 450


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Borra documentos de vuelos (cat-3) de Firestore."
    )
    parser.add_argument(
        "--year",
        type=int,
        default=None,
        help="Año a eliminar (opcional). Sin este flag se eliminan todos los años.",
    )
    parser.add_argument(
        "--tipo",
        choices=["nacional", "internacional"],
        default=None,
        help="Tipo de vuelo a eliminar (opcional).",
    )
    parser.add_argument(
        "--collection",
        default=DEFAULT_COLLECTION,
        help="Colección de Firestore (por defecto facturas).",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Ejecuta el borrado real. Sin esta bandera solo muestra el conteo.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fuerza modo simulación aunque se pase --execute.",
    )
    return parser.parse_args()


def collect_target_docs(
    db,
    collection_name: str,
    year: int | None,
    tipo: str | None,
):
    todos = []
    for tipo_doc in ("vuelos", "vuelos_ruta"):
        query = db.collection(collection_name).where(
            filter=FieldFilter("tipo_documento", "==", tipo_doc)
        )
        if year is not None:
            query = query.where(filter=FieldFilter("year", "==", year))
        docs = list(query.stream())

        if tipo is not None:
            docs = [d for d in docs if (d.to_dict() or {}).get("tipo_vuelo") == tipo]

        todos.extend(docs)
    return todos


def main() -> int:
    args = parse_args()
    dry_run = args.dry_run or not args.execute

    db = get_firestore_client()
    if not db:
        print("Firebase no está disponible en este entorno.")
        return 1

    targets = collect_target_docs(db, args.collection, args.year, args.tipo)

    year_label = str(args.year) if args.year else "todos los años"
    tipo_label = f" | tipo={args.tipo}" if args.tipo else ""
    print(
        f"Encontrados {len(targets)} documento(s) de vuelos "
        f"en '{args.collection}' ({year_label}{tipo_label})."
    )

    for doc in targets[:20]:
        data = doc.to_dict() or {}
        tipo_doc = data.get("tipo_documento", "?")
        if tipo_doc == "vuelos_ruta":
            detalle = (
                f"ruta={data.get('ruta')} | "
                f"mes={data.get('mes_nombre')} | "
                f"{data.get('cantidad_viajes')}x {data.get('km_por_viaje')} km"
            )
        else:
            detalle = (
                f"mes={data.get('mes_nombre')} | "
                f"km={data.get('km')}"
            )
        print(
            f"  - [{tipo_doc}] {doc.id} | año={data.get('year')} | "
            f"tipo_vuelo={data.get('tipo_vuelo')} | {detalle} | "
            f"zona={data.get('zona_id')} | centro={data.get('centro')}"
        )
    if len(targets) > 20:
        print(f"  ... y {len(targets) - 20} más.")

    if dry_run:
        print("\nModo simulación: no se eliminó ningún documento.")
        print("Usa --execute para realizar el borrado real.")
        return 0

    if not targets:
        print("No hay documentos para eliminar.")
        return 0

    print(f"\n⚠️  Estás a punto de eliminar {len(targets)} documento(s) de forma permanente.")
    confirm = input("Escribe BORRAR para confirmar la eliminación definitiva: ").strip()
    if confirm != "BORRAR":
        print("Operación cancelada.")
        return 1

    deleted = 0
    batch = db.batch()
    pending = 0

    for doc in targets:
        batch.delete(doc.reference)
        pending += 1
        deleted += 1

        if pending >= BATCH_SIZE:
            batch.commit()
            batch = db.batch()
            pending = 0

    if pending:
        batch.commit()

    print(f"✅ Eliminados {deleted} documento(s) de vuelos.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
