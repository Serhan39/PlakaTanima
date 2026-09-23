from app.vision.detector import BoundingBox, fit_plate_aspect_ratio


def test_fit_plate_aspect_ratio_trims_top_of_slightly_too_tall_box():
    # Gercek olay: kutu, plakanin ustundeki izgarayi da kapsayip gerekenden
    # "uzun" geldi. Genislik 200px, yukseklik 65px -> oran ~3.08 (hedef
    # 4.5'in altinda ama 3.0 esiginin ustunde) - duzeltilmeli.
    box = BoundingBox(x1=10, y1=100, x2=210, y2=165, confidence=0.8)

    fitted = fit_plate_aspect_ratio(box, target_ratio=4.5)

    assert fitted.x1 == box.x1
    assert fitted.x2 == box.x2
    assert fitted.y2 == box.y2  # alt kenar sabit kalir (plaka genelde alt tarafta)
    assert fitted.y1 > box.y1  # ustten kirpildi
    new_height = fitted.y2 - fitted.y1
    assert abs((fitted.x2 - fitted.x1) / new_height - 4.5) < 0.1


def test_fit_plate_aspect_ratio_leaves_already_correct_box_untouched():
    box = BoundingBox(x1=10, y1=100, x2=210, y2=144, confidence=0.8)  # oran ~4.55

    fitted = fit_plate_aspect_ratio(box, target_ratio=4.5)

    assert fitted == box


def test_fit_plate_aspect_ratio_does_not_touch_two_line_plate_shaped_boxes():
    # Iki satirlik (orn. motosiklet) plakalar dogal olarak KARE'ye yakindir
    # (oran ~1.3-2). Bunlara yanlislikla dokunup bozmamaliyiz.
    box = BoundingBox(x1=10, y1=100, x2=110, y2=170, confidence=0.8)  # oran ~1.43

    fitted = fit_plate_aspect_ratio(box, target_ratio=4.5)

    assert fitted == box


def test_fit_plate_aspect_ratio_ignores_degenerate_box():
    box = BoundingBox(x1=10, y1=100, x2=10, y2=100, confidence=0.8)  # sifir alan

    fitted = fit_plate_aspect_ratio(box, target_ratio=4.5)

    assert fitted == box
