"""Build the Aperture Sans family: five weights, upright and italic.

Regular lands at out/aperture-sans.ttf (the path the other tooling and
docs already know); every other style at out/aperture-sans-<style>.ttf.
"""

from fontgen.build import build_font, normalize_spacing
from fontgen.glyphs import CMAP
from fontgen.kerning import kern_feature, kern_pairs
from fontgen.metrics import CAP
from fontgen.primitives import finalize, rect
from fontgen.sans import (
    ITALIC_ANGLE,
    OPTICAL_TIGHTEN,
    WEIGHTS,
    bearing_scale,
    file_slug,
    make_glyphs,
    side_bearing,
    slant,
    style_name,
    styles,
)
from fontgen.spacing import apply_optical_bearings

FAMILY = "Aperture Sans"


def out_path(weight, italic):
    return f"out/aperture-sans{file_slug(weight, italic)}.ttf"


def build_style(weight, italic):
    glyphs = {".notdef": (finalize([rect(60, 0, 460, CAP)]), 520)}
    for name, fn in make_glyphs(weight).items():
        glyphs[name] = fn()
    glyphs = normalize_spacing(glyphs, side_bearing=side_bearing(weight))
    glyphs = apply_optical_bearings(
        glyphs, OPTICAL_TIGHTEN, scale=bearing_scale(weight)
    )
    pairs = kern_pairs(glyphs)
    if italic:
        glyphs = slant(glyphs)
    path = out_path(weight, italic)
    build_font(
        glyphs,
        CMAP,
        FAMILY,
        style_name(weight, italic),
        path,
        features=kern_feature(pairs),
        weight_class=WEIGHTS[weight][1],
        italic_angle=ITALIC_ANGLE if italic else 0.0,
    )
    print(f"built {path} with {len(glyphs)} glyphs, {len(pairs)} kern pairs")


def main():
    for weight, italic in styles():
        build_style(weight, italic)


if __name__ == "__main__":
    main()
