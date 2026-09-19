from functools import lru_cache

import numpy as np

from app.config import get_settings
from app.plate_utils import is_valid_turkish_plate, normalize_plate

_ALLOWED_CHARS = "ABCDEFGHIJKLMNOPRSTUVYZ0123456789"


def _best_candidate(raw_texts_with_conf: list[tuple[str, float]]) -> tuple[str, float]:
    if not raw_texts_with_conf:
        return "", 0.0

    best_text, best_conf = "", 0.0
    for text, conf in raw_texts_with_conf:
        candidate = normalize_plate(text)
        if is_valid_turkish_plate(candidate) and conf > best_conf:
            best_text, best_conf = candidate, conf

    if best_text:
        return best_text, best_conf

    combined = normalize_plate("".join(text for text, _ in raw_texts_with_conf))
    avg_conf = sum(conf for _, conf in raw_texts_with_conf) / len(raw_texts_with_conf)
    return combined, avg_conf


def _read_with_tesseract(plate_crop: np.ndarray) -> tuple[str, float]:
    """Tamamen cevrimdisi calisir: tesseract binary'si (apt: tesseract-ocr,
    tesseract-ocr-tur) sistemde kurulu olmali; herhangi bir model internetten
    indirilmez. Varsayilan OCR motoru budur (bkz. OCR_ENGINE=tesseract)."""
    import pytesseract

    config = f"--psm 7 -c tessedit_char_whitelist={_ALLOWED_CHARS}"
    data = pytesseract.image_to_data(
        plate_crop, config=config, output_type=pytesseract.Output.DICT
    )
    candidates = [
        (text, float(conf) / 100.0)
        for text, conf in zip(data["text"], data["conf"])
        if text.strip() and float(conf) >= 0
    ]
    return _best_candidate(candidates)


@lru_cache
def _easyocr_reader():
    """EasyOCR, ilk calistirmada model agirliklarini internetten indirir
    (Docker imaji build sirasinda onceden indirilmediyse). Internet
    olmayan/air-gapped kurulumlarda kullanilmamalidir; bkz. README - OCR
    Motoru Secimi."""
    import easyocr

    return easyocr.Reader(["en"], gpu=False, verbose=False)


def _read_with_easyocr(plate_crop: np.ndarray) -> tuple[str, float]:
    results = _easyocr_reader().readtext(plate_crop, allowlist=_ALLOWED_CHARS, detail=1)
    return _best_candidate([(text, conf) for _, text, conf in results])


def read_plate_text(plate_crop: np.ndarray) -> tuple[str, float]:
    engine = get_settings().ocr_engine
    if engine == "easyocr":
        return _read_with_easyocr(plate_crop)
    return _read_with_tesseract(plate_crop)
