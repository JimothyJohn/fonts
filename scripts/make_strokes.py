import json
from pathlib import Path

from fontgen.strokes import strokes_by_char

OUT = Path("out/strokes.json")


def main():
    data = strokes_by_char()
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(data, separators=(",", ":")))
    for key, face in data["faces"].items():
        n_strokes = sum(len(c["strokes"]) for c in face["chars"].values())
        print(f"saved {OUT} [{key}]: {len(face['chars'])} chars, {n_strokes} strokes")


if __name__ == "__main__":
    main()
