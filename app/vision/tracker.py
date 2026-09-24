"""Basit merkez-nokta (centroid) tabanli nesne takibi ve sanal cizgi gecis
tespiti. Agir bir tracking kutuphanesi (DeepSort/ByteTrack) gerektirmez;
tek seritlik kapi kameralari icin yeterlidir. Amac: kameranin genis bir
alani gordugu durumlarda, aracin sadece goruntude "bulunmasini" degil,
tanimlanan cizgiyi FIILEN gecmesini yakalamak."""

from dataclasses import dataclass, field


def side_of_line(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> float:
    """(px,py) noktasinin (x1,y1)-(x2,y2) cizgisine gore hangi tarafta oldugunu
    isaret eden bir deger dondurur (pozitif/negatif = taraf, 0 = cizgi uzerinde)."""
    return (x2 - x1) * (py - y1) - (y2 - y1) * (px - x1)


def is_entry_crossing(post_side: float, inside_positive: bool) -> bool:
    """Bir izin cizgiyi gectikten SONRAKI tarafi (post_side) ile, panelde
    isaretlenen 'icerisi' referans noktasinin tarafi (inside_positive)
    karsilastirilir. Ayni tarafta ise arac icini girmis (True/ENTRY),
    degilse disari cikmis (False/EXIT) demektir. Boylece tek bir kapi/
    kamera hem giren hem cikan araci ayirt edebilir."""
    return (post_side > 0) == inside_positive


@dataclass
class Track:
    id: int
    cx: float
    cy: float
    prev_side: float | None = None
    best_code: str = ""
    best_confidence: float = 0.0
    frames_since_seen: int = 0
    crossed: bool = False
    box: tuple[float, float, float, float] | None = None


@dataclass
class _Detection:
    cx: float
    cy: float
    code: str
    confidence: float
    box: tuple[float, float, float, float] | None = None


class LineCrossingTracker:
    """Her karede gorulen (normalize 0-1 merkez noktasi, OCR kodu, guven)
    tespitlerini onceki karelerdeki izlerle eslestirir; bir izin cizginin
    kars1 tarafina gectigi anda o izi 'crossed' olarak isaretleyip dondurur.
    Bir iz en fazla bir kez cizgiyi gecmis sayilir (ayni aracin ayni gecis
    icin tekrar tekrar bildirilmesini onler)."""

    def __init__(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        match_distance: float = 0.15,
        max_missed_frames: int = 10,
    ):
        self._line = (x1, y1, x2, y2)
        self._match_distance = match_distance
        self._max_missed_frames = max_missed_frames
        self._tracks: list[Track] = []
        self._next_id = 1

    def update(self, detections: list[tuple]) -> list[Track]:
        """detections: [(cx, cy, code, confidence), ...] ya da kutu bilgisiyle
        birlikte [(cx, cy, code, confidence, box), ...] - cx/cy normalize
        edilmis (0-1) merkez noktalari, box ise normalize (x1,y1,x2,y2) veya
        None. code bos string olabilir (OCR basarisiz).
        Bu karede cizgiyi yeni gecen track'lerin listesini dondurur."""
        parsed = []
        for det in detections:
            if len(det) == 5:
                cx, cy, code, confidence, box = det
            else:
                cx, cy, code, confidence = det
                box = None
            parsed.append(_Detection(cx, cy, code, confidence, box))
        matched_ids: set[int] = set()
        newly_crossed: list[Track] = []

        for det in parsed:
            track = self._find_nearest(det.cx, det.cy, matched_ids)
            if track is None:
                track = Track(id=self._next_id, cx=det.cx, cy=det.cy)
                self._next_id += 1
                self._tracks.append(track)

            matched_ids.add(track.id)
            track.frames_since_seen = 0

            side = side_of_line(det.cx, det.cy, *self._line)
            if (
                track.prev_side is not None
                and not track.crossed
                and side != 0
                and track.prev_side != 0
                and (side < 0) != (track.prev_side < 0)
            ):
                track.crossed = True
                newly_crossed.append(track)

            if det.code and det.confidence > track.best_confidence:
                track.best_code = det.code
                track.best_confidence = det.confidence

            track.cx, track.cy = det.cx, det.cy
            track.box = det.box
            track.prev_side = side

        for track in self._tracks:
            if track.id not in matched_ids:
                track.frames_since_seen += 1

        self._tracks = [t for t in self._tracks if t.frames_since_seen <= self._max_missed_frames]

        return newly_crossed

    def active_tracks(self) -> list[Track]:
        """Bu KAREDE eslenmis (frames_since_seen == 0) izleri dondurur -
        canli goruntude sari/yesil kutu cizmek icin (bkz. equipment_gate_worker)."""
        return [t for t in self._tracks if t.frames_since_seen == 0]

    def _find_nearest(self, cx: float, cy: float, matched_ids: set[int]) -> Track | None:
        best: Track | None = None
        best_dist = self._match_distance
        for track in self._tracks:
            if track.id in matched_ids:
                continue
            dist = ((track.cx - cx) ** 2 + (track.cy - cy) ** 2) ** 0.5
            if dist < best_dist:
                best, best_dist = track, dist
        return best
