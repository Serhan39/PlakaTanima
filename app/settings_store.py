"""Calisirken (yeniden dagitim gerektirmeden) panelden degistirilebilen
basit anahtar-deger ayarlar. Bir anahtar veritabaninda yoksa .env'deki
varsayilan deger kullanilir."""

from sqlalchemy.orm import Session

from app.models import AppSetting


def get_setting(db: Session, key: str, default: str) -> str:
    row = db.get(AppSetting, key)
    return row.value if row else default


def set_setting(db: Session, key: str, value: str) -> None:
    row = db.get(AppSetting, key)
    if row:
        row.value = value
    else:
        db.add(AppSetting(key=key, value=value))
    db.commit()
