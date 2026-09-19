from app.plate_utils import format_plate, is_valid_turkish_plate, normalize_plate


def test_normalize_strips_spaces_and_uppercases():
    assert normalize_plate("34 abc 123") == "34ABC123"


def test_valid_plate_formats():
    assert is_valid_turkish_plate("34 A 1234")
    assert is_valid_turkish_plate("06 AB 1234")
    assert is_valid_turkish_plate("35 ABC 12")


def test_invalid_plate_formats():
    assert not is_valid_turkish_plate("99 A 1234")
    assert not is_valid_turkish_plate("34 QWX 123")
    assert not is_valid_turkish_plate("plaka-degil")


def test_format_plate_adds_spacing():
    assert format_plate("34abc123") == "34 ABC 123"
