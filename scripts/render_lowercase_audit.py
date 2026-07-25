"""Diagnostic sheet: every lowercase letter drawn large in each face
(sans contours, script contours, one hand variant), rendered directly
from the geometry so problems are visible at design size.
"""

import string

from PIL import Image, ImageDraw

from fontgen.glyphs import GLYPHS, SKELETONS
from fontgen.hand import _rng, hand_contours
from fontgen.metrics import ASCENT, DESCENT
from fontgen.script import make_glyphs, script_strokes
from fontgen.primitives import signed_area

CELL = 260
SCALE = 0.22
OUT = "out/lowercase-audit.png"

SCRIPT_GLYPHS = make_glyphs(SKELETONS)


def draw_contours(draw, contours, ox, oy):
    shells = [c for c in contours if signed_area(c) < 0]
    holes = [c for c in contours if signed_area(c) >= 0]
    for c in shells:
        draw.polygon([(ox + x * SCALE, oy - y * SCALE) for x, y in c], fill="black")
    for c in holes:
        draw.polygon([(ox + x * SCALE, oy - y * SCALE) for x, y in c], fill="white")


def main():
    letters = string.ascii_lowercase
    cols = ["sans", "script", "hand"]
    width = 90 + len(cols) * CELL
    height = len(letters) * CELL
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)

    for row, ch in enumerate(letters):
        top = row * CELL
        baseline = top + CELL * (ASCENT / (ASCENT - DESCENT))
        draw.text((20, top + CELL / 2 - 10), ch, fill="black")
        for col_i in range(len(cols)):
            x0 = 90 + col_i * CELL
            draw.line([(x0, baseline), (x0 + CELL, baseline)], fill=(220, 220, 235))
            draw.line(
                [(x0, baseline - 480 * SCALE), (x0 + CELL, baseline - 480 * SCALE)],
                fill=(235, 235, 245),
            )
        sans, _ = GLYPHS[ch]()
        script, _ = SCRIPT_GLYPHS[ch]()
        hand = hand_contours(script_strokes(ch, SKELETONS[ch]), _rng(ch, 0))
        for col_i, contours in enumerate([sans, script, hand]):
            draw_contours(draw, contours, 90 + col_i * CELL + 20, baseline)

    img.save(OUT)
    print(f"saved {OUT}")


if __name__ == "__main__":
    main()
