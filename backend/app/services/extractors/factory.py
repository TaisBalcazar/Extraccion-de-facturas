"""
Factory pattern para seleccionar el extractor correcto por categoría.

Proporciona una interfaz centralizada para obtener el extractor
apropiado según el ID de categoría.
"""

from typing import Dict, Optional

from app.services.extractors.base import BaseCategoryExtractor
from app.services.extractors.category1 import Category1Extractor
from app.services.extractors.category2 import Category2Extractor
from app.services.extractors.category3 import Category3Extractor
from app.services.extractors.category4 import Category4Extractor
from app.services.extractors.category5 import Category5Extractor


# Mapeo de categoría ID -> Extractor class
_EXTRACTORS_MAP: Dict[str, type] = {
    "cat-1": Category1Extractor,
    "cat-2": Category2Extractor,
    "cat-3": Category3Extractor,
    "cat-4": Category4Extractor,
    "cat-5": Category5Extractor,
}


class ExtractorFactory:
    """Factory para obtener extractores de facturas por categoría."""
    
    @staticmethod
    def get_extractor(category_id: str) -> Optional[BaseCategoryExtractor]:
        """
        Obtiene una instancia del extractor para la categoría indicada.
        
        Args:
            category_id: ID de la categoría (ej: "cat-1", "cat-2", etc)
        
        Returns:
            Instancia del extractor o None si la categoría no existe
        
        Example:
            extractor = ExtractorFactory.get_extractor("cat-2")
            datos = extractor.extract(file_content, "factura.pdf")
        """
        extractor_class = _EXTRACTORS_MAP.get(category_id)
        if extractor_class:
            return extractor_class()
        return None

    @staticmethod
    def is_supported(category_id: str) -> bool:
        """
        Verifica si una categoría es soportada.
        
        Args:
            category_id: ID de la categoría
        
        Returns:
            True si la categoría es soportada, False si no
        """
        return category_id in _EXTRACTORS_MAP
    
