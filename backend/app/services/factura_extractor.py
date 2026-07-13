"""
Módulo principal para extracción de datos de facturas.

Actúa como interfaz centralizada usando el patrón Factory.
Delega la extracción específica a los extractores por categoría.
"""

from __future__ import annotations

from typing import Optional, Dict, Any

from app.services.extractors import ExtractorFactory
from app.services.ocr_extractor import OCRNotAvailableError


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
        print(f"[EXTRACTOR] Leyendo archivo: {filename}")
        
        # Si se especifica categoría, usar el extractor específico
        if categoria_id and ExtractorFactory.is_supported(categoria_id):
            print(f"[EXTRACTOR] Usando extractor para: {categoria_id}")
            extractor = ExtractorFactory.get_extractor(categoria_id)
            if extractor:
                datos = extractor.extract(file_content, filename)
                return datos
        
        return {"categoria_id": None, "error": "categoria_id es requerido"}

    except OCRNotAvailableError:
        raise
    except Exception as exc:
        print(f"[EXTRACTOR] Error general: {exc}")
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
