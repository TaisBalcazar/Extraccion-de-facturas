"""
Compilación anticipada de patrones regex para búsquedas eficientes.

Los patrones se compilan una sola vez en memoria para evitar
recompilar en cada búsqueda.
"""

import re
from typing import Dict, List, Optional, Tuple


class CompiledPattern:
    """Wrapper para un patrón compilado con opciones de búsqueda."""
    
    def __init__(self, pattern: str, flags: int = re.IGNORECASE):
        self.pattern_str = pattern
        self.compiled = re.compile(pattern, flags)
        self.flags = flags
    
    def search(self, text: str) -> Optional[re.Match]:
        """Busca el patrón en el texto."""
        return self.compiled.search(text)
    
    def findall(self, text: str) -> List[str]:
        """Encuentra todas las coincidencias."""
        return self.compiled.findall(text)
    
    def sub(self, repl: str, text: str) -> str:
        """Reemplaza usando el patrón."""
        return self.compiled.sub(repl, text)


class RegexPatternLibrary:
    """Librería centralizada de patrones regex compilados."""
    
    # ══════════════════════════════════════════════════════════
    # CATEGORÍA 2: ELECTRICIDAD
    # ══════════════════════════════════════════════════════════
    
    # Consumo total (kWh)
    CAT2_CONSUMO_PATTERNS = [
        CompiledPattern(r"consumo\s+total\s*[:\-]?\s*([0-9][0-9\.,]*)\s*kwh"),
        CompiledPattern(r"consumo\s+total\s*[:\-]?\s*([0-9][0-9\.,]*)"),
        CompiledPattern(r"consumo\s*\(?\s*kwh\s*\)?\s*[:\-]?\s*([0-9][0-9\.,]*)"),
        CompiledPattern(r"energ[íi]a\s+consumida\s*\(?\s*kwh\s*\)?\s*[:\-]?\s*([0-9][0-9\.,]*)"),
        CompiledPattern(r"consumo\s+facturado\s*[:\-]?\s*([0-9][0-9\.,]*)"),
        CompiledPattern(r"consumo\s+del\s+mes\s*[:\-]?\s*([0-9][0-9\.,]*)"),
        CompiledPattern(r"total\s+consumo\s*[:\-]?\s*([0-9][0-9\.,]*)"),
        CompiledPattern(r"diferencia\s+(?:de\s+)?(?:lectura|consumo)\s*[:\-]?\s*([0-9][0-9\.,]*)"),
        CompiledPattern(r"\bconsumo\b\s*[:\-]?\s*([0-9][0-9\.,]*)\s*kwh"),
    ]
    
    # Código único eléctrico
    CAT2_COD_UNICO_PATTERNS = [
        CompiledPattern(r"c[óo]digo\s+[úu]nico\s+el[ée]ctrico\s*[:\-]?\s*([A-Z0-9\-]+)"),
        CompiledPattern(r"cod\.?\s*[úu]nico\s*[:\-]?\s*([A-Z0-9\-]+)"),
    ]
    
    # Número de factura
    CAT2_NRO_FACTURA_PATTERNS = [
        CompiledPattern(r"nro\.?\s*factura\s*[:\-]?\s*([0-9\-]+)"),
        CompiledPattern(r"n[°ºo]\.?\s*factura\s*[:\-]?\s*([0-9\-]+)"),
        CompiledPattern(r"factura\s*[:#]?\s*([0-9\-]{6,})"),
    ]
    
    # Medidor/Contador
    CAT2_MEDIDOR_PATTERNS = [
        CompiledPattern(r"n[úu]mero\s+de\s+medidor\s*[:\-]?\s*([A-Z0-9\-]+)"),
        CompiledPattern(r"medidor\s*[:#]?\s*([A-Z0-9\-]+)"),
        CompiledPattern(r"contador\s*[:#]?\s*([A-Z0-9\-]+)"),
    ]
    
    # Lecturas
    CAT2_LECTURA_ANTERIOR_PATTERNS = [
        CompiledPattern(r"lectura\s+anterior\s*[:\-]?\s*([0-9][0-9\.,]*)"),
        CompiledPattern(r"lectura\s+inicial\s*[:\-]?\s*([0-9][0-9\.,]*)"),
    ]
    
    CAT2_LECTURA_ACTUAL_PATTERNS = [
        CompiledPattern(r"lectura\s+actual\s*[:\-]?\s*([0-9][0-9\.,]*)"),
        CompiledPattern(r"lectura\s+final\s*[:\-]?\s*([0-9][0-9\.,]*)"),
    ]
    
    # Razón Social (general, reutilizable)
    RAZON_SOCIAL_PATTERN = CompiledPattern(
        r"raz[óo]n\s+social\s*[:\-]?\s*(.+?)(?:\n|ruc|$)"
    )
    
    # Validación: línea de kWh (para fallback)
    KWH_LINE_PATTERN = CompiledPattern(r"([0-9][0-9\.,]*)\s*k\s*w\s*h")
    
    # Normalización de números
    OCR_FIX_O_PATTERN = CompiledPattern(r"(?<=\d)[oO](?=\d)")
    OCR_FIX_I_PATTERN = CompiledPattern(r"(?<=\d)[iIlL](?=\d)")
    
    # Headers de tabla (normalización)
    NORMALIZE_WHITESPACE = CompiledPattern(r"\s+")
    
    @classmethod
    def search_patterns(cls, patterns: List[CompiledPattern], text: str) -> Optional[str]:
        """
        Busca usando una lista de patrones y retorna el primer match.
        
        Args:
            patterns: Lista de CompiledPattern
            text: Texto a buscar
        
        Returns:
            Primer grupo capturado o None
        """
        for pattern in patterns:
            match = pattern.search(text)
            if match:
                return match.group(1)
        return None
    
    @classmethod
    def search_all_patterns(cls, patterns: List[CompiledPattern], text: str) -> List[str]:
        """
        Busca usando una lista de patrones y retorna todos los matches.
        
        Args:
            patterns: Lista de CompiledPattern
            text: Texto a buscar
        
        Returns:
            Lista de todos los grupos capturados
        """
        results = []
        for pattern in patterns:
            match = pattern.search(text)
            if match:
                results.append(match.group(1))
        return results
