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
_tokens: dict[str, tuple[int | str, float]] = {}  # token -> (kaynak anahtari, olusturulma_zamani)


def mint_token(key: int | str) -> str:
    """`key`, kameralar icin camera_id (int), kapilar icin "gate-{gate_id}"
    (str) olabilir - akis ucu hangi kaynagi acacagini bu anahtardan bulur."""
    token = secrets.token_urlsafe(32)
    with _lock:
        _tokens[token] = (key, time.monotonic())
        _prune_expired_locked()
    return token


def resolve_token(token: str) -> int | str | None:
    """Token gecerliyse ilgili kaynak anahtarini dondurur, degilse None.
    Tek kullanimlik degildir (bir <img> yeniden baglanirsa - orn. aginin
    kisa kesintisinde - ayni token'i tekrar kullanabilir)."""
    with _lock:
        entry = _tokens.get(token)
        if entry is None:
            return None
        key, created_at = entry
        if time.monotonic() - created_at > _TOKEN_TTL_SECONDS:
            del _tokens[token]
            return None
        return key


def _prune_expired_locked() -> None:
    now = time.monotonic()
    expired = [t for t, (_, created_at) in _tokens.items() if now - created_at > _TOKEN_TTL_SECONDS]
    for t in expired:
        del _tokens[t]
