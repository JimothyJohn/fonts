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


def test_normalize_baseline_puts_the_reference_flats_ink_on_zero():
    from fontgen.build import normalize_baseline

    glyphs = {
        "H": ([[(0, -39), (100, -39), (100, 739), (0, 739)]], 200),
        "O": ([[(0, -53), (100, -53), (100, 753), (0, 753)]], 200),
        "space": ([], 320),
    }
    shifted = normalize_baseline(glyphs)
    assert min(y for _, y in shifted["H"][0][0]) == 0
    assert min(y for _, y in shifted["O"][0][0]) == -14  # curves keep their overshoot
    assert shifted["space"] == ([], 320)
    assert shifted["H"][1] == 200


def test_built_fonts_sit_on_the_baseline(tmp_path):
    """Every face's H must rest exactly on y=0 in the shipped font, and
    the cap height the font declares must be where H's ink actually ends."""
    from fontTools.ttLib import TTFont

    from fontgen.build import build_font
    from fontgen.glyphs import CMAP, GLYPHS
    from fontgen.glyphs_serif import GLYPHS as SERIF
    from fontgen.metrics import CAP
    from fontgen.primitives import finalize, rect

    for label, table in (("sans", GLYPHS), ("serif", SERIF)):
        glyphs = {".notdef": (finalize([rect(60, 0, 460, CAP)]), 520)}
        glyphs.update({n: fn() for n, fn in table.items()})
        path = tmp_path / f"{label}.ttf"
        build_font(normalize_spacing(glyphs), CMAP, "T", "Regular", str(path))
        font = TTFont(str(path))
        glyf = font["glyf"]
        assert glyf["H"].yMin == 0, label
        assert font["OS/2"].sCapHeight == glyf["H"].yMax, label
        assert font["OS/2"].sxHeight == glyf["x"].yMax, label
        assert glyf["O"].yMin < 0 < glyf["O"].yMax, label
