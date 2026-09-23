import time

from app import detection_burst


def _reset(camera_id: int) -> None:
    with detection_burst._lock:
        detection_burst._bursts.pop(camera_id, None)


def test_single_candidate_is_not_finalized_before_gap_elapses():
    _reset(101)
    original_gap = detection_burst.BURST_GAP_SECONDS
    try:
        detection_burst.BURST_GAP_SECONDS = 10
        detection_burst.add_burst_candidate(101, "34 ABC 12", 0.4, "snap1.jpg", None)
        finalized = [f for f in detection_burst.pop_finalized_bursts() if f.camera_id == 101]
        assert finalized == []
    finally:
        detection_burst.BURST_GAP_SECONDS = original_gap
        _reset(101)


def test_burst_finalizes_after_gap_elapses_since_last_candidate():
    _reset(102)
    original_gap = detection_burst.BURST_GAP_SECONDS
    try:
        detection_burst.BURST_GAP_SECONDS = 0.05
        detection_burst.add_burst_candidate(102, "34 ABC 12", 0.4, "snap1.jpg", None)
        time.sleep(0.1)
        finalized = [f for f in detection_burst.pop_finalized_bursts() if f.camera_id == 102]
        assert len(finalized) == 1
        assert finalized[0].plate == "34 ABC 12"
    finally:
        detection_burst.BURST_GAP_SECONDS = original_gap
        _reset(102)


def test_majority_vote_picks_the_most_frequent_reading():
    # Gercek olay: ayni gecis icinde 4 deneme - 2'si "07 BAF 140" (dogru),
    # 1'i "07 BRE 140", 1'i "07 BRE 10" (farkli OCR hatalari). Cogunluk
    # oylamasi en sik tekrarlanan (dolayisiyla muhtemelen dogru) okumayi
    # sonuc olarak vermeli.
    _reset(103)
    original_gap = detection_burst.BURST_GAP_SECONDS
    try:
        detection_burst.BURST_GAP_SECONDS = 0.05
        detection_burst.add_burst_candidate(103, "07 BAF 140", 0.40, "snap-a.jpg", None)
        detection_burst.add_burst_candidate(103, "07 BRE 140", 0.42, "snap-b.jpg", None)
        detection_burst.add_burst_candidate(103, "07 BAF 140", 0.42, "snap-c.jpg", None)
        detection_burst.add_burst_candidate(103, "07 BRE 10", 0.42, "snap-d.jpg", None)
        time.sleep(0.1)

        finalized = [f for f in detection_burst.pop_finalized_bursts() if f.camera_id == 103]

        assert len(finalized) == 1
        assert finalized[0].plate == "07 BAF 140"
        assert finalized[0].candidate_count == 2
        assert finalized[0].confidence == 0.42  # kazanan grup icindeki en yuksek guven
        assert finalized[0].snapshot_path == "snap-c.jpg"
    finally:
        detection_burst.BURST_GAP_SECONDS = original_gap
        _reset(103)


def test_burst_finalizes_once_max_duration_exceeded_even_without_a_gap():
    # Aracin uzun sure goruntude kaldigi (orn. bariyerde bekleyen bir
    # arac) durumda, ardisik adaylar arasinda hic bosluk olmasa bile
    # suresiz birikmemesi icin bir ust sinir olmali.
    _reset(104)
    original_gap = detection_burst.BURST_GAP_SECONDS
    original_max = detection_burst.BURST_MAX_SECONDS
    try:
        detection_burst.BURST_GAP_SECONDS = 10
        detection_burst.BURST_MAX_SECONDS = 0.05
        detection_burst.add_burst_candidate(104, "34 ABC 12", 0.4, "snap1.jpg", None)
        time.sleep(0.1)
        detection_burst.add_burst_candidate(104, "34 ABC 12", 0.5, "snap2.jpg", None)

        finalized = [f for f in detection_burst.pop_finalized_bursts() if f.camera_id == 104]

        assert len(finalized) == 1
    finally:
        detection_burst.BURST_GAP_SECONDS = original_gap
        detection_burst.BURST_MAX_SECONDS = original_max
        _reset(104)


def test_pop_finalized_bursts_clears_camera_so_next_pass_starts_fresh():
    _reset(105)
    original_gap = detection_burst.BURST_GAP_SECONDS
    try:
        detection_burst.BURST_GAP_SECONDS = 0.05
        detection_burst.add_burst_candidate(105, "34 ABC 12", 0.4, "snap1.jpg", None)
        time.sleep(0.1)
        first = [f for f in detection_burst.pop_finalized_bursts() if f.camera_id == 105]
        assert len(first) == 1

        second = [f for f in detection_burst.pop_finalized_bursts() if f.camera_id == 105]
        assert second == []
    finally:
        detection_burst.BURST_GAP_SECONDS = original_gap
        _reset(105)
