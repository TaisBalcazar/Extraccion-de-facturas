"""
Elimina todas las facturas enlazadas a zona-8 y actualiza el resumen.

Ejecutar desde la carpeta backend/:
    python scripts/borrar_facturas_zona8.py

Agregar --force para omitir la confirmación interactiva.
"""

import sys
import os

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from google.cloud.firestore_v1.base_query import FieldFilter
from app.core.firebase import get_firestore_client, init_firebase
from app.services.resumen_service import actualizar_resumen

ZONA_ID = "zona-8"


def main():
    force = "--force" in sys.argv

    print("=" * 55)
    print("  BORRADO: Facturas de zona-8")
    print("=" * 55)
    print()

    print("[*] Conectando a Firebase...")
    init_firebase()
    db = get_firestore_client()
    if not db:
        print("[ERROR] No se pudo conectar a Firebase.")
        sys.exit(1)

    # Buscar facturas
    docs = list(
        db.collection("facturas")
        .where(filter=FieldFilter("zona_id", "==", ZONA_ID))
        .stream()
    )

    if not docs:
        print(f"[OK] No hay facturas con zona_id='{ZONA_ID}'. Nada que hacer.")
        return

    print(f"[!] Se encontraron {len(docs)} factura(s) con zona_id='{ZONA_ID}':\n")
    for doc in docs:
        data = doc.to_dict() or {}
        print(
            f"     • {doc.id}  |  centro={data.get('centro', '—')}  "
            f"|  cat={data.get('categoria_id', '—')}  "
            f"|  año={data.get('year', '—')}  "
            f"|  archivo={data.get('filename', '—')}"
        )

    print()

    if not force:
        resp = input(f"¿Eliminar estas {len(docs)} factura(s)? (s/N): ").strip().lower()
        if resp != "s":
            print("Operación cancelada.")
            sys.exit(0)
        print()

    eliminadas = 0
    errores = 0

    for doc in docs:
        data = doc.to_dict() or {}
        owner_uid = data.get("owner_uid", "")
        filename = data.get("filename", doc.id)

        try:
            # Actualizar resumen antes de borrar (igual que el endpoint DELETE)
            if owner_uid:
                try:
                    actualizar_resumen(db, owner_uid, data, signo=-1)
                except Exception as exc_res:
                    print(f"  [WARN] No se pudo actualizar resumen para {doc.id}: {exc_res}")

            db.collection("facturas").document(doc.id).delete()
            print(f"  [OK] Eliminada: {doc.id}  ({filename})")
            eliminadas += 1

        except Exception as exc:
            print(f"  [ERR] Error eliminando {doc.id}: {exc}")
            errores += 1

    print()
    print(f"[OK] Listo — {eliminadas} eliminada(s), {errores} error(es).")

    if errores == 0:
        print()
        print("Ahora puedes ejecutar el script de migración:")
        print("    python scripts/migrar_zonas_7.py")


if __name__ == "__main__":
    main()
