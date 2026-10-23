"""Draw the neutral icons in static/icons/ (Phase 12; public release Phase 3; the program's icon, owner 2026-10-23, the board
https://claude.ai/artifact/CAnmauKcs6mpTcndK3PBWQ): the Myers Labs sun, the app's own loading sun, on the app's charcoal.

    icon-180.png, icon-192.png, icon-512.png, icon-maskable-512.png   the home-screen icons before the team is known (and
                                                                        the fallback when the team's drawing fails), square
    sun.svg, sun-32.png                                                the browser tab on every page
    icon-256.png                                                       the Linux launcher and the packaged program
    kickoff.ico                                                        the program (.exe), the Desktop icon and the tray

The team's own home-screen icons stay the football in its colors, drawn by the server at /icons/<name>
(app/services/icons.py). Run from the project root:

    .\\.venv\\Scripts\\python tools\\make_icons.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.icons import SUN_SVG, ico_bytes, sun_png  # noqa: E402

OUT = ROOT / "static" / "icons"
HOME = {"icon-180.png": (180, 1.0), "icon-192.png": (192, 1.0), "icon-512.png": (512, 1.0), "icon-maskable-512.png": (512, 0.8)}  # maskable: inside the safe circle


def write(name: str, data: bytes) -> None:
    (OUT / name).write_bytes(data)
    print(f"wrote static/icons/{name} ({len(data):,} bytes)")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, (size, scale) in HOME.items():
        write(name, sun_png(size, rounded=False, small=False, scale=scale, samples=3))
    write("icon-256.png", sun_png(256, samples=3))
    write("sun-32.png", sun_png(32))
    (OUT / "sun.svg").write_text(SUN_SVG, encoding="utf-8", newline="\n")
    print("wrote static/icons/sun.svg")
    write("kickoff.ico", ico_bytes([sun_png(16), sun_png(24), sun_png(32), sun_png(48), sun_png(256, samples=3)]))


if __name__ == "__main__":
    main()
