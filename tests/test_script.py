import pytest

from fontgen.build import build_font, normalize_spacing
from fontgen.glyphs import CMAP, GLYPHS, SKELETONS
from fontgen.metrics import CAP
from fontgen.primitives import finalize, record_strokes, rect
from fontgen.script import (
    LOWERCASE,
    NO_TAIL,
    SLANT,
    TOP_EXIT,
    TOP_JOIN_Y,
    make_glyphs,
    script_strokes,
)

SCRIPT_GLYPHS = make_glyphs(SKELETONS)


@pytest.mark.parametrize("name", [n for n in SKELETONS if n != "space"])
def test_script_glyph_has_contours(name):
    contours, advance = SCRIPT_GLYPHS[name]()
    assert advance > 0
    assert len(contours) > 0
    assert all(len(c) >= 3 for c in contours)


def test_cmap_covered():
    for glyph_name in CMAP.values():
        assert glyph_name in SCRIPT_GLYPHS


# No-tail letters: j's pen finishes on the descender hook with no
# natural join point, and g/q/y exit through their descenders (a rising
# baseline tail crossed their own ink).
TAILED = sorted(LOWERCASE - {"j"} - NO_TAIL)


@pytest.mark.parametrize(
    "name,extra",
    [("j", 0), ("g", 0), ("y", 0), ("q", 1)],  # q's extra stroke is its loop
)
def test_no_tail_letters(name, extra):
    with record_strokes() as sans_strokes:
        SKELETONS[name]()
    strokes = script_strokes(name, SKELETONS[name])
    assert len(strokes) == len(sans_strokes) + extra


@pytest.mark.parametrize("name", sorted(TOP_EXIT))
def test_top_exit_tails_end_high(name):
    """o/v/w join the next letter from the top: their tail's endpoint
    must sit at the top join height, not down at baseline-join level."""
    strokes = script_strokes(name, SKELETONS[name])
    tail_end_y = strokes[-1]["pts"][-1][1]
    assert tail_end_y == pytest.approx(TOP_JOIN_Y)


@pytest.mark.parametrize("name", TAILED)
def test_lowercase_grows_exit_tail(name):
    """Every tailed lowercase letter's script ink must extend farther
    right than the sans ink of the same skeleton, slant removed: that
    extra reach is the exit tail."""
    sans_contours, _ = GLYPHS[name]()
    sans_right = max(x for c in sans_contours for x, _ in c)
    strokes = script_strokes(name, SKELETONS[name])
    script_right = max(x - SLANT * y for s in strokes for x, y in s["pts"])
    assert script_right > sans_right + 50


def test_slant_applied_to_stem():
    """l is a bare stem: after the shear its top must sit right of its
    bottom by SLANT * height."""
    strokes = script_strokes("l", SKELETONS["l"])
    stem = strokes[0]["pts"]
    (x0, y0), (x1, y1) = stem[0], stem[-1]
    top, bottom = ((x1, y1), (x0, y0)) if y1 > y0 else ((x0, y0), (x1, y1))
    assert top[0] - bottom[0] == pytest.approx(SLANT * (top[1] - bottom[1]))


def test_uppercase_gets_no_tail_or_loops():
    """Caps are slanted and bowed but unjoined: same stroke count as the
    sans, and every stroke's endpoints (shear removed) are unmoved --
    only interior points may bow."""
    with record_strokes() as sans_strokes:
        SKELETONS["H"]()
    strokes = script_strokes("H", SKELETONS["H"])
    assert len(strokes) == len(sans_strokes)
    for sans, script in zip(sans_strokes, strokes):
        for p_sans, p_script in [
            (sans["pts"][0], script["pts"][0]),
            (sans["pts"][-1], script["pts"][-1]),
        ]:
            unsheared = (p_script[0] - SLANT * p_script[1], p_script[1])
            assert unsheared == pytest.approx(p_sans)


def test_long_straight_strokes_are_bowed():
    """l's stem must no longer be a ruler line: resampled with interior
    points that deviate from the endpoint chord."""
    strokes = script_strokes("l", SKELETONS["l"])
    stem = strokes[0]["pts"]
    assert len(stem) > 2
    (x0, y0), (x1, y1) = stem[0], stem[-1]
    mid = stem[len(stem) // 2]
    chord_x = x0 + (x1 - x0) * ((mid[1] - y0) / (y1 - y0))
    assert abs(mid[0] - chord_x) > 5


@pytest.mark.parametrize("name", sorted("bdhkl"))
def test_ascender_loops_added(name):
    with record_strokes() as sans_strokes:
        SKELETONS[name]()
    strokes = script_strokes(name, SKELETONS[name])
    # skeleton + loop + exit tail
    assert len(strokes) == len(sans_strokes) + 2


def test_f_gets_tail_but_no_loop():
    """f's own top hook plus an ascender loop was an unreadable knot --
    it keeps the exit tail only."""
    with record_strokes() as sans_strokes:
        SKELETONS["f"]()
    strokes = script_strokes("f", SKELETONS["f"])
    assert len(strokes) == len(sans_strokes) + 1


# p: loop + exit tail; q: loop only (no tail, it exits through the loop)
@pytest.mark.parametrize("name,extra", [("p", 2), ("q", 1)])
def test_descender_loops_added(name, extra):
    with record_strokes() as sans_strokes:
        SKELETONS[name]()
    strokes = script_strokes(name, SKELETONS[name])
    assert len(strokes) == len(sans_strokes) + extra


def test_script_deterministic():
    a = script_strokes("a", SKELETONS["a"])
    b = script_strokes("a", SKELETONS["a"])
    assert a == b


def test_full_script_font_builds(tmp_path):
    glyphs = {".notdef": (finalize([rect(60, 0, 460, CAP)]), 520)}
    for name, fn in SCRIPT_GLYPHS.items():
        glyphs[name] = fn()
    glyphs = normalize_spacing(glyphs, side_bearing=45)

    out_path = tmp_path / "script.ttf"
    build_font(glyphs, CMAP, "Test Script", "Regular", str(out_path))
    assert out_path.exists()
    assert out_path.stat().st_size > 0
