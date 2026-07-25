"""Serif-foot geometry, generated from a glyph's declared terminals rather
than hand-assembled per letter.

`serif_foot(point, toward)` is the only entry point a caller needs: it
looks at the direction from `point` back toward `toward` and picks the
matching construction automatically --

- near-vertical  -> a flat foot flaring via a concave fillet into the stem
  (bracketed, like Times' serifs on I/H/L).
- near-horizontal -> the same bracket, rotated 90 degrees, for arm/crossbar
  ends (E, F, T, Z).
- anything else (a genuine diagonal) -> a smooth elliptical flare aligned
  with the stroke's own angle.

Earlier versions of this module hand-picked one of three constructors per
terminal, with a manual up=/rightward=/toward= flag at every call site --
which is exactly how the digit six (still calling the vertical constructor
on a diagonal hook) and digit four (two independent feet crashing into
each other) shipped broken: nothing forced the flag to match the geometry
it was describing. Auto-classifying from the two points removes the flag
entirely, so there's no longer a way for them to disagree.
"""

import math

from shapely.geometry import Polygon

from fontgen.primitives import arc_pts

# Stem half-width (matches the stroke width every stem is already drawn
# at), how far a foot's flat edge extends past the stem, and the fillet
# radius that blends between them. A flat rectangle laid across a stem end
# reads as a crossbar, not a serif -- the fillet is what makes the stem
# visually *widen into* the foot instead of a foot being overlaid on top.
BRACKET_SW = 39.0
BRACKET_FOOT_W = 90.0
BRACKET_FILLET_R = 45.0
BRACKET_OVERLAP = 50.0

# A diagonal's flare: wide across the stroke, shallow along it, and pulled
# slightly inward from the terminal (push) so it doesn't perch entirely
# outside the stroke's own ink.
DIAG_FOOT_W = 95.0
DIAG_DEPTH = 42.0
DIAG_PUSH = 0.05

# A terminal within this many degrees of true vertical or true horizontal
# gets the bracketed foot; anything else (every real diagonal in this
# font -- A's ~70 degrees through six's ~20) gets the elliptical flare.
# The two bracket cases are unambiguous (every straight stem/arm in this
# font is either exactly vertical or exactly horizontal); this threshold
# only has to be strict enough to keep true diagonals off the bracket
# path, since a rotated bracket's own fillet, sized for an axis-aligned
# stem, doesn't stay well-behaved once the angle is more than a few
# degrees off-axis (see the digit-six/digit-K regression this replaced).
AXIS_TOLERANCE_DEG = 5.0


def _bracket_foot(cx, y0, up, sw, fw, r, overlap):
    """A flat foot on the line y=y0, flaring via concave fillets into a
    vertical stem of half-width sw that continues away from y0. `up=True`
    means the stem rises above y0 (a bottom serif); `up=False` means it
    descends below y0 (a top serif).

    The stem this attaches to is drawn with a round cap (matching the rest
    of the font), which bulges sw units past y0 in the outward direction --
    past the flat foot edge this would otherwise draw right at y0, leaving
    the cap's round bulge poking out as its own separate lump. Shifting y0
    outward by sw first makes the foot's own silhouette fully swallow that
    bulge instead.
    """
    y0 = y0 - sw if up else y0 + sw
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


def _bracket_foot_h(x0, cy, rightward, sw, fw, r, overlap, guideline_shift):
    """The same bracketed foot as _bracket_foot, rotated 90 degrees for a
    HORIZONTAL stem (an arm/crossbar end). `rightward=True` means the stem
    runs to the right of x0 (a left-end serif); `rightward=False` means it
    runs left (a right-end serif).

    Every horizontal terminal in this font sits exactly on a top or bottom
    guideline (cap-height, x-height, or baseline) -- so a foot centered
    symmetrically on cy would spread `fw` units above AND below it, poking
    `fw` units past the guideline on the outward side. `guideline_shift`
    (positive to shift the center down, negative to shift it up) keeps only
    a small deliberate overshoot there, matching how round letters already
    overshoot, instead of a large accidental one.
    """
    cy = cy + guideline_shift
    x0 = x0 - sw if rightward else x0 + sw
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


def _diagonal_flare(px, py, ux, uy, fw, depth, push):
    """A serif flare for a DIAGONAL stroke terminal at (px, py), oriented
    to match the stroke's actual direction (ux, uy) instead of assuming a
    vertical or horizontal stem.

    Two earlier approaches both failed. Reusing the vertical bracket
    unrotated made the flare run vertically while the stroke ran off at an
    angle, reading as a stray vertical nub bolted onto the diagonal.
    Rotating (or shearing) a hand-built bracket polygon to match the angle
    fixed the direction but introduced a *precision* bug: the polygon's
    "buried" edge was constructed to land exactly on the real stroke's own
    edge, and at a generic (non axis-aligned) angle that exact coincidence
    is a classic GEOS robustness trap -- unary_union either threw
    'TopologyException: side location conflict' outright, or silently
    produced a spiky sliver where the near-coincident edges got resolved
    the wrong way, worse the further the angle sat from vertical.

    This sidesteps the whole problem: instead of matching the stroke's
    width exactly, it's a smooth parametrized ellipse -- wide (fw) across
    the stroke, shallow (depth) along it -- centered just inside the
    terminal. A curve has no straight edges to exactly coincide with
    anything, so it unions with the stroke exactly the way every other
    curved shape in this codebase already does (bowls, hooks, rings), with
    no special-cased robustness issue.
    """
    perp = (-uy, ux)
    cx, cy = px + depth * push * ux, py + depth * push * uy
    n = 40
    pts = []
    for i in range(n):
        t = 2 * math.pi * i / n
        local_x = fw * math.cos(t)
        local_y = depth * math.sin(t)
        pts.append(
            (
                cx + local_x * perp[0] + local_y * ux,
                cy + local_x * perp[1] + local_y * uy,
            )
        )
    return Polygon(pts)


def serif_foot(point, toward):
    """Build a serif foot for the stroke terminal at `point`, given any
    other point `toward` back along the same stroke (used only to derive
    its local direction -- distance doesn't matter).
    """
    px, py = point
    tx, ty = toward
    dx, dy = tx - px, ty - py
    length = math.hypot(dx, dy)
    ux, uy = dx / length, dy / length
    angle = math.degrees(math.atan2(dy, dx))
    from_vertical = abs(abs(angle) - 90)
    from_horizontal = min(abs(angle), abs(abs(angle) - 180))

    if from_vertical <= AXIS_TOLERANCE_DEG:
        up = dy > 0
        return _bracket_foot(
            px, py, up, BRACKET_SW, BRACKET_FOOT_W, BRACKET_FILLET_R, BRACKET_OVERLAP
        )
    if from_horizontal <= AXIS_TOLERANCE_DEG:
        rightward = dx > 0
        # Stroke goes down from here (dy < 0) => this terminal sits on a
        # TOP guideline, so the foot must shift down to avoid overshooting
        # above it; stroke goes up => a BOTTOM guideline, shift up.
        shift = (BRACKET_FOOT_W - 15) * (-1 if dy < 0 else 1)
        return _bracket_foot_h(
            px,
            py,
            rightward,
            BRACKET_SW,
            BRACKET_FOOT_W,
            BRACKET_FILLET_R,
            BRACKET_OVERLAP,
            shift,
        )
    return _diagonal_flare(px, py, ux, uy, DIAG_FOOT_W, DIAG_DEPTH, DIAG_PUSH)
