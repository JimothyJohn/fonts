"""One sheet for a whole family: every style on its own line, at text
size, so weight progression and the italic lean can be judged together.

Text is laid out here glyph by glyph from the font's own advances and
GPOS kern pairs (this PIL has no raqm, so its text layout can't apply
kerning itself); a second line per style shows the kerning-critical
pairs.
"""

import sys

from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont

from fontgen.glyphs import CMAP
from fontgen.kerning import kerning_from_font
from fontgen.metrics import UPM
from fontgen.sans import file_slug, style_name, styles

OUT_PATH = sys.argv[1] if len(sys.argv) > 1 else "out/family-sans.png"
TEXT = "The quick brown fox jumps over 42 lazy dogs. Hello, world!"
PAIRS = "AVAWAY LTa Ty To Tr Te P. F, r. y, 7. LY Vo Wa fo"


def draw_line(draw, font, tt, kern, x, y, text, size):
    scale = size / UPM
    hmtx = tt["hmtx"]
    prev = None
    for ch in text:
        name = CMAP.get(ord(ch))
        if name is None:
            continue
        if prev is not None:
            x += kern.get((prev, name), 0) * scale
        draw.text((x, y), ch, font=font, fill="black", anchor="ls")
        x += hmtx[name][0] * scale
        prev = name


def main():
    size = 60
    line_height = int(size * 1.35)
    rows = styles()
    img = Image.new("RGB", (2500, line_height * 2 * len(rows) + 60), "white")
    draw = ImageDraw.Draw(img)
    for i, (weight, italic) in enumerate(rows):
        path = f"out/aperture-sans{file_slug(weight, italic)}.ttf"
        font = ImageFont.truetype(path, size)
        tt = TTFont(path)
        kern = kerning_from_font(tt)
        y = 30 + i * 2 * line_height + size
        draw.text(
            (40, y - size * 0.6), style_name(weight, italic), fill=(140, 140, 140)
        )
        draw_line(draw, font, tt, kern, 300, y, TEXT, size)
        draw_line(draw, font, tt, kern, 300, y + line_height, PAIRS, size)
    img.save(OUT_PATH)
    print(f"saved {OUT_PATH}")


if __name__ == "__main__":
    main()
