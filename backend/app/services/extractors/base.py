"""
Clase base abstracta para extractores de facturas por categoría.

Define la interfaz que todos los extractores deben implementar.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import io
import re
from datetime import datetime

import pdfplumber

from app.services.schemas import CategorySchema


class BaseCategoryExtractor(ABC):
    """
    Clase base para extractores específicos por categoría.
    
    Define la interfaz que debe implementar cada extractor de categoría.
    Proporciona métodos utilitarios comunes para la extracción de datos.
    """
    
    def __init__(self, schema: CategorySchema):
        """
        Inicializa el extractor con su esquema asociado.
        
        Args:
            schema: Instancia de CategorySchema con definición de campos
        """
        self.schema = schema
        self.category_id = schema.category_id
        self.category_name = schema.category_name
    
    @abstractmethod
    def extract(self, file_content: bytes, filename: str) -> Dict[str, Any]:
        """
        Extrae datos específicos de la categoría desde un PDF.
        
        Método abstracto que cada categoría debe implementar.
        
        Args:
            file_content: Contenido binario del archivo PDF
            filename: Nombre original del archivo
        
        Returns:
            Dict con los datos extraídos. Debe contener al menos
            los campos definidos en self.schema.get_field_names()
        """
        pass
    
    # ════════════════════════════════════════════════════════════
    # Métodos utilitarios comunes para extracción
    # ════════════════════════════════════════════════════════════
    
    def extract_pdf_text(self, file_content: bytes) -> str:
        """
        Extrae todo el texto de un PDF; aplica OCR si el PDF está escaneado.

        Args:
            file_content: Contenido binario del PDF

        Returns:
            Texto completo extraído del PDF (o por OCR si estaba escaneado)

        Raises:
            Exception: Si hay error al procesar el PDF
        """
        try:
            with pdfplumber.open(io.BytesIO(file_content)) as pdf:
                texto_completo = ""
                for page in pdf.pages:
                    texto_completo += page.extract_text() or ""

            from app.services.ocr_extractor import extract_text_smart
            texto_completo, ocr_usado = extract_text_smart(file_content, texto_completo)
            if ocr_usado:
                print(f"OCR aplicado ({self.category_name})")

            return texto_completo
        except Exception as e:
            print(f"Error extrayendo texto PDF: {e}")
            raise
    
    def extract_date(self, fecha_str: str) -> Optional[str]:
        """
        Convierte una cadena de fecha a formato ISO (YYYY-MM-DD).
        
        Soporta formatos:
        - DD/MM/YYYY
        - YYYY/MM/DD
        - DD-MM-YYYY
        - YYYY-MM-DD
        
        Args:
            fecha_str: Cadena con la fecha
        
        Returns:
            Fecha en formato ISO o None si no puede convertir
        """
        if not fecha_str:
            return None
        
        try:
            fecha_str = fecha_str.replace("/", "-")
            partes = fecha_str.split("-")
            
            if len(partes) == 3:
                if len(partes[0]) == 4:
                    return fecha_str  # Ya es ISO
                
                dia, mes, anio = partes
                if len(anio) == 2:
                    anio = "20" + anio
                return f"{anio}-{mes.zfill(2)}-{dia.zfill(2)}"
        except Exception:
            pass
        
        return None
    
    def extract_value(self, pattern: str, text: str, group: int = 1) -> Optional[float]:
        """
        Busca un patrón regex y extrae un valor numérico.
        
        Args:
            pattern: Patrón regex para buscar
            text: Texto donde buscar
            group: Número de grupo a extraer (default: 1)
        
        Returns:
            Valor numérico o None si no encuentra
        """
        try:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                valor_str = match.group(group).replace(",", ".").replace(" ", "")
                return float(valor_str)
        except Exception:
            pass
        return None
    
    def extract_first_match(self, patterns: list, text: str) -> Optional[float]:
        """
        Intenta extraer un valor usando varios patrones regex.
        
        Retorna el primer valor encontrado.
        
        Args:
            patterns: Lista de patrones regex a intentar
            text: Texto donde buscar
        
        Returns:
            Primer valor encontrado o None
        """
        for pattern in patterns:
            value = self.extract_value(pattern, text)
            if value is not None:
                return value
        return None
    
    def extract_string(self, pattern: str, text: str, group: int = 1) -> Optional[str]:
        """
        Busca un patrón regex y extrae una cadena.
        
        Args:
            pattern: Patrón regex para buscar
            text: Texto donde buscar
            group: Número de grupo a extraer (default: 1)
        
        Returns:
            Cadena extraída o None
        """
        try:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(group).strip()
        except Exception:
            pass
        return None
    
    def initialize_data_dict(self) -> Dict[str, Any]:
        """
        Inicializa un diccionario con los campos de la categoría.
        
        Todos los campos se inicializan a None.
        
        Returns:
            Dict vacío con los nombres de campos esperados
        """
        data = {}
        for field_name in self.schema.get_field_names():
            data[field_name] = None
        data["category_id"] = self.category_id
        data["category_name"] = self.category_name
        return data
    
    def find_dates_in_text(self, text: str) -> list:
        """
        Encuentra todas las fechas en el texto.
        
        Args:
            text: Texto a analizar
        
        Returns:
            Lista de fechas en formato ISO, o vacía si no encuentra
        """
        fecha_patterns = [
            r"(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})",
            r"(\d{4}[-/]\d{1,2}[-/]\d{1,2})",
        ]
        
        fechas_encontradas = []
        for pattern in fecha_patterns:
            matches = re.findall(pattern, text)
            fechas_encontradas.extend(matches)
        
        # Convertir a ISO
        fechas_iso = []
        for fecha in fechas_encontradas:
            fecha_iso = self.extract_date(fecha)
            if fecha_iso and fecha_iso not in fechas_iso:
                fechas_iso.append(fecha_iso)
        
        return fechas_iso
    
    def create_error_response(self, error_msg: str) -> Dict[str, Any]:
        """
        Crea una respuesta de error con la estructura esperada.
        
        Args:
            error_msg: Mensaje de error
        
        Returns:
            Dict con la estructura de respuesta pero con error
        """
        data = self.initialize_data_dict()
        data["error"] = error_msg
        data["extraction_success"] = False
        return data
