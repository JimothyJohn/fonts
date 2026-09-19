from fontgen.build import build_font, normalize_spacing
from fontgen.glyphs import CMAP, SKELETONS
from fontgen.hand import NUM_VARIANTS, _rng, feature_code, hand_contours
from fontgen.metrics import CAP
from fontgen.primitives import finalize, rect
from fontgen.script import body_bounds, script_strokes

FAMILY = "Aperture Hand"
STYLE = "Regular"
OUT = "out/aperture-hand.ttf"
SIDE_BEARING = 45


def main():
    glyphs = {".notdef": (finalize([rect(60, 0, 460, CAP)]), 520)}
    varying = []
    bounds = {}
    for name, fn in SKELETONS.items():
        strokes = script_strokes(name, fn, bow=True)
        _, advance, _terminals = fn()
        body = body_bounds(strokes)
        for v in range(NUM_VARIANTS):
            contours = hand_contours(strokes, _rng(name, v))
            glyph_name = name if v == 0 else f"{name}.alt{v}"
            glyphs[glyph_name] = (contours, advance)
            if body is not None:
                bounds[glyph_name] = body
        if strokes:
            varying.append(name)

    # Bearings come from each letter's body so the exit tail overshoots
    # the advance onto the next letter (as in the script face).
    glyphs = normalize_spacing(glyphs, side_bearing=SIDE_BEARING, spacing_bounds=bounds)

    build_font(glyphs, CMAP, FAMILY, STYLE, OUT, features=feature_code(varying))
    print(
        f"built {OUT} with {len(glyphs)} glyphs ({len(varying)} x{NUM_VARIANTS} variants)"
    )


if __name__ == "__main__":
    main()
