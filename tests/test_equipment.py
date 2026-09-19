import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("WATCHLIST_ENCRYPTION_KEY", "Gz3n5J9y8k2p6xQm1wZ7fL0oR4sT8vU2cA6bD9eH3iM=")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.crypto import decrypt_text
from app.database import Base
from app.models import CameraDirection, EquipmentCrossingLog, EquipmentGate, EquipmentState, EquipmentZone
from app.routers.equipment import apply_crossing
from app.settings_store import get_setting, set_setting
from app.vision.ocr import _best_candidate


def _session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def _zone_and_gates(db):
    zone_a = EquipmentZone(id=1, name="A Alani")
    zone_b = EquipmentZone(id=2, name="B Alani")
    db.add_all([zone_a, zone_b])
    db.commit()

    exit_a = EquipmentGate(id=1, name="A Cikis", zone_id=1, direction=CameraDirection.EXIT)
    entry_b = EquipmentGate(id=2, name="B Giris", zone_id=2, direction=CameraDirection.ENTRY)
    db.add_all([exit_a, entry_b])
    db.commit()
    db.refresh(exit_a)
    db.refresh(entry_b)
    return exit_a, entry_b


def test_entry_gate_sets_zone():
    db = _session()
    _, entry_b = _zone_and_gates(db)

    event = apply_crossing(db, entry_b, "IS-001", 0.8)
    db.commit()

    assert event["message"] == "IS-001 plakali arac B Alani alaninda"
    state = db.query(EquipmentState).first()
    assert state.zone_id == 2


def test_exit_gate_clears_zone():
    db = _session()
    exit_a, entry_b = _zone_and_gates(db)

    apply_crossing(db, entry_b, "IS-001", 0.8)
    db.commit()

    event = apply_crossing(db, exit_a, "IS-001", 0.8)
    db.commit()

    assert event["message"] == "IS-001 plakali arac disarida"
    state = db.query(EquipmentState).first()
    assert state.zone_id is None


def test_repeated_reads_within_window_are_debounced():
    db = _session()
    _, entry_b = _zone_and_gates(db)

    first = apply_crossing(db, entry_b, "IS-001", 0.8)
    db.commit()
    second = apply_crossing(db, entry_b, "IS-001", 0.9)
    db.commit()

    assert first is not None
    assert second is None
    assert db.query(EquipmentCrossingLog).count() == 1


def test_different_plates_are_not_debounced_against_each_other():
    db = _session()
    _, entry_b = _zone_and_gates(db)

    apply_crossing(db, entry_b, "IS-001", 0.8)
    apply_crossing(db, entry_b, "IS-002", 0.8)
    db.commit()

    assert db.query(EquipmentCrossingLog).count() == 2


def test_plate_is_stored_encrypted_not_in_plaintext():
    db = _session()
    _, entry_b = _zone_and_gates(db)
    apply_crossing(db, entry_b, "IS-001", 0.8)
    db.commit()

    log = db.query(EquipmentCrossingLog).first()
    assert log.plate_encrypted != "IS-001"
    assert decrypt_text(log.plate_encrypted) == "IS-001"


def test_feature_flag_defaults_to_disabled():
    db = _session()
    assert get_setting(db, "equipment_tracking_enabled", "false") == "false"
    set_setting(db, "equipment_tracking_enabled", "true")
    assert get_setting(db, "equipment_tracking_enabled", "false") == "true"


def test_loose_ocr_candidate_does_not_require_turkish_plate_format():
    # 'IS-MAK-01' standart Turkiye plaka formatina uymaz (harfle basliyor);
    # strict=True modda dogrudan secilemez ama strict=False (ekipman modu)
    # ile en guvenilir aday olarak (normalize edilip) secilebilmelidir.
    candidates = [("IS-MAK-01", 0.9), ("XX", 0.4)]
    text, conf = _best_candidate(candidates, strict=False)
    assert text == "ISMAK01"
    assert conf == 0.9

    strict_text, _ = _best_candidate(candidates, strict=True)
    assert strict_text != "ISMAK01"
