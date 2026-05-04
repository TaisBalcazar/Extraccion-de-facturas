from __future__ import annotations

import re


MESES = {
    "enero": "01",
    "febrero": "02",
    "marzo": "03",
    "abril": "04",
    "mayo": "05",
    "junio": "06",
    "julio": "07",
    "agosto": "08",
    "septiembre": "09",
    "octubre": "10",
    "noviembre": "11",
    "diciembre": "12",
}


def detectar_filtros(mensaje: str) -> tuple[str | None, str | None, str | None]:
    year_match = re.search(r"20\d{2}", mensaje)
    year_filter = year_match.group(0) if year_match else None

    mes_filter = None
    for mes_nombre, mes_num in MESES.items():
        if mes_nombre in mensaje:
            mes_filter = mes_num
            break

    servicio_filter = None
    if "luz" in mensaje or "electricidad" in mensaje or "electrica" in mensaje:
        servicio_filter = "Electricidad"
    elif "agua" in mensaje:
        servicio_filter = "Agua"
    elif "solar" in mensaje or "panel" in mensaje:
        servicio_filter = "Solar"

    return year_filter, mes_filter, servicio_filter
