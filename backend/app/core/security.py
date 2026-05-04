from fastapi import Header, HTTPException
from firebase_admin import auth

from app.core.firebase import init_firebase


def get_current_user(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token no enviado")

    token = authorization.replace("Bearer ", "", 1).strip()
    if not token:
        raise HTTPException(status_code=401, detail="Token vacio")

    try:
        init_firebase()
        decoded = auth.verify_id_token(token)
        return {"uid": decoded.get("uid"), "email": decoded.get("email")}
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Token invalido") from exc
