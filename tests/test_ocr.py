import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("WATCHLIST_ENCRYPTION_KEY", "Gz3n5J9y8k2p6xQm1wZ7fL0oR4sT8vU2cA6bD9eH3iM=")

import cv2
import numpy as np

from app.config import get_settings
from app.vision.ocr import _preprocess_for_tesseract, _save_debug_crop, _strip_left_band, _upscale_if_small


def _small_bgr_crop(height=30, width=90):
    return np.random.randint(0, 255, (height, width, 3), dtype=np.uint8)


def test_preprocess_for_tesseract_upscales_small_crops_to_target_height():
    crop = _small_bgr_crop(height=30, width=90)

    processed = _preprocess_for_tesseract(crop)

    assert processed.shape[0] == 80  # _TARGET_CROP_HEIGHT


def test_preprocess_for_tesseract_returns_single_channel_binary_image():
    crop = _small_bgr_crop()

    processed = _preprocess_for_tesseract(crop)

    assert processed.ndim == 2
    assert set(np.unique(processed).tolist()) <= {0, 255}


def test_preprocess_for_tesseract_leaves_already_large_crops_at_their_height():
    crop = _small_bgr_crop(height=120, width=300)

    processed = _preprocess_for_tesseract(crop)

    assert processed.shape[0] == 120


def test_upscale_if_small_grows_small_crop_without_binarizing():
    crop = _small_bgr_crop(height=30, width=90)

    processed = _upscale_if_small(crop)

    assert processed.shape[0] == 80
    assert processed.ndim == 3  # EasyOCR icin renk kanallari korunur


def test_upscale_if_small_leaves_already_large_crops_untouched():
    crop = _small_bgr_crop(height=120, width=300)

    processed = _upscale_if_small(crop)

    assert processed.shape == crop.shape


def test_strip_left_band_trims_default_fraction_off_the_left_edge():
    # Gercek olay: "07 MYS 57" plakasinin OCR okumalari (orn. "97MYS57",
    # "402HYS57") sondaki "MYS57" sabit kalirken bastaki "07" her
    # seferinde farkli bozuluyordu - Turkiye plakalarinin solundaki mavi
    # TR/AB bandinin OCR'a karistigina isaret ediyor. Varsayilan %12'lik
    # kirpma bu bandi disarida birakmali.
    crop = _small_bgr_crop(height=60, width=200)
    get_settings.cache_clear()

    trimmed = _strip_left_band(crop)

    assert trimmed.shape[1] == 200 - int(200 * 0.12)
    assert np.array_equal(trimmed, crop[:, 24:])


def test_strip_left_band_is_a_noop_when_fraction_is_zero(monkeypatch):
    crop = _small_bgr_crop(height=60, width=200)
    monkeypatch.setenv("PLATE_CROP_LEFT_TRIM_FRACTION", "0")
    get_settings.cache_clear()
    try:
        trimmed = _strip_left_band(crop)
        assert trimmed.shape == crop.shape
    finally:
        get_settings.cache_clear()


def test_save_debug_crop_writes_the_exact_image_ocr_receives(tmp_path, monkeypatch):
    # "okumuyor" teshisi icin: OCR'a TAM OLARAK giden goruntuyu sabit bir
    # dosyaya yazar, boylece kullanicidan bu dosyayi isteyip tahmin yerine
    # gercek girdiyi gozle inceleyebiliriz.
    import app.snapshots as snapshots

    monkeypatch.setattr(snapshots, "SNAPSHOT_DIR", tmp_path / "snapshots")
    crop = _small_bgr_crop(height=40, width=100)

    _save_debug_crop(crop)

    debug_path = tmp_path / "snapshots" / "_debug_last_plate_crop.jpg"
    assert debug_path.exists()


def test_save_debug_crop_never_raises_even_if_write_fails():
    # Tani ozelligi, ana akisi ASLA bozmamali - yazma basarisiz olsa bile.
    _save_debug_crop(None)  # gecersiz girdi, cv2.imwrite hata versin diye
