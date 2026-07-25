"""Emit a standalone copy of the scrawl demo with the pen-stroke data
inlined.

demo/typewriter.html fetches ../out/strokes.json, which only works when
the repo is served over HTTP -- browsers block fetch() on file:// URLs,
so double-clicking that file shows a load failure. The copy written to
out/typewriter.html carries the stroke data inside the page itself
(window.APERTURE_STROKES) and opens fine by double-click.
"""

import json
from pathlib import Path

from fontgen.strokes import strokes_by_char

DEMO = Path("demo/typewriter.html")
OUT = Path("out/typewriter.html")
MARKER = "<script>"


def main():
    data = strokes_by_char()

    html = DEMO.read_text()
    if MARKER not in html:
        raise SystemExit(f"no {MARKER!r} block found in {DEMO}")
    embed = (
        "<script>window.APERTURE_STROKES = "
        + json.dumps(data, separators=(",", ":"))
        + ";</script>\n"
    )
    html = html.replace(MARKER, embed + MARKER, 1)

    OUT.write_text(html)
    print(f"saved {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
