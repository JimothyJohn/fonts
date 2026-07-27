"""Aperture Olde: a blackletter (textura quadrata / "Olde English")
face generated from the same glyph skeletons as the sans.

Where the moderne face models a pointed pen (width from pressure, so
vertical strokes swell and horizontals vanish), this models the BROAD
NIB that wrote medieval textura: a flat pen held at a constant
NIB_DEG angle. A stroke's width is set by how much of the nib's edge
it drags -- full width perpendicular to the nib, a hairline parallel
to it. That one change gives thick verticals AND substantial
horizontals, with the up-right diagonals (A's left leg, V's right, the
rising strokes of x and W) collapsing to hairlines exactly where a
scribe's pen would.

Three blackletter conventions layered on the nib model:

- **Fracture.** Textura has no round bowls: curves break into short
  straight strokes. Every sampled curve is Douglas-Peucker simplified
  to a few segments before stroking, turning O into the angular
  hexagonal ring and n's arch into a broken shoulder. (This is also why
  no overshoot stretch is needed -- fractured letters are flat-topped.)
- **Diamond nib-marks.** Where the didone grew slab serifs and balls,
  the broad nib leaves a rhombus: every declared terminal gets a
  nib-angled diamond whose tip pokes a touch past the line it sits on,
  and free-hanging thin curve ends (c's mouth, g's tail, 3's spine) get
  a smaller one. The dots of i, j, !, ? and the period become diamonds
  outright, and the comma is a diamond with a hairline tail.
- **Density.** Blackletter is set dark and tight; the build script
  narrows the side bearings accordingly.

The humanizing layer is inherited in spirit from the moderne but
re-tuned: fractured segments must NOT be bowed back into curves, so
only the width breathes (each facet cut slightly its own weight, the
way no two pen strokes repeat), plus per-glyph weight and lean drift
and the same ink-soak corner softening. All variation is seeded
(zlib.crc32), so builds stay byte-identical.
"""

import itertools
import math

from shapely import affinity
from shapely import geometry as sg
from shapely.ops import unary_union

from fontgen.metrics import STROKE
from fontgen.moderne import (
    SOFTEN_R,
    STROKE_OVERRIDES,
    _path_length,
    _rand,
    _varwidth_shape,
)
from fontgen.primitives import Point, polygon_to_contours, record_strokes, union_all

# The broad nib: held at NIB_DEG from horizontal, its full edge MAIN
# units across, leaving a HAIR-thin line when dragged along its own
# angle. CONTRAST_POW shapes the falloff between the two.
NIB_DEG = 35.0
MAIN = 148.0
HAIR = 24.0
CONTRAST_POW = 1.4

# How far a curve may deviate from its fractured (straightened)
# replacement -- higher fractures into fewer, longer facets.
FRACTURE_TOL = 30.0
CURVE_MIN_PTS = 8

# Textura draws long diagonals as a heavy VERTICAL run plus a short
# connector -- the picket-fence texture comes from everything snapping
# to vertical. Straight authored diagonals in this angle band (from
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
# all but vanish; they're main strokes, so they keep at least this width.
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

# Humanizing (all crc32-seeded): per-facet width jitter, per-glyph
# weight and lean drift. No bows -- fracture IS the geometry.
FACET_VAR = 0.05
GLYPH_WEIGHT_VAR = 0.03
SLANT_VAR = 0.012


def _nib_width(dx: float, dy: float) -> float:
    """Broad-nib stroke width for a movement direction: the nib edge's
    projection across the stroke, normalized so a vertical stroke gets
    exactly MAIN (directions steeper than vertical clip at full width)."""
    phi = math.atan2(dy, dx)
    rel = phi - math.radians(NIB_DEG)
    f = min(abs(math.sin(rel)) / math.sin(math.radians(90.0 - NIB_DEG)), 1.0)
    return HAIR + (MAIN - HAIR) * f**CONTRAST_POW


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


def _fracture(pts: list[Point], closed: bool) -> list[Point]:
    """Break a sampled curve into blackletter facets. Straight chains
    (authored point lists) pass through untouched."""
    if len(pts) < CURVE_MIN_PTS:
        return pts
    if closed:
        ring = sg.LineString([*pts, pts[0]]).simplify(FRACTURE_TOL)
        out = [tuple(p) for p in ring.coords[:-1]]
        return out if len(out) >= 3 else pts
    line = sg.LineString(pts).simplify(FRACTURE_TOL)
    return [tuple(p) for p in line.coords]


def _seg_widths(name: str, si: int, pts: list[Point], closed: bool, scale: float):
    """Per-segment nib widths, with the seeded per-facet jitter."""
    pairs = list(zip(pts, pts[1:] + ([pts[0]] if closed else [])))
    widths = []
    for k, ((x0, y0), (x1, y1)) in enumerate(pairs):
        w = _nib_width(x1 - x0, y1 - y0) * scale
        w = max(w, CHAIN_MIN_WIDTH.get(name, 0.0))
        w *= 1 + _rand(f"{name}:{si}:{k}:facet", -FACET_VAR, FACET_VAR)
        widths.append(w)
    return widths


def _diamond(center: Point, size: float) -> sg.Polygon:
    """The mark a lifted broad nib leaves: a rhombus with its long axis
    along the nib angle."""
    nib = math.radians(NIB_DEG)
    ux, uy = math.cos(nib) * size * 0.62, math.sin(nib) * size * 0.62
    vx, vy = -math.sin(nib) * size * 0.42, math.cos(nib) * size * 0.42
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


def _terminal_diamonds(name: str, terminals) -> list[sg.Polygon]:
    shapes = []
    for i, (p, toward) in enumerate(terminals):
        out = _outward(p, toward)
        if out is None:
            continue
        size = MAIN * DIAMOND_SIZE * (1 + _rand(f"{name}:dia:{i}", -0.08, 0.08))
        shapes.append(_place_diamond(p, out, size))
    return shapes


def _end_diamonds(name: str, prepared, ink, terminals) -> list[sg.Polygon]:
    """Small nib-marks on free-hanging thin curve ends -- the blackletter
    counterpart of the didone's ball terminals, same free-end probe."""
    term_pts = [p for p, _ in terminals]
    ends = []
    for _, pts, widths, closed, is_curve in prepared:
        if closed or not is_curve:
            continue
        for end in (0, -1):
            p = pts[end]
            q = pts[1] if end == 0 else pts[-2]
            w = widths[0] if end == 0 else widths[-1]
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
    return [
        _place_diamond(
            p,
            out,
            MAIN * END_DIAMOND_SIZE * (1 + _rand(f"{name}:enddia:{i}", -0.08, 0.08)),
        )
        for i, (p, out) in enumerate(merged)
    ]


def _prepare(name: str, si: int, stroke: dict, terminals):
    """One recorded stroke -> ("dot", diamond) or ("stroke", (shape,
    pts, widths, closed, is_curve)) after verticalizing, fracture and
    nib widths."""
    pts = [tuple(p) for p in stroke["pts"]]
    closed = stroke["closed"]
    if closed and len(pts) > 1 and math.dist(pts[0], pts[-1]) < 1e-6:
        pts = pts[:-1]
    if len(pts) < 2 or _path_length(pts) < DOT_MAX_LEN:
        return "dot", _diamond(pts[0], stroke["width"] * 1.15)
    is_curve = len(pts) >= CURVE_MIN_PTS
    if is_curve:
        pts = _fracture(pts, closed)
    elif not closed:
        pts = _verticalize(name, pts, terminals)
    scale = min(max(stroke["width"] / STROKE, 0.6), 1.5)
    scale *= 1 + _rand(f"{name}:weight", -GLYPH_WEIGHT_VAR, GLYPH_WEIGHT_VAR)
    widths = _seg_widths(name, si, pts, closed, scale)
    return "stroke", (
        _varwidth_shape(pts, widths, closed),
        pts,
        widths,
        closed,
        is_curve,
    )


def _comma_shapes() -> list:
    """A nib-mark with a hairline tail flicking down-left."""
    head = _diamond((250.0, 45.0), 110.0)
    tail_pts = [(262.0, 20.0), (238.0, -50.0), (200.0, -115.0)]
    return [head, _varwidth_shape(tail_pts, [50.0, 22.0], closed=False)]


def _f_strokes_bl():
    """Textura f: the didone's hairline flag arc fractures into an
    invisible stub here, and the sans' 180-unit crossbar disappears
    inside a 148-wide stem. Redrawn with a long bar and a slimmer,
    clearly angled flag riding off the stem top."""
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


OVERRIDES = {**STROKE_OVERRIDES, "f": _f_strokes_bl, "t": _t_strokes_bl}


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
    for si, s in enumerate(strokes):
        kind, payload = _prepare(name, si, s, terminals)
        if kind == "dot":
            dots.append(payload)
        else:
            prepared.append(payload)
    stroke_shapes = [p[0] for p in prepared]
    ink = unary_union(stroke_shapes + dots) if (stroke_shapes or dots) else sg.Polygon()
    diamonds = _terminal_diamonds(name, terminals)
    diamonds += _end_diamonds(name, prepared, ink, terminals)
    return stroke_shapes + dots + diamonds, advance


def _build(name: str, fn):
    def build():
        shapes, advance = blackletter_shapes(name, fn)
        geom = union_all(shapes)
        slant = _rand(f"{name}:lean", -SLANT_VAR, SLANT_VAR)
        geom = affinity.affine_transform(geom, [1, slant, 0, 1, 0, 0])
        geom = (
            geom.buffer(SOFTEN_R, quad_segs=4)
            .buffer(-2 * SOFTEN_R, quad_segs=4)
            .buffer(SOFTEN_R, quad_segs=4)
        )
        return polygon_to_contours(geom), advance

    return build


def make_glyphs(skeletons: dict) -> dict:
    """name -> () -> (contours, advance) for the blackletter face -- the
    same contract GLYPHS exposes for the sans."""
    return {name: _build(name, fn) for name, fn in skeletons.items()}
