"""Build N near-identical font variants with small per-glyph jitter baked
in. All variants share identical glyph order, cmap, and advance widths --
computed once from the unjittered base -- so swapping @font-face between
them causes zero layout reflow, only a wobble in the ink itself.
"""

import json
import os

from fontgen.build import build_font, normalize_spacing
from fontgen.glyphs import CMAP, GLYPHS
from fontgen.jitter import jitter_glyph_set
from fontgen.metrics import CAP
from fontgen.primitives import finalize, rect

FAMILY = "Aperture Sans Jitter"
OUT_DIR = "out/jitter"
NUM_VARIANTS = 10


def base_glyphs():
    glyphs = {".notdef": (finalize([rect(60, 0, 460, CAP)]), 520)}
    for name, fn in GLYPHS.items():
        glyphs[name] = fn()
    return normalize_spacing(glyphs)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    base = base_glyphs()

    for i in range(NUM_VARIANTS):
        variant = jitter_glyph_set(base, variant_seed=i)
        out_path = f"{OUT_DIR}/variant-{i}.ttf"
        build_font(variant, CMAP, FAMILY, f"Variant{i}", out_path)
        print(f"built {out_path}")

    manifest_path = f"{OUT_DIR}/manifest.json"
    with open(manifest_path, "w") as f:
        json.dump({"count": NUM_VARIANTS}, f)
    print(f"built {manifest_path}")


if __name__ == "__main__":
    main()
