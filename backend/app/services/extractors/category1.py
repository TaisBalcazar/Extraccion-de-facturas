"""
Extractor para Categoría 1: Gasolina/Combustible.

Extrae datos de facturas de combustible, diesel, gasolina y refrigerantes.
"""

import re
from datetime import datetime
from typing import Dict, Any, Optional

from app.services.schemas import Category1Schema
from app.services.extractors.base import BaseCategoryExtractor


class Category1Extractor(BaseCategoryExtractor):
    """Extractor especializado para facturas de gasolina/combustible."""
    
    def __init__(self):
        super().__init__(Category1Schema())

    @staticmethod
    def _to_float(raw_value: str) -> Optional[float]:
        normalized = (raw_value or "").strip().replace(" ", "")
        if not normalized:
            return None

        if "," in normalized and "." in normalized:
            if normalized.rfind(",") > normalized.rfind("."):
                normalized = normalized.replace(".", "").replace(",", ".")
            else:
                normalized = normalized.replace(",", "")
        elif "," in normalized:
            normalized = normalized.replace(".", "").replace(",", ".")

        try:
            return float(normalized)
        except ValueError:
            return None

    def _extract_float_from_patterns(self, text: str, patterns: list[str]) -> Optional[float]:
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if not match:
                continue
            value = self._to_float(match.group(1))
            if value is not None:
                return value
        return None

    @staticmethod
    def _is_numeric_token(token: str) -> bool:
        return re.fullmatch(r"\d+(?:[\.,]\d+)?", token or "") is not None

    def _extract_values_from_product_row(self, text: str) -> tuple[Optional[float], Optional[float], Optional[float]]:
        """
        Extrae (cantidad, precio_unitario, precio_linea) de la fila de producto.

        Ejemplo esperado de OCR:
        0121 16.573 DIESEL PREMIUM 1.5625 1.614455 3.176955 0.0 25.9
        """
        for raw_line in text.splitlines():
            line = re.sub(r"\s+", " ", (raw_line or "").strip())
            if not line:
                continue

            parts = line.split(" ")
            if len(parts) < 6:
                continue

            # La fila de detalle suele iniciar con código numérico.
            if not parts[0].isdigit():
                continue

            # La segunda columna suele ser cantidad.
            if not self._is_numeric_token(parts[1]):
                continue

            cantidad = self._to_float(parts[1])

            # Capturar columna numérica de derecha a izquierda (cola de importes).
            tail_numeric: list[float] = []
            for token in reversed(parts):
                if self._is_numeric_token(token):
                    val = self._to_float(token)
                    if val is not None:
                        tail_numeric.append(val)
                else:
                    break

            if not tail_numeric:
                continue

            tail_numeric.reverse()

            # En la estructura esperada, el primero de la cola es P.Unitario
            precio_unitario = tail_numeric[0]
            # El último suele ser el valor de línea (antes de IVA)
            precio_linea = tail_numeric[-1]

            if cantidad is not None and precio_unitario is not None:
                return cantidad, precio_unitario, precio_linea

        return None, None, None

    @staticmethod
    def _extract_factura_numero(text: str) -> Optional[str]:
        patterns = [
            r"\b(?:no\.?|n[°ºo]\.?|n[uú]mero)\s*[:\-]?\s*([0-9]{3}-[0-9]{3}-[0-9]{6,})",
            r"\bfactura\s*[:#]?\s*([0-9]{3}-[0-9]{3}-[0-9]{6,})",
            r"\b(?:no\.?|n[°ºo]\.?|n[uú]mero)\s*[:\-]?\s*([0-9][0-9\-]{5,})",
            r"\bfactura\s*[:#]?\s*([0-9][0-9\-]{5,})",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if not match:
                continue
            numero = match.group(1).strip()
            if numero:
                return numero
        return None

    def _extract_iva_amount(self, text: str) -> Optional[float]:
        """Extrae monto de IVA priorizando valores mayores a 0 cuando existan."""
        values: list[float] = []

        # 1) Parsear por línea con "iva" para distinguir porcentaje del monto.
        for raw_line in text.splitlines():
            line = (raw_line or "").strip()
            if not re.search(r"\biva\b", line, re.IGNORECASE):
                continue

            nums = re.findall(r"\d+(?:[\.,]\d+)?", line)
            parsed = [self._to_float(n) for n in nums]
            parsed = [v for v in parsed if v is not None]
            if not parsed:
                continue

            # Si la línea contiene %, el primer número suele ser la tasa (12.00)
            # y el siguiente el valor del IVA (3.10).
            if "%" in line and len(parsed) >= 2:
                values.extend(parsed[1:])
            else:
                values.extend(parsed)

        # 2) Fallback: patrón donde IVA % va seguido por valor.
        explicit = re.findall(
            r"iva\s*\d+(?:[\.,]\d+)?\s*%\s*[:\-]?\s*\$?\s*(\d+[\.,]\d+)",
            text,
            re.IGNORECASE,
        )
        for raw in explicit:
            val = self._to_float(raw)
            if val is not None:
                values.append(val)

        if not values:
            return None

        non_zero = [v for v in values if v > 0]
        return max(non_zero) if non_zero else values[0]

    @staticmethod
    def _select_best_emission_date(text: str, fechas_iso: list[str]) -> Optional[str]:
        """Selecciona la mejor fecha de emisión evitando falsos positivos de OCR."""
        # 1) Priorizar fechas junto a etiquetas de emisión/autorización
        keyword_patterns = [
            r"fecha\s+de\s+emisi[óo]n[^0-9]{0,40}(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})",
            r"fecha\s+y\s+hora\s+de\s+autorizaci[óo]n[^0-9]{0,40}(\d{4}[-/]\d{1,2}[-/]\d{1,2})",
            r"fecha\s+y\s+hora\s+de\s+autorizaci[óo]n[^0-9]{0,40}(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})",
        ]
        for pattern in keyword_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if not match:
                continue
            raw = match.group(1).replace("/", "-")
            partes = raw.split("-")
            if len(partes) != 3:
                continue
            if len(partes[0]) == 4:
                iso = raw
            else:
                dia, mes, anio = partes
                if len(anio) == 2:
                    anio = "20" + anio
                iso = f"{anio}-{mes.zfill(2)}-{dia.zfill(2)}"
            try:
                anio = int(iso[:4])
                if 2015 <= anio <= datetime.now().year + 1:
                    return iso
            except Exception:
                continue

        # 2) Si no hay contexto, escoger una fecha razonable reciente
        for iso in fechas_iso:
            try:
                anio = int(iso[:4])
                if 2015 <= anio <= datetime.now().year + 1:
                    return iso
            except Exception:
                continue

        return fechas_iso[0] if fechas_iso else None
    
    def extract(self, file_content: bytes, filename: str) -> Dict[str, Any]:
        """
        Extrae datos de factura de combustible.
        
        Busca consumos de diesel, gasolina, refrigerantes, etc. en galones o kg.
        """
        try:
            print(f"📖 [CAT1 EXTRACTOR] Leyendo PDF: {filename}")
            texto_completo = self.extract_pdf_text(file_content)
            print(f"📖 [CAT1 EXTRACTOR] Texto extraído: {len(texto_completo)} caracteres")
            
            datos = self.initialize_data_dict()
            datos["filename"] = filename
            
            # Número de factura conservando su formato (ej: 002-012-000374669).
            datos["factura_numero"] = self._extract_factura_numero(texto_completo)
            
            # Fechas
            fechas = self.find_dates_in_text(texto_completo)
            if fechas:
                datos["fecha_emision"] = self._select_best_emission_date(texto_completo, fechas)
                if len(fechas) > 1:
                    datos["periodo_inicio"] = fechas[0]
                    datos["periodo_fin"] = fechas[1]
            
            # Campos clave solicitados para categoría 1
            row_cantidad, row_pu, row_precio = self._extract_values_from_product_row(texto_completo)

            datos["precio_unitario"] = row_pu or self._extract_float_from_patterns(
                texto_completo,
                [
                    r"\b(?:p\s*[/\.]\s*u|p\.?\s*u\.?)\b\s*[:\-]?\s*\$?\s*([0-9][0-9\.,]*)",
                    r"p\.\s*unitario\s*[:\-]?\s*\$?\s*([0-9][0-9\.,]*)",
                    r"precio\s+unitario\s*[:\-]?\s*\$?\s*([0-9][0-9\.,]*)",
                    r"\bp\s*[/\.]?\s*u\b[^0-9]{0,20}([0-9][0-9\.,]*)",
                ],
            )
            datos["cantidad"] = row_cantidad or self._extract_float_from_patterns(
                texto_completo,
                [
                    r"\bcant(?:idad)?\.?\b\s*(?:\(\s*gal(?:ones)?\s*\))?\s*[:\-]?\s*([0-9][0-9\.,]*)",
                    r"\bcant(?:idad)?\.?\b[\s\r\n]+([0-9][0-9\.,]*)",
                    r"\bcant\.?\b[^0-9]{0,20}([0-9][0-9\.,]*)",
                    r"\bgal(?:ones)?\b\s*[:\-]?\s*([0-9][0-9\.,]*)",
                ],
            )
            datos["iva"] = self._extract_iva_amount(texto_completo)
            datos["total"] = self._extract_float_from_patterns(
                texto_completo,
                [
                    r"valor\s+total\s*(?:\(usd\))?\s*[:\-]?\s*\$?\s*([0-9][0-9\.,]*)",
                    r"\btotal\s+a\s+pagar\s*[:\-]?\s*\$?\s*([0-9][0-9\.,]*)",
                    r"\btotal\b\s*[:\-]?\s*\$?\s*([0-9][0-9\.,]*)",
                ],
            )

            # Si no se encontró total explícito, usar valor de línea + IVA.
            if datos.get("total") is None and row_precio is not None:
                iva_val = float(datos.get("iva") or 0)
                datos["total"] = round(float(row_precio) + iva_val, 2)

            # Fallback de tabla: cantidad ≈ total / precio_unitario.
            if (
                datos.get("cantidad") is None
                and datos.get("precio_unitario")
                and datos.get("total")
                and float(datos.get("precio_unitario") or 0) > 0
            ):
                datos["cantidad"] = round(float(datos["total"]) / float(datos["precio_unitario"]), 3)

            # Mantener compatibilidad con campos previos
            datos["total_usd"] = datos.get("total")
            
            datos["extraction_success"] = True
            datos["texto_completo"] = texto_completo[:500]
            
            print(f"✅ [CAT1 EXTRACTOR] Extracción exitosa")
            return datos
        
        except Exception as exc:
            print(f"❌ [CAT1 EXTRACTOR] Error: {exc}")
            return self.create_error_response(str(exc))
