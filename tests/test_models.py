import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("WATCHLIST_ENCRYPTION_KEY", "Gz3n5J9y8k2p6xQm1wZ7fL0oR4sT8vU2cA6bD9eH3iM=")

from datetime import timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import DetectionLog


def _session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_detected_at_round_trips_as_timezone_aware_utc():
    # Gercek olay: SQLite, DateTime(timezone=True) ile bile tzinfo'yu
    # saklamiyor - okurken naive bir datetime donuyordu. Bu da API
    # yanitlarinda saatin "UTC oldugu belirtilmeden" serilize edilmesine
    # (sonunda 'Z'/ofset olmadan) yol aciyordu; tarayici bunu YEREL saat
    # sanip hic donusturmuyor, kullaniciya log saatleri Turkiye saatinden
    # 3 saat geri gorunuyordu ("saat yanlis" sikayeti). UTCDateTime bu
    # gap'i okurken kapatir.
    db = _session()
    log = DetectionLog(camera_id=1, plate_encrypted="x", plate_hash="y", confidence=0.5, snapshot_path="")
    db.add(log)
    db.commit()
    db.refresh(log)

    assert log.detected_at.tzinfo is not None
    assert log.detected_at.utcoffset().total_seconds() == 0
    assert log.detected_at.isoformat().endswith("+00:00")
