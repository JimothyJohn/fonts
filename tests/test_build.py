from fontgen.build import normalize_spacing


def test_normalize_spacing_shifts_ink_to_side_bearing():
    contours = [[(100, 0), (200, 0), (200, 100), (100, 100)]]
    normalized = normalize_spacing({"x": (contours, 999)}, side_bearing=50)
    shifted, advance = normalized["x"]
    xs = [x for c in shifted for x, _ in c]
    assert min(xs) == 50
    assert max(xs) == 150
    assert advance == 200  # ink width (100) + 2 * side_bearing (50)


def test_normalize_spacing_leaves_empty_glyph_untouched():
    normalized = normalize_spacing({"space": ([], 320)}, side_bearing=50)
    assert normalized["space"] == ([], 320)


def test_normalize_spacing_preserves_ink_shape():
    contours = [[(10, 0), (30, 0), (30, 20), (10, 20)]]
    normalized = normalize_spacing({"x": (contours, 0)}, side_bearing=70)
    shifted, _ = normalized["x"]
    ys = [y for c in shifted for _, y in c]
    assert min(ys) == 0
    assert max(ys) == 20
