"""Bir aracin kamera onunden gecisi surerken, ayni plaka icin ardisik
birkac kare (worker CAPTURE_INTERVAL_SECONDS=2sn'de bir tespit dener,
yani bir arac ~10-12sn goruntude kalirsa 5-6 deneme birikir) BAGIMSIZ
OKUMALAR olarak tek tek kaydedilmek yerine, kisa sureli bir "patlama"
(burst) havuzunda toplanir; havuz suresi dolunca EN COK TEKRAR EDEN
okuma (cogunluk oylamasi) TEK bir DetectionLog olarak kaydedilir.

Neden: tek kare guveni (kutu+OCR ortalamasi) gercek kamera goruntusunde
dogru/yanlis okumalari guvenilir sekilde ayirt etmiyor (orn. dogru
"07 BAF 140" da, yanlis "07 BRE 10" da ~%40-42 kombine guvenle geldi).
Amaayni gecis icindeki BIRDEN FAZLA denemede, dogru okuma genelde
yanlislardan daha SIK tekrarlanir (OCR hatalari rastgele/degisken
olma egilimindedir) - bu yuzden cogunluk oylamasi, tek kare guveninden
daha guvenilir bir sinyal saglar.

Tamamen bellek ici (islem yeniden baslarsa aktif patlamalar kaybolur -
kabul edilebilir, cunku en fazla birkaç saniyelik veri kaybi olur ve
zaten arac hala goruntudeyken bir sonraki kare yeni bir patlama baslatir).
"""

import os
import threading
import time
from collections import Counter
from dataclasses import dataclass, field

from app.models import WatchlistCategory

BURST_GAP_SECONDS = float(os.environ.get("DETECTION_BURST_GAP_SECONDS", "4"))
BURST_MAX_SECONDS = float(os.environ.get("DETECTION_BURST_MAX_SECONDS", "20"))


@dataclass
class _Candidate:
    plate: str
    confidence: float
    snapshot_path: str
    matched_category: WatchlistCategory | None


@dataclass
class _Burst:
    first_seen: float
    last_seen: float
    candidates: list[_Candidate] = field(default_factory=list)


@dataclass
class FinalizedDetection:
    camera_id: int
    plate: str
    confidence: float
    snapshot_path: str
    matched_category: WatchlistCategory | None
    candidate_count: int


_lock = threading.Lock()
_bursts: dict[int, _Burst] = {}


def add_burst_candidate(
    camera_id: int,
    plate: str,
    confidence: float,
    snapshot_path: str,
    matched_category: WatchlistCategory | None,
) -> None:
    now = time.monotonic()
    with _lock:
        burst = _bursts.get(camera_id)
        if burst is None:
            burst = _Burst(first_seen=now, last_seen=now)
            _bursts[camera_id] = burst
        burst.last_seen = now
        burst.candidates.append(_Candidate(plate, confidence, snapshot_path, matched_category))


def pop_finalized_bursts() -> list[FinalizedDetection]:
    """Son adayindan beri BURST_GAP_SECONDS gecmis (arac goruntuden
    ayrilmis) ya da BURST_MAX_SECONDS'i asmis (guvenlik siniri - suresiz
    birikmesin) tum kamera patlamalarini sonuclandirir, havuzdan
    kaldirir ve dondurur. Cagrilmadigi surece havuzda bekler; /api/detect/image
    her tespit denemesinde (arac olsun olmasin, ~2sn'de bir) cagrildigi
    icin bu suresiz beklemeye yol acmaz."""
    now = time.monotonic()
    finalized: list[FinalizedDetection] = []
    with _lock:
        stale_camera_ids = [
            camera_id
            for camera_id, burst in _bursts.items()
            if now - burst.last_seen >= BURST_GAP_SECONDS or now - burst.first_seen >= BURST_MAX_SECONDS
        ]
        for camera_id in stale_camera_ids:
            burst = _bursts.pop(camera_id)
            finalized.append(_finalize(camera_id, burst))
    return finalized


def _finalize(camera_id: int, burst: _Burst) -> FinalizedDetection:
    counts = Counter(c.plate for c in burst.candidates)
    winning_plate, _ = counts.most_common(1)[0]
    winning_candidates = [c for c in burst.candidates if c.plate == winning_plate]
    best = max(winning_candidates, key=lambda c: c.confidence)
    all_plates = [c.plate for c in burst.candidates]
    print(
        f"[detect] Kamera {camera_id}: {len(burst.candidates)} aday toplandi {all_plates}, "
        f"kazanan='{winning_plate}' ({len(winning_candidates)} oy, guven={best.confidence:.2f}) - kaydediliyor"
    )
    return FinalizedDetection(
        camera_id=camera_id,
        plate=winning_plate,
        confidence=best.confidence,
        snapshot_path=best.snapshot_path,
        matched_category=best.matched_category,
        candidate_count=len(winning_candidates),
    )
