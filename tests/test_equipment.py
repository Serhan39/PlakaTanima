import os
from datetime import datetime, timedelta, timezone

os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("WATCHLIST_ENCRYPTION_KEY", "Gz3n5J9y8k2p6xQm1wZ7fL0oR4sT8vU2cA6bD9eH3iM=")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.crypto import decrypt_text, deterministic_hash, encrypt_text
from app.database import Base
from app.models import CameraDirection, EquipmentCrossingLog, EquipmentGate, EquipmentState, EquipmentZone
from app.routers.equipment import apply_crossing, crossing_logs, time_report, update_gate_line
from app.schemas import EquipmentGateLineUpdate
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


def test_explicit_direction_overrides_gate_default_direction():
    # Ayni fiziksel kapidan hem giren hem cikan arac olabilir; cizgi takibi
    # yapan worker her gecis icin gercek yonu acikca gonderir ve bu,
    # kapinin sabit/varsayilan yonunu (gate.direction) gecersiz kilmalidir.
    db = _session()
    exit_a, _ = _zone_and_gates(db)  # exit_a.direction == EXIT (varsayilan)

    event = apply_crossing(db, exit_a, "IS-001", 0.8, direction=CameraDirection.ENTRY)
    db.commit()

    assert event["direction"] == "entry"
    assert event["message"] == "IS-001 plakali arac A Alani alaninda"
    state = db.query(EquipmentState).first()
    assert state.zone_id == exit_a.zone_id


def test_update_gate_line_persists_line_and_inside_point():
    db = _session()
    exit_a, _ = _zone_and_gates(db)

    updated = update_gate_line(
        exit_a.id,
        EquipmentGateLineUpdate(line_x1=0.2, line_y1=0.3, line_x2=0.8, line_y2=0.3, inside_x=0.5, inside_y=0.1),
        db=db,
    )

    assert updated.line_x1 == 0.2
    assert updated.line_y2 == 0.3
    assert updated.inside_x == 0.5
    assert updated.inside_y == 0.1

    reloaded = db.get(EquipmentGate, exit_a.id)
    assert reloaded.line_x1 == 0.2
    assert reloaded.inside_y == 0.1


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


def test_crossing_source_defaults_to_camera():
    db = _session()
    _, entry_b = _zone_and_gates(db)
    apply_crossing(db, entry_b, "IS-001", 0.8)
    db.commit()

    log = db.query(EquipmentCrossingLog).first()
    assert log.source == "camera"


def test_manual_crossing_is_marked_as_manual_source():
    # Panelden elle girilen bir duzeltme, OCR/kamera kaynakli kayitlardan
    # Gecis Kayitlari tablosunda ayirt edilebilmeli.
    db = _session()
    _, entry_b = _zone_and_gates(db)
    apply_crossing(db, entry_b, "IS-001", confidence=1.0, source="manual")
    db.commit()

    log = db.query(EquipmentCrossingLog).first()
    assert log.source == "manual"
    assert log.confidence == 1.0


def test_feature_flag_defaults_to_disabled():
    db = _session()
    assert get_setting(db, "equipment_tracking_enabled", "false") == "false"
    set_setting(db, "equipment_tracking_enabled", "true")
    assert get_setting(db, "equipment_tracking_enabled", "false") == "true"


def test_crossing_logs_filters_by_zone_and_gate():
    db = _session()
    exit_a, entry_b = _zone_and_gates(db)
    apply_crossing(db, entry_b, "IS-001", 0.8)
    apply_crossing(db, exit_a, "IS-002", 0.7)
    db.commit()

    only_b = crossing_logs(zone_id=2, db=db, _=None)
    assert len(only_b) == 1
    assert only_b[0].plate == "IS-001"
    assert only_b[0].zone_name == "B Alani"
    assert only_b[0].gate_name == "B Giris"

    only_exit_a = crossing_logs(gate_id=1, db=db, _=None)
    assert len(only_exit_a) == 1
    assert only_exit_a[0].plate == "IS-002"
    assert only_exit_a[0].direction == CameraDirection.EXIT


def test_crossing_logs_filters_by_plate_query():
    db = _session()
    exit_a, entry_b = _zone_and_gates(db)
    apply_crossing(db, entry_b, "IS-001", 0.8)
    apply_crossing(db, entry_b, "MAK-999", 0.8)
    db.commit()

    results = crossing_logs(plate_query="is-0", db=db, _=None)
    assert len(results) == 1
    assert results[0].plate == "IS-001"


def test_time_report_computes_durations_per_zone():
    db = _session()
    exit_a, entry_b = _zone_and_gates(db)
    start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    end = start + timedelta(hours=1)

    plate_hash = deterministic_hash("IS-001")
    plate_encrypted = encrypt_text("IS-001")

    db.add(
        EquipmentCrossingLog(
            gate_id=entry_b.id,
            plate_encrypted=plate_encrypted,
            plate_hash=plate_hash,
            direction=CameraDirection.ENTRY,
            zone_id=entry_b.zone_id,
            confidence=0.9,
            created_at=start + timedelta(minutes=10),
        )
    )
    db.add(
        EquipmentCrossingLog(
            gate_id=exit_a.id,
            plate_encrypted=plate_encrypted,
            plate_hash=plate_hash,
            direction=CameraDirection.EXIT,
            zone_id=exit_a.zone_id,
            confidence=0.9,
            created_at=start + timedelta(minutes=40),
        )
    )
    db.commit()

    report = time_report(date_from=start, date_to=end, db=db, _=None)

    assert len(report) == 1
    entry = report[0]
    assert entry.plate == "IS-001"
    assert entry.total_seconds == 3600

    breakdown = {b.zone_name: b.duration_seconds for b in entry.breakdown}
    assert breakdown["Disarida"] == 30 * 60  # 0-10dk + 40-60dk disarida
    assert breakdown["B Alani"] == 30 * 60  # 10-40dk B alaninda


def test_time_report_carries_state_from_before_period_start():
    db = _session()
    exit_a, entry_b = _zone_and_gates(db)
    start = datetime(2026, 1, 1, 1, 0, 0, tzinfo=timezone.utc)
    end = start + timedelta(hours=1)

    plate_hash = deterministic_hash("IS-002")
    plate_encrypted = encrypt_text("IS-002")

    # Rapor araligindan ONCE B alanina girmis; arac raporun basinda zaten
    # B alaninda olmali (disarida degil).
    db.add(
        EquipmentCrossingLog(
            gate_id=entry_b.id,
            plate_encrypted=plate_encrypted,
            plate_hash=plate_hash,
            direction=CameraDirection.ENTRY,
            zone_id=entry_b.zone_id,
            confidence=0.9,
            created_at=start - timedelta(minutes=30),
        )
    )
    db.commit()

    report = time_report(date_from=start, date_to=end, db=db, _=None)

    assert len(report) == 1
    breakdown = {b.zone_name: b.duration_seconds for b in report[0].breakdown}
    assert breakdown == {"B Alani": 3600}


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
