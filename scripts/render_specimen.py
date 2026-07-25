import sys

from PIL import Image, ImageDraw, ImageFont

FONT_PATH = sys.argv[1] if len(sys.argv) > 1 else "out/aperture-sans.ttf"
OUT_PATH = sys.argv[2] if len(sys.argv) > 2 else "out/specimen.png"

LINES = [
    "ABCDEFGHIJKLM",
    "NOPQRSTUVWXYZ",
    "abcdefghijklm",
    "nopqrstuvwxyz",
    "0123456789",
    "The quick brown fox",
    "jumps over 42 lazy dogs!",
    "Hello, world - why? yes:",
]


def main():
    size = 90
    font = ImageFont.truetype(FONT_PATH, size)
    line_height = int(size * 1.4)
    img = Image.new("RGB", (1500, line_height * len(LINES) + 60), "white")
    draw = ImageDraw.Draw(img)
    for i, line in enumerate(LINES):
        draw.text((40, 30 + i * line_height), line, font=font, fill="black")
    img.save(OUT_PATH)
    print(f"saved {OUT_PATH}")


if __name__ == "__main__":
    main()
