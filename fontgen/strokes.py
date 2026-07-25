"""Export per-character pen strokes for the handwriting demo.

Two faces are exported, each as its own stroke set:

- sans: every glyph function replayed under primitives.record_strokes()
  to capture the centerlines its ink is buffered from;
- script: the script face's transformed strokes (loops, exit tails,
  slant) from fontgen.script.

Serif is deliberately absent: its feet are assembled as raw polygons,
not pen strokes, so a stroke replay would render footless stems. Hand
is absent because it IS the script strokes plus ink treatment the demo
applies its own way per stamp.

Each face's strokes are shifted by the exact same offset
normalize_spacing applies to that face's filled contours -- built with
the same side bearings as the corresponding font -- so a stroke replay
lines up 1:1 with how that font spaces the same character.
"""

from fontgen.build import normalize_spacing
from fontgen.glyphs import CMAP, GLYPHS, SKELETONS
from fontgen.metrics import ASCENT, DESCENT, SIDE_BEARING, UPM
from fontgen.primitives import finalize, record_strokes, stroke_union
from fontgen.script import script_strokes

Stroke = dict  # {"pts": [(x, y), ...], "width": float, "closed": bool}

SCRIPT_SIDE_BEARING = 45  # matches scripts/make_font_script.py


def _spaced(
    recorded: dict[str, list[Stroke]],
    glyphs: dict,
    side_bearing: float,
) -> dict[str, dict]:
    """Shift each glyph's strokes to match normalize_spacing's side
    bearings for the same contours; returns name -> {advance, strokes}."""
    normalized = normalize_spacing(glyphs, side_bearing=side_bearing)
    out = {}
    for name, (contours, advance) in normalized.items():
        strokes = recorded[name]
        if contours:
            raw_contours, _ = glyphs[name]
            x_min = min(x for c in raw_contours for x, _ in c)
            shift = side_bearing - x_min
            strokes = [
                {**s, "pts": [(x + shift, y) for x, y in s["pts"]]} for s in strokes
            ]
        out[name] = {"advance": advance, "strokes": strokes}
    return out


def glyph_strokes() -> dict[str, dict]:
    """The sans face: name -> {"advance", "strokes"}."""
    recorded, glyphs = {}, {}
    for name, fn in GLYPHS.items():
        with record_strokes() as strokes:
            glyphs[name] = fn()
        recorded[name] = strokes
    return _spaced(recorded, glyphs, SIDE_BEARING)


def script_glyph_strokes() -> dict[str, dict]:
    """The script face: same shape, from the transformed script strokes
    (buffered here exactly the way the script font builds its ink, so
    the spacing shift matches that font)."""
    recorded, glyphs = {}, {}
    for name, fn in SKELETONS.items():
        strokes = script_strokes(name, fn)
        recorded[name] = strokes
        shapes = [
            stroke_union([s["pts"]], s["width"], closed=s["closed"]) for s in strokes
        ]
        _, advance, _terminals = fn()
        glyphs[name] = (finalize(shapes), advance)
    return _spaced(recorded, glyphs, SCRIPT_SIDE_BEARING)


def _char_payload(by_name: dict[str, dict]) -> dict:
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
    return chars


def strokes_by_char() -> dict:
    """JSON-ready export: shared metrics plus one stroke set per face
    (coordinates rounded; y-up in font units)."""
    return {
        "upm": UPM,
        "ascent": ASCENT,
        "descent": DESCENT,
        "faces": {
            "sans": {"label": "Sans", "chars": _char_payload(glyph_strokes())},
            "script": {
                "label": "Script",
                "chars": _char_payload(script_glyph_strokes()),
            },
        },
    }
