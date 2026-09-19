"""Is makinesi takip ozelligi icin: her aktif kapi kamerasindan periyodik
kare yakalayip /api/equipment/detect/image ucuna gonderen bagimsiz worker
sureci. `python -m app.equipment_gate_worker` ile calistirilir. Ozellik
panelden kapatilmis olsa bile bu worker calisirsa gecisleri islemeye devam
eder - sadece panel sekmesinin gorunurlugunu etkiler."""

import os
import time

import cv2
import requests

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")
WORKER_USERNAME = os.environ.get("EQUIPMENT_WORKER_USERNAME", os.environ.get("WORKER_USERNAME", ""))
WORKER_PASSWORD = os.environ.get("EQUIPMENT_WORKER_PASSWORD", os.environ.get("WORKER_PASSWORD", ""))
CAPTURE_INTERVAL_SECONDS = float(os.environ.get("EQUIPMENT_CAPTURE_INTERVAL_SECONDS", "3"))


def _login() -> str:
    response = requests.post(
        f"{API_BASE_URL}/api/auth/login",
        data={"username": WORKER_USERNAME, "password": WORKER_PASSWORD},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def _fetch_gates(token: str) -> list[dict]:
    response = requests.get(f"{API_BASE_URL}/api/equipment/gates", headers={"Authorization": f"Bearer {token}"}, timeout=10)
    response.raise_for_status()
    return [g for g in response.json() if g["is_active"] and g["rtsp_url"]]


def _process_gate(gate: dict, token: str) -> None:
    capture = cv2.VideoCapture(gate["rtsp_url"])
    ok, frame = capture.read()
    capture.release()
    if not ok:
        print(f"[equipment-worker] Kare alinamadi: {gate['name']} ({gate['rtsp_url']})")
        return

    ok, buffer = cv2.imencode(".jpg", frame)
    if not ok:
        return

    requests.post(
        f"{API_BASE_URL}/api/equipment/detect/image",
        params={"gate_id": gate["id"]},
        files={"file": ("frame.jpg", buffer.tobytes(), "image/jpeg")},
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )


def main() -> None:
    if not WORKER_USERNAME or not WORKER_PASSWORD:
        # Is Makinasi Takip ozelligi varsayilan olarak kapali/opsiyoneldir;
        # kimlik bilgisi tanimlanana kadar sessizce bekler, docker-compose
        # icinde varsayilan bir servis olarak crash-loop yapmadan durabilir.
        # .env doldurulduktan sonra `docker compose restart equipment-worker`.
        print("[equipment-worker] EQUIPMENT_WORKER_USERNAME/PASSWORD tanimli degil, bekleniyor...")
        while True:
            time.sleep(3600)

    token = _login()
    last_login = time.monotonic()

    while True:
        if time.monotonic() - last_login > 3600:
            token = _login()
            last_login = time.monotonic()

        try:
            for gate in _fetch_gates(token):
                _process_gate(gate, token)
        except requests.HTTPError as exc:
            print(f"[equipment-worker] API hatasi: {exc}")

        time.sleep(CAPTURE_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
