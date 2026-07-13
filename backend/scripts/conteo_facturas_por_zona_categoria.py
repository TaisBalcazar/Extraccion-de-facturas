"""
Cuenta documentos de la colección 'facturas' del owner_uid indicado,
agrupados por (categoria_id, year, zona_id, centro).

Para categoria_id = "cat-4" desglosa además por tipo_documento
(agua / papel_bond / hospedaje).

Imprime el resultado ordenado y genera un CSV en:
    backend/scripts/output/conteo_facturas.csv

Al final imprime el total general de documentos leídos (== lecturas
de Firestore consumidas por este script).

Ejecutar desde la carpeta backend/:
    python scripts/conteo_facturas_por_zona_categoria.py
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.firebase import get_firestore_client, init_firebase  # noqa: E402
from google.cloud.firestore_v1.base_query import FieldFilter        # noqa: E402

OWNER_UID = "GSmOljJ3ROQhOe9EppQCh7MXU9Y2"
CAT4_ID = "cat-4"

OUTPUT_DIR = Path(__file__).resolve().parent / "output"
OUTPUT_CSV = OUTPUT_DIR / "conteo_facturas.csv"


def main() -> int:
    print("=" * 65)
    print("  Conteo de facturas por categoria / year / zona / centro")
    print("=" * 65)
    print(f"  owner_uid = {OWNER_UID}\n")

    init_firebase()
    db = get_firestore_client()
    if not db:
        print("[ERROR] No se pudo conectar a Firebase.")
        return 1

    # (categoria_id, year, zona_id, centro) -> count
    conteo: dict[tuple, int] = defaultdict(int)
    # (year, zona_id, centro, tipo_documento) -> count, solo cat-4
    conteo_cat4_tipo: dict[tuple, int] = defaultdict(int)

    total_docs = 0

    docs = (
        db.collection("facturas")
        .where(filter=FieldFilter("owner_uid", "==", OWNER_UID))
        .stream()
    )

    for doc in docs:
        total_docs += 1
        data = doc.to_dict() or {}

        categoria_id = data.get("categoria_id", "(sin_categoria)")
        year = data.get("year", "(sin_year)")
        zona_id = data.get("zona_id", "(sin_zona)")
        centro = data.get("centro", "(sin_centro)")

        conteo[(categoria_id, year, zona_id, centro)] += 1

        if categoria_id == CAT4_ID:
            tipo_documento = data.get("tipo_documento", "(sin_tipo_documento)")
            conteo_cat4_tipo[(year, zona_id, centro, tipo_documento)] += 1

    # ── Salida por consola ───────────────────────────────────────────
    print(f"Combinaciones distintas (categoria/year/zona/centro): {len(conteo)}\n")

    for (categoria_id, year, zona_id, centro), n in sorted(conteo.items(), key=lambda kv: kv[0]):
        print(f"  cat={categoria_id:<8} year={year!s:<6} zona={zona_id:<8} centro={centro:<30} -> {n}")

    if conteo_cat4_tipo:
        print(f"\nDesglose cat-4 por tipo_documento:\n")
        for (year, zona_id, centro, tipo_documento), n in sorted(conteo_cat4_tipo.items(), key=lambda kv: kv[0]):
            print(
                f"  year={year!s:<6} zona={zona_id:<8} centro={centro:<30} "
                f"tipo_documento={tipo_documento:<20} -> {n}"
            )

    # ── CSV ───────────────────────────────────────────────────────────
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_CSV, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["categoria_id", "year", "zona_id", "centro", "tipo_documento", "count"])
        for (categoria_id, year, zona_id, centro), n in sorted(conteo.items(), key=lambda kv: kv[0]):
            writer.writerow([categoria_id, year, zona_id, centro, "", n])
        for (year, zona_id, centro, tipo_documento), n in sorted(conteo_cat4_tipo.items(), key=lambda kv: kv[0]):
            writer.writerow([CAT4_ID, year, zona_id, centro, tipo_documento, n])

    print(f"\nCSV guardado en: {OUTPUT_CSV}")
    print(f"\nTotal general de documentos leídos: {total_docs}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
