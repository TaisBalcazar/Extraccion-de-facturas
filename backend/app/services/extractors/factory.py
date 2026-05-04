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
    def get_supported_categories() -> list:
        """
        Retorna lista de IDs de categorías soportadas.
        
        Returns:
            Lista de IDs de categoría
        """
        return list(_EXTRACTORS_MAP.keys())
    
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
    
    @staticmethod
    def register_extractor(category_id: str, extractor_class: type) -> None:
        """
        Registra un nuevo extractor para una categoría.
        
        Permite extender el sistema de extractores dinámicamente.
        
        Args:
            category_id: ID de la nueva categoría
            extractor_class: Clase que hereda de BaseCategoryExtractor
        
        Raises:
            TypeError: Si extractor_class no hereda de BaseCategoryExtractor
        
        Example:
            class CustomExtractor(BaseCategoryExtractor):
                pass
            
            ExtractorFactory.register_extractor("cat-custom", CustomExtractor)
        """
        if not issubclass(extractor_class, BaseCategoryExtractor):
            raise TypeError(
                f"extractor_class debe heredar de BaseCategoryExtractor, "
                f"recibió {extractor_class.__name__}"
            )
        
        _EXTRACTORS_MAP[category_id] = extractor_class
        print(f"✅ Extractor registrado: {category_id} -> {extractor_class.__name__}")
