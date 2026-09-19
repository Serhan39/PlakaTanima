from dataclasses import dataclass

import numpy as np
from sqlalchemy.orm import Session

from app.config import get_settings
from app.crypto import deterministic_hash
from app.models import WatchlistCategory, WatchlistEntry
from app.plate_utils import format_plate, is_valid_turkish_plate
from app.vision.detector import HaarCascadePlateDetector, OnnxPlateDetector, PlateDetector
from app.vision.ocr import read_equipment_code, read_plate_text


@dataclass
class PipelineResult:
    plate: str
    confidence: float
    matched_category: WatchlistCategory | None


@dataclass
class EquipmentDetection:
    code: str
    confidence: float


def build_default_detector() -> PlateDetector:
    settings = get_settings()
    try:
        return OnnxPlateDetector(settings.plate_detector_model_path, min_confidence=settings.detection_confidence_threshold)
    except FileNotFoundError:
        return HaarCascadePlateDetector(min_confidence=settings.detection_confidence_threshold)


def recognize_plates(frame: np.ndarray, detector: PlateDetector, db: Session) -> list[PipelineResult]:
    results: list[PipelineResult] = []
    for box in detector.detect(frame):
        crop = box.crop(frame)
        if crop.size == 0:
            continue
        text, ocr_conf = read_plate_text(crop)
        if not text or not is_valid_turkish_plate(text):
            continue

        plate = format_plate(text)
        confidence = (box.confidence + ocr_conf) / 2
        plate_hash = deterministic_hash(plate)
        match = db.query(WatchlistEntry).filter(WatchlistEntry.plate_hash == plate_hash).first()

        results.append(
            PipelineResult(
                plate=plate,
                confidence=round(confidence, 3),
                matched_category=match.category if match else None,
            )
        )
    return results


def recognize_equipment_codes(frame: np.ndarray, detector: PlateDetector, min_length: int = 3) -> list[EquipmentDetection]:
    """Standart Turkiye plaka formatina zorlamadan, is makinesi/ekipman
    etiketlerini okur (bkz. app/vision/ocr.py::read_equipment_code)."""
    results: list[EquipmentDetection] = []
    for box in detector.detect(frame):
        crop = box.crop(frame)
        if crop.size == 0:
            continue
        text, ocr_conf = read_equipment_code(crop)
        if not text or len(text) < min_length:
            continue

        confidence = round((box.confidence + ocr_conf) / 2, 3)
        results.append(EquipmentDetection(code=text, confidence=confidence))
    return results
