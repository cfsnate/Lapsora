"""Application configuration and encryption helpers."""

import base64
import hashlib
import secrets

from cryptography.fernet import Fernet
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LAPSORA_", env_file=".env")

    SECRET_KEY: str = ""
    DATA_DIR: str = "data"
    DATABASE_URL: str = "sqlite:///data/lapsora.db"
    JWT_EXPIRY_HOURS: int = 24
    JWT_ALGORITHM: str = "HS256"

    # TLS / ACME settings
    TLS_ENABLED: bool = False
    TLS_CERT_DIR: str = ""  # defaults to DATA_DIR/certs at runtime
    ACME_DIRECTORY_URL: str = "https://acme-v02.api.letsencrypt.org/directory"
    ACME_EMAIL: str = ""
    ACME_CA_BUNDLE: str = ""  # Path to CA bundle PEM for internal ACME servers
    TLS_DOMAIN: str = ""

    def model_post_init(self, __context: object) -> None:
        if not self.SECRET_KEY:
            import logging
            logging.getLogger(__name__).warning(
                "LAPSORA_SECRET_KEY not set — using random key. "
                "Encrypted data will be unreadable after restart."
            )
            self.SECRET_KEY = secrets.token_hex(32)


settings = Settings()


def _derive_fernet_key(secret: str) -> bytes:
    """Derive a Fernet-compatible key from the SECRET_KEY via SHA-256 + base64."""
    digest = hashlib.sha256(secret.encode()).digest()
    return base64.urlsafe_b64encode(digest)


def encrypt(plaintext: str) -> str:
    """Encrypt a string and return the Fernet token as a string."""
    f = Fernet(_derive_fernet_key(settings.SECRET_KEY))
    return f.encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    """Decrypt a Fernet token string back to plaintext."""
    f = Fernet(_derive_fernet_key(settings.SECRET_KEY))
    return f.decrypt(token.encode()).decode()
