import os
import threading
import time
from unittest.mock import MagicMock, patch

import requests

os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("WATCHLIST_ENCRYPTION_KEY", "Gz3n5J9y8k2p6xQm1wZ7fL0oR4sT8vU2cA6bD9eH3iM=")

import app.equipment_gate_worker as equipment_gate_worker


def _fake_capture():
    cap = MagicMock()
    cap.isOpened.return_value = True
    cap.read.return_value = (True, "sahte-kare")
    return cap


def _run_with_stop_event(target, args, run_seconds: float) -> threading.Thread:
    equipment_gate_worker._stop_event.clear()
    thread = threading.Thread(target=target, args=args, daemon=True)
    thread.start()
    time.sleep(run_seconds)
    equipment_gate_worker._stop_event.set()
    thread.join(timeout=4)
    return thread


def test_login_with_retry_survives_transient_connection_errors():
    attempts = {"count": 0}

    def flaky_login():
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise requests.exceptions.ConnectionError("api henuz hazir degil")
        return "gercek-token"

    with patch.object(equipment_gate_worker, "_login", side_effect=flaky_login), \
         patch("app.equipment_gate_worker.time.sleep"):
        token = equipment_gate_worker._login_with_retry()

    assert token == "gercek-token"
    assert attempts["count"] == 3


def test_reader_loop_keeps_reading_even_if_processing_would_be_slow():
    # Regresyon testi: eskiden tek bir dongude okuma+tespit(ONNX)+OCR+
    # sleep(frame_interval) yapiliyordu - isleme suresi RTSP okumasini
    # doğrudan geciktiriyordu. Bu da (kapida gozlemlenen %360+ CPU'nun
    # kok nedeni) RTSP arka bellegi surekli birikip FFmpeg'in bunu telafi
    # etmeye calismasina yol aciyordu. _reader_loop artik SADECE okur -
    # asla isleme icin beklemez, capture.read() kisa surede cok kez
    # cagrilmis olmali.
    cap = _fake_capture()
    latest: dict = {"frame": None}
    frame_lock = threading.Lock()
    gate = {"id": 1, "name": "Test Kapi", "rtsp_url": "rtsp://sahte"}

    with patch("app.equipment_gate_worker.cv2.VideoCapture", return_value=cap):
        thread = _run_with_stop_event(
            equipment_gate_worker._reader_loop, (gate, latest, frame_lock), run_seconds=0.2
        )

    assert not thread.is_alive()
    assert cap.read.call_count > 20
    assert latest["frame"] == "sahte-kare"


def test_gate_loop_submits_crossing_when_tracker_detects_one():
    # Aracin cizgiyi gectigini simule ediyoruz: ilk tespit cizginin bir
    # tarafinda, ikinci tespit diger tarafinda - LineCrossingTracker bunu
    # bir gecis olarak isaretlemeli ve _submit_crossing cagrilmali.
    gate = {
        "id": 7,
        "name": "Test Kapi",
        "rtsp_url": "rtsp://sahte",
        "line_x1": 0.5, "line_y1": 0.0, "line_x2": 0.5, "line_y2": 1.0,
        "inside_x": 0.9, "inside_y": 0.5,
    }

    frames = [
        MagicMock(shape=(100, 200, 3)),  # arac cizginin solunda (disarida)
        MagicMock(shape=(100, 200, 3)),  # arac cizginin sagina gecti (icerisi)
    ]
    detect_calls = {"count": 0}

    class _FakeBox:
        def __init__(self, x1, y1, x2, y2):
            self.x1, self.y1, self.x2, self.y2 = x1, y1, x2, y2

        def crop(self, frame):
            return MagicMock(size=100)

    def fake_detect(frame):
        detect_calls["count"] += 1
        # cizgi x=0.5'te (genislik 200px -> piksel 100); track'in AYNI
        # nesne sayilip eslesebilmesi icin (match_distance=0.15) iki kare
        # arasindaki merkez farki kucuk tutulur: ilk kare cizginin hafif
        # solunda (cx=0.45), ikincisi hafif saginda (cx=0.55) - cizgiyi
        # yeni gecmis sayilmali.
        x_center = 90 if detect_calls["count"] == 1 else 110
        return [_FakeBox(x_center - 10, 40, x_center + 10, 60)]

    fake_detector = MagicMock()
    fake_detector.detect.side_effect = fake_detect

    # _gate_loop kendi ic "latest" degiskenini _reader_loop'a paylasir;
    # gercek RTSP okumasi yerine, latest["frame"]'i disaridan biz
    # besleyen sahte bir _reader_loop kullaniyoruz.
    def fake_reader(gate_arg, latest, frame_lock):
        for frame in frames:
            with frame_lock:
                latest["frame"] = frame
            time.sleep(0.03)
        while not equipment_gate_worker._stop_event.is_set():
            time.sleep(0.01)

    equipment_gate_worker.TRACKER_FPS = 50  # testin hizli bitmesi icin

    with patch.object(equipment_gate_worker, "build_default_detector", return_value=fake_detector), \
         patch.object(equipment_gate_worker, "read_equipment_code", return_value=("ABC123", 0.9)), \
         patch.object(equipment_gate_worker, "_reader_loop", side_effect=fake_reader), \
         patch.object(equipment_gate_worker, "_preview_loop"), \
         patch.object(equipment_gate_worker, "_submit_live_state"), \
         patch.object(equipment_gate_worker, "_submit_crossing") as mock_submit:

        equipment_gate_worker._stop_event.clear()
        thread = threading.Thread(target=equipment_gate_worker._gate_loop, args=(gate, lambda: "tok"), daemon=True)
        thread.start()
        time.sleep(0.3)
        equipment_gate_worker._stop_event.set()
        thread.join(timeout=4)

    assert not thread.is_alive()
    assert mock_submit.called
    submitted_code = mock_submit.call_args[0][2]
    assert submitted_code == "ABC123"


def test_gate_loop_reports_live_box_state_with_crossed_flag():
    # Panelde canli goruntude aracin kutusu sari (henuz gecmedi) -> yesil
    # (cizgiyi gecti) olarak boyanabilmesi icin, her isleme adiminda o an
    # gorulen tum izlerin kutulari + crossed durumu bildirilmeli.
    gate = {
        "id": 9,
        "name": "Test Kapi 2",
        "rtsp_url": "rtsp://sahte",
        "line_x1": 0.5, "line_y1": 0.0, "line_x2": 0.5, "line_y2": 1.0,
        "inside_x": 0.9, "inside_y": 0.5,
    }

    frames = [MagicMock(shape=(100, 200, 3))]

    class _FakeBox:
        def __init__(self, x1, y1, x2, y2):
            self.x1, self.y1, self.x2, self.y2 = x1, y1, x2, y2

        def crop(self, frame):
            return MagicMock(size=100)

    fake_detector = MagicMock()
    fake_detector.detect.return_value = [_FakeBox(80, 40, 100, 60)]  # cizginin solunda, henuz gecmedi

    def fake_reader(gate_arg, latest, frame_lock):
        for frame in frames:
            with frame_lock:
                latest["frame"] = frame
            time.sleep(0.03)
        while not equipment_gate_worker._stop_event.is_set():
            time.sleep(0.01)

    equipment_gate_worker.TRACKER_FPS = 50

    with patch.object(equipment_gate_worker, "build_default_detector", return_value=fake_detector), \
         patch.object(equipment_gate_worker, "read_equipment_code", return_value=("XYZ999", 0.7)), \
         patch.object(equipment_gate_worker, "_reader_loop", side_effect=fake_reader), \
         patch.object(equipment_gate_worker, "_preview_loop"), \
         patch.object(equipment_gate_worker, "_submit_crossing"), \
         patch.object(equipment_gate_worker, "_submit_live_state") as mock_live_state:

        equipment_gate_worker._stop_event.clear()
        thread = threading.Thread(target=equipment_gate_worker._gate_loop, args=(gate, lambda: "tok"), daemon=True)
        thread.start()
        time.sleep(0.15)
        equipment_gate_worker._stop_event.set()
        thread.join(timeout=4)

    assert not thread.is_alive()
    assert mock_live_state.called
    _, gate_id, boxes = mock_live_state.call_args[0]
    assert gate_id == 9
    assert len(boxes) == 1
    assert boxes[0]["crossed"] is False
    assert boxes[0]["code"] == "XYZ999"
    assert len(boxes[0]["box"]) == 4
