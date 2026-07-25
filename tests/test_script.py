import pytest

from fontgen.build import build_font, normalize_spacing
from fontgen.glyphs import CMAP, GLYPHS, SKELETONS
from fontgen.metrics import CAP
from fontgen.primitives import finalize, record_strokes, rect
from fontgen.script import LOWERCASE, SLANT, make_glyphs, script_strokes

SCRIPT_GLYPHS = make_glyphs(SKELETONS)


@pytest.mark.parametrize("name", [n for n in SKELETONS if n != "space"])
def test_script_glyph_has_contours(name):
    contours, advance = SCRIPT_GLYPHS[name]()
    assert advance > 0
    assert len(contours) > 0
    assert all(len(c) >= 3 for c in contours)


def test_cmap_covered():
    for glyph_name in CMAP.values():
        assert glyph_name in SCRIPT_GLYPHS


# j is the one lowercase letter with no exit tail: its pen finishes on
# the descender hook, below baseline and heading left -- there is no
# natural join point, so _exit_point correctly finds nothing.
TAILED = sorted(LOWERCASE - {"j"})


def test_j_gets_no_tail():
    with record_strokes() as sans_strokes:
        SKELETONS["j"]()
    strokes = script_strokes("j", SKELETONS["j"])
    assert len(strokes) == len(sans_strokes)


@pytest.mark.parametrize("name", TAILED)
def test_lowercase_grows_exit_tail(name):
    """Every tailed lowercase letter's script ink must extend farther
    right than the sans ink of the same skeleton, slant removed: that
    extra reach is the exit tail."""
    sans_contours, _ = GLYPHS[name]()
    sans_right = max(x for c in sans_contours for x, _ in c)
    strokes = script_strokes(name, SKELETONS[name])
    script_right = max(x - SLANT * y for s in strokes for x, y in s["pts"])
    assert script_right > sans_right + 50


def test_slant_applied_to_stem():
    """l is a bare stem: after the shear its top must sit right of its
    bottom by SLANT * height."""
    strokes = script_strokes("l", SKELETONS["l"])
    stem = strokes[0]["pts"]
    (x0, y0), (x1, y1) = stem[0], stem[-1]
    top, bottom = ((x1, y1), (x0, y0)) if y1 > y0 else ((x0, y0), (x1, y1))
    assert top[0] - bottom[0] == pytest.approx(SLANT * (top[1] - bottom[1]))


def test_uppercase_gets_no_tail():
    """Caps are slanted but unjoined: the shear-corrected centerlines
    must match the sans centerlines exactly."""
    with record_strokes() as sans_strokes:
        SKELETONS["H"]()
    sans_right = max(x for s in sans_strokes for x, _ in s["pts"])
    strokes = script_strokes("H", SKELETONS["H"])
    script_right = max(x - SLANT * y for s in strokes for x, y in s["pts"])
    assert script_right == pytest.approx(sans_right)


def test_script_deterministic():
    a = script_strokes("a", SKELETONS["a"])
    b = script_strokes("a", SKELETONS["a"])
    assert a == b


def test_full_script_font_builds(tmp_path):
    glyphs = {".notdef": (finalize([rect(60, 0, 460, CAP)]), 520)}
    for name, fn in SCRIPT_GLYPHS.items():
        glyphs[name] = fn()
    glyphs = normalize_spacing(glyphs, side_bearing=45)

    out_path = tmp_path / "script.ttf"
    build_font(glyphs, CMAP, "Test Script", "Regular", str(out_path))
    assert out_path.exists()
    assert out_path.stat().st_size > 0
