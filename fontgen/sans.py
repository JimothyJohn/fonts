"""Aperture Sans as a family: five weights, each upright and oblique.

The Regular sans is the skeletons in fontgen.glyphs inked as written --
each centerline swept by a round pen of width STROKE. Every other member
of the family is the SAME skeleton, re-inked: the recorded centerlines
(fontgen.primitives.record_strokes, the replay mechanism the serif,
script and hand faces already build on) are swept again with a pen
scaled to that weight's stroke, then, for the obliques, sheared about the
baseline. Nothing about a letter's construction is duplicated per
weight, so a skeleton fix lands in all ten styles at once.

Two things the pen alone doesn't settle:

- Spacing scales with weight. A heavier stroke wants tighter bearings
  (the counters are already tighter), a lighter one more air; each
  weight's bearing is the Regular's scaled by sqrt(STROKE / stroke), and
  the optical tucks for rounds/diagonals scale the same way.
- The obliques are true slanted romans, the geometric-sans convention
  (Futura, Century Gothic): no redrawn single-storey forms, just the
  upright letters leaned ITALIC_ANGLE degrees, sheared about y=0 so
  everything on the baseline stays put -- after spacing and kerning, so
  they keep the upright's advances and pairs.
"""

import inspect
import math

from shapely import affinity
from shapely.geometry import LinearRing, LineString

from fontgen.glyphs import SKELETONS
from fontgen.metrics import SIDE_BEARING, STROKE
from fontgen.primitives import (
    CURVE_SEGMENTS,
    contours_to_polygon,
    polygon_to_contours,
    record_strokes,
    union_all,
)

#: style -> (round-pen stroke width, OS/2 usWeightClass).
WEIGHTS = {
    "Light": (50, 300),
    "Regular": (STROKE, 400),
    "Medium": (96, 500),
    "Bold": (120, 700),
    "Black": (150, 900),
}

ITALIC_ANGLE = 12.0

#: Optical side-bearing tucks at Regular weight (see fontgen.spacing);
#: scaled with each weight's bearing.
OPTICAL_TIGHTEN = {
    "O": (12, 12),
    "Q": (12, 12),
    "C": (12, 6),
    "G": (12, 6),
    "D": (0, 12),
    "S": (6, 6),
    "J": (8, 0),
    "L": (0, 12),
    "P": (0, 6),
    "F": (0, 8),
    "A": (14, 14),
    "V": (14, 14),
    "W": (14, 14),
    "X": (8, 8),
    "Y": (14, 14),
    "T": (16, 16),
    "o": (12, 12),
    "c": (12, 6),
    "e": (12, 6),
    "a": (12, 0),
    "b": (0, 12),
    "d": (12, 0),
    "p": (0, 12),
    "q": (12, 0),
    "g": (12, 0),
    "s": (6, 6),
    "f": (4, 6),
    "t": (4, 6),
    "r": (0, 8),
    "j": (6, 0),
    "v": (14, 14),
    "w": (14, 14),
    "x": (8, 8),
    "y": (14, 8),
    "zero": (12, 12),
    "two": (8, 6),
    "three": (8, 10),
    "four": (10, 4),
    "five": (6, 8),
    "six": (10, 8),
    "seven": (6, 14),
    "eight": (10, 10),
    "nine": (8, 10),
}


def styles():
    """Every (weight, italic) pair in the family, Regular first."""
    return [(w, it) for w in WEIGHTS for it in (False, True)]


def style_name(weight, italic):
    if weight == "Regular":
        return "Italic" if italic else "Regular"
    return f"{weight} Italic" if italic else weight


def file_slug(weight, italic):
    """out/aperture-sans[-<style>].ttf -- Regular keeps the bare name."""
    name = style_name(weight, italic)
    return "" if name == "Regular" else "-" + name.lower().replace(" ", "-")


def side_bearing(weight):
    stroke, _ = WEIGHTS[weight]
    return round(SIDE_BEARING * math.sqrt(STROKE / stroke))


def bearing_scale(weight):
    return side_bearing(weight) / SIDE_BEARING


def _ink(strokes, width_scale):
    quad_segs = max(2, CURVE_SEGMENTS // 4)
    shapes = []
    for s in strokes:
        pts, closed = s["pts"], s["closed"]
        line = LinearRing(pts) if closed else LineString(pts)
        shapes.append(
            line.buffer(
                s["width"] * width_scale / 2,
                quad_segs=quad_segs,
                cap_style="round",
                join_style="round",
            )
        )
    return union_all(shapes)


def make_glyphs(weight="Regular"):
    """name -> () -> (contours, advance) for one weight's UPRIGHT -- the
    same contract fontgen.glyphs.GLYPHS honors for the Regular. Obliques
    come from `slant`, applied after spacing."""
    stroke, _ = WEIGHTS[weight]
    k = stroke / STROKE

    def build(fn):
        pen_aware = "pen" in inspect.signature(fn).parameters

        def glyph():
            with record_strokes() as strokes:
                _shapes, advance, _terminals = fn(pen=stroke) if pen_aware else fn()
            return polygon_to_contours(_ink(strokes, k)), advance

        return glyph

    return {name: build(fn) for name, fn in SKELETONS.items()}


def slant(glyphs):
    """The oblique of a spaced {name: (contours, advance)} set: every
    contour sheared ITALIC_ANGLE about the baseline, advances untouched.
    Spacing is settled on the upright first because a sheared glyph's
    bounding box is the slant's worth wider than its ink at any one
    height; measuring bearings on it would pad every advance by that."""
    slanted = {}
    for name, (contours, advance) in glyphs.items():
        if not contours:
            slanted[name] = (contours, advance)
            continue
        geom = affinity.skew(
            contours_to_polygon(contours), xs=ITALIC_ANGLE, origin=(0.0, 0.0)
        )
        slanted[name] = (polygon_to_contours(geom), advance)
    return slanted
