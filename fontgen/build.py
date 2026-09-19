"""Assemble a TTF from glyph contours using fontTools' low-level FontBuilder API."""

import calendar

from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.fontBuilder import FontBuilder
from fontTools.misc.timeTools import epoch_diff
from fontTools.pens.ttGlyphPen import TTGlyphPen

from fontgen.metrics import ASCENT, CAP, DESCENT, SIDE_BEARING, UPM, X_HEIGHT
from fontgen.primitives import Point

#: head.created/modified for every build (seconds since the 1904 Mac
#: epoch): a fixed date instead of "now", so the same source produces the
#: same bytes.
BUILD_TIMESTAMP = calendar.timegm((2026, 1, 1, 0, 0, 0)) - epoch_diff

GlyphSpec = tuple[list[list[Point]], float]  # (contours, advance_width)


def normalize_spacing(
    glyphs: dict[str, GlyphSpec], side_bearing: float = SIDE_BEARING
) -> dict[str, GlyphSpec]:
    """Force every glyph to the same left/right side bearing, regardless of
    whatever ad hoc coordinates its contours were authored with.

    Each glyph's ink is shifted so its leftmost point sits at exactly
    `side_bearing`, and its advance width is set to ink_width + 2 *
    side_bearing. This is what keeps inter-letter spacing visually even
    without hand-tuning every glyph's bounds. Glyphs with no ink (e.g.
    "space") are left untouched.
    """
    normalized = {}
    for name, (contours, advance) in glyphs.items():
        if not contours:
            normalized[name] = (contours, advance)
            continue
        xs = [x for contour in contours for x, _ in contour]
        x_min, x_max = min(xs), max(xs)
        shift = side_bearing - x_min
        shifted = [[(x + shift, y) for x, y in contour] for contour in contours]
        new_advance = (x_max - x_min) + 2 * side_bearing
        normalized[name] = (shifted, new_advance)
    return normalized


def _draw_glyph(contours: list[list[Point]]):
    pen = TTGlyphPen(None)
    for contour in contours:
        if not contour:
            continue
        pen.moveTo(contour[0])
        for pt in contour[1:]:
            pen.lineTo(pt)
        pen.closePath()
    return pen.glyph()


def legacy_names(family_name: str, style_name: str) -> tuple[str, str]:
    """The name-table's legacy family/subfamily (IDs 1/2) can only express
    Regular, Bold, Italic and Bold Italic. Any other weight folds into the
    family name ("Aperture Sans Light" / "Italic") so old-style menus
    still group and style-link it; IDs 16/17 carry the real family and
    full subfamily for everything modern."""
    words = style_name.split()
    italic = "Italic" in words
    weight = " ".join(w for w in words if w != "Italic") or "Regular"
    if weight in ("Regular", "Bold"):
        return family_name, style_name or "Regular"
    return f"{family_name} {weight}", "Italic" if italic else "Regular"


def build_font(
    glyphs: dict[str, GlyphSpec],
    cmap: dict[int, str],
    family_name: str,
    style_name: str,
    out_path: str,
    features: str | None = None,
    weight_class: int = 400,
    italic_angle: float = 0.0,
) -> None:
    glyph_order = [".notdef"] + [n for n in glyphs if n != ".notdef"]

    fb = FontBuilder(unitsPerEm=UPM, isTTF=True)
    fb.setupGlyphOrder(glyph_order)
    fb.setupCharacterMap(cmap)

    ttglyphs = {name: _draw_glyph(contours) for name, (contours, _) in glyphs.items()}
    fb.setupGlyf(ttglyphs)

    metrics = {}
    for name, (_, advance) in glyphs.items():
        glyph = ttglyphs[name]
        lsb = glyph.xMin if glyph.numberOfContours else 0
        metrics[name] = (round(advance), lsb)
    fb.setupHorizontalMetrics(metrics)

    fb.setupHorizontalHeader(ascent=ASCENT, descent=DESCENT)
    ps_name = f"{family_name}-{style_name}".replace(" ", "")
    full_name = f"{family_name} {style_name}"
    legacy_family, legacy_style = legacy_names(family_name, style_name)
    fb.setupNameTable(
        {
            "familyName": legacy_family,
            "styleName": legacy_style,
            "uniqueFontIdentifier": f"1.000;{ps_name}",
            "fullName": full_name,
            "version": "Version 1.000",
            "psName": ps_name,
            "typographicFamily": family_name,
            "typographicSubfamily": style_name,
        }
    )
    is_bold = legacy_style in ("Bold", "Bold Italic")
    is_italic = "Italic" in style_name
    # fsSelection's REGULAR bit (0x40) must be set whenever neither bold nor
    # italic is -- leaving it unset (as fontTools' default does) is what
    # macOS's strict font validator flags as a malformed name/style pairing.
    fs_selection = (0x20 if is_bold else 0) | (0x01 if is_italic else 0)
    if not is_bold and not is_italic:
        fs_selection |= 0x40
    fb.setupOS2(
        sTypoAscender=ASCENT,
        sTypoDescender=DESCENT,
        sTypoLineGap=0,
        usWinAscent=ASCENT,
        usWinDescent=-DESCENT,
        sCapHeight=round(CAP),
        sxHeight=round(X_HEIGHT),
        usWeightClass=weight_class,
        fsSelection=fs_selection,
    )
    # updateHead, not setupHead: the latter re-initializes the whole table
    # (glyph bounds, unitsPerEm) from defaults. Pinned timestamps keep the
    # build byte-identical from run to run.
    fb.updateHead(
        macStyle=(0x01 if is_bold else 0) | (0x02 if is_italic else 0),
        created=BUILD_TIMESTAMP,
        modified=BUILD_TIMESTAMP,
    )
    fb.setupPost(italicAngle=-italic_angle)

    if features is not None:
        addOpenTypeFeaturesFromString(fb.font, features)

    fb.save(out_path)
