"""Her aktif kamera icin SUREKLI ACIK bir RTSP baglantisi tutan bagimsiz
worker sureci. `python -m app.camera_worker` ile veya docker-compose
icindeki `worker` servisiyle calistirilir; boylece kamera yakalama yuku
web/API surecinden izole edilir ve yatayda olceklenebilir.

Onceki surumde her dongude kamera basina YENIDEN baglaniliyordu; bunu
kalici baglantiya cevirdigimiz ILK denemede kritik bir hata vardi: kare
okuma dongusu, aninda gonderilmesi gereken HTTP isteklerini (onizleme +
OZELLIKLE OCR tespiti - bu saniyeler surebilir) kendi icinde, SENKRON
olarak yapiyordu. Bu, dongunun bir sonraki capture.read() cagrisini
geciktiriyor; RTSP soket arabellegi bu sure icinde dolup taskiyor ve
sonuc olarak kamera "neredeyse hic yeni kare gostermeme, hep ayni karede
takili kalma" seklinde davranmaya basliyordu (onceki her-dongude-yeniden-
baglan yontemi, her seferinde SIFIRDAN basladigi icin bu sorunu yasamiyordu).

Duzeltme: OKUMA ve GONDERME islemleri artik AYRI iki dongude (ayri thread)
calisiyor. Okuma dongusu SADECE capture.read() yapip en son kareyi paylasilan
bir degiskende tutuyor - asla ag/HTTP beklemez, boylece RTSP arabellegi
surekli bosaltilmis olur. Gonderme dongusu ise periyodik olarak (PREVIEW_
INTERVAL_SECONDS) en son kareyi alip onizleme onbellegine, daha seyrek
olarak da (CAPTURE_INTERVAL_SECONDS) tespite gonderir - bu HTTP cagrilari
ne kadar surerse sursun, okuma dongusunu ASLA bloke etmez."""

import os
import threading
import time

import cv2
import requests

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")
WORKER_USERNAME = os.environ.get("WORKER_USERNAME", "")
WORKER_PASSWORD = os.environ.get("WORKER_PASSWORD", "")
DETECT_INTERVAL_SECONDS = float(os.environ.get("CAPTURE_INTERVAL_SECONDS", "2"))
PREVIEW_INTERVAL_SECONDS = float(os.environ.get("PREVIEW_INTERVAL_SECONDS", "0.1"))
PREVIEW_JPEG_QUALITY = int(os.environ.get("PREVIEW_JPEG_QUALITY", "70"))
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


def _is_active(camera_id: int) -> bool:
    with _lock:
        return camera_id in _active_camera_ids


def _sender_loop(camera_id: int, latest: dict, frame_lock: threading.Lock, get_token) -> None:
    """RTSP okuma dongusunden tamamen bagimsiz calisir; boylece HTTP/OCR
    gecikmesi asla kare okumayi bloke etmez ve RTSP arabellegi taze kalir.

    Onizleme ve tespit icin AYRI JPEG kodlamalari kullanilir: onizleme
    dusuk kalitede (PREVIEW_JPEG_QUALITY, varsayilan 70) - kucuk dosya =
    daha hizli yukleme = panelde daha akici gorunum; tespit ise OCR
    dogrulugu icin tam kalitede kalir, akiciliktan etkilenmez."""
    last_detect = 0.0
    while _is_active(camera_id):
        time.sleep(PREVIEW_INTERVAL_SECONDS)
        with frame_lock:
            frame = latest["frame"]
        if frame is None:
            continue

        token = get_token()

        ok, preview_buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), PREVIEW_JPEG_QUALITY])
        if ok:
            _push_preview(camera_id, preview_buffer.tobytes(), token)

        now = time.monotonic()
        if now - last_detect >= DETECT_INTERVAL_SECONDS:
            last_detect = now
            ok, detect_buffer = cv2.imencode(".jpg", frame)
            if ok:
                _submit_detection(camera_id, detect_buffer.tobytes(), token)


def _camera_loop(camera: dict, get_token) -> None:
    camera_id = camera["id"]
    print(f"[worker] Baglaniliyor: {camera['name']} ({camera['rtsp_url']})")
    capture = cv2.VideoCapture(camera["rtsp_url"])

    latest: dict = {"frame": None}
    frame_lock = threading.Lock()
    sender = threading.Thread(target=_sender_loop, args=(camera_id, latest, frame_lock, get_token), daemon=True)
    sender.start()

    while _is_active(camera_id):
        ok, frame = capture.read()
        if not ok:
            print(f"[worker] Kare alinamadi: {camera['name']}, yeniden baglaniliyor...")
            capture.release()
            time.sleep(2)
            capture = cv2.VideoCapture(camera["rtsp_url"])
            continue

        with frame_lock:
            latest["frame"] = frame

    capture.release()
    sender.join(timeout=PREVIEW_INTERVAL_SECONDS + 2)
    print(f"[worker] Izleme durduruldu: {camera['name']} (kamera artik pasif/silinmis)")


def _login_with_retry() -> str:
    """Docker Compose'da 'depends_on: api' sadece api KONTEYNERININ
    baslamis olmasini garanti eder, icindeki uvicorn'un istek almaya HAZIR
    oldugunu degil (ozellikle DB migrasyonlari suren ilk acilista birkac
    saniye surebilir). Bu yuzden ilk giris denemesi basarisiz olursa
    surece cokup Docker'in (giderek yavaslayan) yeniden baslatma
    politikasina guvenmek yerine, burada kendimiz kisa araliklarla
    tekrar deneriz."""
    delay = 2.0
    while True:
        try:
            return _login()
        except requests.RequestException as exc:
            print(f"[worker] API'ye giris yapilamadi ({exc}), {delay:.0f}sn sonra tekrar denenecek...")
            time.sleep(delay)
            delay = min(delay * 1.5, 30.0)


def main() -> None:
    if not WORKER_USERNAME or not WORKER_PASSWORD:
        raise SystemExit("WORKER_USERNAME ve WORKER_PASSWORD ortam degiskenleri gerekli")

    token_holder = {"value": _login_with_retry(), "at": time.monotonic()}

    def get_token() -> str:
        if time.monotonic() - token_holder["at"] > 3600:
            token_holder["value"] = _login_with_retry()
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
