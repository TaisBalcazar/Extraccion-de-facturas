"""
importar_historico_cat2_v2.py
Carga histórico de electricidad (cat-2) desde Excel a Firestore.

Fuente: DATOS_ENERGIA_ARCGIS.xlsx  — Hoja 1 (2018–2025)
Filtro: solo filas donde year <= 2024
Zona/centro fijos: zona-7 / Zona 7 / LOJA

Uso:
    cd backend
    python scripts/importar_historico_cat2_v2.py                        # interactivo
    python scripts/importar_historico_cat2_v2.py --dry-run              # simula sin escribir
    python scripts/importar_historico_cat2_v2.py --yes                  # sin confirmaciones
    python scripts/importar_historico_cat2_v2.py --verificar            # solo verifica Firestore
"""

import sys
import os
import hashlib
import re
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd

from app.core.firebase import get_firestore_client, init_firebase
from app.services.resumen_service import reconstruir_resumen
from google.cloud.firestore_v1.base_query import FieldFilter

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURACIÓN
# ─────────────────────────────────────────────────────────────────────────────

EXCEL_PATH   = r"C:\Users\Smart\Downloads\DATOS_ENERGIA_ARCGIS.xlsx"
SHEET_NAME   = "Hoja 1"          # hoja con datos desde 2018
YEAR_LIMITE  = 2024              # se procesan SOLO filas con year <= este valor

OWNER_UID    = "GSmOljJ3ROQhOe9EppQCh7MXU9Y2"
OWNER_EMAIL  = "utplsostenible@gmail.com"
ZONA_ID      = "zona-7"
ZONA_NOMBRE  = "Zona 7"
CENTRO       = "LOJA"
CATEGORIA_ID = "cat-2"
CATEGORIA_NOMBRE = "Categoría 2"
ITEM         = "Consumo eléctrico de la organización"
FILENAME_SRC = "historico_excel_2018_2024"

MESES = {
    1: "Enero",    2: "Febrero",  3: "Marzo",     4: "Abril",
    5: "Mayo",     6: "Junio",    7: "Julio",      8: "Agosto",
    9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre",
}

# ─────────────────────────────────────────────────────────────────────────────
# Catálogo oficial UTPL: medidor (solo dígitos) → nombre_medidor
# ─────────────────────────────────────────────────────────────────────────────

MEDIDORES_UTPL: dict[str, str] = {
    "33733":      "SAN CAYETANO (SN)",
    "32789":      "SAN CAYETANO (SN)",
    "32369":      "CASA DE FORMACIÓN MARISTA",
    "32373":      "EDIFICIO 3,4,5 Y 6",
    "31933":      "MAD",
    "31947":      "EDIF CENTRAL, CAPILLA, MISIONES",
    "202951":     "RESIDENCIA IDENTE",
    "32545":      "EDIFICIO R LAB ALIMENTOS JUNTO A ECOLAC",
    "32783":      "EDIFICIO V-P-BIOPRODUCTOS LAB NUEVO QUIMICA Y P1 EDIF NUEVO MEDICINA",
    "1269208":    "SAN CAYETANO (SN)",
    "1269207":    "SAN CAYETANO (SN)",
    "1269206":    "SAN CAYETANO (SN)",
    "205934":     "SAN CAYETANO (SN)",
    "33659":      "UGTI",
    "202955":     "SAN CAYETANO (SN)",
    "28978":      "SAN CAYETANO (SN)",
    "31922":      "CAFETERIA",
    "31925":      "C. CONVENCIONES, ARCHIVO, CANCHAS TAPADAS Y DGCOM",
    "32317":      "SAN CAYETANO (SN)",
    "32316":      "SAN CAYETANO (SN)",
    "32377":      "EDIFICIO 1, 2, 7, 8, OCTOGONO, CANCHAS, MUSEO Y GRADAS ELÉCTRICAS",
    "32779":      "EDIFICIO Q y M",
    "2011204737": "SAN CAYETANO (SN)",
    "203893":     "SAN CAYETANO (SN)",
    "33607":      "EDIFICIO S DGTI",
    "33683":      "EDIFICIO 9",
    "240297":     "CENTRO DE REUNIONES RESIDENCIA IDENTE",
    "33775":      "SAN CAYETANO (SN)",
    "205771":     "SAN CAYETANO (SN)",
    "207555":     "SAN CAYETANO (SN)",
    "202653":     "SAN CAYETANO (SN)",
    "1000362554": "SAN CAYETANO (SN)",
    "1000362557": "SAN CAYETANO (SN)",
    "242170":     "RESIDENCIA IDENTE",
    "24711":      "SAN CAYETANO (SN)",
    "246903":     "EDIF 10 AGO",
    "33942":      "PARQUEADERO UTPL",
    "28625":      "EUCALIPTOS",
    "34191":      "EDIFICIO 1, 2, 7, 8, OCTOGONO, CANCHAS, MUSEO Y GRADAS ELÉCTRICAS",
    "34270":      "EDIF D FACULTADES",
    "34343":      "EDIF CENTRAL, CAPILLA, MISIONES",
    "34447":      "LABORATORIOS EDIFICIO Q",
    "18234549":   "BODEGA VIA A ZAMORA",
}

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _lookup_medidor(medidor_raw) -> str | None:
    if medidor_raw is None:
        return None
    key = re.sub(r"\D", "", str(medidor_raw).strip())
    nombre = MEDIDORES_UTPL.get(key)
    if not nombre:
        print(f"  [WARN] Medidor '{key}' no encontrado en catalogo UTPL")
    return nombre


def _to_float(val) -> float | None:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        return float(str(val).replace(",", ".").strip())
    except (ValueError, TypeError):
        return None


def _to_int(val) -> int | None:
    f = _to_float(val)
    return int(round(f)) if f is not None else None


def _format_date(val) -> str | None:
    """Convierte pandas Timestamp o string a DD-MM-YYYY."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    if hasattr(val, "strftime"):
        return val.strftime("%d-%m-%Y")
    s = str(val).strip()
    # si viene como YYYY-MM-DD, convertir
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    return s or None


def _hash_factura(cod_unico: str | None, periodo_inicio: str | None, mes_numero: int | None) -> str:
    """Hash determinista: md5(cod_unico_periodo_inicio_mes_numero)."""
    clave = f"{cod_unico or ''}_{periodo_inicio or ''}_{mes_numero or ''}"
    return hashlib.md5(clave.encode()).hexdigest()


def _build_doc(row: pd.Series) -> dict:
    year       = _to_int(row.get("Año"))
    mes_numero = _to_int(row.get("mes nro"))
    mes_nombre = MESES.get(mes_numero, str(row.get("mes", "")))

    # cod_unico: pandas lee números como float (ej: 1800053900.0) → limpiar el .0
    _cod_raw  = row.get("Código único eléctrico nacional ", "")
    _cod_str  = str(_cod_raw or "").strip()
    if _cod_str.endswith(".0") and _cod_str[:-2].isdigit():
        _cod_str = _cod_str[:-2]
    cod_unico = _cod_str or None
    medidor_raw     = row.get("medidor")
    medidor         = re.sub(r"\D", "", str(medidor_raw or "").strip()) or None
    nombre_medidor  = _lookup_medidor(medidor_raw)
    direccion       = str(row.get("Ubicación", "") or "").strip() or None

    periodo_inicio  = _format_date(row.get("fecha desde"))
    periodo_fin     = _format_date(row.get("fecha hasta"))
    fecha_emision   = periodo_inicio  # el Excel no tiene fecha de emisión separada

    dias_facturados = _to_int(row.get("dias facturados "))

    consumo_total   = _to_float(row.get("Energía activa total kw"))
    valor_consumo   = _to_float(row.get("Valor de consumo $ ENERGÍA"))
    comercializacion    = _to_float(row.get("Comercialización"))
    alumbrado_publico   = _to_float(row.get("Servicio Alumbrado Público"))
    contribucion_bomberos = _to_float(row.get("Contribución Bomberos "))
    subsidio_tarifa = _to_float(row.get("Subsidio Cruzado"))
    valor_total     = _to_float(row.get("VALOR TOTAL PAGADO (USD)"))

    hash_factura = _hash_factura(cod_unico, periodo_inicio, mes_numero)

    doc = {
        "categoria_id":    CATEGORIA_ID,
        "categoria_nombre": CATEGORIA_NOMBRE,
        "zona_id":         ZONA_ID,
        "zona_nombre":     ZONA_NOMBRE,
        "centro":          CENTRO,
        "item":            ITEM,
        "owner_uid":       OWNER_UID,
        "owner_email":     OWNER_EMAIL,

        "hash_factura":    hash_factura,
        "nro_factura":     None,
        "filename":        FILENAME_SRC,

        "medidor":          medidor,
        "nombre_medidor":   nombre_medidor,
        "cod_unico":        cod_unico,
        "direccion_servicio": direccion,

        "year":            year,
        "mes_numero":      mes_numero,
        "mes_nombre":      mes_nombre,
        "fecha_emision":   fecha_emision,
        "periodo_inicio":  periodo_inicio,
        "periodo_fin":     periodo_fin,
        "dias_facturados": dias_facturados,

        "consumo_total":          consumo_total,
        "valor_consumo":          valor_consumo,
        "valor_total":            valor_total,
        "alumbrado_publico":      alumbrado_publico,
        "comercializacion":       comercializacion,
        "contribucion_bomberos":  contribucion_bomberos,
        "subsidio_tarifa":        subsidio_tarifa,

        "upload_date": datetime.now().isoformat(),
    }

    # Eliminar campos None para no contaminar Firestore
    return {k: v for k, v in doc.items() if v is not None}


# ─────────────────────────────────────────────────────────────────────────────
# Leer y filtrar Excel
# ─────────────────────────────────────────────────────────────────────────────

def leer_excel() -> list[dict]:
    print(f"\n[EXCEL] Leyendo: {EXCEL_PATH}")
    print(f"[EXCEL] Hoja: {SHEET_NAME!r}")

    df = pd.read_excel(EXCEL_PATH, sheet_name=SHEET_NAME)
    print(f"[EXCEL] Columnas disponibles ({len(df.columns)}):")
    for col in df.columns:
        print(f"  - {col!r}")
    print(f"[EXCEL] Total filas leidas: {len(df)}")

    # Filtrar por año
    df["_year_num"] = pd.to_numeric(df["Año"], errors="coerce")
    filas_2025_plus = df[df["_year_num"] > YEAR_LIMITE]
    df_filtrado = df[df["_year_num"] <= YEAR_LIMITE].copy()

    print(f"\n[FILTRO] Filas descartadas (year > {YEAR_LIMITE}): {len(filas_2025_plus)}")
    if len(filas_2025_plus) > 0:
        dist = filas_2025_plus["_year_num"].value_counts().sort_index()
        for yr, cnt in dist.items():
            print(f"  year={int(yr)}: {cnt} filas descartadas")
    print(f"[FILTRO] Filas a procesar (year <= {YEAR_LIMITE}): {len(df_filtrado)}")

    # Construir documentos
    docs: list[dict] = []
    medidores_sin_match: set[str] = set()

    for i, row in df_filtrado.iterrows():
        doc = _build_doc(row)
        docs.append(doc)
        if doc.get("nombre_medidor") is None and doc.get("medidor"):
            medidores_sin_match.add(doc["medidor"])

    if medidores_sin_match:
        print(f"\n[WARN] Medidores sin match en catalogo ({len(medidores_sin_match)}): {sorted(medidores_sin_match)}")

    return docs


# ─────────────────────────────────────────────────────────────────────────────
# Verificación post-carga
# ─────────────────────────────────────────────────────────────────────────────

def verificar(db) -> None:
    print("\n[VERIFICAR] Leyendo documentos cat-2 en Firestore...")
    docs = list(
        db.collection("facturas")
        .where(filter=FieldFilter("owner_uid",    "==", OWNER_UID))
        .where(filter=FieldFilter("categoria_id", "==", "cat-2"))
        .limit(5000)
        .stream()
    )
    total = len(docs)
    print(f"[VERIFICAR] Documentos encontrados: {total}")

    if total == 0:
        print("[VERIFICAR] Sin documentos cat-2.")
        return

    years: dict[int, int] = {}
    sin_year = 0
    con_anio = 0
    sin_nombre_medidor = 0
    errores: list[str] = []

    for doc in docs:
        d = doc.to_dict() or {}
        year_val = d.get("year")
        if year_val is None:
            sin_year += 1
            errores.append(f"  [{doc.id[:12]}] Falta campo 'year'")
        elif not isinstance(year_val, int):
            errores.append(f"  [{doc.id[:12]}] 'year' no es int: {type(year_val).__name__}")
        else:
            years[year_val] = years.get(year_val, 0) + 1

        if "anio" in d:
            con_anio += 1
            errores.append(f"  [{doc.id[:12]}] Campo 'anio' presente (no debe existir)")

        if not d.get("nombre_medidor"):
            sin_nombre_medidor += 1

        for campo_prohibido in ("razon_social", "tipo_tarifa", "valor_forma_pago"):
            if campo_prohibido in d:
                errores.append(f"  [{doc.id[:12]}] Campo prohibido presente: '{campo_prohibido}'")

    print(f"\n[VERIFICAR] ── Resumen ──────────────────────────────────")
    print(f"  Total documentos:          {total}")
    print(f"  Rango de years:            {sorted(years.keys()) if years else 'N/A'}")
    print(f"  Distribucion:              {dict(sorted(years.items()))}")
    print(f"  Sin campo 'year':          {sin_year}")
    print(f"  Con campo 'anio' (error):  {con_anio}")
    print(f"  Sin nombre_medidor:        {sin_nombre_medidor}")

    if errores:
        print(f"\n[VERIFICAR] {len(errores)} problema(s):")
        for e in errores[:20]:
            print(e)
        if len(errores) > 20:
            print(f"  ... y {len(errores) - 20} mas")
    else:
        print("\n[VERIFICAR] OK todos los campos son correctos")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    dry_run        = "--dry-run"   in sys.argv
    autoconfirm    = "--yes"       in sys.argv
    solo_verificar = "--verificar" in sys.argv

    print("=" * 60)
    print("  Carga historica cat-2 (Electricidad) desde Excel")
    print("=" * 60)
    if dry_run:
        print("  MODO: DRY-RUN (sin cambios en Firestore)\n")

    print("[*] Conectando a Firebase...")
    init_firebase()
    db = get_firestore_client()
    if not db:
        print("[ERROR] No se pudo conectar a Firebase.")
        sys.exit(1)
    print("[OK] Conexion exitosa.")

    if solo_verificar:
        verificar(db)
        return

    # ── Leer Excel ────────────────────────────────────────────────
    docs = leer_excel()
    print(f"\n[CARGA] Documentos preparados: {len(docs)}")

    if not docs:
        print("[CARGA] Nada que insertar.")
        return

    # Muestra de ejemplo
    print("\n[CARGA] Ejemplo del primer documento:")
    for k, v in list(docs[0].items())[:12]:
        print(f"  {k}: {v!r}")

    # ── Confirmación ──────────────────────────────────────────────
    if not autoconfirm and not dry_run:
        resp = input(
            f"\n¿Insertar {len(docs)} documentos en Firestore? (s/N): "
        ).strip().lower()
        if resp not in ("s", "si", "sí", "y", "yes"):
            print("[!] Cancelado.")
            sys.exit(0)

    if dry_run:
        print(f"\n[DRY-RUN] Se insertarian {len(docs)} documentos (sin cambios)")
        return

    # ── Inserción en batches de 500 ───────────────────────────────
    batch_size = 500
    insertados = 0
    for i in range(0, len(docs), batch_size):
        batch = db.batch()
        for doc in docs[i:i + batch_size]:
            batch.set(db.collection("facturas").document(), doc)
        batch.commit()
        insertados += len(docs[i:i + batch_size])
        print(f"[CARGA]  {insertados}/{len(docs)}...")

    print(f"\n[CARGA] OK {insertados} documentos insertados")

    # ── Reconstruir resumen agregado (mantiene resumenes/{uid} sincronizado) ──
    if insertados > 0:
        print(f"\n[RESUMEN] Reconstruyendo resumenes/{OWNER_UID}...")
        reconstruir_resumen(db, OWNER_UID)
        print("[RESUMEN] OK")

    # ── Verificación ──────────────────────────────────────────────
    verificar(db)


if __name__ == "__main__":
    main()
