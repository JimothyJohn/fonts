"""Kerning pairs derived from the glyphs' own geometry.

normalize_spacing plus the optical tucks set each glyph's bearings from
its widest point. That is right for a letter next to a flat, but two
glyphs whose extremes lie at opposite heights -- A beside V, L beside T,
T over a lowercase, r before a period -- leave a wedge of air between
them that reads as a gap, and no per-glyph bearing can close it. Kerning
is the per-pair fix, and here it is measured rather than typed:

- Each glyph is profiled row by row (every ROW_STEP units): where its ink
  begins and ends at that height.
- A side is OPEN if its ink at the optical center (FOCUS_Y, between mid
  x-height and mid cap) sits well inside its own extreme -- a diagonal, a
  bar overhang, an arm, a mark that lives only near the baseline. Only
  pairs where at least one facing side is open are candidates; a stem
  beside a stem or a round beside a round is what the bearings were set
  for and is left alone.
- For a candidate pair at its normal advance, the felt gap at each row
  is measured between the two glyphs' CONVEX HULLS, each hull taken over
  just the rows the partner occupies. The hull is what the eye reads as
  a letter's edge: k's arm and leg tips bound the k, so a round next to
  it is judged against the line between those tips, not the pocket
  behind them; but T's bar lies outside a lowercase partner's rows, so
  toward that partner T is just its stem and the partner tucks under.
  The pair's felt gap is the tightest row after a penalty that grows
  with the row's distance from the center (a gap up at the cap line or
  down at the feet must be that much narrower to count), and the kern
  is (target - felt gap), target being what a flat beside a flat (H H)
  measures.
- Two clamps: the pair's tightest RAW ink gap never drops below FLOOR
  of the target (no collisions), and no kern exceeds MAX of the target.
- Only negative kerns are emitted, and digit-beside-digit pairs are
  skipped so figures stay tabular.

The result is a plain GPOS `kern` feature (flat pairs), compiled by
build_font via feaLib. Measured on upright shapes; obliques inherit it
unchanged, since a shear about the baseline preserves every row's gap.
"""

from shapely.geometry import LineString, box

from fontgen.primitives import contours_to_polygon

ROW_STEP = 20
ROW_LO, ROW_HI = -300, 950

#: Optical center; penalty per unit of distance from it; how far inside
#: its own extreme a side's center ink must sit to count as open.
FOCUS_Y = 300.0
FOCUS_SLOPE = 0.5
OPEN_DEPTH = 60

#: Clamps as fractions of the flat-flat target gap.
FLOOR = 0.45
MAX = 0.6

#: Kerns smaller than this are noise, not spacing.
MIN_KERN = 10

DIGITS = {
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
}
ROWS = list(range(ROW_LO, ROW_HI + 1, ROW_STEP))
PENALTY = [FOCUS_SLOPE * abs(y - FOCUS_Y) for y in ROWS]
FOCUS_ROW = min(range(len(ROWS)), key=lambda i: abs(ROWS[i] - FOCUS_Y))


def _spans(poly):
    spans = []
    for y in ROWS:
        cut = poly.intersection(LineString([(-3000, y), (5000, y)]))
        spans.append(None if cut.is_empty else (cut.bounds[0], cut.bounds[2]))
    return spans


class _Glyph:
    def __init__(self, contours, advance):
        self.poly = contours_to_polygon(contours)
        self.advance = advance
        self.spans = _spans(self.poly)
        self._hulls = {}
        inked = [s for s in self.spans if s]
        self.left_extreme = min(s[0] for s in inked)
        self.right_extreme = max(s[1] for s in inked)
        at_focus = self.spans[FOCUS_ROW]
        self.left_open = (
            at_focus is None or at_focus[0] - self.left_extreme > OPEN_DEPTH
        )
        self.right_open = (
            at_focus is None or self.right_extreme - at_focus[1] > OPEN_DEPTH
        )

    def _hull(self, lo, hi):
        """Row spans of the convex hull of just the ink between rows lo
        and hi (inclusive indices) -- what a partner living in those rows
        actually faces. Cached: partners share row ranges heavily."""
        key = (lo, hi)
        if key not in self._hulls:
            band = box(-3000, ROWS[lo] - ROW_STEP / 2, 5000, ROWS[hi] + ROW_STEP / 2)
            self._hulls[key] = _spans(self.poly.intersection(band).convex_hull)
        return self._hulls[key]

    def hull(self, rows):
        return self._hull(rows[0], rows[-1])


def _shared_rows(left, right):
    return [
        i
        for i, (ls, rs) in enumerate(zip(left.spans, right.spans))
        if ls is not None and rs is not None
    ]


def _raw_gaps(left, right, rows):
    return [left.advance + right.spans[i][0] - left.spans[i][1] for i in rows]


def _felt_gap(left, right, rows):
    lh, rh = left.hull(rows), right.hull(rows)
    return min(
        left.advance + rh[i][0] - lh[i][1] + PENALTY[i]
        for i in rows
        if lh[i] is not None and rh[i] is not None
    )


def kern_pairs(glyphs, reference="H"):
    """{(left, right): kern} for every pair that needs one. `glyphs` is
    the final, spaced {name: (contours, advance)} set the font is built
    from (upright) -- kerning is measured on exactly what ships."""
    profiles = {
        name: _Glyph(contours, advance)
        for name, (contours, advance) in glyphs.items()
        if contours and name != ".notdef"
    }
    ref = profiles[reference]
    target = _felt_gap(ref, ref, _shared_rows(ref, ref))
    floor, ceiling = FLOOR * target, MAX * target

    pairs = {}
    for lname, left in profiles.items():
        for rname, right in profiles.items():
            if lname in DIGITS and rname in DIGITS:
                continue
            if not (left.right_open or right.left_open):
                continue
            rows = _shared_rows(left, right)
            if not rows:
                continue
            kern = target - _felt_gap(left, right, rows)
            if kern >= 0:
                continue
            kern = max(kern, floor - min(_raw_gaps(left, right, rows)), -ceiling)
            kern = 5 * round(kern / 5)
            if kern <= -MIN_KERN:
                pairs[(lname, rname)] = int(kern)
    return pairs


def kern_feature(pairs):
    """feaLib source for a flat-pair GPOS kern feature ("" if no pairs)."""
    if not pairs:
        return ""
    lines = [f"    pos {l} {r} {v};" for (l, r), v in sorted(pairs.items())]
    return "feature kern {\n" + "\n".join(lines) + "\n} kern;\n"


def kerning_from_font(font):
    """Read flat kern pairs back out of a built font's GPOS -- the inverse
    of kern_feature, for renderers and tests."""
    if "GPOS" not in font:
        return {}
    pairs = {}
    for lookup in font["GPOS"].table.LookupList.Lookup:
        for sub in lookup.SubTable:
            if sub.LookupType == 9:
                sub = sub.ExtSubTable
            if sub.LookupType != 2 or sub.Format != 1:
                continue
            for left, pair_set in zip(sub.Coverage.glyphs, sub.PairSet):
                for rec in pair_set.PairValueRecord:
                    v = rec.Value1.XAdvance if rec.Value1 else 0
                    if v:
                        pairs[(left, rec.SecondGlyph)] = v
    return pairs
