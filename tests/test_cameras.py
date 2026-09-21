import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("WATCHLIST_ENCRYPTION_KEY", "Gz3n5J9y8k2p6xQm1wZ7fL0oR4sT8vU2cA6bD9eH3iM=")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.live_frame_cache import set_frame
from app.models import Camera
from app.routers.cameras import camera_preview


def _session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_preview_returns_cached_frame_without_touching_rtsp():
    # Onbellekte kare varsa, RTSP'ye hic baglanmadan (gecersiz bir adres
    # olsa bile) aninda o kareyi dondurmeli - bu, worker'in zaten actigi
    # tek baglantiyi yeniden kullanarak "donma" hissini ortadan kaldiran
    # asil mekanizma.
    db = _session()
    camera = Camera(name="Test Kamera", rtsp_url="rtsp://gecersiz-adres.local/stream")
    db.add(camera)
    db.commit()
    db.refresh(camera)

    set_frame(camera.id, b"onbellekten-gelen-kare")

    response = camera_preview(camera.id, db=db)
    assert response.body == b"onbellekten-gelen-kare"
    assert response.media_type == "image/jpeg"
