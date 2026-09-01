"""Per-character glyph definitions built from primitives.

Each glyph function returns (shapes, advance_width, terminals). Coordinates
are authored against the shared grid in metrics.py: baseline at y=0, cap
height at y=CAP, standard glyph width/side-bearings unless a letter needs
its own (I, M, W, digits with round bowls, etc).

Every glyph assembles a list of shapes (strokes, bowls, rings) -- unioning
them (via `finalize`, applied by whichever build step consumes a glyph) is
what keeps T-junctions (e.g. E's crossbar meeting its stem) and bowl-to-stem
joins (e.g. D, P, B, R) free of internal seams.

`terminals` declares, for every straight stroke's free end (a stem top, an
arm end, a diagonal's terminus -- anywhere a serif would go, NOT an internal
joint like K's elbow or A's apex), a `(point, toward)` pair: `point` is the
terminal itself and `toward` is any other point back along the same stroke,
used only to derive the stroke's local direction. This is the single source
of truth both fonts share -- the sans build ignores it, the serif build
(fontgen/serifs.py) uses it to auto-classify each terminal as vertical,
horizontal, or diagonal and generate the matching foot, with no manual
per-glyph angle bookkeeping to get wrong. Declaring a terminal here, right
next to the coordinates that define it, is what keeps the two fonts from
drifting apart the way a hand-maintained duplicate glyph set would.

Curved letters (O, C, G, Q, S, ring-based digits) declare no terminals --
serifs belong at the ends of straight strokes, not on curves.
"""

from fontgen.metrics import BASE, CAP, DESCENT, MID, OVERSHOOT, STROKE, X_HEIGHT
from fontgen.primitives import (
    arc_band,
    arc_pts,
    disc,
    ellipse_band,
    ellipse_pts,
    finalize,
    rect,
    ring,
    stroke_union,
)

# Full circular glyphs (O, C, G, Q, zero) are tangent to CAP/BASE at this
# outer radius, sized so they overshoot the flat cap-height/baseline by
# OVERSHOOT -- without it, round shapes look optically smaller than
# flat-topped letters at the same nominal height.
RING_R = (CAP - BASE) / 2 + OVERSHOOT

# Same idea, one size down, for x-height bowls (a, b, c, d, e, g, o, p, q).
LOWER_OVERSHOOT = 10
LOWER_RING_R = X_HEIGHT / 2 + LOWER_OVERSHOOT
XMID = X_HEIGHT / 2


def _chain(*point_lists, width=STROKE):
    return stroke_union(point_lists, width)


def _bowl(x, cy, r, a0=-90, a1=90, width=STROKE, cap_style="flat"):
    return arc_band(x, cy, r, a0, a1, width, cap_style=cap_style)


def _lerp(a, b, t):
    return a + (b - a) * t


#: A bowl that bulges out no farther than its own half-height is a
#: quarter-circle -- geometrically tidy, but it reads as narrow/pinched
#: compared to how bowls actually look in most typefaces. This is how much
#: farther a bowl bulges out relative to its half-height by default.
BOWL_WIDTH_RATIO = 1.35


def _bulge_bowl(stem_x, y_bottom, y_top, bulge_r, bulge, width_ratio=BOWL_WIDTH_RATIO):
    """A round bowl bulging out from a vertical stem -- an elliptical half
    (or partial) arc, wider than it is tall, with flush ends where it
    meets the stem. The shared curve behind D/P/B/R and a/b/d/p/q/g:
    `bulge='right'` bows out to the right of the stem (as in b, p, D, P,
    B, R); 'left' bows out to the left (as in a, d, q, g).

    `bulge_r` sets the bowl's half-height (y_top/y_bottom are bulge_r away
    from its vertical center); the horizontal radius is scaled up by
    `width_ratio` so the bowl isn't locked to a circle's 1:1 width.
    """
    cy = (y_top + y_bottom) / 2
    ry = (y_top - y_bottom) / 2
    rx = ry * width_ratio
    a0, a1 = (-90, 90) if bulge == "right" else (90, 270)
    return ellipse_band(stem_x, cy, rx, ry, a0, a1, STROKE)


def _stem_bowl(stem_x, stem_top, stem_bottom, bowl_cy, bowl_r, bulge):
    """A vertical stem with a round bowl attached at one side -- the shared
    skeleton behind b/d/p/q (and a's short-stem variant).
    """
    return [
        _chain([(stem_x, stem_bottom), (stem_x, stem_top)]),
        _bulge_bowl(stem_x, bowl_cy - bowl_r, bowl_cy + bowl_r, bowl_r, bulge),
    ]


def _s_curve(L, R, T, B):
    """S's skeleton (also used for s, 5): two stacked elliptical arcs
    sampled into ONE polyline, meeting tangentially at the waist.

    Earlier attempts, for the record: a right-angle zigzag read as
    swastika-like at this weight; an eased sine gave the reverse-curve
    handedness but its long straight waist crossing still read as a
    lightning bolt; and two separately-stroked circles never joined
    cleanly. The construction that works: the top arc's LOWEST point and
    the bottom arc's HIGHEST point are the same point with the same
    (horizontal) tangent, so sampling top-arc-then-bottom-arc into one
    skeleton is smooth by construction. Handedness comes from sweep
    direction: the top arc runs CCW from its upper-right mouth over the
    top and down the left side to its bottom; the bottom arc continues
    CW from its top down the right side and around, mouth at lower
    left. Top slightly smaller than bottom, as in most S's.
    """
    cx = (L + R) / 2
    margin = 12
    height = (T - margin) - (B + margin)
    ry_top = height / 2 * 0.46
    ry_bot = height / 2 - ry_top
    rx_top = (R - L) / 2 * 0.82
    rx_bot = (R - L) / 2 * 0.95
    top = ellipse_pts(cx, T - margin - ry_top, rx_top, ry_top, 35, 270)
    bottom = ellipse_pts(cx, B + margin + ry_bot, rx_bot, ry_bot, 90, -125)
    skeleton = top + bottom[1:]
    return [stroke_union([skeleton], STROKE, cap_style="round")]


def _hook(stem_x, stem_top, hook_r, hook_cy, curl_end=-200):
    """A descender hook (J, j, g's tail): the stem comes straight down and
    curls left, like a shepherd's crook. The hook circle is centered so
    its RIGHTMOST point -- not its middle -- is where the stem meets it: a
    circle's tangent at its rightmost point is naturally vertical, matching
    the stem, so it curls away to only one side instead of wrapping
    symmetrically into a closed loop (which is what centering the hook on
    the stem's own x used to do -- it read as a down-arrow, not a hook).
    """
    hook_cx = stem_x - hook_r
    return [
        _chain([(stem_x, stem_top), (stem_x, hook_cy - 5)]),
        # Round cap on the curl's free end: every other free end in the
        # font is round, and the default flat cut reads as an angled chop.
        _bowl(hook_cx, hook_cy, hook_r, 0, curl_end, cap_style="round"),
    ]


def _arch(x0, x1, y_top, y_bottom, stem0_top=None, stem1_bottom=None):
    """n's skeleton: two legs joined by an arch across the top. Used
    directly for n and as the right-hand half of h (with a taller left
    stem passed via stem0_top).

    Legs stop at bowl_cy -- the height of the arch's own two endpoints --
    not y_top: y_top is the height of the arch's *peak*, in the middle,
    not where it meets either leg, so extending a leg past bowl_cy ran a
    bare straight stem alongside the curve up to the peak height, poking
    out past where the curve had already arched away.
    """
    r = (x1 - x0) / 2
    bowl_cy = y_top - r
    return [
        _chain([(x0, y_bottom), (x0, stem0_top if stem0_top is not None else bowl_cy)]),
        _chain(
            [
                (x1, stem1_bottom if stem1_bottom is not None else y_bottom),
                (x1, bowl_cy),
            ]
        ),
        _bowl((x0 + x1) / 2, bowl_cy, r, 0, 180),
    ]


def _basin(x0, x1, y_top, y_bottom):
    """u's skeleton: two legs joined by a bowl across the bottom."""
    r = (x1 - x0) / 2
    bowl_cy = y_bottom + r
    return [
        _chain([(x0, y_top), (x0, bowl_cy)]),
        _chain([(x1, y_top), (x1, bowl_cy)]),
        _bowl((x0 + x1) / 2, bowl_cy, r, 180, 360),
    ]


# ---- straight-line uppercase ------------------------------------------------


def glyph_E(L=70, R=570, T=CAP, B=BASE):
    midy = (T + B) / 2
    shape = _chain(
        [(L, B), (L, T)],
        [(L, T), (R, T)],
        [(L, midy), (R - 60, midy)],
        [(L, B), (R, B)],
    )
    terminals = [
        ((L, B), (L, T)),
        ((L, T), (L, B)),
        ((R, T), (L, T)),
        ((R, B), (L, B)),
    ]
    return [shape], 640, terminals


def glyph_F(L=70, R=570, T=CAP, B=BASE):
    midy = (T + B) / 2
    shape = _chain([(L, B), (L, T)], [(L, T), (R, T)], [(L, midy), (R - 60, midy)])
    terminals = [((L, B), (L, T)), ((L, T), (L, B)), ((R, T), (L, T))]
    return [shape], 640, terminals


def glyph_H(L=70, R=570, T=CAP, B=BASE):
    midy = (T + B) / 2
    shape = _chain([(L, B), (L, T)], [(R, B), (R, T)], [(L, midy), (R, midy)])
    terminals = [
        ((L, B), (L, T)),
        ((L, T), (L, B)),
        ((R, B), (R, T)),
        ((R, T), (R, B)),
    ]
    return [shape], 640, terminals


def glyph_I():
    x = 170
    terminals = [((x, BASE), (x, CAP)), ((x, CAP), (x, BASE))]
    return [_chain([(x, BASE), (x, CAP)])], 340, terminals


def glyph_L(L=70, R=570, T=CAP, B=BASE):
    shape = _chain([(L, T), (L, B)], [(L, B), (R, B)])
    terminals = [((L, T), (L, B)), ((R, B), (L, B))]
    return [shape], 640, terminals


def glyph_T(L=70, R=570, T=CAP, B=BASE):
    midx = (L + R) / 2
    shape = _chain([(L, T), (R, T)], [(midx, T), (midx, B)])
    terminals = [((L, T), (R, T)), ((R, T), (L, T)), ((midx, B), (midx, T))]
    return [shape], 640, terminals


def glyph_A(L=70, R=570, T=CAP, B=BASE):
    midx = (L + R) / 2
    cb_y = 260
    t = (T - cb_y) / (T - B)
    xl = _lerp(midx, L, t)
    xr = _lerp(midx, R, t)
    shape = _chain([(midx, T), (L, B)], [(midx, T), (R, B)], [(xl, cb_y), (xr, cb_y)])
    terminals = [((L, B), (midx, T)), ((R, B), (midx, T))]
    return [shape], 640, terminals


def glyph_V(L=70, R=570, T=CAP, B=BASE):
    midx = (L + R) / 2
    shape = _chain([(L, T), (midx, B), (R, T)])
    terminals = [((L, T), (midx, B)), ((R, T), (midx, B))]
    return [shape], 640, terminals


def glyph_W(L=40, R=760, T=CAP, B=BASE):
    midx = (L + R) / 2
    q1 = _lerp(L, midx, 0.5)
    q3 = _lerp(midx, R, 0.5)
    shape = _chain([(L, T), (q1, B), (midx, T - 220), (q3, B), (R, T)])
    terminals = [((L, T), (q1, B)), ((R, T), (q3, B))]
    return [shape], 800, terminals


def glyph_M(L=70, R=610, T=CAP, B=BASE):
    midx = (L + R) / 2
    shape = _chain([(L, B), (L, T), (midx, T - 350), (R, T), (R, B)])
    terminals = [
        ((L, B), (L, T)),
        ((L, T), (L, B)),
        ((R, T), (R, B)),
        ((R, B), (R, T)),
    ]
    return [shape], 680, terminals


def glyph_N(L=70, R=570, T=CAP, B=BASE):
    shape = _chain([(L, B), (L, T), (R, B), (R, T)])
    terminals = [
        ((L, B), (L, T)),
        ((L, T), (L, B)),
        ((R, B), (R, T)),
        ((R, T), (R, B)),
    ]
    return [shape], 640, terminals


def glyph_Z(L=70, R=570, T=CAP, B=BASE):
    shape = _chain([(L, T), (R, T), (L, B), (R, B)])
    # Only the two FREE bar ends get serifs. (R, T) and (L, B) are the
    # corners where the diagonal turns -- joints, not terminals -- and
    # serifs there filled Z's corners into solid blocks.
    terminals = [((L, T), (R, T)), ((R, B), (L, B))]
    return [shape], 640, terminals


def glyph_X(L=70, R=570, T=CAP, B=BASE):
    shape = _chain([(L, T), (R, B)], [(R, T), (L, B)])
    terminals = [
        ((L, T), (R, B)),
        ((R, B), (L, T)),
        ((R, T), (L, B)),
        ((L, B), (R, T)),
    ]
    return [shape], 640, terminals


def glyph_Y(L=70, R=570, T=CAP, B=BASE):
    midx = (L + R) / 2
    midy = 380
    shape = _chain([(L, T), (midx, midy), (R, T)], [(midx, midy), (midx, B)])
    terminals = [
        ((L, T), (midx, midy)),
        ((R, T), (midx, midy)),
        ((midx, B), (midx, midy)),
    ]
    return [shape], 640, terminals


def glyph_K(L=70, R=570, T=CAP, B=BASE):
    # Joint sits a little above center so the upper arm is shorter than
    # the lower leg -- both meeting at the vertical midpoint reads as too
    # symmetric, but too far above center (430) looked too high.
    joint_y = 380
    shape = _chain([(L, B), (L, T)], [(L, joint_y), (R, T)], [(L, joint_y), (R, B)])
    terminals = [
        ((L, B), (L, T)),
        ((L, T), (L, B)),
        ((R, T), (L, joint_y)),
        ((R, B), (L, joint_y)),
    ]
    return [shape], 640, terminals


# ---- curved uppercase --------------------------------------------------------


def glyph_O():
    cx, cy, r_out = 360, MID, RING_R
    return [ring(cx, cy, r_out, r_out - STROKE)], 720, []


def glyph_C():
    cx, cy, r = 360, MID, RING_R - STROKE / 2
    return [_bowl(cx, cy, r, 40, 320, cap_style="round")], 720, []


def glyph_G():
    cx, cy, r = 360, MID, RING_R - STROKE / 2
    # Gap sits above the midline (not straddling it) so the ring still has
    # ink exactly at y=cy on the right, where the crossbar needs to connect.
    shapes = [
        _bowl(cx, cy, r, 50, 370, cap_style="round"),
        # Ends flush with the ring's centerline -- its own round cap
        # already reaches the ring's outer edge, so overshooting past r
        # poked a visible "nipple" out past the boundary.
        _chain([(cx + 60, MID), (cx + r, MID)], width=STROKE),
    ]
    return shapes, 720, []


def glyph_Q():
    cx, cy, r_out = 360, MID, RING_R
    shapes = [
        ring(cx, cy, r_out, r_out - STROKE),
        _chain([(cx + 90, cy - 150), (cx + 260, BASE - 60)], width=STROKE),
    ]
    return shapes, 720, []


def glyph_S(L=90, R=550, T=CAP, B=BASE):
    return _s_curve(L, R, T, B), 640, []


def glyph_U(L=90, R=590, T=CAP):
    bowl_cy = 250
    r = (R - L) / 2
    shapes = [
        _chain([(L, T), (L, bowl_cy)], [(R, T), (R, bowl_cy)]),
        _bowl((L + R) / 2, bowl_cy, r, 180, 360),
    ]
    terminals = [((L, T), (L, bowl_cy)), ((R, T), (R, bowl_cy))]
    return shapes, 680, terminals


def glyph_D(L=70, T=CAP, B=BASE):
    r = (T - B) / 2
    shapes = _stem_bowl(L, T, B, MID, r, "right")
    terminals = [((L, T), (L, B)), ((L, B), (L, T))]
    return shapes, 540, terminals


#: P and R's bowl used to reach a full 235 units both up/down and out --
#: fuller looks better, but reaching that far down the stem read as
#: bloated. Shrinking the vertical reach while holding the horizontal
#: reach (rx) fixed keeps the same width with a higher, tighter bowl.
_PR_RX = 235 * BOWL_WIDTH_RATIO


def glyph_P(L=70, T=CAP, B=BASE):
    ry = 185
    cy = T - ry
    shapes = [
        _chain([(L, B), (L, T)]),
        _bulge_bowl(L, cy - ry, cy + ry, ry, "right", width_ratio=_PR_RX / ry),
    ]
    terminals = [((L, B), (L, T)), ((L, T), (L, B))]
    return shapes, 560, terminals


def glyph_B(L=70, T=CAP, B=BASE):
    # Bottom bowl bigger than the top -- the reverse reads upside-down/goofy.
    # r_bot = 350 - r_top keeps the two bowls meeting exactly, no gap/overlap.
    # 150/200 rather than the old 120/230: a top bowl barely half the
    # bottom's size read as a caricature in every face, not classic
    # top-light asymmetry.
    r_top, r_bot = 150, 200
    cy_top = T - r_top
    cy_bot = r_bot
    shapes = [
        _chain([(L, B), (L, T)]),
        _bulge_bowl(L, cy_top - r_top, cy_top + r_top, r_top, "right"),
        _bulge_bowl(L, cy_bot - r_bot, cy_bot + r_bot, r_bot, "right"),
    ]
    terminals = [((L, B), (L, T)), ((L, T), (L, B))]
    return shapes, 540, terminals


def glyph_R(L=70, T=CAP, B=BASE, R=580):
    ry = 185
    cy = T - ry
    shapes = [
        _chain([(L, B), (L, T)]),
        _bulge_bowl(L, cy - ry, cy + ry, ry, "right", width_ratio=_PR_RX / ry),
        _chain([(L, cy - ry), (R - 30, B)]),
    ]
    terminals = [((L, B), (L, T)), ((L, T), (L, B)), ((R - 30, B), (L, cy - ry))]
    return shapes, 600, terminals


def glyph_J(R=470, T=CAP):
    hook_r = 175
    hook_cy = hook_r + 20
    shapes = _hook(R, T, hook_r, hook_cy)
    terminals = [((R, T), (R, hook_cy))]
    return shapes, 500, terminals


# ---- digits -------------------------------------------------------------


def glyph_zero():
    cx, cy, r_out = 360, MID, RING_R
    return [ring(cx, cy, r_out, r_out - STROKE)], 700, []


def glyph_one():
    x = 300
    shapes = [
        _chain([(x, CAP), (x, BASE)]),
        _chain([(x - 100, CAP - 110), (x, CAP)]),
        _chain([(x - 110, BASE), (x + 110, BASE)]),
    ]
    return shapes, 600, []


def glyph_two(L=80, R=560, T=CAP, B=BASE):
    # One continuous spine: open the mouth at the upper LEFT (150deg),
    # sweep over the top, and run off the arc at -35deg straight into
    # the baseline corner -- the tangent there already points at (L, B),
    # so the arc-to-diagonal joint is smooth instead of the elbow the
    # old three-piece 2 had. Base bar laid on separately.
    r = 175
    cx, cy = (L + R) / 2, T - r
    spine = arc_pts(cx, cy, r, 150, -35) + [(L, B)]
    shapes = [
        stroke_union([spine], STROKE, cap_style="round"),
        _chain([(L, B), (R, B)]),
    ]
    terminals = [((R, B), (L, B))]
    return shapes, 640, terminals


def glyph_three(L=150, R=620, T=CAP, B=BASE):
    # Two stacked bowls, but with real MOUTHS: the old version cut both
    # arcs off at exactly +/-90, so the 3 had a dead-flat left side and
    # read as a bracket. Sweeping past vertical (to 125/-125) hooks the
    # top arc back toward the upper left and the bottom arc toward the
    # lower left, the way a 3 is actually drawn. Bottom bowl a touch
    # bigger, matching B's top/bottom logic.
    r_top, r_bot = 165, 175
    cx = L + 10
    shapes = [
        _bowl(cx, T - r_top, r_top, 125, -90, cap_style="round"),
        _bowl(cx, r_bot, r_bot, 90, -125, cap_style="round"),
    ]
    return shapes, 660, []


def glyph_four(L=70, R=590, T=CAP, B=BASE):
    midy = 260
    shapes = [
        _chain([(R - 60, T), (L, midy), (R, midy)]),
        _chain([(R, T), (R, B)]),
    ]
    # No separate terminal for the diagonal's own top end -- it's only 60
    # units from the vertical stem's top, and two independent flared feet
    # that close together crash into each other's fillets at sharp angles.
    # The vertical stem's own serif is close enough to let the diagonal
    # simply merge into it.
    terminals = [((R, T), (R, B)), ((R, B), (R, T))]
    return shapes, 660, terminals


def glyph_five(L=90, R=550, T=CAP, B=BASE):
    # A real 5 at last -- the old glyph just reused the S skeleton. One
    # continuous spine, as drawn: top bar right-to-left, down the short
    # stem, then around the bowl (150deg over the right side to -115deg,
    # mouth at the lower left). The stem-to-arc junction is bridged by
    # the polyline itself, so no piece can drift out of tangency.
    stem_x = L + 40
    r = 190
    cx, cy = (L + R) / 2 + 10, r + 15
    spine = [(R - 30, T), (stem_x, T), (stem_x, 350)] + arc_pts(cx, cy, r, 152, -115)
    shapes = [stroke_union([spine], STROKE, cap_style="round")]
    terminals = [((R - 30, T), (stem_x, T))]
    return shapes, 640, terminals


def glyph_six(L=100, R=570, T=CAP, B=BASE):
    # The neck is now a true curve: up the left side from the bowl,
    # then a wide elliptical sweep over to the upper right, ending
    # mid-air (where the derived faces put their ball/diamond
    # terminals). The old two-segment chain had a sharp elbow that read
    # as a broken flag in every face.
    # The neck's straight run sits ON the bowl's left band (bowl-left
    # centerline, cx - r_bowl + STROKE/2), not at a fixed left margin --
    # at r_bowl=170 the old L+20 start left a visible gap between neck
    # and bowl at the waist. Bowl bumped up a size; at 170 it read tiny
    # against the tall neck.
    r_bowl = 190
    cx = (L + R) / 2
    cy_bowl = r_bowl
    neck_x = cx - r_bowl + STROKE / 2
    rx, ry = 250, 215
    neck = [(neck_x, cy_bowl)] + ellipse_pts(neck_x + rx, T - ry, rx, ry, 180, 65)
    shapes = [
        ring(cx, cy_bowl, r_bowl, r_bowl - STROKE),
        stroke_union([neck], STROKE, cap_style="round"),
    ]
    return shapes, 640, []


def glyph_seven(L=80, R=580, T=CAP, B=BASE):
    shape = _chain([(L, T), (R, T), (B + 220, B)])
    terminals = [((L, T), (R, T)), ((B + 220, B), (R, T))]
    return [shape], 640, terminals


def glyph_eight(L=80, R=580, T=CAP, B=BASE):
    r_top, r_bot = 165, 175
    cx = (L + R) / 2
    cy_top = T - r_top
    cy_bot = (cy_top - r_top) + 10 - r_bot
    shapes = [
        ring(cx, cy_top, r_top, r_top - STROKE),
        ring(cx, cy_bot, r_bot, r_bot - STROKE),
    ]
    return shapes, 660, []


def glyph_nine(L=100, R=570, T=CAP, B=BASE):
    # 6 rotated in spirit: bowl at the top, neck running down the right
    # side and sweeping out through a wide elliptical tail to the lower
    # left, ending mid-air near the baseline.
    # Mirror of six's fix: neck runs down the bowl's own right band
    # (cx + r_bowl - STROKE/2) instead of a fixed R - 20, which sat just
    # clear of the 170-radius bowl and left a seam; bowl enlarged to
    # match six.
    r_bowl = 190
    cx = (L + R) / 2
    cy_bowl = T - r_bowl
    neck_x = cx + r_bowl - STROKE / 2
    rx, ry = 250, 215
    neck = [(neck_x, cy_bowl)] + ellipse_pts(neck_x - rx, B + ry, rx, ry, 0, -115)
    shapes = [
        ring(cx, cy_bowl, r_bowl, r_bowl - STROKE),
        stroke_union([neck], STROKE, cap_style="round"),
    ]
    return shapes, 640, []


# ---- punctuation ----------------------------------------------------------


def glyph_space():
    return [], 320, []


def glyph_period():
    s = 90
    return [rect(230, 0, 230 + s, s)], 420, []


def glyph_comma():
    shape = _chain([(260, 40), (200, -110)], width=90)
    return [shape], 420, []


def glyph_hyphen():
    y = 300
    return [_chain([(90, y), (470, y)], width=STROKE)], 560, []


def glyph_colon():
    s = 90
    shapes = [rect(230, 120, 230 + s, 120 + s), rect(230, 380, 230 + s, 380 + s)]
    return shapes, 420, []


def glyph_exclam():
    x = 250
    s = 90
    shapes = [
        _chain([(x, CAP), (x, 220)], width=STROKE),
        rect(x - s / 2, 0, x + s / 2, s),
    ]
    terminals = [((x, CAP), (x, 220))]
    return shapes, 420, terminals


def glyph_question(L=90, R=530, T=CAP):
    # Bowl opens at the LOWER LEFT: from ~175 the arc climbs over the top,
    # down the right side, and hooks in toward the stem at -75. The old
    # -150..90 sweep ran the other way around -- through the bottom -- and
    # the nearly-closed circle over a hanging stem read as a qoppa.
    r = 150
    cx = (L + R) / 2
    cy = T - r
    stem_bottom = 220
    s = 90
    shapes = [
        _bowl(cx, cy, r, 175, -75, cap_style="round"),
        _chain([(cx, cy - r + 20), (cx, stem_bottom)]),
        rect(cx - s / 2, 0, cx + s / 2, s),
    ]
    return shapes, 620, []


# ---- lowercase ------------------------------------------------------------


def glyph_a_lc():
    # Geometric single-storey a (the Century Gothic construction): a FULL
    # round bowl -- the same ring as o -- with the stem overlapping its
    # right edge. The previous half-ellipse bowl closed flat against the
    # stem, and a half-disc with a bar down its flat side reads as a
    # mirrored D, not an a; keeping the counter fully round is what makes
    # the bowl read as a bowl.
    r = LOWER_RING_R
    cx = 250
    stem_x = cx + r - STROKE / 2
    shapes = [
        ring(cx, XMID, r, r - STROKE),
        _chain([(stem_x, BASE), (stem_x, X_HEIGHT)]),
    ]
    terminals = [
        ((stem_x, X_HEIGHT), (stem_x, BASE)),
        ((stem_x, BASE), (stem_x, X_HEIGHT)),
    ]
    return shapes, 520, terminals


def glyph_b_lc():
    # Same full-x-height bowl as d/p/q -- the 0.82-scaled bowl this used
    # to have hovered clear of both the baseline and x-height, which read
    # as a thorn rather than a b.
    stem_x = 70
    shapes = _stem_bowl(stem_x, CAP, BASE, XMID, LOWER_RING_R, "right")
    terminals = [((stem_x, BASE), (stem_x, CAP)), ((stem_x, CAP), (stem_x, BASE))]
    return shapes, 540, terminals


def glyph_d_lc():
    stem_x = 420
    shapes = _stem_bowl(stem_x, CAP, BASE, XMID, LOWER_RING_R, "left")
    terminals = [
        ((stem_x, CAP), (stem_x, BASE)),
        ((stem_x, BASE), (stem_x, CAP)),
    ]
    return shapes, 540, terminals


def glyph_p_lc():
    stem_x = 70
    shapes = _stem_bowl(stem_x, X_HEIGHT, DESCENT, XMID, LOWER_RING_R, "right")
    terminals = [
        ((stem_x, X_HEIGHT), (stem_x, DESCENT)),
        ((stem_x, DESCENT), (stem_x, X_HEIGHT)),
    ]
    return shapes, 540, terminals


def glyph_q_lc():
    stem_x = 420
    shapes = _stem_bowl(stem_x, X_HEIGHT, DESCENT, XMID, LOWER_RING_R, "left")
    terminals = [
        ((stem_x, X_HEIGHT), (stem_x, DESCENT)),
        ((stem_x, DESCENT), (stem_x, X_HEIGHT)),
    ]
    return shapes, 540, terminals


def glyph_g_lc():
    # Like q, but the descender curls into a hook instead of running
    # straight down. The single stem chain spans from the hook all the way
    # up to the bowl's own top point (not just to X_HEIGHT) so it closes
    # the bowl's right side completely -- leaving it short of that point
    # is what previously left the bowl open at the upper right.
    stem_x = 420
    bowl_r = LOWER_RING_R
    y_top = XMID + bowl_r
    y_bottom = XMID - bowl_r
    # A fuller hook than j's (bigger radius) so the descender reads as
    # g's under-loop rather than a clipped flick -- but only slightly
    # further back up (-190): the old -240 sweep curled the free end up
    # past the baseline into the bowl's underside, tangling the two into
    # a spiral.
    hook_r = 125
    hook_cy = DESCENT + hook_r
    shapes = [
        _chain([(stem_x, hook_cy - 5), (stem_x, y_top)]),
        _bulge_bowl(stem_x, y_bottom, y_top, bowl_r, "left"),
        _bowl(stem_x - hook_r, hook_cy, hook_r, 0, -190, cap_style="round"),
    ]
    return shapes, 540, []


def glyph_o_lc():
    cx, cy = 250, XMID
    return [ring(cx, cy, LOWER_RING_R, LOWER_RING_R - STROKE)], 500, []


def glyph_c_lc():
    cx, cy, r = 260, XMID, LOWER_RING_R - STROKE / 2
    return [_bowl(cx, cy, r, 40, 320, cap_style="round")], 500, []


def glyph_e_lc():
    # A real e: the bar crosses at mid-height and meets the bowl exactly
    # where the arc starts (angle 0, right side), sealing the eye; the
    # arc sweeps over the top and around, leaving the aperture at the
    # LOWER right (between 305 and 360 degrees) -- the previous version
    # opened at mid-right, which read as a struck-through epsilon.
    cx, cy, r = 260, XMID, LOWER_RING_R - STROKE / 2
    shapes = [
        _bowl(cx, cy, r, 0, 305, cap_style="round"),
        _chain([(cx - r, cy), (cx + r, cy)]),
    ]
    return shapes, 500, []


def glyph_s_lc(L=70, R=410):
    return _s_curve(L, R, X_HEIGHT, BASE), 480, []


def glyph_n_lc(L=70, R=410):
    shapes = _arch(L, R, X_HEIGHT, BASE)
    terminals = [((L, BASE), (L, X_HEIGHT)), ((R, BASE), (R, X_HEIGHT))]
    return shapes, 480, terminals


def glyph_m_lc(x0=60, x1=300, x2=540):
    shapes = _arch(x0, x1, X_HEIGHT, BASE) + _arch(x1, x2, X_HEIGHT, BASE)
    terminals = [
        ((x0, BASE), (x0, X_HEIGHT)),
        ((x1, BASE), (x1, X_HEIGHT)),
        ((x2, BASE), (x2, X_HEIGHT)),
    ]
    return shapes, 610, terminals


def glyph_h_lc(L=70, R=410):
    shapes = _arch(L, R, X_HEIGHT, BASE, stem0_top=CAP)
    terminals = [
        ((L, BASE), (L, CAP)),
        ((L, CAP), (L, BASE)),
        ((R, BASE), (R, X_HEIGHT)),
    ]
    return shapes, 480, terminals


def glyph_u_lc(L=70, R=410):
    shapes = _basin(L, R, X_HEIGHT, BASE)
    terminals = [((L, X_HEIGHT), (L, BASE)), ((R, X_HEIGHT), (R, BASE))]
    return shapes, 480, terminals


def glyph_r_lc():
    # Stem plus a wide open shoulder: the arm leaves the stem partway
    # up, arcs over tangent to x-height, and ends free at the upper
    # right. The old 110-unit quarter-circle hugged the stem so tightly
    # the whole letter read as an iota.
    stem_x = 70
    arm_r = 150
    shapes = [
        _chain([(stem_x, BASE), (stem_x, X_HEIGHT)]),
        _bowl(stem_x + arm_r, X_HEIGHT - arm_r, arm_r, 180, 15, cap_style="round"),
    ]
    terminals = [((stem_x, BASE), (stem_x, X_HEIGHT))]
    return shapes, 460, terminals


def glyph_v_lc(L=70, R=410):
    midx = (L + R) / 2
    shape = _chain([(L, X_HEIGHT), (midx, BASE), (R, X_HEIGHT)])
    terminals = [((L, X_HEIGHT), (midx, BASE)), ((R, X_HEIGHT), (midx, BASE))]
    return [shape], 480, terminals


def glyph_w_lc(L=40, R=560):
    midx = (L + R) / 2
    q1 = _lerp(L, midx, 0.5)
    q3 = _lerp(midx, R, 0.5)
    dip = X_HEIGHT - 160
    shape = _chain([(L, X_HEIGHT), (q1, BASE), (midx, dip), (q3, BASE), (R, X_HEIGHT)])
    terminals = [((L, X_HEIGHT), (q1, BASE)), ((R, X_HEIGHT), (q3, BASE))]
    return [shape], 600, terminals


def glyph_x_lc(L=70, R=410):
    shape = _chain([(L, X_HEIGHT), (R, BASE)], [(R, X_HEIGHT), (L, BASE)])
    terminals = [
        ((L, X_HEIGHT), (R, BASE)),
        ((R, BASE), (L, X_HEIGHT)),
        ((R, X_HEIGHT), (L, BASE)),
        ((L, BASE), (R, X_HEIGHT)),
    ]
    return [shape], 480, terminals


def glyph_y_lc(L=70, R=410):
    midx = (L + R) / 2
    cross_y = 140
    shapes = [
        _chain([(L, X_HEIGHT), (midx, cross_y)]),
        _chain([(R, X_HEIGHT), (midx, cross_y), (midx - 50, DESCENT)]),
    ]
    terminals = [((L, X_HEIGHT), (midx, cross_y)), ((R, X_HEIGHT), (midx, cross_y))]
    return shapes, 480, terminals


def glyph_z_lc(L=70, R=410):
    shape = _chain([(L, X_HEIGHT), (R, X_HEIGHT), (L, BASE), (R, BASE)])
    # Free bar ends only, as in Z -- with all four declared, the serifs on
    # z's short bars merged into a solid block.
    terminals = [((L, X_HEIGHT), (R, X_HEIGHT)), ((R, BASE), (L, BASE))]
    return [shape], 480, terminals


def glyph_k_lc(L=70, R=400):
    joint_y = 260
    shapes = [
        _chain([(L, BASE), (L, CAP)]),
        _chain([(L, joint_y), (R, X_HEIGHT)]),
        _chain([(L, joint_y), (R, BASE)]),
    ]
    terminals = [
        ((L, BASE), (L, CAP)),
        ((L, CAP), (L, BASE)),
        ((R, X_HEIGHT), (L, joint_y)),
        ((R, BASE), (L, joint_y)),
    ]
    return shapes, 460, terminals


def glyph_i_lc():
    x = 170
    dot_cy = X_HEIGHT + 155
    shapes = [_chain([(x, BASE), (x, X_HEIGHT)]), disc(x, dot_cy, 45)]
    terminals = [((x, BASE), (x, X_HEIGHT))]
    return shapes, 340, terminals


def glyph_j_lc():
    stem_x = 250
    hook_r = 110
    hook_cy = DESCENT + hook_r
    dot_cy = X_HEIGHT + 155
    shapes = [
        *_hook(stem_x, X_HEIGHT, hook_r, hook_cy),
        disc(stem_x, dot_cy, 45),
    ]
    return shapes, 460, []


def glyph_l_lc():
    x = 170
    terminals = [((x, BASE), (x, CAP)), ((x, CAP), (x, BASE))]
    return [_chain([(x, BASE), (x, CAP)])], 340, terminals


def glyph_t_lc():
    stem_x = 170
    top = 600
    shapes = [
        _chain([(stem_x, BASE), (stem_x, top)]),
        _chain([(stem_x - 90, X_HEIGHT), (stem_x + 90, X_HEIGHT)]),
    ]
    # Only the foot gets a terminal: a serif on t's stem TOP (which stops
    # between x-height and cap, not on a guideline) read as a dagger.
    terminals = [((stem_x, BASE), (stem_x, top))]
    return shapes, 400, terminals


def glyph_f_lc():
    stem_x = 170
    hook_r = 140
    hook_cy = CAP - hook_r
    # Stem must reach the hook's top (hook_cy + hook_r), not just its arc
    # center, or the two pieces don't overlap. The hook stays in the upper
    # quadrant (25..100): sweeping on down to -15 made its free end droop
    # level with -- and nearly touch -- the crossbar, closing the letter
    # into a scythe.
    shapes = [
        _chain([(stem_x, BASE), (stem_x, hook_cy + hook_r)]),
        _bowl(stem_x, hook_cy, hook_r, 25, 100, cap_style="round"),
        _chain([(stem_x - 90, X_HEIGHT), (stem_x + 90, X_HEIGHT)]),
    ]
    terminals = [((stem_x, BASE), (stem_x, hook_cy))]
    return shapes, 400, terminals


# ---- registry ---------------------------------------------------------------

#: name -> () -> (shapes, advance_width, terminals). The raw, unfinalized
#: form both fonts build from -- `GLYPHS` below wraps these for the existing
#: (contours, advance) sans contract; fontgen/serifs.py consumes the raw
#: form directly to add feet before finalizing.
SKELETONS = {
    "A": glyph_A,
    "B": glyph_B,
    "C": glyph_C,
    "D": glyph_D,
    "E": glyph_E,
    "F": glyph_F,
    "G": glyph_G,
    "H": glyph_H,
    "I": glyph_I,
    "J": glyph_J,
    "K": glyph_K,
    "L": glyph_L,
    "M": glyph_M,
    "N": glyph_N,
    "O": glyph_O,
    "P": glyph_P,
    "Q": glyph_Q,
    "R": glyph_R,
    "S": glyph_S,
    "T": glyph_T,
    "U": glyph_U,
    "V": glyph_V,
    "W": glyph_W,
    "X": glyph_X,
    "Y": glyph_Y,
    "Z": glyph_Z,
    "a": glyph_a_lc,
    "b": glyph_b_lc,
    "c": glyph_c_lc,
    "d": glyph_d_lc,
    "e": glyph_e_lc,
    "f": glyph_f_lc,
    "g": glyph_g_lc,
    "h": glyph_h_lc,
    "i": glyph_i_lc,
    "j": glyph_j_lc,
    "k": glyph_k_lc,
    "l": glyph_l_lc,
    "m": glyph_m_lc,
    "n": glyph_n_lc,
    "o": glyph_o_lc,
    "p": glyph_p_lc,
    "q": glyph_q_lc,
    "r": glyph_r_lc,
    "s": glyph_s_lc,
    "t": glyph_t_lc,
    "u": glyph_u_lc,
    "v": glyph_v_lc,
    "w": glyph_w_lc,
    "x": glyph_x_lc,
    "y": glyph_y_lc,
    "z": glyph_z_lc,
    "zero": glyph_zero,
    "one": glyph_one,
    "two": glyph_two,
    "three": glyph_three,
    "four": glyph_four,
    "five": glyph_five,
    "six": glyph_six,
    "seven": glyph_seven,
    "eight": glyph_eight,
    "nine": glyph_nine,
    "space": glyph_space,
    "period": glyph_period,
    "comma": glyph_comma,
    "hyphen": glyph_hyphen,
    "colon": glyph_colon,
    "exclam": glyph_exclam,
    "question": glyph_question,
}


def _sans(fn):
    def build():
        shapes, advance, _terminals = fn()
        return finalize(shapes), advance

    return build


#: name -> () -> (contours, advance_width) -- the plain sans build, exactly
#: the contract every existing caller (tests, make_font.py, the jitter
#: script) already expects.
GLYPHS = {name: _sans(fn) for name, fn in SKELETONS.items()}

CMAP = {
    **{ord(c): c for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"},
    **{ord(c): c for c in "abcdefghijklmnopqrstuvwxyz"},
    **{
        ord(str(i)): name
        for i, name in enumerate(
            [
                "zero",
                "one",
                "two",
                "three",
                "four",
                "five",
                "six",
                "seven",
                "eight",
                "nine",
            ]
        )
    },
    ord(" "): "space",
    ord("."): "period",
    ord(","): "comma",
    ord("-"): "hyphen",
    ord(":"): "colon",
    ord("!"): "exclam",
    ord("?"): "question",
}
