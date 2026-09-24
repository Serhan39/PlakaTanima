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
    camera = Camera(name="Test", rtsp_url="rtsp://x")  # roi_points varsayilan None
    cropped, x, y = _apply_roi(frame, camera)
    assert cropped is frame
    assert (x, y) == (0, 0)


def test_apply_roi_returns_full_frame_when_fewer_than_three_points():
    # Bir cokgen en az 3 nokta gerektirir; API bunu zaten reddediyor ama
    # DB'de elle bozuk/eksik veri kalirsa yine de coken bir kirpma yerine
    # tum kareye donmeli.
    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    camera = Camera(name="Test", rtsp_url="rtsp://x", roi_points=[[0.1, 0.1], [0.5, 0.5]])
    cropped, x, y = _apply_roi(frame, camera)
    assert cropped is frame
    assert (x, y) == (0, 0)


def test_apply_roi_crops_to_bounding_box_of_a_rectangular_polygon():
    # 200 genislik x 100 yukseklik bir karede, sagin sag yarisinin alt
    # yarisini (x: 0.5-1.0, y: 0.5-1.0) 4 koseli bir dikdortgen olarak
    # isaretleyelim - eski dikdortgen davranisiyla ayni sonucu vermeli.
    frame = np.full((100, 200, 3), 200, dtype=np.uint8)
    camera = Camera(
        name="Test",
        rtsp_url="rtsp://x",
        roi_points=[[0.5, 0.5], [1.0, 0.5], [1.0, 1.0], [0.5, 1.0]],
    )

    cropped, x, y = _apply_roi(frame, camera)

    assert (x, y) == (100, 50)
    assert cropped.shape[:2] == (50, 100)  # (yukseklik, genislik)
    assert (cropped == 200).all()  # tam dikdortgen oldugu icin hicbir yer karartilmamali


def test_apply_roi_blackens_pixels_outside_an_asymmetric_polygon():
    # Kullanicinin istedigi asil ozellik: capraz/duzensiz bir sekil (burada
    # bir ucgen) cizildiginde, sekle GIRMEYEN ama dikdortgen SINIRA giren
    # pikseller (orn. duvar/tabela) karartilmali - sadece bounding box
    # kirpmasi degil, gercek cokgen maskesi uygulanmali.
    frame = np.full((100, 200, 3), 255, dtype=np.uint8)
    # Ucgen: (0,0)-(1,0)-(0,1) normalize - sol-ust kose bosluk
    camera = Camera(name="Test", rtsp_url="rtsp://x", roi_points=[[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]])

    cropped, x, y = _apply_roi(frame, camera)

    assert (x, y) == (0, 0)
    assert cropped.shape[:2] == (100, 200)
    # Ucgenin ICINDE kalan bir nokta (sol-ust kosede) beyaz kalmali
    assert tuple(cropped[5, 5]) == (255, 255, 255)
    # Ucgenin DISINDA ama dikdortgen sinirda kalan bir nokta (sag-alt kose) karartilmali
    assert tuple(cropped[95, 195]) == (0, 0, 0)


def test_apply_roi_ignores_degenerate_region():
    # Tum noktalar tek bir cizgi/nokta uzerindeyse (sifir alan), coken bir
    # kirpma islemi yerine tum kareye geri donmeli.
    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    camera = Camera(name="Test", rtsp_url="rtsp://x", roi_points=[[0.5, 0.5], [0.5, 0.5], [0.5, 0.5]])

    cropped, x, y = _apply_roi(frame, camera)

    assert cropped is frame
    assert (x, y) == (0, 0)
