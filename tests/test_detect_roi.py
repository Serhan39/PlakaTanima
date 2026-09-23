import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("WATCHLIST_ENCRYPTION_KEY", "Gz3n5J9y8k2p6xQm1wZ7fL0oR4sT8vU2cA6bD9eH3iM=")

import numpy as np

from app.models import Camera
from app.routers.detect import _apply_roi


def test_apply_roi_returns_full_frame_when_camera_is_none():
    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    cropped, x, y = _apply_roi(frame, None)
    assert cropped is frame
    assert (x, y) == (0, 0)


def test_apply_roi_returns_full_frame_when_roi_not_set():
    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    camera = Camera(name="Test", rtsp_url="rtsp://x")  # roi_* alanlari varsayilan None
    cropped, x, y = _apply_roi(frame, camera)
    assert cropped is frame
    assert (x, y) == (0, 0)


def test_apply_roi_crops_to_normalized_region_and_returns_pixel_offset():
    # 200 genislik x 100 yukseklik bir karede, sagin sag yarisinin alt
    # yarisini (x: 0.5-1.0, y: 0.5-1.0) bolge olarak isaretleyelim.
    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    camera = Camera(name="Test", rtsp_url="rtsp://x", roi_x1=0.5, roi_y1=0.5, roi_x2=1.0, roi_y2=1.0)

    cropped, x, y = _apply_roi(frame, camera)

    assert (x, y) == (100, 50)
    assert cropped.shape[:2] == (50, 100)  # (yukseklik, genislik)


def test_apply_roi_ignores_degenerate_region():
    # x2<=x1 ya da y2<=y1 gibi gecersiz/ters bir bolge tanimlanirsa
    # (orn. kullanicinin elle DB'de bozuk deger birakmasi), tum kareye
    # geri donmeli - coken bir kirpma islemi yerine.
    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    camera = Camera(name="Test", rtsp_url="rtsp://x", roi_x1=0.8, roi_y1=0.5, roi_x2=0.2, roi_y2=0.9)

    cropped, x, y = _apply_roi(frame, camera)

    assert cropped is frame
    assert (x, y) == (0, 0)
