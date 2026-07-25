import pytest
from fontTools.ttLib import TTFont

from fontgen.build import build_font, normalize_spacing
from fontgen.glyphs import CMAP, SKELETONS
from fontgen.hand import NUM_VARIANTS, _rng, feature_code, hand_contours
from fontgen.metrics import CAP
from fontgen.primitives import finalize, rect
from fontgen.script import script_strokes


def _contours(name, variant):
    strokes = script_strokes(name, SKELETONS[name])
    return hand_contours(strokes, _rng(name, variant))


@pytest.mark.parametrize("name", [n for n in SKELETONS if n != "space"])
def test_every_glyph_inks(name):
    for v in range(NUM_VARIANTS):
        contours = _contours(name, v)
        assert len(contours) > 0
        assert all(len(c) >= 3 for c in contours)


def test_variants_are_distinct_drawings():
    a0, a1, a2 = (_contours("a", v) for v in range(NUM_VARIANTS))
    assert a0 != a1
    assert a1 != a2
    assert a0 != a2


def test_variants_deterministic():
    assert _contours("g", 1) == _contours("g", 1)


def test_pressure_varies_along_stroke():
    """Variable-pressure ink: l's stem outline must not be two parallel
    edges -- the horizontal ink width has to change measurably along
    the stem (taper at the ends, down-bias in the middle)."""
    contours = _contours("l", 0)
    pts = [p for c in contours for p in c]
    ys = sorted(y for _, y in pts)
    y_lo, y_hi = ys[0], ys[-1]

    def width_at(y_target, tol=12):
        xs = [x for x, y in pts if abs(y - y_target) < tol]
        return max(xs) - min(xs) if len(xs) >= 2 else None

    mid = width_at((y_lo + y_hi) / 2)
    near_tip = width_at(y_hi - 25)
    assert mid is not None and near_tip is not None
    assert near_tip < mid * 0.92


@pytest.fixture(scope="module")
def hand_font(tmp_path_factory):
    out = tmp_path_factory.mktemp("hand") / "hand.ttf"
    glyphs = {".notdef": (finalize([rect(60, 0, 460, CAP)]), 520)}
    varying = []
    for name, fn in SKELETONS.items():
        strokes = script_strokes(name, fn)
        _, advance, _ = fn()
        for v in range(NUM_VARIANTS):
            glyph_name = name if v == 0 else f"{name}.alt{v}"
            glyphs[glyph_name] = (hand_contours(strokes, _rng(name, v)), advance)
        if strokes:
            varying.append(name)
    glyphs = normalize_spacing(glyphs, side_bearing=45)
    build_font(
        glyphs, CMAP, "Test Hand", "Regular", str(out), features=feature_code(varying)
    )
    return TTFont(str(out))


def test_font_carries_all_variants(hand_font):
    order = hand_font.getGlyphOrder()
    for name in SKELETONS:
        if name == "space":
            continue
        assert name in order
        assert f"{name}.alt1" in order
        assert f"{name}.alt2" in order


def test_cmap_maps_only_defaults(hand_font):
    mapped = set(hand_font.getBestCmap().values())
    assert not any(".alt" in g for g in mapped)


def test_calt_feature_present(hand_font):
    gsub = hand_font["GSUB"].table
    features = [fr.FeatureTag for fr in gsub.FeatureList.FeatureRecord]
    assert "calt" in features
