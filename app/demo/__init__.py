"""The made-up league (public release Phase 2, 2026-10-02).

A fictional college football world that answers like CFBD: 136 playful schools in ten conferences,
two full seasons simulated play by play, rosters, recruiting classes, transfers, polls and ratings.
Every value is generated here from a seed; nothing is copied from CFBD. It exists for three jobs:

1. Demo mode (`python -m app --demo`): the whole app with no key and no network.
2. The live simulator (`tools/live_sim.py`): a made-up game in progress on a fast clock.
3. Tests: data that can be published, so the public repo can carry its test suite.

Modules: `names` (the word lists), `league` (teams, players, schedules, recruiting), `sim` (one game
play by play), `season` (every game of both seasons, polls and ratings), `render` (the CFBD-shaped
answers), `upstream` (an httpx handler that routes requests to `render`).
"""
