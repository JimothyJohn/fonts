from fontgen.blackletter import make_glyphs
from fontgen.build import build_font, normalize_spacing
from fontgen.glyphs import CMAP, SKELETONS
from fontgen.metrics import CAP
from fontgen.primitives import finalize, rect

FAMILY = "Aperture Olde"
STYLE = "Regular"
OUT = "out/aperture-olde.ttf"

# Blackletter is set dense and dark -- the picket-fence texture needs
# the stems of neighboring letters close together.
SIDE_BEARING = 38


def main():
    glyphs = {".notdef": (finalize([rect(60, 0, 460, CAP)]), 520)}
    for name, fn in make_glyphs(SKELETONS).items():
        glyphs[name] = fn()
    glyphs = normalize_spacing(glyphs, side_bearing=SIDE_BEARING)

    build_font(glyphs, CMAP, FAMILY, STYLE, OUT)
    print(f"built {OUT} with {len(glyphs)} glyphs")


if __name__ == "__main__":
    main()
