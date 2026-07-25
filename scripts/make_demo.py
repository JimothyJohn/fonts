"""Emit a standalone copy of the typewriter demo with the jitter variant
fonts inlined as base64 data: URIs.

demo/typewriter.html fetches the variants from ../out/jitter, which only
works when the repo is served over HTTP -- browsers block fetch() on
file:// URLs, so double-clicking that file shows "Failed to load font
variants". The copy written to out/typewriter.html carries the fonts
inside the page itself (window.APERTURE_VARIANTS) and opens fine by
double-click.
"""

import base64
import json
from pathlib import Path

DEMO = Path("demo/typewriter.html")
JITTER_DIR = Path("out/jitter")
OUT = Path("out/typewriter.html")
MARKER = "<script>"


def main():
    manifest = json.loads((JITTER_DIR / "manifest.json").read_text())
    urls = [
        "data:font/ttf;base64,"
        + base64.b64encode((JITTER_DIR / f"variant-{i}.ttf").read_bytes()).decode()
        for i in range(manifest["count"])
    ]

    html = DEMO.read_text()
    if MARKER not in html:
        raise SystemExit(f"no {MARKER!r} block found in {DEMO}")
    embed = f"<script>window.APERTURE_VARIANTS = {json.dumps(urls)};</script>\n"
    html = html.replace(MARKER, embed + MARKER, 1)

    OUT.write_text(html)
    print(f"saved {OUT} ({OUT.stat().st_size // 1024} KB, {len(urls)} variants inlined)")


if __name__ == "__main__":
    main()
