import base64
import hashlib
import hmac

from cryptography.fernet import Fernet

from app.config import get_settings


def _fernet() -> Fernet:
    settings = get_settings()
    key = settings.watchlist_encryption_key
    if not key:
        raise RuntimeError(
            "WATCHLIST_ENCRYPTION_KEY is not set. Generate one with "
            "`python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"`"
        )
    return Fernet(key.encode())


def encrypt_text(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt_text(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()


def deterministic_hash(value: str) -> str:
    settings = get_settings()
    digest = hmac.new(settings.jwt_secret_key.encode(), value.upper().encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode()
