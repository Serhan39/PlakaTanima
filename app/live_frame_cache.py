"""Kameralarin en son yakalanan karesini bellekte tutan basit bir onbellek.

Canli kamera izgarasi, her istekte RTSP'ye yeniden baglanmak yerine (bu,
el sikisma + anahtar kare bekleme yuzunden 1-3 saniye surebilir ve
"donarak gosterme" hissi yaratir) buradan anlik olarak okur. Kareyi buraya
yazan taraf app/camera_worker.py'dir - zaten tespit icin actigi TEK RTSP
baglantisini yeniden kullanir, ekstra kamera baglantisi acmaz.

Tek uvicorn sureci varsayimiyla (docker-compose'da --workers kullanilmiyor)
process-ici bellek yeterlidir, ayri bir cache servisine (Redis vb.) gerek yok."""

import threading
import time

_lock = threading.Lock()
_frames: dict[int, tuple[bytes, float]] = {}


def set_frame(camera_id: int, jpeg_bytes: bytes) -> None:
    with _lock:
        _frames[camera_id] = (jpeg_bytes, time.monotonic())


def get_frame(camera_id: int) -> bytes | None:
    with _lock:
        entry = _frames.get(camera_id)
    return entry[0] if entry else None
