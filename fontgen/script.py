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
# Spacing ignores the tail (see body_bounds), so the tip lands REACH
# minus both letters' side bearings INSIDE the next letter's ink, where
# it meets a stem or bowl instead of pointing at a gap.
JOIN_Y = 160
REACH = 150

# Exit tails and loop up-strokes are drawn a touch lighter than the
# main strokes, which reads as the pen easing off pressure.
TAIL_WIDTH_RATIO = 0.8
LOOP_WIDTH_RATIO = 0.85

# Where the pen may plausibly leave a letter: endpoints (or, for
# letters that end on a closed bowl, any point) in this y-band qualify
# as the tail's start.
EXIT_ZONE_Y = (-30, 290)

# ...and only from the letter's right side: the exit may sit at most
# this far inside the body's right edge. t's crossbar overhangs its stem
# by 110 and keeps its tail; f's hook (130), r's arm, s's lower-left
# terminal and b/p's stems are out -- those tails slashed through the
# bowl or turned r into c and f into t.
EXIT_MAX_INSET = 120

# Cursive loops. Ascenders (a full-height 2-pt vertical stem) get an
# up-stroke that bows LOOP_W out to the right and rejoins the stem at
# its apex, closing the loop where it leaves the stem near x-height --
# the classic looped l. Descenders on p/q get the mirrored loop below
# the baseline; q loops right instead of left, per cursive convention.
# f is excluded: its skeleton already hooks at the top, and a loop on
# top of the hook turned the letter into an unreadable knot.
ASC_LOOP_LETTERS = set("bdhkl")
DESC_LOOP_SIDE = {"p": -1, "q": 1}

# Letters whose pen finishes somewhere a rising baseline tail would
# cross the letter's own ink (descender flicks and hooks on g/y, q's
# under-loop; j's hook was always excluded by geometry). They exit
# through their descender instead, like real cursive.
NO_TAIL = set("gqy")

# Letters that join the next letter from the TOP in real handwriting:
# o closes its bowl at the top right, v/w finish their last upstroke at
# x-height. A baseline tail on these read as a completely different
# letter (o + low tail = a; v/w + low tail = checkmarks).
TOP_EXIT = set("ovw")
TOP_JOIN_Y = X_HEIGHT * 0.72
LOOP_W = 105
ASC_CROSS_Y = X_HEIGHT * 0.58
ASC_MIN_TOP = 660
DESC_MAX_BOTTOM = -150

# Naturalness, for the hand face only: any long ruler-straight segment
# gets a subtle bow -- resampled with a one-hump perpendicular sine
# displacement, direction chosen deterministically per (glyph, stroke)
# so builds are stable. The script face sets its stems straight, like
# every face but hand.
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


def _ground_stem(strokes: list[dict]) -> list[dict]:
    """u's right stem stops where its bowl begins, so the pen never
    reaches the baseline on that side. Run such a stem -- a vertical on
    the letter's right whose foot hangs in the exit zone, joined to
    another stroke -- down to the baseline, giving the tail a foot to
    leave from (as on a/d/n) instead of dangling off the junction."""
    x_max = max(x for s in strokes for x, _ in s["pts"])
    ends = [p for s in strokes if not s["closed"] for p in (s["pts"][0], s["pts"][-1])]
    out = []
    for s in strokes:
        if _vertical_stem(s):
            i = 0 if s["pts"][0][1] < s["pts"][1][1] else 1
            foot = s["pts"][i]
            if (
                0 < foot[1] <= EXIT_ZONE_Y[1]
                and foot[0] >= x_max - EXIT_MAX_INSET
                and sum(1 for e in ends if math.dist(e, foot) < 1) > 1
            ):
                pts = list(s["pts"])
                pts[i] = (foot[0], 0.0)
                s = {**s, "pts": pts}
        out.append(s)
    return out


def _exit(strokes: list[dict]) -> tuple[Point, Point] | None:
    """Where the pen leaves the letter, and the direction it is
    travelling there: the rightmost pen-lift inside the exit zone. A
    pen-lift is an open stroke's endpoint that no other stroke shares
    (e's crossbar meets its bowl at the right; the pen does not lift
    there). None when that point is not on the letter's right side: a
    tail from b/p/r/s/f's left would run through or under the letter's
    own body.
    """
    lo, hi = EXIT_ZONE_Y
    opens = [s["pts"] for s in strokes if not s["closed"] and len(s["pts"]) >= 2]
    ends = [(p[i], p[i + step]) for p in opens for i, step in ((0, 1), (-1, -1))]
    lifts = [
        (at, prev)
        for at, prev in ends
        if lo <= at[1] <= hi and sum(1 for e, _ in ends if math.dist(e, at) < 1) == 1
    ]
    if not lifts:
        return None
    at, prev = max(lifts, key=lambda e: e[0][0])
    x_max = max(x for s in strokes for x, _ in s["pts"])
    if at[0] < x_max - EXIT_MAX_INSET:
        return None
    d = math.hypot(at[0] - prev[0], at[1] - prev[1]) or 1.0
    return at, ((at[0] - prev[0]) / d, (at[1] - prev[1]) / d)


def _exit_tail(strokes: list[dict]) -> dict | None:
    found = _exit(strokes)
    if found is None:
        return None
    start, (dx, dy) = found
    x_max = max(x for s in strokes for x, _ in s["pts"])
    end = (x_max + REACH, JOIN_Y)
    span = end[0] - start[0]
    if span <= 0:
        return None
    if dx > 0 and dy > 0:
        # The pen is already rising to the right (c, e): carry that
        # motion on. Sagging first hung a hook off the terminal.
        lead = span * 0.35
        c1 = (start[0] + dx * lead, min(start[1] + dy * lead, max(start[1], JOIN_Y)))
        c2 = (end[0] - span * 0.35, max(start[1], JOIN_Y * 0.85))
    else:
        # Sag close to the baseline before hooking up late -- a rounder,
        # more pen-like swash than an even S-curve.
        c1 = (start[0] + span * 0.22, start[1] * 0.12)
        c2 = (end[0] - span * 0.30, JOIN_Y * 0.18)
    width = max(s["width"] for s in strokes) * TAIL_WIDTH_RATIO
    return {
        "pts": _cubic(start, c1, c2, end),
        "width": width,
        "closed": False,
        "tail": True,
    }


def _top_exit_tail(strokes: list[dict]) -> dict | None:
    """A short swash leaving the letter high: from the rightmost open
    endpoint near x-height (v/w's final upstroke), or -- for closed
    bowls like o -- the upper-right of the bowl, easing right and down
    to the top join height."""
    high = [
        p
        for s in strokes
        if not s["closed"] and len(s["pts"]) >= 2
        for p in (s["pts"][0], s["pts"][-1])
        if p[1] >= X_HEIGHT * 0.8
    ]
    if high:
        start = max(high, key=lambda p: p[0])
    else:
        start = max(
            (p for s in strokes for p in s["pts"]),
            key=lambda p: p[0] + 0.6 * p[1],
        )
    x_max = max(x for s in strokes for x, _ in s["pts"])
    end = (x_max + REACH * 0.75, TOP_JOIN_Y)
    span = end[0] - start[0]
    if span <= 0:
        return None
    c1 = (start[0] + span * 0.45, start[1] + 12)
    c2 = (end[0] - span * 0.3, end[1] + 30)
    width = max(s["width"] for s in strokes) * TAIL_WIDTH_RATIO
    return {
        "pts": _cubic(start, c1, c2, end),
        "width": width,
        "closed": False,
        "tail": True,
    }


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


def script_strokes(name: str, fn, bow: bool = False) -> list[dict]:
    """The script variant's pen strokes for one glyph: recorded skeleton,
    plus cursive loops and exit tail for lowercase (the tail stroke is
    flagged "tail"), then slanted. `bow=True` (the hand face) first
    gives every long straight stroke a soft bow.
    """
    with record_strokes() as strokes:
        fn()
    if name in LOWERCASE:
        strokes = _add_loops(name, strokes)
        # Tail before bowing: the exit point must come from the authored
        # geometry -- a bowed stem gains interior points that would
        # otherwise masquerade as exit candidates (j grew a bogus tail).
        if name not in NO_TAIL:
            if name in TOP_EXIT:
                tail = _top_exit_tail(strokes)
            else:
                strokes = _ground_stem(strokes)
                tail = _exit_tail(strokes)
            if tail is not None:
                strokes = strokes + [tail]
    if bow:
        strokes = _naturalize(name, strokes)
    return _slant(strokes)


def body_bounds(strokes: list[dict]) -> tuple[float, float] | None:
    """The horizontal extent of a glyph's ink WITHOUT its exit tail: the
    box its side bearings are measured from, so the tail is free to
    overshoot the advance and land on the next letter. None when every
    stroke is a tail (never, in practice) or there are no strokes."""
    body = [s for s in strokes if not s.get("tail")]
    if not body:
        return None
    x_min = min(x - s["width"] / 2 for s in body for x, _ in s["pts"])
    x_max = max(x + s["width"] / 2 for s in body for x, _ in s["pts"])
    return x_min, x_max


def _build(name: str, fn):
    def build():
        strokes = script_strokes(name, fn)
        shapes = [
            stroke_union([s["pts"]], s["width"], closed=s["closed"]) for s in strokes
        ]
        _, advance, _terminals = fn()
        return finalize(shapes), advance

    return build


def spacing_bounds(skeletons: dict) -> dict[str, tuple[float, float]]:
    """name -> (x_min, x_max) of the tail-less ink for every glyph, to
    hand to normalize_spacing so tails reach into the next letter."""
    bounds = {}
    for name, fn in skeletons.items():
        b = body_bounds(script_strokes(name, fn))
        if b is not None:
            bounds[name] = b
    return bounds


def make_glyphs(skeletons: dict) -> dict:
    """name -> () -> (contours, advance) for the script face -- the same
    contract GLYPHS exposes for the sans.
    """
    return {name: _build(name, fn) for name, fn in skeletons.items()}
