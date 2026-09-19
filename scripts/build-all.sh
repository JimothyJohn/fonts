#!/usr/bin/env bash
# Rebuild every tracked font artifact after a geometry change: all seven
# faces' TTFs (the sans as its full family), their alphabet and specimen
# sheets, and the docs/ copies
# the GitHub Pages specimen serves. Exits non-zero on the first failure
# and prints every path it wrote.
#
#   scripts/build-all.sh          # everything
#   scripts/build-all.sh sans     # one face (sans|serif|script|hand|moderne|olde|marquee)
set -euo pipefail
cd "$(dirname "$0")/.."

usage() { sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }
[[ "${1:-}" == "-h" || "${1:-}" == "--help" ]] && usage 0

make_script() {
  case "$1" in
    sans) echo make_font.py ;;
    serif) echo make_font_serif.py ;;
    script) echo make_font_script.py ;;
    hand) echo make_font_hand.py ;;
    moderne) echo make_font_moderne.py ;;
    olde) echo make_font_blackletter.py ;;
    marquee) echo make_font_marquee.py ;;
    *) echo "unknown face: $1" >&2; usage 2 ;;
  esac
}

faces=("$@")
[[ ${#faces[@]} -eq 0 ]] && faces=(sans serif script hand moderne olde marquee)
for face in "${faces[@]}"; do make_script "$face" >/dev/null; done

for face in "${faces[@]}"; do
  uv run python "scripts/$(make_script "$face")"
  uv run python scripts/render_alphabet.py "out/aperture-$face.ttf" "out/alphabet-$face.png"
  uv run python scripts/render_specimen.py "out/aperture-$face.ttf" "out/specimen-$face.png"
  if [[ "$face" == sans ]]; then
    # make_font.py builds the whole family; ship every member.
    uv run python scripts/render_family.py out/family-sans.png
    for f in out/aperture-sans*.ttf; do
      cp "$f" "docs/fonts/$(basename "$f")"
      echo "wrote docs/fonts/$(basename "$f")"
    done
  else
    cp "out/aperture-$face.ttf" "docs/fonts/aperture-$face.ttf"
    echo "wrote docs/fonts/aperture-$face.ttf"
  fi
done
