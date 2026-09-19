import re

# Turkiye plakalarinda kullanilmayan harfler: Q, W, X (Turk alfabesinde/plaka mevzuatinda yok)
_LETTERS = "ABCDEFGHIJKLMNOPRSTUVYZ"
_PLATE_RE = re.compile(
    rf"^(0[1-9]|[1-7][0-9]|8[01])"
    rf"([{_LETTERS}]{{1}}\d{{4,5}}|[{_LETTERS}]{{2}}\d{{3,4}}|[{_LETTERS}]{{3}}\d{{2}})$"
)

_OCR_CONFUSION_MAP = str.maketrans({"İ": "I", "Ç": "C", "Ş": "S", "Ğ": "G", "Ü": "U", "Ö": "O", "0": "0"})


def normalize_plate(raw: str) -> str:
    cleaned = raw.strip().upper().translate(_OCR_CONFUSION_MAP)
    cleaned = re.sub(r"[\s.\-]", "", cleaned)
    return cleaned


def is_valid_turkish_plate(raw: str) -> bool:
    return bool(_PLATE_RE.match(normalize_plate(raw)))


def format_plate(raw: str) -> str:
    plate = normalize_plate(raw)
    match = re.match(rf"^(\d{{2}})([{_LETTERS}]+)(\d+)$", plate)
    if not match:
        return plate
    il, harf, rakam = match.groups()
    return f"{il} {harf} {rakam}"
