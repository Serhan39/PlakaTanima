from functools import lru_cache

import numpy as np

from app.plate_utils import is_valid_turkish_plate, normalize_plate

_ALLOWED_CHARS = "ABCDEFGHIJKLMNOPRSTUVYZ0123456789"


@lru_cache
def _reader():
    import easyocr

    return easyocr.Reader(["en"], gpu=False, verbose=False)


def read_plate_text(plate_crop: np.ndarray) -> tuple[str, float]:
    results = _reader().readtext(plate_crop, allowlist=_ALLOWED_CHARS, detail=1)
    if not results:
        return "", 0.0

    best_text, best_conf = "", 0.0
    for _, text, conf in results:
        candidate = normalize_plate(text)
        if is_valid_turkish_plate(candidate) and conf > best_conf:
            best_text, best_conf = candidate, conf

    if best_text:
        return best_text, best_conf

    combined = normalize_plate("".join(text for _, text, _ in results))
    avg_conf = sum(conf for _, _, conf in results) / len(results)
    return combined, avg_conf
