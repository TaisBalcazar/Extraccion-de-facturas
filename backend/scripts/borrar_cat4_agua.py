"""
borrar_cat4_agua.py
Elimina TODOS los documentos de agua potable (cat-4 / item "Consumo de agua")
de Firestore en lotes de 500.

Modos:
    python scripts/borrar_cat4_agua.py            → simulación (no borra nada)
    python scripts/borrar_cat4_agua.py --execute  → borra (pide confirmación)

Ejecutar SIEMPRE después de revisar dry_run_cat4_agua.py.
Ejecutar ANTES de recargar_cat4_agua.py.
"""

from __future__ import annotations
import argparse
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from google.cloud.firestore_v1.base_query import FieldFilter  # noqa: E402
from app.core.firebase import get_firestore_client             # noqa: E402

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURACIÓN
# ─────────────────────────────────────────────────────────────────────────────

OWNER_UID  = "GSmOljJ3ROQhOe9EppQCh7MXU9Y2"
BATCH_SIZE = 500


def _es_agua(data: dict) -> bool:
    item = str(data.get("item") or "").strip().lower()
    return "agua" in item


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Borra documentos de agua potable (cat-4) de Firestore."
    )
    parser.add_argument("--execute", action="store_true", help="Realiza el borrado real.")
    parser.add_argument("--dry-run", action="store_true", help="Fuerza simulación (por defecto).")
    args = parser.parse_args()
    dry_run = args.dry_run or not args.execute

    db = get_firestore_client()
    if not db:
        print("[ERROR] Firebase no disponible.")
        return 1

    print("[*] Consultando documentos de agua (cat-4)...")
    all_docs = list(
        db.collection("facturas")
        .where(filter=FieldFilter("owner_uid",    "==", OWNER_UID))
        .where(filter=FieldFilter("categoria_id", "==", "cat-4"))
        .stream()
    )
    targets = [d for d in all_docs if _es_agua(d.to_dict() or {})]

    print(f"[*] Documentos de agua encontrados: {len(targets)}")

    if not targets:
        print("[INFO] Nada que borrar.")
        return 0

    # Vista previa (primeros 5)
    for doc in targets[:5]:
        data = doc.to_dict() or {}
        print(
            f"  - {doc.id[:20]}… | "
            f"year={data.get('year')} | "
            f"mes={data.get('mes_numero')} | "
            f"medidor={data.get('medidor')}"
        )
    if len(targets) > 5:
        print(f"  ... y {len(targets) - 5} más.")

    if dry_run:
        print(f"\n[DRY-RUN] Se eliminarían {len(targets)} documentos. (sin cambios)")
        print("          Usa --execute para borrar de verdad.")
        return 0

    print(f"\n Estás a punto de borrar {len(targets)} documentos de forma PERMANENTE.")
    confirm = input("Escribe BORRAR para confirmar: ").strip()
    if confirm != "BORRAR":
        print("[!] Cancelado.")
        return 1

    deleted = 0
    for i in range(0, len(targets), BATCH_SIZE):
        batch = db.batch()
        chunk = targets[i : i + BATCH_SIZE]
        for doc in chunk:
            batch.delete(doc.reference)
        batch.commit()
        deleted += len(chunk)
        print(f"  Eliminados {deleted}/{len(targets)}...")

    print(f"\n {deleted} documentos de agua eliminados.")
    print("  Ahora ejecuta recargar_cat4_agua.py --execute")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
