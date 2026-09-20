import pytest
from shapely import geometry as sg
from shapely.ops import unary_union

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
    body_bounds,
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
# natural join point, g/q/y exit through their descenders (a rising
# baseline tail crossed their own ink), and b/f/p/r/s have no pen-lift
# on their right side (see BASELINE_TAILED below).
TAILED = sorted(LOWERCASE - set("jbfprs") - NO_TAIL)


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


def test_script_stems_are_straight_and_hand_stems_are_bowed():
    """The script face is typeset: l's stem stays a ruler line. Only the
    hand face (bow=True) resamples it with interior points that deviate
    from the endpoint chord."""
    straight = script_strokes("l", SKELETONS["l"])[0]["pts"]
    assert len(straight) == 2
    stem = script_strokes("l", SKELETONS["l"], bow=True)[0]["pts"]
    assert len(stem) > 2
    (x0, y0), (x1, y1) = stem[0], stem[-1]
    mid = stem[len(stem) // 2]
    chord_x = x0 + (x1 - x0) * ((mid[1] - y0) / (y1 - y0))
    assert abs(mid[0] - chord_x) > 5


def test_tail_is_flagged_and_excluded_from_spacing():
    """The exit tail is the only stroke flagged "tail", and body_bounds
    stops at the body's ink so the tail can overshoot the advance."""
    strokes = script_strokes("n", SKELETONS["n"])
    tails = [s for s in strokes if s.get("tail")]
    assert len(tails) == 1 and tails[0] is strokes[-1]
    x_min, x_max = body_bounds(strokes)
    tail_tip = max(x for x, _ in tails[0]["pts"])
    assert tail_tip > x_max + 50
    assert x_min < x_max
    assert body_bounds(tails) is None


# skeleton + loop + exit tail; b has no tail (its stem is on the left)
@pytest.mark.parametrize(
    "name,extra", [("b", 1), ("d", 2), ("h", 2), ("k", 2), ("l", 2)]
)
def test_ascender_loops_added(name, extra):
    with record_strokes() as sans_strokes:
        SKELETONS[name]()
    strokes = script_strokes(name, SKELETONS[name])
    assert len(strokes) == len(sans_strokes) + extra


def test_f_gets_no_loop_and_no_tail():
    """f's own top hook plus an ascender loop was an unreadable knot,
    and a baseline tail made it read as t -- it stays the bare skeleton."""
    with record_strokes() as sans_strokes:
        SKELETONS["f"]()
    strokes = script_strokes("f", SKELETONS["f"])
    assert len(strokes) == len(sans_strokes)


# loop only: p's stem is on its left, q exits through the loop
@pytest.mark.parametrize("name,extra", [("p", 1), ("q", 1)])
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


# The exact set of letters that grow a tail. A tail is only right where
# the pen leaves the letter from its right side; everything else (the
# tail slashing through b/p/s's own bowl, r + tail reading as c, f + tail
# reading as t) was a bug that the "reaches right" test above let through.
BASELINE_TAILED = set("acdehiklmntuxz")


def _unsheared_tail(name):
    strokes = script_strokes(name, SKELETONS[name])
    tails = [s for s in strokes if s.get("tail")]
    body = [s for s in strokes if not s.get("tail")]

    def unshear(s):
        return [(x - SLANT * y, y) for x, y in s["pts"]]

    return [unshear(s) for s in tails], [{**s, "pts": unshear(s)} for s in body]


@pytest.mark.parametrize("name", sorted(LOWERCASE))
def test_exactly_the_right_letters_are_tailed(name):
    tails, _ = _unsheared_tail(name)
    assert len(tails) == (1 if name in BASELINE_TAILED | TOP_EXIT else 0)


@pytest.mark.parametrize("name", sorted(BASELINE_TAILED))
def test_tail_never_crosses_its_own_letter(name):
    """Past its first stretch (where it necessarily leaves the ink it
    grows from) the tail runs through free space."""
    tails, body = _unsheared_tail(name)
    ink = unary_union(
        [
            sg.LineString(s["pts"] + ([s["pts"][0]] if s["closed"] else [])).buffer(
                s["width"] / 2
            )
            for s in body
            if len(set(s["pts"])) > 1
        ]
    )
    tail = sg.LineString(tails[0])
    free = tail.difference(sg.Point(tails[0][0]).buffer(120))
    assert not free.intersects(ink)


@pytest.mark.parametrize("name", ["c", "e"])
def test_tail_continues_a_rising_terminal(name):
    """c and e finish travelling up and to the right; the tail carries
    that motion on instead of dipping back to the baseline first (which
    hung a hook off the terminal)."""
    tails, body = _unsheared_tail(name)
    start = tails[0][0]
    # it starts at a real pen-lift, not at a junction between strokes
    ends = [p for s in body for p in (s["pts"][0], s["pts"][-1])]
    assert ends.count(start) == 1
    assert min(y for _, y in tails[0]) >= start[1] - 1


def test_u_tail_leaves_from_a_grounded_stem():
    """u's right stem stops where the bowl begins; the tail must not
    dangle from that junction -- the stem runs down to the baseline and
    the tail leaves from its foot, as on a/d/n."""
    tails, body = _unsheared_tail("u")
    sx, sy = tails[0][0]
    assert sy == pytest.approx(0)
    assert any(
        not s["closed"]
        and len(s["pts"]) == 2
        and (sx, sy) in [tuple(p) for p in s["pts"]]
        for s in body
    )
