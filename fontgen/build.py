"""Assemble a TTF from glyph contours using fontTools' low-level FontBuilder API."""

import calendar

from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.fontBuilder import FontBuilder
from fontTools.misc.timeTools import epoch_diff
from fontTools.pens.ttGlyphPen import TTGlyphPen

from fontgen.metrics import LINE_ASCENT, LINE_DESCENT, SIDE_BEARING, UPM
from fontgen.primitives import Point

#: head.created/modified for every build (seconds since the 1904 Mac
#: epoch): a fixed date instead of "now", so the same source produces the
#: same bytes.
BUILD_TIMESTAMP = calendar.timegm((2026, 1, 1, 0, 0, 0)) - epoch_diff

GlyphSpec = tuple[list[list[Point]], float]  # (contours, advance_width)


def normalize_spacing(
    glyphs: dict[str, GlyphSpec],
    side_bearing: float = SIDE_BEARING,
    spacing_bounds: dict[str, tuple[float, float]] | None = None,
) -> dict[str, GlyphSpec]:
    """Force every glyph to the same left/right side bearing, regardless of
    whatever ad hoc coordinates its contours were authored with.

    Each glyph's ink is shifted so its leftmost point sits at exactly
    `side_bearing`, and its advance width is set to ink_width + 2 *
    side_bearing. This is what keeps inter-letter spacing visually even
    without hand-tuning every glyph's bounds. Glyphs with no ink (e.g.
    "space") are left untouched.

    `spacing_bounds` optionally names, per glyph, the (x_min, x_max) to
    space from instead of the ink's own extremes -- how the cursive faces
    let an exit tail overshoot the advance into the next letter while
    the letter's body keeps standard bearings.
    """
    normalized = {}
    for name, (contours, advance) in glyphs.items():
        if not contours:
            normalized[name] = (contours, advance)
            continue
        xs = [x for contour in contours for x, _ in contour]
        x_min, x_max = min(xs), max(xs)
        if spacing_bounds and name in spacing_bounds:
            x_min, x_max = spacing_bounds[name]
        shift = side_bearing - x_min
        shifted = [[(x + shift, y) for x, y in contour] for contour in contours]
        new_advance = (x_max - x_min) + 2 * side_bearing
        normalized[name] = (shifted, new_advance)
    return normalized


def normalize_baseline(
    glyphs: dict[str, GlyphSpec], reference: str = "H"
) -> dict[str, GlyphSpec]:
    """Put the font's baseline where the flat strokes' ink ends.

    The skeleton grid runs stem CENTERLINES along BASE/CAP, so a stem's
    round cap dips half a pen below y=0 -- every straight letter would
    sit below the line next to any other font. Shift the whole glyph set
    up by the reference glyph's ink depth (H: two plain stems, no
    overshoot) so flats sit exactly on y=0 and curves overshoot below it,
    the way a font's baseline is meant to read. Faces with a wider pen
    shift further; each face's own H decides.
    """
    if reference not in glyphs or not glyphs[reference][0]:
        return glyphs
    shift = -min(y for contour in glyphs[reference][0] for _, y in contour)
    return {
        name: ([[(x, y + shift) for x, y in c] for c in contours], advance)
        for name, (contours, advance) in glyphs.items()
    }


def _ink_top(glyphs: dict[str, GlyphSpec], name: str, fallback: float) -> int:
    if name not in glyphs or not glyphs[name][0]:
        return round(fallback)
    return round(max(y for contour in glyphs[name][0] for _, y in contour))


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
    glyphs = normalize_baseline(glyphs)
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

    fb.setupHorizontalHeader(ascent=LINE_ASCENT, descent=LINE_DESCENT)
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
        sTypoAscender=LINE_ASCENT,
        sTypoDescender=LINE_DESCENT,
        sTypoLineGap=0,
        usWinAscent=LINE_ASCENT,
        usWinDescent=-LINE_DESCENT,
        # Measured from the (baseline-normalized) ink, so they mean what
        # a renderer expects: where H's top and x's top actually are.
        sCapHeight=_ink_top(glyphs, "H", LINE_ASCENT * 0.7),
        sxHeight=_ink_top(glyphs, "x", LINE_ASCENT * 0.5),
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
