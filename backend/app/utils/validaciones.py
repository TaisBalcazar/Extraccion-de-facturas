import unicodedata

VARIANTES_RAZON_SOCIAL_UTPL = [
    "UNIVERSIDAD TECNICA PARTICULAR DE LOJA",
    "UNIVERSIDAD TÉCNICA PARTICULAR DE LOJA",
    "UTPL",
    "LEY DE PROTECCION DE DATOS",
    "LEY DE PROTECCIÓN DE DATOS",
]


def es_razon_social_valida(razon_social: str) -> bool:
    """
    Verifica que la razón social corresponde a UTPL.
    Acepta múltiples variantes porque la institución aparece de distintas
    formas en las facturas (incluyendo Ley de Protección de Datos).
    Solo se usa para validar — nunca se guarda en Firestore.
    """
    razon = str(razon_social).upper().strip()
    return any(v in razon for v in VARIANTES_RAZON_SOCIAL_UTPL)


# ──────────────────────────────────────────────────────────────
# Normalización de "centro" (nombre de sede/localidad)
# ──────────────────────────────────────────────────────────────
# Alias conocidos -> valor canónico. Solo se normalizan variantes de
# capitalización/espacios detectadas en datos reales (centro="Loja" vs
# "LOJA" en cat-4/agua). No se aplica un .upper() global porque algunos
# centros del catálogo tienen mayúsculas/minúsculas intencionales
# (ej. "GUAYAQUIL (Kennedy)" en zona-5).
_CENTRO_ALIASES: dict[str, str] = {
    "LOJA": "LOJA",
}


def _clave_centro(valor: str) -> str:
    """Clave de comparación: mayúsculas, sin espacios extremos, sin tildes."""
    texto = unicodedata.normalize("NFD", str(valor or "").strip().upper())
    return "".join(c for c in texto if unicodedata.category(c) != "Mn")


def normalizar_centro(centro: str) -> str:
    """
    Normaliza el valor de `centro` a su forma canónica cuando existe un alias
    conocido (ej. "Loja" / "loja" / " Loja " -> "LOJA"). Si no hay alias
    registrado, retorna el valor solo con espacios recortados, sin alterar
    su capitalización original.
    """
    if not centro:
        return centro
    limpio = str(centro).strip()
    return _CENTRO_ALIASES.get(_clave_centro(limpio), limpio)
