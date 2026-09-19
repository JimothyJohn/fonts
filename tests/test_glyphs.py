import pytest

from fontgen.build import build_font, normalize_spacing
from fontgen.glyphs import CMAP, GLYPHS, LOWER_OVERSHOOT
from fontgen.metrics import (
    BASE,
    CAP,
    DESCENT,
    OVERSHOOT,
    SIDE_BEARING,
    STROKE,
    X_HEIGHT,
)
from fontgen.primitives import finalize, rect


@pytest.mark.parametrize("name,fn", list(GLYPHS.items()))
def test_glyph_has_positive_advance(name, fn):
    _, advance = fn()
    assert advance > 0


@pytest.mark.parametrize("name,fn", [(n, f) for n, f in GLYPHS.items() if n != "space"])
def test_non_space_glyph_has_contours(name, fn):
    contours, _ = fn()
    assert len(contours) > 0
    assert all(len(c) >= 3 for c in contours)


def test_cmap_targets_exist_in_glyph_set():
    for codepoint, glyph_name in CMAP.items():
        assert glyph_name in GLYPHS, (
            f"cmap entry U+{codepoint:04X} -> {glyph_name!r} missing from GLYPHS"
        )


def test_full_font_builds(tmp_path):
    glyphs = {".notdef": (finalize([rect(60, 0, 460, CAP)]), 520)}
    for name, fn in GLYPHS.items():
        glyphs[name] = fn()
    glyphs = normalize_spacing(glyphs)

    out_path = tmp_path / "test.ttf"
    build_font(glyphs, CMAP, "Test Family", "Regular", str(out_path))
    assert out_path.exists()
    assert out_path.stat().st_size > 0


@pytest.mark.parametrize("name,fn", [(n, f) for n, f in GLYPHS.items() if n != "space"])
def test_normalize_spacing_gives_uniform_side_bearings(name, fn):
    contours, advance = fn()
    (shifted, new_advance) = normalize_spacing({name: (contours, advance)})[name]
    xs = [x for c in shifted for x, _ in c]
    assert min(xs) == pytest.approx(SIDE_BEARING)
    assert new_advance - max(xs) == pytest.approx(SIDE_BEARING)


# ---- vertical alignment ------------------------------------------------------
#
# The optical contract every face inherits: a straight stroke's ink reaches
# STROKE/2 past its guideline (its round cap), and a curve's extreme reaches
# OVERSHOOT further than that. Regression for the rings that used to be sized
# OUTER-edge-to-guideline (O visibly shorter than H, 8 floating 69 units above
# the baseline ink, 6 floating 39, S/5/J each short by their own margin).

FLAT_TOP = CAP + STROKE / 2
FLAT_BOTTOM = BASE - STROKE / 2
CURVE_TOP = FLAT_TOP + OVERSHOOT
CURVE_BOTTOM = FLAT_BOTTOM - OVERSHOOT
LC_FLAT_TOP = X_HEIGHT + STROKE / 2
LC_CURVE_TOP = LC_FLAT_TOP + LOWER_OVERSHOOT
LC_CURVE_BOTTOM = FLAT_BOTTOM - LOWER_OVERSHOOT
DESC_FLAT = DESCENT - STROKE / 2
DESC_CURVE = DESC_FLAT - LOWER_OVERSHOOT


def _ink_y(name):
    contours, _ = GLYPHS[name]()
    ys = [y for c in contours for _, y in c]
    return min(ys), max(ys)


@pytest.mark.parametrize(
    "name,top,bottom",
    [
        ("H", FLAT_TOP, FLAT_BOTTOM),
        ("E", FLAT_TOP, FLAT_BOTTOM),
        ("I", FLAT_TOP, FLAT_BOTTOM),
        ("one", FLAT_TOP, FLAT_BOTTOM),
        ("O", CURVE_TOP, CURVE_BOTTOM),
        ("C", CURVE_TOP, CURVE_BOTTOM),
        ("G", CURVE_TOP, CURVE_BOTTOM),
        ("S", CURVE_TOP, CURVE_BOTTOM),
        ("zero", CURVE_TOP, CURVE_BOTTOM),
        ("three", CURVE_TOP, CURVE_BOTTOM),
        ("eight", CURVE_TOP, CURVE_BOTTOM),
        ("six", CURVE_TOP, CURVE_BOTTOM),
        ("nine", CURVE_TOP, CURVE_BOTTOM),
        ("two", CURVE_TOP, FLAT_BOTTOM),
        ("five", FLAT_TOP, CURVE_BOTTOM),
        ("J", FLAT_TOP, CURVE_BOTTOM),
        ("U", FLAT_TOP, CURVE_BOTTOM),
        ("D", CURVE_TOP, CURVE_BOTTOM),
        ("B", CURVE_TOP, CURVE_BOTTOM),
        ("P", CURVE_TOP, FLAT_BOTTOM),
        ("question", CURVE_TOP, BASE),
        ("n", LC_CURVE_TOP, FLAT_BOTTOM),
        ("u", LC_FLAT_TOP, LC_CURVE_BOTTOM),
        ("o", LC_CURVE_TOP, LC_CURVE_BOTTOM),
        ("c", LC_CURVE_TOP, LC_CURVE_BOTTOM),
        ("e", LC_CURVE_TOP, LC_CURVE_BOTTOM),
        ("s", LC_CURVE_TOP, LC_CURVE_BOTTOM),
        ("a", LC_CURVE_TOP, LC_CURVE_BOTTOM),
        ("b", FLAT_TOP, LC_CURVE_BOTTOM),
        ("p", LC_CURVE_TOP, DESC_FLAT),
        ("g", LC_CURVE_TOP, DESC_CURVE),
        ("j", X_HEIGHT + 200, DESC_CURVE),
        ("y", LC_FLAT_TOP, DESC_FLAT),
        ("f", CURVE_TOP, FLAT_BOTTOM),
        ("r", LC_CURVE_TOP, FLAT_BOTTOM),
    ],
)
def test_curves_overshoot_flats_by_exactly_overshoot(name, top, bottom):
    lo, hi = _ink_y(name)
    assert hi == pytest.approx(top, abs=1.5), f"{name} top {hi} != {top}"
    assert lo == pytest.approx(bottom, abs=1.5), f"{name} bottom {lo} != {bottom}"


def test_round_dots_match_the_tittle():
    """period/colon/exclam/question dots are the same disc as i's dot."""
    from shapely.geometry import Polygon

    from fontgen.primitives import contours_to_polygon

    def dot_area(name):
        poly = contours_to_polygon(GLYPHS[name]()[0])
        parts = list(poly.geoms) if hasattr(poly, "geoms") else [poly]
        return min(p.area for p in parts)

    tittle = dot_area("i")
    assert tittle > 0
    for name in ("period", "exclam", "question"):
        assert dot_area(name) == pytest.approx(tittle, rel=1e-6), name
    colon = contours_to_polygon(GLYPHS["colon"]()[0])
    assert all(
        isinstance(p, Polygon) and p.area == pytest.approx(tittle, rel=1e-6)
        for p in colon.geoms
    )
