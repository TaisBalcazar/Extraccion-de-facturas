"""
Script de backfill: genera el documento /resumenes/{uid} para cada usuario
a partir de las facturas ya existentes en Firestore.

Ejecutar UNA SOLA VEZ desde la raiz del proyecto:
    python backend/scripts/backfill_resumenes.py

Si necesitas re-ejecutarlo (ej. correccion de datos), ejecuta con --force
para sobreescribir resumenes existentes:
    python backend/scripts/backfill_resumenes.py --force
"""

import sys
import os

# Configura UTF-8 para evitar errores de encoding en Windows
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Agrega el backend al path para importar los modulos de la app
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.firebase import get_firestore_client, init_firebase
from app.services.resumen_service import reconstruir_resumen


def main():
    force = "--force" in sys.argv

    print("[*] Conectando a Firebase...")
    init_firebase()
    db = get_firestore_client()
    if not db:
        print("[ERROR] No se pudo conectar a Firebase. Verifica las credenciales.")
        sys.exit(1)

    print("[*] Buscando usuarios con facturas...")
    docs = db.collection("facturas").stream()

    owner_uids: set[str] = set()
    for doc in docs:
        data = doc.to_dict() or {}
        uid = data.get("owner_uid")
        if uid:
            owner_uids.add(uid)

    if not owner_uids:
        print("[!] No se encontraron facturas con owner_uid. Nada que hacer.")
        return

    print(f"[*] Usuarios encontrados: {len(owner_uids)}")

    for uid in owner_uids:
        resumen_ref = db.collection("resumenes").document(uid)
        ya_existe = resumen_ref.get().exists

        if ya_existe and not force:
            print(f"[skip] [{uid[:8]}...] Ya tiene resumen (usa --force para sobreescribir)")
            continue

        print(f"[...] [{uid[:8]}...] Reconstruyendo resumen...")
        try:
            resumen = reconstruir_resumen(db, uid)
            total = resumen.get("totales", {}).get("total_facturas", 0)
            monto = resumen.get("totales", {}).get("monto_global", 0.0)
            print(f"[OK]  [{uid[:8]}...] Listo — {total} facturas, ${monto:.2f} USD total")
        except Exception as exc:
            print(f"[ERR] [{uid[:8]}...] Error: {exc}")

    print("\n[OK] Backfill completado.")
    print("     El dashboard ahora puede usar GET /api/v1/dashboard (1 lectura por carga).")


if __name__ == "__main__":
    main()
