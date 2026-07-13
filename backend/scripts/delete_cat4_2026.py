"""Elimina ingresos/facturas de la categoría 4 para un año dado.

Uso por defecto:
    python scripts/delete_cat4_2026.py --dry-run

Ejecución real:
    python scripts/delete_cat4_2026.py --execute

Opcionalmente se puede cambiar el año o la categoría:
    python scripts/delete_cat4_2026.py --year 2026 --category-id cat-4 --execute
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


DEFAULT_YEAR = 2026
DEFAULT_CATEGORY_ID = "cat-4"
DEFAULT_COLLECTION = "facturas"
BATCH_SIZE = 450


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Borra documentos de Firestore por año y categoría."
    )
    parser.add_argument("--year", type=int, default=DEFAULT_YEAR, help="Año a eliminar")
    parser.add_argument(
        "--category-id",
        default=DEFAULT_CATEGORY_ID,
        help="ID de categoría a eliminar (por defecto cat-4)",
    )
    parser.add_argument(
        "--collection",
        default=DEFAULT_COLLECTION,
        help="Colección de Firestore a revisar (por defecto facturas)",
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


def collect_target_docs(db, collection_name: str, year: int, category_id: str):
    query = (
        db.collection(collection_name)
        .where(filter=FieldFilter("year", "==", year))
        .where(filter=FieldFilter("categoria_id", "==", category_id))
    )
    return list(query.stream())


def main() -> int:
    args = parse_args()
    dry_run = args.dry_run or not args.execute

    db = get_firestore_client()
    if not db:
        print("Firebase no está disponible en este entorno.")
        return 1

    targets = collect_target_docs(db, args.collection, args.year, args.category_id)

    print(
        f"Encontrados {len(targets)} documento(s) en '{args.collection}' "
        f"para year={args.year} y categoria_id={args.category_id}."
    )

    for doc in targets[:10]:
        data = doc.to_dict() or {}
        print(
            f"- {doc.id} | filename={data.get('filename')} | "
            f"fecha_emision={data.get('fecha_emision')} | total={data.get('total') or data.get('valor_total')}"
        )

    if dry_run:
        print("Modo simulación: no se eliminó ningún documento.")
        return 0

    if not targets:
        print("No hay documentos para eliminar.")
        return 0

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