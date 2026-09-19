"""One sheet for a whole family: every style on its own line, at text
size, so weight progression and the italic lean can be judged together.
"""

import sys

from PIL import Image, ImageDraw, ImageFont

from fontgen.sans import file_slug, style_name, styles

OUT_PATH = sys.argv[1] if len(sys.argv) > 1 else "out/family-sans.png"
TEXT = "The quick brown fox jumps over 42 lazy dogs. Hello, world!"


def main():
    size = 64
    line_height = int(size * 1.5)
    rows = styles()
    img = Image.new("RGB", (2100, line_height * len(rows) + 60), "white")
    draw = ImageDraw.Draw(img)
    for i, (weight, italic) in enumerate(rows):
        font = ImageFont.truetype(
            f"out/aperture-sans{file_slug(weight, italic)}.ttf", size
        )
        y = 30 + i * line_height
        draw.text(
            (40, y + size * 0.3), style_name(weight, italic), fill=(140, 140, 140)
        )
        draw.text((300, y), TEXT, font=font, fill="black")
    img.save(OUT_PATH)
    print(f"saved {OUT_PATH}")


if __name__ == "__main__":
    main()
