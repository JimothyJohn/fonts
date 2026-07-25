"""Snapshot the current out/*.ttf builds as numbered versions.

Each run copies out/aperture-sans.ttf and out/aperture-serif.ttf into
out/versions/ as aperture-sans-vN.ttf / aperture-serif-vN.ttf, where N is
one past the highest version already present. The version is also baked
into the font's internal names (family "Aperture Sans v3", psName
ApertureSansV3-Regular, version string "Version 3.000") so every snapshot
installs as its own family in Font Book and versions can be compared
side by side instead of silently replacing each other.
"""

import re
import shutil
from pathlib import Path

from fontTools.ttLib import TTFont

OUT_DIR = Path("out")
VERSIONS_DIR = OUT_DIR / "versions"
FONTS = {
    "aperture-sans.ttf": "Aperture Sans",
    "aperture-serif.ttf": "Aperture Serif",
    "aperture-script.ttf": "Aperture Script",
    "aperture-hand.ttf": "Aperture Hand",
}
STYLE = "Regular"


def latest_version(slug: str) -> tuple[int, Path | None]:
    """Highest existing snapshot number (0 if none) and its path, for one
    family's file slug (e.g. "aperture-sans")."""
    versions = {
        int(m.group(1)): p
        for p in VERSIONS_DIR.glob(f"{slug}-v*.ttf")
        if (m := re.match(rf"{re.escape(slug)}-v(\d+)\.ttf$", p.name))
    }
    if not versions:
        return 0, None
    n = max(versions)
    return n, versions[n]


def unchanged(src: Path, snapshot: Path) -> bool:
    """True when the actual letterforms are identical -- the name table
    differs by construction (the snapshot has the version stamped in),
    so compare the glyph data instead of the file bytes."""
    return TTFont(src).getTableData("glyf") == TTFont(snapshot).getTableData("glyf")


def stamp_names(path: Path, family: str, version: int) -> None:
    font = TTFont(path)
    versioned_family = f"{family} v{version}"
    ps_name = f"{family.replace(' ', '')}V{version}-{STYLE}"
    records = {
        1: versioned_family,
        3: f"{version}.000;{ps_name}",
        4: f"{versioned_family} {STYLE}",
        5: f"Version {version}.000",
        6: ps_name,
    }
    name = font["name"]
    for name_id, value in records.items():
        name.setName(value, name_id, 3, 1, 0x409)  # Windows
        name.setName(value, name_id, 1, 0, 0)  # Macintosh
    font["head"].fontRevision = float(version)
    font.save(path)


def main():
    VERSIONS_DIR.mkdir(parents=True, exist_ok=True)
    for filename, family in FONTS.items():
        src = OUT_DIR / filename
        if not src.exists():
            print(f"skipped {family}: {src} not built")
            continue
        slug = filename.removesuffix(".ttf")
        current, latest_path = latest_version(slug)
        if latest_path is not None and unchanged(src, latest_path):
            print(f"skipped {family}: unchanged since {latest_path.name}")
            continue
        version = current + 1
        dst = VERSIONS_DIR / f"{slug}-v{version}.ttf"
        shutil.copy(src, dst)
        stamp_names(dst, family, version)
        print(f"saved {dst} as family '{family} v{version}'")


if __name__ == "__main__":
    main()
