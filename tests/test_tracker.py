from app.vision.tracker import LineCrossingTracker, is_entry_crossing, side_of_line


def test_side_of_line_opposite_signs_on_each_side():
    # Yatay cizgi (0,0.5)-(1,0.5): ustundeki ve altindaki noktalar zit isaretli olmali
    above = side_of_line(0.5, 0.2, 0, 0.5, 1, 0.5)
    below = side_of_line(0.5, 0.8, 0, 0.5, 1, 0.5)
    assert (above > 0) != (below > 0)


def test_no_crossing_when_staying_on_same_side():
    tracker = LineCrossingTracker(0, 0.5, 1, 0.5)
    tracker.update([(0.5, 0.2, "IS-001", 0.9)])
    crossed = tracker.update([(0.5, 0.25, "IS-001", 0.9)])
    assert crossed == []


def test_crossing_detected_when_moving_to_other_side():
    # Gercek kullanimda nesne kareler arasinda kucuk adimlarla hareket eder;
    # esleme mesafesinin (match_distance) icinde kalacak sekilde kademeli
    # olarak cizgiyi (y=0.5) gecirilir.
    tracker = LineCrossingTracker(0, 0.5, 1, 0.5)
    crossed = []
    for y in [0.20, 0.30, 0.40, 0.48, 0.55, 0.65]:
        crossed = tracker.update([(0.5, y, "IS-001", 0.9)])
        if crossed:
            break
    assert len(crossed) == 1
    assert crossed[0].best_code == "IS-001"


def test_track_crosses_only_once():
    tracker = LineCrossingTracker(0, 0.5, 1, 0.5)
    triggered = 0
    for y in [0.20, 0.30, 0.40, 0.48, 0.55, 0.65, 0.55, 0.48, 0.40, 0.30]:
        crossed = tracker.update([(0.5, y, "IS-001", 0.9)])
        triggered += len(crossed)
    assert triggered == 1  # geri donse bile ikinci kez tetiklenmemeli


def test_best_code_keeps_highest_confidence_reading():
    tracker = LineCrossingTracker(0, 0.5, 1, 0.5)
    readings = [
        (0.20, "IS-00L", 0.4),  # zayif okuma
        (0.28, "IS-001", 0.9),  # guclu okuma
        (0.36, "", 0.0),
        (0.44, "", 0.0),
        (0.52, "", 0.0),  # gecis aninda OCR basarisiz olabilir
    ]
    crossed = []
    for y, code, conf in readings:
        crossed = tracker.update([(0.5, y, code, conf)])
        if crossed:
            break
    assert len(crossed) == 1
    assert crossed[0].best_code == "IS-001"
    assert crossed[0].best_confidence == 0.9


def test_different_positions_create_separate_tracks():
    tracker = LineCrossingTracker(0, 0.5, 1, 0.5)
    crossed_codes: set[str] = set()
    for y in [0.20, 0.30, 0.40, 0.48, 0.55, 0.65]:
        crossed = tracker.update([(0.1, y, "IS-001", 0.9), (0.9, y, "IS-002", 0.9)])
        crossed_codes.update(c.best_code for c in crossed)
    assert crossed_codes == {"IS-001", "IS-002"}


def test_stale_tracks_are_dropped_after_missed_frames():
    tracker = LineCrossingTracker(0, 0.5, 1, 0.5, max_missed_frames=2)
    tracker.update([(0.5, 0.2, "IS-001", 0.9)])
    tracker.update([])  # 1. kayip kare
    tracker.update([])  # 2. kayip kare
    tracker.update([])  # 3. kayip kare -> track silinmeli
    # Ayni konumda yeni bir tespit gelirse artik YENI bir track olarak
    # baslamali (eski gecmisi/prev_side'i tasimamali), yani hemen gecis
    # tetiklenmemeli.
    crossed = tracker.update([(0.5, 0.8, "IS-001", 0.9)])
    assert crossed == []


def test_is_entry_crossing_matches_inside_reference_side():
    # inside referansi ustte (pozitif taraf farz edelim): ustte kalan gecis GIRIS,
    # altta kalan gecis CIKIS olmali.
    inside_positive = side_of_line(0.5, 0.1, 0, 0.5, 1, 0.5) > 0
    post_side_above = side_of_line(0.5, 0.2, 0, 0.5, 1, 0.5)
    post_side_below = side_of_line(0.5, 0.8, 0, 0.5, 1, 0.5)

    assert is_entry_crossing(post_side_above, inside_positive) is True
    assert is_entry_crossing(post_side_below, inside_positive) is False
