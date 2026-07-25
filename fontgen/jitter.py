"""Per-glyph jitter for building near-identical font variants.

The idea: build N TTFs that share identical glyph order, cmap, and advance
widths (so swapping @font-face between them mid-paragraph causes zero
reflow), but where each glyph's ink has small, deterministic random
variation baked in -- not just tilt and position, but stroke weight and
width/height too. Cycling a page's font-family across variants at a
typewriter-strike cadence then reads as mechanical wobble rather than a
font change.

The deeper shape parameters (STROKE, BOWL_WIDTH_RATIO, etc.) are baked in
at *generation time* as default-argument values across every glyph
function in glyphs.py -- genuinely re-deriving each glyph with a different
stroke width per variant would mean threading a parameters object through
the whole pipeline. Instead this operates after the fact, directly on the
finalized geometry, using operations that correspond to the same physical
properties:

- stroke weight -> a morphological offset (Shapely buffer) on the actual
  filled shape, which thickens or thins ink and correspondingly shrinks or
  grows counters, just like a heavier or lighter keystrike would.
- width/height -> anisotropic scale, which also perturbs how round arcs
  and bowls read (a circle scaled unevenly becomes a slightly eccentric
  ellipse) without needing to touch the arc-generation math at all.
"""

import math
import random

from fontgen.build import GlyphSpec
from fontgen.primitives import Point, contours_to_polygon, polygon_to_contours


def jitter_contours(
    contours: list[list[Point]],
    seed: int,
    max_rotation_deg: float = 1.4,
    max_dx: float = 9.0,
    max_dy: float = 6.0,
    max_scale_x: float = 0.045,
    max_scale_y: float = 0.035,
    max_stroke_delta: float = 5.0,
) -> list[list[Point]]:
    """Jitter a glyph's contours: stroke weight, width, height, rotation,
    and position, all deterministic for a given seed. Kept small enough
    relative to side bearings that neighboring glyphs never visually
    collide.
    """
    if not contours:
        return contours
    rng = random.Random(seed)

    stroke_delta = rng.uniform(-max_stroke_delta, max_stroke_delta)
    if stroke_delta:
        polygon = contours_to_polygon(contours)
        if not polygon.is_empty:
            buffered = polygon.buffer(stroke_delta, join_style="round")
            if not buffered.is_empty:
                contours = polygon_to_contours(buffered)

    angle = math.radians(rng.uniform(-max_rotation_deg, max_rotation_deg))
    dx = rng.uniform(-max_dx, max_dx)
    dy = rng.uniform(-max_dy, max_dy)
    scale_x = 1 + rng.uniform(-max_scale_x, max_scale_x)
    scale_y = 1 + rng.uniform(-max_scale_y, max_scale_y)
    cos_a, sin_a = math.cos(angle), math.sin(angle)

    xs = [x for c in contours for x, _ in c]
    ys = [y for c in contours for _, y in c]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2

    jittered = []
    for contour in contours:
        new_contour = []
        for x, y in contour:
            ox, oy = (x - cx) * scale_x, (y - cy) * scale_y
            rx = ox * cos_a - oy * sin_a
            ry = ox * sin_a + oy * cos_a
            new_contour.append((rx + cx + dx, ry + cy + dy))
        jittered.append(new_contour)
    return jittered


def jitter_glyph_set(
    glyphs: dict[str, GlyphSpec], variant_seed: int
) -> dict[str, GlyphSpec]:
    """Apply jitter_contours to every glyph in a set, keyed so each glyph
    name gets its own stable-but-distinct seed within the variant (glyphs
    don't all jitter identically) while staying deterministic across runs.
    Advance widths are passed through unchanged.
    """
    out = {}
    for name, (contours, advance) in glyphs.items():
        glyph_seed = hash((variant_seed, name)) & 0xFFFFFFFF
        out[name] = (jitter_contours(contours, glyph_seed), advance)
    return out
