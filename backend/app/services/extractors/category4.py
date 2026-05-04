"""
Extractor para Categoría 4: Residuos y Agua.

Extrae datos de facturas relacionadas con residuos, papel, limpieza y consumo de agua.
"""

from typing import Dict, Any

from app.services.schemas import Category4Schema
from app.services.extractors.base import BaseCategoryExtractor


class Category4Extractor(BaseCategoryExtractor):
    """Extractor especializado para facturas de residuos y agua."""
    
    def __init__(self):
        super().__init__(Category4Schema())
    
    def extract(self, file_content: bytes, filename: str) -> Dict[str, Any]:
        """
        Extrae datos de factura de residuos/agua.
        
        Busca gastos en papel, limpieza, materiales de oficina y consumo de agua.
        """
        try:
            print(f"📖 [CAT4 EXTRACTOR] Leyendo PDF: {filename}")
            texto_completo = self.extract_pdf_text(file_content)
            print(f"📖 [CAT4 EXTRACTOR] Texto extraído: {len(texto_completo)} caracteres")
            
            datos = self.initialize_data_dict()
            datos["filename"] = filename
            
            # Tipo de servicio
            datos["tipo_servicio"] = self.detect_service_type(texto_completo)
            
            # Número de factura
            factura_patterns = [
                r"factura[:\s#]*([A-Z0-9\-]+)",
                r"nro\.?\s*([0-9\-]+)",
                r"n[úu]mero[:\s]*([A-Z0-9\-]+)",
                r"invoice[:\s#]*([A-Z0-9\-]+)",
                r"fact\.\s*([A-Z0-9\-]+)",
            ]
            for pattern in factura_patterns:
                valor = self.extract_string(pattern, texto_completo)
                if valor and 3 <= len(valor) <= 30:
                    datos["factura_numero"] = valor
                    break
            
            # Fechas
            fechas = self.find_dates_in_text(texto_completo)
            if fechas:
                datos["fecha_emision"] = fechas[0]
                if len(fechas) > 1:
                    datos["periodo_inicio"] = fechas[0]
                    datos["periodo_fin"] = fechas[1]
            
            # Total USD
            total_patterns = [
                r"total\s+a\s+pagar[:\s]*\$?\s*(\d+[\.,]\d{2})",
                r"total[:\s]*\$?\s*(\d+[\.,]\d{2})",
                r"\$\s*(\d+[\.,]\d{2})\s*usd",
                r"base\s+imponible[:\s]*\$?\s*(\d+[\.,]\d{2})",
            ]
            datos["total_usd"] = self.extract_first_match(total_patterns, texto_completo)
            
            # ════════════════════════════════════════════════════════════
            # Campos específicos de Categoría 4
            # ════════════════════════════════════════════════════════════
            
            # Papel de baño (USD)
            papel_bano_patterns = [
                r"papel\s+de\s+ba[ñn]o\s*[:\s]*\$?\s*(\d+[\.,]?\d*)",
                r"ba[ñn]o\s+[:\s]*\$?\s*(\d+[\.,]?\d*)",
                r"ba[ñn]o.*?\$?\s*(\d+[\.,]?\d*)",
            ]
            datos["papel_bano"] = self.extract_first_match(papel_bano_patterns, texto_completo)
            
            # Papel bond (USD)
            papel_bond_patterns = [
                r"papel\s+bond\s*[:\s]*\$?\s*(\d+[\.,]?\d*)",
                r"(?:papel\s+)?bond\s*[:\s]*\$?\s*(\d+[\.,]?\d*)",
            ]
            datos["papel_bond"] = self.extract_first_match(papel_bond_patterns, texto_completo)
            
            # Materiales de oficina (USD)
            materiales_patterns = [
                r"materiales\s+(?:varios\s+)?de\s+oficina\s*[:\s]*\$?\s*(\d+[\.,]?\d*)",
                r"materiales\s+oficina\s*[:\s]*\$?\s*(\d+[\.,]?\d*)",
                r"materiales\s+varios[:\s]*\$?\s*(\d+[\.,]?\d*)",
            ]
            datos["materiales_oficina"] = self.extract_first_match(materiales_patterns, texto_completo)
            
            # Productos de limpieza (USD)
            limpieza_patterns = [
                r"productos\s+de\s+limpieza\s*[:\s]*\$?\s*(\d+[\.,]?\d*)",
                r"limpieza\s*[:\s]*\$?\s*(\d+[\.,]?\d*)",
                r"productos\s+limpieza[:\s]*\$?\s*(\d+[\.,]?\d*)",
            ]
            datos["productos_limpieza"] = self.extract_first_match(limpieza_patterns, texto_completo)
            
            # Vasos plásticos (USD)
            vasos_patterns = [
                r"vasos?\s+pl[áa]sticos?\s*[:\s]*\$?\s*(\d+[\.,]?\d*)",
                r"pl[áa]sticos?\s*[:\s]*\$?\s*(\d+[\.,]?\d*)",
                r"vasos\s+de\s+pl[áa]stico[:\s]*\$?\s*(\d+[\.,]?\d*)",
            ]
            datos["vasos_plasticos"] = self.extract_first_match(vasos_patterns, texto_completo)
            
            # Consumo de agua (m³)
            agua_patterns = [
                r"consumo\s+(?:de\s+)?agua\s*[:\s]*(\d+[\.,]?\d*)\s*m3",
                r"consumo\s+agua\s*[:\s]*(\d+[\.,]?\d*)",
                r"agua\s*[:\s]*(\d+[\.,]?\d*)\s*m[³3]",
                r"consumo[:\s]*(\d+[\.,]?\d*)\s*m[³3]",
            ]
            datos["consumo_agua"] = self.extract_first_match(agua_patterns, texto_completo)
            
            # Residuos orgánicos (kg)
            residuos_patterns = [
                r"residuos?\s+org[áa]nicos?.*relleno\s*[:\s]*(\d+[\.,]?\d*)",
                r"residuos?\s+org[áa]nicos?[:\s]*(\d+[\.,]?\d*)\s*kg",
                r"org[áa]nicos?\s+relleno[:\s]*(\d+[\.,]?\d*)",
            ]
            datos["residuos_organicos"] = self.extract_first_match(residuos_patterns, texto_completo)
            
            # Aguas residuales (m³)
            aguas_patterns = [
                r"aguas?\s+residuales?.*inodoros?\s*[:\s]*(\d+[\.,]?\d*)",
                r"aguas?\s+residuales?[:\s]*(\d+[\.,]?\d*)\s*m[³3]",
                r"inodoros?[:\s]*(\d+[\.,]?\d*)\s*m[³3]",
            ]
            datos["aguas_residuales"] = self.extract_first_match(aguas_patterns, texto_completo)
            
            datos["extraction_success"] = True
            datos["texto_completo"] = texto_completo[:500]
            
            print(f"✅ [CAT4 EXTRACTOR] Extracción exitosa")
            return datos
        
        except Exception as exc:
            print(f"❌ [CAT4 EXTRACTOR] Error: {exc}")
            return self.create_error_response(str(exc))
