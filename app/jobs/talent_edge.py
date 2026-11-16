"""The Talent Edge job (FEAT-16): every FBS roster, the seven recruiting classes before it, three seasons of the
portal and 247's team talent, matched and measured by app/services/talent_edge.py and kept in
data/season/<year>/talent-edge.json (and talent-edge-players.json).

    python -m app.jobs.talent_edge [--season 2026] [--url http://127.0.0.1:8642]

Calls, all through the client, its cache and the quota guard, paced to the month's target: one /roster for every
FBS team at once (classification=fbs, checked 2026-10-30: 15,806 players of all 138 teams in one answer), the
nationwide /recruiting/players classes S-6 to S (shared with the national lists' keys, a signed class kept a
month) and the junior-college classes of the same years (measured 2026-10-30: 652 roster players' ids were in no
high-school class, and the 2024 and 2025 JUCO classes alone held 307 of them), /player/portal for S-2 to S,
/talent, /teams/fbs, and the season's /games for the week. A cached answer
is used as it is, so a run in the same week costs nothing. Any of them missing (no answer and nothing cached)
fails the run and the previous files stay."""

from __future__ import annotations

import logging
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from app.cache import DataKind
from app.cfbd.client import CfbdClient, paced_calls
from app.cfbd.models import Game, PlayerTransfer, Recruit, RosterPlayer, Team, TeamTalent
from app.jobs import JobFailed, JobSkipped
from app.services.national_extra import class_kind, fetch_class
from app.services.parts import Part, PartFetcher, iso
from app.services.stats_extra import talent_lookup
from app.services.talent_edge import TalentEdgeStore, build_table, class_years, match_players, player_rows, portal_years, unknown_positions

log = logging.getLogger("kickoff.jobs.talent_edge")

NAME = "talent_edge"


def latest_week(games: list[Any], fbs: set[str]) -> int | None:
    """The greatest regular-season week with a completed game that has an FBS side, else None."""
    weeks = [
        g.week
        for g in games
        if getattr(g, "completed", False) is True
        and isinstance(getattr(g, "week", None), int)
        and str(getattr(g, "season_type", None) or "regular") == "regular"
        and (getattr(g, "home_team", None) in fbs or getattr(g, "away_team", None) in fbs)
    ]
    return max(weeks) if weeks else None


def _source(part: Part) -> dict[str, Any]:
    fetched = part.fetched
    return {"fetchedAt": iso(fetched.fetched_at) if fetched else None, "stale": bool(fetched.stale) if fetched else None, "records": len(part.records), "skipped": part.skipped}


def _identity(team: Team) -> dict[str, Any]:
    return {"abbreviation": team.abbreviation, "conference": team.conference, "color": team.color, "altColor": team.alternate_color}


class TalentEdgeJob:
    def __init__(self, client: CfbdClient, data_dir: Path, season: int, fetcher: PartFetcher | None = None) -> None:
        self.client = client
        self.season = season
        self.fetcher = fetcher or PartFetcher(client)
        self.store = TalentEdgeStore(data_dir, season)

    async def _fetch(self) -> dict[str, Part]:
        s = self.season
        f = self.fetcher
        parts: dict[str, Part] = {
            "teams": await f.fetch("teams", "/teams/fbs", {"year": s}, Team, DataKind.TEAMS),
            "roster": await f.fetch("rosterFbs", "/roster", {"year": s, "classification": "fbs"}, RosterPlayer, DataKind.ROSTER),
            "talent": await f.fetch("talent", "/talent", {"year": s}, TeamTalent, DataKind.SEASON_STATS),
            "games": await f.fetch("games", "/games", {"year": s}, Game, DataKind.SCHEDULE),
        }
        for year in class_years(s):
            parts[f"class{year}"] = await fetch_class(f, year, s)
            parts[f"juco{year}"] = await f.fetch(f"recruitsJuco_{year}", "/recruiting/players", {"year": year, "classification": "JUCO"}, Recruit, class_kind(year, s))
        for year in portal_years(s):
            parts[f"portal{year}"] = await f.fetch(f"portal{year}", "/player/portal", {"year": year}, PlayerTransfer, DataKind.SEASON_STATS)
        return parts

    async def run(self) -> dict[str, Any]:
        before = self.client.quota.status(self.client._clock()).ledger_calls_this_month
        with paced_calls():
            parts = await self._fetch()
        missing = [name for name, part in parts.items() if not part.ok and name != "games"]
        if missing:
            reasons = "; ".join(f"{name}: {parts[name].error or 'no answer'}" for name in missing)
            raise JobFailed(f"CFBD data missing for {len(missing)} source{'s' if len(missing) != 1 else ''} ({reasons})")
        fbs = {t.school for t in parts["teams"].records if isinstance(t.school, str) and t.school}
        if not fbs:
            raise JobFailed(f"CFBD's FBS team list for {self.season} is empty")
        recruits = {}
        for year in class_years(self.season):
            for r in [*parts[f"class{year}"].records, *parts[f"juco{year}"].records]:
                key = str(r.id).strip()
                if key:
                    recruits[key] = r
        portal = [t for year in portal_years(self.season) for t in parts[f"portal{year}"].records]
        players, problems = match_players(parts["roster"].records, recruits, portal, self.season, fbs)
        if not players:
            # rollover R1 (2026-11-15): a new season's rosters come from CFBD in the summer; until then the job waits a week
            # (skipped) instead of failing the weekly run, which tried all three jobs again every three hours
            raise JobSkipped(f"CFBD has no {self.season} FBS roster yet; Talent Edge waits for it")
        listed = Counter(p.team for p in players)
        for school in sorted(fbs - set(listed)):
            problems.append(f"{school}: no players on CFBD's {self.season} FBS roster")
        for name, part in sorted(parts.items()):
            if part.skipped:
                problems.append(f"{name}: {part.skipped} record{'s' if part.skipped != 1 else ''} could not be read and were skipped ({'; '.join(part.problems[:2])})")
        unknown = unknown_positions(players)
        if unknown:
            log.warning("Talent Edge: position codes outside every group, left out of the groups: %s", ", ".join(f"{code} ({n})" for code, n in unknown.items()))
        for problem in problems[:20]:
            log.warning("Talent Edge: %s", problem)
        if len(problems) > 20:
            log.warning("Talent Edge: %d more problems (the first 50 are kept in the table)", len(problems) - 20)
        teams = {t.school: _identity(t) for t in parts["teams"].records if isinstance(t.school, str) and t.school in fbs}
        week = latest_week(parts["games"].records, fbs) if parts["games"].ok else None
        table = build_table(players, talent_lookup(parts["talent"].records, fbs), teams, self.season, week, {name: _source(part) for name, part in parts.items()}, problems)
        for school, row in table["teams"].items():
            s = row["summary"]
            log.info("Talent Edge %s: %d listed, %d rated by recruit record, %d by portal, %d unrated, %d transfers", school, s["roster"], s["ratedByRecruit"], s["ratedByPortal"], s["unrated"], s["transfers"])
        try:
            self.store.save(table, player_rows(players))
        except OSError as exc:
            raise JobFailed(f"The table could not be written to {self.store.path}: {exc}") from exc
        calls = max(self.client.quota.status(self.client._clock()).ledger_calls_this_month - before, 0)
        rated = sum(row["summary"]["rated"] for row in table["teams"].values())
        message = f"{len(table['teams'])} teams, {len(players)} players, {rated} rated, {calls} CFBD call{'s' if calls != 1 else ''}" + (f", {len(problems)} problem{'s' if len(problems) != 1 else ''} logged" if problems else "")
        return {"week": week, "message": message, "teams": len(table["teams"]), "players": len(players), "rated": rated, "calls": calls, "problems": len(problems)}


if __name__ == "__main__":
    from app.jobs.cli import main

    raise SystemExit(main(NAME, sys.argv[1:]))
