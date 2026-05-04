from datetime import datetime
import asyncio
import hashlib
import io
import re
import unicodedata
from typing import Optional, Tuple

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from google.cloud.firestore_v1.base_query import FieldFilter
import pdfplumber

from app.core.firebase import get_firestore_client
from app.core.security import get_current_user
from app.services.chat_logic import MESES, detectar_filtros
from app.services.factura_extractor import extraer_datos_factura
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
    # Categoría 5
    "periodos", "horas_trabajadas_bimestre1", "horas_trabajadas_bimestre2",
]

# Campos exactos permitidos por categoría (sin relleno con null).
_CATEGORY_ALLOWED_FIELDS = {
    "cat-1": {
        "factura_numero",
        "precio_unitario",
        "cantidad",
        "iva",
        "total",
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

# Razón social permitida para evidencias de huella de carbono.
RAZON_SOCIAL_REQUERIDA = "UNIVERSIDAD TECNICA PARTICULAR DE LOJA"


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

    razon_detectada = _extraer_razon_social_desde_texto(texto_pdf)
    texto_normalizado = _normalizar_texto(texto_pdf)
    razon_requerida_norm = _normalizar_texto(RAZON_SOCIAL_REQUERIDA)

    if razon_detectada:
        razon_detectada_norm = _normalizar_texto(razon_detectada)
        if razon_requerida_norm in razon_detectada_norm:
            return True, razon_detectada, ""
        return (
            False,
            razon_detectada,
            f"La razón social no es la Universidad Técnica Particular de Loja (UTPL). Se detectó: '{razon_detectada}'.",
        )

    # Fallback: algunos PDFs no etiquetan explícitamente "Razón Social".
    if razon_requerida_norm in texto_normalizado:
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
        facturas = _obtener_facturas_filtradas(
            db, user["uid"], tipo_servicio=tipo_servicio, year=year
        )

        # medidor no tiene índice dedicado: filtro local barato
        if medidor:
            facturas = [f for f in facturas if f.get("medidor") == medidor]

        # Serializar con FACTURA_FIELDS y ordenar
        result = [_doc_to_dict(f.get("__id__", ""), f) for f in facturas]
        result.sort(key=lambda x: str(x.get("fecha_emision") or ""), reverse=True)
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
    asociacion = _validar_asociacion_factura(db, zona_id, categoria_id, item, centro)

    print(f"[UPLOAD] Usuario: {user.get('email')} | Archivos: {len(files)}")

    resultados, errores, duplicados = [], [], []

    for file in files:
        filename = file.filename or ""
        print(f"📄 [UPLOAD] Procesando: {filename}")

        if not filename.lower().endswith(".pdf"):
            errores.append({"filename": filename, "error": "Solo se aceptan archivos PDF"})
            continue

        try:
            content = await file.read()
            print(f"📥 [UPLOAD] {filename} — {len(content)} bytes")

            # OPTIMIZACIÓN: Usar PDFExtractor para evitar lectura duplicada
            pdf_extractor = PDFExtractor(content, filename)
            try:
                es_razon_social_valida, razon_social_detectada, alerta_razon_social = _validar_razon_social_desde_extractor(pdf_extractor)
            finally:
                pdf_extractor.close()
            if not es_razon_social_valida:
                print(f"🚫 [UPLOAD] Rechazada por razón social: {filename} | {alerta_razon_social}")
                errores.append({
                    "filename": filename,
                    "error": alerta_razon_social,
                    "razon_social_detectada": razon_social_detectada,
                    "tipo_alerta": "razon_social_invalida",
                })
                continue

            # Pasar la categoría_id al extractor para que use el extractor específico
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


@router.delete("/facturas/{factura_id}")
def eliminar_factura(factura_id: str, user: dict = Depends(get_current_user)):
    """Elimina una factura por ID, validando propiedad."""
    try:
        db = get_firestore_client()
        doc_ref = db.collection("facturas").document(factura_id)
        doc = doc_ref.get()

        if not doc.exists:
            raise HTTPException(status_code=404, detail="Factura no encontrada")

        data = doc.to_dict() or {}

        # Validación estricta: el campo debe existir y coincidir
        if data.get("owner_uid") != user.get("uid"):
            raise HTTPException(status_code=403, detail="No autorizado para eliminar esta factura")

        doc_ref.delete()
        return {"message": "Factura eliminada correctamente", "id": factura_id}

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Error al eliminar factura: {exc}"
        ) from exc