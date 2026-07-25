import pytest

from fontgen.build import build_font, normalize_spacing
from fontgen.glyphs import CMAP, GLYPHS
from fontgen.metrics import CAP, SIDE_BEARING
from fontgen.primitives import finalize, rect


@pytest.mark.parametrize("name,fn", list(GLYPHS.items()))
def test_glyph_has_positive_advance(name, fn):
    _, advance = fn()
    assert advance > 0


@pytest.mark.parametrize("name,fn", [(n, f) for n, f in GLYPHS.items() if n != "space"])
def test_non_space_glyph_has_contours(name, fn):
    contours, _ = fn()
    assert len(contours) > 0
    assert all(len(c) >= 3 for c in contours)


def test_cmap_targets_exist_in_glyph_set():
    for codepoint, glyph_name in CMAP.items():
        assert glyph_name in GLYPHS, (
            f"cmap entry U+{codepoint:04X} -> {glyph_name!r} missing from GLYPHS"
        )


def test_full_font_builds(tmp_path):
    glyphs = {".notdef": (finalize([rect(60, 0, 460, CAP)]), 520)}
    for name, fn in GLYPHS.items():
        glyphs[name] = fn()
    glyphs = normalize_spacing(glyphs)

    out_path = tmp_path / "test.ttf"
    build_font(glyphs, CMAP, "Test Family", "Regular", str(out_path))
    assert out_path.exists()
    assert out_path.stat().st_size > 0


@pytest.mark.parametrize("name,fn", [(n, f) for n, f in GLYPHS.items() if n != "space"])
def test_normalize_spacing_gives_uniform_side_bearings(name, fn):
    contours, advance = fn()
    (shifted, new_advance) = normalize_spacing({name: (contours, advance)})[name]
    xs = [x for c in shifted for x, _ in c]
    assert min(xs) == pytest.approx(SIDE_BEARING)
    assert new_advance - max(xs) == pytest.approx(SIDE_BEARING)
