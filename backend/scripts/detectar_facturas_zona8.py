"""
Detecta facturas enlazadas a zonas afectadas por la migración de 8 → 7 zonas.

Zonas afectadas:
  - zona-8  (Zona 8 - DMQ): será ELIMINADA. Sus centros pasan a zona-2.
  - zona-2  (Zona 2 antigua): cambia de centros por completo.
            Antes: COCA, JOYA DE LOS SACHAS, TENA, CAYAMBE, SAN MIGUEL DE LOS BANCOS, EL CHACO
            Después: centros de Quito/DMQ

Si hay facturas en estas zonas deben ser reasignadas ANTES de ejecutar
el script de migración (migrar_zonas_7.py).

Ejecutar desde la carpeta backend/:
    python scripts/detectar_facturas_zona8.py
"""

import sys
import os
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.firebase import get_firestore_client, init_firebase

# Zonas que impacta la migración
ZONAS_AFECTADAS = {
    "zona-8": "Zona 8 - DMQ  →  será ELIMINADA (sus centros pasan a zona-2)",
    "zona-2": "Zona 2 antigua →  cambia de centros (Coca/Tena → Quito/DMQ)",
}

# A qué zona irá cada centro de las zonas afectadas después de la migración
REASIGNACION_SUGERIDA = {
    # Centros de zona-8 (DMQ) → zona-2 nueva
    "QUITO":               "zona-2",
    "QUITO-AMAGUAÑA":      "zona-2",
    "QUITO-CALDERÓN":      "zona-2",
    "QUITO-CARAPUNGO":     "zona-2",
    "QUITO-CARCELÉN":      "zona-2",
    "QUITO-MACHACHI":      "zona-2",
    "QUITO-SAN RAFAEL":    "zona-2",
    "QUITO-TUMBACO":       "zona-2",
    "QUITO-TURUBAMBA":     "zona-2",
    "QUITO-VILLAFLORA":    "zona-2",
    # Centros de zona-2 antigua → sus nuevas zonas
    "COCA":                    "zona-1",
    "JOYA DE LOS SACHAS":      "zona-1",
    "CAYAMBE":                 "zona-1",
    "SAN MIGUEL DE LOS BANCOS":"zona-4",
    "EL CHACO":                "zona-3",
    "TENA":                    "zona-3",
}


def main():
    print("=" * 65)
    print("  DETECCIÓN: Facturas en zonas afectadas por la migración")
    print("=" * 65)
    print()

    print("[*] Conectando a Firebase...")
    init_firebase()
    db = get_firestore_client()
    if not db:
        print("[ERROR] No se pudo conectar a Firebase.")
        sys.exit(1)

    # Buscar facturas en todas las colecciones de zonas afectadas
    resultados: dict[str, list[dict]] = defaultdict(list)
    total_docs = 0

    print("[*] Escaneando colección 'facturas'...\n")

    docs = db.collection("facturas").stream()
    for doc in docs:
        data = doc.to_dict() or {}
        zona_id = data.get("zona_id", "")
        if zona_id in ZONAS_AFECTADAS:
            resultados[zona_id].append({
                "id":           doc.id,
                "zona_id":      zona_id,
                "zona_nombre":  data.get("zona_nombre", "—"),
                "centro":       data.get("centro", "—"),
                "categoria_id": data.get("categoria_id", "—"),
                "item":         data.get("item", "—"),
                "owner_email":  data.get("owner_email", "—"),
                "filename":     data.get("filename", "—"),
                "year":         data.get("year", "—"),
            })
            total_docs += 1

    # ── Mostrar resultados ────────────────────────────────────────────
    if total_docs == 0:
        print("No se encontraron facturas en las zonas afectadas.")
        print("    Puedes ejecutar el script de migración sin riesgos.")
        return

    print(f"Se encontraron {total_docs} factura(s) en zonas afectadas:\n")

    for zona_id, facturas in resultados.items():
        descripcion = ZONAS_AFECTADAS[zona_id]
        print(f"  {'─'*60}")
        print(f"  {zona_id.upper()}  —  {descripcion}")
        print(f"  Total facturas: {len(facturas)}")
        print(f"  {'─'*60}")

        # Agrupar por centro para mejor lectura
        por_centro: dict[str, list[dict]] = defaultdict(list)
        for f in facturas:
            por_centro[f["centro"]].append(f)

        for centro, items in sorted(por_centro.items()):
            nueva_zona = REASIGNACION_SUGERIDA.get(centro, "⚠️  revisar manualmente")
            print(f"\n Centro: {centro} -> reasignar a {nueva_zona}")
            print(f"    Facturas: {len(items)}")
            for f in items:
                print(
                    f"      • [{f['id'][:16]}...]  "
                    f"cat={f['categoria_id']}  "
                    f"año={f['year']}  "
                    f"archivo={f['filename']}"
                )
        print()

    # ── Resumen accionable ────────────────────────────────────────────
    print("=" * 65)
    print("  ACCIÓN REQUERIDA antes de ejecutar migrar_zonas_7.py")
    print("=" * 65)
    print()
    print("  Opción A (recomendada): Reasignar las facturas usando la")
    print("  consola de Firebase o creando un script adicional que")
    print("  actualice el campo zona_id y zona_nombre en cada documento.")
    print()
    print("  Opción B: Ejecutar la migración de todas formas. Las")
    print("  facturas mantendrán el zona_id antiguo pero el dashboard")
    print("  puede mostrar la zona incorrecta hasta que se corrijan.")
    print()

    # Guardar reporte en archivo
    reporte_path = os.path.join(os.path.dirname(__file__), "reporte_zonas_afectadas.txt")
    with open(reporte_path, "w", encoding="utf-8") as fh:
        fh.write(f"Facturas en zonas afectadas: {total_docs}\n\n")
        for zona_id, facturas in resultados.items():
            fh.write(f"\n{zona_id} — {ZONAS_AFECTADAS[zona_id]}\n")
            fh.write(f"Total: {len(facturas)}\n")
            for f in facturas:
                fh.write(
                    f"  id={f['id']}  centro={f['centro']}  "
                    f"cat={f['categoria_id']}  año={f['year']}  "
                    f"archivo={f['filename']}  email={f['owner_email']}\n"
                )

    print(f"Reporte guardado en: {reporte_path}")


if __name__ == "__main__":
    main()
