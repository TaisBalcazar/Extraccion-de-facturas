"""Elimina registros de la categoría 1 de Firestore.

Modo simulación (por defecto, sin borrar nada):
    python scripts/delete_cat1.py --dry-run

Ejecutar borrado real de todos los años:
    python scripts/delete_cat1.py --execute

Ejecutar borrado real de un año específico:
    python scripts/delete_cat1.py --year 2025 --execute
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
from app.services.resumen_service import reconstruir_resumen  # noqa: E402


DEFAULT_CATEGORY_ID = "cat-1"
DEFAULT_COLLECTION = "facturas"
BATCH_SIZE = 450


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Borra documentos de Firestore para la categoría 1."
    )
    parser.add_argument(
        "--year",
        type=int,
        default=None,
        help="Año a eliminar (opcional). Si no se indica, se eliminan todos los años.",
    )
    parser.add_argument(
        "--category-id",
        default=DEFAULT_CATEGORY_ID,
        help="ID de categoría (por defecto cat-1)",
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


def collect_target_docs(db, collection_name: str, year: int | None, category_id: str):
    query = db.collection(collection_name).where(
        filter=FieldFilter("categoria_id", "==", category_id)
    )
    if year is not None:
        query = query.where(filter=FieldFilter("year", "==", year))
    return list(query.stream())


def main() -> int:
    args = parse_args()
    dry_run = args.dry_run or not args.execute

    db = get_firestore_client()
    if not db:
        print("Firebase no está disponible en este entorno.")
        return 1

    targets = collect_target_docs(db, args.collection, args.year, args.category_id)

    year_label = str(args.year) if args.year else "todos los años"
    print(
        f"Encontrados {len(targets)} documento(s) en '{args.collection}' "
        f"para categoria_id={args.category_id}, año={year_label}."
    )

    for doc in targets[:10]:
        data = doc.to_dict() or {}
        print(
            f"  - {doc.id} | filename={data.get('filename')} | "
            f"year={data.get('year')} | zona={data.get('zona_id')} | "
            f"centro={data.get('centro')} | item={data.get('item')}"
        )
    if len(targets) > 10:
        print(f"  ... y {len(targets) - 10} más.")

    if dry_run:
        print("\nModo simulación: no se eliminó ningún documento.")
        print("Usa --execute para realizar el borrado real.")
        return 0

    if not targets:
        print("No hay documentos para eliminar.")
        return 0

    print(f"\n Estás a punto de eliminar {len(targets)} documento(s) de forma permanente.")
    confirm = input("Escribe BORRAR para confirmar la eliminación definitiva: ").strip()
    if confirm != "BORRAR":
        print("Operación cancelada.")
        return 1

    owner_uids_afectados = {
        (doc.to_dict() or {}).get("owner_uid") for doc in targets
    }
    owner_uids_afectados.discard(None)

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

    for uid in owner_uids_afectados:
        print(f"\n[RESUMEN] Reconstruyendo resumenes/{uid}...")
        reconstruir_resumen(db, uid)
        print("[RESUMEN] OK")

    print(f"Eliminados {deleted} documento(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
