"""Aperture Olde: a blackletter (textura quadrata / "Olde English")
face generated from the same glyph skeletons as the sans.

Where the moderne face models a pointed pen (width from pressure, so
vertical strokes swell and horizontals vanish), this models the BROAD
NIB that wrote medieval textura: a flat pen held at a constant
NIB_DEG angle. Every recorded centerline is SWEPT with that nib -- the
Minkowski sum of the path and a thin rectangle, built as the union of
the convex hulls of the nib at each pair of consecutive path points --
so a stroke's width is set purely by how much of the nib's edge it
drags: full width perpendicular to the nib, a hairline (the nib's own
thickness) along it, and every angle in between modulating
continuously along a curve. That one rule gives thick verticals AND
substantial horizontals, with the up-right diagonals (A's left leg,
V's right, the rising strokes of x and W) collapsing to hairlines
exactly where a scribe's pen would, and the nib's angled edge showing
at every stroke end.

Two blackletter conventions layered on the nib model:

- **Verticalized diagonals.** Textura draws a long diagonal as a heavy
  vertical run plus a short connector -- the picket-fence texture comes
  from everything snapping to vertical. Long authored diagonals are
  broken that way, anchored at their free end so feet and heads stay
  where the letter needs them.
- **Diamond nib-marks.** Every declared terminal gets a nib-angled
  rhombus whose tip pokes a touch past the line it sits on, and
  free-hanging thin curve ends (c's mouth, g's tail, 3's spine) get a
  smaller one. The dots of i, j, !, ? and the period become diamonds
  outright, and the comma is a diamond with a hairline tail.

Curves are swept smooth, not fractured into facets, and nothing is
randomized: the face is typeset, every letter the same drawing every
time, and its baseline is the flats' ink like every other face's.
"""

import itertools
import math

from shapely import geometry as sg
from shapely.ops import unary_union

from fontgen.metrics import STROKE
from fontgen.primitives import Point, polygon_to_contours, record_strokes, union_all

# The broad nib: held at NIB_DEG from horizontal. MAIN is the width of a
# vertical stem, HAIR the nib's own thickness (the width of a stroke
# dragged along the nib's angle). The nib's edge length follows from
# the two, so a vertical comes out exactly MAIN wide.
NIB_DEG = 35.0
MAIN = 148.0
HAIR = 24.0
_NIB = math.radians(NIB_DEG)
NIB_LEN = (MAIN - HAIR * math.sin(_NIB)) / math.cos(_NIB)

# Textura draws long diagonals as a heavy VERTICAL run plus a short
# connector. Straight authored diagonals in this angle band (from
# horizontal) and at least this long get broken that way, anchored at
# their terminal (free) end so feet and heads stay where the letter
# needs them.
VERT_BAND = (40.0, 78.0)
VERT_MIN_LEN = 180.0
VERT_FRAC = 0.72
# Letters whose crossing or lone diagonal IS the letter: verticalizing
# X's strokes turns it into a broken gate, Z into a C-ish zigzag, 4
# into a sideways A, M into an H, 7 into a T. They keep true diagonals
# (the nib still thins the up-right ones).
VERT_SKIP = {"X", "x", "Z", "z", "four", "M", "seven"}

# 6/9's shallow neck and 1's flag run close to the nib angle and would
# all but vanish; they're main strokes, so a round pen of this width
# is laid under the nib sweep to keep them at least this wide.
CHAIN_MIN_WIDTH = {"six": 62.0, "nine": 62.0, "one": 62.0}

# Nib-mark diamonds: sized relative to MAIN at stroke terminals,
# smaller at free-hanging curve ends, poking POKE units past the
# terminal so feet and heads bite past their guide lines. They must be
# wider than the stem they cap or they disappear into it.
DIAMOND_SIZE = 1.45
END_DIAMOND_SIZE = 1.0
DIAMOND_POKE = 22.0
END_MAX_W = 70.0
END_MERGE_DIST = 80.0

DOT_MAX_LEN = 12.0
CURVE_MIN_PTS = 8


def _nib_width(dx: float, dy: float) -> float:
    """Width of the nib sweep across a stroke moving in direction
    (dx, dy): the nib edge's projection across it plus the nib
    thickness's projection along it -- exactly MAIN for a vertical, the
    thickness alone along the nib angle."""
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return HAIR
    ux, uy = dx / length, dy / length
    nx, ny = math.cos(_NIB), math.sin(_NIB)
    across = abs(nx * uy - ny * ux)
    along = abs(nx * ux + ny * uy)
    return NIB_LEN * across + HAIR * along


def _nib_corners(scale: float) -> list[Point]:
    """The nib rectangle (length NIB_LEN, thickness HAIR, both scaled)
    centered on the origin."""
    hl, ht = NIB_LEN * scale / 2, HAIR * scale / 2
    ux, uy = math.cos(_NIB), math.sin(_NIB)
    vx, vy = -uy, ux
    return [
        (ux * hl + vx * ht, uy * hl + vy * ht),
        (ux * hl - vx * ht, uy * hl - vy * ht),
        (-ux * hl - vx * ht, -uy * hl - vy * ht),
        (-ux * hl + vx * ht, -uy * hl + vy * ht),
    ]


def _end_clip(p: Point, q: Point, scale: float) -> sg.Polygon:
    """The half-plane behind stroke end `p` (the side toward `q`): the
    nib overhangs its endpoint by up to its own reach, so a straight
    stroke's sweep is clipped square at each end. A stem's foot then
    sits flat on the guideline it was drawn to, and a bar ends where it
    was authored, as in every other face; the diamond nib-marks supply
    the textura ends. Curves keep the nib's angled edge at their free
    ends (c's mouth, e's tail): a half-plane through a curve's end
    would cut through the rest of the letter."""
    dx, dy = p[0] - q[0], p[1] - q[1]
    length = math.hypot(dx, dy)
    ux, uy = (dx / length, dy / length) if length > 1e-9 else (1.0, 0.0)
    reach = 4 * NIB_LEN * scale
    far = 1e5
    # Corners of a rectangle spanning `far` behind p and `far` to each side.
    vx, vy = -uy, ux
    return sg.Polygon(
        [
            (p[0] + vx * far, p[1] + vy * far),
            (p[0] - vx * far, p[1] - vy * far),
            (
                p[0] - vx * far - ux * reach - ux * far,
                p[1] - vy * far - uy * reach - uy * far,
            ),
            (
                p[0] + vx * far - ux * reach - ux * far,
                p[1] + vy * far - uy * reach - uy * far,
            ),
        ]
    )


def _nib_sweep(pts: list[Point], closed: bool, scale: float, clip: bool = False):
    """Sweep the nib along a path: the union, over consecutive point
    pairs, of the convex hull of the nib placed at both points. `clip`
    squares off both ends of an open path at its endpoints."""
    corners = _nib_corners(scale)
    pairs = list(itertools.pairwise(pts))
    if closed and len(pts) > 2:
        pairs.append((pts[-1], pts[0]))
    hulls = []
    for (x0, y0), (x1, y1) in pairs:
        hulls.append(
            sg.MultiPoint(
                [(x0 + cx, y0 + cy) for cx, cy in corners]
                + [(x1 + cx, y1 + cy) for cx, cy in corners]
            ).convex_hull
        )
    if not hulls:
        return sg.Polygon()
    swept = unary_union(hulls).buffer(0)
    if clip and not closed:
        swept = swept.intersection(_end_clip(pts[0], pts[1], scale))
        swept = swept.intersection(_end_clip(pts[-1], pts[-2], scale))
    return swept


def _verticalize(name: str, pts: list[Point], terminals) -> list[Point]:
    """Break each long straight diagonal of an authored chain into a
    vertical run plus a connector, textura-style. The vertical run sits
    at the segment's terminal (free) end -- A's verticals rise from its
    feet, V's hang from its arms -- falling back to the upper end for
    interior joints. Endpoints never move, so joins stay seamless; the
    nib model then makes each vertical run full weight and each
    down-left connector a hairline on its own."""
    if name in VERT_SKIP or len(pts) > 6 or len(pts) < 2:
        return pts
    term_pts = [p for p, _ in terminals]

    def is_terminal(p: Point) -> bool:
        return any(math.dist(p, t) < 5 for t in term_pts)

    out = [pts[0]]
    for (x0, y0), (x1, y1) in itertools.pairwise(pts):
        dx, dy = x1 - x0, y1 - y0
        length = math.hypot(dx, dy)
        angle = abs(math.degrees(math.atan2(dy, dx)))
        angle = 180 - angle if angle > 90 else angle
        if length >= VERT_MIN_LEN and VERT_BAND[0] <= angle <= VERT_BAND[1]:
            t0, t1 = is_terminal((x0, y0)), is_terminal((x1, y1))
            if t0 == t1:  # both or neither: feet win, else the upper end
                anchor_p0 = (y0 < y1) if t0 else (y0 > y1)
            else:
                anchor_p0 = t0
            if anchor_p0:
                # vertical run leaves p0; connector arrives at p1
                out.append((x0, y0 + VERT_FRAC * dy))
            else:
                # connector leaves p0; vertical run arrives at p1
                out.append((x1, y1 - VERT_FRAC * dy))
        out.append((x1, y1))
    return out


def _diamond(center: Point, size: float) -> sg.Polygon:
    """The mark a lifted broad nib leaves: a rhombus with its long axis
    along the nib angle."""
    ux, uy = math.cos(_NIB) * size * 0.62, math.sin(_NIB) * size * 0.62
    vx, vy = -math.sin(_NIB) * size * 0.42, math.cos(_NIB) * size * 0.42
    cx, cy = center
    return sg.Polygon(
        [(cx + ux, cy + uy), (cx + vx, cy + vy), (cx - ux, cy - uy), (cx - vx, cy - vy)]
    )


def _place_diamond(p: Point, outward: Point, size: float) -> sg.Polygon:
    """A diamond at a stroke end, pulled inward so its farthest tip
    pokes exactly DIAMOND_POKE units past the terminal along `outward`."""
    shape = _diamond((0.0, 0.0), size)
    ext = max(x * outward[0] + y * outward[1] for x, y in shape.exterior.coords)
    cx = p[0] + outward[0] * (DIAMOND_POKE - ext)
    cy = p[1] + outward[1] * (DIAMOND_POKE - ext)
    return _diamond((cx, cy), size)


def _outward(p: Point, q: Point) -> Point | None:
    dx, dy = p[0] - q[0], p[1] - q[1]
    length = math.hypot(dx, dy)
    if length < 1e-6:
        return None
    return (dx / length, dy / length)


def _terminal_diamonds(terminals) -> list[sg.Polygon]:
    shapes = []
    for p, toward in terminals:
        out = _outward(p, toward)
        if out is None:
            continue
        shapes.append(_place_diamond(p, out, MAIN * DIAMOND_SIZE))
    return shapes


def _end_diamonds(prepared, ink, terminals) -> list[sg.Polygon]:
    """Small nib-marks on free-hanging thin curve ends -- the blackletter
    counterpart of the didone's ball terminals, same free-end probe."""
    term_pts = [p for p, _ in terminals]
    ends = []
    for _, pts, closed, is_curve, scale in prepared:
        if closed or not is_curve:
            continue
        for end in (0, -1):
            p = pts[end]
            q = pts[1] if end == 0 else pts[-2]
            w = _nib_width(p[0] - q[0], p[1] - q[1]) * scale
            if w > END_MAX_W:
                continue
            if any(math.dist(p, t) < 40 for t in term_pts):
                continue
            out = _outward(p, q)
            if out is None:
                continue
            probe = (p[0] + out[0] * (w / 2 + 16), p[1] + out[1] * (w / 2 + 16))
            if ink.intersects(sg.Point(probe).buffer(5)):
                continue
            ends.append((p, out))
    merged: list[tuple[Point, Point]] = []
    for p, out in ends:
        for i, (mp, _) in enumerate(merged):
            if math.dist(p, mp) < END_MERGE_DIST:
                merged[i] = (((p[0] + mp[0]) / 2, (p[1] + mp[1]) / 2), out)
                break
        else:
            merged.append((p, out))
    return [_place_diamond(p, out, MAIN * END_DIAMOND_SIZE) for p, out in merged]


def _prepare(name: str, stroke: dict, terminals):
    """One recorded stroke -> ("dot", diamond) or ("stroke", (shape,
    pts, closed, is_curve, scale)) after verticalizing, trimming and
    the nib sweep."""
    pts = [tuple(p) for p in stroke["pts"]]
    closed = stroke["closed"]
    if closed and len(pts) > 1 and math.dist(pts[0], pts[-1]) < 1e-6:
        pts = pts[:-1]
    if (
        len(pts) < 2
        or sum(math.dist(a, b) for a, b in itertools.pairwise(pts)) < DOT_MAX_LEN
    ):
        return "dot", _diamond(pts[0], stroke["width"] * 1.15)
    is_curve = len(pts) >= CURVE_MIN_PTS
    if not is_curve and not closed:
        pts = _verticalize(name, pts, terminals)
    scale = min(max(stroke["width"] / STROKE, 0.6), 1.5)
    swept = _nib_sweep(pts, closed, scale, clip=not is_curve)
    floor = CHAIN_MIN_WIDTH.get(name)
    if floor and not is_curve:
        line = sg.LinearRing(pts) if closed else sg.LineString(pts)
        swept = unary_union([swept, line.buffer(floor / 2, quad_segs=8)])
    return "stroke", (swept, pts, closed, is_curve, scale)


def _comma_shapes() -> list:
    """A nib-mark with a hairline tail flicking down-left."""
    head = _diamond((250.0, 45.0), 110.0)
    tail_pts = [(262.0, 20.0), (238.0, -50.0), (200.0, -115.0)]
    return [head, _nib_sweep(tail_pts, False, 0.45)]


def _f_strokes_bl():
    """Textura f: the sans' 180-unit crossbar disappears inside a
    148-wide stem, and its hook comes out as a hairline stub. Redrawn
    with a long bar and a slimmer, clearly angled flag riding off the
    stem top."""
    return [
        {"pts": [(170.0, 0.0), (170.0, 700.0)], "width": STROKE, "closed": False},
        {"pts": [(40.0, 480.0), (315.0, 480.0)], "width": STROKE, "closed": False},
        {
            "pts": [(172.0, 662.0), (395.0, 610.0)],
            "width": STROKE * 0.55,
            "closed": False,
        },
    ]


def _t_strokes_bl():
    """Textura t: same crossbar problem as f -- the sans bar barely
    clears the fat stem, so it reads as two nubs. Long bar instead."""
    return [
        {"pts": [(170.0, 0.0), (170.0, 600.0)], "width": STROKE, "closed": False},
        {"pts": [(40.0, 480.0), (315.0, 480.0)], "width": STROKE, "closed": False},
    ]


OVERRIDES = {"f": _f_strokes_bl, "t": _t_strokes_bl}


def blackletter_shapes(name: str, fn) -> tuple[list, float]:
    """All Shapely shapes for one glyph (strokes, dots, diamonds) plus
    its advance width."""
    with record_strokes() as strokes:
        _, advance, terminals = fn()
    if name == "comma":
        return _comma_shapes(), advance
    if name in OVERRIDES:
        strokes = OVERRIDES[name]()
    dots, prepared = [], []
    for s in strokes:
        kind, payload = _prepare(name, s, terminals)
        if kind == "dot":
            dots.append(payload)
        else:
            prepared.append(payload)
    stroke_shapes = [p[0] for p in prepared]
    ink = unary_union(stroke_shapes + dots) if (stroke_shapes or dots) else sg.Polygon()
    diamonds = _terminal_diamonds(terminals)
    diamonds += _end_diamonds(prepared, ink, terminals)
    return stroke_shapes + dots + diamonds, advance


def _build(name: str, fn):
    def build():
        shapes, advance = blackletter_shapes(name, fn)
        return polygon_to_contours(union_all(shapes)), advance

    return build


def make_glyphs(skeletons: dict) -> dict:
    """name -> () -> (contours, advance) for the blackletter face -- the
    same contract GLYPHS exposes for the sans."""
    return {name: _build(name, fn) for name, fn in skeletons.items()}
