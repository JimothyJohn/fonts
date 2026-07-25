from fontgen.build import build_font, normalize_spacing
from fontgen.glyphs import CMAP, SKELETONS
from fontgen.hand import NUM_VARIANTS, _rng, feature_code, hand_contours
from fontgen.metrics import CAP
from fontgen.primitives import finalize, rect
from fontgen.script import script_strokes

FAMILY = "Aperture Hand"
STYLE = "Regular"
OUT = "out/aperture-hand.ttf"
SIDE_BEARING = 45


def main():
    glyphs = {".notdef": (finalize([rect(60, 0, 460, CAP)]), 520)}
    varying = []
    for name, fn in SKELETONS.items():
        strokes = script_strokes(name, fn)
        _, advance, _terminals = fn()
        for v in range(NUM_VARIANTS):
            contours = hand_contours(strokes, _rng(name, v))
            glyph_name = name if v == 0 else f"{name}.alt{v}"
            glyphs[glyph_name] = (contours, advance)
        if strokes:
            varying.append(name)

    glyphs = normalize_spacing(glyphs, side_bearing=SIDE_BEARING)

    build_font(glyphs, CMAP, FAMILY, STYLE, OUT, features=feature_code(varying))
    print(
        f"built {OUT} with {len(glyphs)} glyphs ({len(varying)} x{NUM_VARIANTS} variants)"
    )


if __name__ == "__main__":
    main()
