import os
from unittest.mock import patch

os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("WATCHLIST_ENCRYPTION_KEY", "Gz3n5J9y8k2p6xQm1wZ7fL0oR4sT8vU2cA6bD9eH3iM=")

import numpy as np
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.vision.detector import BoundingBox, PlateDetector
from app.vision.pipeline import recognize_plates


class _FakeDetector(PlateDetector):
    """Testte gercek bir ONNX/Haar motoruna gerek kalmadan, sabit bir
    kutu dondurmesi icin kullanilan sahte tespit motoru."""

    def __init__(self, box: BoundingBox):
        self._box = box

    def detect(self, frame):
        return [self._box]


def _session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_recognize_plates_result_carries_the_original_detection_box():
    # Kullanicinin "sistemin plakaya nasil odaklandigini gorelim" istegi
    # icin, PipelineResult artik OCR ile okunan metnin yani sira, o metnin
    # hangi kutudan geldigini de tasimali - snapshot uzerine cizim
    # yapabilmek (app/snapshots.py::draw_detection_boxes) icin sart.
    frame = np.zeros((200, 200, 3), dtype=np.uint8)
    box = BoundingBox(10, 20, 100, 60, confidence=0.9)
    detector = _FakeDetector(box)
    db = _session()

    with patch("app.vision.pipeline.read_plate_text", return_value=("34ABC12", 0.95)):
        results = recognize_plates(frame, detector, db)

    assert len(results) == 1
    assert results[0].plate == "34 ABC 12"
    assert results[0].box is box


def test_recognize_plates_skips_invalid_plate_text_without_returning_a_box():
    frame = np.zeros((200, 200, 3), dtype=np.uint8)
    box = BoundingBox(10, 20, 100, 60, confidence=0.9)
    detector = _FakeDetector(box)
    db = _session()

    with patch("app.vision.pipeline.read_plate_text", return_value=("gecersiz metin", 0.5)):
        results = recognize_plates(frame, detector, db)

    assert results == []


def test_recognize_plates_drops_very_low_confidence_reading_even_if_format_is_valid():
    # Neredeyse hicbir bilgi tasimayan (kutu ve OCR ikisi de cok dusuk
    # guvenli) bir okuma, format olarak gecerli olsa bile reddedilmeli.
    frame = np.zeros((200, 200, 3), dtype=np.uint8)
    box = BoundingBox(10, 20, 100, 60, confidence=0.2)
    detector = _FakeDetector(box)
    db = _session()

    with patch("app.vision.pipeline.read_plate_text", return_value=("07BRE10", 0.2)):
        # ortalama: (0.2 + 0.2) / 2 = 0.2 -> varsayilan MIN_PLATE_READ_CONFIDENCE 0.3'un altinda
        results = recognize_plates(frame, detector, db)

    assert results == []


def test_recognize_plates_keeps_realworld_confidence_that_used_to_be_wrongly_dropped():
    # Gercek olay: "07 BAF 140" plakasi kutu+OCR ortalama guveni %42 ile
    # geldi (dogru okundugunda dahi). Once kombine guven, KUTU icin
    # dusunulmus %50'lik esikle (DETECTION_CONFIDENCE_THRESHOLD)
    # karsilastirilinca sistem HICBIR sonuc goster(e)miyordu ("simdi hic
    # gormuyor" sikayeti). Artik ayri, daha dusuk bir esik
    # (MIN_PLATE_READ_CONFIDENCE, varsayilan 0.3) kullanildigi icin bu
    # gercekci guven seviyesindeki dogru okuma artik kaydedilmeli.
    frame = np.zeros((200, 200, 3), dtype=np.uint8)
    box = BoundingBox(10, 20, 100, 60, confidence=0.44)
    detector = _FakeDetector(box)
    db = _session()

    with patch("app.vision.pipeline.read_plate_text", return_value=("07BAF140", 0.40)):
        results = recognize_plates(frame, detector, db)

    assert len(results) == 1
    assert results[0].plate == "07 BAF 140"


def test_recognize_plates_keeps_reading_at_or_above_threshold():
    frame = np.zeros((200, 200, 3), dtype=np.uint8)
    box = BoundingBox(10, 20, 100, 60, confidence=0.9)
    detector = _FakeDetector(box)
    db = _session()

    with patch("app.vision.pipeline.read_plate_text", return_value=("34ABC12", 0.95)):
        results = recognize_plates(frame, detector, db)

    assert len(results) == 1
    assert results[0].confidence >= 0.3
