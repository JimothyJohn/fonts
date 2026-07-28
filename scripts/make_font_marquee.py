from fontgen.build import build_font, normalize_spacing
from fontgen.glyphs import CMAP, SKELETONS
from fontgen.marquee import make_glyphs
from fontgen.metrics import CAP
from fontgen.primitives import finalize, rect

FAMILY = "Aperture Marquee"
STYLE = "Regular"
OUT = "out/aperture-marquee.ttf"

# Bulb runs read airier than solid strokes; keep letters a bit closer
# than the sans so words still group.
SIDE_BEARING = 58


def main():
    glyphs = {".notdef": (finalize([rect(60, 0, 460, CAP)]), 520)}
    for name, fn in make_glyphs(SKELETONS).items():
        glyphs[name] = fn()
    glyphs = normalize_spacing(glyphs, side_bearing=SIDE_BEARING)

    build_font(glyphs, CMAP, FAMILY, STYLE, OUT)
    print(f"built {OUT} with {len(glyphs)} glyphs")


if __name__ == "__main__":
    main()
