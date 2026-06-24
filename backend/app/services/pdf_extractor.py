"""
Optimización de extracción de PDFs con caching.

Evita leer el PDF múltiples veces durante la extracción de datos.
"""

import io
import re
from typing import Optional, Dict
import pdfplumber


class PDFExtractor:
    """
    Envoltura inteligente para extracción de PDFs con caching.
    
    Lee el PDF una sola vez y reutiliza los datos extraídos
    para todas las operaciones posteriores.
    """
    
    def __init__(self, file_content: bytes, filename: str = ""):
        """
        Inicializa el extractor con contenido del PDF.
        
        Args:
            file_content: Bytes del archivo PDF
            filename: Nombre del archivo (para logging)
        """
        self._content = file_content
        self._filename = filename
        self._text_cache: Optional[str] = None
        self._pdf_cache: Optional[pdfplumber.PDF] = None
        self._razon_social_cache: Optional[str] = None
        self._razon_social_valida_cache: Optional[bool] = None
    
    @property
    def texto_completo(self) -> str:
        """
        Retorna el texto completo del PDF (con caching).
        
        Returns:
            Texto extraído del PDF
        """
        if self._text_cache is None:
            self._extract_text()
        return self._text_cache
    
    @property
    def pdf_doc(self) -> pdfplumber.PDF:
        """
        Retorna el documento pdfplumber abierto (con caching).
        
        Returns:
            Documento PDF abierto
        """
        if self._pdf_cache is None:
            self._pdf_cache = pdfplumber.open(io.BytesIO(self._content))
        return self._pdf_cache
    
    def _extract_text(self) -> None:
        """Extrae y cachea el texto del PDF; usa OCR si el PDF está escaneado."""
        try:
            texto = ""
            for page in self.pdf_doc.pages:
                texto += page.extract_text() or ""

            from app.services.ocr_extractor import extract_text_smart
            texto, ocr_usado = extract_text_smart(self._content, texto)
            if ocr_usado:
                print(f"📷 OCR aplicado en '{self._filename}'")

            self._text_cache = texto
        except Exception as e:
            print(f"❌ Error extrayendo texto PDF: {e}")
            self._text_cache = ""
    
    def extract_text(self) -> str:
        """Retorna el texto completo (público)."""
        return self.texto_completo
    
    def get_tables(self, page_idx: int = 0) -> list:
        """
        Retorna tablas de una página específica.
        
        Args:
            page_idx: Índice de la página (0-based)
        
        Returns:
            Lista de tablas en la página
        """
        try:
            if page_idx >= len(self.pdf_doc.pages):
                return []
            return self.pdf_doc.pages[page_idx].extract_tables() or []
        except Exception as e:
            print(f"⚠️ Error extrayendo tablas: {e}")
            return []
    
    def get_all_tables(self) -> Dict[int, list]:
        """
        Retorna todas las tablas del documento por página.
        
        Returns:
            Dict {página: [tablas]}
        """
        result = {}
        try:
            for idx, page in enumerate(self.pdf_doc.pages):
                tables = page.extract_tables() or []
                if tables:
                    result[idx] = tables
        except Exception as e:
            print(f"⚠️ Error extrayendo todas las tablas: {e}")
        return result
    
    def set_razon_social(self, razon_social: str, es_valida: bool) -> None:
        """
        Cachea la razón social detectada.
        
        Args:
            razon_social: Razón social detectada
            es_valida: Si la razón social es válida
        """
        self._razon_social_cache = razon_social
        self._razon_social_valida_cache = es_valida
    
    def get_razon_social(self) -> Optional[str]:
        """Retorna la razón social cacheada."""
        return self._razon_social_cache
    
    def is_razon_social_valida(self) -> Optional[bool]:
        """Retorna si la razón social es válida."""
        return self._razon_social_valida_cache
    
    def close(self) -> None:
        """Cierra el documento PDF."""
        if self._pdf_cache:
            self._pdf_cache.close()
            self._pdf_cache = None
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        self.close()
