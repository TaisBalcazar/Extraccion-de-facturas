"""
Extractor para Categoría 2: Electricidad.

Extrae datos de facturas de consumo eléctrico.
OPTIMIZADO: Usa patrones regex compilados para mejor rendimiento.
"""

import re
import io
from typing import Dict, Any, Optional

import pdfplumber

from app.services.schemas import Category2Schema
from app.services.extractors.base import BaseCategoryExtractor
from app.services.regex_patterns import RegexPatternLibrary


class Category2Extractor(BaseCategoryExtractor):
    """Extractor especializado para facturas de electricidad."""
    
    def __init__(self):
        super().__init__(Category2Schema())

    @staticmethod
    def _to_float(raw_value: str) -> Optional[float]:
        normalized = (raw_value or "").strip().replace(" ", "")
        if not normalized:
            return None

        # OCR frecuente en PDFs: confunde O/0 e I/1 dentro de números.
        normalized = re.sub(r"(?<=\d)[oO](?=\d)", "0", normalized)
        normalized = re.sub(r"(?<=\d)[iIlL](?=\d)", "1", normalized)

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
    def _extract_numbers_from_line(line: str) -> list[float]:
        raw_numbers = re.findall(r"([0-9][0-9\.,]*)", line or "")
        numbers: list[float] = []
        for raw in raw_numbers:
            normalized = Category2Extractor._to_float(raw)
            if normalized is not None:
                numbers.append(normalized)
        return numbers

    def _extract_consumo_from_lines(self, text: str) -> Optional[float]:
        """Busca consumo en líneas con contexto semántico cuando el patrón directo falla."""
        lines = [line.strip() for line in (text or "").splitlines() if line.strip()]

        for line in lines:
            line_lower = line.lower()
            if "consumo" not in line_lower and "kwh" not in line_lower:
                continue

            # Evitar capturar líneas monetarias.
            if "$" in line or "usd" in line_lower:
                continue

            values = self._extract_numbers_from_line(line)
            if not values:
                continue

            # Preferir el último valor numérico de la línea de consumo.
            candidate = values[-1]
            if candidate > 0:
                return candidate

        return None

    def _extract_consumo_from_any_kwh(self, text: str) -> Optional[float]:
        """Fallback final: toma un valor cercano a kWh cuando no hay etiqueta clara."""
        matches = re.findall(r"([0-9][0-9\.,]*)\s*k\s*w\s*h", text or "", re.IGNORECASE)
        candidates = [self._to_float(m) for m in matches]
        candidates = [c for c in candidates if c is not None and c > 0]
        if not candidates:
            return None

        # Evitar valores fuera de rango típico de lectura mensual.
        plausible = [c for c in candidates if c <= 50000]
        if plausible:
            return plausible[0]
        return candidates[0]

    def _extract_consumo_total(self, text: str) -> Optional[float]:
        """Extrae consumo total en kWh en varios formatos comunes de factura."""
        consumo = self._extract_float_from_patterns(
            text,
            [
                r"consumo\s+total\s*[:\-]?\s*([0-9][0-9\.,]*)\s*kwh",
                r"consumo\s+total\s*[:\-]?\s*([0-9][0-9\.,]*)",
                r"consumo\s*\(?\s*kwh\s*\)?\s*[:\-]?\s*([0-9][0-9\.,]*)",
                r"energ[íi]a\s+consumida\s*\(?\s*kwh\s*\)?\s*[:\-]?\s*([0-9][0-9\.,]*)",
                r"consumo\s+facturado\s*[:\-]?\s*([0-9][0-9\.,]*)",
                r"consumo\s+del\s+mes\s*[:\-]?\s*([0-9][0-9\.,]*)",
                r"total\s+consumo\s*[:\-]?\s*([0-9][0-9\.,]*)",
                r"diferencia\s+(?:de\s+)?(?:lectura|consumo)\s*[:\-]?\s*([0-9][0-9\.,]*)",
                r"\bconsumo\b\s*[:\-]?\s*([0-9][0-9\.,]*)\s*kwh",
                r"consumo\s+total\s*[:\-]?\s*([0-9OoIl][0-9OoIl\.,]*)",
            ],
        )
        if consumo is not None:
            return consumo

        consumo = self._extract_consumo_from_lines(text)
        if consumo is not None:
            return consumo

        return self._extract_consumo_from_any_kwh(text)

    @staticmethod
    def _normalize_header_cell(cell: object) -> str:
        text = re.sub(r"\s+", "", str(cell or "")).lower()
        text = text.replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u")
        return text

    @staticmethod
    def _find_consumo_total_column(header_row: list[str]) -> Optional[int]:
        """Encuentra la columna de consumo total evitando subtotal e interno."""
        # Prioridad 1: coincidencia exacta/compacta 'consumototal'.
        for idx, cell in enumerate(header_row):
            if "consumototal" in cell:
                return idx

        # Prioridad 2: contiene consumo + total, pero excluye subtotal/interno/transformador.
        for idx, cell in enumerate(header_row):
            if "consumo" not in cell or "total" not in cell:
                continue
            if "subtotal" in cell:
                continue
            if "interno" in cell or "transformador" in cell:
                continue
            return idx

        # Último recurso: una columna solo llamada consumo (sin subtotal/interno)
        for idx, cell in enumerate(header_row):
            if "consumo" not in cell:
                continue
            if "subtotal" in cell:
                continue
            if "interno" in cell or "transformador" in cell:
                continue
            return idx

        return None

    def _extract_consumo_total_from_tables(self, file_content: bytes) -> Optional[float]:
        """Prioriza extracción desde tablas donde existe columna 'Consumo Total'."""
        try:
            with pdfplumber.open(io.BytesIO(file_content)) as pdf:
                for page in pdf.pages:
                    tables = page.extract_tables() or []
                    for table in tables:
                        if not table or len(table) < 2:
                            continue

                        n_cols = max(len(row) for row in table if row)

                        def cell(row_idx: int, col_idx: int) -> str:
                            if row_idx >= len(table):
                                return ""
                            row = table[row_idx] or []
                            if col_idx >= len(row):
                                return ""
                            return self._normalize_header_cell(row[col_idx])

                        def build_header(r1: int, r2: Optional[int]) -> list[str]:
                            header: list[str] = []
                            for c in range(n_cols):
                                top = cell(r1, c)
                                bottom = cell(r2, c) if r2 is not None else ""
                                header.append(top + bottom)
                            return header

                        for header_row in range(min(3, len(table) - 1)):
                            # Algunos PDFs parten cabecera en dos filas (ej: "Consumo" + "Total").
                            header = build_header(header_row, header_row + 1)
                            consumo_total_idx = self._find_consumo_total_column(header)

                            if consumo_total_idx is None:
                                # fallback: cabecera en una sola fila
                                header = build_header(header_row, None)
                                consumo_total_idx = self._find_consumo_total_column(header)

                            if consumo_total_idx is None:
                                continue

                            consumo_subtotal_idx = next(
                                (idx for idx, h in enumerate(header) if "consumo" in h and "subtotal" in h),
                                None,
                            )
                            unidad_idx = next(
                                (
                                    idx
                                    for idx, h in enumerate(header)
                                    if "unidad" in h and ("medida" in h or "unidadmedida" in h)
                                ),
                                None,
                            )
                            descripcion_idx = next(
                                (
                                    idx
                                    for idx, h in enumerate(header)
                                    if "descripcion" in h
                                ),
                                0,
                            )

                            data_start = header_row + 2
                            
                            # FIX: Si el header estaba en 1 sola fila (con \n internos), pdfplumber
                            # pone todo en header_row y los datos reales están en header_row+1.
                            # Detectamos esto viendo si header_row+1 tiene un valor numérico en
                            # la columna consumo_total (indicando que es fila de datos, no de header).
                            if header_row + 1 < len(table):
                                next_row = table[header_row + 1] or []
                                next_cell = str(next_row[consumo_total_idx] if consumo_total_idx < len(next_row) else "").strip()
                                if re.match(r"^[0-9]", next_cell):
                                    data_start = header_row + 1
                            
                            best_consumo: Optional[float] = None

                            for data_row in table[data_start:]:
                                if not data_row:
                                    continue

                                raw_values = [str(v or "").strip() for v in data_row]
                                if not any(raw_values):
                                    continue

                                if consumo_total_idx >= len(raw_values):
                                    continue

                                # Filtrar por unidad energética principal.
                                if unidad_idx is not None and unidad_idx < len(raw_values):
                                    unidad = raw_values[unidad_idx].lower().replace(" ", "")
                                    if unidad and "kwh" not in unidad:
                                        continue

                                consumo_total = self._to_float(raw_values[consumo_total_idx])
                                if consumo_total is None or consumo_total <= 0:
                                    continue

                                consumo_subtotal = None
                                if consumo_subtotal_idx is not None and consumo_subtotal_idx < len(raw_values):
                                    consumo_subtotal = self._to_float(raw_values[consumo_subtotal_idx])

                                if consumo_subtotal is not None and consumo_total < consumo_subtotal:
                                    # Si algo sale invertido por OCR, usar el mayor entre ambos.
                                    consumo_total = max(consumo_total, consumo_subtotal)

                                descripcion = ""
                                if descripcion_idx is not None and descripcion_idx < len(raw_values):
                                    descripcion = self._normalize_header_cell(raw_values[descripcion_idx])

                                # Priorizar fila "energía activa total" si existe.
                                if "energiaactivatotal" in descripcion:
                                    return consumo_total

                                if best_consumo is None or consumo_total > best_consumo:
                                    best_consumo = consumo_total

                            if best_consumo is not None:
                                return best_consumo
        except Exception as exc:
            print(f"⚠️ [CAT2 EXTRACTOR] Error leyendo tablas para consumo_total: {exc}")

        return None

    @staticmethod
    def _extract_digits_from_patterns(text: str, patterns: list[str]) -> Optional[str]:
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if not match:
                continue
            digits = re.sub(r"\D", "", match.group(1))
            if digits:
                return digits
        return None
    
    def extract(self, file_content: bytes, filename: str) -> Dict[str, Any]:
        """
        Extrae datos de factura de electricidad.
        
        Busca medidor, consumo en kWh, lecturas, subtotales, IVA, etc.
        """
        try:
            print(f"📖 [CAT2 EXTRACTOR] Leyendo PDF: {filename}")
            texto_completo = self.extract_pdf_text(file_content)
            print(f"📖 [CAT2 EXTRACTOR] Texto extraído: {len(texto_completo)} caracteres")
            
            datos = self.initialize_data_dict()
            datos["filename"] = filename
            datos["tipo_servicio"] = "Electricidad"
            
            # Código único eléctrico
            datos["cod_unico"] = self._extract_digits_from_patterns(
                texto_completo,
                [
                    r"c[óo]digo\s+[úu]nico\s+el[ée]ctrico\s*[:\-]?\s*([A-Z0-9\-]+)",
                    r"cod\.?\s*[úu]nico\s*[:\-]?\s*([A-Z0-9\-]+)",
                ],
            )

            # Nro. factura con solo números
            datos["nro_factura"] = self._extract_digits_from_patterns(
                texto_completo,
                [
                    r"nro\.?\s*factura\s*[:\-]?\s*([0-9\-]+)",
                    r"n[°ºo]\.?\s*factura\s*[:\-]?\s*([0-9\-]+)",
                    r"factura\s*[:#]?\s*([0-9\-]{6,})",
                ],
            )
            
            # Medidor: conservar solo el número
            datos["medidor"] = self._extract_digits_from_patterns(
                texto_completo,
                [
                    r"n[úu]mero\s+de\s+medidor\s*[:\-]?\s*([A-Z0-9\-]+)",
                    r"medidor\s*[:#]?\s*([A-Z0-9\-]+)",
                    r"contador\s*[:#]?\s*([A-Z0-9\-]+)",
                ],
            )
            
            # Razón Social
            datos["razon_social"] = None
            match_rs = re.search(
                r"raz[óo]n\s+social\s*[:\-]?\s*(.+?)(?:\n|ruc|$)",
                texto_completo, re.IGNORECASE
            )
            if match_rs:
                datos["razon_social"] = match_rs.group(1).strip()

            # Tipo de tarifa ARCONEL
            datos["tipo_tarifa"] = None
            match_tarifa = re.search(
                r"tipo\s+de\s+tarifa\s+arconel\s*[:\-]?\s*(.+?)(?:\n|geocod|$)",
                texto_completo, re.IGNORECASE
            )
            if match_tarifa:
                datos["tipo_tarifa"] = match_tarifa.group(1).strip()

            # Dirección / Ubicación del servicio
            datos["direccion_servicio"] = None
            match_dir = re.search(
                r"direcci[óo]n\s+(?:del\s+)?servicio\s*[:\-]?\s*(.+?)(?:\n|$)",
                texto_completo, re.IGNORECASE
            )
            if match_dir:
                datos["direccion_servicio"] = match_dir.group(1).strip()

            # Días facturados
            datos["dias_facturados"] = self._extract_float_from_patterns(
                texto_completo,
                [
                    r"d[íi]as\s+facturados\s*[:\-]?\s*([0-9]+)",
                    r"facturados\s*[:\-]?\s*([0-9]+)",
                ],
            )

            # Fechas: emisión, periodo inicio y fin
            datos["fecha_emision"] = None
            match_emision = re.search(
                r"fecha\s+de\s+emisi[óo]n\s*[:\-]?\s*([0-9]{2}[-/][0-9]{2}[-/][0-9]{4})",
                texto_completo, re.IGNORECASE
            )
            if match_emision:
                datos["fecha_emision"] = match_emision.group(1).strip()

            datos["periodo_inicio"] = None
            match_desde = re.search(
                r"fecha\s+desde\s*[:\-]?\s*([0-9]{2}[-/][0-9]{2}[-/][0-9]{4})",
                texto_completo, re.IGNORECASE
            )
            if match_desde:
                datos["periodo_inicio"] = match_desde.group(1).strip()
                # Derivar año y mes del período
                partes = re.split(r"[-/]", datos["periodo_inicio"])
                if len(partes) == 3:
                    datos["anio"] = int(partes[2])
                    datos["mes_numero"] = int(partes[1])
                    meses = {1:"Enero",2:"Febrero",3:"Marzo",4:"Abril",5:"Mayo",6:"Junio",
                             7:"Julio",8:"Agosto",9:"Septiembre",10:"Octubre",11:"Noviembre",12:"Diciembre"}
                    datos["mes_nombre"] = meses.get(datos["mes_numero"], "")

            datos["periodo_fin"] = None
            match_hasta = re.search(
                r"fecha\s+hasta\s*[:\-]?\s*([0-9]{2}[-/][0-9]{2}[-/][0-9]{4})",
                texto_completo, re.IGNORECASE
            )
            if match_hasta:
                datos["periodo_fin"] = match_hasta.group(1).strip()
            
            # Campos clave solicitados para categoría 2
            datos["lectura_anterior"] = self._extract_float_from_patterns(
                texto_completo,
                [
                    r"lectura\s+anterior\s*[:\-]?\s*([0-9][0-9\.,]*)",
                    r"lect\.\s*anterior\s*[:\-]?\s*([0-9][0-9\.,]*)",
                ],
            )
            datos["lectura_actual"] = self._extract_float_from_patterns(
                texto_completo,
                [
                    r"lectura\s+actual\s*[:\-]?\s*([0-9][0-9\.,]*)",
                    r"lect\.\s*actual\s*[:\-]?\s*([0-9][0-9\.,]*)",
                ],
            )
            datos["diferencia_consumo"] = self._extract_float_from_patterns(
                texto_completo,
                [
                    r"diferencia\s+(?:de\s+)?(?:lectura|consumo)\s*[:\-]?\s*([0-9][0-9\.,]*)",
                    r"consumo\s*[:\-]?\s*([0-9][0-9\.,]*)\s*kwh",
                ],
            )
            datos["consumo_subtotal"] = self._extract_float_from_patterns(
                texto_completo,
                [
                    r"consumo\s+subtotal\s*[:\-]?\s*([0-9][0-9\.,]*)",
                ],
            )
            datos["consumo_interno_transformador"] = self._extract_float_from_patterns(
                texto_completo,
                [
                    r"consumo\s+interno\s+transformador\s*[:\-]?\s*([0-9][0-9\.,]*)",
                    r"interno\s+transformador\s*[:\-]?\s*([0-9][0-9\.,]*)",
                ],
            )

            datos["consumo_total"] = self._extract_consumo_total_from_tables(file_content)
            if datos["consumo_total"] is None:
                datos["consumo_total"] = self._extract_consumo_total(texto_completo)

            # Fallback robusto: usar diferencia o calcular por lecturas cuando falta consumo_total.
            if datos["consumo_total"] is None:
                if datos.get("diferencia_consumo") is not None:
                    datos["consumo_total"] = datos["diferencia_consumo"]
                elif (
                    datos.get("lectura_actual") is not None
                    and datos.get("lectura_anterior") is not None
                    and datos["lectura_actual"] >= datos["lectura_anterior"]
                ):
                    datos["consumo_total"] = round(
                        datos["lectura_actual"] - datos["lectura_anterior"],
                        3,
                    )

            # Reconciliación final para evitar truncamientos/OCR (ej: 30/31 en lugar de 3103).
            lectura_diff = None
            if (
                datos.get("lectura_actual") is not None
                and datos.get("lectura_anterior") is not None
                and datos["lectura_actual"] >= datos["lectura_anterior"]
            ):
                lectura_diff = round(datos["lectura_actual"] - datos["lectura_anterior"], 3)

            interno = float(datos.get("consumo_interno_transformador") or 0)
            subtotal = datos.get("consumo_subtotal")

            # Caso ideal de estas facturas: total = subtotal + interno.
            if subtotal is not None and interno > 0:
                total_estimado = round(float(subtotal) + interno, 3)
                if (
                    datos.get("consumo_total") is None
                    or float(datos["consumo_total"]) < total_estimado * 0.8
                ):
                    print(
                        f"ℹ️ [CAT2 EXTRACTOR] Ajustando consumo_total con subtotal+interno: "
                        f"{datos.get('consumo_total')} -> {total_estimado}"
                    )
                    datos["consumo_total"] = total_estimado

            # Si quedó muy por debajo de la diferencia de lecturas, corregir.
            if lectura_diff is not None and datos.get("consumo_total") is not None:
                consumo_total_val = float(datos["consumo_total"])
                if consumo_total_val < lectura_diff * 0.7:
                    corregido = round(lectura_diff + interno, 3) if interno > 0 else lectura_diff
                    print(
                        f"ℹ️ [CAT2 EXTRACTOR] Ajustando consumo_total por lecturas: "
                        f"{consumo_total_val} -> {corregido}"
                    )
                    datos["consumo_total"] = corregido

            # Compatibilidad para consumidores que aún leen consumo_kwh.
            if datos.get("consumo_total") is not None:
                datos["consumo_kwh"] = datos["consumo_total"]
            else:
                # Log de diagnóstico para casos donde el PDF trae formato no contemplado.
                lineas_consumo = [
                    line.strip() for line in texto_completo.splitlines()
                    if line and ("consumo" in line.lower() or "kwh" in line.lower())
                ]
                print(f"⚠️ [CAT2 EXTRACTOR] consumo_total no detectado. Líneas candidatas: {lineas_consumo[:6]}")
            datos["total_sec_elec"] = self._extract_float_from_patterns(
                texto_completo,
                [
                    r"total\s+sector\s+el[ée]ctrico\s*\(?a\)?\s*[:\-]?\s*\$?\s*([0-9][0-9\.,]*)",
                    r"sector\s+el[ée]ctrico\s*\(?a\)?\s*[:\-]?\s*\$?\s*([0-9][0-9\.,]*)",
                ],
            )
            datos["contribucion_bomberos"] = self._extract_float_from_patterns(
                texto_completo,
                [
                    r"(?:contribuci[óo]n\s+(?:al\s+)?cuerpo\s+de\s+bomberos|contribuci[óo]n\s+bomberos)\s*[:\-]?\s*\$?\s*([0-9][0-9\.,]*)",
                ],
            )

            # Valor Consumo $ (energía activa)
            datos["valor_consumo"] = self._extract_float_from_patterns(
                texto_completo,
                [
                    r"valor\s+consumo\s*[:\-]?\s*\$?\s*([0-9][0-9\.,]*)",
                ],
            )

            # Subsidio Tarifa Eléctrica
            datos["subsidio_tarifa"] = self._extract_float_from_patterns(
                texto_completo,
                [
                    r"subsidio\s+tarifa\s+el[ée]ctrica\s*[:\-]?\s*\$?\s*([0-9][0-9\.,]*)-?",
                ],
            )
            # Guardar como negativo si aplica
            if datos["subsidio_tarifa"] is not None:
                match_neg = re.search(
                    r"subsidio\s+tarifa\s+el[ée]ctrica\s*[:\-]?\s*\$?\s*[0-9][0-9\.,]*\s*-",
                    texto_completo, re.IGNORECASE
                )
                if match_neg:
                    datos["subsidio_tarifa"] = -abs(datos["subsidio_tarifa"])

            # Comercialización
            datos["comercializacion"] = self._extract_float_from_patterns(
                texto_completo,
                [
                    r"comercializaci[óo]n\s*[:\-]?\s*\$?\s*([0-9][0-9\.,]*)",
                ],
            )

            # Servicio Alumbrado Público
            datos["alumbrado_publico"] = self._extract_float_from_patterns(
                texto_completo,
                [
                    r"servicio\s+alumbrado\s+p[úu]blico\s+general\s*[:\-]?\s*\$?\s*([0-9][0-9\.,]*)",
                    r"alumbrado\s+p[úu]blico\s+general\s*[:\-]?\s*\$?\s*([0-9][0-9\.,]*)",
                ],
            )

            # Valor forma de pago (sector eléctrico)
            datos["valor_forma_pago"] = self._extract_float_from_patterns(
                texto_completo,
                [
                    r"otros\s+con\s+utilizaci[óo]n\s+del\s+sistema\s+financiero\s*[:\-]?\s*\$?\s*([0-9][0-9\.,]*)",
                    r"forma\s+de\s+pago\s*[:\-]?\s*\$?\s*([0-9][0-9\.,]*)",
                ],
            )
            if datos["valor_forma_pago"] is None:
                datos["valor_forma_pago"] = datos.get("total_sec_elec")

            datos["valor_total"] = self._extract_float_from_patterns(
                texto_completo,
                [
                    r"valor\s+total\s*(?:\(usd\))?\s*[:\-]?\s*\$?\s*([0-9][0-9\.,]*)",
                    r"\btotal\s+a\s+pagar\b\s*[:\-]?\s*\$?\s*([0-9][0-9\.,]*)",
                ],
            )
            
            datos["extraction_success"] = True
            datos["texto_completo"] = texto_completo[:500]
            
            print(f"✅ [CAT2 EXTRACTOR] Extracción exitosa")
            return datos
        
        except Exception as exc:
            print(f"❌ [CAT2 EXTRACTOR] Error: {exc}")
            return self.create_error_response(str(exc))