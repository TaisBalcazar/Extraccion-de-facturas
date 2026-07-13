import json
import os
import firebase_admin
from firebase_admin import credentials, firestore

from app.core.config import settings

_firebase_initialized = False  # ← declarar globalmente


def _load_and_fix_service_account(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    pk = data.get("private_key")
    if isinstance(pk, str) and "\\n" in pk:
        data["private_key"] = pk.replace("\\n", "\n")
    return data


def _fix_dict_private_key(d: dict) -> dict:
    pk = d.get("private_key")
    if isinstance(pk, str) and "\\n" in pk:
        d = dict(d)
        d["private_key"] = pk.replace("\\n", "\n")
    return d


def init_firebase() -> None:
    global _firebase_initialized

    if firebase_admin._apps:
        _firebase_initialized = True
        return

    credentials_path = settings.firebase_credentials_path
    try:
        if credentials_path and os.path.exists(str(credentials_path)):
            print(f"Cargando credenciales desde archivo: {credentials_path}")
            sa = _load_and_fix_service_account(str(credentials_path))
            cred = credentials.Certificate(sa)
        else:
            print("Cargando credenciales desde variables de entorno...")
            creds_dict = settings.firebase_credentials_dict
            if isinstance(creds_dict, dict) and creds_dict.get("client_email"):
                creds_dict = _fix_dict_private_key(creds_dict)
                cred = credentials.Certificate(creds_dict)
            else:
                raise ValueError("No valid Firebase credentials configured")

        firebase_admin.initialize_app(cred)
        _firebase_initialized = True
        print("Firebase inicializado correctamente")

    except Exception as exc:
        if getattr(settings, "app_env", "development") == "development":
            print(f"No se pudo inicializar Firebase (modo development): {exc}")
            return
        raise


def get_firestore_client():
    init_firebase()
    if not _firebase_initialized:
        return None
    return firestore.client()