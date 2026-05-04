"""
Extractor para Categoría 3: Vuelos.

Nota: Los datos de vuelos típicamente vienen de archivos Excel, no PDF.
Este extractor es un placeholder para fase 2.
"""

from typing import Dict, Any

from app.services.schemas import Category3Schema
from app.services.extractors.base import BaseCategoryExtractor


class Category3Extractor(BaseCategoryExtractor):
    """
    Extractor para vuelos.
    
    NOTA: Esta categoría requiere procesamiento de archivos Excel.
    Por ahora retorna un error indicando que está en desarrollo.
    Se habilitará en fase 2 cuando se implemente soporte para Excel.
    """
    
    def __init__(self):
        super().__init__(Category3Schema())
    
    def extract(self, file_content: bytes, filename: str) -> Dict[str, Any]:
        """
        Placeholder para extracción de datos de vuelos.
        
        Retorna error indicando que esta categoría está en desarrollo.
        """
        print(f"⚠️  [CAT3 EXTRACTOR] Categoría 3 (Vuelos) en desarrollo")
        
        datos = self.initialize_data_dict()
        datos["filename"] = filename
        datos["tipo_servicio"] = "Vuelos"
        datos["extraction_success"] = False
        datos["error"] = (
            "Categoría 3 (Vuelos) se encuentra en desarrollo. "
            "Esta categoría requiere procesamiento de archivos Excel, "
            "no PDF. Será habilitada en fase 2. "
            "Por favor, sube los datos en formato Excel en su lugar."
        )
        
        return datos
