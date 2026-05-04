"""
Módulo extractors - Sistema de extracción de facturas por categoría.

Proporciona extractores especializados para cada categoría de factura,
usando un patrón Factory para seleccionar el extractor apropiado.

Ejemplo de uso:
    from app.services.extractors import ExtractorFactory
    
    extractor = ExtractorFactory.get_extractor("cat-2")
    datos = extractor.extract(file_content, "factura.pdf")
"""

from app.services.extractors.factory import ExtractorFactory
from app.services.extractors.base import BaseCategoryExtractor

__all__ = [
    "ExtractorFactory",
    "BaseCategoryExtractor",
]
