"""Canli kamera video akisi (MJPEG) icin kisa omurlu, dar yetkili token'lar.

`<img src="...">` etiketi ozel bir Authorization header'i tasiyamadigi
icin, tarayicinin dogrudan bagli olabilecegi akis ucu (/api/cameras/{id}/stream)
normal JWT yerine burada uretilen, SADECE tek bir kameranin goruntusunu
almaya yeten, kisa sureli bir token kabul eder. Token, once normal JWT ile
kimligi dogrulanmis bir istemciye (POST /api/cameras/{id}/stream-token)
verilir; boylece asil JWT hicbir zaman URL/tarayici gecmisine sizmaz."""

import secrets
import threading
import time

_TOKEN_TTL_SECONDS = 600  # 10 dakika - akis baglantisi kurulduktan sonra
                          # token'in kendisi suresi dolsa bile baglanti acik kalir

_lock = threading.Lock()
_tokens: dict[str, tuple[int, float]] = {}  # token -> (camera_id, olusturulma_zamani)


def mint_token(camera_id: int) -> str:
    token = secrets.token_urlsafe(32)
    with _lock:
        _tokens[token] = (camera_id, time.monotonic())
        _prune_expired_locked()
    return token


def resolve_token(token: str) -> int | None:
    """Token gecerliyse ilgili camera_id'yi dondurur, degilse None.
    Tek kullanimlik degildir (bir <img> yeniden baglanirsa - orn. aginin
    kisa kesintisinde - ayni token'i tekrar kullanabilir)."""
    with _lock:
        entry = _tokens.get(token)
        if entry is None:
            return None
        camera_id, created_at = entry
        if time.monotonic() - created_at > _TOKEN_TTL_SECONDS:
            del _tokens[token]
            return None
        return camera_id


def _prune_expired_locked() -> None:
    now = time.monotonic()
    expired = [t for t, (_, created_at) in _tokens.items() if now - created_at > _TOKEN_TTL_SECONDS]
    for t in expired:
        del _tokens[t]
