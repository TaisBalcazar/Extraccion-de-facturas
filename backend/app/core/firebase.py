import firebase_admin
from firebase_admin import credentials, firestore

from app.core.config import settings


def init_firebase() -> None:
    if firebase_admin._apps:
        return

    credentials_path = settings.firebase_credentials_path
    if credentials_path:
        cred = credentials.Certificate(str(credentials_path))
    else:
        cred = credentials.Certificate(settings.firebase_credentials_dict)

    firebase_admin.initialize_app(cred)


def get_firestore_client():
    init_firebase()
    return firestore.client()
