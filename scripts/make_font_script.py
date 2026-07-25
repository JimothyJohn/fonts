from fontgen.build import build_font, normalize_spacing
from fontgen.glyphs import CMAP, SKELETONS
from fontgen.metrics import CAP
from fontgen.primitives import finalize, rect
from fontgen.script import make_glyphs

FAMILY = "Aperture Script"
STYLE = "Regular"
OUT = "out/aperture-script.ttf"

# Tighter than the sans' 70: exit tails already reach into the letter
# gap, and cursive flow wants the next letter close.
SIDE_BEARING = 45


def main():
    glyphs = {".notdef": (finalize([rect(60, 0, 460, CAP)]), 520)}
    for name, fn in make_glyphs(SKELETONS).items():
        glyphs[name] = fn()
    glyphs = normalize_spacing(glyphs, side_bearing=SIDE_BEARING)

    build_font(glyphs, CMAP, FAMILY, STYLE, OUT)
    print(f"built {OUT} with {len(glyphs)} glyphs")


if __name__ == "__main__":
    main()
