"""
normalizar_centro_cat4_loja.py

Corrige la inconsistencia de datos centro="Loja" (minusculas/capitalizado)
vs centro="LOJA" (mayusculas, valor canonico usado por el resto del sistema)
en la coleccion `facturas`.

Origen del bug: backend/scripts/importar_historico_cat4_agua.py escribio
"Loja" en 569 documentos historicos de agua (cat-4, 2018-2024) antes de que
el punto de origen fuera corregido para usar normalizar_centro().

Este script:
  1. Busca documentos cuyo campo `centro` normalice a "LOJA" pero cuyo valor
     crudo sea distinto (ej. "Loja", " Loja", "loja").
  2. Imprime un preview (conteo total + ejemplos) SIN escribir nada.
  3. Pide confirmacion explicita (o --confirm) antes de escribir.
  4. Actualiza los documentos afectados en Firestore usando batch writes.

Ejecutar desde la carpeta backend/:
    python scripts/normalizar_centro_cat4_loja.py             -> preview + pide confirmacion
    python scripts/normalizar_centro_cat4_loja.py --confirm   -> preview + escribe sin preguntar
"""

from __future__ import annotations

import argparse
import sys
import os

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from google.cloud.firestore_v1.base_query import FieldFilter

from app.core.firebase import get_firestore_client, init_firebase
from app.utils.validaciones import normalizar_centro

OWNER_UID = "GSmOljJ3ROQhOe9EppQCh7MXU9Y2"
BATCH_SIZE = 500


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Normaliza centro='Loja' -> 'LOJA' en la coleccion facturas."
    )
    parser.add_argument(
        "--confirm", action="store_true",
        help="Ejecuta la escritura sin pedir confirmacion interactiva."
    )
    args = parser.parse_args()

    print("=" * 60)
    print("  NORMALIZAR centro: 'Loja' -> 'LOJA' (owner: %s)" % OWNER_UID)
    print("=" * 60)
    print()

    print("[*] Conectando a Firebase...")
    init_firebase()
    db = get_firestore_client()
    if not db:
        print("[ERROR] No se pudo conectar a Firebase.")
        return 1

    print("[*] Escaneando facturas del owner...")
    docs = list(
        db.collection("facturas")
        .where(filter=FieldFilter("owner_uid", "==", OWNER_UID))
        .stream()
    )
    print(f"    Total documentos del owner: {len(docs)}")

    # Candidatos: el valor normalizado difiere del valor crudo guardado.
    candidatos: list[tuple[str, str, str, str, int | None]] = []  # (doc_id, categoria_id, valor_actual, valor_nuevo, year)
    for doc in docs:
        data = doc.to_dict() or {}
        centro_actual = data.get("centro")
        if not centro_actual:
            continue
        centro_normalizado = normalizar_centro(centro_actual)
        if centro_normalizado and centro_normalizado != centro_actual:
            candidatos.append((
                doc.id,
                data.get("categoria_id", "?"),
                centro_actual,
                centro_normalizado,
                data.get("year"),
            ))

    print()
    print(f"{'='*60}")
    print(f"  Documentos a modificar: {len(candidatos)}")
    print(f"{'='*60}")

    if not candidatos:
        print("[OK] No hay nada que normalizar. Todos los valores de centro ya son consistentes.")
        return 0

    # Desglose por categoria_id / year
    from collections import Counter
    desglose = Counter((c[1], c[4]) for c in candidatos)
    print("\n--- Desglose por categoria_id / year ---")
    for (cat, year), count in sorted(desglose.items(), key=lambda x: (str(x[0][0]), str(x[0][1]))):
        print(f"  cat={cat!s:8s} year={year!s:6s} -> {count} docs")

    print("\n--- Ejemplos (primeros 5) ---")
    for doc_id, cat, actual, nuevo, year in candidatos[:5]:
        print(f"  {doc_id:30s} | cat={cat:6s} | year={year!s:6s} | '{actual}' -> '{nuevo}'")

    print()

    if not args.confirm:
        resp = input(f"¿Actualizar estos {len(candidatos)} documento(s)? (s/N): ").strip().lower()
        if resp != "s":
            print("Operación cancelada. No se escribió nada.")
            return 0

    print()
    print("[*] Escribiendo actualizaciones en batches...")

    actualizados = 0
    batch = db.batch()
    pending = 0

    for doc_id, _cat, _actual, nuevo, _year in candidatos:
        ref = db.collection("facturas").document(doc_id)
        batch.update(ref, {"centro": nuevo})
        pending += 1
        actualizados += 1

        if pending >= BATCH_SIZE:
            batch.commit()
            batch = db.batch()
            pending = 0
            print(f"    Actualizados {actualizados}/{len(candidatos)}...")

    if pending:
        batch.commit()

    print()
    print(f"✅ {actualizados} documento(s) actualizados a centro='LOJA'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
