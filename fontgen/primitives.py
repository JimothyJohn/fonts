"""Geometry helpers for building glyph outlines via stroke-then-union.

Every glyph is built as a set of shapes (strokes, rings, arc bands) that get
unioned into one clean outline per glyph. Unioning is what avoids visible
internal seams at T-junctions and joints -- two overlapping filled shapes
merge into a single simple contour instead of sitting on top of each other
as separate overlapping outlines. Shapely (via GEOS) does the actual
boolean geometry; this module just wraps it with the font-shape vocabulary
(strokes, arc bands, rings) and converts the result to the flat point-list
contours the TrueType pen expects.
"""

import math
from contextlib import contextmanager

from shapely import geometry as sg
from shapely.ops import unary_union

Point = tuple[float, float]

# Active stroke recorder (see record_strokes). When set, every primitive
# appends the centerline it is about to buffer -- the "pen path" -- so
# consumers like the handwriting demo can replay how a glyph is drawn
# without re-deriving skeletons from the filled outlines.
_RECORDER: list | None = None


@contextmanager
def record_strokes():
    """Capture the centerline of every primitive built inside the block.

    Yields a list that fills with {"pts", "width", "closed"} dicts in
    construction order -- which follows each glyph function's authoring
    order, a natural proxy for pen/stroke order. Nesting restores the
    outer recorder on exit.
    """
    global _RECORDER
    previous = _RECORDER
    _RECORDER = strokes = []
    try:
        yield strokes
    finally:
        _RECORDER = previous


def _record(pts: list[Point], width: float, closed: bool = False) -> None:
    if _RECORDER is not None and len(pts) >= 1:
        _RECORDER.append(
            {"pts": [tuple(p) for p in pts], "width": width, "closed": closed}
        )


# Segments per full circle when approximating curves/round joins. Higher is
# smoother; this is the shared knob for how "curvy" round strokes look.
CURVE_SEGMENTS = 64


def arc_pts(
    cx: float, cy: float, r: float, a0: float, a1: float, n: int | None = None
) -> list[Point]:
    """Sample points along a circular arc from angle a0 to a1 (degrees).

    a0/a1 may be given in either order; the arc walks directly from a0 to a1
    (no implicit shortest-path wraparound), so callers control direction by
    choosing angle values (e.g. a1 = a0 - 270 to go the "long way" clockwise).
    """
    if n is None:
        n = max(8, round(CURVE_SEGMENTS * abs(a1 - a0) / 360))
    return [
        (
            cx + r * math.cos(math.radians(a)),
            cy + r * math.sin(math.radians(a)),
        )
        for a in [a0 + (a1 - a0) * i / n for i in range(n + 1)]
    ]


def ellipse_pts(
    cx: float,
    cy: float,
    rx: float,
    ry: float,
    a0: float,
    a1: float,
    n: int | None = None,
) -> list[Point]:
    """Sample points along an elliptical arc -- arc_pts with independent
    x/y radii, for bowls that bulge out wider than they are tall.
    """
    if n is None:
        n = max(8, round(CURVE_SEGMENTS * abs(a1 - a0) / 360))
    return [
        (
            cx + rx * math.cos(math.radians(a)),
            cy + ry * math.sin(math.radians(a)),
        )
        for a in [a0 + (a1 - a0) * i / n for i in range(n + 1)]
    ]


def signed_area(points: list[Point]) -> float:
    area = 0.0
    for (x0, y0), (x1, y1) in zip(points, points[1:] + points[:1]):
        area += x0 * y1 - x1 * y0
    return area / 2.0


def oriented(points: list[Point], clockwise: bool) -> list[Point]:
    """Return points wound in the requested direction (y-up convention)."""
    area = signed_area(points)
    is_ccw = area > 0
    wants_ccw = not clockwise
    if is_ccw == wants_ccw:
        return points
    return list(reversed(points))


def stroke_union(
    point_lists,
    width: float,
    closed: bool = False,
    join_style: str = "round",
    cap_style: str = "round",
):
    """Stroke one or more polylines and union them into one shape.

    Disconnected pieces that happen to overlap (e.g. a T-junction between a
    stem and a crossbar) merge cleanly instead of leaving overlapping
    outlines. `join_style`/`cap_style` follow Shapely's buffer vocabulary
    ("round", "mitre", "bevel" for joins; "round", "flat", "square" for caps).
    """
    quad_segs = max(2, CURVE_SEGMENTS // 4)
    shapes = []
    for pts in point_lists:
        if len(pts) < 2:
            continue
        _record(list(pts), width, closed=closed)
        line = sg.LinearRing(pts) if closed else sg.LineString(pts)
        shapes.append(
            line.buffer(
                width / 2,
                quad_segs=quad_segs,
                cap_style=cap_style,
                join_style=join_style,
            )
        )
    if not shapes:
        return sg.Polygon()
    return unary_union(shapes)


def arc_band(
    cx: float,
    cy: float,
    r: float,
    a0: float,
    a1: float,
    width: float,
    cap_style: str = "flat",
):
    """A thick ribbon following an arc. Flush (flat) cut ends by default,
    for bowls/hooks that butt up against a straight stem; pass
    cap_style="round" for a free-floating open terminal (e.g. C's ends).
    """
    pts = arc_pts(cx, cy, r, a0, a1)
    _record(pts, width)
    quad_segs = max(2, CURVE_SEGMENTS // 4)
    return sg.LineString(pts).buffer(
        width / 2, quad_segs=quad_segs, cap_style=cap_style, join_style="round"
    )


def ellipse_band(
    cx: float,
    cy: float,
    rx: float,
    ry: float,
    a0: float,
    a1: float,
    width: float,
    cap_style: str = "flat",
):
    """A thick ribbon following an elliptical arc -- arc_band with
    independent x/y radii, for a bowl that's rounder/fuller than a
    circular arc of the same height would allow (e.g. D/B/P/R's bowls,
    which bulge out wider than their half-height).
    """
    pts = ellipse_pts(cx, cy, rx, ry, a0, a1)
    _record(pts, width)
    quad_segs = max(2, CURVE_SEGMENTS // 4)
    return sg.LineString(pts).buffer(
        width / 2, quad_segs=quad_segs, cap_style=cap_style, join_style="round"
    )


def ring(cx: float, cy: float, r_outer: float, r_inner: float):
    """A full annulus (e.g. 'O')."""
    r_mid = (r_outer + r_inner) / 2
    _record(arc_pts(cx, cy, r_mid, 90, 450), r_outer - r_inner, closed=True)
    quad_segs = max(2, CURVE_SEGMENTS // 4)
    outer = sg.Point(cx, cy).buffer(r_outer, quad_segs=quad_segs)
    inner = sg.Point(cx, cy).buffer(r_inner, quad_segs=quad_segs)
    return outer.difference(inner)


def rect(x0: float, y0: float, x1: float, y1: float):
    # Centerline: the midline of the long axis, pulled in by half the short
    # side at each end so a round-capped stroke covers the same extent. A
    # square degenerates to a dot.
    w, h = x1 - x0, y1 - y0
    if w >= h:
        cy, half = (y0 + y1) / 2, h / 2
        a, b = min(x0 + half, (x0 + x1) / 2), max(x1 - half, (x0 + x1) / 2)
        _record([(a, cy), (max(b, a + 0.5), cy)], h)
    else:
        cx, half = (x0 + x1) / 2, w / 2
        a, b = min(y0 + half, (y0 + y1) / 2), max(y1 - half, (y0 + y1) / 2)
        _record([(cx, a), (cx, max(b, a + 0.5))], w)
    return sg.box(x0, y0, x1, y1)


def disc(cx: float, cy: float, r: float):
    """A filled circle -- used for dots (i, j)."""
    _record([(cx, cy), (cx + 0.5, cy)], 2 * r)
    quad_segs = max(2, CURVE_SEGMENTS // 4)
    return sg.Point(cx, cy).buffer(r, quad_segs=quad_segs)


def union_all(shapes):
    return unary_union([s for s in shapes if s is not None and not s.is_empty])


def polygon_to_contours(geom) -> list[list[Point]]:
    """Flatten a Shapely (Multi)Polygon into pen-ready contours: exterior
    rings clockwise, hole rings counter-clockwise, closing point dropped.
    """
    if geom is None or geom.is_empty:
        return []
    polys = list(geom.geoms) if hasattr(geom, "geoms") else [geom]
    contours = []
    for poly in polys:
        if poly.is_empty:
            continue
        contours.append(oriented(list(poly.exterior.coords)[:-1], clockwise=True))
        for interior in poly.interiors:
            contours.append(oriented(list(interior.coords)[:-1], clockwise=False))
    return contours


def finalize(shapes) -> list[list[Point]]:
    """Union a list of shapes for one glyph and flatten to pen contours."""
    return polygon_to_contours(union_all(shapes))


def contours_to_polygon(contours: list[list[Point]]):
    """Rebuild the actual filled shape (shells minus holes) from flattened
    contours -- the inverse of polygon_to_contours/finalize. Uses winding
    direction to tell shells from holes (matches polygon_to_contours'
    convention: shells clockwise, holes counter-clockwise), unioning all
    shells and subtracting all holes so it reconstructs the right shape
    even when a glyph has several disjoint pieces (e.g. i's stem + dot),
    since a hole only ever coincides with the one shell it belongs to.

    Used to re-open already-finalized glyph contours for further editing
    (jitter's post-hoc distortion, the serif finisher's added feet)
    without needing the original pre-finalize shape list.
    """
    shells, holes = [], []
    for c in contours:
        if len(c) < 3:
            continue
        poly = sg.Polygon(c)
        if not poly.is_valid:
            poly = poly.buffer(0)
        if signed_area(c) < 0:
            shells.append(poly)
        else:
            holes.append(poly)
    if not shells:
        return sg.Polygon()
    shape = unary_union(shells)
    if holes:
        shape = shape.difference(unary_union(holes))
    return shape
