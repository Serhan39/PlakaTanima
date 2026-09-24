"""Kameralarin en son yakalanan karesini bellekte tutan basit bir onbellek.

Canli kamera izgarasi, her istekte RTSP'ye yeniden baglanmak yerine (bu,
el sikisma + anahtar kare bekleme yuzunden 1-3 saniye surebilir ve
"donarak gosterme" hissi yaratir) buradan anlik olarak okur. Kareyi buraya
yazan taraf app/camera_worker.py'dir - zaten tespit icin actigi TEK RTSP
baglantisini yeniden kullanir, ekstra kamera baglantisi acmaz.

Tek uvicorn sureci varsayimiyla (docker-compose'da --workers kullanilmiyor)
process-ici bellek yeterlidir, ayri bir cache servisine (Redis vb.) gerek yok.

Anahtar kameralar icin dogrudan camera_id (int), kapilar icin ise
"gate-{gate_id}" (str) seklindedir - iki farkli tablonun ID uzayi ayni
sozlukte karismasin diye."""

import threading
import time

_lock = threading.Lock()
_frames: dict[int | str, tuple[bytes, float]] = {}


def set_frame(key: int | str, jpeg_bytes: bytes) -> None:
    with _lock:
        _frames[key] = (jpeg_bytes, time.monotonic())


def get_frame(key: int | str) -> bytes | None:
    with _lock:
        entry = _frames.get(key)
    return entry[0] if entry else None
