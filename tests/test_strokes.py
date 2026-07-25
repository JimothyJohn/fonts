import pytest

from fontgen.build import normalize_spacing
from fontgen.glyphs import CMAP, GLYPHS
from fontgen.metrics import STROKE
from fontgen.primitives import record_strokes, stroke_union
from fontgen.strokes import glyph_strokes, strokes_by_char


def test_recorder_captures_stroke_union_polylines():
    with record_strokes() as strokes:
        stroke_union([[(0, 0), (100, 0)], [(0, 0), (0, 100)]], STROKE)
    assert len(strokes) == 2
    assert strokes[0]["pts"] == [(0, 0), (100, 0)]
    assert strokes[0]["width"] == STROKE
    assert not strokes[0]["closed"]


def test_recorder_inactive_outside_context():
    with record_strokes() as strokes:
        pass
    stroke_union([[(0, 0), (100, 0)]], STROKE)
    assert strokes == []


def test_recorder_nesting_restores_outer():
    with record_strokes() as outer:
        stroke_union([[(0, 0), (1, 0)]], STROKE)
        with record_strokes() as inner:
            stroke_union([[(0, 0), (2, 0)]], STROKE)
        stroke_union([[(0, 0), (3, 0)]], STROKE)
    assert len(outer) == 2
    assert len(inner) == 1


@pytest.mark.parametrize("name", [n for n in GLYPHS if n != "space"])
def test_every_glyph_records_strokes(name):
    spec = glyph_strokes()[name]
    assert len(spec["strokes"]) > 0
    for stroke in spec["strokes"]:
        assert stroke["width"] > 0
        assert len(stroke["pts"]) >= 2


def test_advances_match_normalized_font():
    glyphs = {name: fn() for name, fn in GLYPHS.items()}
    normalized = normalize_spacing(glyphs)
    strokes = glyph_strokes()
    for name, (_, advance) in normalized.items():
        assert strokes[name]["advance"] == pytest.approx(advance)


@pytest.mark.parametrize("name", [n for n in GLYPHS if n != "space"])
def test_stroke_centerlines_stay_inside_contour_bbox(name):
    """Every centerline point is on the ink the font builds from that same
    centerline, so it must lie inside the filled outline's bbox. (The
    full w/2 inflation is NOT a valid bound: flat-capped arc bands trim
    the ink at the arc's endpoints.)
    """
    glyphs = {name: GLYPHS[name]()}
    contours, _ = normalize_spacing(glyphs)[name]
    xs = [x for c in contours for x, _ in c]
    ys = [y for c in contours for _, y in c]
    tol = 1.0
    spec = glyph_strokes()[name]
    for stroke in spec["strokes"]:
        for x, y in stroke["pts"]:
            assert min(xs) - tol <= x <= max(xs) + tol
            assert min(ys) - tol <= y <= max(ys) + tol


def test_strokes_by_char_covers_cmap_and_is_deterministic():
    a = strokes_by_char()
    b = strokes_by_char()
    assert a == b
    for codepoint in CMAP:
        assert chr(codepoint) in a["chars"]
    assert a["chars"][" "]["strokes"] == []
    assert a["upm"] == 1000
