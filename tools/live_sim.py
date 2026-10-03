r"""Live-game simulator (developer tool): the real app against the made-up league, with the demo
team's game in progress on a fast clock.

Since public release Phase 2 (2026-10-02) this is demo mode (`python -m app --demo`, app/demo/run.py)
with the simulator's defaults; before, it replayed a recorded game. The Live sheet's real
poller, event store, delay buffer, SSE stream and archive writer run against a made-up game that is
"in progress" on the simulated clock. Nothing here calls CFBD or any other network service, reads
the project's .env, or touches the project's data folder (the league is cached in data/demo/).

Usage (PowerShell, from the project root):

    .\.venv\Scripts\python tools\live_sim.py
        Kickoff 40 simulated minutes from now, 10 simulated seconds per real second.
        Open http://127.0.0.1:8650/ and go to the Live sheet. Ctrl+C stops it.

    .\.venv\Scripts\python tools\live_sim.py --speed 60 --start -5
        Faster, and start 5 simulated minutes before kickoff (the window is already open).

    .\.venv\Scripts\python tools\live_sim.py --fail-at 30 --fail-for 45
        /live/plays answers HTTP 500 from simulated minute 30 after kickoff for 45 real seconds,
        to exercise the retry, backoff, circuit breaker and stale paths.

    .\.venv\Scripts\python tools\live_sim.py --tier 1
        Imitate a Tier 1 key: no live play-by-play (CFBD answers 401), so the sheet falls back.

Options are demo mode's (`python -m app --demo --help`); the defaults here are --start -40.

Timing notes: every duration inside the app is simulated time. At --speed 60 the 12 s poll is
0.2 real seconds, a 45 s broadcast delay is 0.75 real seconds. Like a real game, /games/teams and
/games/players stay empty until the final, so the Live sheet's leaders come from the play-by-play.
Browser-side clocks (Date.now) run in real time while the server runs in simulated time.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.demo.run import add_arguments, run  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Serve the real app against a made-up game in progress.")
    add_arguments(parser)
    parser.set_defaults(start=-40.0)
    return run(parser.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
