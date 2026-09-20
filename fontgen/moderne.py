"""Aperture Moderne: a high-contrast Didone-style display face generated
from the same glyph skeletons as the sans.

Like the script face, this replays each glyph function under
primitives.record_strokes() to get its centerline pen strokes, then
re-renders them -- but instead of a uniform buffer, every stroke is
rebuilt with an angle-dependent width (the pointed-pen "expansion"
look): vertical movement gets the full MAIN weight, horizontal movement
collapses to a HAIRline, with |sin(angle)|^CONTRAST_POW easing between
them. That one rule turns O into a vertically-stressed didone O (thick
sides, hairline top/bottom), makes crossbars and arms hairlines, and
leaves stems at full display weight.

A sampled curve is outlined as ONE smooth shape
(primitives.varwidth_outline): the width is evaluated at every vertex
and the two edges are offset from the centerline along the local
normal, so the weight swells and thins continuously around a bowl with
no facets. Straight authored chains are stroked segment by
segment with mitered joints, the crisp corners a didone wants.

Three typographic conventions the pure angle rule can't express are
layered on top:

- **Down-left diagonals go thin.** In every didone, A's left leg, V's
  right leg, X's rising stroke, W's inner strokes are hairline-thin
  while their down-right partners are thick -- a relic of how a flexible
  pen is pulled. Straight authored segments (short point-lists, not
  sampled curves) whose canonical downward direction points left are
  demoted to THIN_W. Glyphs whose identity *lives* in a thick down-left
  stroke (Z, z, 7) are exempted.
- **Ball terminals.** Free-hanging stroke ends that have gone thin
  (f's hook, g's tail, c/e's aperture ends, 3's spine) get the didone
  ball: a disc planted just past the hairline's end. "Free" is decided
  geometrically -- a probe point just beyond the end must land on empty
  ink -- so bowl ends that die into a stem never sprout one.
- **Unbracketed hairline serifs.** The skeletons already declare every
  terminal that deserves a foot (shared with the serif face); here each
  becomes a flat slab -- horizontal under stems and diagonals, a small
  vertical beak on arm ends -- with no fillet, per the style.

Because the hairlines are so much thinner than the STROKE the skeletons
were authored against, curved strokes are pre-stretched vertically about
their own center so their outer edge still reaches the overshoot line
the original round cap reached; without this, O renders 26 units
shorter than H and every arch sits visibly low.

Nothing is randomized and nothing is bowed or softened: the face is
typeset, every letter the same drawing every time, sitting on the same
baseline as every other face.
"""

import itertools
import math

from shapely import geometry as sg
from shapely.ops import unary_union

from fontgen.metrics import STROKE
from fontgen.primitives import (
    Point,
    arc_pts,
    polygon_to_contours,
    record_strokes,
    union_all,
    varwidth_outline,
)

# The weight axis: full stems vs hairlines, and the easing power between
# them (higher power holds strokes thin longer, snapping to thick only
# near vertical -- the crisp didone look).
MAIN = 112.0
HAIR = 26.0
CONTRAST_POW = 1.6

# Demoted strokes (down-left diagonals, N/M's hairline stems) get this
# fixed width: a touch over HAIR so they read as drawn, not as cracks.
THIN_W = 30.0

# Curved strokes are scaled vertically about their own center so the new
# hairline edge reaches where the old round cap (STROKE/2 beyond the
# centerline) used to reach.
STRETCH = (STROKE - HAIR) / 2

# Glyphs whose down-left diagonal is the main stroke and must stay thick.
DOWNLEFT_THICK = {"Z", "z", "seven", "one", "two", "comma"}

# Didone N and M carry their weight in the diagonals; their vertical
# stems are traditionally hairlines with full serifs.
VERTICAL_THIN = {"N", "M"}

# Floors for straight-chain strokes only (sampled curves keep the pure
# contrast model): a hairline hyphen vanishes at text sizes, and 6/9's
# shallow neck is a main stroke, not a crossbar.
CHAIN_MIN_WIDTH = {
    "hyphen": 58.0,
    "six": 72.0,
    "nine": 72.0,
    # f/t crossbars and G's bar are load-bearing at small sizes; didones
    # keep them slab-weight, unlike A/H/e's true hairline crossbars.
    "f": 48.0,
    "t": 48.0,
    "G": 60.0,
}

# 6/9's neck terminal was declared for the serif face's flare; a flat
# didone slab floating on a curve's end just reads as debris.
SERIF_SKIP = {"six", "nine"}

# Bare stroke tops that end mid-air (t's stem, !'s taper point) read as
# lollipops with a slab floating on them; these keep only their feet.
TOP_SERIF_SKIP = {"t", "exclam"}

# Glyphs whose free curve ends get a ball even where the stroke is
# still thick (didone r, j and f's flag traditionally end in a full ball).
BALL_FORCE = {"r", "j", "J", "f"}

# A straight segment counts as a demotable diagonal when its angle from
# horizontal falls in this band (outside it, it's an arm or a stem).
DIAG_BAND = (18.0, 80.0)
DIAG_MIN_LEN = 60.0
# Only authored straight chains are demoted -- sampled curves have many
# points and take the smooth |sin| contrast instead.
STRAIGHT_MAX_PTS = 6

CURVE_MIN_PTS = 8
# Only tall curves (full bowls, rings, S-spines) get the overshoot
# stretch: on a shallow hook the fixed 26-unit compensation becomes a
# 30% blow-up that tears the hook off its stem (f's hook did exactly
# that), and small arcs never had meaningful cap overshoot to restore.
STRETCH_MIN_EXTENT = 320.0

BALL_R = 50.0
BALL_MAX_W = 62.0
BALL_MERGE_DIST = 95.0
BALL_ADVANCE = 0.25  # how far past the stroke end the ball's center sits, in radii

SERIF_T = 28.0
SERIF_HW = 92.0
ARM_T = 30.0
ARM_HH = 55.0
AXIS_TOL_DEG = 8.0

# Anything this short is a dot (i/j dots, period, colon), rendered as a
# plain disc -- the angle model would flatten it into a hairline sliver.
DOT_MAX_LEN = 12.0

# A smooth outline's corner (where two consecutive sampled segments
# meet) is mitered; the miter is capped at this multiple of the half
# width so a kink can't throw a spike.
MITER_CAP = 2.0


def _fold_angle(dx: float, dy: float) -> float:
    """Angle from horizontal folded into [0, 90] (direction-agnostic)."""
    a = abs(math.degrees(math.atan2(dy, dx)))
    return 180 - a if a > 90 else a


def _seg_widths(name: str, pts: list[Point], closed: bool, scale: float) -> list[float]:
    """One width per segment of the polyline (wrapping if closed)."""
    pairs = list(itertools.pairwise(pts))
    if closed:
        pairs.append((pts[-1], pts[0]))
    widths = []
    for (x0, y0), (x1, y1) in pairs:
        dx, dy = x1 - x0, y1 - y0
        length = math.hypot(dx, dy)
        angle = _fold_angle(dx, dy)
        f = abs(math.sin(math.radians(angle))) ** CONTRAST_POW
        w = HAIR + (MAIN - HAIR) * f
        straight = not closed and len(pts) <= STRAIGHT_MAX_PTS
        demoted_diagonal = (
            name not in DOWNLEFT_THICK
            and length > DIAG_MIN_LEN
            and DIAG_BAND[0] <= angle <= DIAG_BAND[1]
            and dx * dy > 0
        )
        hairline_stem = name in VERTICAL_THIN and angle > DIAG_BAND[1] and length > 100
        if straight and (demoted_diagonal or hairline_stem):
            w = THIN_W
        w *= scale
        if straight:
            w = max(w, CHAIN_MIN_WIDTH.get(name, 0.0))
        widths.append(w)
    return widths


def _varwidth_shape(pts: list[Point], widths: list[float], closed: bool):
    """Stroke a straight chain with per-segment widths: one quad per
    segment, plus a convex-hull filler over each joint so corners come
    out as clean near-miters instead of the round bulges a disc join
    would add (a disc at V's apex would dip half a stem-width past the
    baseline).
    """
    quads, ends = [], []
    n = len(pts)
    seg_indices = list(range(n - 1)) + ([n - 1] if closed else [])
    for k, i in enumerate(seg_indices):
        (x0, y0), (x1, y1) = pts[i], pts[(i + 1) % n]
        dx, dy = x1 - x0, y1 - y0
        length = math.hypot(dx, dy)
        if length < 1e-6:
            ends.append(None)
            continue
        nx, ny = -dy / length, dx / length
        h = widths[k] / 2
        quads.append(
            sg.Polygon(
                [
                    (x0 + nx * h, y0 + ny * h),
                    (x1 + nx * h, y1 + ny * h),
                    (x1 - nx * h, y1 - ny * h),
                    (x0 - nx * h, y0 - ny * h),
                ]
            )
        )
        ends.append((nx, ny, h))
    # Joint fillers: at each interior vertex (every vertex, if closed),
    # the hull of the two adjoining quads' corner points.
    m = len(seg_indices)
    joints = range(m) if closed else range(1, m)
    for k in joints:
        a, b = ends[k - 1], ends[k % m]
        if a is None or b is None:
            continue
        vx, vy = pts[k % n]
        (nax, nay, ha), (nbx, nby, hb) = a, b
        hull = sg.MultiPoint(
            [
                (vx + nax * ha, vy + nay * ha),
                (vx - nax * ha, vy - nay * ha),
                (vx + nbx * hb, vy + nby * hb),
                (vx - nbx * hb, vy - nby * hb),
            ]
        ).convex_hull
        if hull.geom_type == "Polygon":
            quads.append(hull)
    if not quads:
        return sg.Polygon()
    return unary_union(quads).buffer(0)


def _path_length(pts: list[Point]) -> float:
    return sum(math.dist(a, b) for a, b in itertools.pairwise(pts))


def _y_stretch(pts: list[Point], closed: bool) -> list[Point]:
    """Scale a curve vertically about its own center so its hairline
    extremes reach the overshoot the original STROKE-wide round edge
    reached."""
    ys = [y for _, y in pts]
    y_min, y_max = min(ys), max(ys)
    ry = (y_max - y_min) / 2
    if ry < STRETCH_MIN_EXTENT / 2:
        return pts
    if not closed:
        # A bulge bowl's endpoints ARE its vertical extremes (they sit
        # on the stem at top and bottom); stretching would push them
        # past the stem's ends, leaving pips above/below the letter.
        # Overshoot belongs only to curves whose extremes are interior.
        end_ys = {pts[0][1], pts[-1][1]}
        at_max = any(abs(y - y_max) < 15 for y in end_ys)
        at_min = any(abs(y - y_min) < 15 for y in end_ys)
        if at_max and at_min:
            return pts
    cy = (y_min + y_max) / 2
    factor = (ry + STRETCH) / ry
    return [(x, cy + (y - cy) * factor) for x, y in pts]


def _prepare(name: str, stroke: dict):
    """One recorded stroke -> ("dot", disc) or ("stroke", (shape, pts,
    widths, closed, is_curve)) after dedup, stretch and width assignment."""
    pts = [tuple(p) for p in stroke["pts"]]
    closed = stroke["closed"]
    if closed and len(pts) > 1 and math.dist(pts[0], pts[-1]) < 1e-6:
        pts = pts[:-1]
    if len(pts) < 2 or _path_length(pts) < DOT_MAX_LEN:
        r = stroke["width"] / 2
        return "dot", sg.Point(pts[0]).buffer(r, quad_segs=16)
    is_curve = len(pts) >= CURVE_MIN_PTS
    if is_curve:
        pts = _y_stretch(pts, closed)
    scale = min(max(stroke["width"] / STROKE, 0.6), 1.5)
    widths = _seg_widths(name, pts, closed, scale)
    shape = (
        varwidth_outline(pts, widths, closed, miter_cap=MITER_CAP)
        if is_curve
        else _varwidth_shape(pts, widths, closed)
    )
    return "stroke", (shape, pts, widths, closed, is_curve)


def _ball_shapes(name, prepared, ink, terminals):
    """Didone ball terminals on free-hanging thin stroke ends."""
    term_pts = [p for p, _ in terminals]
    centers = []
    for own_shape, pts, widths, closed, is_curve in prepared:
        if closed or not is_curve:
            continue
        for end in (0, -1):
            p = pts[end]
            q = pts[1] if end == 0 else pts[-2]
            w = widths[0] if end == 0 else widths[-1]
            if w > BALL_MAX_W and name not in BALL_FORCE:
                continue
            if any(math.dist(p, t) < 40 for t in term_pts):
                continue
            ox, oy = p[0] - q[0], p[1] - q[1]
            length = math.hypot(ox, oy)
            if length < 1e-6:
                continue
            ox, oy = ox / length, oy / length
            probe = (p[0] + ox * (w / 2 + 16), p[1] + oy * (w / 2 + 16))
            if ink.intersects(sg.Point(probe).buffer(5)):
                continue
            center = (
                p[0] + ox * BALL_R * BALL_ADVANCE,
                p[1] + oy * BALL_R * BALL_ADVANCE,
            )
            # A ball must land in clear space: if much of it would sit
            # on ink from OTHER strokes (g's hook end curls back under
            # its own bowl), the letter reads as a blob -- skip it.
            ball = sg.Point(center).buffer(BALL_R, quad_segs=16)
            overlap = ball.intersection(ink.difference(own_shape)).area
            if overlap > 0.35 * ball.area:
                continue
            centers.append(center)
    merged: list[tuple[float, float]] = []
    for c in centers:
        for i, m in enumerate(merged):
            if math.dist(c, m) < BALL_MERGE_DIST:
                merged[i] = ((c[0] + m[0]) / 2, (c[1] + m[1]) / 2)
                break
        else:
            merged.append(c)
    return [sg.Point(c).buffer(BALL_R, quad_segs=16) for c in merged]


def _serif_shapes(name, terminals):
    """Flat unbracketed slabs at every declared terminal: horizontal
    under vertical stems and diagonals (sitting exactly on the line the
    stroke ends at), small vertical beaks on horizontal arm ends."""
    shapes = []
    for (px, py), (tx, ty) in terminals:
        dx, dy = px - tx, py - ty
        angle = _fold_angle(dx, dy)
        if angle <= AXIS_TOL_DEG:  # horizontal arm -> vertical beak
            if dx > 0:
                shapes.append(sg.box(px - ARM_T, py - ARM_HH, px, py + ARM_HH))
            else:
                shapes.append(sg.box(px, py - ARM_HH, px + ARM_T, py + ARM_HH))
        elif dy < 0:  # stem or diagonal ending downward -> foot slab
            shapes.append(sg.box(px - SERIF_HW, py, px + SERIF_HW, py + SERIF_T))
        elif name not in TOP_SERIF_SKIP:  # ending upward -> head slab
            shapes.append(sg.box(px - SERIF_HW, py - SERIF_T, px + SERIF_HW, py))
    return shapes


def _comma_shapes():
    """The didone comma is not a stroked skeleton at all: a full ball
    with a hairline tail flicking down-left."""
    ball = sg.Point(255, 40).buffer(BALL_R, quad_segs=16)
    tail_pts = [(268.0, 20.0), (243.0, -50.0), (203.0, -118.0)]
    return [ball, _varwidth_shape(tail_pts, [54.0, 24.0], closed=False)]


def _f_strokes():
    """f's recorded hook curls over the apex and dies thin at the LEFT --
    backwards for a didone, whose f carries a hairline flag off to the
    right ending in a ball. Redrawn: same stem and crossbar, but the arc
    runs only from the apex (where the stem's own ink swallows that thin
    end, so no ball sprouts there) 60 degrees down the right side --
    stopping while its tangent is still shallow, so the flag stays a
    hairline and its forced ball hangs in the air above the crossbar
    instead of drooping into it like a P bowl."""
    return [
        {"pts": [(170.0, 0.0), (170.0, 700.0)], "width": STROKE, "closed": False},
        {"pts": [(80.0, 480.0), (260.0, 480.0)], "width": STROKE, "closed": False},
        {"pts": arc_pts(170, 560, 140, 30, 90), "width": STROKE, "closed": False},
    ]


STROKE_OVERRIDES = {"f": _f_strokes}


def moderne_shapes(name: str, fn) -> tuple[list, float]:
    """All Shapely shapes for one glyph (strokes, dots, balls, serifs)
    plus its advance width."""
    with record_strokes() as strokes:
        _, advance, terminals = fn()
    if name == "comma":
        return _comma_shapes(), advance
    if name in STROKE_OVERRIDES:
        strokes = STROKE_OVERRIDES[name]()
    dots, prepared = [], []
    for s in strokes:
        kind, payload = _prepare(name, s)
        if kind == "dot":
            dots.append(payload)
        else:
            prepared.append(payload)
    stroke_shapes = [p[0] for p in prepared]
    ink = unary_union(stroke_shapes + dots) if (stroke_shapes or dots) else sg.Polygon()
    balls = _ball_shapes(name, prepared, ink, terminals)
    serifs = _serif_shapes(name, terminals) if name not in SERIF_SKIP else []
    return stroke_shapes + dots + balls + serifs, advance


def _build(name: str, fn):
    def build():
        shapes, advance = moderne_shapes(name, fn)
        return polygon_to_contours(union_all(shapes).buffer(0)), advance

    return build


def make_glyphs(skeletons: dict) -> dict:
    """name -> () -> (contours, advance) for the moderne face -- the same
    contract GLYPHS exposes for the sans."""
    return {name: _build(name, fn) for name, fn in skeletons.items()}
