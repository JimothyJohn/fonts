import math

import pytest

from fontgen.build import build_font, normalize_spacing
from fontgen.glyphs import CMAP, SKELETONS
from fontgen.marquee import BULB_R, MIN_SEP, make_glyphs, marquee_shapes
from fontgen.metrics import CAP
from fontgen.primitives import finalize, rect

GLYPHS = make_glyphs(SKELETONS)


@pytest.mark.parametrize("name,fn", list(GLYPHS.items()))
def test_glyph_builds_with_positive_advance(name, fn):
    contours, advance = fn()
    assert advance > 0
    if name != "space":
        assert contours
        assert all(len(c) >= 3 for c in contours)


def test_cmap_targets_exist():
    for glyph_name in CMAP.values():
        assert glyph_name in GLYPHS


def test_stem_becomes_a_string_of_bulbs():
    # I's 700-unit stem at ~96 pitch: several separate bulbs, spanning
    # the stem's full extent (endpoint bulbs land ON the ends).
    shapes, _ = marquee_shapes("I", SKELETONS["I"])
    assert 6 <= len(shapes) <= 10
    ys = [s.centroid.y for s in shapes]
    assert min(ys) < BULB_R and max(ys) > 700 - BULB_R


def test_bulbs_never_stack():
    for name in ("E", "B", "g", "eight"):
        shapes, _ = marquee_shapes(name, SKELETONS[name])
        centers = [(s.centroid.x, s.centroid.y) for s in shapes]
        for i, a in enumerate(centers):
            for b in centers[i + 1 :]:
                # Scatter jitter moves centers a few units after the
                # dedupe check, so allow it on top of MIN_SEP.
                assert math.dist(a, b) > MIN_SEP - 12


def test_period_is_one_solid_bulb():
    # A burnt-out (ring) period would read as a degree sign.
    contours, _ = GLYPHS["period"]()
    assert len(contours) == 1


def test_builds_are_deterministic():
    for name in ("I", "O", "Q", "period"):
        assert GLYPHS[name]() == GLYPHS[name](), name


def test_full_font_builds(tmp_path):
    glyphs = {".notdef": (finalize([rect(60, 0, 460, CAP)]), 520)}
    for name, fn in GLYPHS.items():
        glyphs[name] = fn()
    glyphs = normalize_spacing(glyphs, side_bearing=58)
    out = tmp_path / "marquee.ttf"
    build_font(glyphs, CMAP, "Aperture Marquee", "Regular", str(out))
    assert out.stat().st_size > 0
