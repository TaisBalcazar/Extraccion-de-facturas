"""
limpiar_y_recargar_cat2.py
Limpia y recarga los documentos de Categoría 2 (Electricidad) en Firestore.

Pasos:
  1. Borra TODOS los docs cat-2 del owner (batches de 500)
  2. Carga histórico 2018-2023 desde CSVs locales
  3. Verifica la carga

Uso:
    cd backend
    python scripts/limpiar_y_recargar_cat2.py            # interactivo
    python scripts/limpiar_y_recargar_cat2.py --dry-run  # solo simula
    python scripts/limpiar_y_recargar_cat2.py --yes      # sin confirmaciones
    python scripts/limpiar_y_recargar_cat2.py --verificar  # solo verifica
"""

import sys
import os
import csv
import hashlib
import re
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.firebase import get_firestore_client, init_firebase
from app.services.resumen_service import reconstruir_resumen
from google.cloud.firestore_v1.base_query import FieldFilter

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURACIÓN — ajusta antes de ejecutar
# ─────────────────────────────────────────────────────────────────────────────

OWNER_UID   = "GSmOljJ3ROQhOe9EppQCh7MXU9Y2"
OWNER_EMAIL = "utplsostenible@gmail.com"

# Directorio con los CSVs históricos.
# Cada archivo debe llamarse historico_YYYY_MM.csv (ej: historico_2018_01.csv)
CSV_DIR: str | None = None  # ← CONFIGURA ESTA RUTA antes de ejecutar

# Metadatos de asociación para los documentos históricos
ZONA_ID          = "zona-7"
ZONA_NOMBRE      = "Zona 7 - Sur"
CENTRO           = "LOJA"
CATEGORIA_ID     = "cat-2"
CATEGORIA_NOMBRE = "Categoría 2"
ITEM             = "CONSUMO ELECTRICO EN INSTALACIONES UTPL"

# Columnas del CSV → campo destino en Firestore
# Ajusta los nombres si tus CSVs usan encabezados distintos
CSV_COLUMN_MAP = {
    "medidor":               "medidor",
    "consumo_total":         "consumo_total",
    "valor_total":           "valor_total",
    "valor_consumo":         "valor_consumo",
    "alumbrado_publico":     "alumbrado_publico",
    "comercializacion":      "comercializacion",
    "contribucion_bomberos": "contribucion_bomberos",
    "subsidio_tarifa":       "subsidio_tarifa",
    "dias_facturados":       "dias_facturados",
    "razon_social":          "razon_social",
    "cod_unico":             "cod_unico",
    "periodo_inicio":        "periodo_inicio",
    "periodo_fin":           "periodo_fin",
    "fecha_emision":         "fecha_emision",
    "total_sec_elec":        "total_sec_elec",
}

# ─────────────────────────────────────────────────────────────────────────────
# Catálogo oficial UTPL: medidor → {ubicacion, nombre_medidor}
# ─────────────────────────────────────────────────────────────────────────────

MEDIDORES_UTPL = {
    "33733":      {"ubicacion": "SAN CAYETANO",                                              "nombre_medidor": "SAN CAYETANO (SN)"},
    "32789":      {"ubicacion": "SAN CAYETANO",                                              "nombre_medidor": "SAN CAYETANO (SN)"},
    "32369":      {"ubicacion": "PARIS PRAGA",                                               "nombre_medidor": "CASA DE FORMACIÓN MARISTA"},
    "32373":      {"ubicacion": "PARIS PRAGA",                                               "nombre_medidor": "EDIFICIO 3,4,5 Y 6"},
    "31933":      {"ubicacion": "MARCELINO CHAMPAGNATT SANTIAGO DE LAS MONTAÑAS",            "nombre_medidor": "MAD"},
    "31947":      {"ubicacion": "MARCELINO CHAMPAGNATT SANTIAGO DE LAS MONTAÑAS",            "nombre_medidor": "EDIF CENTRAL, CAPILLA, MISIONES"},
    "202951":     {"ubicacion": "RESIDENCIA MISIONEROS IDENTES",                             "nombre_medidor": "RESIDENCIA IDENTE"},
    "32545":      {"ubicacion": "PARIS PRAGA",                                               "nombre_medidor": "EDIFICIO R LAB ALIMENTOS JUNTO A ECOLAC"},
    "32783":      {"ubicacion": "PARIS PRAGA",                                               "nombre_medidor": "EDIFICIO V-P-BIOPRODUCTOS LAB NUEVO QUIMICA Y P1 EDIF NUEVO MEDICINA"},
    "1269208":    {"ubicacion": "SAN CAYETANO",                                              "nombre_medidor": "SAN CAYETANO (SN)"},
    "1269207":    {"ubicacion": "SAN CAYETANO",                                              "nombre_medidor": "SAN CAYETANO (SN)"},
    "1269206":    {"ubicacion": "SAN CAYETANO",                                              "nombre_medidor": "SAN CAYETANO (SN)"},
    "205934":     {"ubicacion": "SAN CAYETANO",                                              "nombre_medidor": "SAN CAYETANO (SN)"},
    "33659":      {"ubicacion": "PARIS PRAGA",                                               "nombre_medidor": "UGTI"},
    "202955":     {"ubicacion": "SAN CAYETANO",                                              "nombre_medidor": "SAN CAYETANO (SN)"},
    "28978":      {"ubicacion": "SAN CAYETANO",                                              "nombre_medidor": "SAN CAYETANO (SN)"},
    "31922":      {"ubicacion": "PARIS PRAGA",                                               "nombre_medidor": "CAFETERIA"},
    "31925":      {"ubicacion": "PARIS PRAGA",                                               "nombre_medidor": "C. CONVENCIONES, ARCHIVO, CANCHAS TAPADAS Y DGCOM"},
    "32317":      {"ubicacion": "SAN CAYETANO",                                              "nombre_medidor": "SAN CAYETANO (SN)"},
    "32316":      {"ubicacion": "SAN CAYETANO",                                              "nombre_medidor": "SAN CAYETANO (SN)"},
    "32377":      {"ubicacion": "PARIS PRAGA",                                               "nombre_medidor": "EDIFICIO 1, 2, 7, 8, OCTOGONO, CANCHAS, MUSEO Y GRADAS ELÉCTRICAS"},
    "32779":      {"ubicacion": "PARIS PRAGA",                                               "nombre_medidor": "EDIFICIO Q y M"},
    "2011204737": {"ubicacion": "SAN CAYETANO",                                              "nombre_medidor": "SAN CAYETANO (SN)"},
    "203893":     {"ubicacion": "SAN CAYETANO",                                              "nombre_medidor": "SAN CAYETANO (SN)"},
    "33607":      {"ubicacion": "PARIS PRAGA",                                               "nombre_medidor": "EDIFICIO S DGTI"},
    "33683":      {"ubicacion": "PARIS PRAGA",                                               "nombre_medidor": "EDIFICIO 9"},
    "240297":     {"ubicacion": "RESIDENCIA MISIONEROS IDENTES",                             "nombre_medidor": "CENTRO DE REUNIONES RESIDENCIA IDENTE"},
    "33775":      {"ubicacion": "SAN CAYETANO",                                              "nombre_medidor": "SAN CAYETANO (SN)"},
    "205771":     {"ubicacion": "SAN CAYETANO",                                              "nombre_medidor": "SAN CAYETANO (SN)"},
    "207555":     {"ubicacion": "SAN CAYETANO",                                              "nombre_medidor": "SAN CAYETANO (SN)"},
    "202653":     {"ubicacion": "SAN CAYETANO",                                              "nombre_medidor": "SAN CAYETANO (SN)"},
    "1000362554": {"ubicacion": "SAN CAYETANO",                                              "nombre_medidor": "SAN CAYETANO (SN)"},
    "1000362557": {"ubicacion": "SAN CAYETANO",                                              "nombre_medidor": "SAN CAYETANO (SN)"},
    "242170":     {"ubicacion": "JOSE CORONEL ILLESCAS VIA NUEVA A ZAMORA / VALLE - LOJA",  "nombre_medidor": "RESIDENCIA IDENTE"},
    "24711":      {"ubicacion": "SAN CAYETANO",                                              "nombre_medidor": "SAN CAYETANO (SN)"},
    "246903":     {"ubicacion": "10 DE AGOSTO",                                              "nombre_medidor": "EDIF 10 AGO"},
    "33942":      {"ubicacion": "MARCELINO CHAMPAGNATT",                                     "nombre_medidor": "PARQUEADERO UTPL"},
    "28625":      {"ubicacion": "EUCALIPTOS / SUCRE",                                        "nombre_medidor": "EUCALIPTOS"},
    "34191":      {"ubicacion": "PARIS PRAGA",                                               "nombre_medidor": "EDIFICIO 1, 2, 7, 8, OCTOGONO, CANCHAS, MUSEO Y GRADAS ELÉCTRICAS"},
    "34270":      {"ubicacion": "EDIFICIO D",                                                "nombre_medidor": "EDIF D FACULTADES"},
    "34343":      {"ubicacion": "MARCELINO CHAMPAGNATT SANTIAGO DE LAS MONTAÑAS",            "nombre_medidor": "EDIF CENTRAL, CAPILLA, MISIONES"},
    "34447":      {"ubicacion": "PARIS PRAGA / VALLE - LOJA",                                "nombre_medidor": "LABORATORIOS EDIFICIO Q"},
    "18234549":   {"ubicacion": "JOSE CORONEL ILLESCAS S/N VIA NUEVA A ZAMORA / VALLE - LOJA", "nombre_medidor": "BODEGA VIA A ZAMORA"},
}

MESES = {
    1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
    5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
    9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre",
}

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _lookup_medidor(medidor_raw: str | None) -> dict:
    """Devuelve {nombre_medidor, ubicacion} desde el catálogo UTPL."""
    if not medidor_raw:
        return {"nombre_medidor": None, "ubicacion": None}
    key = re.sub(r"\D", "", str(medidor_raw).strip())
    entry = MEDIDORES_UTPL.get(key)
    if entry:
        return entry
    print(f"  [WARN] Medidor '{key}' no encontrado en catálogo UTPL")
    return {"nombre_medidor": None, "ubicacion": None}


def _to_float(value) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return float(str(value).replace(",", ".").strip())
    except (ValueError, TypeError):
        return None


def _to_int(value) -> int | None:
    f = _to_float(value)
    return int(f) if f is not None else None


def _hash_historico(medidor: str | None, year: int, mes_numero: int) -> str:
    """Hash determinista para históricos (sin nro_factura disponible)."""
    clave = f"historico:{medidor}:{year}:{mes_numero}"
    return hashlib.md5(clave.encode()).hexdigest()


# ─────────────────────────────────────────────────────────────────────────────
# PASO 1 — Borrado
# ─────────────────────────────────────────────────────────────────────────────

def borrar_cat2(db, dry_run: bool = False) -> int:
    print("\n[BORRADO] Buscando documentos cat-2...")
    docs = list(
        db.collection("facturas")
        .where(filter=FieldFilter("owner_uid",    "==", OWNER_UID))
        .where(filter=FieldFilter("categoria_id", "==", "cat-2"))
        .stream()
    )
    total = len(docs)
    print(f"[BORRADO] Encontrados: {total} documentos")

    if total == 0:
        return 0

    if dry_run:
        print(f"[DRY-RUN] Se eliminarían {total} documentos (sin cambios)")
        return total

    batch_size = 500
    eliminados = 0
    for i in range(0, total, batch_size):
        batch = db.batch()
        for doc in docs[i:i + batch_size]:
            batch.delete(doc.reference)
        batch.commit()
        eliminados += len(docs[i:i + batch_size])
        print(f"[BORRADO]  {eliminados}/{total}...")

    print(f"[BORRADO] {eliminados} documentos eliminados")
    return eliminados


# ─────────────────────────────────────────────────────────────────────────────
# PASO 2 — Carga histórica desde CSVs
# ─────────────────────────────────────────────────────────────────────────────

def _parse_csv_filename(filename: str) -> tuple[int, int] | None:
    """Extrae (year, mes) de 'historico_2018_01.csv'."""
    m = re.search(r"(\d{4})_(\d{2})", filename)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None


def _build_doc(row: dict, year: int, mes_numero: int, filename: str) -> dict:
    """Construye el documento Firestore desde una fila del CSV."""
    medidor_raw = str(row.get("medidor") or "").strip()
    medidor     = re.sub(r"\D", "", medidor_raw) or None
    cat_info    = _lookup_medidor(medidor)

    # direccion_servicio: catálogo tiene prioridad sobre el CSV
    direccion = cat_info.get("ubicacion") or str(row.get("direccion_servicio") or "").strip() or None

    consumo_total = _to_float(row.get("consumo_total"))

    doc = {
        # Asociación
        "categoria_id":      CATEGORIA_ID,
        "categoria_nombre":  CATEGORIA_NOMBRE,
        "zona_id":           ZONA_ID,
        "zona_nombre":       ZONA_NOMBRE,
        "centro":            CENTRO,
        "item":              ITEM,
        "owner_uid":         OWNER_UID,
        "owner_email":       OWNER_EMAIL,

        # Identificación
        "filename":          filename,
        "upload_date":       datetime.now().isoformat(),
        "nro_factura":       None,
        "hash_factura":      _hash_historico(medidor, year, mes_numero),
        "cod_unico":         str(row.get("cod_unico") or "").strip() or None,

        # Suministro
        "medidor":           medidor,
        "nombre_medidor":    cat_info.get("nombre_medidor"),
        "razon_social":      str(row.get("razon_social") or "").strip() or None,
        "direccion_servicio": direccion,

        # Temporal — campo canónico: year (int), NO anio
        "year":              year,
        "mes_numero":        mes_numero,
        "mes_nombre":        MESES.get(mes_numero, ""),
        "fecha_emision":     str(row.get("fecha_emision") or "").strip() or None,
        "periodo_inicio":    str(row.get("periodo_inicio") or "").strip() or None,
        "periodo_fin":       str(row.get("periodo_fin") or "").strip() or None,
        "dias_facturados":   _to_int(row.get("dias_facturados")),

        # Consumo (kWh)
        "consumo_total":     consumo_total,
        "consumo_kwh":       consumo_total,

        # Valores económicos
        "valor_total":           _to_float(row.get("valor_total")),
        "valor_consumo":         _to_float(row.get("valor_consumo")),
        "alumbrado_publico":     _to_float(row.get("alumbrado_publico")),
        "comercializacion":      _to_float(row.get("comercializacion")),
        "contribucion_bomberos": _to_float(row.get("contribucion_bomberos")),
        "subsidio_tarifa":       _to_float(row.get("subsidio_tarifa")),
        "total_sec_elec":        _to_float(row.get("total_sec_elec")),
        # tipo_tarifa y valor_forma_pago deliberadamente excluidos
    }

    # Eliminar campos None para no contaminar Firestore
    return {k: v for k, v in doc.items() if v is not None}


def cargar_historico(db, csv_dir: str, dry_run: bool = False) -> int:
    csv_path = Path(csv_dir)
    archivos = sorted(csv_path.glob("historico_*.csv"))

    if not archivos:
        print(f"[HISTORICO] No se encontraron archivos historico_*.csv en:\n  {csv_dir}")
        return 0

    print(f"\n[HISTORICO] Archivos encontrados: {len(archivos)}")
    for a in archivos:
        print(f"  {a.name}")

    docs_a_insertar: list[dict] = []
    medidores_sin_match: set[str] = set()

    for archivo in archivos:
        parsed = _parse_csv_filename(archivo.name)
        if not parsed:
            print(f"  [SKIP] Nombre no reconocido: {archivo.name}")
            continue
        year, mes_numero = parsed

        try:
            with open(archivo, encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                filas = 0
                for row in reader:
                    doc = _build_doc(row, year, mes_numero, archivo.name)
                    docs_a_insertar.append(doc)
                    filas += 1
                    if doc.get("nombre_medidor") is None and doc.get("medidor"):
                        medidores_sin_match.add(doc["medidor"])
            print(f"[OK] {archivo.name} -> {filas} registros")
        except Exception as exc:
            print(f"  [ERR] {archivo.name}: {exc}")

    print(f"\n[HISTORICO] Total registros a importar: {len(docs_a_insertar)}")

    if medidores_sin_match:
        print(f"[WARN] Medidores sin match en catálogo ({len(medidores_sin_match)}): {sorted(medidores_sin_match)}")

    if dry_run:
        print(f"[DRY-RUN] Se insertarían {len(docs_a_insertar)} documentos (sin cambios)")
        return len(docs_a_insertar)

    if not docs_a_insertar:
        return 0

    batch_size = 500
    insertados = 0
    for i in range(0, len(docs_a_insertar), batch_size):
        batch = db.batch()
        for doc in docs_a_insertar[i:i + batch_size]:
            batch.set(db.collection("facturas").document(), doc)
        batch.commit()
        insertados += len(docs_a_insertar[i:i + batch_size])
        print(f"[HISTORICO]  {insertados}/{len(docs_a_insertar)}...")

    print(f"[HISTORICO] {insertados} documentos insertados")
    return insertados


# ─────────────────────────────────────────────────────────────────────────────
# PASO 3 — Verificación post-carga
# ─────────────────────────────────────────────────────────────────────────────

def verificar_cat2(db) -> None:
    print("\n[VERIFICAR] Leyendo documentos cat-2...")
    docs = list(
        db.collection("facturas")
        .where(filter=FieldFilter("owner_uid",    "==", OWNER_UID))
        .where(filter=FieldFilter("categoria_id", "==", "cat-2"))
        .limit(500)
        .stream()
    )

    total = len(docs)
    print(f"[VERIFICAR] Documentos encontrados (muestra ≤500): {total}")

    if total == 0:
        print("[VERIFICAR] Sin documentos cat-2. ¿Se ejecutó la carga?")
        return

    errores: list[str] = []
    years_encontrados: set[int] = set()
    consumo_total_sum = 0.0
    sin_nombre_medidor = 0
    medidores_sin_match: set[str] = set()

    for doc in docs:
        data   = doc.to_dict() or {}
        doc_id = doc.id[:12]

        # 'year' debe existir y ser int
        year_val = data.get("year")
        if year_val is None:
            errores.append(f"  [{doc_id}] Falta campo 'year'")
        elif not isinstance(year_val, int):
            errores.append(f"  [{doc_id}] 'year' no es int: {type(year_val).__name__} = {year_val}")
        else:
            years_encontrados.add(year_val)

        # 'anio' NO debe existir
        if "anio" in data:
            errores.append(f"  [{doc_id}] Campo 'anio' presente (debe eliminarse)")

        # 'dias_facturados' debe ser int si existe
        dias = data.get("dias_facturados")
        if dias is not None and not isinstance(dias, int):
            errores.append(f"  [{doc_id}] 'dias_facturados' no es int: {type(dias).__name__} = {dias}")

        # 'nombre_medidor' debe estar poblado
        if not data.get("nombre_medidor"):
            sin_nombre_medidor += 1
            med = data.get("medidor")
            if med:
                medidores_sin_match.add(med)

        consumo_total_sum += float(data.get("consumo_total") or 0)

    print(f"\n[VERIFICAR] ── Resumen ──────────────────────────────────")
    print(f"  Total documentos (muestra):  {total}")
    print(f"  Rango de años:               {sorted(years_encontrados) if years_encontrados else 'N/A'}")
    print(f"  Consumo total acumulado:     {consumo_total_sum:,.2f} kWh")
    print(f"  Docs sin nombre_medidor:     {sin_nombre_medidor}")
    if medidores_sin_match:
        print(f"  Medidores sin match:         {sorted(medidores_sin_match)}")

    if errores:
        print(f"\n[VERIFICAR] {len(errores)} problema(s) detectado(s):")
        for e in errores[:20]:
            print(e)
        if len(errores) > 20:
            print(f"  ... y {len(errores) - 20} más")
    else:
        print("\n[VERIFICAR] Todos los campos son correctos")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    dry_run        = "--dry-run"    in sys.argv
    autoconfirm    = "--yes"        in sys.argv
    solo_verificar = "--verificar"  in sys.argv

    print("=" * 60)
    print("  Limpieza y re-carga — Categoría 2 (Electricidad)")
    print("=" * 60)
    if dry_run:
        print("  MODO: DRY-RUN (sin cambios en Firestore)\n")

    print("[*] Conectando a Firebase...")
    init_firebase()
    db = get_firestore_client()
    if not db:
        print("[ERROR] No se pudo conectar a Firebase.")
        sys.exit(1)
    print("[OK] Conexión exitosa.")

    if solo_verificar:
        verificar_cat2(db)
        return

    # ── Paso 1: Borrado ───────────────────────────────────────────
    if not autoconfirm and not dry_run:
        resp = input(
            "\n¿Borrar TODOS los docs cat-2 del owner? Es irreversible. (s/N): "
        ).strip().lower()
        if resp not in ("s", "si", "sí", "y", "yes"):
            print("[!] Cancelado.")
            sys.exit(0)

    borrar_cat2(db, dry_run=dry_run)

    # ── Paso 2: Carga histórica ───────────────────────────────────
    if CSV_DIR is None:
        print("\n[HISTORICO] CSV_DIR no configurado — omitiendo carga histórica.")
        print("            Edita la variable CSV_DIR al inicio del script.")
    else:
        if not autoconfirm and not dry_run:
            resp = input(f"\n¿Cargar histórico desde '{CSV_DIR}'? (s/N): ").strip().lower()
            if resp not in ("s", "si", "sí", "y", "yes"):
                print("[!] Carga histórica omitida.")
                if not dry_run:
                    print(f"\n[RESUMEN] Reconstruyendo resumenes/{OWNER_UID}...")
                    reconstruir_resumen(db, OWNER_UID)
                    print("[RESUMEN] OK")
                    verificar_cat2(db)
                return

        cargar_historico(db, CSV_DIR, dry_run=dry_run)

    # ── Paso 3: Reconstruir resumen agregado ───────────────────────
    if not dry_run:
        print(f"\n[RESUMEN] Reconstruyendo resumenes/{OWNER_UID}...")
        reconstruir_resumen(db, OWNER_UID)
        print("[RESUMEN] OK")

    # ── Paso 4: Verificación ──────────────────────────────────────
    if not dry_run:
        verificar_cat2(db)


if __name__ == "__main__":
    main()
