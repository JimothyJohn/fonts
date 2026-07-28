"""Aperture Marquee: a carnival-lightbulb face generated from the same
glyph skeletons as the sans.

Every recorded pen stroke is resampled at even arc-length and replaced
by a run of round bulbs -- the letters read as marquee signage, each
stroke a string of lights. Nothing else from the other faces applies:
no contrast model, no serifs, no fracture; the skeleton IS the letter,
displayed as dots.

Details that keep it signage rather than mush:

- Bulbs land ON stroke endpoints (a stem gets a bulb exactly at its
  top and foot), with the interior spaced evenly between them, so
  letters keep their full intended extent.
- Junction dedupe: where strokes meet (T-joins, bowl-to-stem), two
  bulbs would stack into a blob; any bulb landing too close to an
  already-placed one is skipped.
- A seeded fraction of bulbs are "burnt out" -- drawn as rings instead
  of discs -- which is what makes it signage instead of a dotted line.
- The skeletons' own dots (i/j dots, period, colon) become single
  slightly-larger bulbs.

All variation (burnt-out picks, bulb size and placement jitter) is
seeded from glyph/stroke names via zlib.crc32, so builds stay
byte-identical, matching the other faces.
"""

import itertools
import math
import zlib

from shapely import geometry as sg

from fontgen.primitives import Point, finalize, record_strokes

# Bulb geometry: disc radius, center-to-center pitch along the stroke,
# and how close two bulbs may sit before the later one is skipped.
BULB_R = 44.0
PITCH = 96.0
MIN_SEP = 0.75 * PITCH

# Burnt-out bulbs: fraction drawn as rings, and the ring's inner radius
# relative to the bulb.
BURNT_FRACTION = 0.15
RING_INNER = 0.52

# Humanizing jitter, seeded: bulb radius drift and center scatter.
RADIUS_VAR = 0.10
SCATTER = 5.0

# A recorded stroke this short is one of the skeletons' own dots
# (i's dot, the period); it becomes a single larger bulb.
DOT_MAX_LEN = 12.0
DOT_BULB_SCALE = 1.15

QUAD_SEGS = 16


def _rand(key: str, lo: float, hi: float) -> float:
    return lo + (hi - lo) * (zlib.crc32(key.encode()) / 0xFFFFFFFF)


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


def _bulb(name: str, index: int, center: Point, r: float, can_burn: bool = True):
    """One bulb: a disc, or -- for the seeded burnt-out fraction -- a
    ring. Structural bulbs (stroke endpoints, the skeletons' own dots)
    never burn: a ring at a terminal reads as debris, and a burnt-out
    period is a degree sign."""
    r *= 1 + _rand(f"{name}:{index}:r", -RADIUS_VAR, RADIUS_VAR)
    cx = center[0] + _rand(f"{name}:{index}:x", -SCATTER, SCATTER)
    cy = center[1] + _rand(f"{name}:{index}:y", -SCATTER, SCATTER)
    disc = sg.Point(cx, cy).buffer(r, quad_segs=QUAD_SEGS)
    if can_burn and _rand(f"{name}:{index}:burnt", 0.0, 1.0) < BURNT_FRACTION:
        return disc.difference(
            sg.Point(cx, cy).buffer(r * RING_INNER, quad_segs=QUAD_SEGS)
        )
    return disc


def marquee_shapes(name: str, fn) -> tuple[list, float]:
    """All bulb shapes for one glyph plus its advance width."""
    with record_strokes() as strokes:
        _, advance, _terminals = fn()
    placed: list[Point] = []
    shapes = []
    index = 0
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
            is_dot = True
        else:
            centers, r = _resample(pts, closed), BULB_R
            is_dot = False
        for j, c in enumerate(centers):
            if any(math.dist(c, p) < MIN_SEP for p in placed):
                continue
            placed.append(c)
            endpoint = not closed and j in (0, len(centers) - 1)
            shapes.append(_bulb(name, index, c, r, can_burn=not (is_dot or endpoint)))
            index += 1
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
