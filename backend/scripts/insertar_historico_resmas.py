"""
Script para insertar el histórico de resmas de papel bond (2018–2024) en Firestore.

Obtiene automáticamente el owner_uid, zona_id, zona_nombre y centro a partir de los
documentos de papel bond ya existentes en la colección 'facturas' (datos 2025).

Si no encuentra documentos existentes, solicita los datos al usuario.

Uso:
    cd backend
    python scripts/insertar_historico_resmas.py

Para omitir la confirmación interactiva:
    python scripts/insertar_historico_resmas.py --yes

Para forzar re-inserción aunque ya exista el año:
    python scripts/insertar_historico_resmas.py --force
"""

import sys
import os
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.firebase import get_firestore_client, init_firebase
from google.cloud.firestore_v1.base_query import FieldFilter

# ─────────────────────────────────────────────────────────────────────────────
# Datos históricos extraídos del PDF "Histórico de resmas de papel utilizadas"
# Campos: año → mes_numero → total_resmas
# Solo se incluyen 2018–2024 (2025 ya está cargado)
# ─────────────────────────────────────────────────────────────────────────────

PESO_KG_POR_RESMA = 2.33

MESES_NOMBRE = {
    1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
    5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
    9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre",
}

HISTORICO = {
    2018: {
        1: 1329, 2: 837,  3: 173,  4: 353,
        5: 1002, 6: 333,  7: 1473, 8: 1280,
        9: 370,  10: 228, 11: 920, 12: 142,
    },
    2019: {
        1: 1067, 2: 1195, 3: 579,  4: 400,
        5: 771,  6: 266,  7: 1185, 8: 654,
        9: 392,  10: 999, 11: 468, 12: 676,
    },
    2020: {
        1: 505,  2: 412,  3: 155,  4: 0,
        5: 0,    6: 34,   7: 75,   8: 0,
        9: 149,  10: 20,  11: 50,  12: 68,
    },
    2021: {
        1: 80,   2: 137,  3: 43,   4: 0,
        5: 0,    6: 121,  7: 150,  8: 75,
        9: 60,   10: 148, 11: 63,  12: 61,
    },
    2022: {
        1: 16,   2: 15,   3: 248,  4: 184,
        5: 247,  6: 6,    7: 1,    8: 85,
        9: 368,  10: 126, 11: 344, 12: 157,
    },
    2023: {
        1: 226,  2: 147,  3: 116,  4: 212,
        5: 197,  6: 816,  7: 256,  8: 0,
        9: 451,  10: 0,   11: 168, 12: 176,
    },
    2024: {
        1: 0,    2: 251,  3: 195,  4: 217,
        5: 30,   6: 69,   7: 64,   8: 138,
        9: 63,   10: 428, 11: 117, 12: 258,
    },
}


def _build_periodos(year: int, meses: dict) -> tuple[list, int, float, float]:
    """Construye la lista de periodos y los totales anuales para un año dado."""
    periodos = []
    for mes_num in range(1, 13):
        total_resmas = meses.get(mes_num, 0)
        peso_kg = round(total_resmas * PESO_KG_POR_RESMA, 3)
        peso_ton = round(peso_kg / 1000, 6)
        periodos.append({
            "mes_numero": mes_num,
            "mes_nombre": MESES_NOMBRE[mes_num],
            "total_resmas": total_resmas,
            "peso_papel_kg": peso_kg,
            "peso_papel_toneladas": peso_ton,
            "anio": year,
        })

    total_resmas_anual = sum(p["total_resmas"] for p in periodos)
    peso_kg_anual = round(total_resmas_anual * PESO_KG_POR_RESMA, 3)
    peso_ton_anual = round(peso_kg_anual / 1000, 6)

    return periodos, total_resmas_anual, peso_kg_anual, peso_ton_anual


def _buscar_metadata_existente(db) -> dict | None:
    """
    Busca un documento de papel bond existente en Firestore para reutilizar
    el owner_uid, zona_id, zona_nombre y centro.
    """
    try:
        docs = (
            db.collection("facturas")
            .where(filter=FieldFilter("tipo_documento", "==", "papel_bond"))
            .limit(1)
            .stream()
        )
        for doc in docs:
            data = doc.to_dict() or {}
            if data.get("owner_uid") and data.get("zona_id") and data.get("centro"):
                return {
                    "owner_uid":    data["owner_uid"],
                    "owner_email":  data.get("owner_email", ""),
                    "zona_id":      data["zona_id"],
                    "zona_nombre":  data.get("zona_nombre", ""),
                    "centro":       data["centro"],
                }
    except Exception as exc:
        print(f"[WARN] No se pudo consultar documentos existentes: {exc}")
    return None


def _solicitar_metadata_manual() -> dict:
    """Solicita al usuario los datos de asociación cuando no hay documentos previos."""
    print("\nNo se encontraron documentos de papel bond previos.")
    print("Por favor ingresa los datos de asociación:\n")
    owner_uid   = input("  owner_uid   (UID del usuario en Firebase): ").strip()
    owner_email = input("  owner_email (email del usuario): ").strip()
    zona_id     = input("  zona_id     (ej: zona-7): ").strip()
    zona_nombre = input("  zona_nombre (ej: Zona 7): ").strip()
    centro      = input("  centro      (ej: LOJA): ").strip()
    return {
        "owner_uid":    owner_uid,
        "owner_email":  owner_email,
        "zona_id":      zona_id,
        "zona_nombre":  zona_nombre,
        "centro":       centro,
    }


def _anio_ya_existe(db, owner_uid: str, zona_id: str, centro: str, anio: int) -> str | None:
    """Retorna el doc_id si ya existe un documento de papel bond para ese año, o None."""
    try:
        docs = (
            db.collection("facturas")
            .where(filter=FieldFilter("owner_uid", "==", owner_uid))
            .where(filter=FieldFilter("year", "==", anio))
            .stream()
        )
        for doc in docs:
            data = doc.to_dict() or {}
            if (
                data.get("tipo_documento") == "papel_bond"
                and data.get("zona_id") == zona_id
                and data.get("centro") == centro
            ):
                return doc.id
    except Exception as exc:
        print(f"[WARN] Error al verificar duplicado para {anio}: {exc}")
    return None


def main():
    force = "--force" in sys.argv
    autoconfirm = "--yes" in sys.argv

    print("=" * 60)
    print("  Inserción histórica de resmas de papel (2018–2024)")
    print("=" * 60)

    print("\n[*] Conectando a Firebase...")
    init_firebase()
    db = get_firestore_client()
    if not db:
        print("[ERROR] No se pudo conectar a Firebase.")
        sys.exit(1)
    print("[OK] Conexión exitosa.")

    # ── Obtener metadatos de asociación ──────────────────────────
    print("\n[*] Buscando metadatos de documentos existentes...")
    meta = _buscar_metadata_existente(db)
    if meta:
        print(f"[OK] Metadatos encontrados:")
        print(f"     owner_uid  : {meta['owner_uid'][:12]}...")
        print(f"     owner_email: {meta['owner_email']}")
        print(f"     zona_id    : {meta['zona_id']}")
        print(f"     zona_nombre: {meta['zona_nombre']}")
        print(f"     centro     : {meta['centro']}")
    else:
        meta = _solicitar_metadata_manual()

    if not meta["owner_uid"]:
        print("[ERROR] owner_uid es obligatorio.")
        sys.exit(1)

    # ── Confirmar antes de insertar ───────────────────────────────
    years_to_insert = sorted(HISTORICO.keys())
    print(f"\n[*] Se insertarán {len(years_to_insert)} años: {years_to_insert}")
    print(f"    Factor de peso: {PESO_KG_POR_RESMA} kg/resma")

    if not autoconfirm:
        resp = input("\n¿Continuar? (s/N): ").strip().lower()
        if resp not in ("s", "si", "sí", "y", "yes"):
            print("[!] Operación cancelada.")
            sys.exit(0)

    # ── Inserción ─────────────────────────────────────────────────
    print()
    now_iso = datetime.now().isoformat()
    insertados = 0
    omitidos = 0
    errores = 0

    for year in years_to_insert:
        meses = HISTORICO[year]

        # Verificar si ya existe
        doc_id_existente = _anio_ya_existe(db, meta["owner_uid"], meta["zona_id"], meta["centro"], year)
        if doc_id_existente and not force:
            print(f"[skip] {year} — ya existe (doc {doc_id_existente[:12]}...). Usa --force para sobreescribir.")
            omitidos += 1
            continue

        periodos, total_resmas, peso_kg, peso_ton = _build_periodos(year, meses)

        doc_data = {
            "filename":             f"historico_resmas_{year}.pdf",
            "upload_date":          now_iso,
            "owner_uid":            meta["owner_uid"],
            "owner_email":          meta["owner_email"],
            "zona_id":              meta["zona_id"],
            "zona_nombre":          meta["zona_nombre"],
            "centro":               meta["centro"],
            "categoria_id":         "cat-4",
            "categoria_nombre":     "Categoría 4",
            "item":                 "Papel bond",
            "tipo_documento":       "papel_bond",
            "anio":                 year,
            "fecha_emision":        f"{year}-12-31",
            "year":                 year,
            "periodos":             periodos,
            "total_resmas_anual":   total_resmas,
            "peso_papel_kg_anual":  peso_kg,
            "peso_papel_ton_anual": peso_ton,
        }

        try:
            if doc_id_existente and force:
                db.collection("facturas").document(doc_id_existente).set(doc_data)
                accion = "actualizado"
            else:
                ref = db.collection("facturas").add(doc_data)
                doc_id_existente = ref[1].id
                accion = "insertado"

            print(
                f"[OK]  {year} {accion} (doc {doc_id_existente[:12]}...) — "
                f"{total_resmas} resmas | {peso_kg} kg | {peso_ton} ton"
            )
            insertados += 1

        except Exception as exc:
            print(f"[ERR] {year} — Error: {exc}")
            errores += 1

    # ── Resumen ───────────────────────────────────────────────────
    print()
    print("=" * 60)
    print(f"  Completado: {insertados} insertados, {omitidos} omitidos, {errores} errores")
    print("=" * 60)
    if insertados > 0:
        print("\n[!] Recuerda reconstruir el resumen del usuario para que el dashboard")
        print("    refleje los nuevos datos:")
        print("    python scripts/backfill_resumenes.py --force")


if __name__ == "__main__":
    main()
