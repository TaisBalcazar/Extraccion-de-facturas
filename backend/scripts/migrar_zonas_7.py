"""
Migración de zonas: de 8 zonas a 7 zonas.

Cambios principales:
  - Zona 2 pasa a ser DMQ (antes era Zona 8)
  - Los centros de la antigua Zona 2 se redistribuyen:
      CAYAMBE, COCA, JOYA DE LOS SACHAS → Zona 1
      EL CHACO, TENA                     → Zona 3
      SAN MIGUEL DE LOS BANCOS           → Zona 4
  - Zona 4 absorbe también: BABAHOYO, BALZAR, DAULE (antes Zona 5)
  - Zona 5 gana LA TRONCAL (antes Zona 6), pierde BABAHOYO/BALZAR/DAULE
  - Zona 6 pierde GUALAQUIZA (→ Zona 7) y LA TRONCAL (→ Zona 5)
  - Zona 7 gana GUALAQUIZA
  - zona-8 se elimina

Ejecutar desde la raíz del proyecto backend:
    python backend/scripts/migrar_zonas_7.py

Agregar --force para omitir la confirmación interactiva.
"""

import sys
import os

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.firebase import get_firestore_client, init_firebase

NUEVAS_ZONAS = [
    {
        "id": "zona-1",
        "nombre": "Zona 1",
        "numero": 1,
        "centros": [
            "CAYAMBE", "COCA", "IBARRA", "JOYA DE LOS SACHAS", "NUEVA LOJA",
            "OTAVALO", "SANGABRIEL", "SHUSHUFINDI", "TULCAN",
        ],
    },
    {
        "id": "zona-2",
        "nombre": "Zona 2 - DMQ",
        "numero": 2,
        "centros": [
            "QUITO", "QUITO-AMAGUAÑA", "QUITO-CALDERÓN", "QUITO-CARAPUNGO",
            "QUITO-CARCELÉN", "QUITO-MACHACHI", "QUITO-SAN RAFAEL",
            "QUITO-TUMBACO", "QUITO-TURUBAMBA", "QUITO-VILLAFLORA",
        ],
    },
    {
        "id": "zona-3",
        "nombre": "Zona 3",
        "numero": 3,
        "centros": [
            "ALAUSÍ", "AMBATO", "EL CHACO", "GUARANDA", "LATACUNGA",
            "PELILEO", "PUYO", "RIOBAMBA", "TENA",
        ],
    },
    {
        "id": "zona-4",
        "nombre": "Zona 4",
        "numero": 4,
        "centros": [
            "BAHÍA DE CARAQUEZ", "CALCETA", "CHONE", "ESMERALDAS", "LA CONCORDIA",
            "MANTA", "PEDERNALES", "PORTOVIEJO", "QUININDÉ", "SAN MIGUEL DE LOS BANCOS",
            "SANTO DOMINGO", "BABAHOYO", "BALZAR", "DAULE",
        ],
    },
    {
        "id": "zona-5",
        "nombre": "Zona 5",
        "numero": 5,
        "centros": [
            "DURÁN", "GALÁPAGOS - SAN CRISTOBAL", "GALÁPAGOS - SANTA CRUZ",
            "GUASMO", "GUAYAQUIL - CENTENARIO", "GUAYAQUIL (Kennedy)",
            "GUAYAQUIL-SUR OESTE", "LA TRONCAL", "MILAGRO", "NARANJAL",
            "PLAYAS", "QUEVEDO", "QUINSALOMA", "SALINAS", "SAMANES", "SAMBORONDÓN",
        ],
    },
    {
        "id": "zona-6",
        "nombre": "Zona 6",
        "numero": 6,
        "centros": [
            "AZOGUES", "CAÑAR", "CJG CUENCA", "CUENCA", "GUALACEO",
            "LIMÓN INDANZA", "MACAS", "MENDÉZ", "MONAY", "PAUTE",
            "SANTA ISABEL", "SUCUA",
        ],
    },
    {
        "id": "zona-7",
        "nombre": "Zona 7",
        "numero": 7,
        "centros": [
            "ALAMOR", "BALSAS", "CARIAMANGA", "CATACOCHA", "CATAMAYO", "CELICA",
            "GUALAQUIZA", "HUAQUILLAS", "LOJA", "MACARÁ", "MACHALA", "MADRID",
            "NEW YORK", "PASAJE", "PIÑAS", "ROMA", "SANTA ROSA", "SARAGURO",
            "YANZATZA", "ZAMORA", "ZARUMA", "ZUMBA",
        ],
    },
]

ID_A_ELIMINAR = "zona-8"


def main():
    force = "--force" in sys.argv

    print("=" * 60)
    print("  MIGRACIÓN: Reducción de 8 zonas a 7 zonas")
    print("=" * 60)
    print()

    if not force:
        print("Este script realizará los siguientes cambios en Firestore:")
        print(f"  • Actualizar zonas: zona-1 a zona-7 (centros nuevos)")
        print(f"  • Eliminar: {ID_A_ELIMINAR} (DMQ ahora es zona-2)")
        print()
        resp = input("¿Continuar? (s/N): ").strip().lower()
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

    # Actualizar/crear cada zona nueva
    for zona in NUEVAS_ZONAS:
        ref = db.collection("zonas").document(zona["id"])
        snap = ref.get()
        accion = "Actualizado" if snap.exists else "Creado"
        ref.set(
            {
                "nombre": zona["nombre"],
                "numero": zona["numero"],
                "centros": zona["centros"],
                "is_system": True,
            },
            merge=False,
        )
        print(f"[OK] {accion}: {zona['id']} — {zona['nombre']} ({len(zona['centros'])} centros)")

    # Eliminar zona-8
    ref8 = db.collection("zonas").document(ID_A_ELIMINAR)
    if ref8.get().exists:
        ref8.delete()
        print(f"[OK] Eliminado: {ID_A_ELIMINAR}")
    else:
        print(f"[--] {ID_A_ELIMINAR} no existía, nada que eliminar")

    print()
    print("[OK] Migración completada.")
    print()
    print("AVISO: Las facturas ya subidas que tengan zona_id='zona-8' o")
    print("       zona_id='zona-2' (antigua) mantendrán su zona original.")
    print("       Si necesitas reasignarlas, hazlo manualmente o con otro script.")


if __name__ == "__main__":
    main()
