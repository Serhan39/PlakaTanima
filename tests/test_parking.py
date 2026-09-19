import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("WATCHLIST_ENCRYPTION_KEY", "Gz3n5J9y8k2p6xQm1wZ7fL0oR4sT8vU2cA6bD9eH3iM=")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.crypto import deterministic_hash
from app.database import Base
from app.models import Camera, CameraDirection, ParkingState
from app.routers.detect import _update_parking_state
from app.settings_store import get_setting, set_setting


def _session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def _camera(direction: CameraDirection) -> Camera:
    return Camera(id=1, name="Test", rtsp_url="rtsp://demo", direction=direction)


def test_entry_camera_adds_vehicle():
    db = _session()
    camera = _camera(CameraDirection.ENTRY)
    _update_parking_state(db, camera, "34 ABC 12", deterministic_hash("34 ABC 12"))
    db.commit()
    assert db.query(ParkingState).count() == 1


def test_entry_camera_does_not_duplicate():
    db = _session()
    camera = _camera(CameraDirection.ENTRY)
    for _ in range(3):
        _update_parking_state(db, camera, "34 ABC 12", deterministic_hash("34 ABC 12"))
        db.commit()
    assert db.query(ParkingState).count() == 1


def test_exit_camera_removes_vehicle():
    db = _session()
    entry_camera = _camera(CameraDirection.ENTRY)
    _update_parking_state(db, entry_camera, "34 ABC 12", deterministic_hash("34 ABC 12"))
    db.commit()

    exit_camera = Camera(id=2, name="Cikis", rtsp_url="rtsp://demo2", direction=CameraDirection.EXIT)
    _update_parking_state(db, exit_camera, "34 ABC 12", deterministic_hash("34 ABC 12"))
    db.commit()

    assert db.query(ParkingState).count() == 0


def test_none_direction_camera_ignored():
    db = _session()
    camera = _camera(CameraDirection.NONE)
    _update_parking_state(db, camera, "34 ABC 12", deterministic_hash("34 ABC 12"))
    db.commit()
    assert db.query(ParkingState).count() == 0


def test_settings_store_roundtrip():
    db = _session()
    assert get_setting(db, "parking_capacity", "50") == "50"
    set_setting(db, "parking_capacity", "80")
    assert get_setting(db, "parking_capacity", "50") == "80"
