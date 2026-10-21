"""Kickoff Companion installed as a package (freeze wave F6, 2026-10-21): `uvx kickoff-companion`, or
`pip install kickoff-companion` and then `kickoff-companion`.

The program's own package is `app`, kept inside this one with its `static` folder and the `.env` template, so
nothing else lands at the top level of an environment. This module puts that folder on the path and hands over to
app.cli.main. The `installed` file beside it tells app/paths.py that this folder is the package's and read-only, so
`.env`, `data/` and `logs/` go to the app-data folder instead."""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main(argv: list[str] | None = None) -> int:
    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))
    from app.cli import main as run

    return run(argv)
