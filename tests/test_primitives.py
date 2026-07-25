import math

import pytest

from fontgen.primitives import (
    arc_band,
    arc_pts,
    finalize,
    oriented,
    polygon_to_contours,
    rect,
    ring,
    signed_area,
    stroke_union,
    union_all,
)


def test_arc_pts_endpoints():
    pts = arc_pts(0, 0, 10, 0, 90, n=4)
    assert pts[0] == pytest.approx((10, 0))
    assert pts[-1] == pytest.approx((0, 10), abs=1e-9)
    assert len(pts) == 5


def test_arc_pts_reverse_direction():
    forward = arc_pts(0, 0, 10, 0, 180, n=8)
    backward = arc_pts(0, 0, 10, 180, 0, n=8)
    assert forward == list(reversed(backward))


def test_signed_area_square():
    ccw_square = [(0, 0), (1, 0), (1, 1), (0, 1)]
    assert signed_area(ccw_square) == pytest.approx(1.0)
    assert signed_area(list(reversed(ccw_square))) == pytest.approx(-1.0)


def test_oriented_flips_when_needed():
    ccw_square = [(0, 0), (1, 0), (1, 1), (0, 1)]
    cw = oriented(ccw_square, clockwise=True)
    assert signed_area(cw) < 0
    ccw = oriented(ccw_square, clockwise=False)
    assert signed_area(ccw) > 0


def test_stroke_union_single_segment_has_expected_width():
    shape = stroke_union([[(0, 0), (10, 0)]], width=4)
    minx, miny, maxx, maxy = shape.bounds
    assert miny == pytest.approx(-2, abs=1e-6)
    assert maxy == pytest.approx(2, abs=1e-6)
    # round caps extend the bounding box by ~half-width past each end
    assert minx < 0
    assert maxx > 10


def test_stroke_union_merges_overlapping_pieces_into_one_polygon():
    # a stem with a crossbar through its middle -- classic T-junction
    shape = stroke_union(
        [[(0, 0), (0, 10)], [(-5, 5), (5, 5)]], width=2, cap_style="flat"
    )
    contours = polygon_to_contours(shape)
    assert len(contours) == 1  # merged into one simple outline, no seam


def test_stroke_union_disconnected_pieces_stay_separate():
    shape = stroke_union([[(0, 0), (1, 0)], [(100, 100), (101, 100)]], width=0.5)
    contours = polygon_to_contours(shape)
    assert len(contours) == 2


def test_arc_band_is_a_ribbon_of_expected_radii():
    band = arc_band(0, 0, r=10, a0=0, a1=90, width=2)
    contour = polygon_to_contours(band)[0]
    radii = [math.hypot(x, y) for x, y in contour]
    assert min(radii) == pytest.approx(9, abs=0.1)
    assert max(radii) == pytest.approx(11, abs=0.1)


def test_ring_has_a_hole():
    shape = ring(0, 0, r_outer=10, r_inner=6)
    contours = polygon_to_contours(shape)
    assert len(contours) == 2
    outer, inner = contours
    assert signed_area(outer) < 0
    assert signed_area(inner) > 0


def test_rect_bounds():
    shape = rect(0, 0, 10, 20)
    contours = polygon_to_contours(shape)
    assert len(contours) == 1
    xs = [p[0] for p in contours[0]]
    ys = [p[1] for p in contours[0]]
    assert min(xs) == 0 and max(xs) == 10
    assert min(ys) == 0 and max(ys) == 20


def test_union_all_merges_overlapping_rects():
    shapes = [rect(0, 0, 10, 10), rect(5, 5, 15, 15)]
    merged = union_all(shapes)
    contours = polygon_to_contours(merged)
    assert len(contours) == 1


def test_finalize_drops_empty_shapes():
    contours = finalize([rect(0, 0, 1, 1), rect(0, 0, 0, 0)])
    assert len(contours) == 1
