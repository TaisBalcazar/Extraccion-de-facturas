import logging
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes.health import router as health_router
from app.api.routes.facturas import router as facturas_router
from app.api.routes.catalogos import router as catalogos_router
from app.core.config import settings
from app.core.firebase import get_firestore_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


# =========================
# EXCEPTION HANDLING
# =========================
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Captura cualquier excepción no manejada por los routers.

    Loguea el stacktrace completo en el servidor (logs de Render) y devuelve
    al cliente un mensaje genérico con un código de referencia para poder
    correlacionar el error en los logs, sin exponer detalles internos.
    """
    error_id = uuid.uuid4().hex
    logger.error(
        "Error no manejado [%s] en %s %s", error_id, request.method, request.url.path,
        exc_info=exc,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Error interno del servidor", "error_id": error_id},
    )


# INSERT DE CATALOGOS BASE

ZONAS_BASE = [
    {
        "id": "zona-1",
        "nombre": "Zona 1",
        "numero": 1,
        "centros": ["CAYAMBE", "COCA", "IBARRA", "JOYA DE LOS SACHAS", "NUEVA LOJA", "OTAVALO",
                    "SANGABRIEL", "SHUSHUFINDI", "TULCAN"]
    },
    {
        "id": "zona-2",
        "nombre": "Zona 2 - DMQ",
        "numero": 2,
        "centros": ["QUITO", "QUITO-AMAGUAÑA", "QUITO-CALDERÓN", "QUITO-CARAPUNGO",
                    "QUITO-CARCELÉN", "QUITO-MACHACHI", "QUITO-SAN RAFAEL",
                    "QUITO-TUMBACO", "QUITO-TURUBAMBA", "QUITO-VILLAFLORA"]
    },
    {
        "id": "zona-3",
        "nombre": "Zona 3",
        "numero": 3,
        "centros": ["ALAUSÍ", "AMBATO", "EL CHACO", "GUARANDA", "LATACUNGA", "PELILEO",
                    "PUYO", "RIOBAMBA", "TENA"]
    },
    {
        "id": "zona-4",
        "nombre": "Zona 4",
        "numero": 4,
        "centros": ["BAHÍA DE CARAQUEZ", "CALCETA", "CHONE", "ESMERALDAS", "LA CONCORDIA", "MANTA",
                    "PEDERNALES", "PORTOVIEJO", "QUININDÉ", "SAN MIGUEL DE LOS BANCOS",
                    "SANTO DOMINGO", "BABAHOYO", "BALZAR", "DAULE"]
    },
    {
        "id": "zona-5",
        "nombre": "Zona 5",
        "numero": 5,
        "centros": ["DURÁN", "GALÁPAGOS - SAN CRISTOBAL", "GALÁPAGOS - SANTA CRUZ",
                    "GUASMO", "GUAYAQUIL - CENTENARIO", "GUAYAQUIL (Kennedy)",
                    "GUAYAQUIL-SUR OESTE", "LA TRONCAL", "MILAGRO", "NARANJAL",
                    "PLAYAS", "QUEVEDO", "QUINSALOMA", "SALINAS", "SAMANES", "SAMBORONDÓN"]
    },
    {
        "id": "zona-6",
        "nombre": "Zona 6",
        "numero": 6,
        "centros": ["AZOGUES", "CAÑAR", "CJG CUENCA", "CUENCA", "GUALACEO",
                    "LIMÓN INDANZA", "MACAS", "MENDÉZ", "MONAY", "PAUTE",
                    "SANTA ISABEL", "SUCUA"]
    },
    {
        "id": "zona-7",
        "nombre": "Zona 7",
        "numero": 7,
        "centros": ["ALAMOR", "BALSAS", "CARIAMANGA", "CATACOCHA", "CATAMAYO", "CELICA",
                    "GUALAQUIZA", "HUAQUILLAS", "LOJA", "MACARÁ", "MACHALA", "MADRID",
                    "NEW YORK", "PASAJE", "PIÑAS", "ROMA", "SANTA ROSA", "SARAGURO",
                    "YANZATZA", "ZAMORA", "ZARUMA", "ZUMBA"]
    },
]

CATEGORIAS_BASE = [
    {
        "id": "cat-1",
        "nombre": "Categoría 1",
        "numero": 1,
        "items": [
            "Diesel consumido en buses busetas y vehículos",
            "Gasolina móvil consumida en vehículos",
            "Gasolina ecopais consumida en vehículos",
            "Diesel consumido en generadores",
            "Emisiones por gases refrigerantes",
            "Recarga de extintores",
            "Gestión de excretas y fermentación enterica del ganado propiedad de la institución"
        ]
    },
    {
        "id": "cat-2",
        "nombre": "Categoría 2",
        "numero": 2,
        "items": [
            "Consumo eléctrico de la organización"
        ]
    },
    {
        "id": "cat-3",
        "nombre": "Categoría 3",
        "numero": 3,
        "items": [
            "Vuelos nacionales",
            "Vuelos internacionales"
        ]
    },
    {
        "id": "cat-4",
        "nombre": "Categoría 4",
        "numero": 4,
        "items": [
            "Papel bond",
            "Papel de baño",
            "Materiales varios de oficina",
            "Productos de limpieza",
            "Vasos plásticos",
            "Pernoctación en hoteles",
            "Consumo de agua",
            "Residuos orgánicos que van al relleno sanitario",
            "Aguas residuales descargadas en inodoros"
        ]
    },
    {
        "id": "cat-5",
        "nombre": "Categoría 5",
        "numero": 5,
        "items": [
            "Uso de plataformas virtuales"
        ]
    }
]


# =========================
# AUTO INIT
# =========================
def init_catalogos():
    db = get_firestore_client()

    if db is None:  # GUARDIA: evita crash si Firebase no está disponible
        logger.warning("Firebase no disponible, saltando init de catalogos")
        return

    logger.info("Inicializando catalogos...")

    for zona in ZONAS_BASE:
        ref = db.collection("zonas").document(zona["id"])
        if not ref.get().exists:
            ref.set({
                "nombre": zona["nombre"],
                "numero": zona["numero"],
                "centros": zona["centros"],
                "is_system": True
            })
            logger.info("Zona creada: %s", zona["nombre"])

    for cat in CATEGORIAS_BASE:
        ref = db.collection("categorias").document(cat["id"])
        if not ref.get().exists:
            ref.set({
                "nombre": cat["nombre"],
                "numero": cat["numero"],
                "items": cat["items"],
                "is_system": True
            })
            logger.info("Categoria creada: %s", cat["nombre"])


# =========================
# LIFESPAN
# =========================
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Iniciando API...")
    init_catalogos()
    logger.info("API lista")
    yield
    logger.info("Cerrando API...")


# =========================
# APP
# =========================
def create_app() -> FastAPI:
    app = FastAPI(
        title="Facturas API",
        version="1.0.0",
        description="API productiva para gestion de facturas",
        lifespan=lifespan
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_exception_handler(Exception, unhandled_exception_handler)

    app.include_router(health_router, tags=["health"])
    app.include_router(facturas_router, prefix="/api/v1", tags=["facturas"])
    app.include_router(catalogos_router, prefix="/api/v1", tags=["catalogos"])

    return app


app = create_app()