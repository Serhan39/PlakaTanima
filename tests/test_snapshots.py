import numpy as np

from app.snapshots import draw_detection_boxes
from app.vision.detector import BoundingBox


def test_draw_detection_boxes_returns_a_copy_not_the_original():
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    box = BoundingBox(10, 10, 50, 50, confidence=0.9)

    annotated = draw_detection_boxes(frame, [(box, "34 ABC 12")])

    assert not np.array_equal(frame, annotated)  # orijinal degismemis
    assert np.array_equal(frame, np.zeros((100, 100, 3), dtype=np.uint8))  # frame hala siyah


def test_draw_detection_boxes_draws_blue_pixels_on_box_border():
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    box = BoundingBox(10, 10, 50, 50, confidence=0.9)

    annotated = draw_detection_boxes(frame, [(box, "34 ABC 12")])

    # Kutu kenari (BGR'de mavi = (255,0,0)) cizilmis olmali
    border_pixel = annotated[10, 30]
    assert border_pixel[0] > 200  # B kanali yuksek
    assert border_pixel[1] < 50  # G kanali dusuk
    assert border_pixel[2] < 50  # R kanali dusuk


def test_draw_detection_boxes_handles_multiple_boxes():
    frame = np.zeros((200, 200, 3), dtype=np.uint8)
    boxes = [
        (BoundingBox(10, 10, 50, 50, confidence=0.9), "34 ABC 12"),
        (BoundingBox(100, 100, 150, 150, confidence=0.8), "06 XYZ 34"),
    ]

    annotated = draw_detection_boxes(frame, boxes)

    assert annotated[10, 30][0] > 200
    assert annotated[100, 130][0] > 200
