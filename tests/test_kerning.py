"""Geometry-derived kerning: the pairs a typographer would kern get
pulled in, the pairs the bearings already handle are left alone, nothing
collides, and the values round-trip through the built font's GPOS."""

import pytest
from fontTools.ttLib import TTFont

from fontgen.build import build_font, normalize_spacing
from fontgen.glyphs import CMAP
from fontgen.kerning import (
    FLOOR,
    MAX,
    MIN_KERN,
    _Glyph,
    _raw_gaps,
    _shared_rows,
    kern_feature,
    kern_pairs,
    kerning_from_font,
)
from fontgen.metrics import CAP, SIDE_BEARING
from fontgen.primitives import finalize, rect
from fontgen.sans import OPTICAL_TIGHTEN, make_glyphs, slant
from fontgen.spacing import apply_optical_bearings


@pytest.fixture(scope="module")
def spaced():
    glyphs = {name: fn() for name, fn in make_glyphs("Regular").items()}
    glyphs = normalize_spacing(glyphs, side_bearing=SIDE_BEARING)
    return apply_optical_bearings(glyphs, OPTICAL_TIGHTEN)


@pytest.fixture(scope="module")
def pairs(spaced):
    return kern_pairs(spaced)


@pytest.mark.parametrize(
    "left,right",
    [
        ("A", "V"),
        ("A", "W"),
        ("A", "Y"),
        ("L", "T"),
        ("T", "o"),
        ("T", "a"),
        ("T", "y"),
    ],
)
def test_classic_pairs_pull_in(pairs, left, right):
    assert pairs.get((left, right), 0) <= -40, (left, right, pairs.get((left, right)))


@pytest.mark.parametrize(
    "left,right",
    [("r", "period"), ("F", "comma"), ("P", "period"), ("seven", "period")],
)
def test_punctuation_tucks_under_overhangs(pairs, left, right):
    assert pairs.get((left, right), 0) <= -40


@pytest.mark.parametrize(
    "left,right",
    [
        ("H", "H"),
        ("n", "n"),
        ("o", "o"),
        ("o", "n"),
        ("n", "o"),
        ("k", "o"),
        ("d", "b"),
        ("I", "l"),
    ],
)
def test_pairs_the_bearings_already_handle_are_left_alone(pairs, left, right):
    assert (left, right) not in pairs


def test_figures_stay_tabular(pairs):
    digits = [
        "zero",
        "one",
        "two",
        "three",
        "four",
        "five",
        "six",
        "seven",
        "eight",
        "nine",
    ]
    assert not [p for p in pairs if p[0] in digits and p[1] in digits]


def test_kerns_are_negative_rounded_and_bounded(pairs):
    target = 2 * SIDE_BEARING
    for pair, v in pairs.items():
        assert -MAX * target - 1 <= v <= -MIN_KERN, (pair, v)
        assert v % 5 == 0, (pair, v)


def test_no_pair_collides_after_kerning(spaced, pairs):
    """Adversarial: for every emitted pair, the tightest row of raw ink
    is still at least FLOOR of the flat-flat gap apart."""
    profiles = {n: _Glyph(c, a) for n, (c, a) in spaced.items() if c}
    floor = FLOOR * 2 * SIDE_BEARING
    for (left, right), v in pairs.items():
        lp, rp = profiles[left], profiles[right]
        rows = _shared_rows(lp, rp)
        assert min(_raw_gaps(lp, rp, rows)) + v >= floor - 3, (left, right, v)


@pytest.mark.parametrize(
    "left,right", [("A", "V"), ("T", "o"), ("r", "period"), ("n", "n")]
)
def test_row_gaps_survive_the_shear(spaced, left, right):
    """Why the obliques reuse the upright's pairs: a shear about the
    baseline moves both glyphs of a row by the same amount, so every
    row's gap -- and therefore every kern -- is unchanged."""
    up = {n: _Glyph(*spaced[n]) for n in (left, right)}
    it = {
        n: _Glyph(*g) for n, g in slant({n: spaced[n] for n in (left, right)}).items()
    }
    rows = _shared_rows(up[left], up[right])
    assert rows == _shared_rows(it[left], it[right])
    for a, b in zip(
        _raw_gaps(up[left], up[right], rows), _raw_gaps(it[left], it[right], rows)
    ):
        assert a == pytest.approx(b, abs=1.0)


def test_feature_round_trips_through_the_font(tmp_path, spaced, pairs):
    glyphs = {".notdef": (finalize([rect(60, 0, 460, CAP)]), 520), **spaced}
    path = tmp_path / "k.ttf"
    build_font(
        glyphs,
        CMAP,
        "Aperture Sans",
        "Regular",
        str(path),
        features=kern_feature(pairs),
    )
    assert kerning_from_font(TTFont(str(path))) == pairs


def test_empty_pairs_make_no_feature():
    assert kern_feature({}) == ""
