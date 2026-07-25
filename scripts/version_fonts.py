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
}
STYLE = "Regular"


def next_version() -> int:
    versions = [
        int(m.group(1))
        for p in VERSIONS_DIR.glob("*-v*.ttf")
        if (m := re.search(r"-v(\d+)\.ttf$", p.name))
    ]
    return max(versions, default=0) + 1


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
    version = next_version()
    for filename, family in FONTS.items():
        src = OUT_DIR / filename
        dst = VERSIONS_DIR / filename.replace(".ttf", f"-v{version}.ttf")
        shutil.copy(src, dst)
        stamp_names(dst, family, version)
        print(f"saved {dst} as family '{family} v{version}'")


if __name__ == "__main__":
    main()
