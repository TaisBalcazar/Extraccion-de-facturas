import os
from pathlib import Path
from dataclasses import dataclass


@dataclass
class Settings:
    app_env: str = os.getenv("APP_ENV", "development")
    allowed_origins_raw: str = os.getenv("ALLOWED_ORIGINS", "http://localhost:4200")
    firebase_credentials_path_raw: str = os.getenv("FIREBASE_CREDENTIALS_PATH", "")
    
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
    def project_root(self) -> Path:
        return Path(__file__).resolve().parents[3]

    @property
    def firebase_credentials_path(self) -> Path | None:
        candidates = []

        if self.firebase_credentials_path_raw:
            candidates.append(Path(self.firebase_credentials_path_raw))

        candidates.extend(
            [
                self.project_root / "firebase-config.json",
                self.project_root / "utpl-sostenible-firebase-adminsdk-fbsvc-7a7506e60e.json",
                self.project_root / "backend" / "firebase-config.json",
            ]
        )

        for candidate in candidates:
            if candidate.exists():
                return candidate

        return None
    
    @property
    def firebase_credentials_dict(self) -> dict:
        """Construir diccionario de credenciales de Firebase desde variables de entorno."""
        return {
            "type": "service_account",
            "project_id": self.firebase_project_id,
            "private_key_id": self.firebase_private_key_id,
            "private_key": self.firebase_private_key.replace(r"\n", "\n"),
            "client_email": self.firebase_client_email,
            "client_id": self.firebase_client_id,
            "auth_uri": self.firebase_auth_uri,
            "token_uri": self.firebase_token_uri,
            "auth_provider_x509_cert_url": self.firebase_auth_provider_x509_cert_url,
            "client_x509_cert_url": self.firebase_client_x509_cert_url,
        }


settings = Settings()
