"""
importar_historico_cat4_agua.py
Importa datos históricos de agua potable (cat-4) desde el Excel de base de datos.

Excel fuente:
    C:\\Users\\Smart\\Documents\\UTPL\\Documentos sistema\\24_OCT_Agua_Base_de_Datos.xlsx

ID determinista por documento: cat4_{medidor}_{year}_{mes:02d}
  → Ejemplo: cat4_22357_2018_01

No sobreescribe documentos que ya existan.
Importa todos los registros del Excel sin filtrar por catálogo ni razón social.

Modos:
    cd backend
    python scripts/importar_historico_cat4_agua.py            → simulación (sin cambios)
    python scripts/importar_historico_cat4_agua.py --execute  → escribe en Firestore
"""

from __future__ import annotations
import argparse
import hashlib
import re
import sys
from datetime import datetime
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

try:
    import openpyxl
except ImportError:
    print("[ERROR] openpyxl no instalado. Ejecuta: pip install openpyxl")
    sys.exit(1)

from app.core.firebase import get_firestore_client  # noqa: E402
from app.services.resumen_service import reconstruir_resumen  # noqa: E402
from app.utils.validaciones import normalizar_centro  # noqa: E402

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURACIÓN
# ─────────────────────────────────────────────────────────────────────────────

EXCEL_PATH = r"C:\Users\Smart\Documents\UTPL\Documentos sistema\24_OCT_Agua_Base_de_Datos.xlsx"

OWNER_UID        = "GSmOljJ3ROQhOe9EppQCh7MXU9Y2"
OWNER_EMAIL      = "utplsostenible@gmail.com"
ZONA_ID          = "zona-7"
ZONA_NOMBRE      = "Zona 7"
CATEGORIA_ID     = "cat-4"
CATEGORIA_NOMBRE = "Categoría 4"
ITEM             = "Consumo de agua"

BATCH_SIZE = 500

# Mapeo de columna Excel → índice (basado en inspección del archivo)
COL = {
    "year":                    0,
    "mes_numero_raw":          1,   # '01_ENE', '02_FEB', …
    "mes_nombre":              2,   # 'Enero', 'Febrero', …
    "zona":                    3,   # ignorado (usamos ZONA_ID/ZONA_NOMBRE fijos)
    "provincia":               4,   # ignorado
    "centro":                  5,   # 'Loja'
    "medidor":                 6,
    "status":                  7,   # 'Activo' / 'Inactivo'
    "categoria":               8,
    "ubicacion":               9,
    "lectura_anterior":       10,
    "lectura_actual":         11,
    "consumo_m3":             12,
    "agua_potable":           13,
    "recoleccion_basura":     14,
    "costo_basico_facturacion": 15,
    "proteccion_microcuencas": 16,
    "seguridad_ciudadana":    17,
    "aportes_planes_maestros": 18,
    "alcantarillado":         19,
    "interes_recargo":        20,
    "total_facturado":        21,
    # cols 22-30 (x, y, Verificación, Comprobación, None…) → ignoradas
}

# Estado del medidor: Excel → esquema canónico
STATUS_MAP: dict[str, str] = {
    "activo":   "Funcionando",
    "inactivo": "Inactivo",
}

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _to_float(val) -> float | None:
    if val is None:
        return None
    try:
        return float(str(val).replace(",", ".").strip())
    except (ValueError, TypeError):
        return None


def _to_int(val) -> int | None:
    f = _to_float(val)
    return int(f) if f is not None else None


def _parse_mes_numero(val) -> int | None:
    """Convierte '01_ENE', '1', 1, etc. → entero 1-12."""
    if val is None:
        return None
    m = re.match(r"(\d+)", str(val).strip())
    return int(m.group(1)) if m else None


def _map_status(val) -> str | None:
    """'Activo' → 'Funcionando', 'Inactivo' → 'Suspendido'."""
    if val is None:
        return None
    return STATUS_MAP.get(str(val).strip().lower())


def _doc_id(medidor: str, year: int, mes_numero: int) -> str:
    return f"cat4_{medidor}_{year}_{mes_numero:02d}"


def _hash_historico(medidor: str, year: int, mes_numero: int) -> str:
    """Hash determinista para históricos (sin número de factura ni fecha de emisión)."""
    clave = f"historico:cat4:{medidor}:{year}:{mes_numero:02d}"
    return hashlib.md5(clave.encode()).hexdigest()


def _cell(row: tuple, col_idx: int):
    return row[col_idx] if col_idx < len(row) else None


# ─────────────────────────────────────────────────────────────────────────────
# Construcción del documento
# ─────────────────────────────────────────────────────────────────────────────

def _build_doc(row: tuple) -> dict | None:
    """
    Construye el documento Firestore a partir de una fila del Excel.
    Devuelve None si los campos mínimos (year, mes_numero, medidor) faltan.
    """
    year       = _to_int(_cell(row, COL["year"]))
    mes_numero = _parse_mes_numero(_cell(row, COL["mes_numero_raw"]))
    medidor    = str(_cell(row, COL["medidor"]) or "").strip()
    medidor    = re.sub(r"\D", "", medidor)  # solo dígitos

    if not year or not mes_numero or not medidor:
        return None

    mes_nombre = str(_cell(row, COL["mes_nombre"]) or "").strip() or None
    centro     = normalizar_centro(str(_cell(row, COL["centro"]) or "").strip()) or None
    status     = _map_status(_cell(row, COL["status"]))
    categoria  = str(_cell(row, COL["categoria"]) or "").strip() or None
    ubicacion  = str(_cell(row, COL["ubicacion"]) or "").strip() or None

    doc: dict = {
        # Clasificación (equivalente a selección en pantalla de evidencias)
        "categoria_id":      CATEGORIA_ID,
        "categoria_nombre":  CATEGORIA_NOMBRE,
        "zona_id":           ZONA_ID,
        "zona_nombre":       ZONA_NOMBRE,
        "item":              ITEM,
        "centro":            centro or "LOJA",

        # Identificación del propietario
        "owner_uid":   OWNER_UID,
        "owner_email": OWNER_EMAIL,
        "upload_date": datetime.now().isoformat(),

        # Tiempo
        "year":       year,
        "mes_numero": mes_numero,
        "mes_nombre": mes_nombre,

        # Medidor
        "medidor":        medidor,
        "estado_medidor": status,
        "categoria":      categoria,
        "ubicacion":      ubicacion,

        # Consumo
        "lectura_anterior": _to_float(_cell(row, COL["lectura_anterior"])),
        "lectura_actual":   _to_float(_cell(row, COL["lectura_actual"])),
        "consumo_m3":       _to_float(_cell(row, COL["consumo_m3"])),

        # Costos
        "agua_potable":              _to_float(_cell(row, COL["agua_potable"])),
        "recoleccion_basura":        _to_float(_cell(row, COL["recoleccion_basura"])),
        "costo_basico_facturacion":  _to_float(_cell(row, COL["costo_basico_facturacion"])),
        "proteccion_microcuencas":   _to_float(_cell(row, COL["proteccion_microcuencas"])),
        "seguridad_ciudadana":       _to_float(_cell(row, COL["seguridad_ciudadana"])),
        "aportes_planes_maestros":   _to_float(_cell(row, COL["aportes_planes_maestros"])),
        "alcantarillado":            _to_float(_cell(row, COL["alcantarillado"])),
        "interes_recargo":           _to_float(_cell(row, COL["interes_recargo"])),
        "total_facturado":           _to_float(_cell(row, COL["total_facturado"])),

        # Metadata histórica (sin factura PDF asociada)
        "filename":       "historico_excel_2018_2024",
        "hash_factura":   _hash_historico(medidor, year, mes_numero),
        # factura_numero y fecha_emision se omiten (None → filtrado abajo)
        "factura_numero": None,
        "fecha_emision":  None,
    }

    # Eliminar None para no contaminar Firestore
    return {k: v for k, v in doc.items() if v is not None}


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Importa histórico de agua potable (cat-4) desde Excel a Firestore."
    )
    parser.add_argument("--execute", action="store_true", help="Escribe en Firestore.")
    parser.add_argument("--dry-run", action="store_true", help="Solo simula (por defecto).")
    args = parser.parse_args()
    dry_run = args.dry_run or not args.execute

    excel_path = Path(EXCEL_PATH)
    if not excel_path.exists():
        print(f"[ERROR] Excel no encontrado: {EXCEL_PATH}")
        return 1

    print(f"[*] Leyendo: {excel_path.name}")
    wb = openpyxl.load_workbook(excel_path, data_only=True, read_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    wb.close()

    data_rows = rows[1:]  # saltar encabezado
    print(f"[*] Filas de datos: {len(data_rows)}")
    if dry_run:
        print("    MODO DRY-RUN: no se escribirá nada en Firestore.\n")

    db = get_firestore_client() if not dry_run else None
    if not dry_run and not db:
        print("[ERROR] Firebase no disponible.")
        return 1

    # Pre-cargar IDs existentes para verificar sin query por cada fila
    ids_existentes: set[str] = set()
    if not dry_run:
        print("[*] Cargando IDs existentes en cat-4 agua...")
        existentes = (
            db.collection("facturas")
            .where("owner_uid",    "==", OWNER_UID)
            .where("categoria_id", "==", CATEGORIA_ID)
            .where("item",         "==", ITEM)
            .stream()
        )
        for doc in existentes:
            ids_existentes.add(doc.id)
        print(f"    Docs ya existentes: {len(ids_existentes)}")

    # Procesar filas
    pendientes:           list[tuple[str, dict]] = []   # (doc_id, doc_data)
    saltados_vacios:      int = 0
    saltados_año:         int = 0
    saltados_existentes:  int = 0

    for i, row in enumerate(data_rows, start=2):
        doc = _build_doc(row)
        if doc is None:
            saltados_vacios += 1
            continue

        # Solo importar hasta 2024; desde 2025 se sube desde la plataforma
        if doc.get("year", 0) > 2024:
            saltados_año += 1
            continue

        doc_id = _doc_id(doc["medidor"], doc["year"], doc["mes_numero"])

        if doc_id in ids_existentes:
            saltados_existentes += 1
            continue

        pendientes.append((doc_id, doc))

    print(f"\n{'='*57}")
    print(f"  Filas leídas                 : {len(data_rows)}")
    print(f"  Docs a importar              : {len(pendientes)}")
    print(f"  Saltados (ya existen)        : {saltados_existentes}")
    print(f"  Saltados (año > 2024)        : {saltados_año}")
    print(f"  Saltados (sin datos mínimos) : {saltados_vacios}")
    print(f"{'='*57}")

    # Muestra de los primeros 3 docs a importar
    if pendientes:
        print("\n--- Muestra (primeros 3) ---")
        for doc_id, doc in pendientes[:3]:
            print(
                f"  {doc_id} | "
                f"medidor={doc.get('medidor')} | "
                f"{doc.get('year')}-{str(doc.get('mes_numero','?')).zfill(2)} | "
                f"total={doc.get('total_facturado')} | "
                f"estado={doc.get('estado_medidor')}"
            )

    if dry_run:
        print("\n[DRY-RUN] No se escribió nada. Usa --execute para importar.")
        return 0

    if not pendientes:
        print("[INFO] Nada que importar.")
        return 0

    # Escritura en batches con IDs deterministas
    insertados  = 0
    batch       = db.batch()
    pending_cnt = 0

    for doc_id, doc in pendientes:
        ref = db.collection("facturas").document(doc_id)
        batch.set(ref, doc)
        pending_cnt += 1
        insertados  += 1

        if pending_cnt >= BATCH_SIZE:
            batch.commit()
            batch       = db.batch()
            pending_cnt = 0
            print(f"  Insertados {insertados}/{len(pendientes)}...")

    if pending_cnt:
        batch.commit()

    print(f"\n {insertados} documentos históricos importados.")
    print(f"  {saltados_existentes} ya existían y fueron omitidos.")

    # ── Reconstruir resumen agregado (mantiene resumenes/{uid} sincronizado) ──
    if insertados > 0:
        print(f"\n[RESUMEN] Reconstruyendo resumenes/{OWNER_UID}...")
        reconstruir_resumen(db, OWNER_UID)
        print("[RESUMEN] OK")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
