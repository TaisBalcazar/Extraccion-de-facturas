"""
Esquemas y definiciones de campos por categoría.

Fuente única de verdad para los campos que cada categoría debe extraer.
"""

from dataclasses import dataclass
from typing import Optional, List, Dict, Any


@dataclass
class FieldDefinition:
    """Define un campo extraíble de una factura."""
    name: str
    label: str
    type: str  # "numeric", "string", "date", "calculated"
    unit: Optional[str] = None
    patterns: Optional[List[str]] = None  # regex patterns para búsqueda
    description: str = ""


class CategorySchema:
    """Define la estructura de una categoría de facturas."""
    
    category_id: str
    category_name: str
    common_fields: List[FieldDefinition]  # campos comunes a todas las categorías
    specific_fields: List[FieldDefinition]  # campos específicos de la categoría
    
    @property
    def all_fields(self) -> List[FieldDefinition]:
        """Retorna todos los campos (comunes + específicos)."""
        return self.common_fields + self.specific_fields
    
    def get_field_names(self) -> List[str]:
        """Retorna nombres de todos los campos."""
        return [f.name for f in self.all_fields]


# ══════════════════════════════════════════════════════════════
# Campos comunes a todas las categorías
# ══════════════════════════════════════════════════════════════

COMMON_FIELDS = [
    FieldDefinition(
        name="filename",
        label="Nombre de archivo",
        type="string",
        description="Nombre original del archivo subido"
    ),
    FieldDefinition(
        name="fecha_emision",
        label="Fecha de emisión",
        type="date",
        patterns=[
            r"(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})",
            r"(\d{4}[-/]\d{1,2}[-/]\d{1,2})",
            r"fecha[:\s]*(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})",
        ],
        description="Fecha en que se emitió el documento"
    ),
    FieldDefinition(
        name="periodo_inicio",
        label="Período inicio",
        type="date",
        description="Fecha de inicio del período de consumo"
    ),
    FieldDefinition(
        name="periodo_fin",
        label="Período fin",
        type="date",
        description="Fecha de fin del período de consumo"
    ),
    FieldDefinition(
        name="total_usd",
        label="Total USD",
        type="numeric",
        unit="USD",
        patterns=[
            r"total\s+a\s+pagar[:\s]*\$?\s*(\d+[\.,]\d{2})",
            r"total[:\s]*\$?\s*(\d+[\.,]\d{2})",
            r"\$\s*(\d+[\.,]\d{2})\s*usd",
        ],
        description="Monto total a pagar en USD"
    ),
    FieldDefinition(
        name="factura_numero",
        label="Número de factura",
        type="string",
        patterns=[
            r"factura[:\s#]*([A-Z0-9\-]+)",
            r"nro\.?\s*([0-9\-]+)",
            r"invoice[:\s#]*([A-Z0-9\-]+)",
        ],
        description="Número o referencia de la factura"
    ),
]


# ══════════════════════════════════════════════════════════════
# CATEGORÍA 1: Gasolina/Combustible
# ══════════════════════════════════════════════════════════════

class Category1Schema(CategorySchema):
    """Categoría 1: Gasolina, Diesel, Combustibles y Refrigeración."""
    
    category_id = "cat-1"
    category_name = "Categoría 1 - Gasolina/Combustible"
    
    common_fields = COMMON_FIELDS
    
    specific_fields = [
        FieldDefinition(
            name="precio_unitario",
            label="Precio unitario",
            type="numeric",
            unit="USD",
            patterns=[
                r"\b(?:p\s*/\s*u|p\.?u\.?)\b\s*[:\-]?\s*\$?\s*([0-9][0-9\.,]*)",
                r"precio\s+unitario\s*[:\-]?\s*\$?\s*([0-9][0-9\.,]*)",
            ],
            description="Precio unitario en dólares"
        ),
        FieldDefinition(
            name="cantidad",
            label="Cantidad",
            type="numeric",
            unit="Galones",
            patterns=[
                r"\bcant(?:idad)?\b\s*[:\-]?\s*([0-9][0-9\.,]*)",
            ],
            description="Cantidad en galones"
        ),
        FieldDefinition(
            name="total",
            label="Total",
            type="numeric",
            unit="USD",
            patterns=[
                r"valor\s+total\s*(?:\(usd\))?\s*[:\-]?\s*\$?\s*([0-9][0-9\.,]*)",
                r"\btotal\b\s*[:\-]?\s*\$?\s*([0-9][0-9\.,]*)",
            ],
            description="Valor total en dólares"
        ),
    ]


# ══════════════════════════════════════════════════════════════
# CATEGORÍA 2: Electricidad
# ══════════════════════════════════════════════════════════════

class Category2Schema(CategorySchema):
    """Categoría 2: Consumo eléctrico."""
    
    category_id = "cat-2"
    category_name = "Categoría 2 - Electricidad"
    
    common_fields = COMMON_FIELDS
    
    specific_fields = [
        FieldDefinition(
            name="cod_unico",
            label="Código único eléctrico",
            type="string",
            patterns=[
                r"c[óo]digo\s+[úu]nico\s+el[ée]ctrico\s*[:\-]?\s*([A-Z0-9\-]+)",
            ],
            description="Código único eléctrico"
        ),
        FieldDefinition(
            name="nro_factura",
            label="Nro factura",
            type="string",
            patterns=[
                r"nro\.?\s*factura\s*[:\-]?\s*([0-9\-]+)",
                r"n[°ºo]\.?\s*factura\s*[:\-]?\s*([0-9\-]+)",
            ],
            description="Número de factura con solo dígitos"
        ),
        FieldDefinition(
            name="medidor",
            label="Número de medidor",
            type="string",
            patterns=[
                r"medidor[:\s#]*([A-Z0-9\-]+)",
                r"n[úu]mero\s+de\s+medidor[:\s]*([A-Z0-9\-]+)",
                r"contador[:\s#]*([A-Z0-9\-]+)",
            ],
            description="Número de medidor/contador"
        ),
        FieldDefinition(
            name="consumo_total",
            label="Consumo total",
            type="numeric",
            unit="kWh",
            patterns=[
                r"consumo\s+total\s*[:\-]?\s*([0-9][0-9\.,]*)\s*kwh",
                r"consumo\s+total\s*[:\-]?\s*([0-9][0-9\.,]*)",
            ],
            description="Consumo total de energía en kWh"
        ),
        FieldDefinition(
            name="consumo_kwh",
            label="Consumo eléctrico",
            type="numeric",
            unit="kWh",
            patterns=[
                r"consumo[:\s]*\(kwh\)[:\s]*(\d+[\.,]?\d*)",
                r"(\d+[\.,]?\d*)\s*kwh",
                r"consumo[:\s]*(\d+[\.,]?\d*)\s*kW",
            ],
            description="Consumo de energía eléctrica en kWh"
        ),
        FieldDefinition(
            name="lectura_anterior",
            label="Lectura anterior",
            type="numeric",
            unit="kWh",
            patterns=[
                r"lectura\s+anterior[:\s]*(\d+[\.,]?\d*)",
            ],
            description="Lectura anterior del medidor"
        ),
        FieldDefinition(
            name="lectura_actual",
            label="Lectura actual",
            type="numeric",
            unit="kWh",
            patterns=[
                r"lectura\s+actual[:\s]*(\d+[\.,]?\d*)",
            ],
            description="Lectura actual del medidor"
        ),
        FieldDefinition(
            name="diferencia_consumo",
            label="Diferencia consumo",
            type="numeric",
            unit="kWh",
            patterns=[
                r"diferencia[:\s]*(\d+[\.,]?\d*)",
            ],
            description="Diferencia entre lectura actual y anterior"
        ),
        FieldDefinition(
            name="total_sec_elec",
            label="Total sector eléctrico",
            type="numeric",
            unit="USD",
            patterns=[
                r"total\s+sector\s+el[ée]ctrico\s*\(?a\)?\s*[:\-]?\s*\$?\s*([0-9][0-9\.,]*)",
            ],
            description="Total del sector eléctrico (A)"
        ),
        FieldDefinition(
            name="valor_total",
            label="Valor total",
            type="numeric",
            unit="USD",
            patterns=[
                r"valor\s+total\s*(?:\(usd\))?\s*[:\-]?\s*\$?\s*([0-9][0-9\.,]*)",
            ],
            description="Valor total en USD"
        ),
        FieldDefinition(
            name="subtotal",
            label="Subtotal",
            type="numeric",
            unit="USD",
            patterns=[
                r"subtotal[:\s]+\$?\s*(\d+[\s,\.]?\d{0,3}[,\.]?\d{0,2})",
            ],
            description="Subtotal del servicio"
        ),
        FieldDefinition(
            name="iva",
            label="IVA",
            type="numeric",
            unit="USD",
            patterns=[
                r"i\.?v\.?a\.?\s+(?:0%|12%|15%)[:\s]+\$?\s*(\d+[\s,\.]?\d{0,3}[,\.]?\d{0,2})",
            ],
            description="Impuesto al valor agregado"
        ),
        FieldDefinition(
            name="descuento",
            label="Descuento",
            type="numeric",
            unit="USD",
            patterns=[
                r"descuento[:\s]+\$?\s*(\d+[\s,\.]?\d{0,3}[,\.]?\d{0,2})",
            ],
            description="Descuento aplicado"
        ),
        FieldDefinition(
            name="razon_social",
            label="Razón social",
            type="string",
            description="Razón social del cliente"
        ),
        FieldDefinition(
            name="tipo_tarifa",
            label="Tipo de tarifa",
            type="string",
            description="Tipo de tarifa ARCONEL"
        ),
        FieldDefinition(
            name="direccion_servicio",
            label="Dirección del servicio",
            type="string",
            description="Ubicación del servicio de electricidad"
        ),
        FieldDefinition(
            name="dias_facturados",
            label="Días facturados",
            type="numeric",
            unit="días",
            description="Número de días del período facturado"
        ),
        FieldDefinition(
            name="anio",
            label="Año",
            type="numeric",
            description="Año derivado del período de facturación"
        ),
        FieldDefinition(
            name="mes_numero",
            label="Mes número",
            type="numeric",
            description="Número del mes (1-12)"
        ),
        FieldDefinition(
            name="mes_nombre",
            label="Mes nombre",
            type="string",
            description="Nombre del mes en español"
        ),
        FieldDefinition(
            name="valor_consumo",
            label="Valor consumo",
            type="numeric",
            unit="USD",
            description="Valor monetario del consumo de energía"
        ),
        FieldDefinition(
            name="subsidio_tarifa",
            label="Subsidio tarifa eléctrica",
            type="numeric",
            unit="USD",
            description="Monto de subsidio de tarifa eléctrica (negativo si aplica descuento)"
        ),
        FieldDefinition(
            name="comercializacion",
            label="Comercialización",
            type="numeric",
            unit="USD",
            description="Cargo por comercialización"
        ),
        FieldDefinition(
            name="alumbrado_publico",
            label="Alumbrado público",
            type="numeric",
            unit="USD",
            description="Cargo por servicio de alumbrado público"
        ),
        FieldDefinition(
            name="valor_forma_pago",
            label="Valor forma de pago",
            type="numeric",
            unit="USD",
            description="Costo por forma de pago o utilización del sistema financiero"
        ),
        FieldDefinition(
            name="consumo_subtotal",
            label="Consumo subtotal",
            type="numeric",
            unit="kWh",
            description="Subtotal del consumo sin transformador"
        ),
        FieldDefinition(
            name="consumo_interno_transformador",
            label="Consumo interno transformador",
            type="numeric",
            unit="kWh",
            description="Consumo interno del transformador"
        ),
    ]


# ══════════════════════════════════════════════════════════════
# CATEGORÍA 3: Vuelos (Nota: origen Excel, fase 2)
# ══════════════════════════════════════════════════════════════

class Category3Schema(CategorySchema):
    """Categoría 3: Vuelos (nacional e internacional)."""
    
    category_id = "cat-3"
    category_name = "Categoría 3 - Vuelos"
    
    common_fields = COMMON_FIELDS
    
    specific_fields = [
        FieldDefinition(
            name="vuelos_domesticos_pasajeros",
            label="Vuelos domésticos - Número de pasajeros",
            type="numeric",
            unit="tickets",
            description="Número de tickets/pasajeros en vuelos domésticos nacionales"
        ),
        FieldDefinition(
            name="vuelos_domesticos_distancia",
            label="Vuelos domésticos - Distancia",
            type="numeric",
            unit="km",
            description="Distancia total en km de vuelos domésticos"
        ),
        FieldDefinition(
            name="vuelos_internacionales_pasajeros",
            label="Vuelos internacionales - Número de pasajeros",
            type="numeric",
            unit="tickets",
            description="Número de tickets/pasajeros en vuelos internacionales"
        ),
        FieldDefinition(
            name="vuelos_internacionales_distancia",
            label="Vuelos internacionales - Distancia",
            type="numeric",
            unit="km",
            description="Distancia total en km de vuelos internacionales"
        ),
        FieldDefinition(
            name="perdidas_energia_cat2",
            label="Pérdidas de energía reportada en CAT 2",
            type="calculated",
            unit="MWh",
            description="Calculado con: (Consumo total MWh * 3,28%) / (1 - 3,28%)"
        ),
    ]


# ══════════════════════════════════════════════════════════════
# CATEGORÍA 4: Residuos y Agua
# ══════════════════════════════════════════════════════════════

class Category4Schema(CategorySchema):
    """Categoría 4: Residuos, papel, limpieza y agua."""
    
    category_id = "cat-4"
    category_name = "Categoría 4 - Residuos/Agua"
    
    common_fields = COMMON_FIELDS
    
    specific_fields = [
        FieldDefinition(
            name="papel_bano",
            label="Papel de baño",
            type="numeric",
            unit="USD",
            patterns=[
                r"papel\s+de\s+ba[ñn]o\s*[:\s]*\$?\s*(\d+[\.,]?\d*)",
                r"ba[ñn]o.*\$?\s*(\d+[\.,]?\d*)",
            ],
            description="Gasto en papel de baño"
        ),
        FieldDefinition(
            name="papel_bond",
            label="Papel bond",
            type="numeric",
            unit="USD",
            patterns=[
                r"papel\s+bond\s*[:\s]*\$?\s*(\d+[\.,]?\d*)",
                r"bond.*\$?\s*(\d+[\.,]?\d*)",
            ],
            description="Gasto en papel bond"
        ),
        FieldDefinition(
            name="materiales_oficina",
            label="Materiales varios de oficina",
            type="numeric",
            unit="USD",
            patterns=[
                r"materiales\s+(?:varios\s+)?de\s+oficina\s*[:\s]*\$?\s*(\d+[\.,]?\d*)",
                r"materiales\s+oficina\s*[:\s]*\$?\s*(\d+[\.,]?\d*)",
            ],
            description="Gasto en materiales diversos de oficina"
        ),
        FieldDefinition(
            name="productos_limpieza",
            label="Productos de limpieza",
            type="numeric",
            unit="USD",
            patterns=[
                r"productos\s+de\s+limpieza\s*[:\s]*\$?\s*(\d+[\.,]?\d*)",
                r"limpieza\s*[:\s]*\$?\s*(\d+[\.,]?\d*)",
            ],
            description="Gasto en productos de limpieza"
        ),
        FieldDefinition(
            name="vasos_plasticos",
            label="Vasos plásticos",
            type="numeric",
            unit="USD",
            patterns=[
                r"vasos?\s+pl[áa]sticos?\s*[:\s]*\$?\s*(\d+[\.,]?\d*)",
                r"pl[áa]sticos?\s*[:\s]*\$?\s*(\d+[\.,]?\d*)",
            ],
            description="Gasto en vasos plásticos"
        ),
        FieldDefinition(
            name="consumo_agua",
            label="Consumo de agua",
            type="numeric",
            unit="m³",
            patterns=[
                r"consumo\s+(?:de\s+)?agua\s*[:\s]*(\d+[\.,]?\d*)\s*m3",
                r"consumo\s+agua\s*[:\s]*(\d+[\.,]?\d*)",
            ],
            description="Consumo de agua en metros cúbicos"
        ),
        FieldDefinition(
            name="residuos_organicos",
            label="Residuos orgánicos relleno sanitario",
            type="numeric",
            unit="kg",
            patterns=[
                r"residuos?\s+org[áa]nicos?.*relleno\s*[:\s]*(\d+[\.,]?\d*)",
            ],
            description="Kilogramos de residuos orgánicos al relleno"
        ),
        FieldDefinition(
            name="aguas_residuales",
            label="Aguas residuales descargadas",
            type="numeric",
            unit="m³",
            patterns=[
                r"aguas?\s+residuales?.*inodoros?\s*[:\s]*(\d+[\.,]?\d*)",
            ],
            description="Volumen de aguas residuales descargadas"
        ),
    ]


# ══════════════════════════════════════════════════════════════
# CATEGORÍA 5: Plataformas Virtuales
# ══════════════════════════════════════════════════════════════

class Category5Schema(CategorySchema):
    """Categoría 5: Uso de plataformas virtuales."""
    
    category_id = "cat-5"
    category_name = "Categoría 5 - Plataforma Virtual"
    
    common_fields = COMMON_FIELDS
    
    specific_fields = [
        FieldDefinition(
            name="periodos",
            label="Períodos",
            type="list",
            description=(
                "Lista de bloques extraídos del documento. Cada elemento incluye "
                "periodo, tipo, total_min_eva y total_min_zoom."
            )
        ),
        FieldDefinition(
            name="horas_trabajadas_bimestre1",
            label="Horas trabajadas bimestre 1",
            type="numeric",
            unit="horas",
            patterns=[
                r"(?:primer\s+)?bimestre[:\s]*(\d+[\.,]?\d*)\s*horas?",
                r"bimestre\s+1[:\s]*(\d+[\.,]?\d*)\s*horas?",
            ],
            description="Horas trabajadas en plataforma virtual en primer bimestre (compatibilidad histórica)"
        ),
        FieldDefinition(
            name="horas_trabajadas_bimestre2",
            label="Horas trabajadas bimestre 2",
            type="numeric",
            unit="horas",
            patterns=[
                r"(?:segundo\s+)?bimestre[:\s]*(\d+[\.,]?\d*)\s*horas?",
                r"bimestre\s+2[:\s]*(\d+[\.,]?\d*)\s*horas?",
            ],
            description="Horas trabajadas en plataforma virtual en segundo bimestre (compatibilidad histórica)"
        ),
    ]


# ══════════════════════════════════════════════════════════════
# Mapeo de categorías
# ══════════════════════════════════════════════════════════════

CATEGORY_SCHEMAS: Dict[str, CategorySchema] = {
    "cat-1": Category1Schema(),
    "cat-2": Category2Schema(),
    "cat-3": Category3Schema(),
    "cat-4": Category4Schema(),
    "cat-5": Category5Schema(),
}


def get_schema(category_id: str) -> Optional[CategorySchema]:
    """Obtiene el esquema para una categoría."""
    return CATEGORY_SCHEMAS.get(category_id)


def get_all_field_names(category_id: str) -> List[str]:
    """Retorna todos los nombres de campos para una categoría."""
    schema = get_schema(category_id)
    if schema:
        return schema.get_field_names()
    return []
