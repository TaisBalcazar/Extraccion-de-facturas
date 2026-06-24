"""Elimina registros de hospedaje (pernoctación en hoteles) de Firestore.

Modo simulación (por defecto, sin borrar nada):
    python scripts/delete_cat4_hospedaje.py --dry-run

Ejecutar borrado real:
    python scripts/delete_cat4_hospedaje.py --execute

Filtrar por año:
    python scripts/delete_cat4_hospedaje.py --year 2026 --execute

Filtrar por mes (1-12):
    python scripts/delete_cat4_hospedaje.py --month 3 --execute
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
        description="Borra documentos de hospedaje (cat-4) de Firestore."
    )
    parser.add_argument(
        "--year",
        type=int,
        default=None,
        help="Año a eliminar (opcional). Sin este flag se eliminan todos los años.",
    )
    parser.add_argument(
        "--month",
        type=int,
        default=None,
        help="Mes a eliminar 1-12 (opcional). Requiere --year.",
    )
    parser.add_argument(
        "--collection",
        default=DEFAULT_COLLECTION,
        help="Colección de Firestore (por defecto facturas)",
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


def collect_target_docs(db, collection_name: str, year: int | None, month: int | None):
    query = db.collection(collection_name).where(
        filter=FieldFilter("tipo_documento", "==", "hospedaje")
    )
    if year is not None:
        query = query.where(filter=FieldFilter("year", "==", year))
    docs = list(query.stream())

    # Filtro de mes en Python (evita índice compuesto en Firestore)
    if month is not None:
        docs = [d for d in docs if (d.to_dict() or {}).get("mes_numero") == month]

    return docs


def main() -> int:
    args = parse_args()
    dry_run = args.dry_run or not args.execute

    if args.month is not None and args.year is None:
        print("⚠️  --month requiere --year. Especifica también el año.")
        return 1

    db = get_firestore_client()
    if not db:
        print("Firebase no está disponible en este entorno.")
        return 1

    targets = collect_target_docs(db, args.collection, args.year, args.month)

    year_label = str(args.year) if args.year else "todos los años"
    month_label = f" mes {args.month}" if args.month else ""
    print(
        f"Encontrados {len(targets)} documento(s) de hospedaje en '{args.collection}' "
        f"({year_label}{month_label})."
    )

    for doc in targets[:15]:
        data = doc.to_dict() or {}
        print(
            f"  - {doc.id} | año={data.get('year')} | "
            f"mes={data.get('mes_numero')} ({data.get('mes_nombre')}) | "
            f"noches={data.get('noches')} | "
            f"zona={data.get('zona_id')} | centro={data.get('centro')}"
        )
    if len(targets) > 15:
        print(f"  ... y {len(targets) - 15} más.")

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

    print(f"✅ Eliminados {deleted} documento(s) de hospedaje.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
