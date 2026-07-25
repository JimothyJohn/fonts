"""Shared grid constants every glyph is drawn against."""

UPM = 1000
BASE = 0
CAP = 700
MID = CAP / 2
STROKE = 78
DESCENT = -200
ASCENT = 800

SIDE_BEARING = 70
OVERSHOOT = 14

# Lowercase grid. Ascenders (b, d, f, h, k, l, t) reach CAP, same as the
# capitals; descenders (g, j, p, q, y) reach DESCENT.
X_HEIGHT = 480
XMID = X_HEIGHT / 2
