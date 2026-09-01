"""Serif variant of the glyph set: the shared skeletons, re-stroked with a
contrast pen and finished with feet.

Every letter's shape and every terminal that should grow a foot are still
declared once, in fontgen.glyphs.SKELETONS (see that module's docstring for
why terminals live there instead of being re-derived here). This module
does not touch that geometry; it changes how the geometry is INKED:

Instead of taking the skeletons' circular-pen shapes as-is, each glyph is
rebuilt from its recorded stroke centerlines (fontgen.primitives.
record_strokes -- the same replay mechanism the script/hand faces use) and
swept with an axis-aligned ELLIPTICAL pen, PEN_THICK wide by PEN_THIN
tall. That one substitution is what turns the monoline sans into a text
serif: vertical stems come out thick, horizontal bars and curve tops/
bottoms thin, and every diagonal and bowl modulates smoothly in between,
with vertical stress -- the newsprint "legibility group" model.

The sweep is computed as an exact Minkowski sum via an affine trick:
scale the centerline by (1/a, 1/b), buffer with a UNIT CIRCLE, scale
back. A circular buffer in the squashed space is exactly the elliptical
pen in glyph space, so joins and caps come out as the pen would draw
them, and GEOS only ever sees its best-tested operation (round buffer of
a polyline). Because PEN_THIN equals the skeletons' circular STROKE, all
vertical metrics the skeletons were tuned against are untouched -- the
pen only ever widens things sideways.

Two optical corrections ride along, both things a circular pen hid:

- Closed rings (O, o, 0, 6, 8, 9, Q, a's bowl) are grown vertically by
  RING_OVERSHOOT. Seriffed stems visually sit CAP_BULGE_V below the
  nominal baseline (their feet swallow the pen cap there), so a ring
  tangent to the nominal guidelines floats above the seriffed line;
  round shapes must overshoot past it, not hover inside it.
- Dot marks (i/j tittles, period, colon, exclam, question) are drawn as
  true circles sized to the new stem weight -- the skeletons' square
  dots read as foreign next to contrast strokes -- and dots that sit on
  the baseline are dropped to the same optical line the serif feet
  define.
- Free CURVE ends grow ball terminals, the legibility group's signature
  finish (Century's c/r/f bulbs). A candidate is found structurally, not
  by name: an open recorded stroke with enough points to be a curve
  (straight chains never qualify), whose endpoint neither carries a
  declared serif terminal (those get feet) nor lies buried in another
  stroke's ink (bowl/arch ends flush against stems stay plain).
"""

import math

from shapely import affinity
from shapely.geometry import LinearRing, LineString, Point

from fontgen.glyphs import CMAP, SKELETONS
from fontgen.metrics import BASE, STROKE
from fontgen.primitives import finalize, record_strokes, union_all
from fontgen.serifs import PEN_THICK, PEN_THIN, serif_foot

#: Extra vertical radius for closed rings, chosen so a capital ring's
#: bottom edge lands ~10 units below the seriffed baseline (which sits
#: CAP_BULGE_V below nominal): today's capital ring already overshoots
#: nominal by 14, so 14 + grow = CAP_BULGE_V + 10.
RING_OVERSHOOT = 35.0

#: Dot radius: diameter ~= PEN_THICK, so a tittle reads as a full stop of
#: the stem's own weight rather than a fleck.
DOT_R = 52.0

#: A recorded stroke this short is a dot mark, not a stroke.
DOT_LEN = 2.0

#: Baseline dots sink this far below nominal, to sit on the optical line
#: the serif feet define (feet reach CAP_BULGE_V below; round shapes stop
#: slightly short of round-letter overshoot, like the rings do).
DOT_SINK = 30.0

#: Ball-terminal radius (scaled by each stroke's recorded width, like the
#: pen): diameter just past PEN_THICK, so the bulb reads as a deliberate
#: full stop on the thin curve end without outweighing the stems.
BALL_R = 55.0

#: An open recorded stroke with at least this many points is a curve
#: (arcs/spines are densely sampled; straight chains carry 2-5 points).
CURVE_MIN_PTS = 8


def _pen_stroke(stroke):
    """Sweep one recorded centerline with the elliptical pen."""
    pts, width, closed = stroke["pts"], stroke["width"], stroke["closed"]
    k = width / STROKE
    a, b = (PEN_THICK / 2) * k, (PEN_THIN / 2) * k

    if closed:
        line = LinearRing(pts)
        ys = [y for _, y in pts]
        rv = (max(ys) - min(ys)) / 2
        if rv > 1:
            line = affinity.scale(
                line,
                xfact=1.0,
                yfact=(rv + RING_OVERSHOOT) / rv,
                origin=(0.0, (max(ys) + min(ys)) / 2),
            )
    else:
        line = LineString(pts)
        if line.length < DOT_LEN:
            (x0, y0), (x1, y1) = pts[0], pts[-1]
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            if cy - width / 2 <= BASE + 1:
                cy = BASE - DOT_SINK + DOT_R
            return Point(cx, cy).buffer(DOT_R, quad_segs=24)

    squashed = affinity.scale(line, xfact=1.0 / a, yfact=1.0 / b, origin=(0.0, 0.0))
    swept = squashed.buffer(1.0, quad_segs=24)
    return affinity.scale(swept, xfact=a, yfact=b, origin=(0.0, 0.0))


def _ball_terminals(strokes, inked, terminals):
    """Ball terminals for every free curve end (see module docstring)."""
    term_pts = [p for p, _ in terminals]
    balls = []
    for i, s in enumerate(strokes):
        if s["closed"] or len(s["pts"]) < CURVE_MIN_PTS:
            continue
        others = union_all([shape for j, shape in enumerate(inked) if j != i])
        for ex, ey in (s["pts"][0], s["pts"][-1]):
            if any(math.hypot(ex - tx, ey - ty) < 2 for tx, ty in term_pts):
                continue
            if not others.is_empty and others.covers(Point(ex, ey)):
                continue
            k = s["width"] / STROKE
            balls.append(Point(ex, ey).buffer(BALL_R * k, quad_segs=24))
    return balls


def _serif(fn):
    def build():
        with record_strokes() as strokes:
            _shapes, advance, terminals = fn()
        inked = [_pen_stroke(s) for s in strokes]
        balls = _ball_terminals(strokes, inked, terminals)
        feet = [serif_foot(point, toward) for point, toward in terminals]
        return finalize([*inked, *balls, *feet]), advance

    return build


GLYPHS = {name: _serif(fn) for name, fn in SKELETONS.items()}

__all__ = ["CMAP", "GLYPHS"]
