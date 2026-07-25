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

from fontgen.primitives import Point, finalize, record_strokes, stroke_union

SLANT_DEG = 12
SLANT = math.tan(math.radians(SLANT_DEG))

# Cursive joins happen low, around a third of the x-height: the exit
# tail ends at JOIN_Y, REACH to the right of the glyph's ink edge.
JOIN_Y = 160
REACH = 155

# Exit tails are drawn a touch lighter than the main strokes, which
# reads as the pen easing off pressure as it leaves the letter.
TAIL_WIDTH_RATIO = 0.8

# Where the pen may plausibly leave a letter: endpoints (or, for
# letters that end on a closed bowl, any point) in this y-band qualify
# as the tail's start.
EXIT_ZONE_Y = (-30, 290)

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
    c1 = (start[0] + span * 0.3, start[1] * 0.3)
    c2 = (end[0] - span * 0.3, JOIN_Y * 0.55)
    width = max(s["width"] for s in strokes) * TAIL_WIDTH_RATIO
    return {"pts": _cubic(start, c1, c2, end), "width": width, "closed": False}


def _slant(strokes: list[dict]) -> list[dict]:
    return [{**s, "pts": [(x + SLANT * y, y) for x, y in s["pts"]]} for s in strokes]


def script_strokes(name: str, fn) -> list[dict]:
    """The script variant's pen strokes for one glyph: recorded skeleton,
    plus exit tail for lowercase, then slanted.
    """
    with record_strokes() as strokes:
        fn()
    if name in LOWERCASE:
        tail = _exit_tail(strokes)
        if tail is not None:
            strokes = strokes + [tail]
    return _slant(strokes)


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
