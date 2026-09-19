"""Her aktif kamera icin RTSP akisindan periyodik kare yakalayip ana API'nin
/api/detect/image ucuna gonderen bagimsiz worker sureci. `python -m app.camera_worker`
ile veya docker-compose icindeki `worker` servisiyle calistirilir; boylece
kamera yakalama yuku web/API surecinden izole edilir ve yatayda olceklenebilir."""

import os
import time

import cv2
import requests

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")
WORKER_USERNAME = os.environ.get("WORKER_USERNAME", "")
WORKER_PASSWORD = os.environ.get("WORKER_PASSWORD", "")
CAPTURE_INTERVAL_SECONDS = float(os.environ.get("CAPTURE_INTERVAL_SECONDS", "2"))


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
    return [c for c in response.json() if c["is_active"]]


def _process_camera(camera: dict, token: str) -> None:
    capture = cv2.VideoCapture(camera["rtsp_url"])
    ok, frame = capture.read()
    capture.release()
    if not ok:
        print(f"[worker] Kare alinamadi: {camera['name']} ({camera['rtsp_url']})")
        return

    ok, buffer = cv2.imencode(".jpg", frame)
    if not ok:
        return

    requests.post(
        f"{API_BASE_URL}/api/detect/image",
        params={"camera_id": camera["id"]},
        files={"file": ("frame.jpg", buffer.tobytes(), "image/jpeg")},
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )


def main() -> None:
    if not WORKER_USERNAME or not WORKER_PASSWORD:
        raise SystemExit("WORKER_USERNAME ve WORKER_PASSWORD ortam degiskenleri gerekli")

    token = _login()
    last_login = time.monotonic()

    while True:
        if time.monotonic() - last_login > 3600:
            token = _login()
            last_login = time.monotonic()

        try:
            for camera in _fetch_cameras(token):
                _process_camera(camera, token)
        except requests.HTTPError as exc:
            print(f"[worker] API hatasi: {exc}")

        time.sleep(CAPTURE_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
