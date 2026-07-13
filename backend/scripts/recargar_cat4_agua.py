"""
recargar_cat4_agua.py
Recarga las facturas de agua potable (cat-4) releyendo los PDFs originales.

Pasos internos:
  1. Lee todos los PDFs del directorio configurado (PDF_DIR)
  2. Extrae datos con Category4Extractor (modo _extract_agua)
  3. Valida que la razón social sea UTPL
  4. Genera hash para evitar duplicados
  5. Guarda en Firestore con el esquema canónico aprobado

Modos:
    python scripts/recargar_cat4_agua.py            → simulación (no escribe)
    python scripts/recargar_cat4_agua.py --execute  → escribe en Firestore

IMPORTANTE: ejecutar DESPUÉS de borrar_cat4_agua.py --execute
"""

from __future__ import annotations
import argparse
import hashlib
import sys
from datetime import datetime
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from google.cloud.firestore_v1.base_query import FieldFilter        # noqa: E402
from app.core.firebase import get_firestore_client                  # noqa: E402
from app.services.extractors.category4 import Category4Extractor   # noqa: E402
from app.services.resumen_service import reconstruir_resumen       # noqa: E402
from app.utils.validaciones import es_razon_social_valida           # noqa: E402

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURACIÓN — editar antes de ejecutar
# ─────────────────────────────────────────────────────────────────────────────

PDF_DIR = r"C:\ruta\a\los\pdfs\agua"   # ← carpeta con los PDFs originales de agua

OWNER_UID        = "GSmOljJ3ROQhOe9EppQCh7MXU9Y2"
OWNER_EMAIL      = "utplsostenible@gmail.com"
ZONA_ID          = "zona-7"
ZONA_NOMBRE      = "Zona 7"
CENTRO           = "LOJA"
CATEGORIA_ID     = "cat-4"
CATEGORIA_NOMBRE = "Categoría 4"
ITEM             = "Consumo de agua"

BATCH_SIZE = 500

# Campos copiados del extractor al documento Firestore (whitelist canónica)
_CAMPOS_AGUA = {
    "factura_numero", "fecha_emision", "mes_numero", "mes_nombre",
    "consumo_m3", "agua_potable", "alcantarillado",
    "aportes_planes_maestros", "seguridad_ciudadana",
    "proteccion_microcuencas", "costo_basico_facturacion",
    "recoleccion_basura", "interes_recargo", "total_facturado",
    "medidor", "estado_medidor", "categoria", "ubicacion",
    "lectura_anterior", "lectura_actual",
}

# ─────────────────────────────────────────────────────────────────────────────

_extractor = Category4Extractor()


def _build_doc(datos: dict, filename: str) -> dict:
    doc: dict = {}

    for field in _CAMPOS_AGUA:
        value = datos.get(field)
        if value is not None:
            doc[field] = value

    # Metadatos
    doc["filename"]    = filename
    doc["upload_date"] = datetime.now().isoformat()
    doc["owner_uid"]   = OWNER_UID
    doc["owner_email"] = OWNER_EMAIL

    # Asociación (equivalente a lo que selecciona el usuario en la pantalla)
    doc["zona_id"]          = ZONA_ID
    doc["zona_nombre"]      = ZONA_NOMBRE
    doc["centro"]           = CENTRO
    doc["categoria_id"]     = CATEGORIA_ID
    doc["categoria_nombre"] = CATEGORIA_NOMBRE
    doc["item"]             = ITEM

    # year: fecha_emision viene DD-MM-YYYY → los primeros 4 chars no son año.
    # Fuentes en orden de prioridad:
    #   1. datos["year"]  (extractor lo deriva de "Correspondiente a: YYYY-mes")
    #   2. fecha_emision[-4:]  (último recurso si "Correspondiente a:" falló en OCR)
    fecha = datos.get("fecha_emision") or ""
    if len(fecha) >= 4 and fecha[:4].isdigit():
        doc["year"] = int(fecha[:4])
    elif datos.get("year"):
        try:
            doc["year"] = int(datos["year"])
        except (TypeError, ValueError):
            pass
    if not doc.get("year") and len(fecha) >= 4 and fecha[-4:].isdigit():
        doc["year"] = int(fecha[-4:])

    # hash para deduplicación (mismo algoritmo que _generar_hash_factura)
    factura_numero = datos.get("factura_numero")
    medidor        = datos.get("medidor")
    fecha_emision  = datos.get("fecha_emision")
    if factura_numero and medidor and fecha_emision:
        clave = f"{factura_numero}:{medidor}:{fecha_emision}"
        doc["hash_factura"] = hashlib.md5(clave.encode()).hexdigest()

    return doc


def _hash_existe(db, hash_factura: str) -> bool:
    try:
        hits = (
            db.collection("facturas")
            .where(filter=FieldFilter("owner_uid",    "==", OWNER_UID))
            .where(filter=FieldFilter("hash_factura", "==", hash_factura))
            .limit(1)
            .stream()
        )
        return any(hits)
    except Exception:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Recarga PDFs de agua (cat-4) en Firestore con esquema canónico."
    )
    parser.add_argument("--execute", action="store_true", help="Escribe en Firestore.")
    parser.add_argument("--dry-run", action="store_true", help="Solo simula (por defecto).")
    args = parser.parse_args()
    dry_run = args.dry_run or not args.execute

    pdf_path = Path(PDF_DIR)
    if not pdf_path.exists():
        print(f"[ERROR] PDF_DIR no existe: {PDF_DIR}")
        print("        Edita la variable PDF_DIR al inicio del script.")
        return 1

    pdfs = sorted(pdf_path.glob("*.pdf"))
    if not pdfs:
        print(f"[ERROR] No hay archivos .pdf en: {PDF_DIR}")
        return 1

    print(f"[*] PDFs encontrados: {len(pdfs)}")
    if dry_run:
        print("    MODO DRY-RUN: no se escribirá nada en Firestore.\n")

    db = get_firestore_client() if not dry_run else None
    if not dry_run and not db:
        print("[ERROR] Firebase no disponible.")
        return 1

    docs_a_insertar:       list[dict] = []
    saltados_no_agua:      int = 0
    saltados_razon_social: int = 0
    saltados_sin_extrac:   int = 0
    errores:               list[str] = []

    for pdf in pdfs:
        filename = pdf.name
        try:
            content = pdf.read_bytes()
            datos = _extractor.extract(content, filename)

            if not datos.get("extraction_success"):
                print(f"  [SKIP] Sin extracción: {filename} — {datos.get('error', '?')}")
                saltados_sin_extrac += 1
                continue

            # Solo documentos de agua (el extractor pone tipo_documento internamente)
            if datos.get("tipo_documento") != "agua":
                print(f"  [SKIP] No es agua ({datos.get('tipo_documento')}): {filename}")
                saltados_no_agua += 1
                continue

            # Validar razón social UTPL
            razon = str(datos.get("razon_social") or "").strip()
            if razon and not es_razon_social_valida(razon):
                print(f"  [SKIP] Razón social inválida ({razon!r}): {filename}")
                saltados_razon_social += 1
                continue

            doc = _build_doc(datos, filename)
            docs_a_insertar.append(doc)

            mes = str(doc.get("mes_numero") or "?").zfill(2)
            print(
                f"  [OK] {filename} | "
                f"{doc.get('year')}-{mes} | "
                f"medidor={doc.get('medidor')} | "
                f"total={doc.get('total_facturado')}"
            )

        except Exception as exc:
            print(f"  [ERR] {filename}: {exc}")
            errores.append(f"{filename}: {exc}")

    print(f"\n{'='*57}")
    print(f"  PDFs procesados             : {len(pdfs)}")
    print(f"  Docs listos para insertar   : {len(docs_a_insertar)}")
    print(f"  Saltados (no son agua)      : {saltados_no_agua}")
    print(f"  Saltados (razón social)     : {saltados_razon_social}")
    print(f"  Saltados (sin extracción)   : {saltados_sin_extrac}")
    print(f"  Errores                     : {len(errores)}")
    print(f"{'='*57}")

    if errores:
        print("\n[ERRORES DETALLE]")
        for e in errores:
            print(f"  {e}")

    if dry_run:
        print("\n[DRY-RUN] No se escribió nada. Usa --execute para cargar.")
        return 0

    if not docs_a_insertar:
        print("[INFO] Nada que insertar.")
        return 0

    insertados  = 0
    saltados_dup = 0
    batch       = db.batch()
    pending     = 0

    for doc in docs_a_insertar:
        hash_f = doc.get("hash_factura")
        if hash_f and _hash_existe(db, hash_f):
            print(f"  [DUP] Ya existe {hash_f[:10]}… ({doc.get('filename')})")
            saltados_dup += 1
            continue

        batch.set(db.collection("facturas").document(), doc)
        pending    += 1
        insertados += 1

        if pending >= BATCH_SIZE:
            batch.commit()
            batch   = db.batch()
            pending = 0
            print(f"  Insertados {insertados}...")

    if pending:
        batch.commit()

    print(f"\n {insertados} documentos insertados | {saltados_dup} duplicados omitidos.")

    # ── Reconstruir resumen agregado (mantiene resumenes/{uid} sincronizado) ──
    if insertados > 0:
        print(f"\n[RESUMEN] Reconstruyendo resumenes/{OWNER_UID}...")
        reconstruir_resumen(db, OWNER_UID)
        print("[RESUMEN] OK")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
