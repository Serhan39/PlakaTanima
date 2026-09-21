"""Her aktif kamera icin SUREKLI ACIK bir RTSP baglantisi tutan bagimsiz
worker sureci. `python -m app.camera_worker` ile veya docker-compose
icindeki `worker` servisiyle calistirilir; boylece kamera yakalama yuku
web/API surecinden izole edilir ve yatayda olceklenebilir.

Onceki surumde her dongude kamera basina YENIDEN baglaniliyordu
(cv2.VideoCapture ac -> tek kare oku -> kapat); RTSP el sikismasi + ilk
anahtar kareyi bekleme kamera/aga gore 1-3 saniye surebildigi icin bu,
panelin "Canli Kameralar" izgarasinda atlayarak/donarak gorunmesine yol
aciyordu. Simdi her kamera icin baglanti BIR KERE aciliyor ve surekli
okunuyor (app/equipment_gate_worker.py'deki gecit izleme mantigiyla
ayni desen); okunan her kare canli onizleme onbellegine (PREVIEW_INTERVAL_SECONDS
siklikla) gonderiliyor, tespit ise ayri ve daha seyrek bir siklikla
(CAPTURE_INTERVAL_SECONDS) calisiyor - boylece onizleme akiciligi ile
tespit yuku birbirinden bagimsiz ayarlanabiliyor."""

import os
import threading
import time

import cv2
import requests

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")
WORKER_USERNAME = os.environ.get("WORKER_USERNAME", "")
WORKER_PASSWORD = os.environ.get("WORKER_PASSWORD", "")
DETECT_INTERVAL_SECONDS = float(os.environ.get("CAPTURE_INTERVAL_SECONDS", "2"))
PREVIEW_INTERVAL_SECONDS = float(os.environ.get("PREVIEW_INTERVAL_SECONDS", "0.5"))
CAMERA_LIST_REFRESH_SECONDS = float(os.environ.get("CAMERA_LIST_REFRESH_SECONDS", "10"))

_lock = threading.Lock()
_active_camera_ids: set[int] = set()


def _login() -> str:
    response = requests.post(
        f"{API_BASE_URL}/api/auth/login",
        data={"username": WORKER_USERNAME, "password": WORKER_PASSWORD},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def _fetch_cameras(token: str) -> list[dict]:
    response = requests.get(f"{API_BASE_URL}/api/cameras", headers={"Authorization": f"Bearer {token}"}, timeout=10)
    response.raise_for_status()
    return [c for c in response.json() if c["is_active"] and c["rtsp_url"]]


def _push_preview(camera_id: int, jpeg_bytes: bytes, token: str) -> None:
    try:
        requests.post(
            f"{API_BASE_URL}/api/cameras/{camera_id}/live-frame",
            files={"file": ("frame.jpg", jpeg_bytes, "image/jpeg")},
            headers={"Authorization": f"Bearer {token}"},
            timeout=5,
        )
    except requests.RequestException:
        pass  # canli onizleme ikincil ozellik, hata tespit akisini kesmemeli


def _submit_detection(camera_id: int, jpeg_bytes: bytes, token: str) -> None:
    try:
        requests.post(
            f"{API_BASE_URL}/api/detect/image",
            params={"camera_id": camera_id},
            files={"file": ("frame.jpg", jpeg_bytes, "image/jpeg")},
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
    except requests.RequestException as exc:
        print(f"[worker] Tespit gonderilemedi (kamera {camera_id}): {exc}")


def _camera_loop(camera: dict, get_token) -> None:
    camera_id = camera["id"]
    print(f"[worker] Baglaniliyor: {camera['name']} ({camera['rtsp_url']})")
    capture = cv2.VideoCapture(camera["rtsp_url"])
    last_preview = 0.0
    last_detect = 0.0

    while True:
        with _lock:
            if camera_id not in _active_camera_ids:
                break

        ok, frame = capture.read()
        if not ok:
            print(f"[worker] Kare alinamadi: {camera['name']}, yeniden baglaniliyor...")
            capture.release()
            time.sleep(2)
            capture = cv2.VideoCapture(camera["rtsp_url"])
            continue

        now = time.monotonic()
        if now - last_preview >= PREVIEW_INTERVAL_SECONDS:
            last_preview = now
            ok, buffer = cv2.imencode(".jpg", frame)
            if ok:
                jpeg_bytes = buffer.tobytes()
                token = get_token()
                _push_preview(camera_id, jpeg_bytes, token)
                if now - last_detect >= DETECT_INTERVAL_SECONDS:
                    last_detect = now
                    _submit_detection(camera_id, jpeg_bytes, token)

    capture.release()
    print(f"[worker] Izleme durduruldu: {camera['name']} (kamera artik pasif/silinmis)")


def main() -> None:
    if not WORKER_USERNAME or not WORKER_PASSWORD:
        raise SystemExit("WORKER_USERNAME ve WORKER_PASSWORD ortam degiskenleri gerekli")

    token_holder = {"value": _login(), "at": time.monotonic()}

    def get_token() -> str:
        if time.monotonic() - token_holder["at"] > 3600:
            token_holder["value"] = _login()
            token_holder["at"] = time.monotonic()
        return token_holder["value"]

    threads: dict[int, threading.Thread] = {}

    while True:
        try:
            cameras = _fetch_cameras(get_token())
        except requests.RequestException as exc:
            print(f"[worker] Kamera listesi alinamadi: {exc}")
            cameras = []

        with _lock:
            _active_camera_ids.clear()
            _active_camera_ids.update(c["id"] for c in cameras)

        for camera in cameras:
            if camera["id"] not in threads or not threads[camera["id"]].is_alive():
                thread = threading.Thread(target=_camera_loop, args=(camera, get_token), daemon=True)
                threads[camera["id"]] = thread
                thread.start()

        time.sleep(CAMERA_LIST_REFRESH_SECONDS)


if __name__ == "__main__":
    main()
