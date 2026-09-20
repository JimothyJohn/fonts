"""The figures' shapes, pinned where they used to be strange: a 0 that was
the letter O, a 4 with two tops, a 5 whose stem jogged into its bowl, a
6/9 that was a small circle on a ruler-straight stick (reading as b/g),
an 8 with a double-thick waist, a 3 whose bowls missed each other, and a
2 whose diagonal kinked off its head. Every face re-inks these
skeletons, so the contract is asserted on the skeleton and its sans ink.
"""

import math

import pytest
from shapely import affinity
from shapely import geometry as sg

from fontgen.glyphs import GLYPHS, SKELETONS
from fontgen.metrics import CAP, STROKE
from fontgen.primitives import contours_to_polygon, record_strokes


def _ink(name):
    contours, _ = GLYPHS[name]()
    return contours_to_polygon(contours)


def _strokes(name):
    with record_strokes() as strokes:
        SKELETONS[name]()
    return strokes


def _turns(pts):
    """Absolute turning angle (degrees) at each interior vertex."""
    out = []
    for a, b, c in zip(pts, pts[1:], pts[2:]):
        h0 = math.atan2(b[1] - a[1], b[0] - a[0])
        h1 = math.atan2(c[1] - b[1], c[0] - b[0])
        out.append(abs(math.degrees((h1 - h0 + math.pi) % (2 * math.pi) - math.pi)))
    return out


def _crossings(poly, line):
    hit = poly.intersection(line)
    parts = getattr(hit, "geoms", [hit])
    return sorted((p for p in parts if p.length > 0), key=lambda p: p.bounds[:2])


def test_zero_is_an_oval_not_the_letter_o():
    zx0, zy0, zx1, zy1 = _ink("zero").bounds
    ox0, _, ox1, _ = _ink("O").bounds
    assert (zx1 - zx0) < (ox1 - ox0) - 100
    assert (zy1 - zy0) / (zx1 - zx0) > 1.3


def test_two_diagonal_leaves_the_head_tangentially():
    spine = max(_strokes("two"), key=lambda s: len(s["pts"]))["pts"]
    assert max(_turns(spine)) < 7  # no more than one arc sample's turn


def test_three_bowls_meet_at_one_waist_point():
    top, bottom = _strokes("three")
    assert top["pts"][-1] == pytest.approx(bottom["pts"][0])


def test_four_has_a_single_apex():
    """The diagonal runs into the stem's top; it used to stop 60 short of
    it, leaving two round tops side by side."""
    x0, _, x1, _ = _ink("four").bounds
    y = CAP + 30
    assert len(_crossings(_ink("four"), sg.LineString([(x0 - 9, y), (x1 + 9, y)]))) == 1


def test_five_pen_turns_exactly_twice():
    """Bar into stem, stem into bowl. The stem used to jog sideways to
    reach a bowl it did not touch -- a third corner, and a knob."""
    (spine,) = _strokes("five")
    assert sum(1 for t in _turns(spine["pts"]) if t > 15) == 2


@pytest.mark.parametrize("name", ["six", "nine"])
def test_six_nine_have_no_ruler_straight_side(name):
    longest = max(
        math.dist(a, b) for s in _strokes(name) for a, b in zip(s["pts"], s["pts"][1:])
    )
    assert longest < 0.2 * CAP


def test_nine_is_six_turned_over():
    six, nine = _ink("six"), _ink("nine")
    turned = affinity.rotate(six, 180, origin=six.envelope.centroid)
    cx, cy = nine.envelope.centroid.coords[0]
    tx, ty = turned.envelope.centroid.coords[0]
    turned = affinity.translate(turned, cx - tx, cy - ty)
    assert turned.symmetric_difference(nine).area < 0.01 * nine.area


def test_eight_waist_is_one_stroke_thick():
    ink = _ink("eight")
    x0, y0, x1, y1 = ink.bounds
    cx = (x0 + x1) / 2
    bottom, waist, top = _crossings(ink, sg.LineString([(cx, y0 - 9), (cx, y1 + 9)]))
    assert waist.length == pytest.approx(STROKE, abs=4)
    assert bottom.length == pytest.approx(STROKE, abs=4)
    assert top.length == pytest.approx(STROKE, abs=4)
