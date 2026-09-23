import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("WATCHLIST_ENCRYPTION_KEY", "Gz3n5J9y8k2p6xQm1wZ7fL0oR4sT8vU2cA6bD9eH3iM=")

import cv2
import numpy as np

from app.vision.ocr import _preprocess_for_tesseract, _upscale_if_small


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
