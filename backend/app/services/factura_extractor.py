"""
Módulo principal para extracción de datos de facturas.

Actúa como interfaz centralizada usando el patrón Factory.
Delega la extracción específica a los extractores por categoría.
"""

from __future__ import annotations

from typing import Optional, Dict, Any

from app.services.extractors import ExtractorFactory


def convertir_fecha_a_iso(fecha_str: str) -> Optional[str]:
    """
    Convierte una cadena de fecha a formato ISO (YYYY-MM-DD).
    
    Soporta:
    - DD/MM/YYYY
    - YYYY/MM/DD
    - DD-MM-YYYY
    - YYYY-MM-DD
    
    Args:
        fecha_str: Cadena con la fecha
    
    Returns:
        Fecha en formato ISO o None
    """
    if not fecha_str:
        return None

    try:
        fecha_str = fecha_str.replace("/", "-")
        partes = fecha_str.split("-")
        if len(partes) == 3:
            if len(partes[0]) == 4:
                return fecha_str

            dia, mes, anio = partes
            if len(anio) == 2:
                anio = "20" + anio
            return f"{anio}-{mes.zfill(2)}-{dia.zfill(2)}"
    except Exception:
        return None

    return None


def extraer_datos_factura(
    file_content: bytes, 
    filename: str, 
    categoria_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Extrae datos de una factura PDF usando el extractor apropiado por categoría.
    
    Si no se especifica la categoría, intenta usar una lógica de detección
    (compatible hacia atrás con la versión anterior).
    
    Args:
        file_content: Contenido binario del archivo PDF
        filename: Nombre original del archivo
        categoria_id: ID de la categoría (ej: "cat-1", "cat-2", etc).
                      Si no se proporciona, intenta detectar automáticamente.
    
    Returns:
        Dict con los datos extraídos de la factura
    
    Example:
        # Con categoría especificada (recomendado)
        datos = extraer_datos_factura(file_content, "factura.pdf", "cat-2")
        
        # Sin categoría (compatible hacia atrás)
        datos = extraer_datos_factura(file_content, "factura.pdf")
    """
    try:
        print(f"📖 [EXTRACTOR] Leyendo archivo: {filename}")
        
        # Si se especifica categoría, usar el extractor específico
        if categoria_id and ExtractorFactory.is_supported(categoria_id):
            print(f"📂 [EXTRACTOR] Usando extractor para: {categoria_id}")
            extractor = ExtractorFactory.get_extractor(categoria_id)
            if extractor:
                datos = extractor.extract(file_content, filename)
                return datos
        
        # Fallback: intentar detectar automáticamente (Cat-2 para compatibilidad)
        print(f"⚠️  [EXTRACTOR] Categoría no especificada, usando detección automática (Cat-2)")
        extractor = ExtractorFactory.get_extractor("cat-2")
        if extractor:
            datos = extractor.extract(file_content, filename)
            return datos
        
        # Si nada funciona, retornar error
        return {
            "tipo_servicio": "Desconocido",
            "factura_numero": None,
            "medidor": None,
            "fecha_emision": None,
            "periodo_inicio": None,
            "periodo_fin": None,
            "total_usd": None,
            "consumo_kwh": None,
            "error": "No se pudo determinar la categoría o extractor no disponible",
        }
    
    except Exception as exc:
        print(f"❌ [EXTRACTOR] Error general: {exc}")
        return {
            "tipo_servicio": "Desconocido",
            "factura_numero": None,
            "medidor": None,
            "fecha_emision": None,
            "periodo_inicio": None,
            "periodo_fin": None,
            "total_usd": None,
            "consumo_kwh": None,
            "error": str(exc),
        }
