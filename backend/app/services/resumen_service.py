"""
Servicio de resumen pre-agregado por usuario.

Mantiene un documento /resumenes/{owner_uid} con totales por categoría,
año y mes. El dashboard lee ese único documento (1 lectura de Firestore)
en lugar de iterar todas las facturas.

Estructura del documento:
{
  "totales": { "total_facturas": N, "monto_global": X, "ultima_actualizacion": "..." },
  "cat-1": {
    "por_año": {
      "2024": {
        "count": 12, "monto_total": 1245.5, "cantidad_total": 580.3,
        "por_mes": { "1": { "count": 1, "monto": 100.5, "cantidad": 45.2 }, ... }
      }
    }
  },
  "cat-2": {
    "por_año": {
      "2024": {
        "count": 36, "consumo_kwh_total": 15234.5, "valor_total": 4567.89,
        "por_mes": { "1": { "count": 3, "consumo_kwh": 1234.5, "valor_total": 456.78 }, ... }
      }
    }
  },
  "cat-3": {
    "por_año": {
      "2024": {
        "count": 48, "km_total_total": 62000.0,
        "km_nacional_total": 12000.0, "km_internacional_total": 50000.0,
        "vuelos_total": 48.0,
        "por_mes": { "1": { "count": 4, "km_total": 5200.0, ... }, ... }
      }
    }
  },
  ...
}
"""

from datetime import datetime
from typing import Optional
from google.cloud.firestore_v1 import Client
from google.cloud.firestore_v1.transforms import Increment


def _extraer_año_mes(datos: dict) -> tuple[Optional[int], Optional[int]]:
    """Extrae año y mes de un documento de factura."""
    anio = datos.get("year")
    mes = datos.get("mes_numero")
    if anio and mes:
        return int(anio), int(mes)

    # Parsear desde fecha_emision o periodo_inicio
    fecha = datos.get("fecha_emision") or datos.get("periodo_inicio") or ""
    if not fecha:
        return None, None

    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            dt = datetime.strptime(str(fecha)[:10], fmt)
            return dt.year, dt.month
        except ValueError:
            continue

    if len(str(fecha)) >= 4 and str(fecha)[:4].isdigit():
        return int(str(fecha)[:4]), None

    return None, None


def _campos_por_categoria(categoria_id: str, datos: dict) -> dict:
    """Devuelve los campos numéricos relevantes para el dashboard según la categoría."""
    if categoria_id == "cat-1":
        return {
            "monto": float(datos.get("total") or datos.get("total_usd") or 0),
            "cantidad": float(datos.get("cantidad") or 0),
        }
    if categoria_id == "cat-2":
        return {
            "consumo_kwh": float(
                datos.get("consumo_kwh") or datos.get("consumo_total") or 0
            ),
            "valor_total": float(
                datos.get("valor_total") or datos.get("total_sec_elec") or 0
            ),
        }
    if categoria_id == "cat-3":
        km = float(datos.get("km_total") or 0)
        es_nacional = str(datos.get("tipo_vuelo") or "").lower() == "nacional"
        return {
            "km_total": km,
            "km_nacional": km if es_nacional else 0.0,
            "km_internacional": 0.0 if es_nacional else km,
            "vuelos": float(datos.get("cantidad_viajes") or 0),
        }
    if categoria_id == "cat-4":
        return {
            "agua_m3": float(
                datos.get("consumo_agua") or datos.get("consumo_m3") or 0
            ),
            "monto": float(
                datos.get("total_usd") or datos.get("total_facturado") or 0
            ),
            "total_resmas": float(datos.get("total_resmas_anual") or 0),
            "peso_papel_kg": float(datos.get("peso_papel_kg_anual") or 0),
            "peso_papel_ton": float(datos.get("peso_papel_ton_anual") or 0),
        }
    if categoria_id == "cat-5":
        return {
            "horas_b1": float(datos.get("horas_trabajadas_bimestre1") or 0),
            "horas_b2": float(datos.get("horas_trabajadas_bimestre2") or 0),
        }
    return {}


def _monto_global(datos: dict) -> float:
    return float(
        datos.get("total_usd")
        or datos.get("total")
        or datos.get("valor_total")
        or datos.get("total_sec_elec")
        or 0
    )


def actualizar_resumen(db: Client, owner_uid: str, datos: dict, signo: int = 1) -> None:
    """
    Actualiza el documento de resumen de forma incremental.

    signo=1  → sumar  (llamar tras upload exitoso)
    signo=-1 → restar (llamar antes de delete, con los datos de la factura a eliminar)
    """
    categoria_id = datos.get("categoria_id")
    if not categoria_id:
        return

    anio, mes = _extraer_año_mes(datos)
    if not anio:
        return

    campos = _campos_por_categoria(categoria_id, datos)
    monto = _monto_global(datos)

    año_key = str(anio)
    update: dict = {
        "totales.total_facturas": Increment(signo),
        "totales.monto_global": Increment(signo * monto),
        "totales.ultima_actualizacion": datetime.now().isoformat(),
        f"{categoria_id}.por_año.{año_key}.count": Increment(signo),
    }

    for campo, valor in campos.items():
        update[f"{categoria_id}.por_año.{año_key}.{campo}_total"] = Increment(
            signo * valor
        )

    if mes:
        mes_key = str(mes)
        update[f"{categoria_id}.por_año.{año_key}.por_mes.{mes_key}.count"] = Increment(
            signo
        )
        for campo, valor in campos.items():
            update[
                f"{categoria_id}.por_año.{año_key}.por_mes.{mes_key}.{campo}"
            ] = Increment(signo * valor)

    db.collection("resumenes").document(owner_uid).set(update, merge=True)


def reconstruir_resumen(db: Client, owner_uid: str) -> dict:
    """
    Reconstruye el resumen desde cero leyendo todas las facturas del usuario.
    Usar solo para backfill inicial o si el resumen queda inconsistente.
    """
    from google.cloud.firestore_v1.base_query import FieldFilter

    docs = list(
        db.collection("facturas")
        .where(filter=FieldFilter("owner_uid", "==", owner_uid))
        .stream()
    )

    resumen: dict = {
        "totales": {
            "total_facturas": 0,
            "monto_global": 0.0,
            "ultima_actualizacion": datetime.now().isoformat(),
        }
    }

    for doc in docs:
        datos = doc.to_dict() or {}
        categoria_id = datos.get("categoria_id")
        if not categoria_id:
            continue

        anio, mes = _extraer_año_mes(datos)
        if not anio:
            continue

        campos = _campos_por_categoria(categoria_id, datos)
        monto = _monto_global(datos)

        resumen["totales"]["total_facturas"] += 1
        resumen["totales"]["monto_global"] = round(
            resumen["totales"]["monto_global"] + monto, 4
        )

        cat = resumen.setdefault(categoria_id, {"por_año": {}})
        año_data = cat["por_año"].setdefault(
            str(anio), {"count": 0, "por_mes": {}}
        )
        año_data["count"] += 1

        for campo, valor in campos.items():
            key = f"{campo}_total"
            año_data[key] = round(año_data.get(key, 0.0) + valor, 4)

        if mes:
            mes_data = año_data["por_mes"].setdefault(str(mes), {"count": 0})
            mes_data["count"] += 1
            for campo, valor in campos.items():
                mes_data[campo] = round(mes_data.get(campo, 0.0) + valor, 4)

    db.collection("resumenes").document(owner_uid).set(resumen)
    return resumen
