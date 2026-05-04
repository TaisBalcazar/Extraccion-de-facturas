from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from google.cloud.firestore import ArrayUnion, ArrayRemove

from app.core.firebase import get_firestore_client
from app.core.security import get_current_user

router = APIRouter()


# =========================
# Helpers
# =========================
def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _doc_id(prefix: str, numero: int | None) -> str | None:
    if numero is None:
        return None
    return f"{prefix}-{numero}"


# =========================
# Models
# =========================
class ZonaIn(BaseModel):
    numero: int | None = Field(default=None, ge=1)
    nombre: str = Field(min_length=1)
    centros: list[str] = Field(default_factory=list)


class CategoriaIn(BaseModel):
    numero: int | None = Field(default=None, ge=1)
    nombre: str = Field(min_length=1)
    items: list[str] = Field(default_factory=list)


class CentrosPatch(BaseModel):
    centros: list[str] = Field(min_length=1)


class ItemsPatch(BaseModel):
    items: list[str] = Field(min_length=1)


# =========================
# Utils protección
# =========================
def _check_system_doc(snap):
    data = snap.to_dict() or {}
    if data.get("is_system"):
        raise HTTPException(status_code=403, detail="No se puede modificar catálogo base")


def _require_admin(user: dict):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Solo admin puede modificar")


# =========================
# Catalogos
# =========================
@router.get("/catalogos")
def get_catalogos(user: dict = Depends(get_current_user)) -> dict:
    db = get_firestore_client()

    zonas_docs = db.collection("zonas").stream()
    categorias_docs = db.collection("categorias").stream()

    zonas = [{"id": d.id, **(d.to_dict() or {})} for d in zonas_docs]
    categorias = [{"id": d.id, **(d.to_dict() or {})} for d in categorias_docs]

    zonas.sort(key=lambda z: (z.get("numero") is None, z.get("numero") or 0, str(z.get("nombre") or "")))
    categorias.sort(key=lambda c: (c.get("numero") is None, c.get("numero") or 0, str(c.get("nombre") or "")))

    return {"zonas": zonas, "categorias": categorias}


# =========================
# ZONAS
# =========================
@router.get("/zonas")
def list_zonas(user: dict = Depends(get_current_user)) -> list[dict]:
    db = get_firestore_client()
    docs = db.collection("zonas").stream()

    zonas = [{"id": d.id, **(d.to_dict() or {})} for d in docs]
    zonas.sort(key=lambda z: (z.get("numero") is None, z.get("numero") or 0, str(z.get("nombre") or "")))

    return zonas


@router.put("/zonas/{zona_id}")
def update_zona(zona_id: str, payload: ZonaIn, user: dict = Depends(get_current_user)) -> dict:
    db = get_firestore_client()
    ref = db.collection("zonas").document(zona_id)
    snap = ref.get()

    if not snap.exists:
        raise HTTPException(status_code=404, detail="Zona no encontrada")

    _check_system_doc(snap)

    now = _utc_now_iso()
    ref.set({
        **payload.model_dump(),
        "updated_at": now,
        "updated_by_uid": user.get("uid"),
    }, merge=True)

    return {"id": zona_id, **payload.model_dump()}


@router.post("/zonas/{zona_id}/centros")
def add_centros(zona_id: str, payload: CentrosPatch, user: dict = Depends(get_current_user)) -> dict:
    _require_admin(user)

    db = get_firestore_client()
    ref = db.collection("zonas").document(zona_id)
    snap = ref.get()

    if not snap.exists:
        raise HTTPException(status_code=404, detail="Zona no encontrada")

    now = _utc_now_iso()
    ref.update({
        "centros": ArrayUnion(payload.centros),
        "updated_at": now,
        "updated_by_uid": user.get("uid"),
    })

    return {"message": "Centros agregados", "id": zona_id}


@router.delete("/zonas/{zona_id}/centros")
def remove_centros(zona_id: str, payload: CentrosPatch, user: dict = Depends(get_current_user)) -> dict:
    _require_admin(user)

    db = get_firestore_client()
    ref = db.collection("zonas").document(zona_id)
    snap = ref.get()

    if not snap.exists:
        raise HTTPException(status_code=404, detail="Zona no encontrada")

    now = _utc_now_iso()
    ref.update({
        "centros": ArrayRemove(payload.centros),
        "updated_at": now,
        "updated_by_uid": user.get("uid"),
    })

    return {"message": "Centros eliminados", "id": zona_id}


# =========================
# CATEGORIAS
# =========================
@router.get("/categorias")
def list_categorias(user: dict = Depends(get_current_user)) -> list[dict]:
    db = get_firestore_client()
    docs = db.collection("categorias").stream()

    categorias = [{"id": d.id, **(d.to_dict() or {})} for d in docs]
    categorias.sort(key=lambda c: (c.get("numero") is None, c.get("numero") or 0, str(c.get("nombre") or "")))

    return categorias


@router.put("/categorias/{categoria_id}")
def update_categoria(categoria_id: str, payload: CategoriaIn, user: dict = Depends(get_current_user)) -> dict:
    db = get_firestore_client()
    ref = db.collection("categorias").document(categoria_id)
    snap = ref.get()

    if not snap.exists:
        raise HTTPException(status_code=404, detail="Categoría no encontrada")

    _check_system_doc(snap)

    now = _utc_now_iso()
    ref.set({
        **payload.model_dump(),
        "updated_at": now,
        "updated_by_uid": user.get("uid"),
    }, merge=True)

    return {"id": categoria_id, **payload.model_dump()}


@router.post("/categorias/{categoria_id}/items")
def add_items(categoria_id: str, payload: ItemsPatch, user: dict = Depends(get_current_user)) -> dict:
    _require_admin(user)

    db = get_firestore_client()
    ref = db.collection("categorias").document(categoria_id)
    snap = ref.get()

    if not snap.exists:
        raise HTTPException(status_code=404, detail="Categoría no encontrada")

    now = _utc_now_iso()
    ref.update({
        "items": ArrayUnion(payload.items),
        "updated_at": now,
        "updated_by_uid": user.get("uid"),
    })

    return {"message": "Items agregados", "id": categoria_id}


@router.delete("/categorias/{categoria_id}/items")
def remove_items(categoria_id: str, payload: ItemsPatch, user: dict = Depends(get_current_user)) -> dict:
    _require_admin(user)

    db = get_firestore_client()
    ref = db.collection("categorias").document(categoria_id)
    snap = ref.get()

    if not snap.exists:
        raise HTTPException(status_code=404, detail="Categoría no encontrada")

    now = _utc_now_iso()
    ref.update({
        "items": ArrayRemove(payload.items),
        "updated_at": now,
        "updated_by_uid": user.get("uid"),
    })

    return {"message": "Items eliminados", "id": categoria_id}