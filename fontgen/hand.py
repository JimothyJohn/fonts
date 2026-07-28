"""Aperture Hand: a genuinely handwritten-looking face, built ground-up
around how a pen actually behaves rather than how outlines are usually
drawn.

Three layers separate this from the script face's tidy geometry:

1. Variable-pressure ink. Strokes are not buffered at constant width:
   each pen path is resampled densely and inked as a chain of discs
   whose radius follows a pressure model -- heavier on downstrokes,
   lighter on upstrokes (how a right-handed pen loads the nib), tapered
   in and out at stroke ends (pen landing and lifting), with a slow
   pressure drift along the path. No two millimeters of a stroke have
   exactly the same weight.

2. Hand wobble. Every path is displaced by two low-frequency harmonics
   plus a fine tremor, perpendicular to travel -- closed loops use
   whole-period harmonics so the seam stays smooth. On top, each
   variant of each glyph gets its own tilt, x/y squash, extra shear,
   and baseline drift, so letters sit on the line the way handwriting
   does: not quite.

3. Per-occurrence variation. Every glyph is generated NUM_VARIANTS
   times from different deterministic seeds and wired up with an
   OpenType calt cycle (see feature_code), so consecutive occurrences
   of the same letter come out as different drawings in any
   shaping-aware renderer (macOS, browsers, ...) -- the font never
   repeats itself locally.

The pen paths come from the script face (loops, exit tails, slant), so
Hand reads as cursive; everything downstream of the path is new.
"""

import itertools
import math
import random
import zlib

from shapely import geometry as sg
from shapely.ops import unary_union

from fontgen.primitives import Point, polygon_to_contours

NUM_VARIANTS = 3

# Path sampling / ink
STEP = 13  # resample spacing along the pen path, font units
MIN_INK_WIDTH = 24
DOT_LENGTH = 40  # paths shorter than this are inked as a single dot

# Pressure model
DOWN_BIAS = 0.11  # downstrokes heavier, upstrokes lighter, by this fraction
TAPER_LEN = 70  # entry/exit taper distance
TAPER_FLOOR = 0.62  # pen-down / pen-up width fraction at the very tip
DRIFT_AMP = 0.07  # slow pressure drift amplitude
DRIFT_WAVELENGTH = 320

# Wobble model
WOBBLE_WAVELENGTH = (260, 520)
WOBBLE_AMP = (3.5, 8.0)
TREMOR_WAVELENGTH = 48
TREMOR_AMP = 1.6

# Per-variant frame jiggle
MAX_TILT_DEG = 1.4
MAX_SQUASH = 0.035
MAX_EXTRA_SHEAR = 0.014
MAX_BASELINE_DRIFT = 10.0


def _rng(name: str, variant: int) -> random.Random:
    return random.Random(zlib.crc32(f"{name}/{variant}".encode()))


def _resample(pts: list[Point], step: float) -> tuple[list[Point], list[float], float]:
    """Even-arclength resampling of a polyline: points, their arclength
    positions, and the total length."""
    lengths = [
        math.hypot(x1 - x0, y1 - y0) for (x0, y0), (x1, y1) in itertools.pairwise(pts)
    ]
    total = sum(lengths)
    if total == 0:
        return [pts[0]], [0.0], 0.0
    out_pts, out_s = [], []
    n = max(2, round(total / step))
    targets = [total * i / n for i in range(n + 1)]
    seg = 0
    seg_start = 0.0
    for s in targets:
        while seg < len(lengths) - 1 and s > seg_start + lengths[seg]:
            seg_start += lengths[seg]
            seg += 1
        seg_len = lengths[seg] or 1.0
        t = min(1.0, max(0.0, (s - seg_start) / seg_len))
        (x0, y0), (x1, y1) = pts[seg], pts[seg + 1]
        out_pts.append((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t))
        out_s.append(s)
    return out_pts, out_s, total


def _tangents(pts: list[Point], closed: bool) -> list[Point]:
    n = len(pts)
    out = []
    for i in range(n):
        if closed:
            a, b = pts[(i - 1) % n], pts[(i + 1) % n]
        else:
            a, b = pts[max(0, i - 1)], pts[min(n - 1, i + 1)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        d = math.hypot(dx, dy) or 1.0
        out.append((dx / d, dy / d))
    return out


def _wobble(
    pts: list[Point], s: list[float], total: float, closed: bool, rng: random.Random
) -> list[Point]:
    """Perpendicular displacement: two low-frequency harmonics plus a
    fine tremor. Closed paths snap each harmonic to a whole number of
    periods so the displacement is continuous across the seam."""
    waves = []
    for _ in range(2):
        wavelength = rng.uniform(*WOBBLE_WAVELENGTH)
        amp = rng.uniform(*WOBBLE_AMP)
        phase = rng.uniform(0, 2 * math.pi)
        waves.append((wavelength, amp, phase))
    waves.append((TREMOR_WAVELENGTH, TREMOR_AMP, rng.uniform(0, 2 * math.pi)))

    tangents = _tangents(pts, closed)
    out = []
    for p, si, (tx, ty) in zip(pts, s, tangents):
        d = 0.0
        for wavelength, amp, phase in waves:
            if closed and total > 0:
                periods = max(1, round(total / wavelength))
                d += amp * math.sin(2 * math.pi * periods * si / total + phase)
            else:
                d += amp * math.sin(2 * math.pi * si / wavelength + phase)
        out.append((p[0] - ty * d, p[1] + tx * d))
    return out


def _pressure_widths(
    base: float,
    s: list[float],
    total: float,
    tangents: list[Point],
    closed: bool,
    rng: random.Random,
) -> list[float]:
    drift_phase = rng.uniform(0, 2 * math.pi)
    out = []
    for si, (_, ty) in zip(s, tangents):
        f = 1.0 + DOWN_BIAS * (-ty)  # pen travelling down presses harder
        if not closed:
            edge = min(si, total - si)
            t = min(1.0, edge / TAPER_LEN)
            smooth = t * t * (3 - 2 * t)
            f *= TAPER_FLOOR + (1 - TAPER_FLOOR) * smooth
        if closed and total > 0:
            periods = max(1, round(total / DRIFT_WAVELENGTH))
            f *= 1.0 + DRIFT_AMP * math.sin(
                2 * math.pi * periods * si / total + drift_phase
            )
        else:
            f *= 1.0 + DRIFT_AMP * math.sin(
                2 * math.pi * si / DRIFT_WAVELENGTH + drift_phase
            )
        out.append(max(MIN_INK_WIDTH, base * f))
    return out


def _frame_jiggle(strokes: list[dict], rng: random.Random) -> list[dict]:
    """The whole letter's frame moves a little: tilt, squash, extra
    shear, baseline drift -- each variant sits on the line differently."""
    all_pts = [p for s in strokes for p in s["pts"]]
    xs = [x for x, _ in all_pts]
    ys = [y for _, y in all_pts]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    angle = math.radians(rng.uniform(-MAX_TILT_DEG, MAX_TILT_DEG))
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    sx = 1 + rng.uniform(-MAX_SQUASH, MAX_SQUASH)
    sy = 1 + rng.uniform(-MAX_SQUASH, MAX_SQUASH)
    shear = rng.uniform(-MAX_EXTRA_SHEAR, MAX_EXTRA_SHEAR)
    dy = rng.uniform(-MAX_BASELINE_DRIFT, MAX_BASELINE_DRIFT)

    def xf(p: Point) -> Point:
        ox, oy = (p[0] - cx) * sx, (p[1] - cy) * sy
        rx = ox * cos_a - oy * sin_a
        ry = ox * sin_a + oy * cos_a
        return (rx + cx + shear * (ry + cy), ry + cy + dy)

    return [{**s, "pts": [xf(p) for p in s["pts"]]} for s in strokes]


def _ink_stroke(s: dict, rng: random.Random):
    pts = s["pts"]
    if s["closed"]:
        pts = pts if pts[0] == pts[-1] else pts + [pts[0]]
    rpts, arcs, total = _resample(pts, STEP)
    if total < DOT_LENGTH:
        mx = sum(x for x, _ in pts) / len(pts)
        my = sum(y for _, y in pts) / len(pts)
        return sg.Point(mx, my).buffer(s["width"] / 2, quad_segs=8)
    rpts = _wobble(rpts, arcs, total, s["closed"], rng)
    tangents = _tangents(rpts, s["closed"])
    widths = _pressure_widths(s["width"], arcs, total, tangents, s["closed"], rng)
    return unary_union(
        [sg.Point(x, y).buffer(w / 2, quad_segs=8) for (x, y), w in zip(rpts, widths)]
    )


def feature_code(names: list[str]) -> str:
    """The calt cycle that makes consecutive letters differ. Rules read:
    after a default-set glyph comes an alt1, after an alt1 comes an
    alt2, and after an alt2 nothing matches so the run restarts at the
    default -- a 3-cycle over any stretch of text. Any glyph outside
    the classes (space, punctuation gaps) resets the cycle, which is
    fine: what matters is neighbors never repeating a drawing."""
    set0 = " ".join(names)
    set1 = " ".join(f"{n}.alt1" for n in names)
    set2 = " ".join(f"{n}.alt2" for n in names)
    return (
        "languagesystem DFLT dflt;\n"
        "languagesystem latn dflt;\n"
        f"@HAND0 = [{set0}];\n"
        f"@HAND1 = [{set1}];\n"
        f"@HAND2 = [{set2}];\n"
        "feature calt {\n"
        "    sub @HAND0 @HAND0' by @HAND1;\n"
        "    sub @HAND1 @HAND0' by @HAND2;\n"
        "} calt;\n"
    )


def hand_contours(strokes: list[dict], rng: random.Random) -> list[list[Point]]:
    """One handwritten drawing of a glyph: frame jiggle, then each pen
    path wobbled and inked with variable pressure."""
    if not strokes:
        return []
    strokes = _frame_jiggle(strokes, rng)
    shape = unary_union([_ink_stroke(s, rng) for s in strokes]).simplify(1.2)
    return polygon_to_contours(shape)
