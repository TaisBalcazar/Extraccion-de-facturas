# Arquitectura del Sistema de Extracción de Facturas

## 📋 Descripción General

El sistema ha sido refactorizado para soportar múltiples categorías de facturas con campos específicos para cada una. Se implementó el patrón **Factory + Strategy** para garantizar escalabilidad, mantenibilidad y seguimiento de buenas prácticas.

## 🏗️ Estructura del Proyecto

```
backend/app/services/
├── factura_extractor.py          # Interfaz principal (delegador)
├── schemas.py                    # Definición de campos por categoría
├── chat_logic.py                 # (existente)
└── extractors/
    ├── __init__.py              # Exporta Factory
    ├── base.py                  # Clase base abstracta
    ├── factory.py               # Factory Pattern
    ├── category1.py             # Extractor: Gasolina/Combustible
    ├── category2.py             # Extractor: Electricidad
    ├── category3.py             # Extractor: Vuelos (stub - fase 2)
    ├── category4.py             # Extractor: Residuos/Agua
    └── category5.py             # Extractor: Plataforma Virtual
```

## 🎯 Categorías Soportadas

### Categoría 1: Gasolina/Combustible
**Campos específicos:**
- `diesel_buses` - Diesel en buses (Galones)
- `gasolina_movil` - Gasolina móvil en vehículos (Galones)
- `gasolina_ecopais` - Gasolina Ecopais (Galones)
- `diesel_generadores` - Diesel en generadores (Galones)
- `refrigerantes_recarga` - Recarga de refrigerantes (kg)
- `extintores_recarga` - Recarga de extintores (kg)
- `ganado_cabezas` - Número promedio de cabezas de ganado

### Categoría 2: Electricidad
**Campos específicos:**
- `medidor` - Número de medidor
- `consumo_kwh` - Consumo eléctrico (kWh)
- `lectura_anterior` - Lectura anterior del medidor
- `lectura_actual` - Lectura actual del medidor
- `diferencia_consumo` - Diferencia de consumo
- `subtotal` - Subtotal
- `iva` - IVA
- `descuento` - Descuento

### Categoría 3: Vuelos
**Estado:** 🔶 En desarrollo (requiere Excel)
**Nota:** Los datos vienen de archivos Excel, no PDF. Será implementado en fase 2.

### Categoría 4: Residuos/Agua
**Campos específicos:**
- `papel_bano` - Gasto en papel de baño ($)
- `papel_bond` - Gasto en papel bond ($)
- `materiales_oficina` - Materiales varios de oficina ($)
- `productos_limpieza` - Productos de limpieza ($)
- `vasos_plasticos` - Vasos plásticos ($)
- `consumo_agua` - Consumo de agua (m³)
- `residuos_organicos` - Residuos orgánicos (kg)
- `aguas_residuales` - Aguas residuales (m³)

### Categoría 5: Plataforma Virtual
**Campos específicos:**
- `periodos` - Lista de bloques del documento
- Cada bloque incluye `periodo`, `tipo`, `total_min_eva` y `total_min_zoom`
- `horas_trabajadas_bimestre1` / `horas_trabajadas_bimestre2` - Compatibilidad con documentos antiguos

## 🔄 Flujo de Extracción

```
Front-end selecciona: Zona → Categoría → Item
                          ↓
API /upload recibe: zona_id, categoria_id, item, files
                          ↓
facturas.py → extraer_datos_factura(file, filename, categoria_id)
                          ↓
factura_extractor.py → ExtractorFactory.get_extractor(categoria_id)
                          ↓
Extractor específico (Cat1, Cat2, etc)
                          ↓
Retorna Dict con campos específicos de la categoría
                          ↓
Guardado en Firestore
```

## 📦 Cómo Usar

### Para Usar Existente (Frontend/API)

```python
from app.services.factura_extractor import extraer_datos_factura

# Con categoría especificada (RECOMENDADO)
datos = extraer_datos_factura(file_content, "factura.pdf", "cat-2")

# Sin categoría (fallback automático a cat-2)
datos = extraer_datos_factura(file_content, "factura.pdf")
```

### Para Desarrolladores: Acceso a Factory

```python
from app.services.extractors import ExtractorFactory

# Obtener extractor específico
extractor = ExtractorFactory.get_extractor("cat-1")

# Usar el extractor
datos = extractor.extract(file_content, filename)

# Ver categorías soportadas
categorias = ExtractorFactory.get_supported_categories()  # ["cat-1", "cat-2", ...]

# Verificar si se soporta una categoría
if ExtractorFactory.is_supported("cat-5"):
    extractor = ExtractorFactory.get_extractor("cat-5")
```

### Para Acceder a Esquemas

```python
from app.services.schemas import get_schema, get_all_field_names

# Obtener esquema de una categoría
schema = get_schema("cat-2")

# Obtener todos los campos de una categoría
campos = get_all_field_names("cat-2")

# Iterar sobre campos del esquema
for field in schema.all_fields:
    print(f"{field.name}: {field.unit}")
```

## 🔧 Agregar Nueva Categoría

### Paso 1: Definir Schema en `schemas.py`

```python
class Category6Schema(CategorySchema):
    """Categoría 6: Nueva categoría."""
    
    category_id = "cat-6"
    category_name = "Categoría 6 - Nueva"
    
    common_fields = COMMON_FIELDS
    
    specific_fields = [
        FieldDefinition(
            name="campo1",
            label="Nombre del campo",
            type="numeric",
            unit="unidad",
            patterns=[r"patron1", r"patron2"],
            description="Descripción"
        ),
        # ... más campos
    ]

# Agregar al mapeo
CATEGORY_SCHEMAS["cat-6"] = Category6Schema()
```

### Paso 2: Crear Extractor en `extractors/category6.py`

```python
from app.services.schemas import Category6Schema
from app.services.extractors.base import BaseCategoryExtractor

class Category6Extractor(BaseCategoryExtractor):
    def __init__(self):
        super().__init__(Category6Schema())
    
    def extract(self, file_content: bytes, filename: str) -> Dict[str, Any]:
        try:
            print(f"📖 [CAT6 EXTRACTOR] Leyendo PDF: {filename}")
            texto = self.extract_pdf_text(file_content)
            
            datos = self.initialize_data_dict()
            datos["filename"] = filename
            
            # ... lógica de extracción específica
            
            datos["extraction_success"] = True
            return datos
        except Exception as exc:
            return self.create_error_response(str(exc))
```

### Paso 3: Registrar en Factory

En `extractors/__init__.py`:

```python
from app.services.extractors.category6 import Category6Extractor

# En el imports, o usar:
ExtractorFactory.register_extractor("cat-6", Category6Extractor)
```

O en `factory.py`, agregar al mapeo:

```python
_EXTRACTORS_MAP: Dict[str, type] = {
    # ...
    "cat-6": Category6Extractor,
}
```

## ✅ Buenas Prácticas

### Métodos Disponibles en BaseCategoryExtractor

```python
# Extracción de PDF
texto = self.extract_pdf_text(file_content)

# Búsqueda de patrones
valor = self.extract_value(r"patron", texto)
string = self.extract_string(r"patron", texto)
valores = self.extract_first_match([patrones], texto)

# Conversión de fechas
fecha_iso = self.extract_date("25/12/2023")

# Inicialización de datos
datos = self.initialize_data_dict()

# Detección de servicio
tipo = self.detect_service_type(texto)

# Búsqueda de todas las fechas
fechas = self.find_dates_in_text(texto)

# Respuesta de error
error_dict = self.create_error_response("Mensaje de error")
```

### Patrones Regex Útiles

```python
# Dinero
r"\$?\s*(\d+[\.,]?\d*)"

# Fechas
r"(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})"

# Números con comas/puntos
r"(\d+[\.,]?\d*)"

# Palabras clave con variaciones
r"(?:palabra1|palabra2|palabra3)"

# Con acentos opcionales
r"programaci[óo]n"
```

## 📊 Campos Comunes a Todas las Categorías

Todos los extractores incluyen estos campos (definidos en `COMMON_FIELDS`):

- `filename` - Nombre del archivo
- `fecha_emision` - Fecha de emisión
- `periodo_inicio` - Inicio del período
- `periodo_fin` - Fin del período
- `total_usd` - Total en USD
- `factura_numero` - Número de factura

## 🧪 Testing

Para probar un extractor específico:

```python
from app.services.extractors import ExtractorFactory

# Cargar archivo
with open("test_factura.pdf", "rb") as f:
    content = f.read()

# Extraer con categoría específica
extractor = ExtractorFactory.get_extractor("cat-1")
datos = extractor.extract(content, "test_factura.pdf")

# Verificar resultados
print(datos)
assert datos["extraction_success"] == True
assert datos["categoria_id"] == "cat-1"
```

## 🚀 Próximas Fases

1. **Fase 2 - Categoría 3 (Vuelos)**: Implementar procesamiento de archivos Excel
2. **Mejoras**: Machine Learning para auto-detección de categoría
3. **Validación**: Reglas de validación específicas por categoría
4. **Auditoría**: Registro detallado de extracciones exitosas y fallidas

## 📞 Soporte

Para agregar campos nuevos a una categoría existente:
1. Editar el `FieldDefinition` en `schemas.py`
2. Agregar la lógica de extracción en el extractor específico
3. Actualizar los patrones regex si es necesario
4. Probar con archivos de ejemplo

Para bugs o mejoras, revisar la lógica en el extractor específico y el esquema asociado.
