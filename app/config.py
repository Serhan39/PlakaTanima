from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite:///./sertek_alpr.db"
    jwt_secret_key: str = "insecure-dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 480
    watchlist_encryption_key: str = ""
    plate_detector_model_path: str = "models/plate_detector.onnx"
    detection_confidence_threshold: float = 0.5
    company_name: str = "Sertek Bilisim"


@lru_cache
def get_settings() -> Settings:
    return Settings()
