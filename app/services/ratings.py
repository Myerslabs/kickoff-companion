"""The ratings page (Phase 10, owner direction 2026-09-23: SP+ clickable, on its own page, with
the other ratings beside it): every FBS team's SP+ overall, offense, defense and special teams,
Elo, FPI and the team talent composite, each with a rank. Phase 13 adds CFBD's CORE rating, SRS,
opponent-adjusted EPA (WEPA), a strength of schedule worked out from SP+ (CFBD leaves SP+'s own
null in season), and conference SP+. All cached; the new ones are season-stat lifetimes.

Phase 16: the page is a pure function of its parts (ratings_table), the same rating tables the
chips and the national lists read; the nationalAverages pseudo-team is gone, and each rating
carries its own count and national-list metric key."""

from __future__ import annotations

import asyncio
from typing import Any

from app.cache import DataKind
from app.cfbd.client import CfbdClient
from app.cfbd.models import AdjustedTeamMetrics, ConferenceSP, Game, Team, TeamCoreRating, TeamElo, TeamFPI, TeamSP, TeamSRS, TeamTalent
from app.config import Settings
from app.services.depth2 import adjusted_rows, conference_rows, core_tables, more_ratings, sos_played, sos_table, srs_table
from app.services.parts import Assembled, Part, PartFetcher, assemble, statuses
from app.services.stats_extra import elo_table, fpi_tables, ratings_rows, real_teams, sp_tables, talent_table

# Each rating column of the page and the national list its chips open (Phase 16).
METRICS = {
    "sp": "rating:sp",
    "spOffense": "rating:spOffense",
    "spDefense": "rating:spDefense",
    "spSpecial": "rating:spSpecial",
    "sosPlayed": "rating:sosPlayed",
    "elo": "rating:elo",
    "fpi": "rating:fpi",
    "fpiSos": "rating:fpiSos",
    "fpiSor": "rating:fpiSor",
    "talent": "rating:talent",
    "core": "rating:core",
    "coreOffense": "rating:coreOffense",
    "coreDefense": "rating:coreDefense",
    "srs": "rating:srs",
    "adjEpa": "adjusted:epa",
    "adjEpaAllowed": "adjusted:epaAllowed",
}


def fbs_set(teams: list[Team]) -> set[str] | None:
    """The /teams/fbs schools, or None when that part failed (then nothing is filtered by it)."""
    schools = {t.school for t in teams if t.school}
    return schools or None


def ratings_table(parts: dict[str, Part], team: str, conference: str, season: int) -> dict[str, Any]:
    """The Ratings page's data from its parts; no fetching here."""
    fbs = fbs_set(parts["teams"].records)
    conferences = {t.school: t.conference for t in parts["teams"].records if t.school and t.conference}
    rows = ratings_rows(parts["sp"].records, parts["elo"].records, parts["fpi"].records, parts["talent"].records, conferences, fbs)
    sos = sos_played(parts["games"].records, real_teams(parts["sp"].records, fbs))  # the same numbers as sos_table
    extra = more_ratings(parts["core"].records, parts["srs"].records, parts["adjusted"].records, fbs)
    blank = {"value": None, "rank": None}
    for row in rows:
        row["sosPlayed"] = sos.get(row["team"])
        row.update({key: blank for key in ("core", "coreOffense", "coreDefense", "srs", "adjEpa", "adjEpaAllowed")} | extra.get(row["team"], {}))
    us = next((r for r in rows if r["team"] == team), None)
    sps, fpis, cores = sp_tables(parts["sp"].records, fbs), fpi_tables(parts["fpi"].records, fbs), core_tables(parts["core"].records, fbs)
    adjusted = adjusted_rows(parts["adjusted"].records)
    adj_of = {key: next((v[key]["of"] for v in adjusted.values() if v.get(key, {}).get("of")), None) for key in ("epa", "epaAllowed")}
    counts = {
        **{key: table.of for key, table in sps.items()},
        "sosPlayed": sos_table(parts["games"].records, parts["sp"].records, fbs).of,
        "elo": elo_table(parts["elo"].records, fbs).of,
        **{key: table.of for key, table in fpis.items()},
        "talent": talent_table(parts["talent"].records, fbs).of,
        **{key: table.of for key, table in cores.items()},
        "srs": srs_table(parts["srs"].records).of,
        "adjEpa": adj_of["epa"] or 0,
        "adjEpaAllowed": adj_of["epaAllowed"] or 0,
    }
    return {
        "season": season,
        "team": team,
        "conference": conference,
        "rows": rows,
        "us": us,
        "conferences": conference_rows(parts["conferences"].records),
        "published": {"core": bool(parts["core"].records), "srs": bool(parts["srs"].records), "adjusted": bool(parts["adjusted"].records)},
        # Phase 16: one count per rating, so each chip's "of" is its own population (SRS ranks all of Division I)
        "counts": counts,
        "metrics": METRICS,
    }


class RatingsService:
    def __init__(self, client: CfbdClient, settings: Settings) -> None:
        self.client = client
        self.settings = settings
        self.fetcher = PartFetcher(client, 5)

    async def parts(self) -> dict[str, Part]:
        """Every part of the page. The national lists ask through here too, with the same
        (endpoint, params, kind), so a list the page already loaded is a cache hit."""
        year = self.settings.season
        results = await asyncio.gather(
            self.fetcher.fetch("sp", "/ratings/sp", {"year": year}, TeamSP, DataKind.SEASON_STATS),
            self.fetcher.fetch("elo", "/ratings/elo", {"year": year}, TeamElo, DataKind.SEASON_STATS),
            self.fetcher.fetch("fpi", "/ratings/fpi", {"year": year}, TeamFPI, DataKind.SEASON_STATS),
            self.fetcher.fetch("talent", "/talent", {"year": year}, TeamTalent, DataKind.SEASON_STATS),
            self.fetcher.fetch("teams", "/teams/fbs", {"year": year}, Team, DataKind.TEAMS),
            self.fetcher.fetch("games", "/games", {"year": year}, Game, DataKind.SCHEDULE),
            self.fetcher.fetch("core", "/ratings/core", {"year": year}, TeamCoreRating, DataKind.SEASON_STATS),
            self.fetcher.fetch("srs", "/ratings/srs", {"year": year}, TeamSRS, DataKind.SEASON_STATS),
            self.fetcher.fetch("adjusted", "/wepa/team/season", {"year": year}, AdjustedTeamMetrics, DataKind.SEASON_STATS),
            self.fetcher.fetch("conferences", "/ratings/sp/conferences", {"year": year}, ConferenceSP, DataKind.SEASON_STATS),
        )
        return {part.name: part for part in results}

    async def ratings(self) -> Assembled:
        parts = await self.parts()
        data = ratings_table(parts, self.settings.team, self.settings.conference, self.settings.season)
        data["parts"] = statuses(parts, self.client._clock())
        return assemble(data, parts)
