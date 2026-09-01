"""Serif-face design constants and foot geometry.

Two things live here: the elliptical PEN the serif face is stroked with
(see fontgen/glyphs_serif.py for the stroking itself), and the serif-foot
constructions generated from each glyph's declared terminals.

`serif_foot(point, toward)` is the only foot entry point a caller needs:
it looks at the direction from `point` back toward `toward` and picks the
matching construction automatically --

- near-vertical  -> a flat foot flaring via a concave fillet into the stem
  (bracketed, like Times' serifs on I/H/L).
- near-horizontal -> the same bracket, rotated 90 degrees, for arm/crossbar
  ends (E, F, T, Z).
- anything else (a genuine diagonal) -> a flat axis-aligned pad laid along
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
from fontgen.primitives import arc_pts

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

# Foot reach past the stem centerline, and the fillet radius that blends
# foot into stem. A flat rectangle laid across a stem end reads as a
# crossbar, not a serif -- the fillet is what makes the stem visually
# *widen into* the foot. FOOT_W - FILLET_R equals STEM_HW exactly, so each
# fillet's inner end lands right on the stem's edge with no ledge.
BRACKET_FOOT_W = 100.0
BRACKET_FILLET_R = 46.0
BRACKET_OVERLAP = 50.0

# Arm-end flags keep a slightly shorter reach: an arm is thin (ARM_HW), so
# a full-length flag on it reads longer than the same flag on a stem.
ARM_FOOT_W = 90.0
ARM_FILLET_R = 45.0

# A diagonal's guideline pad: half-width along the guideline (sized to
# match the bracket foot's reach against the wider diagonal strokes the
# pen draws) and its flat thickness.
DIAG_FOOT_W = 96.0
DIAG_FOOT_T = 50.0

# A terminal within this many degrees of true vertical or true horizontal
# gets the bracketed foot; anything else (every real diagonal in this
# font -- A's ~70 degrees through six's ~20) gets the guideline pad.
# The two bracket cases are unambiguous (every straight stem/arm in this
# font is either exactly vertical or exactly horizontal); this threshold
# only has to be strict enough to keep true diagonals off the bracket
# path, since a rotated bracket's own fillet, sized for an axis-aligned
# stem, doesn't stay well-behaved once the angle is more than a few
# degrees off-axis (see the digit-six/digit-K regression this replaced).
AXIS_TOLERANCE_DEG = 5.0


def _bracket_foot(cx, y0, up, sw, fw, r, overlap, bulge):
    """A flat foot on the line y=y0, flaring via concave fillets into a
    vertical stem of half-width sw that continues away from y0. `up=True`
    means the stem rises above y0 (a bottom serif); `up=False` means it
    descends below y0 (a top serif).

    The stem this attaches to is drawn with the pen's round cap, which
    bulges `bulge` units past y0 in the outward direction -- past the flat
    foot edge this would otherwise draw right at y0, leaving the cap's
    curve poking out as its own separate lump. Shifting y0 outward by
    `bulge` first makes the foot's own silhouette fully swallow that
    curve instead.
    """
    y0 = y0 - bulge if up else y0 + bulge
    stem_y = y0 + r if up else y0 - r
    cap_y = stem_y + overlap if up else stem_y - overlap
    foot_angle = 270 if up else 90
    right_fillet = arc_pts(cx + fw, stem_y, r, foot_angle, 180, n=16)
    left_fillet = arc_pts(cx - fw, stem_y, r, 360 if up else 0, foot_angle, n=16)
    boundary = (
        [(cx - fw, y0), (cx + fw, y0)]
        + right_fillet[1:]
        + [(cx + sw, cap_y), (cx - sw, cap_y)]
        + left_fillet
    )
    return Polygon(boundary)


def _bracket_foot_h(x0, cy, rightward, sw, fw, r, overlap, guideline_shift, bulge):
    """The same bracketed foot as _bracket_foot, rotated 90 degrees for a
    HORIZONTAL stem (an arm/crossbar end). `rightward=True` means the stem
    runs to the right of x0 (a left-end serif); `rightward=False` means it
    runs left (a right-end serif). `bulge` is how far the pen's cap
    extends horizontally past the arm's endpoint (the pen's thick
    semi-axis), which the foot shifts outward to swallow.

    Every horizontal terminal in this font sits exactly on a top or bottom
    guideline (cap-height, x-height, or baseline) -- so a foot centered
    symmetrically on cy would spread `fw` units above AND below it, poking
    `fw` units past the guideline on the outward side. `guideline_shift`
    keeps only a small deliberate overshoot there, matching how round
    letters already overshoot, instead of a large accidental one.
    """
    cy = cy + guideline_shift
    x0 = x0 - bulge if rightward else x0 + bulge
    stem_x = x0 + r if rightward else x0 - r
    cap_x = stem_x + overlap if rightward else stem_x - overlap
    foot_angle = 180 if rightward else 0
    # The "far" end of each fillet is geometrically the same point (270 for
    # the top fillet, 90 for the bottom) regardless of direction, but
    # arc_pts sweeps directly between the two angle *values* given with no
    # wraparound -- for rightward=False (foot_angle=0) using 270 literally
    # would sweep the long way (270 degrees) instead of the short quarter
    # turn, so it's expressed as -90 (0's short path) in that case.
    top_fillet = arc_pts(
        stem_x, cy + fw, r, foot_angle, 270 if rightward else -90, n=16
    )
    bottom_fillet = arc_pts(stem_x, cy - fw, r, 90, foot_angle, n=16)
    boundary = (
        [(x0, cy - fw), (x0, cy + fw)]
        + top_fillet[1:]
        + [(cap_x, cy + sw), (cap_x, cy - sw)]
        + bottom_fillet
    )
    return Polygon(boundary)


def _guideline_pad(px, py, up, fw, t, bulge):
    """A serif foot for a DIAGONAL stroke terminal at (px, py): a flat pad
    laid along the horizontal guideline the stroke ends on -- which is how
    diagonal serifs actually sit in seriffed faces (A's and V's feet rest
    ON the baseline/cap line, they don't hang off the stroke at its own
    angle). `up=True` means the stroke rises away from the pad (a
    baseline/bottom foot); `up=False` a cap-height/x-height top pad.

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
        up = dy > 0
        return _bracket_foot(
            px,
            py,
            up,
            STEM_HW,
            BRACKET_FOOT_W,
            BRACKET_FILLET_R,
            BRACKET_OVERLAP,
            CAP_BULGE_V,
        )
    if from_horizontal <= AXIS_TOLERANCE_DEG:
        rightward = dx > 0
        # A horizontal terminal sits ON a top guideline (cap or x-height)
        # or a bottom one (the baseline) -- its own stroke runs level, so
        # its direction says nothing about which; classify by the
        # terminal's own height instead. Top => shift the foot down so it
        # doesn't poke above the guideline; bottom => shift it up.
        on_top_guideline = py > XMID
        shift = (ARM_FOOT_W - 15) * (-1 if on_top_guideline else 1)
        return _bracket_foot_h(
            px,
            py,
            rightward,
            ARM_HW,
            ARM_FOOT_W,
            ARM_FILLET_R,
            BRACKET_OVERLAP,
            shift,
            CAP_BULGE_H,
        )
    # A genuine diagonal: its terminal rests on a horizontal guideline, and
    # `up` (stroke rising away from the terminal) says which side the pad
    # goes on.
    return _guideline_pad(px, py, dy > 0, DIAG_FOOT_W, DIAG_FOOT_T, CAP_BULGE_V)
