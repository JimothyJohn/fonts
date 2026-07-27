import math

import pytest
from shapely.geometry import LineString

from fontgen.blackletter import HAIR, MAIN, _nib_width, make_glyphs
from fontgen.build import build_font, normalize_spacing
from fontgen.glyphs import CMAP, SKELETONS
from fontgen.metrics import CAP, MID
from fontgen.primitives import contours_to_polygon, finalize, rect

GLYPHS = make_glyphs(SKELETONS)


def _ink(name):
    contours, _ = GLYPHS[name]()
    return contours_to_polygon(contours)


def _cut(ink, line):
    hit = ink.intersection(line)
    pieces = list(hit.geoms) if hasattr(hit, "geoms") else [hit]
    lengths = sorted(p.length for p in pieces if p.length > 1)
    return sum(lengths), lengths


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


def test_stem_carries_nib_weight():
    total, _ = _cut(_ink("I"), LineString([(-200, MID), (900, MID)]))
    assert MAIN * 0.85 <= total <= MAIN * 1.15


def test_diamond_foot_bites_past_baseline():
    # The nib-mark rhombus pokes a touch below the baseline and spreads
    # wider than the bare stem just above it.
    ink = _ink("I")
    assert -35 <= ink.bounds[1] <= -5
    foot, _ = _cut(ink, LineString([(-300, 6), (900, 6)]))
    assert foot >= MAIN * 1.1


def test_rising_diagonal_thins_toward_nib_angle():
    # The nib model itself: a stroke along the nib angle drags almost
    # none of the edge, one perpendicular to it drags all of it.
    along = _nib_width(math.cos(math.radians(35)), math.sin(math.radians(35)))
    vertical = _nib_width(0, 1)
    assert along <= HAIR * 1.01
    assert vertical >= MAIN * 0.99
    # And in the letterforms: x's rising stroke is visibly lighter than
    # its falling stroke (cut below their crossing; the foot diamonds
    # fatten both pieces, so only the ratio is asserted).
    _, pieces = _cut(_ink("x"), LineString([(-100, 110), (700, 110)]))
    assert len(pieces) == 2
    assert pieces[0] <= pieces[1] * 0.75


def test_verticalized_v_has_two_full_stems():
    # v is drawn textura-style: two heavy vertical runs, not diagonals.
    _, pieces = _cut(_ink("v"), LineString([(-100, 400), (700, 400)]))
    assert len(pieces) == 2
    assert all(p >= MAIN * 0.8 for p in pieces)


def test_fracture_flattens_curves():
    # The fractured O is a polygon of a few facets: far fewer outline
    # points than the sans' 64-segment ring even after corner softening.
    contours, _ = GLYPHS["O"]()
    assert all(len(c) <= 90 for c in contours)


def test_t_and_f_bars_clear_the_stem():
    for name in ("t", "f"):
        total, _ = _cut(_ink(name), LineString([(-100, 480), (700, 480)]))
        assert total >= 250, name
    assert _ink("f").bounds[2] >= 330  # f's flag reaches well right


def test_builds_are_deterministic():
    for name in ("I", "O", "g", "f"):
        assert GLYPHS[name]() == GLYPHS[name](), name


def test_full_font_builds(tmp_path):
    glyphs = {".notdef": (finalize([rect(60, 0, 460, CAP)]), 520)}
    for name, fn in GLYPHS.items():
        glyphs[name] = fn()
    glyphs = normalize_spacing(glyphs, side_bearing=38)
    out = tmp_path / "olde.ttf"
    build_font(glyphs, CMAP, "Aperture Olde", "Regular", str(out))
    assert out.stat().st_size > 0
