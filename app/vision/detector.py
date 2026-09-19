from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


@dataclass
class BoundingBox:
    x1: int
    y1: int
    x2: int
    y2: int
    confidence: float

    def crop(self, frame: np.ndarray) -> np.ndarray:
        return frame[self.y1 : self.y2, self.x1 : self.x2]


class PlateDetector(ABC):
    @abstractmethod
    def detect(self, frame: np.ndarray) -> list[BoundingBox]:
        raise NotImplementedError


class HaarCascadePlateDetector(PlateDetector):
    """OpenCV (BSD lisansli) ile gelen hazir kaskad dosyasini kullanan, ek model
    veya lisans gerektirmeyen dusuk maliyetli tespit motoru. Demo/gelistirme
    ortami ve dusuk trafikli kullanim icin yeterlidir; yuksek dogruluk gereken
    kurulumlarda OnnxPlateDetector'a gecilmesi onerilir."""

    def __init__(self, min_confidence: float = 0.5):
        cascade_path = cv2.data.haarcascades + "haarcascade_russian_plate_number.xml"
        self._cascade = cv2.CascadeClassifier(cascade_path)
        self._min_confidence = min_confidence

    def detect(self, frame: np.ndarray) -> list[BoundingBox]:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        boxes, _, weights = self._cascade.detectMultiScale3(
            gray, scaleFactor=1.1, minNeighbors=4, outputRejectLevels=True
        )
        results = []
        for (x, y, w, h), weight in zip(boxes, weights):
            confidence = min(float(weight) / 10.0, 1.0)
            if confidence >= self._min_confidence:
                results.append(BoundingBox(int(x), int(y), int(x + w), int(y + h), confidence))
        return results


class OnnxPlateDetector(PlateDetector):
    """YOLO tabanli, onceden egitilmis ve ONNX formatina donusturulmus bir plaka
    tespit modelini onnxruntime ile calistirir. Egitim/aktarim asamasinda
    kullanilan framework'un (ornegin Ultralytics) lisans kosullari sadece o
    asamayi ilgilendirir; urun icinde sadece bu dosyadaki bagimsiz ONNX
    calisma zamani (Apache-2.0/MIT lisansli onnxruntime) dagitilir, bu da
    AGPL kapsam genisletmesini urune tasimaz. Model dosyasi musteri/urun
    paketine ayrica saglanir (bkz. README - Model Tedariki)."""

    def __init__(self, model_path: str, input_size: int = 640, min_confidence: float = 0.5):
        import onnxruntime as ort

        if not Path(model_path).exists():
            raise FileNotFoundError(
                f"ONNX model bulunamadi: {model_path}. Egitimli bir plaka tespit modelini "
                "bu yola yerlestirin ya da PLATE_DETECTOR_MODEL_PATH degiskenini guncelleyin."
            )
        self._session = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
        self._input_name = self._session.get_inputs()[0].name
        self._input_size = input_size
        self._min_confidence = min_confidence

    def _preprocess(self, frame: np.ndarray) -> tuple[np.ndarray, float, float]:
        h, w = frame.shape[:2]
        scale = self._input_size / max(h, w)
        resized = cv2.resize(frame, (int(w * scale), int(h * scale)))
        padded = np.full((self._input_size, self._input_size, 3), 114, dtype=np.uint8)
        padded[: resized.shape[0], : resized.shape[1]] = resized
        blob = padded.transpose(2, 0, 1)[None].astype(np.float32) / 255.0
        return blob, scale, scale

    def detect(self, frame: np.ndarray) -> list[BoundingBox]:
        blob, scale_x, scale_y = self._preprocess(frame)
        outputs = self._session.run(None, {self._input_name: blob})[0][0]

        boxes = []
        for row in outputs.T:
            cx, cy, w, h, conf = row[:5]
            if conf < self._min_confidence:
                continue
            x1 = int((cx - w / 2) / scale_x)
            y1 = int((cy - h / 2) / scale_y)
            x2 = int((cx + w / 2) / scale_x)
            y2 = int((cy + h / 2) / scale_y)
            boxes.append(BoundingBox(max(x1, 0), max(y1, 0), x2, y2, float(conf)))
        return _non_max_suppression(boxes)


def _non_max_suppression(boxes: list[BoundingBox], iou_threshold: float = 0.45) -> list[BoundingBox]:
    if not boxes:
        return []
    boxes = sorted(boxes, key=lambda b: b.confidence, reverse=True)
    keep: list[BoundingBox] = []
    for box in boxes:
        if all(_iou(box, kept) < iou_threshold for kept in keep):
            keep.append(box)
    return keep


def _iou(a: BoundingBox, b: BoundingBox) -> float:
    xi1, yi1 = max(a.x1, b.x1), max(a.y1, b.y1)
    xi2, yi2 = min(a.x2, b.x2), min(a.y2, b.y2)
    inter = max(0, xi2 - xi1) * max(0, yi2 - yi1)
    area_a = max(0, a.x2 - a.x1) * max(0, a.y2 - a.y1)
    area_b = max(0, b.x2 - b.x1) * max(0, b.y2 - b.y1)
    union = area_a + area_b - inter
    return inter / union if union else 0.0
