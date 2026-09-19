"""The sans family: every style builds from the one skeleton set, weights
progress monotonically, italics lean by exactly ITALIC_ANGLE, and heavy
weights keep their counters open."""

import math

import pytest
from fontTools.ttLib import TTFont
from shapely.geometry import LineString, MultiPolygon

from fontgen.build import build_font, legacy_names, normalize_spacing
from fontgen.glyphs import CMAP, GLYPHS
from fontgen.metrics import CAP, STROKE
from fontgen.primitives import contours_to_polygon, finalize, rect
from fontgen.sans import (
    ITALIC_ANGLE,
    WEIGHTS,
    file_slug,
    make_glyphs,
    side_bearing,
    style_name,
    styles,
)

STYLES = styles()


def _poly(fn):
    return contours_to_polygon(fn()[0])


def test_family_has_five_weights_upright_and_italic():
    assert len(STYLES) == 10
    assert STYLES[0] == ("Light", False)
    assert {w for w, _ in STYLES} == set(WEIGHTS)


@pytest.mark.parametrize("weight,italic", STYLES)
def test_every_style_covers_the_full_skeleton_set(weight, italic):
    glyphs = make_glyphs(weight, italic)
    assert set(glyphs) == set(GLYPHS)
    for name, fn in glyphs.items():
        contours, advance = fn()
        assert advance > 0
        assert (len(contours) > 0) == (name != "space"), name


def test_regular_upright_matches_the_sans_reference_glyphs():
    """Re-inking the recorded centerlines at STROKE reproduces GLYPHS;
    the only permitted difference is a buried bowl end's cap style."""
    replay = make_glyphs("Regular", False)
    for name in GLYPHS:
        if name == "space":
            continue
        a, b = _poly(GLYPHS[name]), _poly(replay[name])
        assert a.symmetric_difference(b).area < 0.01 * a.area, name


@pytest.mark.parametrize(
    "name,y", [("I", CAP / 2), ("l", CAP / 2), ("H", CAP / 4), ("n", 100)]
)
def test_stem_width_tracks_the_weight(name, y):
    """Slice each stem with a horizontal line clear of any crossbar or
    arch: every segment is one stem, exactly the weight's pen wide."""
    widths = []
    for weight, (stroke, _) in WEIGHTS.items():
        poly = _poly(make_glyphs(weight, False)[name])
        cut = poly.intersection(LineString([(-1000, y), (2000, y)]))
        segments = list(cut.geoms) if hasattr(cut, "geoms") else [cut]
        for seg in segments:
            assert seg.length == pytest.approx(stroke, abs=2), (
                name,
                weight,
                seg.length,
            )
        widths.append(segments[0].length)
    assert widths == sorted(widths)


@pytest.mark.parametrize("weight", list(WEIGHTS))
def test_italic_is_the_upright_sheared_by_the_italic_angle(weight):
    up = _poly(make_glyphs(weight, False)["I"])
    it = _poly(make_glyphs(weight, True)["I"])
    # The lean shifts the cap-height end of the stem by tan(angle) * CAP.
    top_up = max(x for x, y in up.exterior.coords if y > CAP)
    top_it = max(x for x, y in it.exterior.coords if y > CAP)
    assert top_it - top_up == pytest.approx(
        math.tan(math.radians(ITALIC_ANGLE)) * CAP, abs=6
    )
    # Sheared about the baseline: nothing on it moves.
    assert it.bounds[1] == pytest.approx(up.bounds[1], abs=0.5)


@pytest.mark.parametrize("weight,italic", STYLES)
@pytest.mark.parametrize(
    "name", ["a", "e", "g", "B", "eight", "o", "d", "R", "six", "nine"]
)
def test_counters_stay_open_at_every_weight(weight, italic, name):
    poly = _poly(make_glyphs(weight, italic)[name])
    parts = list(poly.geoms) if isinstance(poly, MultiPolygon) else [poly]
    holes = sum(len(p.interiors) for p in parts)
    assert holes >= 1, f"{name} lost its counter at {style_name(weight, italic)}"


@pytest.mark.parametrize("weight,italic", STYLES)
@pytest.mark.parametrize("name", ["f", "g", "j", "e", "c", "s", "r"])
def test_hooks_keep_air_from_their_own_strokes(weight, italic, name):
    """A free end that fuses into a neighbouring stroke at a heavy weight
    turns a hook into a blob -- the closed loop shows up as a hole."""
    poly = _poly(make_glyphs(weight, italic)[name])
    parts = list(poly.geoms) if isinstance(poly, MultiPolygon) else [poly]
    expected = 1 if name in ("g", "e") else 0  # g's bowl and e's eye are real counters
    assert sum(len(p.interiors) for p in parts) == expected, (
        name,
        style_name(weight, italic),
    )


def test_side_bearings_tighten_with_weight():
    bearings = [side_bearing(w) for w in WEIGHTS]
    assert bearings == sorted(bearings, reverse=True)
    assert side_bearing("Regular") == 70


def test_style_names_and_slugs():
    assert style_name("Regular", False) == "Regular"
    assert style_name("Regular", True) == "Italic"
    assert style_name("Black", True) == "Black Italic"
    assert file_slug("Regular", False) == ""
    assert file_slug("Bold", True) == "-bold-italic"
    assert legacy_names("Aperture Sans", "Bold Italic") == (
        "Aperture Sans",
        "Bold Italic",
    )
    assert legacy_names("Aperture Sans", "Light Italic") == (
        "Aperture Sans Light",
        "Italic",
    )
    assert legacy_names("Aperture Sans", "Black") == ("Aperture Sans Black", "Regular")


@pytest.mark.parametrize(
    "weight,italic",
    [("Regular", False), ("Light", True), ("Bold", False), ("Black", True)],
)
def test_built_font_carries_style_metadata(tmp_path, weight, italic):
    glyphs = {".notdef": (finalize([rect(60, 0, 460, CAP)]), 520)}
    for name, fn in make_glyphs(weight, italic).items():
        glyphs[name] = fn()
    glyphs = normalize_spacing(glyphs, side_bearing=side_bearing(weight))
    path = tmp_path / "f.ttf"
    style = style_name(weight, italic)
    build_font(
        glyphs,
        CMAP,
        "Aperture Sans",
        style,
        str(path),
        weight_class=WEIGHTS[weight][1],
        italic_angle=ITALIC_ANGLE if italic else 0.0,
    )
    font = TTFont(str(path))
    names = {r.nameID: r.toUnicode() for r in font["name"].names if r.platformID == 3}
    assert names[16] == "Aperture Sans"
    assert names[17] == style
    assert names[6] == "ApertureSans-" + style.replace(" ", "")
    assert font["OS/2"].usWeightClass == WEIGHTS[weight][1]
    assert font["post"].italicAngle == (-ITALIC_ANGLE if italic else 0.0)
    bold = weight == "Bold"
    assert bool(font["OS/2"].fsSelection & 0x20) == bold
    assert bool(font["OS/2"].fsSelection & 0x01) == italic
    assert bool(font["OS/2"].fsSelection & 0x40) == (not bold and not italic)
    assert font["head"].macStyle == (0x01 if bold else 0) | (0x02 if italic else 0)
    assert STROKE == 78  # the family's Regular pen; WEIGHTS keys off it
