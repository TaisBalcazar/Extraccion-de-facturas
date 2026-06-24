from datetime import datetime
import hashlib
import unicodedata
from typing import Optional, Tuple

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from google.cloud.firestore_v1.base_query import FieldFilter

from app.core.firebase import get_firestore_client
from app.core.security import get_current_user
from app.services.chat_logic import MESES, detectar_filtros
from app.services.factura_extractor import extraer_datos_factura
from app.services.resumen_service import actualizar_resumen
from app.services.pdf_extractor import PDFExtractor
from app.services.regex_patterns import RegexPatternLibrary

router = APIRouter()


# ══════════════════════════════════════════════════════════════
# Campos canónicos de una factura
# Fuente única de verdad: usada en upload, listado y serialización.
# ══════════════════════════════════════════════════════════════

FACTURA_FIELDS = [
    "filename", "upload_date", "zona_id", "zona_nombre",
    "centro", "categoria_id", "categoria_nombre", "item",
    # Categoría 1
    "factura_numero", "precio_unitario", "cantidad", "iva", "total",
    # Categoría 2
    "cod_unico", "nro_factura", "fecha_emision", "medidor",
    "consumo_total", "total_sec_elec", "contribucion_bomberos", "valor_total",
    "razon_social", "tipo_tarifa", "direccion_servicio", "dias_facturados",
    "anio", "mes_numero", "mes_nombre", "valor_consumo", "subsidio_tarifa",
    "comercializacion", "alumbrado_publico", "valor_forma_pago",
    "lectura_anterior", "lectura_actual", "diferencia_consumo",
    "consumo_subtotal", "consumo_interno_transformador", "consumo_kwh",
    "periodo_inicio", "periodo_fin",
    # Categoría 4 — Agua
    "tipo_documento", "consumo_m3",
    # Categoría 4 — Papel Bond
    "total_resmas_anual", "peso_papel_kg_anual", "peso_papel_ton_anual",
    # Categoría 4 - Hospedaje (pernoctación en hoteles)
    "proveedor", "noches_por_mes", "noches_por_mes_numero",
    "total_noches", "detalle_registros", "total_registros",
    # Categoría 5
    "periodos", "horas_trabajadas_bimestre1", "horas_trabajadas_bimestre2",
]

# Campos exactos permitidos por categoría (sin relleno con null).
_CATEGORY_ALLOWED_FIELDS = {
    "cat-1": {
        # Excel — reporte anual (Zona Loja)
        "anio", "tipo_documento", "tipo_combustible_clave", "tipo_combustible_label",
        "precio_galon", "mes_numero", "mes_nombre", "total_usd", "galones", "precios_galon",
        # PDF — facturas individuales (otras zonas)
        "nro_factura", "fecha_emision", "descripcion", "cantidad",
        "precio_unitario", "subtotal",
    },
    "cat-2": {
        "cod_unico",
        "nro_factura",
        "fecha_emision",
        "medidor",
        "consumo_total",
        "total_sec_elec",
        "contribucion_bomberos",
        "valor_total",
        "razon_social",
        "tipo_tarifa",
        "direccion_servicio",
        "dias_facturados",
        "anio",
        "mes_numero",
        "mes_nombre",
        "valor_consumo",
        "subsidio_tarifa",
        "comercializacion",
        "alumbrado_publico",
        "valor_forma_pago",
        "lectura_anterior",
        "lectura_actual",
        "diferencia_consumo",
        "consumo_subtotal",
        "consumo_interno_transformador",
        "consumo_kwh",
        "periodo_inicio",
        "periodo_fin",
    },
    "cat-4": {
        # Agua (Municipio de Loja) — un doc por factura
        "tipo_documento", "anio", "mes_numero", "mes_nombre",
        "consumo_m3", "agua_potable", "alcantarillado",
        "aportes_planes_maestros", "seguridad_ciudadana",
        "proteccion_microcuencas", "costo_basico_facturacion",
        "recoleccion_basura", "interes_recargo", "total_facturado",
        "medidor", "categoria", "ubicacion",
        "lectura_anterior", "lectura_actual",
        # Papel Bond — un doc por año
        "total_resmas_anual", "peso_papel_kg_anual", "peso_papel_ton_anual", "periodos",
        # Hospedaje — un doc por mes
        "noches",
    },
    "cat-3": {
        "anio", "tipo_documento", "tipo_vuelo",
        "mes_numero", "mes_nombre",
        "ruta", "km_por_viaje", "cantidad_viajes", "km_total",
    },
    "cat-5": {
        "periodos",
        "horas_trabajadas_bimestre1",
        "horas_trabajadas_bimestre2",
    },
}

# Campos que NO provienen de la extracción (se generan al guardar)
_CAMPOS_INTERNOS = {"filename", "upload_date"}


# ══════════════════════════════════════════════════════════════
# Mapa para el endpoint /chat
# Cada entrada: tupla de keywords → (campo_firestore, etiqueta_humana)
# ══════════════════════════════════════════════════════════════

CHAT_CAMPO_MAP: list[tuple[tuple[str, ...], tuple[str, str]]] = [
    (
        ("bomberos", "contribucion", "contribución"),
        ("contribucion_bomberos", "contribución a bomberos"),
    ),
]

# Categorías que aceptan Excel además de PDF.
_CATEGORIAS_EXCEL: set[str] = {"cat-1", "cat-3", "cat-4"}

# Mapeo clave interna de combustible → nombre del ítem en Firestore (cat-1).
# Los nombres deben coincidir (sin tildes, minúsculas) con los items de la colección categorias.
_GRUPO_A_ITEM: dict[str, str] = {
    "diesel_buses": "DIESEL CONSUMIDO EN BUSES BUSETAS Y VEHICULOS",
    "gasolina_ecopais": "GASOLINA ECOPAIS CONSUMIDA EN VEHICULOS",
    "gasolina_movil": "GASOLINA MOVIL CONSUMIDA EN VEHICULOS",
}

# Razón social permitida para evidencias de huella de carbono.
RAZON_SOCIAL_REQUERIDA = "UNIVERSIDAD TECNICA PARTICULAR DE LOJA"

# Razón social alternativa válida: facturas donde la identidad del cliente
# está oculta por la Ley de Protección de Datos del Ecuador.
RAZON_SOCIAL_LEY_PROTECCION_DATOS = "LEY DE PROTECCION DE DATOS"

# ──────────────────────────────────────────────────────────────
# Ítems que son reportes de proveedor (no facturas de la UTPL).
# Para estos ítems se omite la validación de razón social porque
# el documento proviene del proveedor, no de la institución.
# ──────────────────────────────────────────────────────────────
_ITEMS_SIN_VALIDACION_RAZON_SOCIAL: set[str] = {
    "papel bond",
    "papel de bano",
    "papel bano",
}


# ══════════════════════════════════════════════════════════════
# Helpers internos
# ══════════════════════════════════════════════════════════════

def _doc_to_dict(doc_id: str, data: dict) -> dict:
    """Serializa un documento Firestore sin inyectar campos nulos."""
    result = {"id": doc_id}
    for key, value in (data or {}).items():
        if key.startswith("__"):
            continue
        result[key] = value
    return result


def _normalizar_texto(valor: object) -> str:
    texto = str(valor or "")
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(caracter for caracter in texto if unicodedata.category(caracter) != "Mn")
    return texto.strip().lower()


def _extraer_razon_social_desde_texto(texto_pdf: str) -> Optional[str]:
    """Intenta detectar la razón social en el texto del PDF (optimizado)."""
    if not texto_pdf:
        return None

    lineas = [linea.strip() for linea in texto_pdf.splitlines() if linea and linea.strip()]
    patron_linea = RegexPatternLibrary.RAZON_SOCIAL_PATTERN

    for index, linea in enumerate(lineas):
        match = patron_linea.search(linea)
        if not match:
            continue

        valor = match.group(1).strip(" -:\t")
        if valor:
            return valor

        if index + 1 < len(lineas):
            siguiente = lineas[index + 1].strip(" -:\t")
            if siguiente:
                return siguiente

    return None


def _validar_razon_social_desde_extractor(pdf_extractor: PDFExtractor) -> Tuple[bool, Optional[str], str]:
    """
    Valida razón social usando PDFExtractor (evita lectura duplicada).

    Returns:
        (es_valida, razon_detectada, detalle_error)
    """
    try:
        texto_pdf = pdf_extractor.extract_text()
    except Exception as exc:
        return False, None, f"No se pudo leer el PDF para validar razón social: {exc}"

    print(f"🔍 [RAZON SOCIAL] Texto extraído ({len(texto_pdf)} chars): {repr(texto_pdf[:300])}")

    if not texto_pdf or len(texto_pdf.strip()) < 20:
        return (
            False,
            None,
            "El PDF parece estar escaneado (imagen sin texto) y no hay OCR disponible en el servidor. "
            "Instala EasyOCR ejecutando: pip install easyocr",
        )

    razon_detectada = _extraer_razon_social_desde_texto(texto_pdf)
    texto_normalizado = _normalizar_texto(texto_pdf)
    razon_requerida_norm = _normalizar_texto(RAZON_SOCIAL_REQUERIDA)

    razon_proteccion_norm = _normalizar_texto(RAZON_SOCIAL_LEY_PROTECCION_DATOS)

    if razon_detectada:
        razon_detectada_norm = _normalizar_texto(razon_detectada)
        if razon_requerida_norm in razon_detectada_norm:
            return True, razon_detectada, ""
        if razon_proteccion_norm in razon_detectada_norm:
            return True, razon_detectada, ""
        return (
            False,
            razon_detectada,
            f"La razón social no es la Universidad Técnica Particular de Loja (UTPL). Se detectó: '{razon_detectada}'.",
        )

    # Fallback 1: texto completo contiene la frase exacta normalizada.
    if razon_requerida_norm in texto_normalizado:
        return True, RAZON_SOCIAL_REQUERIDA, ""
    if razon_proteccion_norm in texto_normalizado:
        return True, RAZON_SOCIAL_LEY_PROTECCION_DATOS, ""

    # Fallback 2: palabras clave independientes (tolerante a errores de OCR en PDFs escaneados).
    # OCR puede cambiar caracteres individuales pero raramente destruye palabras completas.
    palabras_utpl = ["universidad", "particular", "loja"]
    if all(kw in texto_normalizado for kw in palabras_utpl):
        return True, RAZON_SOCIAL_REQUERIDA, ""

    return (
        False,
        None,
        "No se detectó la razón social de la Universidad Técnica Particular de Loja (UTPL) en el PDF.",
    )


def _resolver_catalogo_doc(db, collection_name: str, valor: str, etiqueta: str):
    valor_normalizado = _normalizar_texto(valor)
    if not valor_normalizado:
        raise HTTPException(status_code=400, detail=f"La {etiqueta} es obligatoria")

    doc = db.collection(collection_name).document(valor).get()
    if doc.exists:
        return doc

    for candidate in db.collection(collection_name).stream():
        data = candidate.to_dict() or {}
        if valor_normalizado in {
            _normalizar_texto(candidate.id),
            _normalizar_texto(data.get("nombre")),
            _normalizar_texto(data.get("numero")),
        }:
            return candidate

    raise HTTPException(status_code=400, detail=f"La {etiqueta} seleccionada no existe")


def _datos_to_doc(
    datos: dict,
    filename: str,
    uid: str,
    email: str,
    asociacion: dict,
) -> dict:
    """
    Construye el documento a guardar en Firestore a partir de los datos
    extraídos del PDF y los metadatos de la solicitud.
    """
    doc: dict = {}
    categoria_id = asociacion.get("categoria_id")
    allowed_fields = _CATEGORY_ALLOWED_FIELDS.get(categoria_id)

    # Guardar solo campos con valor.
    # - Si la categoría tiene whitelist, usar solo esos campos.
    # - Si no, conservar comportamiento flexible para otras categorías.
    source_fields = allowed_fields if allowed_fields is not None else set(datos.keys())
    for field in source_fields:
        if field in _CAMPOS_INTERNOS:
            continue
        value = datos.get(field)
        if value is not None:
            doc[field] = value

    # Campos de control
    doc["filename"] = filename
    doc["upload_date"] = datetime.now().isoformat()
    doc["owner_uid"] = uid
    doc["owner_email"] = email
    if datos.get("razon_social"):
        doc["razon_social"] = datos["razon_social"]

    # Campos denormalizados de asociación (zona, categoría, item)
    doc.update(asociacion)

    # Campo para filtrado eficiente en Firestore (evita str-contains en Python)
    fecha = datos.get("fecha_emision") or ""
    doc["year"] = int(fecha[:4]) if len(fecha) >= 4 and fecha[:4].isdigit() else None
    # Cat-3 hospedaje no tiene fecha_emision; usar campo anio del Excel
    if doc["year"] is None and datos.get("anio"):
        try:
            doc["year"] = int(datos["anio"])
        except (TypeError, ValueError):
            pass
    
    # Hash único para detección de duplicados (OPTIMIZACIÓN)
    factura_numero = datos.get("factura_numero") or datos.get("nro_factura")
    medidor = datos.get("medidor")
    hash_factura = _generar_hash_factura(factura_numero, medidor, fecha)
    if hash_factura:
        doc["hash_factura"] = hash_factura

    return doc


def _validar_asociacion_factura(db, zona_id: str, categoria_id: str, item: str, centro: str) -> dict:
    """Valida zona/categoría/item/centro y retorna metadatos normalizados."""
    zona_doc = _resolver_catalogo_doc(db, "zonas", zona_id, "zona")

    categoria_doc = _resolver_catalogo_doc(db, "categorias", categoria_id, "categoría")

    categoria_data = categoria_doc.to_dict() or {}
    zona_data = zona_doc.to_dict() or {}
    item_normalizado = _normalizar_texto(item)
    centro_normalizado = _normalizar_texto(centro)

    if not item_normalizado:
        raise HTTPException(status_code=400, detail="El item es obligatorio")

    if not centro_normalizado:
        raise HTTPException(status_code=400, detail="El centro es obligatorio")

    items_validos = categoria_data.get("items") or []
    item_canonico = next(
        (item_catalogo for item_catalogo in items_validos if _normalizar_texto(item_catalogo) == item_normalizado),
        None,
    )
    if not item_canonico:
        raise HTTPException(
            status_code=400,
            detail="El item seleccionado no pertenece a la categoría indicada",
        )

    centros_validos = zona_data.get("centros") or []
    centro_canonico = next(
        (centro_catalogo for centro_catalogo in centros_validos if _normalizar_texto(centro_catalogo) == centro_normalizado),
        None,
    )
    if not centro_canonico:
        raise HTTPException(
            status_code=400,
            detail="El centro seleccionado no pertenece a la zona indicada",
        )

    return {
        "zona_id": zona_doc.id,
        "zona_nombre": zona_data.get("nombre"),
        "centro": centro_canonico,
        "categoria_id": categoria_doc.id,
        "categoria_nombre": categoria_data.get("nombre"),
        "item": item_canonico,
    }


def _generar_hash_factura(factura_numero: Optional[str], medidor: Optional[str], fecha_emision: Optional[str]) -> Optional[str]:
    """
    Genera un hash único para una factura basado en sus datos clave.
    
    Más rápido que múltiples queries a Firestore.
    
    Args:
        factura_numero: Número de factura
        medidor: Número de medidor
        fecha_emision: Fecha de emisión
    
    Returns:
        Hash MD5 o None si faltan datos
    """
    if not (factura_numero and medidor and fecha_emision):
        return None
    
    datos_clave = f"{factura_numero}:{medidor}:{fecha_emision}"
    return hashlib.md5(datos_clave.encode()).hexdigest()


def _verificar_duplicado(db, factura_numero: Optional[str], medidor: Optional[str], fecha_emision: Optional[str], owner_uid: str) -> bool:
    """
    Verifica si ya existe una factura duplicada.

    OPTIMIZADO: Usa hash único en lugar de múltiples queries.

    Returns:
        True si existe un duplicado
    """
    if not (factura_numero and medidor and fecha_emision):
        return False

    hash_factura = _generar_hash_factura(factura_numero, medidor, fecha_emision)
    if not hash_factura:
        return False

    # Buscar por hash es mucho más rápido que 3 condiciones WHERE
    try:
        duplicados = (
            db.collection("facturas")
            .where(filter=FieldFilter("owner_uid", "==", owner_uid))
            .where(filter=FieldFilter("hash_factura", "==", hash_factura))
            .limit(1)
            .stream()
        )
        return any(duplicados)
    except Exception:
        # Fallback: si hay error, permitir procesar (mejor que rechazar)
        return False


def _obtener_precios_combustible(db) -> dict:
    """Lee los precios de combustible desde Firestore; usa defaults si no hay config."""
    from app.services.extractors.category1 import PRECIOS_COMBUSTIBLE_DEFAULT
    try:
        doc = db.collection("config").document("precios_combustible").get()
        if doc.exists:
            data = doc.to_dict() or {}
            return {
                k: float(data[k])
                for k in PRECIOS_COMBUSTIBLE_DEFAULT
                if k in data and isinstance(data[k], (int, float))
            } | {k: v for k, v in PRECIOS_COMBUSTIBLE_DEFAULT.items() if k not in data}
    except Exception as exc:
        print(f"⚠️ [PRECIOS] Error leyendo config, usando defaults: {exc}")
    return dict(PRECIOS_COMBUSTIBLE_DEFAULT)


def _buscar_combustible_existente(
    db,
    owner_uid: str,
    zona_id: str,
    centro: str,
    anio: int,
    clave_grupo: str,
    mes_numero: int,
) -> Optional[Tuple[str, dict]]:
    """Busca reporte de combustible del mismo usuario/zona/centro/año/grupo/mes."""
    try:
        docs = (
            db.collection("facturas")
            .where(filter=FieldFilter("owner_uid", "==", owner_uid))
            .where(filter=FieldFilter("year", "==", anio))
            .stream()
        )
        for doc in docs:
            data = doc.to_dict() or {}
            if (
                data.get("tipo_documento") == "reporte_combustible"
                and data.get("zona_id") == zona_id
                and data.get("centro") == centro
                and data.get("tipo_combustible_clave") == clave_grupo
                and data.get("mes_numero") == mes_numero
            ):
                return doc.id, data
    except Exception as exc:
        print(f"⚠️ [CAT1 MERGE] Error buscando reporte existente: {exc}")
    return None


def _buscar_hospedaje_existente(
    db,
    owner_uid: str,
    zona_id: str,
    centro: str,
    anio: int,
    mes_numero: int,
) -> Optional[Tuple[str, dict]]:
    """Busca pernoctación del mismo usuario/zona/centro/año/mes."""
    try:
        docs = (
            db.collection("facturas")
            .where(filter=FieldFilter("owner_uid", "==", owner_uid))
            .where(filter=FieldFilter("year", "==", anio))
            .stream()
        )
        for doc in docs:
            data = doc.to_dict() or {}
            if (
                data.get("tipo_documento") == "hospedaje"
                and data.get("zona_id") == zona_id
                and data.get("centro") == centro
                and data.get("mes_numero") == mes_numero
            ):
                return doc.id, data
    except Exception as exc:
        print(f"⚠️ [CAT4 HOSPEDAJE MERGE] Error buscando registro existente: {exc}")
    return None


def _buscar_vuelo_existente(
    db,
    owner_uid: str,
    zona_id: str,
    centro: str,
    anio: int,
    tipo_vuelo: str,
    mes_numero: int,
) -> Optional[Tuple[str, dict]]:
    """Busca doc de vuelos del mismo usuario/zona/centro/año/tipo/mes."""
    try:
        docs = (
            db.collection("facturas")
            .where(filter=FieldFilter("owner_uid", "==", owner_uid))
            .where(filter=FieldFilter("year", "==", anio))
            .stream()
        )
        for doc in docs:
            data = doc.to_dict() or {}
            if (
                data.get("tipo_documento") == "vuelos"
                and data.get("zona_id") == zona_id
                and data.get("centro") == centro
                and data.get("tipo_vuelo") == tipo_vuelo
                and data.get("mes_numero") == mes_numero
            ):
                return doc.id, data
    except Exception as exc:
        print(f"⚠️ [CAT3 VUELOS] Error buscando registro existente: {exc}")
    return None


def _buscar_vuelo_ruta_existente(
    db,
    owner_uid: str,
    zona_id: str,
    centro: str,
    anio: int,
    tipo_vuelo: str,
    mes_numero: int,
    ruta: str,
) -> Optional[Tuple[str, dict]]:
    """Busca doc de detalle-ruta del mismo usuario/zona/centro/año/tipo/mes/ruta."""
    try:
        docs = (
            db.collection("facturas")
            .where(filter=FieldFilter("owner_uid", "==", owner_uid))
            .where(filter=FieldFilter("year", "==", anio))
            .stream()
        )
        for doc in docs:
            data = doc.to_dict() or {}
            if (
                data.get("tipo_documento") == "vuelos_ruta"
                and data.get("zona_id") == zona_id
                and data.get("centro") == centro
                and data.get("tipo_vuelo") == tipo_vuelo
                and data.get("mes_numero") == mes_numero
                and data.get("ruta") == ruta
            ):
                return doc.id, data
    except Exception as exc:
        print(f"⚠️ [CAT3 RUTA] Error buscando registro existente: {exc}")
    return None


def _buscar_papel_bond_existente(
    db,
    owner_uid: str,
    zona_id: str,
    centro: str,
    anio: int,
) -> Optional[Tuple[str, dict]]:
    """
    Busca si ya existe un reporte de papel bond del mismo usuario,
    zona, centro y año.

    Filtra owner_uid + year en Firestore (índices simples ya existentes) y
    comprueba tipo_documento / zona_id / centro en Python para evitar
    la necesidad de índices compuestos adicionales.

    Returns:
        (doc_id, doc_data) si existe, o None si no hay coincidencia.
    """
    try:
        docs = (
            db.collection("facturas")
            .where(filter=FieldFilter("owner_uid", "==", owner_uid))
            .where(filter=FieldFilter("year", "==", anio))
            .stream()
        )
        for doc in docs:
            data = doc.to_dict() or {}
            if (
                data.get("tipo_documento") == "papel_bond"
                and data.get("zona_id") == zona_id
                and data.get("centro") == centro
            ):
                return doc.id, data
    except Exception as exc:
        print(f"⚠️ [BOND MERGE] Error al buscar documento existente: {exc}")
    return None


def _merge_bond_periodos(
    periodos_existentes: list,
    periodos_nuevos: list,
) -> list:
    """
    Fusiona dos listas de períodos de papel bond.

    Reglas:
    - Los meses del nuevo reporte SOBREESCRIBEN a los del existente
      (permite corregir un período ya guardado).
    - Los meses presentes solo en el existente se CONSERVAN
      (permite subir reportes parciales sin perder meses previos).
    - El resultado se ordena cronológicamente por mes_numero.
    """
    mapa: dict = {}
    for periodo in (periodos_existentes or []):
        mes_num = periodo.get("mes_numero")
        if mes_num is not None:
            mapa[mes_num] = periodo
    for periodo in (periodos_nuevos or []):
        mes_num = periodo.get("mes_numero")
        if mes_num is not None:
            mapa[mes_num] = periodo  # nuevo sobreescribe existente
    return sorted(mapa.values(), key=lambda p: p["mes_numero"])


def _obtener_facturas_filtradas(
    db,
    owner_uid: str,
    tipo_servicio: Optional[str] = None,
    year: Optional[str] = None,
    mes: Optional[str] = None,
) -> list[dict]:
    """
    Consulta facturas aplicando filtros en Firestore cuando es posible
    y en Python solo para el mes (que requeriría índice compuesto).
    """
    if not db:
        return []

    query = db.collection("facturas").where(
        filter=FieldFilter("owner_uid", "==", owner_uid)
    )

    if tipo_servicio:
        query = query.where(filter=FieldFilter("tipo_servicio", "==", tipo_servicio))

    # year se filtra en Firestore gracias al campo denormalizado
    if year:
        query = query.where(filter=FieldFilter("year", "==", int(year)))

    facturas = []
    for doc in query.stream():
        data = doc.to_dict()
        data["__id__"] = doc.id
        # Mes no puede filtrarse en Firestore sin índice compuesto adicional
        if mes and f"-{mes}-" not in str(data.get("fecha_emision", "")):
            continue
        facturas.append(data)

    return facturas


def _respuesta_campo(facturas: list, campo: str, label: str) -> str:
    """Genera la respuesta de texto para una consulta de chat sobre un campo numérico."""
    total = sum(f.get(campo, 0) or 0 for f in facturas)
    cantidad = sum(1 for f in facturas if f.get(campo))
    return f"Se gastaron ${total:.2f} USD en {label} en {cantidad} factura(s)."


def _monto_factura(data: dict) -> float:
    """Obtiene el monto de una factura usando campos disponibles por categoría."""
    return float(
        data.get("total_usd")
        or data.get("total")
        or data.get("valor_total")
        or data.get("total_sec_elec")
        or 0
    )


def _consumo_factura(data: dict) -> float:
    """Obtiene el consumo de una factura usando campos disponibles por categoría."""
    return float(data.get("consumo_kwh") or data.get("consumo_total") or 0)


# ══════════════════════════════════════════════════════════════
# Modelos
# ══════════════════════════════════════════════════════════════

class ChatRequest(BaseModel):
    message: str


# ══════════════════════════════════════════════════════════════
# Endpoints
# ══════════════════════════════════════════════════════════════

@router.get("/facturas")
def listar_facturas(
    year: Optional[str] = None,
    tipo_servicio: Optional[str] = None,
    medidor: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    """Lista facturas del usuario con filtros opcionales."""
    try:
        db = get_firestore_client()
        if not db:
            return []

        facturas = _obtener_facturas_filtradas(
            db, user["uid"], tipo_servicio=tipo_servicio, year=year
        )

        # medidor no tiene índice dedicado: filtro local barato
        if medidor:
            facturas = [f for f in facturas if f.get("medidor") == medidor]

        # Serializar con FACTURA_FIELDS y ordenar
        result = [_doc_to_dict(f.get("__id__", ""), f) for f in facturas]
        result.sort(key=lambda x: str(x.get("upload_date") or ""), reverse=True)
        return result

    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Error al listar facturas: {exc}"
        ) from exc


@router.post("/upload")
async def upload_file(
    zona_id: str = Form(...),
    centro: str = Form(...),
    categoria_id: str = Form(...),
    item: str = Form(...),
    files: list[UploadFile] = File(...),
    user: dict = Depends(get_current_user),
):
    """Recibe PDFs, extrae sus datos y los guarda en Firestore."""
    if not files:
        raise HTTPException(status_code=400, detail="No se recibieron archivos")

    db = get_firestore_client()
    if not db:
        raise HTTPException(status_code=503, detail="Firebase no disponible en este entorno")

    asociacion = _validar_asociacion_factura(db, zona_id, categoria_id, item, centro)

    print(f"[UPLOAD] Usuario: {user.get('email')} | Archivos: {len(files)}")

    resultados, errores, duplicados = [], [], []

    for file in files:
        filename = file.filename or ""
        print(f"📄 [UPLOAD] Procesando: {filename}")

        es_excel = filename.lower().endswith((".xlsx", ".xls"))
        es_pdf = filename.lower().endswith(".pdf")

        if not es_pdf and not es_excel:
            errores.append({"filename": filename, "error": "Solo se aceptan archivos PDF o Excel (.xlsx/.xls)"})
            continue

        if es_excel and asociacion.get("categoria_id") not in _CATEGORIAS_EXCEL:
            errores.append({"filename": filename, "error": "Los archivos Excel solo se aceptan para Categoría 1 (Combustible), Categoría 3 (Vuelos) y Categoría 4 (Pernoctación en hoteles)"})
            continue

        try:
            content = await file.read()
            print(f"📥 [UPLOAD] {filename} — {len(content)} bytes")

            razon_social_detectada = None

            if es_pdf:
                # Determinar si el ítem requiere validación de razón social UTPL.
                # Los reportes de proveedor (papel bond, etc.) se procesan sin validar.
                item_norm = _normalizar_texto(asociacion.get("item", ""))
                requiere_razon_social = item_norm not in _ITEMS_SIN_VALIDACION_RAZON_SOCIAL

                # OPTIMIZACIÓN: Usar PDFExtractor para evitar lectura duplicada
                pdf_extractor = PDFExtractor(content, filename)
                try:
                    es_razon_social_valida, razon_social_detectada, alerta_razon_social = _validar_razon_social_desde_extractor(pdf_extractor)
                finally:
                    pdf_extractor.close()

                if requiere_razon_social and not es_razon_social_valida:
                    print(f"🚫 [UPLOAD] Rechazada por razón social: {filename} | {alerta_razon_social}")
                    errores.append({
                        "filename": filename,
                        "error": alerta_razon_social,
                        "razon_social_detectada": razon_social_detectada,
                        "tipo_alerta": "razon_social_invalida",
                    })
                    continue

                if not requiere_razon_social:
                    print(f"ℹ️ [UPLOAD] Validación de razón social omitida para ítem '{asociacion.get('item')}': {filename}")

            else:
                # ── Cat-1 Excel: solo permitido para Zona Loja ───────────────────
                if asociacion.get("categoria_id") == "cat-1":
                    zona_norm = _normalizar_texto(asociacion.get("zona_nombre", ""))
                    if "loja" not in zona_norm:
                        errores.append({
                            "filename": filename,
                            "error": (
                                "El reporte Excel de combustible solo está disponible para Zona 7 (Loja). "
                                "Las demás zonas deben subir facturas PDF individuales."
                            ),
                        })
                        continue
                    print(f"📊 [UPLOAD] Excel combustible cat-1: {filename}")
                    from app.services.extractors.category1 import Category1Extractor
                    precios = _obtener_precios_combustible(db)
                    datos_completos = Category1Extractor(precios=precios).extract(content, filename)

                    if not datos_completos.get("extraction_success"):
                        errores.append({"filename": filename, "error": datos_completos.get("error", "Error extrayendo Excel")})
                        continue

                    cat_doc = db.collection("categorias").document(asociacion["categoria_id"]).get()
                    items_validos = ((cat_doc.to_dict() or {}).get("items") or []) if cat_doc.exists else []
                    grupos = datos_completos.get("grupos") or {}
                    anio_comb = datos_completos.get("anio")

                    for clave_grupo, grupo in grupos.items():
                        if clave_grupo == "diesel_generadores":
                            continue
                        item_label = _GRUPO_A_ITEM.get(clave_grupo)
                        if not item_label:
                            continue
                        item_norm = _normalizar_texto(item_label)
                        item_canonico = next((i for i in items_validos if _normalizar_texto(i) == item_norm), None)
                        if not item_canonico:
                            errores.append({"filename": filename, "tipo_combustible": clave_grupo,
                                "error": f"Item '{item_label}' no encontrado en Categoría 1 (Firestore)."})
                            continue

                        asociacion_grupo = {**asociacion, "item": item_canonico}
                        anio_int = int(anio_comb) if anio_comb else 0

                        for mes in grupo.get("meses", []):
                            if (mes.get("total_usd") or 0) == 0:
                                continue

                            datos_mes = {
                                "filename": filename,
                                "anio": anio_comb,
                                "tipo_documento": "reporte_combustible",
                                "tipo_combustible_clave": clave_grupo,
                                "tipo_combustible_label": grupo["label"],
                                "precio_galon": grupo["precio_galon"],
                                "mes_numero": mes["mes_numero"],
                                "mes_nombre": mes["mes_nombre"],
                                "total_usd": mes["total_usd"],
                                "galones": mes["galones"],
                                "precios_galon": datos_completos.get("precios_galon", {}),
                                "extraction_success": True,
                            }
                            doc_data_mes = _datos_to_doc(
                                datos=datos_mes, filename=filename,
                                uid=user["uid"], email=user.get("email", ""),
                                asociacion=asociacion_grupo,
                            )
                            existente_comb = _buscar_combustible_existente(
                                db, owner_uid=user["uid"],
                                zona_id=asociacion["zona_id"], centro=asociacion["centro"],
                                anio=anio_int, clave_grupo=clave_grupo,
                                mes_numero=mes["mes_numero"],
                            )
                            if existente_comb:
                                doc_id_comb, _ = existente_comb
                                db.collection("facturas").document(doc_id_comb).set(doc_data_mes)
                                print(f"🔄 [CAT1] {clave_grupo} {anio_comb}/{mes['mes_nombre']} actualizado: {doc_id_comb}")
                                resultados.append({"filename": filename, "id": doc_id_comb,
                                    "zona_id": asociacion["zona_id"], "centro": asociacion["centro"],
                                    "categoria_id": asociacion["categoria_id"], "item": item_canonico,
                                    "tipo_combustible": clave_grupo, "mes": mes["mes_nombre"],
                                    "datos_extraidos": datos_mes,
                                    "status": "updated",
                                    "mensaje": f"{grupo['label']} {anio_comb}/{mes['mes_nombre']} actualizado"})
                            else:
                                doc_ref = db.collection("facturas").add(doc_data_mes)
                                doc_id_comb = doc_ref[1].id
                                try:
                                    actualizar_resumen(db, user["uid"], doc_data_mes, signo=1)
                                except Exception as exc_res:
                                    print(f"⚠️ [RESUMEN] {exc_res}")
                                print(f"💾 [CAT1] {clave_grupo} {anio_comb}/{mes['mes_nombre']} guardado: {doc_id_comb}")
                                resultados.append({"filename": filename, "id": doc_id_comb,
                                    "zona_id": asociacion["zona_id"], "centro": asociacion["centro"],
                                    "categoria_id": asociacion["categoria_id"], "item": item_canonico,
                                    "tipo_combustible": clave_grupo, "mes": mes["mes_nombre"],
                                    "datos_extraidos": datos_mes,
                                    "status": "success"})
                    continue  # siguiente archivo

                # ── Cat-3 Excel: vuelos (un documento por ruta × mes) ────────
                if asociacion.get("categoria_id") == "cat-3":
                    print(f"✈️  [UPLOAD] Excel vuelos cat-3: {filename}")
                    from app.services.extractors.category3 import Category3Extractor
                    datos_vuelos = Category3Extractor().extract(content, filename)

                    if not datos_vuelos.get("extraction_success"):
                        errores.append({"filename": filename, "error": datos_vuelos.get("error", "Error extrayendo Excel vuelos")})
                        continue

                    anio_vuelos    = datos_vuelos.get("anio")
                    anio_int_vuelos = int(anio_vuelos) if anio_vuelos else 0

                    cat3_doc = db.collection("categorias").document("cat-3").get()
                    items_validos_vuelos = ((cat3_doc.to_dict() or {}).get("items") or []) if cat3_doc.exists else []

                    _TIPO_A_ITEM_VUELOS: dict[str, str] = {
                        "nacional":      "VUELOS NACIONALES",
                        "internacional": "VUELOS INTERNACIONALES",
                    }

                    for entrada_ruta in (datos_vuelos.get("rutas_por_mes") or []):
                        tipo_r    = entrada_ruta["tipo"]
                        mes_r     = entrada_ruta["mes_num"]
                        ruta_str  = entrada_ruta["ruta"]
                        mes_nom_r = entrada_ruta["mes_nombre"]

                        item_label_r    = _TIPO_A_ITEM_VUELOS[tipo_r]
                        item_canonico_r = next(
                            (i for i in items_validos_vuelos if _normalizar_texto(i) == _normalizar_texto(item_label_r)),
                            None,
                        )
                        if not item_canonico_r:
                            errores.append({
                                "filename": filename,
                                "error": f"Ítem '{item_label_r}' no encontrado en Categoría 3 (Firestore).",
                            })
                            continue

                        asociacion_ruta = {**asociacion, "item": item_canonico_r}
                        datos_ruta = {
                            "filename":        filename,
                            "anio":            anio_vuelos,
                            "tipo_documento":  "vuelos_ruta",
                            "tipo_vuelo":      tipo_r,
                            "mes_numero":      mes_r,
                            "mes_nombre":      mes_nom_r,
                            "ruta":            ruta_str,
                            "km_por_viaje":    entrada_ruta["km_por_viaje"],
                            "cantidad_viajes": entrada_ruta["cantidad"],
                            "km_total":        entrada_ruta["km_total"],
                            "extraction_success": True,
                        }
                        doc_data_ruta = _datos_to_doc(
                            datos=datos_ruta, filename=filename,
                            uid=user["uid"], email=user.get("email", ""),
                            asociacion=asociacion_ruta,
                        )
                        existente_ruta = _buscar_vuelo_ruta_existente(
                            db, owner_uid=user["uid"],
                            zona_id=asociacion["zona_id"], centro=asociacion["centro"],
                            anio=anio_int_vuelos, tipo_vuelo=tipo_r,
                            mes_numero=mes_r, ruta=ruta_str,
                        )
                        if existente_ruta:
                            doc_id_ruta, _ = existente_ruta
                            db.collection("facturas").document(doc_id_ruta).set(doc_data_ruta)
                            print(f"🔄 [CAT3] {ruta_str} {mes_nom_r} actualizado: {doc_id_ruta}")
                            resultados.append({
                                "filename": filename, "id": doc_id_ruta,
                                "zona_id": asociacion["zona_id"], "centro": asociacion["centro"],
                                "categoria_id": asociacion["categoria_id"], "item": item_canonico_r,
                                "tipo_vuelo": tipo_r, "ruta": ruta_str, "mes": mes_nom_r,
                                "km_total": entrada_ruta["km_total"], "status": "updated",
                            })
                        else:
                            doc_ref_ruta = db.collection("facturas").add(doc_data_ruta)
                            doc_id_ruta = doc_ref_ruta[1].id
                            try:
                                actualizar_resumen(db, user["uid"], doc_data_ruta, signo=1)
                            except Exception as exc_res:
                                print(f"⚠️ [RESUMEN] {exc_res}")
                            print(f"💾 [CAT3] {ruta_str} {mes_nom_r}: {entrada_ruta['cantidad']}x {entrada_ruta['km_por_viaje']} km → {doc_id_ruta}")
                            resultados.append({
                                "filename": filename, "id": doc_id_ruta,
                                "zona_id": asociacion["zona_id"], "centro": asociacion["centro"],
                                "categoria_id": asociacion["categoria_id"], "item": item_canonico_r,
                                "tipo_vuelo": tipo_r, "ruta": ruta_str, "mes": mes_nom_r,
                                "km_total": entrada_ruta["km_total"], "status": "success",
                            })
                    continue  # siguiente archivo

                # ── Cat-4 Excel: hospedaje (pernoctación en hoteles) ─────────
                if asociacion.get("categoria_id") == "cat-4":
                    print(f"📊 [UPLOAD] Excel hospedaje cat-4: {filename}")
                    from app.services.extractors.category4 import Category4Extractor
                    datos_hosp = Category4Extractor().extract(content, filename)

                    if not datos_hosp.get("extraction_success"):
                        errores.append({"filename": filename, "error": datos_hosp.get("error", "Error extrayendo Excel hospedaje")})
                        continue

                    anio_hosp = datos_hosp.get("anio")
                    anio_int_hosp = int(anio_hosp) if anio_hosp else 0
                    # {str(mes_numero): noches} — viene del extractor
                    noches_num = datos_hosp.get("noches_por_mes_numero") or {}

                    _MESES_NOMBRES_HOSP: dict[int, str] = {
                        1: "ENERO", 2: "FEBRERO", 3: "MARZO", 4: "ABRIL",
                        5: "MAYO", 6: "JUNIO", 7: "JULIO", 8: "AGOSTO",
                        9: "SEPTIEMBRE", 10: "OCTUBRE", 11: "NOVIEMBRE", 12: "DICIEMBRE",
                    }

                    for mes_key, noches_mes in sorted(noches_num.items(), key=lambda kv: int(kv[0])):
                        mes_num = int(mes_key)
                        if not noches_mes or noches_mes == 0:
                            continue

                        datos_mes_hosp = {
                            "filename": filename,
                            "anio": anio_hosp,
                            "tipo_documento": "hospedaje",
                            "mes_numero": mes_num,
                            "mes_nombre": _MESES_NOMBRES_HOSP.get(mes_num, str(mes_num)),
                            "noches": noches_mes,
                            "extraction_success": True,
                        }
                        doc_data_hosp = _datos_to_doc(
                            datos=datos_mes_hosp, filename=filename,
                            uid=user["uid"], email=user.get("email", ""),
                            asociacion=asociacion,
                        )
                        existente_hosp = _buscar_hospedaje_existente(
                            db, owner_uid=user["uid"],
                            zona_id=asociacion["zona_id"], centro=asociacion["centro"],
                            anio=anio_int_hosp, mes_numero=mes_num,
                        )
                        mes_nombre_log = _MESES_NOMBRES_HOSP.get(mes_num, str(mes_num))
                        if existente_hosp:
                            doc_id_hosp, _ = existente_hosp
                            db.collection("facturas").document(doc_id_hosp).set(doc_data_hosp)
                            print(f"🔄 [CAT4 HOSP] {anio_hosp}/{mes_nombre_log} actualizado: {doc_id_hosp}")
                            resultados.append({
                                "filename": filename, "id": doc_id_hosp,
                                "zona_id": asociacion["zona_id"], "centro": asociacion["centro"],
                                "categoria_id": asociacion["categoria_id"], "item": asociacion.get("item"),
                                "mes": mes_nombre_log, "noches": noches_mes,
                                "datos_extraidos": datos_mes_hosp, "status": "updated",
                                "mensaje": f"Hospedaje {anio_hosp}/{mes_nombre_log} actualizado",
                            })
                        else:
                            doc_ref = db.collection("facturas").add(doc_data_hosp)
                            doc_id_hosp = doc_ref[1].id
                            try:
                                actualizar_resumen(db, user["uid"], doc_data_hosp, signo=1)
                            except Exception as exc_res:
                                print(f"⚠️ [RESUMEN] {exc_res}")
                            print(f"💾 [CAT4 HOSP] {anio_hosp}/{mes_nombre_log}: {noches_mes} noches → {doc_id_hosp}")
                            resultados.append({
                                "filename": filename, "id": doc_id_hosp,
                                "zona_id": asociacion["zona_id"], "centro": asociacion["centro"],
                                "categoria_id": asociacion["categoria_id"], "item": asociacion.get("item"),
                                "mes": mes_nombre_log, "noches": noches_mes,
                                "datos_extraidos": datos_mes_hosp, "status": "success",
                            })
                    continue  # siguiente archivo

                # cat-4 pero Excel no hospedaje (no debería ocurrir, cae al flujo general)
                print(f"📊 [UPLOAD] Excel cat-4 no hospedaje: {filename}")

            # Extracción de datos (PDF y cat-3 Excel; cat-1 Excel ya hizo continue)
            datos = extraer_datos_factura(content, filename, categoria_id)
            datos["razon_social"] = razon_social_detectada
            factura_numero = datos.get("factura_numero") or datos.get("nro_factura")
            medidor = datos.get("medidor")
            fecha_emision = datos.get("fecha_emision")
            total_log = _monto_factura(datos)

            print(
                f"✅ [UPLOAD] Extraído: #{factura_numero} | "
                f"medidor={medidor} | fecha={fecha_emision} | "
                f"servicio={datos.get('tipo_servicio')} | total={total_log}"
            )

            # ── Papel bond: fusionar con reporte existente del mismo año ─────────
            # Si ya existe un documento de papel bond para el mismo usuario / zona /
            # centro / año se FUSIONAN los períodos (los nuevos sobreescriben a los
            # existentes del mismo mes; los meses previos no incluidos se conservan).
            if datos.get("tipo_documento") == "papel_bond":
                anio_bond = datos.get("anio")
                if anio_bond:
                    doc_existente = _buscar_papel_bond_existente(
                        db,
                        owner_uid=user["uid"],
                        zona_id=asociacion.get("zona_id", ""),
                        centro=asociacion.get("centro", ""),
                        anio=int(anio_bond),
                    )
                    if doc_existente:
                        doc_id_existente, doc_data_existente = doc_existente

                        periodos_previos   = doc_data_existente.get("periodos") or []
                        periodos_del_pdf   = datos.get("periodos") or []
                        periodos_fusionados = _merge_bond_periodos(periodos_previos, periodos_del_pdf)

                        total_resmas_anual = sum(p["total_resmas"] for p in periodos_fusionados)
                        peso_kg_anual      = round(total_resmas_anual * 2.33, 3)
                        peso_ton_anual     = round(peso_kg_anual / 1000, 6)

                        db.collection("facturas").document(doc_id_existente).update({
                            "periodos":             periodos_fusionados,
                            "total_resmas_anual":   total_resmas_anual,
                            "peso_papel_kg_anual":  peso_kg_anual,
                            "peso_papel_ton_anual": peso_ton_anual,
                            "filename":             filename,
                            "upload_date":          datetime.now().isoformat(),
                        })
                        # El resumen no cambia en merge: misma factura, mismos períodos acumulados.

                        meses_previos   = len(periodos_previos)
                        meses_en_pdf    = len(periodos_del_pdf)
                        meses_total     = len(periodos_fusionados)
                        meses_nuevos    = meses_total - meses_previos
                        print(
                            f"🔄 [BOND MERGE] Doc {doc_id_existente} actualizado: "
                            f"{meses_previos}→{meses_total} meses totales "
                            f"({meses_en_pdf} en el PDF, {meses_nuevos} mes(es) nuevo(s))"
                        )

                        resultados.append({
                            "filename":       filename,
                            "id":             doc_id_existente,
                            "zona_id":        asociacion["zona_id"],
                            "centro":         asociacion["centro"],
                            "categoria_id":   asociacion["categoria_id"],
                            "item":           asociacion["item"],
                            "datos_extraidos": {
                                **datos,
                                "periodos":             periodos_fusionados,
                                "total_resmas_anual":   total_resmas_anual,
                                "peso_papel_kg_anual":  peso_kg_anual,
                                "peso_papel_ton_anual": peso_ton_anual,
                            },
                            "status":         "merged",
                            "meses_previos":  meses_previos,
                            "meses_en_pdf":   meses_en_pdf,
                            "meses_totales":  meses_total,
                            "mensaje": (
                                f"Reporte fusionado con el año {anio_bond}: "
                                f"{meses_total} mes(es) en total"
                                + (f", {meses_nuevos} nuevo(s)" if meses_nuevos > 0 else " (sin meses nuevos)")
                            ),
                        })
                        continue  # Documento ya actualizado; no crear uno nuevo

            # ── Verificar duplicado normal (facturas con hash) ────────────────────
            if _verificar_duplicado(db, factura_numero, medidor, fecha_emision, user["uid"]):
                print(f"⚠️ [UPLOAD] Duplicado omitido: {filename}")
                duplicados.append({
                    "filename": filename,
                    "factura_numero": factura_numero,
                    "medidor": medidor,
                    "fecha_emision": fecha_emision,
                    "mensaje": "Factura ya existe en la base de datos",
                })
                continue

            doc_data = _datos_to_doc(
                datos=datos,
                filename=filename,
                uid=user["uid"],
                email=user.get("email", ""),
                asociacion=asociacion,
            )

            doc_ref = db.collection("facturas").add(doc_data)
            factura_id = doc_ref[1].id
            print(f"💾 [UPLOAD] Guardado: {filename} → ID {factura_id}")

            try:
                actualizar_resumen(db, user["uid"], doc_data, signo=1)
            except Exception as exc_res:
                print(f"⚠️ [RESUMEN] No se pudo actualizar resumen: {exc_res}")

            resultados.append({
                "filename": filename,
                "id": factura_id,
                "zona_id": asociacion["zona_id"],
                "centro": asociacion["centro"],
                "categoria_id": asociacion["categoria_id"],
                "item": asociacion["item"],
                "datos_extraidos": datos,
                "status": "success",
            })

        except Exception as exc:
            import traceback
            print(f"❌ [UPLOAD] Error en {filename}: {exc}\n{traceback.format_exc()}")
            errores.append({"filename": filename, "error": str(exc)})

    partes = []
    if resultados:
        partes.append(f"{len(resultados)} archivo(s) procesado(s) correctamente")
    if duplicados:
        partes.append(f"{len(duplicados)} duplicado(s) omitido(s)")
    if errores:
        partes.append(f"{len(errores)} error(es)")

    mensaje = ", ".join(partes) if partes else "No se procesaron archivos"
    print(f"✅ [UPLOAD] Resumen: {mensaje}")

    return {
        "message": mensaje,
        "total_archivos": len(files),
        "exitosos": len(resultados),
        "duplicados": len(duplicados),
        "errores": len(errores),
        "resultados": resultados,
        "duplicados_detalle": duplicados,
        "errores_detalle": errores,
    }


@router.post("/chat")
async def chat(request: ChatRequest, user: dict = Depends(get_current_user)):
    """Responde preguntas en lenguaje natural sobre las facturas del usuario."""
    mensaje = request.message.lower()
    respuesta = ""

    try:
        db = get_firestore_client()
        if not db:
            return {"response": "Lo siento, Firebase no está disponible en este entorno.", "query": request.message}
        year_filter, mes_filter, servicio_filter = detectar_filtros(mensaje)

        # ── Consultas por campo numérico específico ──────────────
        for keywords, (campo, label) in CHAT_CAMPO_MAP:
            if any(k in mensaje for k in keywords):
                facturas = _obtener_facturas_filtradas(
                    db, user["uid"], servicio_filter, year_filter, mes_filter
                )
                respuesta = _respuesta_campo(facturas, campo, label)
                break

        # ── Gasto total ──────────────────────────────────────────
        else:
            if any(k in mensaje for k in ("cuanto", "gasto", "total")):
                facturas = _obtener_facturas_filtradas(
                    db, user["uid"], servicio_filter, year_filter, mes_filter
                )
                total = sum(_monto_factura(f) for f in facturas)
                consumo = sum(_consumo_factura(f) for f in facturas)

                periodo = ""
                if mes_filter and year_filter:
                    mes_nombre = next(k for k, v in MESES.items() if v == mes_filter)
                    periodo = f" en {mes_nombre} de {year_filter}"
                elif year_filter:
                    periodo = f" en {year_filter}"
                elif mes_filter:
                    mes_nombre = next(k for k, v in MESES.items() if v == mes_filter)
                    periodo = f" en {mes_nombre}"

                servicio_txt = f" en {servicio_filter.lower()}" if servicio_filter else ""
                consumo_txt = ""
                if consumo > 0 and servicio_filter:
                    unidad = "kWh" if servicio_filter == "Electricidad" else "m³"
                    consumo_txt = f" con {consumo:.2f} {unidad} consumidos"

                respuesta = (
                    f"Se gastaron ${total:.2f} USD en {len(facturas)} factura(s)"
                    f"{servicio_txt}{periodo}{consumo_txt}."
                )

            # ── Medidores ────────────────────────────────────────
            elif "medidor" in mensaje:
                todas = _obtener_facturas_filtradas(db, user["uid"])
                medidores: dict[str, dict] = {}
                for f in todas:
                    med = f.get("medidor")
                    if med:
                        entry = medidores.setdefault(med, {"cantidad": 0, "total": 0.0})
                        entry["cantidad"] += 1
                        entry["total"] += _monto_factura(f)

                if medidores:
                    respuesta = f"Tienes {len(medidores)} medidores registrados:\n"
                    for med, data in list(medidores.items())[:5]:
                        respuesta += f"- {med}: {data['cantidad']} facturas, ${data['total']:.2f} USD\n"
                else:
                    respuesta = "No hay medidores registrados aún."

            # ── Resumen general ──────────────────────────────────
            else:
                todas = _obtener_facturas_filtradas(db, user["uid"])
                monto_total = sum(_monto_factura(f) for f in todas)
                respuesta = (
                    f"Tienes {len(todas)} facturas registradas con un total de "
                    f"${monto_total:.2f} USD. "
                    "Puedes preguntarme sobre gastos por mes, año, tipo de servicio o medidores."
                )

    except Exception:
        respuesta = "Lo siento, hubo un error procesando tu consulta. Intenta reformular la pregunta."

    return {"response": respuesta, "query": request.message}


@router.get("/stats")
def estadisticas(user: dict = Depends(get_current_user)):
    """Estadísticas generales del usuario."""
    try:
        db = get_firestore_client()
        if not db:
            # Devolver estadísticas vacías cuando Firebase no está disponible (desarrollo)
            return {
                "general": {
                    "total_facturas": 0,
                    "monto_total": 0.0,
                    "consumo_total_kwh": 0.0,
                    "consumo_total_m3": 0.0,
                },
                "por_servicio": [],
                "ultimas_facturas": [],
            }

        docs = db.collection("facturas").where(
            filter=FieldFilter("owner_uid", "==", user["uid"])
        ).stream()

        total_facturas = 0
        monto_total = 0.0
        consumo_kwh = 0.0
        consumo_m3 = 0.0
        por_servicio: dict[str, dict] = {}
        ultimas: list[dict] = []

        for doc in docs:
            data = doc.to_dict()
            total_facturas += 1
            monto_total += _monto_factura(data)

            consumo = _consumo_factura(data)
            unidad = data.get("unidad_consumo", "")
            servicio = data.get("tipo_servicio") or "Otro"

            if consumo > 0:
                if unidad in ("m³", "m3") or servicio == "Agua":
                    consumo_m3 += consumo
                else:
                    consumo_kwh += consumo

            entry = por_servicio.setdefault(servicio, {
                "tipo": servicio,
                "cantidad": 0,
                "monto_total": 0.0,
                "consumo_total": 0.0,
                "unidad_consumo": "m³" if servicio == "Agua" else "kWh" if servicio == "Electricidad" else "unidades",
            })
            entry["cantidad"] += 1
            entry["monto_total"] += _monto_factura(data)
            entry["consumo_total"] += consumo

            ultimas.append({
                "filename": data.get("filename"),
                "upload_date": data.get("upload_date"),
                "tipo_servicio": servicio,
                "total_usd": _monto_factura(data),
            })

        ultimas.sort(key=lambda x: x.get("upload_date") or "", reverse=True)

        return {
            "general": {
                "total_facturas": total_facturas,
                "monto_total": round(monto_total, 2),
                "consumo_total_kwh": round(consumo_kwh, 2),
                "consumo_total_m3": round(consumo_m3, 2),
            },
            "por_servicio": [
                {
                    "tipo": v["tipo"],
                    "cantidad": v["cantidad"],
                    "monto_total": round(v["monto_total"], 2),
                    "consumo_total": round(v["consumo_total"], 2),
                    "unidad_consumo": v["unidad_consumo"],
                }
                for v in por_servicio.values()
            ],
            "ultimas_facturas": ultimas[:5],
        }

    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Error al obtener estadísticas: {exc}"
        ) from exc


@router.get("/dashboard")
def dashboard(user: dict = Depends(get_current_user)):
    """
    Retorna el resumen pre-agregado del usuario para alimentar los dashboards.
    Costo: 1 lectura de Firestore, sin importar cuántas facturas existan.
    """
    db = get_firestore_client()
    if not db:
        return {"totales": {"total_facturas": 0, "monto_global": 0.0}, "inicializado": False}

    doc = db.collection("resumenes").document(user["uid"]).get()
    if not doc.exists:
        return {"totales": {"total_facturas": 0, "monto_global": 0.0}, "inicializado": False}

    return {**doc.to_dict(), "inicializado": True}


@router.post("/dashboard/reconstruir")
def reconstruir_dashboard(user: dict = Depends(get_current_user)):
    """
    Reconstruye el resumen leyendo todas las facturas del usuario.
    Usar solo si el resumen queda desincronizado. No llamar desde el dashboard normal.
    """
    from app.services.resumen_service import reconstruir_resumen

    db = get_firestore_client()
    if not db:
        raise HTTPException(status_code=503, detail="Firebase no disponible")

    resumen = reconstruir_resumen(db, user["uid"])
    return {
        "message": "Resumen reconstruido correctamente",
        "total_facturas": resumen.get("totales", {}).get("total_facturas", 0),
    }


@router.delete("/facturas/{factura_id}")
def eliminar_factura(factura_id: str, user: dict = Depends(get_current_user)):
    """Elimina una factura por ID, validando propiedad."""
    try:
        db = get_firestore_client()
        if not db:
            raise HTTPException(status_code=503, detail="Firebase no disponible en este entorno")

        doc_ref = db.collection("facturas").document(factura_id)
        doc = doc_ref.get()

        if not doc.exists:
            raise HTTPException(status_code=404, detail="Factura no encontrada")

        data = doc.to_dict() or {}

        # Validación estricta: el campo debe existir y coincidir
        if data.get("owner_uid") != user.get("uid"):
            raise HTTPException(status_code=403, detail="No autorizado para eliminar esta factura")

        doc_ref.delete()

        try:
            actualizar_resumen(db, user.get("uid"), data, signo=-1)
        except Exception as exc_res:
            print(f"⚠️ [RESUMEN] No se pudo actualizar resumen tras delete: {exc_res}")

        return {"message": "Factura eliminada correctamente", "id": factura_id}

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Error al eliminar factura: {exc}"
        ) from exc


# ══════════════════════════════════════════════════════════════
# Configuración de precios de combustible (Categoría 1)
# ══════════════════════════════════════════════════════════════

class PreciosCombustibleRequest(BaseModel):
    diesel: float
    gasolina_ecopais: float
    gasolina_movil: float


@router.get("/config/precios-combustible")
def get_precios_combustible(user: dict = Depends(get_current_user)):
    """Retorna los precios actuales de combustible (USD/galón)."""
    db = get_firestore_client()
    if not db:
        from app.services.extractors.category1 import PRECIOS_COMBUSTIBLE_DEFAULT
        return dict(PRECIOS_COMBUSTIBLE_DEFAULT)
    return _obtener_precios_combustible(db)


@router.put("/config/precios-combustible")
def update_precios_combustible(
    request: PreciosCombustibleRequest,
    user: dict = Depends(get_current_user),
):
    """Actualiza los precios de combustible. Los nuevos reportes usarán estos valores."""
    db = get_firestore_client()
    if not db:
        raise HTTPException(status_code=503, detail="Firebase no disponible")

    data = {
        "diesel": request.diesel,
        "gasolina_ecopais": request.gasolina_ecopais,
        "gasolina_movil": request.gasolina_movil,
        "updated_at": datetime.now().isoformat(),
        "updated_by": user.get("email", ""),
    }
    db.collection("config").document("precios_combustible").set(data)
    print(f"⛽ [PRECIOS] Actualizados por {user.get('email')}: {data}")
    return {"message": "Precios de combustible actualizados correctamente", **data}