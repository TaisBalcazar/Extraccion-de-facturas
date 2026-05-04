# Facturas - Backend API

Backend FastAPI para el sistema de extracción inteligente de datos de facturas con soporte para múltiples categorías y formato de archivos.

## 🎯 Descripción General

API REST desarrollada con FastAPI que permite:
- Carga y procesamiento de archivos PDF (facturas)
- Extracción automática de datos específicos por categoría
- Almacenamiento en Firebase Firestore
- Gestión de catálogos y zonas
- Autenticación por token Firebase

**Categorías soportadas:**
- **Cat-1:** Gasolina y Combustible
- **Cat-2:** Electricidad
- **Cat-3:** Vuelos (en desarrollo)
- **Cat-4:** Residuos y Agua
- **Cat-5:** Plataforma Virtual

## 📋 Requisitos

- Python 3.9+
- Firebase (cuenta y credenciales)
- pip o conda (gestor de paquetes)

## 🚀 Instalación

### 1. Clonar el repositorio

```bash
git clone <tu-repositorio>
cd facturas_produccion_nuevo
```

### 2. Crear entorno virtual

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux/macOS
source .venv/bin/activate
```

### 3. Instalar dependencias

```bash
cd backend
pip install -r requirements.txt
```

### 4. Configurar Firebase

Tienes dos opciones:

**Opción A: Archivo JSON de Service Account**
- Descarga el archivo desde la consola de Firebase
- Colócalo en `backend/firebase-adminsdk.json` (o similar)
- El backend lo detectará automáticamente

**Opción B: Variables de entorno**
- Copia `backend/.env.example` a `backend/.env`
- Completa las variables de Firebase necesarias

### 5. Ejecutar la API

Desde la raíz del proyecto:

```bash
uvicorn backend.app.main:app --reload --port 8001
```

O desde dentro de `backend/`:

```bash
uvicorn app.main:app --reload --port 8001
```

### 6. Verificar que funciona

```bash
curl http://localhost:8001/health
```

Deberías recibir: `{"status": "ok"}`

## 📁 Estructura del Proyecto

```
backend/
├── app/
│   ├── main.py                 # Aplicación FastAPI
│   ├── api/
│   │   └── routes/
│   │       ├── facturas.py     # Endpoints de facturas
│   │       ├── catalogos.py    # Endpoints de catálogos
│   │       └── health.py       # Health check
│   ├── core/
│   │   ├── config.py           # Configuración
│   │   ├── firebase.py         # Cliente Firebase
│   │   └── security.py         # Autenticación
│   └── services/
│       ├── factura_extractor.py     # Interfaz principal
│       ├── pdf_extractor.py         # Procesamiento de PDFs
│       ├── regex_patterns.py        # Patrones compilados
│       ├── schemas.py               # Definición de campos
│       ├── chat_logic.py            # Lógica de chat
│       └── extractors/              # Extractores por categoría
│           ├── base.py              # Clase base abstracta
│           ├── factory.py           # Factory pattern
│           ├── category1.py         # Extractor: Gasolina
│           ├── category2.py         # Extractor: Electricidad
│           ├── category3.py         # Extractor: Vuelos
│           ├── category4.py         # Extractor: Residuos
│           └── category5.py         # Extractor: Plataforma Virtual
├── requirements.txt
├── Dockerfile
└── .env.example

```

## 🔌 Endpoints Principales

### Salud
- `GET /health` - Verificar que el servidor está funcionando

### Facturas
- `POST /api/v1/upload` - Subir y procesar factura
- `GET /api/v1/facturas` - Listar facturas del usuario
- `DELETE /api/v1/facturas/{factura_id}` - Eliminar factura
- `GET /api/v1/stats` - Estadísticas del usuario

### Catálogos
- `GET /api/v1/catalogos` - Listar catálogos
- `POST /api/v1/catalogos/seed` - Inicializar catálogos

### Zonas (CRUD)
- `GET /api/v1/zonas` - Listar zonas
- `POST /api/v1/zonas` - Crear zona
- `PUT /api/v1/zonas/{zona_id}` - Actualizar zona
- `DELETE /api/v1/zonas/{zona_id}` - Eliminar zona
- `POST /api/v1/zonas/{zona_id}/centros` - Agregar centro a zona
- `DELETE /api/v1/zonas/{zona_id}/centros/{centro}` - Eliminar centro

### Categorías (CRUD)
- `GET /api/v1/categorias` - Listar categorías
- `POST /api/v1/categorias` - Crear categoría
- `PUT /api/v1/categorias/{categoria_id}` - Actualizar categoría
- `DELETE /api/v1/categorias/{categoria_id}` - Eliminar categoría
- `POST /api/v1/categorias/{categoria_id}/items` - Agregar item a categoría
- `DELETE /api/v1/categorias/{categoria_id}/items/{item}` - Eliminar item

### Chat
- `POST /api/v1/chat` - Enviar mensaje al chat

## 🏗️ Arquitectura de Extracción

El sistema utiliza el patrón **Factory + Strategy** para garantizar escalabilidad y mantenibilidad.

### Flujo de Procesamiento

```
Cliente selecciona: Zona → Categoría → Item
                         ↓
POST /api/v1/upload recibe: zona_id, categoria_id, item, files
                         ↓
facturas.py → extraer_datos_factura(file, filename, categoria_id)
                         ↓
factura_extractor.py → ExtractorFactory.get_extractor(categoria_id)
                         ↓
Extractor específico (Cat1Extractor, Cat2Extractor, etc)
                         ↓
Extrae datos y retorna Dict con campos específicos
                         ↓
Valida y guarda en Firestore
```

### Uso en Backend

```python
# Importar la función principal
from backend.app.services.factura_extractor import extraer_datos_factura

# Con categoría (RECOMENDADO)
datos = extraer_datos_factura(file_content, "factura.pdf", "cat-2")

# Acceder a Factory directamente
from backend.app.services.extractors import ExtractorFactory

extractor = ExtractorFactory.get_extractor("cat-1")
datos = extractor.extract(file_content, "factura.pdf")

# Ver categorías soportadas
categorias = ExtractorFactory.get_supported_categories()

# Acceder a esquemas
from backend.app.services.schemas import get_schema

schema = get_schema("cat-2")
```

## 📦 Categorías Soportadas

### Categoría 1: Gasolina/Combustible
Extrae datos de facturas de combustible para vehículos.

**Campos:**
- `diesel_buses` - Diesel en buses (Galones)
- `gasolina_movil` - Gasolina móvil (Galones)
- `gasolina_ecopais` - Gasolina Ecopais (Galones)
- `diesel_generadores` - Diesel en generadores (Galones)
- `refrigerantes_recarga` - Recarga de refrigerantes (kg)
- `extintores_recarga` - Recarga de extintores (kg)
- `ganado_cabezas` - Promedio de cabezas de ganado

### Categoría 2: Electricidad
Extrae datos de facturas de consumo eléctrico.

**Campos:**
- `medidor` - Número de medidor
- `consumo_kwh` - Consumo eléctrico (kWh)
- `lectura_anterior` - Lectura anterior
- `lectura_actual` - Lectura actual
- `diferencia_consumo` - Diferencia de consumo
- `subtotal` - Subtotal
- `iva` - IVA
- `descuento` - Descuento

### Categoría 3: Vuelos
**Estado:** 🔶 En desarrollo (fase 2)

Requiere archivos Excel. Será implementado próximamente.

### Categoría 4: Residuos/Agua
Extrae datos de facturas de residuos y consumo de agua.

**Campos:**
- `papel_bano` - Gasto en papel de baño ($)
- `papel_bond` - Gasto en papel bond ($)
- `materiales_oficina` - Materiales de oficina ($)
- `productos_limpieza` - Productos de limpieza ($)
- `vasos_plasticos` - Vasos plásticos ($)
- `consumo_agua` - Consumo de agua (m³)
- `residuos_organicos` - Residuos orgánicos (kg)
- `aguas_residuales` - Aguas residuales (m³)

### Categoría 5: Plataforma Virtual
Extrae datos de reportes de plataformas virtuales.

**Campos:**
- `periodos` - Lista de bloques del documento
- `horas_trabajadas_bimestre1` - Horas bimestre 1
- `horas_trabajadas_bimestre2` - Horas bimestre 2

## 🛠️ Agregar Nueva Categoría

### Paso 1: Definir Schema

Edita `backend/app/services/schemas.py`:

```python
class Category6Schema(CategorySchema):
    """Categoría 6: Nueva categoría."""
    
    category_id = "cat-6"
    category_name = "Nueva Categoría"
    
    common_fields = COMMON_FIELDS
    
    specific_fields = [
        FieldDefinition("campo1", "Descripción", "unidad"),
        FieldDefinition("campo2", "Descripción", "unidad"),
    ]
```

### Paso 2: Crear Extractor

Crea `backend/app/services/extractors/category6.py`:

```python
from .base import BaseExtractor
from ..schemas import Category6Schema

class Category6Extractor(BaseExtractor):
    """Extractor para Categoría 6."""
    
    schema_class = Category6Schema
    
    def extract(self, content: bytes, filename: str = None) -> dict:
        """Extrae datos de la categoría 6."""
        # Tu lógica aquí
        return {
            "campo1": valor1,
            "campo2": valor2,
            **self.common_fields_data
        }
```

### Paso 3: Registrar en Factory

Edita `backend/app/services/extractors/factory.py`:

```python
from .category6 import Category6Extractor

EXTRACTORS = {
    "cat-1": Category1Extractor,
    "cat-2": Category2Extractor,
    # ... otros
    "cat-6": Category6Extractor,  # Agregar aquí
}
```

## 🐳 Docker

### Construir imagen

```bash
docker build -f backend/Dockerfile -t facturas-api .
```

### Ejecutar contenedor

```bash
docker run -p 8001:8001 \
  -e FIREBASE_PROJECT_ID=tu-proyecto \
  -e FIREBASE_PRIVATE_KEY=tu-clave \
  -e FIREBASE_CLIENT_EMAIL=tu-email \
  facturas-api
```

### Con docker-compose

```bash
docker-compose up
```

## 🔐 Autenticación

Todos los endpoints (excepto `/health`) requieren token JWT de Firebase.

Agregar header:
```bash
Authorization: Bearer <firebase-jwt-token>
```

## 🚧 Roadmap

### ✅ v1.0 - Completo
- 4 categorías funcionales (cat-1, 2, 4, 5)
- Sistema de extracción con Factory Pattern
- Autenticación por Firebase
- CRUD de zonas y categorías
- Validación automática

### 🔶 v1.1 - En Desarrollo
- [ ] Categoría 3 - Vuelos (Excel)
- [ ] Mejorar precisión de patrones regex
- [ ] OCR para imágenes embebidas

### 🔹 v1.2 - Próximo
- [ ] Sistema de auditoría
- [ ] Dashboard de métricas
- [ ] Análisis de confianza

### 🔹 v1.3 - Futuro
- [ ] Machine Learning para auto-clasificación
- [ ] Integración con Google Cloud Vision
- [ ] Soporte multi-idioma

## 🤝 Contribuir

1. Crea una rama: `git checkout -b feature/nueva-categoria`
2. Commit: `git commit -am 'Agregada nueva categoría'`
3. Push: `git push origin feature/nueva-categoria`
4. Abre un Pull Request

## 📝 Notas

- El archivo JSON de service account no debe versionarse
- Usa `.env` para variables sensibles
- La API corre en `http://localhost:8001` en desarrollo
- Documentación interactiva: `http://localhost:8001/docs`

## 📞 Soporte

Para preguntas o problemas, abre un issue en el repositorio.

## 📄 Licencia

Privado - UTPL Sostenible
