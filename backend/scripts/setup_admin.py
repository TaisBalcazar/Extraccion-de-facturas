"""
Asigna el rol "admin" al usuario UTPL Sostenible en Firestore (users/{uid}).

Ejecutar desde la carpeta backend/:
    python scripts/setup_admin.py
"""

import sys
import os

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.firebase import get_firestore_client, init_firebase

ADMIN_UID = "GSmOljJ3ROQhOe9EppQCh7MXU9Y2"
ADMIN_EMAIL = "utplsostenible@gmail.com"


def main():
    print("=" * 55)
    print("  SETUP: Asignar rol admin")
    print("=" * 55)
    print()
    print(f"  UID:   {ADMIN_UID}")
    print(f"  Email: {ADMIN_EMAIL}")
    print(f"  Rol a asignar: admin")
    print()
    print("Esto escribira (merge=True, sin borrar otros campos existentes):")
    print(f'  users/{ADMIN_UID} = {{"role": "admin", "email": "{ADMIN_EMAIL}"}}')
    print()

    resp = input("¿Continuar? (S/N): ").strip().lower()
    if resp != "s":
        print("Operación cancelada.")
        sys.exit(0)

    print()
    print("[*] Conectando a Firebase...")
    init_firebase()
    db = get_firestore_client()
    if not db:
        print("[ERROR] No se pudo conectar a Firebase.")
        sys.exit(1)

    print(f"[*] Escribiendo users/{ADMIN_UID}...")
    db.collection("users").document(ADMIN_UID).set(
        {"role": "admin", "email": ADMIN_EMAIL},
        merge=True,
    )

    print()
    print(f"Listo. users/{ADMIN_UID} ahora tiene role='admin'.")


if __name__ == "__main__":
    main()
