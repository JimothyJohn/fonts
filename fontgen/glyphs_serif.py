"""Serif variant of the glyph set.

This is intentionally thin: every letter's shape and every terminal that
should grow a foot are already declared once, in fontgen.glyphs.SKELETONS
(see that module's docstring for why terminals live there instead of
being re-derived here). All this module does is add a foot at each
declared terminal and finalize -- there is no per-letter serif logic left
to duplicate or drift out of sync with the sans build.
"""

from fontgen.glyphs import CMAP, SKELETONS
from fontgen.primitives import finalize
from fontgen.serifs import serif_foot


def _serif(fn):
    def build():
        shapes, advance, terminals = fn()
        feet = [serif_foot(point, toward) for point, toward in terminals]
        return finalize([*shapes, *feet]), advance

    return build


GLYPHS = {name: _serif(fn) for name, fn in SKELETONS.items()}

__all__ = ["GLYPHS", "CMAP"]
