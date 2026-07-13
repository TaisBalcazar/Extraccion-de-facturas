"""
Borra los 12 registros cat-1 subidos erróneamente con nro_factura="209".

El número "209" fue capturado del texto "Resolución No. 209" del encabezado
de la EERSSA en lugar del número real de factura. Todos tienen campos vacíos.

Modo simulación (por defecto):
    python scripts/delete_cat1_erroneos_209.py

Borrado real:
    python scripts/delete_cat1_erroneos_209.py --execute
"""

from __future__ import annotations

import sys
import os
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.firebase import get_firestore_client, init_firebase  # noqa: E402
from app.services.resumen_service import reconstruir_resumen       # noqa: E402
from google.cloud.firestore_v1.base_query import FieldFilter        # noqa: E402

OWNER_UID    = "GSmOljJ3ROQhOe9EppQCh7MXU9Y2"
CATEGORIA_ID = "cat-1"
NRO_FACTURA  = "209"


def main() -> int:
    dry_run = "--execute" not in sys.argv

    print("=" * 60)
    print("  Borrado de registros cat-1 erróneos (nro_factura=209)")
    print("=" * 60)
    if dry_run:
        print("  MODO: DRY-RUN — usa --execute para borrar de verdad\n")

    init_firebase()
    db = get_firestore_client()
    if not db:
        print("[ERROR] No se pudo conectar a Firebase.")
        return 1

    docs = list(
        db.collection("facturas")
        .where(filter=FieldFilter("owner_uid",    "==", OWNER_UID))
        .where(filter=FieldFilter("categoria_id", "==", CATEGORIA_ID))
        .where(filter=FieldFilter("nro_factura",  "==", NRO_FACTURA))
        .stream()
    )

    print(f"Encontrados: {len(docs)} documento(s) con nro_factura='{NRO_FACTURA}' en {CATEGORIA_ID}\n")

    for doc in docs:
        data = doc.to_dict() or {}
        print(
            f"  {doc.id} | item={data.get('item')} | "
            f"zona={data.get('zona_id')} | centro={data.get('centro')} | "
            f"year={data.get('year')} | mes={data.get('mes_nombre')} | "
            f"filename={data.get('filename')}"
        )

    if dry_run:
        print(f"\nModo simulación: no se eliminó nada. Usa --execute para borrar.")
        return 0

    if not docs:
        print("Nada que eliminar.")
        return 0

    confirm = input(
        f"\n¿Eliminar {len(docs)} documento(s) de forma permanente? "
        "Escribe BORRAR para confirmar: "
    ).strip()
    if confirm != "BORRAR":
        print("Operación cancelada.")
        return 1

    batch = db.batch()
    for doc in docs:
        batch.delete(doc.reference)
    batch.commit()

    print(f"\n[RESUMEN] Reconstruyendo resumenes/{OWNER_UID}...")
    reconstruir_resumen(db, OWNER_UID)
    print("[RESUMEN] OK")

    print(f"{len(docs)} documento(s) eliminado(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
