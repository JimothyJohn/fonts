# Aperture fonts

Seven faces generated from one set of stroke skeletons (`fontgen/glyphs.py`).
The sans is a ten-style family (`fontgen/sans.py`); every other face
re-inks the same skeletons under its own pen model.

## Rebuild ritual

- Any edit under `fontgen/` changes tracked artifacts: `out/*.ttf`,
  `out/alphabet-*.png`, `out/specimen-*.png`, `out/family-sans.png`,
  `docs/fonts/*.ttf`. Run `scripts/build-all.sh` (or `scripts/build-all.sh <face>`)
  before committing. Builds are byte-identical, so a TTF that changes in the
  diff changed for a reason.
- Stage by explicit path. `out/` is gitignored except the allowlisted patterns
  in `.gitignore`; a new artifact needs an `!out/...` entry.

## Verifying shapes

- The alphabet PNG centers each glyph by ink at 120px. It hides spacing and
  the flat-vs-curve height relationship. Judge geometry by drawing large
  per-glyph tiles straight from `GLYPHS[name]()` contours with guidelines
  (see the scratch renderer pattern in git history of PR #9), and judge
  spacing/kerning from `out/family-sans.png` or the specimen sheets.
- The vertical contract: a straight stroke's centerline sits on its
  guideline, so its ink reaches `STROKE/2` past it; a curve's centerline
  overshoots the guideline by `OVERSHOOT`. Author curves against
  `CAP_CURVE`/`BASE_CURVE`/`X_CURVE`/`BASE_CURVE_LC`/`DESCENT_CURVE`, never
  the bare guidelines. `tests/test_glyphs.py` pins this per glyph.
- `build_font` shifts every face so H's ink rests on y=0
  (`normalize_baseline`); line metrics are `LINE_ASCENT`/`LINE_DESCENT`.

## Gotchas

- fontTools `FontBuilder.setup*` methods re-initialize their table from
  defaults; use `updateHead`/`_updateTableWithValues` for a field on a table
  already set up. `setupHead` after `setupGlyf` wipes the glyph bounds.
- Skeletons that need air against their own strokes at heavy weights take a
  `pen` kwarg (e, f, g, j). Add one rather than hard-coding clearances for the
  Regular pen.
- Obliques are spaced and kerned as uprights, then sheared. Measuring bearings
  on a sheared glyph pads every advance by the slant's width.
- PIL here has no raqm, so `draw.text` ignores GPOS kerning;
  `scripts/render_family.py` lays glyphs out itself from `hmtx` + GPOS.

## Stack

`uv run pytest`, `uvx ruff check . && uvx ruff format --check .` (CI pins
ruff 0.16.0). No Makefile; `scripts/` holds every routine.
