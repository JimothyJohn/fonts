import random

import pytest

from fontgen.jitter import jitter_contours, jitter_glyph_set
from fontgen.primitives import contours_to_polygon

# Properly wound per the real convention (shells clockwise/negative area,
# holes counter-clockwise/positive area) -- matches what finalize() actually
# produces, unlike an arbitrary point order.
SQUARE = [(0, 0), (0, 100), (100, 100), (100, 0)]


def _area(pts):
    s = 0.0
    for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
        s += x0 * y1 - x1 * y0
    return abs(s) / 2


def _total_area(contours):
    poly = contours_to_polygon(contours)
    return poly.area


def test_jitter_is_deterministic_for_same_seed():
    a = jitter_contours([SQUARE], seed=42)
    b = jitter_contours([SQUARE], seed=42)
    assert a == b


def test_jitter_differs_for_different_seeds():
    a = jitter_contours([SQUARE], seed=1)
    b = jitter_contours([SQUARE], seed=2)
    assert a != b


def test_jitter_preserves_component_count():
    # a shell plus a disjoint, non-overlapping second shell (e.g. i's stem
    # + dot) -- the number of separate pieces should survive jittering
    # even though point counts change (buffering resamples corners).
    triangle = [(200, 200), (200, 220), (220, 200)]
    contours = [SQUARE, triangle]
    jittered = jitter_contours(contours, seed=7)
    assert len(jittered) == 2


def test_jitter_stays_within_bounds():
    jittered = jitter_contours(
        [SQUARE],
        seed=3,
        max_rotation_deg=1.0,
        max_dx=5,
        max_dy=5,
        max_scale_x=0.05,
        max_scale_y=0.05,
        max_stroke_delta=5,
    )
    xs = [x for c in jittered for x, _ in c]
    ys = [y for c in jittered for _, y in c]
    # small rotation + scale + stroke buffer + translation shouldn't move
    # a 100x100 box drastically
    assert min(xs) > -20
    assert max(xs) < 120
    assert min(ys) > -20
    assert max(ys) < 120


def test_jitter_handles_empty_contours():
    assert jitter_contours([], seed=1) == []


def test_jitter_glyph_set_preserves_advance_and_keys():
    glyphs = {
        "A": ([SQUARE], 100),
        "space": ([], 320),
    }
    jittered = jitter_glyph_set(glyphs, variant_seed=0)
    assert set(jittered.keys()) == set(glyphs.keys())
    assert jittered["A"][1] == 100
    assert jittered["space"] == ([], 320)


def test_jitter_glyph_set_differs_between_variants():
    glyphs = {"A": ([SQUARE], 100)}
    v0 = jitter_glyph_set(glyphs, variant_seed=0)
    v1 = jitter_glyph_set(glyphs, variant_seed=1)
    assert v0["A"][0] != v1["A"][0]


def test_contours_to_polygon_shell_only():
    poly = contours_to_polygon([SQUARE])
    assert poly.area == pytest.approx(10000, rel=1e-6)


def test_contours_to_polygon_subtracts_hole():
    hole = [(20, 20), (30, 20), (30, 30), (20, 30)]  # positive area = hole
    poly = contours_to_polygon([SQUARE, hole])
    assert poly.area == pytest.approx(10000 - 100, rel=1e-6)


def test_contours_to_polygon_keeps_disjoint_shells_separate():
    triangle = [(200, 200), (200, 220), (220, 200)]
    poly = contours_to_polygon([SQUARE, triangle])
    assert poly.area == pytest.approx(10000 + 200, rel=1e-6)


@pytest.mark.parametrize("seed", range(10))
def test_stroke_delta_grows_or_shrinks_area_as_predicted(seed):
    # Isolate stroke jitter by zeroing every other knob, then independently
    # replay the same RNG call order to predict the sign of stroke_delta.
    predicted_delta = random.Random(seed).uniform(-5.0, 5.0)
    jittered = jitter_contours(
        [SQUARE],
        seed=seed,
        max_rotation_deg=0,
        max_dx=0,
        max_dy=0,
        max_scale_x=0,
        max_scale_y=0,
        max_stroke_delta=5.0,
    )
    new_area = _total_area(jittered)
    original_area = _total_area([SQUARE])
    if predicted_delta > 0:
        assert new_area > original_area
    elif predicted_delta < 0:
        assert new_area < original_area


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_scale_jitter_changes_area_boundedly(seed):
    # with stroke jitter disabled, only rotation/scale/translation apply --
    # a rigid rotation+translation preserves area, so any change here comes
    # from the anisotropic scale, and it should stay small.
    jittered = jitter_contours(
        [SQUARE],
        seed=seed,
        max_stroke_delta=0,
    )
    new_area = _total_area(jittered)
    original_area = _total_area([SQUARE])
    ratio = new_area / original_area
    assert 0.85 < ratio < 1.15
