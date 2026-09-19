"""Serif-face design constants and foot geometry.

Two things live here: the elliptical PEN the serif face is stroked with
(see fontgen/glyphs_serif.py for the stroking itself), and the serif-foot
constructions generated from each glyph's declared terminals.

`serif_foot(point, toward)` is the only foot entry point a caller needs:
it looks at the direction from `point` back toward `toward` and picks the
matching construction automatically --

- near-vertical  -> a thin slab flaring via a shallow concave bracket into
  the stem (a flick, like a text face's serifs on I/H/L).
- near-horizontal -> a beak: a thin tapered vertical flick off the arm's
  far edge (E, F, T, Z).
- anything else (a genuine diagonal) -> a thin axis-aligned pad laid along
  the horizontal guideline the stroke ends on (every diagonal terminal in
  this font ends on cap height, x-height, or the baseline).

Earlier versions of this module hand-picked one of three constructors per
terminal, with a manual up=/rightward=/toward= flag at every call site --
which is exactly how the digit six (still calling the vertical constructor
on a diagonal hook) and digit four (two independent feet crashing into
each other) shipped broken: nothing forced the flag to match the geometry
it was describing. Auto-classifying from the two points removes the flag
entirely, so there's no longer a way for them to disagree.
"""

import math

from shapely.geometry import LineString, Polygon

from fontgen.metrics import STROKE, XMID
from fontgen.primitives import ellipse_pts

# The serif face's pen: an axis-aligned ellipse swept along each stroke
# centerline. PEN_THICK is the full width of a vertical stem; PEN_THIN the
# full weight of a horizontal. PEN_THIN deliberately equals the skeleton
# grid's circular STROKE, so every vertical relationship the skeletons
# were tuned against (bar weights, bowl overshoot, how far a cap bulges
# past a stem's end) is preserved exactly -- contrast comes only from
# widening the thick axis. The ~1.4 ratio with vertical stress is the
# newsprint "legibility group" (Ionic/Century) class of text faces.
PEN_THICK = 108.0
PEN_THIN = float(STROKE)

# Stem/arm half-widths under that pen, and the distance the pen's cap
# bulges past a stroke's endpoint: the thin semi-axis vertically past a
# vertical stem's end, the thick semi-axis horizontally past a horizontal
# arm's end. The bulge is what a foot's flat edge must shift outward to
# swallow -- a foot drawn right at the terminal would leave the cap's
# curve poking past it as its own lump.
STEM_HW = PEN_THICK / 2
ARM_HW = PEN_THIN / 2
CAP_BULGE_V = PEN_THIN / 2
CAP_BULGE_H = PEN_THICK / 2

# The serif is a FLICK, not a block: a thin slab whose tips are FOOT_TIP
# thick, rising through a shallow concave bracket (an elliptical quarter
# arc FOOT_REACH - STEM_HW wide and FOOT_RISE tall) into the stem. The
# slab's flat edge sits CAP_BULGE_V outside the terminal to swallow the
# pen's round cap, so the face's baseline (the flats' ink) is that edge.
# Earlier feet were a 46-unit quarter-circle wedge with no slab at all,
# which read as a chunky block at text sizes.
FOOT_REACH = 118.0
FOOT_TIP = 12.0
FOOT_RISE = 30.0
BRACKET_OVERLAP = 50.0

# Arm ends (E, F, T, L, Z) get a BEAK: a thin vertical flick hanging off
# the arm's far edge on the side away from its guideline (down from a
# top arm, up from a bottom one). BEAK_W is how far back along the arm
# its base reaches, BEAK_TIP its thickness at the point, BEAK_DROP how
# far past the arm's edge the point reaches. Its outer edge is flush
# with the pen cap's extreme, so the corner is squared. The old flag was
# a bracketed slab 2 * 90 tall and ~100 wide -- a block on every arm.
BEAK_W = 58.0
BEAK_TIP = 14.0
BEAK_DROP = 62.0

# A diagonal's guideline pad: a thin stadium along the guideline the
# stroke ends on, half-width along the guideline and thickness.
DIAG_FOOT_W = 84.0
DIAG_FOOT_T = 24.0

# A terminal within this many degrees of true vertical or true horizontal
# gets the bracketed foot / beak; anything else (every real diagonal in
# this font -- A's ~70 degrees through six's ~20) gets the guideline pad.
AXIS_TOLERANCE_DEG = 5.0


def _bracket_foot(cx, y0, up, sw, fw, tip, rise, overlap, bulge):
    """A flick foot on the line y=y0 for a vertical stem of half-width sw
    continuing away from y0: a slab of thickness `tip` at its outer ends,
    each end rising through a shallow concave elliptical bracket (fw - sw
    wide, `rise` tall) to meet the stem's edge. `up=True` means the stem
    rises above y0 (a bottom serif); `up=False` a top serif.

    The stem is drawn with the pen's round cap, which bulges `bulge`
    units past y0 outward; the slab's flat edge is shifted out by that
    much so the foot's silhouette swallows the cap's curve instead of
    leaving it poking out as its own lump.
    """
    sign = 1 if up else -1
    base = y0 - sign * bulge
    shoulder = base + sign * (tip + rise)
    cap_y = shoulder + sign * overlap
    rx = fw - sw
    if up:
        right = ellipse_pts(cx + fw, shoulder, rx, rise, 270, 180, n=16)
        left = ellipse_pts(cx - fw, shoulder, rx, rise, 0, -90, n=16)
    else:
        right = ellipse_pts(cx + fw, shoulder, rx, rise, 90, 180, n=16)
        left = ellipse_pts(cx - fw, shoulder, rx, rise, 0, 90, n=16)
    boundary = (
        [(cx - fw, base), (cx + fw, base)]
        + right
        + [(cx + sw, cap_y), (cx - sw, cap_y)]
        + left
    )
    return Polygon(boundary)


def _arm_beak(px, py, rightward, on_top, hw, w, tip, drop, bulge):
    """A beak at the end of a horizontal arm of half-thickness hw ending
    at (px, py). `rightward=True` means the arm runs to the right of px
    (a left-end beak); `on_top` says the arm sits on a top guideline, so
    the beak hangs down from its underside (else it rises from its top
    edge). The outer edge is flush with the pen cap's extreme, `bulge`
    past px; the inner edge is a concave elliptical arc from the point
    back to the arm.
    """
    sx = -1 if rightward else 1  # outward direction along the arm
    sy = -1 if on_top else 1  # direction the beak points, off the arm
    xo = px + sx * bulge
    y_near = py - sy * hw  # the arm's edge on the guideline side
    y_edge = py + sy * hw  # the arm's edge the beak hangs off
    y_tip = y_edge + sy * drop
    # Concave inner edge: quarter ellipse centered on the arm's edge at
    # the tip's x, from the arm (w back along it) to the point; walked
    # point-first so the boundary runs outer edge -> point -> arm.
    a_start = 180 if not rightward else 0
    a_end = a_start + (90 if (not rightward) == on_top else -90)
    inner = ellipse_pts(xo - sx * tip, y_edge, w - tip, drop, a_start, a_end, n=16)
    boundary = [(xo, y_near), (xo, y_tip)] + inner[::-1] + [(xo - sx * w, y_near)]
    return Polygon(boundary)


def _guideline_pad(px, py, up, fw, t, bulge):
    """A serif foot for a DIAGONAL stroke terminal at (px, py): a thin
    flat pad laid along the horizontal guideline the stroke ends on --
    which is how diagonal serifs actually sit in seriffed faces (A's and
    V's feet rest ON the baseline/cap line, they don't hang off the
    stroke at its own angle). `up=True` means the stroke rises away from
    the pad (a baseline/bottom foot); `up=False` a cap-height/x-height
    top pad.

    Two constraints shape this. First, robustness: an earlier stroke-angle-
    aligned construction that shared an exact edge with the stroke was a
    GEOS union trap (TopologyException / spiky slivers), so like the fix
    that replaced it, this shape never coincides with the stroke's own
    edges -- it's axis-aligned while the stroke is not. Second, the pen's
    cap dips `bulge` (its thin semi-axis) past the terminal, so the pad's
    outer edge sits `bulge` outside py (exactly like _bracket_foot's
    shift) to swallow that curve; a stadium (flat top/bottom, round ends)
    keeps the ends in the font's own round-cap vocabulary.
    """
    y_out = py - bulge if up else py + bulge
    cy = y_out + t / 2 if up else y_out - t / 2
    r = t / 2
    return LineString([(px - fw + r, cy), (px + fw - r, cy)]).buffer(
        r, quad_segs=16, cap_style="round"
    )


def serif_foot(point, toward):
    """Build a serif foot for the stroke terminal at `point`, given any
    other point `toward` back along the same stroke (used only to derive
    its local direction -- distance doesn't matter).
    """
    px, py = point
    tx, ty = toward
    dx, dy = tx - px, ty - py
    angle = math.degrees(math.atan2(dy, dx))
    from_vertical = abs(abs(angle) - 90)
    from_horizontal = min(abs(angle), abs(abs(angle) - 180))

    if from_vertical <= AXIS_TOLERANCE_DEG:
        return _bracket_foot(
            px,
            py,
            dy > 0,
            STEM_HW,
            FOOT_REACH,
            FOOT_TIP,
            FOOT_RISE,
            BRACKET_OVERLAP,
            CAP_BULGE_V,
        )
    if from_horizontal <= AXIS_TOLERANCE_DEG:
        # A horizontal terminal sits ON a top guideline (cap or x-height)
        # or a bottom one (the baseline) -- its own stroke runs level, so
        # its direction says nothing about which; classify by the
        # terminal's own height instead.
        return _arm_beak(
            px,
            py,
            dx > 0,
            py > XMID,
            ARM_HW,
            BEAK_W,
            BEAK_TIP,
            BEAK_DROP,
            CAP_BULGE_H,
        )
    # A genuine diagonal: its terminal rests on a horizontal guideline, and
    # `up` (stroke rising away from the terminal) says which side the pad
    # goes on.
    return _guideline_pad(px, py, dy > 0, DIAG_FOOT_W, DIAG_FOOT_T, CAP_BULGE_V)
