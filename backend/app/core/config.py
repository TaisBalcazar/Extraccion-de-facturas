import os
from pathlib import Path
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()  # ← carga el .env ANTES de os.getenv()


@dataclass
class Settings:
    app_env: str = os.getenv("APP_ENV", "development")
    allowed_origins_raw: str = os.getenv("ALLOWED_ORIGINS", "http://localhost:4200")
    firebase_credentials_path_raw: str = os.getenv("FIREBASE_CREDENTIALS_PATH", "")

    # Despliegue temporal Producto 1 (CarbonTrack UTPL): restringe qué categorías
    # devuelve GET /categorias. Vacío (default) = sin restricción, se devuelven todas.
    # Ej: ENABLED_CATEGORIES=cat-2,cat-4
    enabled_categories_raw: str = os.getenv("ENABLED_CATEGORIES", "")

    # Despliegue temporal Producto 1: EERSSA (cat-2) y Municipio de Loja (cat-4)
    # emiten PDFs digitales, no escaneados — el fallback OCR (easyocr/cv2/torch)
    # no es necesario y consume mucha memoria. Default false para no romper el
    # entorno local de desarrollo. Ej: DISABLE_OCR=true
    disable_ocr_raw: str = os.getenv("DISABLE_OCR", "false")

    # Firebase credentials from environment variables
    firebase_project_id: str = os.getenv("FIREBASE_PROJECT_ID", "")
    firebase_private_key_id: str = os.getenv("FIREBASE_PRIVATE_KEY_ID", "")
    firebase_private_key: str = os.getenv("FIREBASE_PRIVATE_KEY", "")
    firebase_client_email: str = os.getenv("FIREBASE_CLIENT_EMAIL", "")
    firebase_client_id: str = os.getenv("FIREBASE_CLIENT_ID", "")
    firebase_auth_uri: str = os.getenv("FIREBASE_AUTH_URI", "https://accounts.google.com/o/oauth2/auth")
    firebase_token_uri: str = os.getenv("FIREBASE_TOKEN_URI", "https://oauth2.googleapis.com/token")
    firebase_auth_provider_x509_cert_url: str = os.getenv("FIREBASE_AUTH_PROVIDER_X509_CERT_URL", "https://www.googleapis.com/oauth2/v1/certs")
    firebase_client_x509_cert_url: str = os.getenv("FIREBASE_CLIENT_X509_CERT_URL", "")

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins_raw.split(",") if origin.strip()]

    @property
    def enabled_categories(self) -> list[str]:
        return [cat.strip() for cat in self.enabled_categories_raw.split(",") if cat.strip()]

    @property
    def disable_ocr(self) -> bool:
        return self.disable_ocr_raw.strip().lower() in ("1", "true", "yes", "on")

    @property
    def project_root(self) -> Path:
        return Path(__file__).resolve().parents[3]

    @property
    def firebase_credentials_path(self) -> Path | None:
        candidates = []

        if self.firebase_credentials_path_raw:
            # Soportar rutas absolutas y relativas
            p = Path(self.firebase_credentials_path_raw)
            candidates.append(p)

        candidates.extend([
            self.project_root / "firebase-config.json",
            self.project_root / "backend" / "firebase-config.json",
        ])

        for candidate in candidates:
            if candidate.exists():
                print(f"Credenciales Firebase encontradas: {candidate}")
                return candidate

        print(f"No se encontró archivo de credenciales. Path configurado: '{self.firebase_credentials_path_raw}'")
        return None

    @property
    def firebase_credentials_dict(self) -> dict:
        return {
            "type": "service_account",
            "project_id": self.firebase_project_id,
            "private_key_id": self.firebase_private_key_id,
            "private_key": self.firebase_private_key.replace("\\n", "\n"),
            "client_email": self.firebase_client_email,
            "client_id": self.firebase_client_id,
            "auth_uri": self.firebase_auth_uri,
            "token_uri": self.firebase_token_uri,
            "auth_provider_x509_cert_url": self.firebase_auth_provider_x509_cert_url,
            "client_x509_cert_url": self.firebase_client_x509_cert_url,
        }


settings = Settings()