import sys

from PIL import Image, ImageDraw, ImageFont

from fontgen.metrics import CAP, DESCENT, UPM, X_HEIGHT

FONT_PATH = sys.argv[1] if len(sys.argv) > 1 else "out/aperture-sans.ttf"
OUT_PATH = sys.argv[2] if len(sys.argv) > 2 else "out/alphabet.png"

ROWS = [
    "ABCDEFGHIJKLM",
    "NOPQRSTUVWXYZ",
    "abcdefghijklm",
    "nopqrstuvwxyz",
    "0123456789.,-",
    ":!?",
]

SIZE = 120
CELL = 130
LEFT_MARGIN = 30
GUIDES = {"cap": CAP, "x-height": X_HEIGHT, "baseline": 0, "descent": DESCENT}
GUIDE_COLOR = (225, 235, 250)
BASELINE_COLOR = (190, 190, 190)


def main():
    font = ImageFont.truetype(FONT_PATH, SIZE)
    px_per_unit = SIZE / UPM
    width = LEFT_MARGIN + max(len(r) for r in ROWS) * CELL + LEFT_MARGIN
    height = len(ROWS) * CELL + 40
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)

    for row_i, row in enumerate(ROWS):
        row_top = 20 + row_i * CELL
        baseline_y = row_top + CELL * 0.75
        for name, units in GUIDES.items():
            y = baseline_y - units * px_per_unit
            color = BASELINE_COLOR if name == "baseline" else GUIDE_COLOR
            draw.line([(LEFT_MARGIN, y), (width - LEFT_MARGIN, y)], fill=color)
        for col_i, ch in enumerate(row):
            cell_x = LEFT_MARGIN + col_i * CELL
            bbox = draw.textbbox((0, 0), ch, font=font)
            ink_width = bbox[2] - bbox[0]
            x = cell_x + (CELL - ink_width) / 2 - bbox[0]
            draw.text((x, baseline_y), ch, font=font, fill="black", anchor="ls")

    img.save(OUT_PATH)
    print(f"saved {OUT_PATH}")


if __name__ == "__main__":
    main()
