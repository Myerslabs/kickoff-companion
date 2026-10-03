"""Draw the neutral home-screen icons in static/icons/ (Phase 12; public release Phase 3): a
leather-brown football with white laces on a dark slate ground. These are what a page links to
before the team is known; the server draws the team's own icons at /icons/<name> from its colors
(app/services/icons.py, the same drawing). Run from the project root:

    .\\.venv\\Scripts\\python tools\\make_icons.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.icons import NEUTRAL_BALL, NEUTRAL_GROUND, SIZES, icon_bytes  # noqa: E402

OUT = ROOT / "static" / "icons"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name in SIZES:
        (OUT / name).write_bytes(icon_bytes(name, NEUTRAL_GROUND, NEUTRAL_BALL, samples=4))
        print(f"wrote static/icons/{name}")


if __name__ == "__main__":
    main()
