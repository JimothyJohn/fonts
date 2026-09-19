"""Shared grid constants every glyph is drawn against."""

UPM = 1000
BASE = 0
CAP = 700
MID = CAP / 2
STROKE = 78
DESCENT = -200
ASCENT = 800

# Font-wide line metrics (hhea/OS2), shared by every face and weight so
# they all set on the same line. Roomier than the design lines above:
# the baseline is placed at the flats' INK (see build.normalize_baseline),
# which raises every glyph by half its pen, so the Black sans reaches
# CAP + 150 + overshoot at the top.
LINE_ASCENT = 900
LINE_DESCENT = -250

SIDE_BEARING = 70
OVERSHOOT = 14

# Lowercase grid. Ascenders (b, d, f, h, k, l, t) reach CAP, same as the
# capitals; descenders (g, j, p, q, y) reach DESCENT.
X_HEIGHT = 480
XMID = X_HEIGHT / 2
