from app.live_frame_cache import get_frame, set_frame


def test_get_frame_returns_none_when_nothing_cached():
    assert get_frame(999999) is None


def test_set_then_get_returns_latest_bytes():
    set_frame(1, b"ilk-kare")
    assert get_frame(1) == b"ilk-kare"

    set_frame(1, b"ikinci-kare")
    assert get_frame(1) == b"ikinci-kare"


def test_frames_are_isolated_per_camera():
    set_frame(10, b"kamera-10")
    set_frame(20, b"kamera-20")
    assert get_frame(10) == b"kamera-10"
    assert get_frame(20) == b"kamera-20"
