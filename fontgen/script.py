"""Aperture Script: a slanted, cursive-flavored variant generated from
the same glyph skeletons as the sans.

Rather than re-authoring 69 glyphs, this replays each glyph function
under primitives.record_strokes() to get its centerline pen strokes,
then transforms the strokes:

- lowercase letters grow an exit tail -- a swash curving from wherever
  the pen naturally finishes near the baseline up into the letter gap at
  join height, so words read as connected flow (the tail is the next
  letter's entry, cursive-style; side bearings are tightened by the
  build script so tails almost touch the following letter's ink);
- everything is sheared right by SLANT_DEG (caps, digits, and
  punctuation get the slant only, matching script faces where capitals
  stand unjoined).

The transformed strokes are re-buffered with the same stroke-then-union
machinery the other fonts use, so joins and T-junctions stay seamless.
"""

import math
import string
import zlib

from fontgen.metrics import X_HEIGHT
from fontgen.primitives import Point, finalize, record_strokes, stroke_union

SLANT_DEG = 12
SLANT = math.tan(math.radians(SLANT_DEG))

# Cursive joins happen low, around a third of the x-height: the exit
# tail ends at JOIN_Y, REACH to the right of the glyph's ink edge.
JOIN_Y = 160
REACH = 170

# Exit tails and loop up-strokes are drawn a touch lighter than the
# main strokes, which reads as the pen easing off pressure.
TAIL_WIDTH_RATIO = 0.8
LOOP_WIDTH_RATIO = 0.85

# Where the pen may plausibly leave a letter: endpoints (or, for
# letters that end on a closed bowl, any point) in this y-band qualify
# as the tail's start.
EXIT_ZONE_Y = (-30, 290)

# Cursive loops. Ascenders (a full-height 2-pt vertical stem) get an
# up-stroke that bows LOOP_W out to the right and rejoins the stem at
# its apex, closing the loop where it leaves the stem near x-height --
# the classic looped l. Descenders on p/q get the mirrored loop below
# the baseline; q loops right instead of left, per cursive convention.
ASC_LOOP_LETTERS = set("bdfhkl")
DESC_LOOP_SIDE = {"p": -1, "q": 1}
LOOP_W = 105
ASC_CROSS_Y = X_HEIGHT * 0.58
ASC_MIN_TOP = 660
DESC_MAX_BOTTOM = -150

# Naturalness: any long ruler-straight segment gets a subtle bow --
# resampled with a one-hump perpendicular sine displacement, direction
# chosen deterministically per (glyph, stroke) so builds are stable.
BOW_MAX = 13
BOW_MIN_LEN = 150

LOWERCASE = set(string.ascii_lowercase)


def _cubic(p0: Point, p1: Point, p2: Point, p3: Point, n: int = 14) -> list[Point]:
    pts = []
    for i in range(n + 1):
        t = i / n
        u = 1 - t
        pts.append(
            (
                u**3 * p0[0]
                + 3 * u**2 * t * p1[0]
                + 3 * u * t**2 * p2[0]
                + t**3 * p3[0],
                u**3 * p0[1]
                + 3 * u**2 * t * p1[1]
                + 3 * u * t**2 * p2[1]
                + t**3 * p3[1],
            )
        )
    return pts


def _exit_point(strokes: list[dict]) -> Point | None:
    """Where the pen leaves the letter: the rightmost open-stroke endpoint
    inside the exit zone, else (for bowl-final letters like o) the
    rightmost point anywhere on a stroke inside the zone.
    """
    lo, hi = EXIT_ZONE_Y

    def in_zone(p: Point) -> bool:
        return lo <= p[1] <= hi

    endpoints = [
        p
        for s in strokes
        if not s["closed"] and len(s["pts"]) >= 2
        for p in (s["pts"][0], s["pts"][-1])
        if in_zone(p)
    ]
    if endpoints:
        return max(endpoints, key=lambda p: p[0])
    everywhere = [p for s in strokes for p in s["pts"] if in_zone(p)]
    if everywhere:
        return max(everywhere, key=lambda p: p[0])
    return None


def _exit_tail(strokes: list[dict]) -> dict | None:
    start = _exit_point(strokes)
    if start is None:
        return None
    x_max = max(x for s in strokes for x, _ in s["pts"])
    end = (x_max + REACH, JOIN_Y)
    span = end[0] - start[0]
    if span <= 0:
        return None
    # Sag close to the baseline before hooking up late -- a rounder,
    # more pen-like swash than an even S-curve.
    c1 = (start[0] + span * 0.22, start[1] * 0.12)
    c2 = (end[0] - span * 0.30, JOIN_Y * 0.18)
    width = max(s["width"] for s in strokes) * TAIL_WIDTH_RATIO
    return {"pts": _cubic(start, c1, c2, end), "width": width, "closed": False}


def _vertical_stem(s: dict) -> bool:
    return (
        not s["closed"]
        and len(s["pts"]) == 2
        and abs(s["pts"][0][0] - s["pts"][1][0]) < 1
    )


def _loop_stroke(sx: float, base: Point, tip_y: float, side: int, width: float) -> dict:
    """An up-stroke from `base` on the stem that bows `side * LOOP_W` out
    and rejoins the stem at (sx, tip_y), enclosing a loop between itself
    and the stem."""
    rise = tip_y - base[1]
    c1 = (sx + side * LOOP_W * 1.15, base[1] + rise * 0.3)
    c2 = (sx + side * LOOP_W * 0.55, tip_y - rise * 0.05)
    return {
        "pts": _cubic(base, c1, c2, (sx, tip_y)),
        "width": width * LOOP_WIDTH_RATIO,
        "closed": False,
    }


def _add_loops(name: str, strokes: list[dict]) -> list[dict]:
    out = list(strokes)
    for s in strokes:
        if not _vertical_stem(s):
            continue
        sx = s["pts"][0][0]
        ys = (s["pts"][0][1], s["pts"][1][1])
        if name in ASC_LOOP_LETTERS and max(ys) >= ASC_MIN_TOP:
            out.append(_loop_stroke(sx, (sx, ASC_CROSS_Y), max(ys), 1, s["width"]))
        if name in DESC_LOOP_SIDE and min(ys) <= DESC_MAX_BOTTOM:
            side = DESC_LOOP_SIDE[name]
            out.append(_loop_stroke(sx, (sx, -5), min(ys), side, s["width"]))
    return out


def _bow(name: str, index: int, s: dict) -> dict:
    """Replace a long straight 2-pt stroke with a gently curved sample of
    itself: same endpoints, a one-hump sine bow perpendicular to the
    segment. Kills the ruler-drawn look without touching the metrics."""
    if s["closed"] or len(s["pts"]) != 2:
        return s
    (x0, y0), (x1, y1) = s["pts"]
    length = math.hypot(x1 - x0, y1 - y0)
    if length < BOW_MIN_LEN:
        return s
    sign = 1 if zlib.crc32(f"{name}:{index}".encode()) & 1 else -1
    amp = sign * min(BOW_MAX, length * 0.04)
    nx, ny = -(y1 - y0) / length, (x1 - x0) / length
    n = 12
    pts = []
    for i in range(n + 1):
        t = i / n
        w = math.sin(math.pi * t) * amp
        pts.append((x0 + (x1 - x0) * t + nx * w, y0 + (y1 - y0) * t + ny * w))
    return {**s, "pts": pts}


def _naturalize(name: str, strokes: list[dict]) -> list[dict]:
    return [_bow(name, i, s) for i, s in enumerate(strokes)]


def _slant(strokes: list[dict]) -> list[dict]:
    return [{**s, "pts": [(x + SLANT * y, y) for x, y in s["pts"]]} for s in strokes]


def script_strokes(name: str, fn) -> list[dict]:
    """The script variant's pen strokes for one glyph: recorded skeleton,
    plus cursive loops and exit tail for lowercase and a soft bow on
    every long straight stroke, then slanted.
    """
    with record_strokes() as strokes:
        fn()
    if name in LOWERCASE:
        strokes = _add_loops(name, strokes)
        # Tail before bowing: the exit point must come from the authored
        # geometry -- a bowed stem gains interior points that would
        # otherwise masquerade as exit candidates (j grew a bogus tail).
        tail = _exit_tail(strokes)
        if tail is not None:
            strokes = strokes + [tail]
    return _slant(_naturalize(name, strokes))


def _build(name: str, fn):
    def build():
        strokes = script_strokes(name, fn)
        shapes = [
            stroke_union([s["pts"]], s["width"], closed=s["closed"]) for s in strokes
        ]
        _, advance, _terminals = fn()
        return finalize(shapes), advance

    return build


def make_glyphs(skeletons: dict) -> dict:
    """name -> () -> (contours, advance) for the script face -- the same
    contract GLYPHS exposes for the sans.
    """
    return {name: _build(name, fn) for name, fn in skeletons.items()}
