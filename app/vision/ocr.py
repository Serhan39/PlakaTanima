from functools import lru_cache

import cv2
import numpy as np

from app.config import get_settings
from app.plate_utils import is_valid_turkish_plate, normalize_plate

_ALLOWED_CHARS = "ABCDEFGHIJKLMNOPRSTUVYZ0123456789"

_TARGET_CROP_HEIGHT = 80  # Tesseract kucuk/dusuk cozunurluklu kirpmalarda cok kotu calisir


def _strip_left_band(plate_crop: np.ndarray) -> np.ndarray:
    """Turkiye plakalarinin solundaki mavi TR/AB bandini OCR'a vermeden
    once kirpar (bkz. app/config.py::plate_crop_left_trim_fraction).
    Fraction 0 ise (veya crop cok darsa) hicbir sey degismez."""
    fraction = get_settings().plate_crop_left_trim_fraction
    w = plate_crop.shape[1]
    cut = int(w * fraction)
    if cut <= 0 or cut >= w:
        return plate_crop
    return plate_crop[:, cut:]


def _preprocess_for_tesseract(plate_crop: np.ndarray) -> np.ndarray:
    """Tesseract'a ham (renkli, kucuk, dusuk kontrastli) bir kamera kirpmasi
    vermek dogrulugu ciddi sekilde dusurur - bu, kullanicinin bildirdigi
    "plakayi asiri hatali okuyor" sikayetinin ana nedeniydi (onceden HIC
    on isleme yapilmiyordu). Standart OCR on isleme adimlari:
      1) Gri tonlama - renk bilgisi metin tanima icin gereksiz/yanıltıcı
      2) Buyutme - kucuk kirpmalarda (orn. 40px yukseklik) Tesseract cok
         zayif kalir; en az ~80px yuksekliğe kubik interpolasyonla buyutulur
      3) CLAHE (yerel kontrast esitleme) - degisken/yetersiz isik telafisi
      4) Otsu esikleme - siyah/beyaz netlestirme, Tesseract'in en iyi
         calistigi girdi turu
    """
    gray = cv2.cvtColor(plate_crop, cv2.COLOR_BGR2GRAY) if plate_crop.ndim == 3 else plate_crop

    h, w = gray.shape[:2]
    if h > 0 and h < _TARGET_CROP_HEIGHT:
        scale = _TARGET_CROP_HEIGHT / h
        gray = cv2.resize(gray, (max(1, int(w * scale)), _TARGET_CROP_HEIGHT), interpolation=cv2.INTER_CUBIC)

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)

    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return binary


def _upscale_if_small(plate_crop: np.ndarray) -> np.ndarray:
    """EasyOCR kendi ic on islemesini yaptigi icin Tesseract'inki kadar agresif
    bir hazirliga ihtiyac duymaz (asiri isleme - orn. binarize etmek - bir
    sinir agini aslinda kotu etkileyebilir), ama cok kucuk kirpmalarda yine
    de buyutme faydali olur."""
    h, w = plate_crop.shape[:2]
    if h > 0 and h < _TARGET_CROP_HEIGHT:
        scale = _TARGET_CROP_HEIGHT / h
        return cv2.resize(plate_crop, (max(1, int(w * scale)), _TARGET_CROP_HEIGHT), interpolation=cv2.INTER_CUBIC)
    return plate_crop


def _best_candidate(raw_texts_with_conf: list[tuple[str, float]], strict: bool = True) -> tuple[str, float]:
    if not raw_texts_with_conf:
        return "", 0.0

    if strict:
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

    # Gevsek mod: Turkiye plaka formatina zorlamadan, en guvenilir/en uzun
    # metin blogunu secer. Fabrika ici is makinelerine ozel, standart plaka
    # kurallarina uymayan etiketler/kodlar icin kullanilir.
    text, conf = max(raw_texts_with_conf, key=lambda c: (c[1], len(c[0])))
    return normalize_plate(text), conf


def _read_with_tesseract(plate_crop: np.ndarray, strict: bool = True) -> tuple[str, float]:
    """Tamamen cevrimdisi calisir: tesseract binary'si (apt: tesseract-ocr,
    tesseract-ocr-tur) sistemde kurulu olmali; herhangi bir model internetten
    indirilmez. Varsayilan OCR motoru budur (bkz. OCR_ENGINE=tesseract)."""
    import pytesseract

    processed = _preprocess_for_tesseract(plate_crop)
    config = f"--psm 7 -c tessedit_char_whitelist={_ALLOWED_CHARS}"
    data = pytesseract.image_to_data(
        processed, config=config, output_type=pytesseract.Output.DICT
    )
    candidates = [
        (text, float(conf) / 100.0)
        for text, conf in zip(data["text"], data["conf"])
        if text.strip() and float(conf) >= 0
    ]
    return _best_candidate(candidates, strict=strict)


@lru_cache
def _easyocr_reader():
    """EasyOCR, ilk calistirmada model agirliklarini internetten indirir
    (Docker imaji build sirasinda onceden indirilmediyse). Internet
    olmayan/air-gapped kurulumlarda kullanilmamalidir; bkz. README - OCR
    Motoru Secimi."""
    import easyocr

    return easyocr.Reader(["en"], gpu=False, verbose=False)


def _read_with_easyocr(plate_crop: np.ndarray, strict: bool = True) -> tuple[str, float]:
    processed = _upscale_if_small(plate_crop)
    results = _easyocr_reader().readtext(processed, allowlist=_ALLOWED_CHARS, detail=1)
    return _best_candidate([(text, conf) for _, text, conf in results], strict=strict)


def read_plate_text(plate_crop: np.ndarray) -> tuple[str, float]:
    plate_crop = _strip_left_band(plate_crop)
    _save_debug_crop(plate_crop)
    engine = get_settings().ocr_engine
    if engine == "easyocr":
        return _read_with_easyocr(plate_crop, strict=True)
    return _read_with_tesseract(plate_crop, strict=True)


def _save_debug_crop(plate_crop: np.ndarray) -> None:
    """OCR'a TAM OLARAK giden goruntuyu (sol bant kirpildikten sonra, ama
    preprocess'ten ONCE) sabit bir dosyaya yazar - boylece "neden okumuyor"
    tesisinde tahmin yapmak yerine kullanicidan bu dosyayi isteyip gercek
    girdiyi goz ile inceleyebiliriz. Tek, uzerine yazilan sabit dosya -
    disk/performans maliyeti ihmal edilebilir."""
    try:
        from app.snapshots import SNAPSHOT_DIR

        SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(SNAPSHOT_DIR / "_debug_last_plate_crop.jpg"), plate_crop)
    except Exception:
        pass  # tani ozelligi - asla ana akisi bozmamali


def read_equipment_code(plate_crop: np.ndarray) -> tuple[str, float]:
    """Turkiye plaka format zorunlulugu olmadan, serbest metin okur. Fabrika
    ici is makinesi/ekipman etiketleri icin kullanilir (bkz. app/routers/equipment.py)."""
    engine = get_settings().ocr_engine
    if engine == "easyocr":
        return _read_with_easyocr(plate_crop, strict=False)
    return _read_with_tesseract(plate_crop, strict=False)
