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

SNAPSHOT_DIR = Path("data/snapshots")


def save_snapshot(frame: np.ndarray) -> str:
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.jpg"
    path = SNAPSHOT_DIR / filename
    cv2.imwrite(str(path), frame)
    return str(path)
