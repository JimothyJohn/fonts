"""Export per-character pen strokes for the handwriting demo.

Replays every glyph function under primitives.record_strokes() to capture
the centerlines each glyph buffers its ink from, then shifts them by the
exact same offset normalize_spacing applies to the filled contours -- so
a stroke replay lines up 1:1 with how the built font spaces the same
character.
"""

from fontgen.build import normalize_spacing
from fontgen.glyphs import CMAP, GLYPHS
from fontgen.metrics import ASCENT, DESCENT, SIDE_BEARING, UPM
from fontgen.primitives import record_strokes

Stroke = dict  # {"pts": [(x, y), ...], "width": float, "closed": bool}


def glyph_strokes() -> dict[str, dict]:
    """name -> {"advance": float, "strokes": [Stroke, ...]}, with stroke
    coordinates already shifted to match normalize_spacing's side bearings.
    """
    recorded: dict[str, list[Stroke]] = {}
    glyphs = {}
    for name, fn in GLYPHS.items():
        with record_strokes() as strokes:
            glyphs[name] = fn()
        recorded[name] = strokes

    normalized = normalize_spacing(glyphs, side_bearing=SIDE_BEARING)

    out = {}
    for name, (contours, advance) in normalized.items():
        strokes = recorded[name]
        if contours:
            raw_contours, _ = glyphs[name]
            x_min = min(x for c in raw_contours for x, _ in c)
            shift = SIDE_BEARING - x_min
            strokes = [
                {**s, "pts": [(x + shift, y) for x, y in s["pts"]]} for s in strokes
            ]
        out[name] = {"advance": advance, "strokes": strokes}
    return out


def strokes_by_char() -> dict:
    """Character-keyed export ready for JSON: metrics plus, per typeable
    character, its advance width and ordered pen strokes (coordinates
    rounded to keep the payload small; y-up in font units).
    """
    by_name = glyph_strokes()
    chars = {}
    for codepoint, name in CMAP.items():
        spec = by_name[name]
        chars[chr(codepoint)] = {
            "advance": round(spec["advance"], 1),
            "strokes": [
                {
                    "w": round(s["width"], 1),
                    "closed": s["closed"],
                    "pts": [[round(x, 1), round(y, 1)] for x, y in s["pts"]],
                }
                for s in spec["strokes"]
            ],
        }
    return {
        "upm": UPM,
        "ascent": ASCENT,
        "descent": DESCENT,
        "chars": chars,
    }
