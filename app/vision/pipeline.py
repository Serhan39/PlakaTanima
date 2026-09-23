from dataclasses import dataclass

import numpy as np
from sqlalchemy.orm import Session

from app.config import get_settings
from app.crypto import deterministic_hash
from app.models import WatchlistCategory, WatchlistEntry
from app.plate_utils import format_plate, is_valid_turkish_plate
from app.vision.detector import BoundingBox, HaarCascadePlateDetector, OnnxPlateDetector, PlateDetector
from app.vision.ocr import read_equipment_code, read_plate_text


@dataclass
class PipelineResult:
    plate: str
    confidence: float
    matched_category: WatchlistCategory | None
    box: BoundingBox


@dataclass
class EquipmentDetection:
    code: str
    confidence: float


def build_default_detector() -> PlateDetector:
    """ONNX modeli (bkz. README - Model Tedariki) bulunamazsa OpenCV'nin
    hazir Haar Cascade motoruna geriye duser - bu, gercek kamera goruntusunde
    (aci/mesafe/isik degisen) genelde YETERSIZ KALIR, sadece demo/gelistirme
    icin dusunulmustur. Hangi motorun secildigini acikca stdout'a yazariz
    (print - projedeki diger worker'larla ayni loglama yontemi, logging
    modulu ek yapilandirma olmadan uvicorn altinda gorunmeyebiliyor); aksi
    halde "plaka okunmuyor" sikayeti geldiginde neden anlasilmaz."""
    settings = get_settings()
    try:
        detector = OnnxPlateDetector(settings.plate_detector_model_path, min_confidence=settings.detection_confidence_threshold)
        print(f"[detect] Plaka tespiti icin ONNX motoru kullaniliyor: {settings.plate_detector_model_path}")
        return detector
    except FileNotFoundError:
        print(
            f"[detect] ONNX model dosyasi bulunamadi ({settings.plate_detector_model_path}) - "
            "OpenCV Haar Cascade demo motoruna geciliyor. Bu motor gercek kamera goruntusunde "
            "genelde yetersiz kalir; gercek kullanim icin bkz. README - Model Tedariki."
        )
        return HaarCascadePlateDetector(min_confidence=settings.detection_confidence_threshold)


def recognize_plates(frame: np.ndarray, detector: PlateDetector, db: Session) -> list[PipelineResult]:
    """Detektorun kendi min_confidence'i sadece KUTU guvenini filtreler;
    OCR metni bulanik/yanlis okunursa bile "format olarak gecerli" bir
    plaka uretebilir (orn. gercek "07 BAF 140" -> yanlis okunan "07 BRE 10"
    de format olarak gecerlidir). Bu yuzden burada, kutu+OCR ORTALAMA
    guveni de ayni esikle (DETECTION_CONFIDENCE_THRESHOLD) tekrar
    filtreleniyor - dusuk guvenli/muhtemelen hatali bir okuma, dogru bir
    okumayla ayni guvenilirlikte kaydedilmemeli."""
    settings = get_settings()
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
        if confidence < settings.detection_confidence_threshold:
            continue
        plate_hash = deterministic_hash(plate)
        match = db.query(WatchlistEntry).filter(WatchlistEntry.plate_hash == plate_hash).first()

        results.append(
            PipelineResult(
                plate=plate,
                confidence=round(confidence, 3),
                matched_category=match.category if match else None,
                box=box,
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
