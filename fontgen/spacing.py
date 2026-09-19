"""Optical side-bearing corrections, applied AFTER normalize_spacing's
uniform pass.

normalize_spacing gives every glyph identical bearings measured from its
ink extremes -- right for flats, whose stems present a full-height edge,
but a round touches that extreme at a single mid-height point and a
diagonal or T-shape is mostly air at its widest, so both read as gappy at
uniform bearings. A table maps glyph name -> (left, right) units to
TIGHTEN each side; classic ratios are rounds tucking ~a fifth of a
bearing, open diagonals a bit more, T most of all. Each face keeps its
own table next to its build, since the right amounts depend on how that
face draws its extremes (a seriffed flat is wider than a sans one).
"""


def apply_optical_bearings(glyphs, tighten, scale=1.0):
    """Shift/narrow each glyph per `tighten[name] = (left, right)`, both
    multiplied by `scale` (a heavier weight wants proportionally less
    tuck, since its bearings are already tighter)."""
    adjusted = {}
    for name, (contours, advance) in glyphs.items():
        dl, dr = tighten.get(name, (0, 0))
        dl, dr = dl * scale, dr * scale
        if not contours or (dl == 0 and dr == 0):
            adjusted[name] = (contours, advance)
            continue
        shifted = [[(x - dl, y) for x, y in contour] for contour in contours]
        adjusted[name] = (shifted, advance - dl - dr)
    return adjusted
