import pytest
from shapely.geometry import LineString

from fontgen.build import build_font, normalize_spacing
from fontgen.glyphs import CMAP, SKELETONS
from fontgen.metrics import CAP, MID
from fontgen.moderne import HAIR, MAIN, THIN_W, make_glyphs
from fontgen.primitives import contours_to_polygon, finalize, rect

GLYPHS = make_glyphs(SKELETONS)


def _ink(name):
    contours, _ = GLYPHS[name]()
    return contours_to_polygon(contours)


def _cut(ink, line):
    """Total ink thickness along a straight cut, plus the pieces."""
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


def test_stem_carries_main_weight():
    # A horizontal cut through I's waist crosses exactly the stem.
    total, _ = _cut(_ink("I"), LineString([(-100, MID), (800, MID)]))
    assert MAIN * 0.9 <= total <= MAIN * 1.15


def test_crossbar_is_hairline():
    # A vertical cut between H's stems crosses only the crossbar.
    total, _ = _cut(_ink("H"), LineString([(320, -100), (320, 800)]))
    assert HAIR * 0.8 <= total <= HAIR * 1.4


def test_O_has_vertical_stress():
    ink = _ink("O")
    cx = (ink.bounds[0] + ink.bounds[2]) / 2
    cy = (ink.bounds[1] + ink.bounds[3]) / 2
    sides, side_pieces = _cut(ink, LineString([(-500, cy), (1500, cy)]))
    waist, waist_pieces = _cut(ink, LineString([(cx, -500), (cx, 1500)]))
    assert len(side_pieces) == 2 and len(waist_pieces) == 2
    # Thick left/right walls, hairline top/bottom -- the didone axis.
    assert sides > waist * 2.5
    assert waist <= HAIR * 2.6


def test_serif_widens_the_foot():
    # Near the baseline, I's slab serif far exceeds the bare stem.
    total, _ = _cut(_ink("I"), LineString([(-300, 10), (900, 10)]))
    assert total >= MAIN * 1.4


def test_N_stems_are_demoted_thin():
    _, pieces = _cut(_ink("N"), LineString([(-100, MID), (900, MID)]))
    assert len(pieces) == 3
    # Both vertical stems are hairlines; the diagonal carries the weight.
    assert pieces[0] <= THIN_W * 1.3
    assert pieces[1] <= THIN_W * 1.3
    assert max(pieces) >= MAIN * 0.9


def test_downleft_diagonal_demoted_in_V_but_not_Z():
    # V: down-right leg thick, down-left leg hairline-thin.
    _, v_pieces = _cut(_ink("V"), LineString([(-100, MID), (900, MID)]))
    assert len(v_pieces) == 2
    assert v_pieces[0] <= THIN_W * 1.6
    assert v_pieces[1] >= MAIN * 0.9
    # Z's identity lives in its down-left diagonal: it must stay thick.
    _, z_pieces = _cut(_ink("Z"), LineString([(-100, MID), (900, MID)]))
    assert max(z_pieces) >= MAIN * 0.8


def test_full_font_builds(tmp_path):
    glyphs = {".notdef": (finalize([rect(60, 0, 460, CAP)]), 520)}
    for name, fn in GLYPHS.items():
        glyphs[name] = fn()
    glyphs = normalize_spacing(glyphs, side_bearing=52)
    out = tmp_path / "moderne.ttf"
    build_font(glyphs, CMAP, "Aperture Moderne", "Regular", str(out))
    assert out.stat().st_size > 0
