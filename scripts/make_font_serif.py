from fontgen.build import build_font, normalize_spacing
from fontgen.glyphs import CMAP
from fontgen.glyphs_serif import GLYPHS
from fontgen.metrics import CAP
from fontgen.primitives import finalize, rect

FAMILY = "Aperture Serif"
STYLE = "Regular"
OUT = "out/aperture-serif.ttf"

# Optical side-bearing corrections, applied AFTER normalize_spacing's
# uniform pass. normalize_spacing gives every glyph identical bearings
# measured from its ink extremes -- correct for seriffed flats, whose
# feet present a full-height edge, but rounds touch that extreme at a
# single mid-height point and diagonals/T-shapes are mostly air at their
# widest, so both read as gappy at uniform bearings. Values are
# (left, right) units to TIGHTEN each side; classic ratios: rounds tuck
# ~a fifth of a bearing, open diagonals a bit more, T most of all.
OPTICAL_TIGHTEN = {
    "O": (14, 14),
    "Q": (14, 14),
    "C": (14, 8),
    "G": (14, 6),
    "D": (0, 14),
    "S": (8, 8),
    "J": (10, 0),
    "L": (0, 12),
    "P": (0, 8),
    "F": (0, 8),
    "A": (16, 16),
    "V": (16, 16),
    "W": (16, 16),
    "X": (10, 10),
    "Y": (16, 16),
    "T": (18, 18),
    "o": (14, 14),
    "c": (14, 8),
    "e": (14, 8),
    "a": (14, 0),
    "b": (0, 14),
    "d": (14, 0),
    "p": (0, 14),
    "q": (14, 0),
    "g": (14, 0),
    "s": (8, 8),
    "f": (4, 6),
    "t": (4, 6),
    "r": (0, 8),
    "j": (8, 0),
    "v": (16, 16),
    "w": (16, 16),
    "x": (10, 10),
    "y": (16, 10),
    "zero": (14, 14),
    "two": (10, 6),
    "three": (10, 12),
    "four": (12, 4),
    "five": (8, 10),
    "six": (12, 10),
    "seven": (8, 16),
    "eight": (12, 12),
    "nine": (10, 12),
}


def apply_optical_bearings(glyphs):
    adjusted = {}
    for name, (contours, advance) in glyphs.items():
        dl, dr = OPTICAL_TIGHTEN.get(name, (0, 0))
        if not contours or (dl == 0 and dr == 0):
            adjusted[name] = (contours, advance)
            continue
        shifted = [[(x - dl, y) for x, y in contour] for contour in contours]
        adjusted[name] = (shifted, advance - dl - dr)
    return adjusted


def main():
    glyphs = {".notdef": (finalize([rect(60, 0, 460, CAP)]), 520)}
    for name, fn in GLYPHS.items():
        glyphs[name] = fn()
    glyphs = apply_optical_bearings(normalize_spacing(glyphs))

    build_font(glyphs, CMAP, FAMILY, STYLE, OUT)
    print(f"built {OUT} with {len(glyphs)} glyphs")


if __name__ == "__main__":
    main()
