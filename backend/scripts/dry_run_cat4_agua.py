"""
dry_run_cat4_agua.py
Inspección previa a la limpieza y recarga de facturas de agua (cat-4).

Cuenta cuántos documentos existen en Firestore para cat-4 / "Consumo de agua",
muestra una muestra de 3 y diagnostica campos sucios o ausentes.
No borra ni escribe nada.

Uso:
    cd backend
    python scripts/dry_run_cat4_agua.py
"""

from __future__ import annotations
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

OWNER_UID = "GSmOljJ3ROQhOe9EppQCh7MXU9Y2"


def _es_agua(data: dict) -> bool:
    item = str(data.get("item") or "").strip().lower()
    return "agua" in item


def main() -> int:
    db = get_firestore_client()
    if not db:
        print("[ERROR] Firebase no disponible.")
        return 1

    print("[*] Consultando facturas cat-4 en Firestore...")
    all_docs = list(
        db.collection("facturas")
        .where(filter=FieldFilter("owner_uid",    "==", OWNER_UID))
        .where(filter=FieldFilter("categoria_id", "==", "cat-4"))
        .stream()
    )

    agua_docs = [d for d in all_docs if _es_agua(d.to_dict() or {})]

    print(f"\n{'='*57}")
    print(f"  Total docs cat-4 encontrados         : {len(all_docs)}")
    print(f"  Total docs cat-4 AGUA (item agua)    : {len(agua_docs)}")
    print(f"{'='*57}")

    if not agua_docs:
        print("\n[INFO] No hay documentos de agua para migrar.")
        return 0

    # Muestra de 3 documentos
    print(f"\n--- Muestra de {min(3, len(agua_docs))} documento(s) ---\n")
    for doc in agua_docs[:3]:
        data = doc.to_dict() or {}
        print(f"  ID            : {doc.id}")
        print(f"  year          : {data.get('year')}")
        print(f"  mes_nombre    : {data.get('mes_nombre')}")
        print(f"  medidor       : {data.get('medidor')}")
        print(f"  item          : {data.get('item')}")
        print(f"  total_facturado: {data.get('total_facturado')}")
        print(f"  consumo_m3    : {data.get('consumo_m3')}")
        print(f"  tipo_documento: {data.get('tipo_documento', '(no presente)')}")
        print(f"  estado_medidor: {data.get('estado_medidor', '(no presente)')}")
        print(f"  factura_numero: {data.get('factura_numero', '(no presente)')}")
        print(f"  fecha_emision : {data.get('fecha_emision', '(no presente)')}")
        print()

    # Diagnóstico de campos sucios / ausentes
    dicts = [d.to_dict() or {} for d in agua_docs]

    sin_year         = sum(1 for d in dicts if not d.get("year"))
    sin_medidor      = sum(1 for d in dicts if not d.get("medidor"))
    con_tipo_doc     = sum(1 for d in dicts if "tipo_documento" in d)
    sin_estado_med   = sum(1 for d in dicts if not d.get("estado_medidor"))
    sin_fecha_emis   = sum(1 for d in dicts if not d.get("fecha_emision"))
    sin_factura_num  = sum(1 for d in dicts if not d.get("factura_numero"))
    sin_hash         = sum(1 for d in dicts if not d.get("hash_factura"))

    print("--- Diagnóstico de campos ---")
    print(f"  Sin 'year'                               : {sin_year}")
    print(f"  Sin 'medidor'                            : {sin_medidor}")
    print(f"  Con 'tipo_documento' (campo a eliminar)  : {con_tipo_doc}")
    print(f"  Sin 'estado_medidor' (campo nuevo)       : {sin_estado_med}")
    print(f"  Sin 'fecha_emision'                      : {sin_fecha_emis}")
    print(f"  Sin 'factura_numero'                     : {sin_factura_num}")
    print(f"  Sin 'hash_factura' (deduplicación rota)  : {sin_hash}")

    print(f"\n[OK] Dry-run completado. Ningún dato modificado.")
    print(
        f"     Ejecuta borrar_cat4_agua.py --execute "
        f"para borrar los {len(agua_docs)} documentos."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
