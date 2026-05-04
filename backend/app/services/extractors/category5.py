"""
Extractor para Categoría 5: Plataformas Virtuales.

Extrae datos de documentos con bloques repetidos por período.
"""

from typing import Dict, Any, List, Optional
import io
import re

import pdfplumber

from app.services.schemas import Category5Schema
from app.services.extractors.base import BaseCategoryExtractor


class Category5Extractor(BaseCategoryExtractor):
    """Extractor especializado para plataformas virtuales."""

    def __init__(self):
        super().__init__(Category5Schema())

    @staticmethod
    def _normalizar_numero(valor: str) -> Optional[float]:
        """Convierte un texto numérico a float tolerando comas y puntos."""
        if not valor:
            return None

        valor = valor.strip().replace(" ", "")
        if not valor:
            return None

        if "," in valor and "." in valor:
            if valor.rfind(",") > valor.rfind("."):
                valor = valor.replace(".", "").replace(",", ".")
            else:
                valor = valor.replace(",", "")
        else:
            valor = valor.replace(",", ".")

        try:
            return float(valor)
        except ValueError:
            return None

    @staticmethod
    def _limpiar_texto(valor: str) -> str:
        return re.sub(r"\s+", " ", valor or "").strip(" :-|\t")

    @staticmethod
    def _limpiar_celda(valor: object) -> str:
        return re.sub(r"\s+", " ", str(valor or "")).strip()

    @staticmethod
    def _es_numero(valor: str) -> bool:
        return bool(re.fullmatch(r"[\d\.,]+", valor or ""))

    def _deduplicar_periodos(self, periodos: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        deduplicados: List[Dict[str, Any]] = []
        vistos = set()

        for periodo in periodos:
            clave = (
                self._limpiar_texto(str(periodo.get("periodo") or "")).lower(),
                self._limpiar_texto(str(periodo.get("tipo") or "")).lower(),
                periodo.get("total_min_eva"),
                periodo.get("total_min_zoom"),
            )
            if clave in vistos:
                continue
            vistos.add(clave)
            deduplicados.append(periodo)

        return deduplicados

    # ──────────────────────────────────────────────────────────────────────
    # Extracción desde tablas (fallback cuando pdfplumber detecta celdas)
    # ──────────────────────────────────────────────────────────────────────

    def _extraer_tipo_desde_tabla(self, tabla_index: int, fila: List[str]) -> Optional[str]:
        for celda in fila:
            texto = self._limpiar_celda(celda).upper()
            if texto in {"DOCENTES", "DOCENTE"}:
                return "Docentes"
            if texto in {"ESTUDIANTES", "ESTUDIANTE"}:
                return "Estudiantes"

        if tabla_index == 0:
            return "Docentes"
        if tabla_index == 1:
            return "Estudiantes"
        return None

    @staticmethod
    def _mapear_indices_metricas(encabezado: List[str]) -> Dict[str, Optional[int]]:
        indices: Dict[str, Optional[int]] = {
            "eva": None,
            "zoom": None,
            "participantes": None,
        }

        for index, celda in enumerate(encabezado):
            texto = celda.upper()
            if indices["eva"] is None and "EVA" in texto:
                indices["eva"] = index
            if indices["zoom"] is None and "ZOOM" in texto:
                indices["zoom"] = index
            if indices["participantes"] is None and "PARTICIP" in texto:
                indices["participantes"] = index

        return indices

    def _parsear_tablas_periodos(self, tablas: List[List[List[object]]]) -> List[Dict[str, Any]]:
        registros: List[Dict[str, Any]] = []

        for tabla_index, tabla in enumerate(tablas):
            if not tabla:
                continue

            encabezado = [self._limpiar_celda(celda) for celda in tabla[0]]
            tipo_tabla = self._extraer_tipo_desde_tabla(tabla_index, encabezado)
            indices_metricas = self._mapear_indices_metricas(encabezado)
            periodos_vistos_en_tabla = set()

            for fila_index, fila in enumerate(tabla):
                fila_limpia = [self._limpiar_celda(celda) for celda in fila]
                fila_no_vacia = [celda for celda in fila_limpia if celda]
                if not fila_no_vacia:
                    continue

                if fila_index == 0 and any("PERIODO" in celda.upper() for celda in fila_no_vacia):
                    continue

                fila_texto = " | ".join(fila_limpia)
                fila_texto_mayus = fila_texto.upper()
                if "TOTAL GENERAL" in fila_texto_mayus:
                    continue

                if any(celda.upper() in {"DOCENTES", "DOCENTE"} for celda in fila_no_vacia):
                    tipo_tabla = "Docentes"
                    continue
                if any(celda.upper() in {"ESTUDIANTES", "ESTUDIANTE"} for celda in fila_no_vacia):
                    tipo_tabla = "Estudiantes"
                    continue

                periodo = None
                for celda in fila_limpia:
                    if not celda:
                        continue
                    if re.search(r"\b\d{4}\b", celda) and ("/" in celda or "-" in celda):
                        periodo = celda
                        break

                if not periodo:
                    continue

                if periodo in periodos_vistos_en_tabla:
                    continue

                valores: Dict[str, Optional[float]] = {
                    "total_min_eva": None,
                    "total_min_zoom": None,
                    "total_participantes_zoom": None,
                }

                if indices_metricas["eva"] is not None and indices_metricas["eva"] < len(fila_limpia):
                    valor_eva = fila_limpia[indices_metricas["eva"]]
                    if self._es_numero(valor_eva):
                        valores["total_min_eva"] = self._normalizar_numero(valor_eva)

                if indices_metricas["zoom"] is not None and indices_metricas["zoom"] < len(fila_limpia):
                    valor_zoom = fila_limpia[indices_metricas["zoom"]]
                    if self._es_numero(valor_zoom):
                        valores["total_min_zoom"] = self._normalizar_numero(valor_zoom)

                if indices_metricas["participantes"] is not None and indices_metricas["participantes"] < len(fila_limpia):
                    valor_participantes = fila_limpia[indices_metricas["participantes"]]
                    if self._es_numero(valor_participantes):
                        valores["total_participantes_zoom"] = self._normalizar_numero(valor_participantes)

                if valores["total_min_eva"] is None and valores["total_min_zoom"] is None and valores["total_participantes_zoom"] is None:
                    continue

                if valores["total_min_eva"] is None or (indices_metricas["eva"] is None and len(fila_limpia) > 1 and self._es_numero(fila_limpia[1])):
                    numeros = [celda for celda in fila_limpia[1:] if self._es_numero(celda)]
                    if numeros:
                        if valores["total_min_eva"] is None:
                            valores["total_min_eva"] = self._normalizar_numero(numeros[0])
                        if valores["total_min_zoom"] is None and len(numeros) > 1:
                            valores["total_min_zoom"] = self._normalizar_numero(numeros[1])
                        if valores["total_participantes_zoom"] is None and len(numeros) > 2:
                            valores["total_participantes_zoom"] = self._normalizar_numero(numeros[2])

                periodo_registro: Dict[str, Any] = {
                    "periodo": periodo,
                    "tipo": tipo_tabla,
                    "total_min_eva": valores["total_min_eva"],
                    "total_min_zoom": valores["total_min_zoom"],
                }

                if valores["total_participantes_zoom"] is not None:
                    periodo_registro["total_participantes_zoom"] = valores["total_participantes_zoom"]

                registros.append(periodo_registro)
                periodos_vistos_en_tabla.add(periodo)

        return self._deduplicar_periodos(registros)

    def _extraer_registros_desde_pdf(self, file_content: bytes) -> List[Dict[str, Any]]:
        tablas: List[List[List[object]]] = []

        try:
            with pdfplumber.open(io.BytesIO(file_content)) as pdf:
                for page in pdf.pages:
                    page_tables = page.extract_tables()
                    if page_tables:
                        tablas.extend(page_tables)
        except Exception as exc:
            print(f"⚠️ [CAT5 EXTRACTOR] Error leyendo tablas del PDF: {exc}")

        if tablas:
            registros = self._parsear_tablas_periodos(tablas)
            if registros:
                return registros

        return []

    # ──────────────────────────────────────────────────────────────────────
    # Parser principal basado en texto plano (cubre el formato EVA/ZOOM)
    # ──────────────────────────────────────────────────────────────────────

    def _extraer_registros_periodos(self, texto: str) -> List[Dict[str, Any]]:
        """
        Parser robusto para el formato real del reporte EVA/ZOOM.

        El texto plano contiene dos bloques con esta estructura:

            Periodos  Total tiempo conexión minutos EVA  [Total tiempo conexión minutos ZOOM]  Total participantes ZOOM
            ABR/2024 - AGO/2024   <nums>
            DOCENTES/ESTUDIANTES  <nums>
            ...
            Total general  <nums>

        El primer bloque (docentes) incluye columna ZOOM; el segundo
        (estudiantes) solo tiene EVA y participantes.

        Regla clave para distinguir años de valores reales:
            - Los años (2024, 2025, 2026) tienen 4 dígitos → se ignoran.
            - Los valores de minutos/participantes tienen ≥ 5 dígitos.
        """
        PATRON_PERIODO   = re.compile(r'([A-Z]{3}/\d{4}\s*-\s*[A-Z]{3}/\d{4})', re.IGNORECASE)
        PATRON_NUMS      = re.compile(r'\b(\d{5,})\b')   # ≥ 5 dígitos → descarta años
        PATRON_TIPO      = re.compile(r'\b(DOCENTES?|ESTUDIANTES?)\b', re.IGNORECASE)
        PATRON_HEADER    = re.compile(r'Periodos\s+Total\s+tiempo', re.IGNORECASE)
        PATRON_TOTAL_GEN = re.compile(r'^\s*Total\s+general\b', re.IGNORECASE)

        columnas_zoom  = False   # ¿la sección activa tiene columna minutos ZOOM?
        periodo_actual: Optional[str] = None
        registros: List[Dict[str, Any]] = []

        for linea in texto.splitlines():
            linea = linea.strip()
            if not linea:
                continue

            # ── Header de bloque: determina las columnas disponibles ─────
            if PATRON_HEADER.search(linea):
                columnas_zoom = 'minutos ZOOM' in linea
                continue

            # ── Saltar fila de totales generales ────────────────────────
            if PATRON_TOTAL_GEN.search(linea):
                continue

            # ── Fila de período: actualiza el período activo ─────────────
            m_periodo = PATRON_PERIODO.search(linea)
            if m_periodo:
                periodo_actual = m_periodo.group(1).strip()
                continue   # los valores reales vienen en la fila DOCENTES/ESTUDIANTES

            # ── Fila de datos: DOCENTES o ESTUDIANTES con valores ────────
            m_tipo = PATRON_TIPO.search(linea)
            if m_tipo and periodo_actual:
                tipo = m_tipo.group(1).title()
                nums = PATRON_NUMS.findall(linea)

                registro: Dict[str, Any] = {
                    "periodo": periodo_actual,
                    "tipo": tipo,
                    "total_min_eva": int(nums[0]) if len(nums) > 0 else None,
                }

                if columnas_zoom:
                    # Sección DOCENTES: EVA | ZOOM | participantes
                    registro["total_min_zoom"]           = int(nums[1]) if len(nums) > 1 else None
                    registro["total_participantes_zoom"] = int(nums[2]) if len(nums) > 2 else None
                else:
                    # Sección ESTUDIANTES: EVA | participantes (sin columna ZOOM)
                    registro["total_min_zoom"]           = None
                    registro["total_participantes_zoom"] = int(nums[1]) if len(nums) > 1 else None

                registros.append(registro)

        return self._deduplicar_periodos(registros)

    # ──────────────────────────────────────────────────────────────────────
    # Punto de entrada principal
    # ──────────────────────────────────────────────────────────────────────

    def extract(self, file_content: bytes, filename: str) -> Dict[str, Any]:
        """
        Extrae datos de documento sobre uso de plataformas virtuales.

        Los documentos pueden contener varios bloques por período, así que
        se devuelven en una lista bajo el campo ``periodos``.
        """
        try:
            print(f"📖 [CAT5 EXTRACTOR] Leyendo PDF: {filename}")
            texto_completo = self.extract_pdf_text(file_content)
            print(f"📖 [CAT5 EXTRACTOR] Texto extraído: {len(texto_completo)} caracteres")

            datos = self.initialize_data_dict()
            datos["filename"] = filename

            # Tipo de servicio
            datos["tipo_servicio"] = "Plataforma Virtual"

            # Número de factura
            factura_patterns = [
                r"factura[:\s#]*([A-Z0-9\-]+)",
                r"nro\.?\s*([0-9\-]+)",
                r"n[úu]mero[:\s]*([A-Z0-9\-]+)",
                r"invoice[:\s#]*([A-Z0-9\-]+)",
                r"referencia[:\s#]*([A-Z0-9\-]+)",
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
            ]
            datos["total_usd"] = self.extract_first_match(total_patterns, texto_completo)

            # ════════════════════════════════════════════════════════════
            # Campos específicos de Categoría 5
            # ════════════════════════════════════════════════════════════

            # Intentar primero con tablas reales (otros formatos de PDF),
            # y si no encuentra nada usar el parser de texto plano.
            periodos = self._extraer_registros_desde_pdf(file_content)
            if not periodos:
                periodos = self._extraer_registros_periodos(texto_completo)
            if periodos:
                datos["periodos"] = periodos

            # Compatibilidad con documentos antiguos que solo exponen bimestres.
            bimestre1_patterns = [
                r"(?:primer\s+)?bimestre\s*1?\s*[:\s]*(\d+[\.,]?\d*)\s*horas?",
                r"bimestre\s+1[:\s]*(\d+[\.,]?\d*)\s*horas?",
                r"primer\s+bimestre[:\s]*(\d+[\.,]?\d*)\s*horas?",
            ]
            bim1 = self.extract_first_match(bimestre1_patterns, texto_completo)
            if bim1 is not None:
                datos["horas_trabajadas_bimestre1"] = bim1

            bimestre2_patterns = [
                r"(?:segundo\s+)?bimestre\s*2?\s*[:\s]*(\d+[\.,]?\d*)\s*horas?",
                r"bimestre\s+2[:\s]*(\d+[\.,]?\d*)\s*horas?",
                r"segundo\s+bimestre[:\s]*(\d+[\.,]?\d*)\s*horas?",
            ]
            bim2 = self.extract_first_match(bimestre2_patterns, texto_completo)
            if bim2 is not None:
                datos["horas_trabajadas_bimestre2"] = bim2

            if not periodos and bim1 is None and bim2 is None:
                print("⚠️ [CAT5 EXTRACTOR] No se detectaron bloques de períodos ni bimestres")

            datos["extraction_success"] = True
            datos["texto_completo"] = texto_completo[:500]

            print(f"✅ [CAT5 EXTRACTOR] Extracción exitosa")
            return datos

        except Exception as exc:
            print(f"❌ [CAT5 EXTRACTOR] Error: {exc}")
            return self.create_error_response(str(exc))