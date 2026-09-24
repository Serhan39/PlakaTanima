"""Is Makinasi Takip icin: her aktif kapinin RTSP akisini SUREKLI okuyup,
tespit edilen plakalari/kodlari kareler arasinda basit bir merkez-nokta
takibiyle izleyen ve panelde kapi icin cizilen sanal cizgiyi FIILEN gectigi
an bunu API'ye bildiren worker.

Neden boyle: kamera genis bir alani goruyorsa (sadece dar kapi bosluguna
degil), aracin goruntude "bulunmasi" ile kapidan "gecmesi" ayni sey
degildir. Bu worker, her kapi icin bagimsiz bir thread'de calisir, cizgiyi
gecen ilk kareyi yakalar ve o ana kadar okunmus en guvenilir plaka/kod ile
birlikte /api/equipment/crossings ucuna bildirir.

Ayni kapidan hem giren hem cikan arac olabilecegi icin yon sabit degildir:
panelde cizgiyle birlikte isaretlenen "icerisi" referans noktasina gore,
aracin gectikten sonraki tarafi o noktayla ayni tarafta ise GIRIS, degilse
CIKIS olarak API'ye acikca bildirilir (bkz. app/vision/tracker.py).

`python -m app.equipment_gate_worker` ile calistirilir (docker-compose'da
`equipment-worker` servisi).

Not: bir kapinin cizgisi panelden degistirildiginde, bu worker'in o
degisikligi almasi icin yeniden baslatilmasi gerekir (`docker compose
restart equipment-worker`) - kapi listesi periyodik olarak yenilenir ama
calisan bir thread'in cizgisi/gorevi thread basinda sabitlenir.
"""

import os
import threading
import time

import cv2
import requests

from app.models import CameraDirection
from app.vision.ocr import read_equipment_code
from app.vision.pipeline import build_default_detector
from app.vision.tracker import LineCrossingTracker, is_entry_crossing, side_of_line

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")
WORKER_USERNAME = os.environ.get("EQUIPMENT_WORKER_USERNAME", os.environ.get("WORKER_USERNAME", ""))
WORKER_PASSWORD = os.environ.get("EQUIPMENT_WORKER_PASSWORD", os.environ.get("WORKER_PASSWORD", ""))
TRACKER_FPS = float(os.environ.get("EQUIPMENT_TRACKER_FPS", "2"))
GATE_REFRESH_SECONDS = float(os.environ.get("EQUIPMENT_GATE_REFRESH_SECONDS", "60"))
MIN_CODE_LENGTH = int(os.environ.get("EQUIPMENT_MIN_CODE_LENGTH", "3"))
PREVIEW_INTERVAL_SECONDS = float(os.environ.get("EQUIPMENT_PREVIEW_INTERVAL_SECONDS", "0.2"))
PREVIEW_JPEG_QUALITY = int(os.environ.get("EQUIPMENT_PREVIEW_JPEG_QUALITY", "70"))

_stop_event = threading.Event()


def _login() -> str:
    response = requests.post(
        f"{API_BASE_URL}/api/auth/login",
        data={"username": WORKER_USERNAME, "password": WORKER_PASSWORD},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def _submit_crossing(token: str, gate_id: int, code: str, confidence: float, direction: CameraDirection) -> None:
    try:
        requests.post(
            f"{API_BASE_URL}/api/equipment/crossings",
            json={"gate_id": gate_id, "code": code, "confidence": confidence, "direction": direction.value},
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
    except requests.RequestException as exc:
        print(f"[equipment-worker] Gecis bildirilemedi (kapi {gate_id}): {exc}")


def _push_preview(gate_id: int, jpeg_bytes: bytes, token: str) -> None:
    """Panelin canli goruntu icin baglanacagi akisi besler (bkz.
    /api/equipment/gates/{gate_id}/stream, app/camera_worker.py'deki
    _push_preview ile ayni desen). Ikincil/gorsel bir ozelliktir - hata
    tespit/takip akisini asla kesmemeli."""
    try:
        requests.post(
            f"{API_BASE_URL}/api/equipment/gates/{gate_id}/live-frame",
            files={"file": ("frame.jpg", jpeg_bytes, "image/jpeg")},
            headers={"Authorization": f"Bearer {token}"},
            timeout=5,
        )
    except requests.RequestException:
        pass


def _submit_live_state(token: str, gate_id: int, boxes: list[dict]) -> None:
    """O an karede gorulen araclarin kutularini bildirir - panel bunu
    canli goruntunun uzerine sari (henuz gecmedi) / yesil (cizgiyi gecti)
    kutu olarak cizer. Ikincil/gorsel bir ozelliktir, hata sessizce yutulur."""
    try:
        requests.post(
            f"{API_BASE_URL}/api/equipment/gates/{gate_id}/live-state",
            json={"boxes": boxes},
            headers={"Authorization": f"Bearer {token}"},
            timeout=5,
        )
    except requests.RequestException:
        pass


def _preview_loop(gate: dict, latest: dict, frame_lock: threading.Lock, get_token) -> None:
    """Okuma dongusunden bagimsiz, sabit araliklarla (PREVIEW_INTERVAL_SECONDS)
    en son kareyi dusuk kalitede panelin canli goruntu akisina gonderir."""
    while not _stop_event.is_set():
        time.sleep(PREVIEW_INTERVAL_SECONDS)
        with frame_lock:
            frame = latest["frame"]
        if frame is None:
            continue
        ok, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), PREVIEW_JPEG_QUALITY])
        if ok:
            _push_preview(gate["id"], buffer.tobytes(), get_token())


def _reader_loop(gate: dict, latest: dict, frame_lock: threading.Lock) -> None:
    """RTSP okuma dongusunu isleme (tespit+OCR+takip) dongusunden AYIRIR -
    aynen camera_worker.py'deki nedenle: bu dongu SADECE capture.read()
    yapip en son kareyi paylasilan degiskende tutar, asla ONNX/OCR icin
    beklemez. Eskiden tek bir dongude okuma+isleme+sleep(frame_interval)
    yapiliyordu; bu, isleme suresi kadar RTSP'nin okunmadan kalmasina ve
    (FFmpeg/OpenCV arka planda biriken kareleri telafi etmeye calistigi
    icin) surekli yuksek CPU kullanimina yol aciyordu (gozlemlenen: bir
    kapi icin %360+ CPU)."""
    capture = cv2.VideoCapture(gate["rtsp_url"])
    while not _stop_event.is_set():
        if not capture.isOpened():
            print(f"[equipment-worker] RTSP acilamadi: {gate['name']} ({gate['rtsp_url']}), 10sn sonra tekrar denenecek")
            capture.release()
            time.sleep(10)
            capture = cv2.VideoCapture(gate["rtsp_url"])
            continue

        ok, frame = capture.read()
        if not ok:
            print(f"[equipment-worker] Akis kesildi: {gate['name']}, yeniden baglaniliyor")
            capture.release()
            time.sleep(2)
            capture = cv2.VideoCapture(gate["rtsp_url"])
            continue

        with frame_lock:
            latest["frame"] = frame

    capture.release()


def _gate_loop(gate: dict, get_token) -> None:
    detector = build_default_detector()  # her thread kendi ornegini kullanir (thread-guvenligi icin)
    line = (gate["line_x1"], gate["line_y1"], gate["line_x2"], gate["line_y2"])
    tracker = LineCrossingTracker(*line)
    inside_positive = side_of_line(gate["inside_x"], gate["inside_y"], *line) > 0
    frame_interval = 1.0 / max(TRACKER_FPS, 0.1)

    latest: dict = {"frame": None}
    frame_lock = threading.Lock()
    reader = threading.Thread(target=_reader_loop, args=(gate, latest, frame_lock), daemon=True)
    reader.start()
    preview = threading.Thread(target=_preview_loop, args=(gate, latest, frame_lock, get_token), daemon=True)
    preview.start()

    print(f"[equipment-worker] Kapi izleniyor (cizgi takibi): {gate['name']}")
    while not _stop_event.is_set():
        time.sleep(frame_interval)
        with frame_lock:
            frame = latest["frame"]
        if frame is None:
            continue

        height, width = frame.shape[:2]
        detections = []
        for box in detector.detect(frame):
            crop = box.crop(frame)
            if crop.size == 0:
                continue
            code, conf = read_equipment_code(crop)
            if code and len(code) < MIN_CODE_LENGTH:
                code = ""
            cx = ((box.x1 + box.x2) / 2) / width
            cy = ((box.y1 + box.y2) / 2) / height
            normalized_box = (box.x1 / width, box.y1 / height, box.x2 / width, box.y2 / height)
            detections.append((cx, cy, code, conf, normalized_box))

        for track in tracker.update(detections):
            direction = CameraDirection.ENTRY if is_entry_crossing(track.prev_side, inside_positive) else CameraDirection.EXIT
            if track.best_code:
                print(f"[equipment-worker] Cizgi gecisi tespit edildi: {gate['name']} -> {track.best_code} ({direction.value})")
                _submit_crossing(get_token(), gate["id"], track.best_code, track.best_confidence, direction)
            else:
                print(f"[equipment-worker] Cizgi gecisi tespit edildi ama plaka okunamadi: {gate['name']} ({direction.value})")

        live_boxes = [
            {"track_id": t.id, "box": list(t.box), "crossed": t.crossed, "code": t.best_code}
            for t in tracker.active_tracks()
            if t.box is not None
        ]
        _submit_live_state(get_token(), gate["id"], live_boxes)

    reader.join(timeout=2)
    preview.join(timeout=2)


def _login_with_retry() -> str:
    """Docker Compose'da 'depends_on: api' sadece api KONTEYNERININ
    baslamis olmasini garanti eder, icindeki uvicorn'un istek almaya HAZIR
    oldugunu degil. Ilk giris denemesi basarisiz olursa surece cokup
    Docker'in yeniden baslatma politikasina guvenmek yerine, kisa
    araliklarla kendimiz tekrar deneriz."""
    delay = 2.0
    while True:
        try:
            return _login()
        except requests.RequestException as exc:
            print(f"[equipment-worker] API'ye giris yapilamadi ({exc}), {delay:.0f}sn sonra tekrar denenecek...")
            time.sleep(delay)
            delay = min(delay * 1.5, 30.0)


def main() -> None:
    if not WORKER_USERNAME or not WORKER_PASSWORD:
        # Is Makinasi Takip ozelligi varsayilan olarak kapali/opsiyoneldir;
        # kimlik bilgisi tanimlanana kadar sessizce bekler, docker-compose
        # icinde varsayilan bir servis olarak crash-loop yapmadan durabilir.
        # .env doldurulduktan sonra `docker compose restart equipment-worker`.
        print("[equipment-worker] EQUIPMENT_WORKER_USERNAME/PASSWORD tanimli degil, bekleniyor...")
        while True:
            time.sleep(3600)

    token_holder = {"value": _login_with_retry(), "at": time.monotonic()}

    def get_token() -> str:
        if time.monotonic() - token_holder["at"] > 3600:
            token_holder["value"] = _login_with_retry()
            token_holder["at"] = time.monotonic()
        return token_holder["value"]

    threads: dict[int, threading.Thread] = {}

    while True:
        try:
            response = requests.get(
                f"{API_BASE_URL}/api/equipment/gates",
                headers={"Authorization": f"Bearer {get_token()}"},
                timeout=10,
            )
            response.raise_for_status()
            gates = [g for g in response.json() if g["is_active"] and g["rtsp_url"]]
        except requests.RequestException as exc:
            print(f"[equipment-worker] Kapi listesi alinamadi: {exc}")
            gates = []

        for gate in gates:
            if gate["id"] not in threads or not threads[gate["id"]].is_alive():
                thread = threading.Thread(target=_gate_loop, args=(gate, get_token), daemon=True)
                threads[gate["id"]] = thread
                thread.start()

        time.sleep(GATE_REFRESH_SECONDS)


if __name__ == "__main__":
    main()
