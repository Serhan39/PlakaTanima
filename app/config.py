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
    # Kutu (plaka BULMA) guveni icin esik yukaridaki degerle ayni kalir.
    # Ancak nihai kutu+OCR ORTALAMA guveni, farkli bir olcekte calisir:
    # gercek kamera goruntusunde Tesseract'in OCR guveni dogru okumalarda
    # bile genelde dusuk kalir (orn. dogru "07 BAF 140" okumasi bile ~%40
    # kombine guvenle geldi) - bu yuzden ayni %50 esigini kombine skora
    # uygulamak DOGRU okumalari da eleyip hicbir sonuc gostermeyebilir.
    # Bu yuzden nihai filtre icin ayri, daha dusuk bir esik kullanilir.
    min_plate_read_confidence: float = 0.3
    company_name: str = "Sertek Bilisim"
    ocr_engine: str = "tesseract"
    # Turkiye plakalarinin sol ucunda fiziksel olarak bulunan mavi "TR"/AB
    # bandi, tespit kutusu plakanin tamamini kapsadiginda OCR'a karisip
    # gercek plaka metninin BASINA rastgele/hatali karakterler ekleniyor
    # (gercek olay: "07 MYS 57" -> "97MYS57", "402HYS57", "40ZAYS57" gibi
    # okumalar - hepsinde sondaki "MYS57"/"YS57" nispeten sabit ama baştaki
    # "07" her seferinde farkli sekilde bozuluyordu). Bu yuzden OCR'a
    # vermeden once kirpmanin sol tarafindan bu oranda bir pay kesiliyor.
    # Sadece plaka okumada uygulanir (read_equipment_code'da degil - is
    # makinesi etiketlerinde bu bant yok).
    plate_crop_left_trim_fraction: float = 0.12

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_use_tls: bool = True

    alert_categories: str = "wanted,blacklist"
    alert_to: str = ""

    daily_report_to: str = ""
    daily_report_hour: int = 8

    parking_capacity: int = 50

    equipment_crossing_debounce_seconds: int = 30
    equipment_min_code_length: int = 3


@lru_cache
def get_settings() -> Settings:
    return Settings()
