from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.health import router as health_router
from app.api.routes.facturas import router as facturas_router
from app.api.routes.catalogos import router as catalogos_router
from app.core.config import settings
from app.core.firebase import get_firestore_client


# INSERT DE CATALOGOS BASE

ZONAS_BASE = [
    {
        "id": "zona-1",
        "nombre": "Zona 1",
        "numero": 1,
        "centros": ["SAN GABRIEL", "SHUSHUFINDI", "IBARRA", "NUEVA LOJA", "OTAVALO", "TULCAN"]
    },
    {
        "id": "zona-2",
        "nombre": "Zona 2",
        "numero": 2,
        "centros": ["COCA", "JOYA DE LOS SACHAS", "TENA", "CAYAMBE", "SAN MIGUEL DE LOS BANCOS", "EL CHACO"]
    },
    {
        "id": "zona-3",
        "nombre": "Zona 3",
        "numero": 3,
        "centros": ["ALAUSÍ", "AMBATO", "GUARANDA", "LATACUNGA", "PELILEO", "PUYO", "RIOBAMBA"]
    },
    {
        "id": "zona-4",
        "nombre": "Zona 4",
        "numero": 4,
        "centros": ["BAHÍA DE CARAQUEZ", "CHONE", "CALCETA", "ESMERALDAS", "LA CONCORDIA", "MANTA",
                    "PEDERNALES", "PORTOVIEJO", "QUININDÉ", "SANTO DOMINGO"]
    },
    {
        "id": "zona-5",
        "nombre": "Zona 5",
        "numero": 5,
        "centros": ["BABAHOYO", "BALZAR", "DAULE", "DURÁN", "GALÁPAGOS - SAN CRISTOBAL",
                    "GALÁPAGOS - SANTA CRUZ", "GUASMO", "GUAYAQUIL (Kennedy)",
                    "GUAYAQUIL - CENTENARIO", "GUAYAQUIL-SUR OESTE", "MILAGRO", "NARANJAL",
                    "PLAYAS", "QUEVEDO", "QUINSALOMA", "SALINAS", "SAMANES", "SAMBORONDÓN"]
    },
    {
        "id": "zona-6",
        "nombre": "Zona 6",
        "numero": 6,
        "centros": ["AZOGUES", "CAÑAR", "CUENCA", "CJG CUENCA", "MONAY", "GUALACEO", "PAUTE",
                    "GUALAQUIZA", "LA TRONCAL", "LIMÓN INDANZA", "MENDÉZ", "MACAS",
                    "SUCUA", "SANTA ISABEL"]
    },
    {
        "id": "zona-7",
        "nombre": "Zona 7",
        "numero": 7,
        "centros": ["ALAMOR", "BALSAS", "CARIAMANGA", "CATACOCHA", "CATAMAYO", "CELICA",
                    "HUAQUILLAS", "LOJA", "MACARÁ", "MACHALA", "PASAJE", "PIÑAS",
                    "SANTA ROSA", "SARAGURO", "YANZATZA", "ZAMORA", "ZARUMA",
                    "ZUMBA", "MADRID", "ROMA", "NEW YORK"]
    },
    {
        "id": "zona-8",
        "nombre": "Zona 8 - DMQ",
        "numero": 8,
        "centros": ["QUITO", "QUITO-CALDERÓN", "QUITO-CARAPUNGO", "QUITO-CARCELÉN",
                    "QUITO-TUMBACO", "QUITO-VILLAFLORA", "QUITO-SAN RAFAEL",
                    "QUITO-AMAGUAÑA", "QUITO-MACHACHI", "QUITO-TURUBAMBA"]
    }
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

    if db is None:  # ← GUARDIA: evita crash si Firebase no está disponible
        print("⚠️  Firebase no disponible, saltando init de catálogos")
        return

    print("🔍 Inicializando catálogos...")

    for zona in ZONAS_BASE:
        ref = db.collection("zonas").document(zona["id"])
        if not ref.get().exists:
            ref.set({
                "nombre": zona["nombre"],
                "numero": zona["numero"],
                "centros": zona["centros"],
                "is_system": True
            })
            print(f"✔ Zona creada: {zona['nombre']}")

    for cat in CATEGORIAS_BASE:
        ref = db.collection("categorias").document(cat["id"])
        if not ref.get().exists:
            ref.set({
                "nombre": cat["nombre"],
                "numero": cat["numero"],
                "items": cat["items"],
                "is_system": True
            })
            print(f"✔ Categoría creada: {cat['nombre']}")


# =========================
# LIFESPAN
# =========================
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Iniciando API...")
    init_catalogos()
    print("✅ API lista")
    yield
    print("🛑 Cerrando API...")


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

    app.include_router(health_router, tags=["health"])
    app.include_router(facturas_router, prefix="/api/v1", tags=["facturas"])
    app.include_router(catalogos_router, prefix="/api/v1", tags=["catalogos"])

    return app


app = create_app()