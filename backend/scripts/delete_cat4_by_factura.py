"""
Borra documentos cat-4 específicos por factura_numero.

Modo simulación (por defecto):
    python scripts/delete_cat4_by_factura.py

Borrado real:
    python scripts/delete_cat4_by_factura.py --execute
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.firebase import get_firestore_client, init_firebase  # noqa: E402
from app.services.resumen_service import reconstruir_resumen       # noqa: E402
from google.cloud.firestore_v1.base_query import FieldFilter        # noqa: E402

OWNER_UID = "GSmOljJ3ROQhOe9EppQCh7MXU9Y2"

FACTURAS_A_BORRAR = [
    "057-017-000108870",  # Enero 2025 — estado_medidor no extraído correctamente
]


def main() -> int:
    dry_run = "--execute" not in sys.argv

    print("=" * 60)
    print("  Borrado puntual de facturas cat-4 erróneas")
    print("=" * 60)
    if dry_run:
        print("  MODO: DRY-RUN — usa --execute para borrar de verdad\n")

    init_firebase()
    db = get_firestore_client()
    if not db:
        print("[ERROR] No se pudo conectar a Firebase.")
        return 1

    encontrados: list = []
    for nro in FACTURAS_A_BORRAR:
        docs = list(
            db.collection("facturas")
            .where(filter=FieldFilter("owner_uid",       "==", OWNER_UID))
            .where(filter=FieldFilter("categoria_id",    "==", "cat-4"))
            .where(filter=FieldFilter("factura_numero",  "==", nro))
            .stream()
        )
        if docs:
            encontrados.extend(docs)
            for d in docs:
                data = d.to_dict() or {}
                print(
                    f"  Encontrado: {d.id} | factura_numero={data.get('factura_numero')} | "
                    f"mes={data.get('mes_nombre')} {data.get('year')} | "
                    f"medidor={data.get('medidor')} | "
                    f"estado_medidor={data.get('estado_medidor')}"
                )
        else:
            print(f"  No encontrado: factura_numero={nro}")

    print(f"\nTotal a eliminar: {len(encontrados)} documento(s)")

    if dry_run:
        print("\nModo simulación: no se eliminó nada. Usa --execute para borrar.")
        return 0

    if not encontrados:
        print("Nada que eliminar.")
        return 0

    confirm = input(
        f"\n¿Eliminar {len(encontrados)} documento(s) de forma permanente? "
        "Escribe BORRAR para confirmar: "
    ).strip()
    if confirm != "BORRAR":
        print("Operación cancelada.")
        return 1

    batch = db.batch()
    for doc in encontrados:
        batch.delete(doc.reference)
    batch.commit()

    print(f"\n[RESUMEN] Reconstruyendo resumenes/{OWNER_UID}...")
    reconstruir_resumen(db, OWNER_UID)
    print("[RESUMEN] OK")

    print(f"{len(encontrados)} documento(s) eliminado(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
