import os
import threading
import time
from unittest.mock import MagicMock, patch

import requests

os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("WATCHLIST_ENCRYPTION_KEY", "Gz3n5J9y8k2p6xQm1wZ7fL0oR4sT8vU2cA6bD9eH3iM=")

import app.camera_worker as camera_worker


def test_login_with_retry_survives_transient_connection_errors():
    # Docker Compose'da 'depends_on: api' konteynerin baslamis olmasini
    # garanti eder ama icindeki uvicorn'un istek almaya hazir oldugunu
    # garanti etmez - bu yuzden ilk birkac giris denemesi basarisiz olabilir.
    # _login_with_retry, cokup Docker'in yeniden baslatmasina guvenmek
    # yerine bunu kendi icinde atlatabilmeli.
    attempts = {"count": 0}

    def flaky_login():
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise requests.exceptions.ConnectionError("api henuz hazir degil")
        return "gercek-token"

    with patch.object(camera_worker, "_login", side_effect=flaky_login), \
         patch("app.camera_worker.time.sleep"):  # testte gercekten beklemeyelim
        token = camera_worker._login_with_retry()

    assert token == "gercek-token"
    assert attempts["count"] == 3


def _fake_capture():
    """Her cagrida basarili bir kare dondurmeye devam eden sahte VideoCapture."""
    cap = MagicMock()
    cap.read.return_value = (True, "sahte-kare")
    return cap


def test_camera_loop_pushes_preview_more_often_than_detection():
    # PREVIEW_INTERVAL_SECONDS kucuk, DETECT_INTERVAL_SECONDS daha buyuk
    # olmali - yani onizleme, tespitten daha sik tetiklenmeli.
    camera_worker.PREVIEW_INTERVAL_SECONDS = 0.01
    camera_worker.DETECT_INTERVAL_SECONDS = 0.2

    with camera_worker._lock:
        camera_worker._active_camera_ids.add(1)

    with patch("app.camera_worker.cv2.VideoCapture", return_value=_fake_capture()), \
         patch("app.camera_worker.cv2.imencode", return_value=(True, MagicMock(tobytes=lambda: b"jpeg"))), \
         patch.object(camera_worker, "_push_preview") as mock_preview, \
         patch.object(camera_worker, "_submit_detection") as mock_detect:

        thread = threading.Thread(
            target=camera_worker._camera_loop,
            args=({"id": 1, "name": "Test", "rtsp_url": "rtsp://sahte"}, lambda: "tok"),
            daemon=True,
        )
        thread.start()
        time.sleep(0.25)
        with camera_worker._lock:
            camera_worker._active_camera_ids.discard(1)
        thread.join(timeout=4)  # _camera_loop, sender thread'inin kapanmasini da bekler

    assert not thread.is_alive()  # kamera pasif olunca dongu durmali
    assert mock_preview.call_count > mock_detect.call_count
    assert mock_detect.call_count >= 1


def test_slow_detection_does_not_stall_frame_reading():
    # Regresyon testi: ilk "kalici baglanti" denemesinde, onizleme/tespit
    # HTTP cagrilari (ozellikle OCR) kare okuma donguSUnun ICINDE senkron
    # yapiliyordu - bu da RTSP arabelleginin dolup kameranin "hep ayni
    # karede takili kalmasi" ile sonuclaniyordu. capture.read() cagri
    # sayisinin, YAVAS bir tespit/onizleme cagrisina ragmen dusuk
    # kalmamasi gerekir (okuma dongusu HTTP'yi beklememeli).
    camera_worker.PREVIEW_INTERVAL_SECONDS = 0.01
    camera_worker.DETECT_INTERVAL_SECONDS = 0.05

    with camera_worker._lock:
        camera_worker._active_camera_ids.add(3)

    def slow_push(*args, **kwargs):
        time.sleep(0.2)  # yavas bir ag/OCR cagrisini simule eder

    cap = _fake_capture()

    with patch("app.camera_worker.cv2.VideoCapture", return_value=cap), \
         patch("app.camera_worker.cv2.imencode", return_value=(True, MagicMock(tobytes=lambda: b"jpeg"))), \
         patch.object(camera_worker, "_push_preview", side_effect=slow_push), \
         patch.object(camera_worker, "_submit_detection"):

        thread = threading.Thread(
            target=camera_worker._camera_loop,
            args=({"id": 3, "name": "Test3", "rtsp_url": "rtsp://sahte3"}, lambda: "tok"),
            daemon=True,
        )
        thread.start()
        time.sleep(0.3)
        with camera_worker._lock:
            camera_worker._active_camera_ids.discard(3)
        thread.join(timeout=4)

    assert not thread.is_alive()
    # Okuma donguSu HTTP'yi beklemedigi icin 0.3sn'de onlarca kez
    # cagrilmis olmali (mock capture pratikte aninda doner); yavas
    # gonderme cagrisi bunu bloke etseydi bu sayi 1-2'de kalirdi.
    assert cap.read.call_count > 20


def test_camera_loop_stops_immediately_when_camera_not_active():
    # Kamera hic active listesine eklenmezse dongu ilk kontrolde cikmali.
    with camera_worker._lock:
        camera_worker._active_camera_ids.discard(2)

    with patch("app.camera_worker.cv2.VideoCapture", return_value=_fake_capture()):
        thread = threading.Thread(
            target=camera_worker._camera_loop,
            args=({"id": 2, "name": "Test2", "rtsp_url": "rtsp://sahte2"}, lambda: "tok"),
            daemon=True,
        )
        thread.start()
        thread.join(timeout=2)

    assert not thread.is_alive()
