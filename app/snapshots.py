"""Tespit anindaki kare goruntusunu diske kaydeder. `data/` klasoru
docker-compose.yml icinde kalici bir birim (volume) oldugu icin, buraya
kaydedilen fotograflar konteyner yeniden olusturulsa bile kaybolmaz.
Goruntuler plaka/kisisel veri icerdigi icin sadece kimlik dogrulamali
API uzerinden (bkz. app/routers/logs.py) sunulur, statik/herkese acik
bir klasor olarak DEGIL."""

import uuid
from pathlib import Path

import cv2
import numpy as np

from app.vision.detector import BoundingBox

SNAPSHOT_DIR = Path("data/snapshots")

_BOX_COLOR = (255, 0, 0)  # BGR - mavi
_BOX_THICKNESS = 3


def draw_detection_boxes(frame: np.ndarray, boxes: list[tuple[BoundingBox, str]]) -> np.ndarray:
    """Tespit edilen plaka(lar)in etrafina mavi bir cerceve ve okunan
    metni cizer; kullanicinin sistemin neye/nereye "odaklandigini"
    gorsel olarak dogrulayabilmesi icin Son Gecen Arac / Kayitlar
    fotograflarina uygulanir. Orijinal kareyi degistirmemek icin bir
    kopya uzerinde calisir."""
    annotated = frame.copy()
    for box, label in boxes:
        cv2.rectangle(annotated, (box.x1, box.y1), (box.x2, box.y2), _BOX_COLOR, _BOX_THICKNESS)
        text_y = box.y1 - 10 if box.y1 - 10 > 10 else box.y2 + 25
        cv2.putText(annotated, label, (box.x1, text_y), cv2.FONT_HERSHEY_SIMPLEX, 0.8, _BOX_COLOR, 2)
    return annotated


def save_snapshot(frame: np.ndarray) -> str:
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.jpg"
    path = SNAPSHOT_DIR / filename
    cv2.imwrite(str(path), frame)
    return str(path)
