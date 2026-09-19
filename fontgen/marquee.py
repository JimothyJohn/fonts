"""Aperture Marquee: a carnival-lightbulb face generated from the same
glyph skeletons as the sans.

Every recorded pen stroke is resampled at even arc-length and replaced
by a run of round bulbs -- the letters read as marquee signage, each
stroke a string of lights. Nothing else from the other faces applies:
no contrast model, no serifs, no fracture; the skeleton IS the letter,
displayed as dots.

Details that keep it signage rather than mush:

- Every bulb is a RING: a black rim around a white interior, a stroked
  circle rather than a filled one, so a run of them reads as glass
  bulbs instead of a dotted line.
- Bulbs land ON stroke endpoints (a stem gets a bulb exactly at its
  top and foot), with the interior spaced evenly between them, so
  letters keep their full intended extent.
- Junction dedupe: where strokes meet (T-joins, bowl-to-stem), two
  bulbs would stack into a blob; any bulb landing too close to an
  already-placed one is skipped.
- The skeletons' own dots (i/j dots, period, colon) become single
  slightly-larger bulbs.

Nothing is randomized: the face is typeset, every letter the same
string of bulbs every time.
"""

import itertools
import math

from shapely import geometry as sg

from fontgen.primitives import Point, finalize, record_strokes

# Bulb geometry: bulb radius, the rim's thickness (every bulb is a
# ring -- black rim, white interior -- a stroked circle, not a filled
# one), center-to-center pitch along the stroke, and how close two
# bulbs may sit before the later one is skipped.
BULB_R = 44.0
RIM = 18.0
PITCH = 96.0
MIN_SEP = 0.75 * PITCH

# A recorded stroke this short is one of the skeletons' own dots
# (i's dot, the period); it becomes a single larger bulb.
DOT_MAX_LEN = 12.0
DOT_BULB_SCALE = 1.15

QUAD_SEGS = 16


def _resample(pts: list[Point], closed: bool) -> list[Point]:
    """Evenly spaced bulb centers along a polyline, endpoints included
    (for closed strokes the wrap segment is part of the walk and no
    duplicate endpoint is emitted)."""
    path = [*pts, pts[0]] if closed else list(pts)
    lengths = [math.dist(a, b) for a, b in itertools.pairwise(path)]
    total = sum(lengths)
    if total < 1e-6:
        return [path[0]]
    n = max(1, round(total / PITCH))
    targets = [total * i / n for i in range(n if closed else n + 1)]
    out = []
    seg, walked = 0, 0.0
    for t in targets:
        while seg < len(lengths) - 1 and walked + lengths[seg] < t:
            walked += lengths[seg]
            seg += 1
        (x0, y0), (x1, y1) = path[seg], path[seg + 1]
        f = (t - walked) / lengths[seg] if lengths[seg] > 0 else 0.0
        out.append((x0 + (x1 - x0) * f, y0 + (y1 - y0) * f))
    return out


def _bulb(center: Point, r: float):
    """One bulb: a ring of outer radius r and a RIM-thick wall."""
    cx, cy = center
    outer = sg.Point(cx, cy).buffer(r, quad_segs=QUAD_SEGS)
    inner = sg.Point(cx, cy).buffer(max(r - RIM, 1.0), quad_segs=QUAD_SEGS)
    return outer.difference(inner)


def marquee_shapes(name: str, fn) -> tuple[list, float]:
    """All bulb shapes for one glyph plus its advance width."""
    with record_strokes() as strokes:
        _, advance, _terminals = fn()
    placed: list[Point] = []
    shapes = []
    for stroke in strokes:
        pts = [tuple(p) for p in stroke["pts"]]
        closed = stroke["closed"]
        if closed and len(pts) > 1 and math.dist(pts[0], pts[-1]) < 1e-6:
            pts = pts[:-1]
        if not pts:
            continue
        path_len = sum(math.dist(a, b) for a, b in itertools.pairwise(pts))
        if len(pts) < 2 or path_len < DOT_MAX_LEN:
            centers, r = [pts[0]], (stroke["width"] / 2) * DOT_BULB_SCALE
        else:
            centers, r = _resample(pts, closed), BULB_R
        for c in centers:
            if any(math.dist(c, p) < MIN_SEP for p in placed):
                continue
            placed.append(c)
            shapes.append(_bulb(c, r))
    return shapes, advance


def _build(name: str, fn):
    def build():
        shapes, advance = marquee_shapes(name, fn)
        return finalize(shapes), advance

    return build


def make_glyphs(skeletons: dict) -> dict:
    """name -> () -> (contours, advance) for the marquee face -- the
    same contract GLYPHS exposes for the sans."""
    return {name: _build(name, fn) for name, fn in skeletons.items()}
