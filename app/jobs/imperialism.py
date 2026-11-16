"""The Imperialism Map job (FEAT-17): deal the season's starting map and replay every finished game to date, from scratch,
into data/season/<year>/imperialism.json (app/services/imperialism.py). Second in the weekly run, after Talent Edge.

    python -m app.jobs.imperialism [--season 2026] [--url http://127.0.0.1:8642]
    python -m app.jobs.imperialism --build-grid --census cb_2024_us_state_20m.zip     the grid, once (tools/imperialism_build.py does the same)

Calls, through the client, its cache and the quota guard, paced: /teams/fbs and the season's /games (both already kept for
the other pages), the postseason's /games and /playoffs/cfp/participants (2 calls when they change). The FBS list and the
regular season are required; the postseason and the playoff field are not (until they exist, the map stops before
Selection Sunday: "CFP field not yet known", a normal state, not a failure). A school CFBD lists with no enrollment row,
or a missing grid, fails the run and the last good map stays."""

from __future__ import annotations

import argparse
import hashlib
import logging
import sys
import time
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any

from app.cache import DataKind
from app.cfbd.client import CfbdClient, paced_calls
from app.cfbd.models import Game, PlayoffParticipant, Team
from app.jobs import JobFailed
from app.jobs.talent_edge import latest_week
from app.services.imperialism import ENROLLMENT_PATH, ImperialismError, ImperialismStore, Season, build_table, read_enrollment
from app.services.imperialism_grid import DEFAULT_PATH as GRID_PATH
from app.services.imperialism_grid import load_grid
from app.services.parts import Part, PartFetcher, iso

log = logging.getLogger("kickoff.jobs.imperialism")

NAME = "imperialism"


def grid_version(path: Path = GRID_PATH) -> str:
    """The first 12 hex digits of the grid file's SHA-256: the tablet keeps the grid until this changes."""
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:12]
    except OSError:
        return "missing"


def _source(part: Part) -> dict[str, Any]:
    fetched = part.fetched
    return {"fetchedAt": iso(fetched.fetched_at) if fetched else None, "stale": bool(fetched.stale) if fetched else None, "records": len(part.records), "error": part.error}


class ImperialismJob:
    def __init__(self, client: CfbdClient, data_dir: Path, season: int, fetcher: PartFetcher | None = None, grid_path: Path = GRID_PATH, enrollment_path: Path = ENROLLMENT_PATH) -> None:
        self.client = client
        self.season = season
        self.fetcher = fetcher or PartFetcher(client)
        self.store = ImperialismStore(data_dir, season)
        self.grid_path = Path(grid_path)
        self.enrollment_path = Path(enrollment_path)

    async def _fetch(self) -> dict[str, Part]:
        s, f = self.season, self.fetcher
        return {
            "teams": await f.fetch("teams", "/teams/fbs", {"year": s}, Team, DataKind.TEAMS),
            "games": await f.fetch("games", "/games", {"year": s}, Game, DataKind.SCHEDULE),
            "postseason": await f.fetch("postseason", "/games", {"year": s, "seasonType": "postseason"}, Game, DataKind.SCHEDULE),
            "field": await f.fetch("field", "/playoffs/cfp/participants", {"year": s}, PlayoffParticipant, DataKind.SCHEDULE),
        }

    async def run(self) -> dict[str, Any]:
        with paced_calls():
            parts = await self._fetch()
        missing = [name for name in ("teams", "games") if not parts[name].ok]
        if missing:
            raise JobFailed("CFBD data missing: " + "; ".join(f"{n}: {parts[n].error or 'no answer'}" for n in missing))
        try:
            grid = load_grid(self.grid_path)
        except (OSError, ValueError) as exc:
            raise JobFailed(f"The map's grid could not be read from {self.grid_path}: {exc}") from exc
        try:
            enrollment = read_enrollment(self.enrollment_path)
        except ImperialismError as exc:
            raise JobFailed(str(exc)) from exc
        fbs: dict[str, dict[str, Any]] = {}
        campuses: dict[str, tuple[float, float]] = {}
        for t in parts["teams"].records:
            if not isinstance(t.school, str) or not t.school:
                continue
            fbs[t.school] = {"id": t.id, "abbreviation": t.abbreviation, "conference": t.conference, "color": t.color, "altColor": t.alternate_color}
            loc = t.location if isinstance(t.location, dict) else {}
            lat, lon = loc.get("latitude"), loc.get("longitude")
            if isinstance(lat, (int, float)) and isinstance(lon, (int, float)) and not isinstance(lat, bool) and not isinstance(lon, bool):
                campuses[t.school] = (float(lat), float(lon))
        if not fbs:
            raise JobFailed(f"CFBD's FBS team list for {self.season} is empty")
        field = [(p.team.school, p.seed) for p in parts["field"].records if p.team is not None and isinstance(p.team.school, str) and isinstance(p.seed, int)] if parts["field"].ok else None
        started = time.perf_counter()
        try:
            season = Season(grid, enrollment, fbs, campuses, self.client._clock())
            key = season.start_key(grid_version(self.grid_path))
            season.replay(parts["games"].records, parts["postseason"].records if parts["postseason"].ok else [], field, "/playoffs/cfp/participants", self.store.load_start(key))
            if season.dealt:
                self.store.save_start(key, season.start)
        except ImperialismError as exc:
            raise JobFailed(str(exc)) from exc
        seconds = time.perf_counter() - started
        week = latest_week(parts["games"].records, set(fbs))
        table = build_table(season, fbs, week, {name: _source(part) for name, part in parts.items()}, grid_version(self.grid_path))
        try:
            self.store.save(table)
        except OSError as exc:
            raise JobFailed(f"The map could not be written to {self.store.path}: {exc}") from exc
        moved = sum(e["cellsMoved"] for e in season.events)
        rules = Counter(e["rule"] for e in season.events)
        log.info("Imperialism Map: %d teams, %d snapshots, %d cells moved (%s), replayed in %.1f s; %s", len(fbs), len(season.snapshots), moved, ", ".join(f"{k} {v}" for k, v in sorted(rules.items())), seconds, "; ".join(season.notes))
        message = f"{len(fbs)} teams, {len(season.snapshots)} snapshots through {season.snapshots[-1].label}, {moved:,} cells moved, {'dealt and ' if season.dealt else ''}replayed in {seconds:.1f} s" + (f"; {season.notes[-1]}" if season.notes else "")
        return {"week": week, "message": message, "snapshots": len(season.snapshots), "cellsMoved": moved, "seconds": round(seconds, 2)}


def build_grid_file(census: Path, out: Path = GRID_PATH) -> int:
    from app.services.imperialism_grid import build_grid, read_states

    with zipfile.ZipFile(census) as z:
        names = [n for n in z.namelist() if n.lower().endswith(".kml")]
        if len(names) != 1:
            print(f"{census.name}: expected one .kml inside, found {names}")
            return 1
        kml = z.read(names[0]).decode("utf-8")
    import json

    built = build_grid(read_states(kml))
    out.write_text(json.dumps(built, separators=(",", ":")) + "\n", encoding="utf-8", newline="\n")
    print(f"{out}: {built['count']} cells ({built['lower48']} in the lower 48, {built['hawaii']} in Hawaii), side {built['side']}")
    return 0


if __name__ == "__main__":
    if "--build-grid" in sys.argv[1:]:
        parser = argparse.ArgumentParser(prog="python -m app.jobs.imperialism --build-grid")
        parser.add_argument("--build-grid", action="store_true")
        parser.add_argument("--census", required=True, help="cb_2024_us_state_20m.zip from the Census Bureau")
        parsed = parser.parse_args()
        raise SystemExit(build_grid_file(Path(parsed.census)))
    from app.jobs.cli import main

    raise SystemExit(main(NAME, sys.argv[1:]))

