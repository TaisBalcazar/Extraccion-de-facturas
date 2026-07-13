from fastapi import Header, HTTPException
from firebase_admin import auth

from app.core.firebase import get_firestore_client, init_firebase


def get_current_user(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token no enviado")

    token = authorization.replace("Bearer ", "", 1).strip()
    if not token:
        raise HTTPException(status_code=401, detail="Token vacio")

    try:
        init_firebase()
        decoded = auth.verify_id_token(token)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Token invalido") from exc

    uid = decoded.get("uid")
    email = decoded.get("email")
    role = "user"

    try:
        db = get_firestore_client()
        if db is not None:
            doc = db.collection("users").document(uid).get()
            if doc.exists:
                role = (doc.to_dict() or {}).get("role") or "user"
    except Exception as exc:
        print(f"[AUTH] No se pudo leer el rol de users/{uid}, usando 'user' por defecto: {exc}")

    return {"uid": uid, "email": email, "role": role}
