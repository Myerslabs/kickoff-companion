"""The extra-call national lists (Phase 16, stream NV, owner answer 3 of 2026-09-28): every recruit's
national rank in a class, every FBS team's returning production, and every FBS team's blue-chip ratio.

Unlike the zero-call lists in national.py, these need nationwide pulls: one /recruiting/players pull
per class (about 4,000 recruits, 1.5 MB) and one /player/returning pull. The Game program, the team
pages and the roster fetch the blue-chip classes and returning production themselves (page_fetches,
PageRanks; owner decision 9, 2026-09-28) so their chips carry a national rank computed by the same
tables as the lists: five keys cold, shared by every page and list, then none until they expire. The blue-chip ratio reads the same four class pulls the
recruit lists read, so the whole set is six keys (verified against the recordings of 2026-09-28,
tests/fixtures/cfbd/recruiting_players_national_<year>.json and player_returning_national.json):

    recruit:<year>        /recruiting/players {year}            a class still recruiting (after this
                                                                 season): RECRUITING, kept 7 days; a
                                                                 signed class: HISTORY, kept 30 days
    bluechip:ratio        the four classes up to this season     as above (all four are signed classes)
    returning:<key>       /player/returning {year: season}       HISTORY, kept 30 days (a yearly figure)

Every fetch goes through the NationalService's players PartFetcher, so through the client's cache,
circuit breaker and quota guard; a refused or failed pull is a part error (stale data when the cache
has any), never a crash. Years are limited to the five recorded classes (season - 3 to season + 1)
before anything is fetched.

This module imports nothing from national.py at load time (national.py, players.py and program.py
import it), so the key helpers below can be used by any payload builder without a cycle."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from app.cache import DataKind
from app.cfbd.models import Recruit, ReturningProduction
from app.services.profiles import rank_teams, ranked_list
from app.services.stats_extra import BLUE_CHIP_CLASSES, blue_chip, num

if TYPE_CHECKING:  # pragma: no cover - types only
    from app.services.national import NationalService, Ranked, Request
    from app.services.parts import Part, PartFetcher

CLASSES_BACK = 3  # the oldest recruit list: season - 3 (the recorded five classes run to season + 1)
CLASSES_AHEAD = 1
BLUECHIP_METRIC = "bluechip:ratio"
RECRUIT_POPULATION = "class recruits with a 247Sports composite rank"

# (key, label, ReturningProduction attribute, format). Keys and labels follow returning_block and the
# glossary aliases, so a hint marks the list's label and a payload key names its list.
RETURNING: list[tuple[str, str, str, str]] = [
    ("percentPPA", "Returning production (PPA)", "percent_ppa", "pct"),
    ("percentPassing", "Returning passing", "percent_passing_ppa", "pct"),
    ("percentReceiving", "Returning receiving", "percent_receiving_ppa", "pct"),
    ("percentRushing", "Returning rushing", "percent_rushing_ppa", "pct"),
    ("usage", "Returning usage", "usage", "pct"),
    ("passingUsage", "Returning passing usage", "passing_usage", "pct"),
    ("receivingUsage", "Returning receiving usage", "receiving_usage", "pct"),
    ("rushingUsage", "Returning rushing usage", "rushing_usage", "pct"),
    ("totalPPA", "Returning PPA, total", "total_ppa", "1f"),
]
RETURNING_BY_KEY = {spec[0]: spec for spec in RETURNING}


# --- keys for the page payloads (no fetch, no import of national.py) ---------------------------------------


def recruit_years(season: int) -> range:
    return range(season - CLASSES_BACK, season + CLASSES_AHEAD + 1)


def recruit_metric(year: Any, season: int) -> str | None:
    """The recruit list of a class, or None for a class outside the five the app lists (a fifth-year
    player's class, a missing year)."""
    if isinstance(year, bool) or not isinstance(year, int) or year not in recruit_years(season):
        return None
    return f"recruit:{year}"


def returning_metrics() -> dict[str, str]:
    """{returning_block key: its list}; national.py's no-dead-chip test reads a `metrics` dict like this."""
    return {key: f"returning:{key}" for key, *_ in RETURNING}


# --- the registry -------------------------------------------------------------------------------------------


def spec(metric: str, season: int) -> dict[str, Any] | None:
    """The Metric fields of an extra-call list, or None when the key is not one (national.resolve
    builds the Metric; the key's shape is already checked there)."""
    family, _, rest = metric.partition(":")
    if family == "recruit" and rest.isdigit() and recruit_metric(int(rest), season):
        return {"key": metric, "family": "recruit", "id": rest, "label": "Recruit rank", "format": "rating100", "higher": True, "unit": "player", "scopes": ("national",), "population": f"{rest} {RECRUIT_POPULATION}", "rank_source": "cfbd", "value_label": "Rating"}
    if metric == BLUECHIP_METRIC:
        first = season - BLUE_CHIP_CLASSES + 1
        return {"key": metric, "family": "bluechip", "id": "ratio", "label": "Blue-chip ratio", "format": "pct", "higher": True, "population": f"FBS teams with a signee in the {first} to {season} classes"}
    if family == "returning" and rest in RETURNING_BY_KEY:
        _key, label, _attr, fmt = RETURNING_BY_KEY[rest]
        return {"key": metric, "family": "returning", "id": rest, "label": label, "format": fmt, "higher": True, "population": "FBS teams"}
    return None


# --- fetches: one key per class and one for returning production -------------------------------------------


def class_kind(year: int, season: int) -> DataKind:
    """A class still signing players (any class after this season's) changes weekly; a signed class
    does not, and is kept a month."""
    return DataKind.RECRUITING if year > season else DataKind.HISTORY


def fetch_class(fetcher: PartFetcher, year: int, season: int) -> Awaitable[Part]:
    return fetcher.fetch(f"recruitsNational_{year}", "/recruiting/players", {"year": year}, Recruit, class_kind(year, season))


def fetch_returning(fetcher: PartFetcher, season: int) -> Awaitable[Part]:
    return fetcher.fetch("returningNational", "/player/returning", {"year": season}, ReturningProduction, DataKind.HISTORY)


def _rank(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


# --- builders (registered in national.FAMILIES) ---------------------------------------------------------------


async def recruit_list(service: NationalService, req: Request, parts: dict[str, Part], meta: dict[str, dict[str, Any]]) -> Ranked:
    """Every ranked recruit of one class in CFBD's composite order; the service sends the top 100
    and every one of our commits below the cut. An unranked recruit is counted, never listed."""
    from app.services.national import Ranked, _tied

    year = int(req.metric.id)
    part = await fetch_class(service.players_fetcher, year, service.season)
    parts[part.name] = part
    rows: list[dict[str, Any]] = []
    unranked = 0
    for r in part.records:
        rank = _rank(r.ranking)
        if rank is None:
            unranked += 1
            continue
        stars = r.stars if isinstance(r.stars, int) and not isinstance(r.stars, bool) and 1 <= r.stars <= 5 else None
        hometown = ", ".join(p for p in (_text(r.city), _text(r.state_province)) if p) or None
        rows.append({
            "rank": rank,
            "playerId": _text(r.athlete_id) or r.id,
            "recruitId": r.id,
            "player": _text(r.name),
            "position": _text(r.position),
            "team": _text(r.committed_to),
            "conference": None,
            "value": round(v, 4) if (v := num(r.rating)) is not None else None,
            "detail": {"stars": stars, "highSchool": _text(r.school), "hometown": hometown, "type": _text(r.recruit_type)},
        })
    rows.sort(key=lambda row: (row["rank"], row["player"] or ""))
    _tied(rows)
    return Ranked(rows, len(rows), unranked, None, part.ok, rank_source="cfbd", note=None if rows or not part.ok else f"CFBD has no ranked recruit in the {year} class yet.")


def _team_listing(service: NationalService, req: Request, values: dict[str, float], own: dict[str, str], meta: dict[str, dict[str, Any]], population: set[str], digits: int, detail: Callable[[str], dict[str, Any]] | None = None) -> tuple[list[dict[str, Any]], int, int, str | None, set[str]]:
    """Rank one value per team, nationally or inside a conference, as the zero-call team families do."""
    from app.services.national import _team_rows

    def conference_of(team: str) -> str | None:
        return own.get(team) or meta.get(team, {}).get("conference")

    conference = service._scope_conference(req, conference_of)
    nat_ranks, _ = rank_teams(values, req.metric.higher)
    scoped = {t: v for t, v in values.items() if conference_of(t) == conference} if conference else values
    listing = ranked_list(scoped, req.metric.higher, None if conference else nat_ranks)
    rows = _team_rows(listing, conference_of, digits, nat_ranks if conference else None, detail)
    pool = {t for t in population if conference is None or conference_of(t) == conference}
    conferences = {c for c in (conference_of(t) for t in population) if c}
    return rows, len(listing), max(0, len(pool) - len(listing)), conference, conferences


# --- the tables behind both the lists and the page chips (one computation, so a chip and its list agree) ----


def bluechip_years(season: int) -> list[int]:
    return list(range(season - BLUE_CHIP_CLASSES + 1, season + 1))


def bluechip_table(class_parts: list[Part], years: list[int], fbs: set[str] | None) -> tuple[dict[str, dict[str, Any]], dict[str, float], set[str], bool]:
    """(blocks, values, population, complete): every FBS team's blue_chip() block from the four nationwide
    class pulls, counted exactly as stats_extra.blue_chip counts one team's (all signees of each class,
    four and five stars blue). Empty unless every class loaded (a missing class would skew the ratio)."""
    by_team: dict[str, dict[int, list[Recruit]]] = defaultdict(lambda: {y: [] for y in years})
    for year, part in zip(years, class_parts, strict=True):
        for r in part.records:
            school = _text(getattr(r, "committed_to", None))
            if school:
                by_team[school][year].append(r)
    complete = bool(class_parts) and all(part.ok for part in class_parts)
    population = set(fbs) if fbs else set(by_team)
    blocks = {team: blue_chip(by_team[team]) for team in population if team in by_team} if complete else {}
    values = {team: b["ratio"] for team, b in blocks.items() if b["ratio"] is not None}
    return blocks, values, population, complete


def returning_table(part: Part, attr: str, fbs: set[str] | None) -> tuple[dict[str, float], dict[str, str], set[str]]:
    """(values, conferences, population) of one returning-production figure for every FBS team."""
    records = [r for r in part.records if _text(getattr(r, "team", None))]
    population = set(fbs) if fbs else {r.team for r in records}
    values: dict[str, float] = {}
    own: dict[str, str] = {}
    for r in records:
        if r.team not in population:
            continue
        if _text(r.conference):
            own[r.team] = r.conference.strip()
        value = num(getattr(r, attr, None))
        if value is not None:
            values[r.team] = value
    return values, own, population


def national_ranks(values: dict[str, float], higher: bool = True) -> dict[str, dict[str, Any]]:
    """{team: {rank, of, tied}} over every value, the national list's own rule (ties share a rank)."""
    listing = ranked_list(values, higher)
    of = len(listing)
    return {team: {"rank": rank, "of": of, "tied": tied} for team, _value, rank, tied in listing}


# --- the page chips: the same pulls through a page's own fetcher, ranked by the same tables -----------------


def page_fetches(fetcher: PartFetcher, season: int, *, returning: bool = True) -> list[Awaitable[Part]]:
    """The nationwide pulls behind the blue-chip (and returning-production) chips on a page, with the list
    builders' own (endpoint, params, kind), so pages and lists share one cache: five keys cold, then none."""
    out = [fetch_class(fetcher, y, season) for y in bluechip_years(season)]
    if returning:
        out.append(fetch_returning(fetcher, season))
    return out


class PageRanks:
    """The national rank of a team's blue-chip ratio and returning-production figures, from the parts a page
    fetched with page_fetches. A part that failed (or was refused by the quota guard) leaves its ranks None:
    the value still shows, without a chip, and the envelope reports the part."""

    def __init__(self, parts: dict[str, Part], season: int, fbs: set[str] | None) -> None:
        years = bluechip_years(season)
        class_parts = [parts.get(f"recruitsNational_{y}") for y in years]
        self.bluechip: dict[str, dict[str, Any]] = {}
        if all(p is not None for p in class_parts):
            _blocks, values, _population, _complete = bluechip_table(class_parts, years, fbs)
            self.bluechip = national_ranks(values)
        self.returning: dict[str, dict[str, dict[str, Any]]] = {}
        part = parts.get("returningNational")
        if part is not None and part.ok:
            for key, _label, attr, _fmt in RETURNING:
                values, _own, _population = returning_table(part, attr, fbs)
                self.returning[key] = national_ranks(values)

    @staticmethod
    def _rank(table: dict[str, dict[str, Any]], team: str | None) -> dict[str, Any]:
        found = table.get(team or "") or {}
        return {"rank": found.get("rank"), "of": found.get("of"), "tied": bool(found.get("tied"))}

    def bluechip_block(self, block: dict[str, Any] | None, team: str | None) -> dict[str, Any] | None:
        """A blue_chip() block with its list key and national rank (None when the pulls are not in)."""
        if block is None:
            return None
        found = self._rank(self.bluechip, team)
        return {**block, "metric": BLUECHIP_METRIC, "nationalRank": found["rank"], "nationalOf": found["of"], "tied": found["tied"]}

    def returning_block(self, block: dict[str, Any] | None, team: str | None) -> dict[str, Any] | None:
        """A returning_block() with `metrics` (the list of each figure) and `ranks` ({key: {rank, of, tied}})."""
        if block is None:
            return None
        ranks = {key: self._rank(self.returning.get(key, {}), team) for key, *_ in RETURNING}
        return {**block, "metrics": returning_metrics(), "ranks": ranks}


# --- builders (registered in national.FAMILIES) ---------------------------------------------------------------


async def bluechip_list(service: NationalService, req: Request, parts: dict[str, Part], meta: dict[str, dict[str, Any]]) -> Ranked:
    """Every FBS team's blue-chip ratio over the last four signed classes."""
    from app.services.national import Ranked

    years = bluechip_years(service.season)
    got = await asyncio.gather(*(fetch_class(service.players_fetcher, y, service.season) for y in years))
    for part in got:
        parts[part.name] = part
    blocks, values, population, complete = bluechip_table(list(got), years, set(meta) or None)

    def detail(team: str) -> dict[str, Any]:
        b = blocks.get(team) or {}
        return {"detail": {"blueChips": b.get("blueChips"), "signees": b.get("signees")}}

    rows, of, unranked, conference, conferences = _team_listing(service, req, values, {}, meta, population, 3, detail)
    note = None if complete else "One of the four classes did not load, so no ratio is shown; the app asks again on the next visit."
    return Ranked(rows, of, unranked, conference, complete, note=note, conferences=conferences)


async def returning_list(service: NationalService, req: Request, parts: dict[str, Part], meta: dict[str, dict[str, Any]]) -> Ranked:
    """Every FBS team's share of last season's production that returns (CFBD's figures), ranked
    more-returning first."""
    from app.services.national import Ranked

    part = await fetch_returning(service.players_fetcher, service.season)
    parts[part.name] = part
    _key, _label, attr, fmt = RETURNING_BY_KEY[req.metric.id]
    values, own, population = returning_table(part, attr, set(meta) or None)
    rows, of, unranked, conference, conferences = _team_listing(service, req, values, own, meta, population, 1 if fmt == "1f" else 3)
    return Ranked(rows, of, unranked, conference, part.ok, conferences=conferences)


Builder = Callable[..., Awaitable["Ranked"]]
FAMILIES: dict[str, Builder] = {"recruit": recruit_list, "bluechip": bluechip_list, "returning": returning_list}
