from fontgen.build import build_font, normalize_spacing
from fontgen.glyphs import CMAP
from fontgen.glyphs_serif import GLYPHS
from fontgen.metrics import CAP
from fontgen.primitives import finalize, rect

FAMILY = "Aperture Serif"
STYLE = "Regular"
OUT = "out/aperture-serif.ttf"


def main():
    glyphs = {".notdef": (finalize([rect(60, 0, 460, CAP)]), 520)}
    for name, fn in GLYPHS.items():
        glyphs[name] = fn()
    glyphs = normalize_spacing(glyphs)

    build_font(glyphs, CMAP, FAMILY, STYLE, OUT)
    print(f"built {OUT} with {len(glyphs)} glyphs")


if __name__ == "__main__":
    main()
