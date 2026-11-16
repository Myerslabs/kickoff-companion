"""Talent Edge (FEAT-16, Feature Set v2 Phase A, owner 2026-10-30): how talented every FBS roster is, position group by
position group, judged by how each listed player was rated coming out of high school.

Each roster player gets his original 247 composite from his recruit record (CFBD's `recruitIds`, looked up in the
nationwide classes, so a transfer's record filed under his first school is found). The transfer portal flags who
came in by transfer and fills the rating for a player with no recruit record. A player found nowhere is unrated.
The groups are the spec's seven (QB, RB, WR, TE, OL, FRONT7, SECONDARY) and three roll-ups (O, D, TOT); the
specialists, ATH and unknown codes count in the roster but in no group.

The numbers per group: listed, rated, average rating and stars of the rated, years since signing (from the recruit
class, so a transfer counts from high school), blue chips as a share of the RATED players (a deliberate break from
the depth-chart ratio: a whole roster's walk-ons would sink every team's share), unrated and transfers. Every
group is ranked among the FBS teams with a rated player there, with a percentile (100 first, 0 last): the
spider draws the percentile (owner 2026-10-30: group averages bunch between 0.89 and 0.95, so raw ratings on a
fixed scale hide the gaps).

    group_of(position) -> group or None                 the spec's table (A.4)
    name_key(first, last) -> str                        lowercase letters only; Jr, Sr, II to V dropped
    match_players(roster, recruits, portal, season)     -> (PlayerTalent list, problems)
    compute_group_metrics(players, season) -> GroupMetrics    pure: the seam a depth chart would filter for (A.8)
    build_table(players, talent, teams, season, week, sources) -> dict    every team, ranked; the job's output
    TalentEdgeStore(data_dir, season)                   data/season/<year>/talent-edge.json and talent-edge-players.json
    run_state(data_dir, season) -> (last good run, last run)    from data/jobs.json, read only
    unavailable_words(season, good, last) -> str        why there is no table: the spec's "unavailable since <date>: <reason>"
    program_block(store, data_dir, us, them) -> dict    the Pre-Game Program's band: both teams, the unit matchups, or why not

Nothing here calls CFBD: the job (app/jobs/talent_edge.py) fetches and hands the records in."""

from __future__ import annotations

import json
import logging
import math
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.jobs import last_of, read_runs
from app.services.answers import atomic_write
from app.services.profiles import rank_teams

log = logging.getLogger("kickoff.talent_edge")

FORMAT = 1
GROUPS = ("QB", "RB", "WR", "TE", "OL", "FRONT7", "SECONDARY")
ROLLUPS = {"O": ("QB", "RB", "WR", "TE", "OL"), "D": ("FRONT7", "SECONDARY"), "TOT": GROUPS}
ALL_GROUPS = (*GROUPS, *ROLLUPS)
POSITIONS: dict[str, tuple[str, ...]] = {
    "QB": ("QB",),
    "RB": ("RB", "FB", "HB", "TB"),
    "WR": ("WR",),
    "TE": ("TE",),
    "OL": ("OL", "OT", "OG", "C", "G", "T", "IOL"),
    "FRONT7": ("DL", "DE", "DT", "NT", "NG", "EDGE", "LB", "ILB", "OLB", "MLB"),
    "SECONDARY": ("DB", "CB", "S", "SAF", "FS", "SS", "NB", "STAR"),
}
GROUP_OF = {code: group for group, codes in POSITIONS.items() for code in codes}
EXCLUDED = frozenset({"K", "P", "LS", "PK", "KR", "PR", "ATH"})
BLUE_CHIP_STARS = 4
PORTAL_SEASONS = 3  # S-2 .. S
CLASS_YEARS = 7  # the recruiting classes S-6 .. S
CROSS_UNITS = (("WR", "SECONDARY"), ("OL", "FRONT7"), ("RB", "FRONT7"))
SOURCES = ("recruit_id", "portal", "none")

_SUFFIX = re.compile(r"\b(jr|sr|ii|iii|iv|v)\b\.?")


def class_years(season: int) -> list[int]:
    return list(range(season - CLASS_YEARS + 1, season + 1))


def portal_years(season: int) -> list[int]:
    return list(range(season - PORTAL_SEASONS + 1, season + 1))


def group_of(position: Any) -> str | None:
    """The group of a CFBD position code (trimmed, any case), or None for a specialist, ATH or an unknown code."""
    code = position.strip().upper() if isinstance(position, str) else ""
    return GROUP_OF.get(code)


def position_code(position: Any) -> str:
    return position.strip().upper() if isinstance(position, str) else ""


def name_key(first: Any, last: Any) -> str:
    """The spec's normalized name (A.3): accents folded, lowercase, the suffixes Jr, Sr, II, III, IV and V dropped,
    then letters only, so apostrophes, hyphens, periods and doubled spaces never decide a match. The same rule as
    the roster's portal match (app/services/depth2.py)."""
    text = f"{first if isinstance(first, str) else ''} {last if isinstance(last, str) else ''}"
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    text = _SUFFIX.sub(" ", text)
    return re.sub(r"[^a-z]", "", text)


def _rating(value: Any) -> float | None:
    """A 247 composite: a finite number above 0 and at most 1, else None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) and 0 < number <= 1 else None


def _stars(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if 1 <= value <= 5 else None


def _year(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and 1900 < value < 2100 else None


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


# --- matching ------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class PlayerTalent:
    """One listed player as Talent Edge sees him. `rating` and `stars` come from the recruit record when it has them,
    else the portal; `recruit_year` only from a recruit record; `source` names where the rating came from."""

    player_id: str
    team: str
    name: str
    position: str
    group: str | None
    rating: float | None
    stars: int | None
    recruit_year: int | None
    source: str  # "recruit_id", "portal" or "none"
    is_transfer: bool


def _recruit_for(ids: Any, recruits: dict[str, Any]) -> Any | None:
    """The recruit record among the player's ids with the latest class (the spec's tie: greatest year), then the
    smallest id so the pick never depends on CFBD's order."""
    found = []
    for raw in ids if isinstance(ids, list) else []:
        key = str(raw).strip() if isinstance(raw, (str, int)) and not isinstance(raw, bool) else ""
        if key and key in recruits:
            found.append(recruits[key])
    if not found:
        return None
    return max(found, key=lambda r: (_year(getattr(r, "year", None)) or 0, -_id_order(getattr(r, "id", ""))))


def _id_order(value: Any) -> int:
    text = str(value)
    return int(text) if text.lstrip("-").isdigit() else 0


def portal_by_team(portal: list[Any], seasons: list[int]) -> dict[str, dict[str, Any]]:
    """{destination: {name key: the latest move in}} over the portal seasons asked for. A later transfer date wins;
    an entry with no date sorts first, so any dated move replaces it."""
    allowed = set(seasons)
    out: dict[str, dict[str, Any]] = defaultdict(dict)
    rows = [t for t in portal if _year(getattr(t, "season", None)) in allowed and _text(getattr(t, "destination", None))]
    rows.sort(key=lambda t: (str(getattr(t, "transfer_date", None) or ""), _year(getattr(t, "season", None)) or 0, name_key(getattr(t, "first_name", None), getattr(t, "last_name", None))))
    for t in rows:
        key = name_key(getattr(t, "first_name", None), getattr(t, "last_name", None))
        if key:
            out[_text(t.destination) or ""][key] = t
    return out


def match_players(roster: list[Any], recruits: dict[str, Any], portal: list[Any], season: int, fbs: set[str] | None = None) -> tuple[list[PlayerTalent], list[str]]:
    """Every listed player of an FBS team (all of them when `fbs` is None) matched by the spec's rules (A.3):

    1. a recruit record by id, the latest class first: rating, stars and class year from it;
    2. the portal by destination and name over the last three seasons: the player is a transfer, and with no
       recruit rating the portal's rating and stars are used (the class year stays unknown);
    3. nothing: unrated.

    Two players of one team with the same name key are never matched to the portal (a wrong transfer is worse than
    a missed one); both keep their recruit match. A record with no id or no team is skipped and named in the
    problems, never guessed at. The result is sorted by team, then player id."""
    problems: list[str] = []
    transfers = portal_by_team(portal, portal_years(season))
    by_team: dict[str, list[Any]] = defaultdict(list)
    for p in roster:
        team = _text(getattr(p, "team", None))
        pid = _text(str(getattr(p, "id", "") or ""))
        if team is None or pid is None:
            problems.append(f"roster record without a team or id: {getattr(p, 'first_name', None)!r} {getattr(p, 'last_name', None)!r} team={team!r}")
            continue
        if fbs is not None and team not in fbs:
            continue
        by_team[team].append(p)
    players: list[PlayerTalent] = []
    for team in sorted(by_team):
        listed: dict[str, Any] = {}
        for p in sorted(by_team[team], key=lambda r: (str(r.id).strip(), name_key(r.first_name, r.last_name), position_code(r.position))):
            pid = str(p.id).strip()
            if pid in listed:
                problems.append(f"{team}: player id {pid} listed twice; the second is skipped")
                continue
            listed[pid] = p
        keys = Counter(name_key(p.first_name, p.last_name) for p in listed.values())
        twins = {k for k, n in keys.items() if k and n > 1}
        for k in sorted(twins):
            problems.append(f"{team}: {keys[k]} players share the name key {k!r}; none of them is matched to the portal")
        moves = transfers.get(team, {})
        for pid, p in listed.items():
            key = name_key(p.first_name, p.last_name)
            recruit = _recruit_for(getattr(p, "recruit_ids", None), recruits)
            move = moves.get(key) if key and key not in twins else None
            rating = _rating(getattr(recruit, "rating", None)) if recruit is not None else None
            stars = _stars(getattr(recruit, "stars", None)) if recruit is not None else None
            year = _year(getattr(recruit, "year", None)) if recruit is not None else None
            source = "recruit_id" if rating is not None else "none"
            if rating is None and move is not None and _rating(getattr(move, "rating", None)) is not None:
                rating = _rating(move.rating)
                stars = _stars(getattr(move, "stars", None))
                source = "portal"
            name = " ".join(part for part in (_text(p.first_name), _text(p.last_name)) if part) or pid
            players.append(PlayerTalent(pid, team, name, position_code(p.position), group_of(p.position), rating, stars if rating is not None else None, year, source, move is not None))
    return players, problems


# --- the numbers ---------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class GroupMetrics:
    count: int
    rated_count: int
    avg_rating: float | None
    avg_stars: float | None
    avg_years: float | None
    bcr_pct: float | None
    unrated_count: int
    transfer_count: int

    def as_json(self) -> dict[str, Any]:
        return {
            "count": self.count,
            "ratedCount": self.rated_count,
            "avgRating": self.avg_rating,
            "avgStars": self.avg_stars,
            "avgYears": self.avg_years,
            "bcrPct": self.bcr_pct,
            "unratedCount": self.unrated_count,
            "transferCount": self.transfer_count,
        }


def _mean(values: list[float], places: int) -> float | None:
    return round(math.fsum(values) / len(values), places) if values else None


def compute_group_metrics(players: list[PlayerTalent], season: int) -> GroupMetrics:
    """The spec's numbers (A.5) for whatever players are handed in. Pure: no files, no calls, no state, so a depth
    chart later only filters the list first (A.8). Averages are over the rated players; years since signing over
    the players with a recruit record's class; the blue-chip share is of the rated players."""
    rated = [p for p in players if p.rating is not None]
    stars = [float(p.stars) for p in rated if p.stars is not None]
    years = [float(season - p.recruit_year) for p in players if p.recruit_year is not None and p.recruit_year <= season]
    blue = sum(1 for p in rated if p.stars is not None and p.stars >= BLUE_CHIP_STARS)
    return GroupMetrics(
        count=len(players),
        rated_count=len(rated),
        avg_rating=_mean([p.rating for p in rated if p.rating is not None], 4),
        avg_stars=_mean(stars, 2),
        avg_years=_mean(years, 2),
        bcr_pct=round(100 * blue / len(rated), 1) if rated else None,
        unrated_count=len(players) - len(rated),
        transfer_count=sum(1 for p in players if p.is_transfer),
    )


def team_groups(players: list[PlayerTalent]) -> dict[str, list[PlayerTalent]]:
    """{group: players} for one team, the roll-ups included; players outside every group are in none."""
    grouped: dict[str, list[PlayerTalent]] = {g: [] for g in ALL_GROUPS}
    for p in players:
        if p.group is None:
            continue
        grouped[p.group].append(p)
    for rollup, members in ROLLUPS.items():
        grouped[rollup] = [p for g in members for p in grouped[g]]
    return grouped


def team_summary(players: list[PlayerTalent]) -> dict[str, int]:
    """The caveat line's counts (A.3): listed, rated by recruit record and by portal, unrated, transfers, and how
    many listed players fall in no group (specialists, ATH, unknown codes)."""
    by_source = Counter(p.source for p in players)
    rated = by_source["recruit_id"] + by_source["portal"]
    return {
        "roster": len(players),
        "rated": rated,
        "ratedByRecruit": by_source["recruit_id"],
        "ratedByPortal": by_source["portal"],
        "unrated": len(players) - rated,
        "transfers": sum(1 for p in players if p.is_transfer),
        "outsideGroups": sum(1 for p in players if p.group is None),
    }


def unknown_positions(players: list[PlayerTalent]) -> dict[str, int]:
    """{code: listed players} for codes neither in a group nor a known specialist (logged once a run, A.4)."""
    counts = Counter(p.position or "(none)" for p in players if p.group is None and p.position not in EXCLUDED)
    return dict(sorted(counts.items()))


def percentile(rank: int, of: int) -> int:
    """100 for the first of `of`, 0 for the last; ties share the rank's percentile."""
    if of <= 1:
        return 100
    return round(100 * (of - rank) / (of - 1))


def build_table(players: list[PlayerTalent], talent: dict[str, dict[str, Any]], teams: dict[str, dict[str, Any]], season: int, week: int | None, sources: dict[str, Any], problems: list[str] | None = None) -> dict[str, Any]:
    """The job's whole output for one season: every team's summary, 247 talent, and each group's numbers with its
    national rank and percentile by average rating (teams with no rated player in a group are unranked there).
    Teams sorted by name, groups in the spec's order, so the same inputs give the same bytes."""
    by_team: dict[str, list[PlayerTalent]] = defaultdict(list)
    for p in players:
        by_team[p.team].append(p)
    metrics: dict[str, dict[str, GroupMetrics]] = {}
    for team in sorted(by_team):
        grouped = team_groups(by_team[team])
        metrics[team] = {g: compute_group_metrics(grouped[g], season) for g in ALL_GROUPS}
    ranks: dict[str, tuple[dict[str, int], int]] = {}
    for g in ALL_GROUPS:
        values = {team: m[g].avg_rating for team, m in metrics.items() if m[g].avg_rating is not None}
        ranks[g] = rank_teams(values, higher_is_better=True)  # type: ignore[arg-type]
    out_teams: dict[str, Any] = {}
    for team in sorted(metrics):
        groups: dict[str, Any] = {}
        for g in ALL_GROUPS:
            row = metrics[team][g].as_json()
            table, of = ranks[g]
            rank = table.get(team)
            row.update({"rank": rank, "of": of if rank is not None else None, "pct": percentile(rank, of) if rank is not None else None})
            groups[g] = row
        identity = teams.get(team, {})
        out_teams[team] = {
            "abbreviation": identity.get("abbreviation"),
            "conference": identity.get("conference"),
            "color": identity.get("color"),
            "altColor": identity.get("altColor"),
            "summary": team_summary(by_team[team]),
            "talent": talent.get(team),
            "groups": groups,
        }
    unknown = unknown_positions(players)
    return {
        "format": FORMAT,
        "season": season,
        "computedWeek": week,
        "groups": list(GROUPS),
        "rollups": {k: list(v) for k, v in ROLLUPS.items()},
        "spider": {"axes": list(GROUPS), "value": "pct", "scale": [0, 100]},
        "sources": dict(sorted(sources.items())),
        "unknownPositions": unknown,
        "problems": sorted(problems or [])[:50],
        "problemCount": len(problems or []),
        "teams": out_teams,
    }


def player_rows(players: list[PlayerTalent]) -> dict[str, Any]:
    """Every matched player, compact (Phase C reads ours): {columns, teams: {team: [[...], ...]}}."""
    columns = ["id", "name", "position", "group", "rating", "stars", "recruitYear", "source", "transfer"]
    teams: dict[str, list[list[Any]]] = defaultdict(list)
    for p in sorted(players, key=lambda r: (r.team, r.player_id)):
        teams[p.team].append([p.player_id, p.name, p.position, p.group, p.rating, p.stars, p.recruit_year, p.source, p.is_transfer])
    return {"format": FORMAT, "columns": columns, "teams": dict(teams)}


def cross_units(a: dict[str, Any], b: dict[str, Any]) -> list[dict[str, Any]]:
    """The spec's six unit matchups (A.6): A's WR, OL and RB against B's Secondary, Front 7 and Front 7, then B's
    against A's. `a_group` is always A's group and `b_group` B's; `offense` says whose unit has the ball."""

    def value(team: dict[str, Any], group: str, key: str) -> Any:
        return ((team.get("groups") or {}).get(group) or {}).get(key)

    pairs = [("a", unit, against) for unit, against in CROSS_UNITS] + [("b", against, unit) for unit, against in CROSS_UNITS]
    return [
        {
            "offense": side,
            "a_group": a_group,
            "b_group": b_group,
            "a_rating": value(a, a_group, "avgRating"),
            "b_rating": value(b, b_group, "avgRating"),
            "a_pct": value(a, a_group, "pct"),
            "b_pct": value(b, b_group, "pct"),
        }
        for side, a_group, b_group in pairs
    ]


# --- the store -----------------------------------------------------------------------------------------------------


class TalentEdgeStore:
    """The job's two files for a season, read back by the answers. The table is kept in memory and re-read when the
    file changes on disk (the job writes it whole, so a reader sees the old file or the new one)."""

    def __init__(self, data_dir: Path, season: int) -> None:
        self.folder = Path(data_dir) / "season" / str(season)
        self.path = self.folder / "talent-edge.json"
        self.players_path = self.folder / "talent-edge-players.json"
        self.season = season
        self._cache: tuple[tuple[int, int], dict[str, Any]] | None = None

    def save(self, table: dict[str, Any], players: dict[str, Any]) -> None:
        """Both files, each written whole. The players go first, so a table on disk never points at missing rows."""
        self.folder.mkdir(parents=True, exist_ok=True)
        atomic_write(self.players_path, json.dumps(players, separators=(",", ":"), ensure_ascii=False) + "\n")
        atomic_write(self.path, json.dumps(table, indent=1, ensure_ascii=False) + "\n")
        self._cache = None

    def load(self) -> dict[str, Any] | None:
        try:
            info = self.path.stat()
            stamp = (info.st_mtime_ns, info.st_size)  # the size too: two writes inside one clock tick share a time on Windows
        except OSError:
            return None
        if self._cache is not None and self._cache[0] == stamp:
            return self._cache[1]
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            log.warning("Talent Edge's table could not be read (%s)", exc)
            return None
        if not isinstance(raw, dict) or raw.get("format") != FORMAT or not isinstance(raw.get("teams"), dict):
            log.warning("Talent Edge's table at %s is not one this build reads; it is left alone", self.path)
            return None
        self._cache = (stamp, raw)
        return raw

    def players(self, team: str) -> list[dict[str, Any]]:
        """One team's matched players as dicts (an empty list when the file is missing or unreadable)."""
        try:
            raw = json.loads(self.players_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        if not isinstance(raw, dict) or not isinstance(raw.get("columns"), list):
            return []
        columns = [str(c) for c in raw["columns"]]
        rows = (raw.get("teams") or {}).get(team) if isinstance(raw.get("teams"), dict) else None
        return [dict(zip(columns, row, strict=False)) for row in rows if isinstance(row, list)] if isinstance(rows, list) else []


JOB = "talent_edge"


def run_state(data_dir: Path, season: int) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    runs = read_runs(data_dir)
    return last_of(runs, JOB, season, "ok"), last_of(runs, JOB, season)


def unavailable_words(season: int, good: dict[str, Any] | None, last: dict[str, Any] | None) -> str:
    """Why there is no table to show, in the spec's words: unavailable since when, and the reason."""
    if last is not None and last.get("status") == "running":
        return f"Talent Edge for {season} is being worked out now (started {last.get('startedAt')})."
    if last is not None and last.get("status") == "failed" and good is None:
        return f"Talent Edge for {season} is unavailable since {last.get('startedAt')}: {last.get('message')}"
    if good is not None:
        return f"Talent Edge for {season} could not be read; the last good run finished {good.get('finishedAt')}."
    return f"Talent Edge for {season} has not been worked out yet. The server works it out on its first start with it, then Sundays from 6 AM."


def _row(table: dict[str, Any], school: str | None) -> dict[str, Any] | None:
    teams = table.get("teams") if isinstance(table.get("teams"), dict) else {}
    row = teams.get(school) if isinstance(school, str) else None
    return {"team": school, **row, "summaryLine": summary_line(row)} if isinstance(row, dict) else None


def program_block(store: TalentEdgeStore, data_dir: Path, us: str, them: str | None) -> dict[str, Any]:
    """FEAT-16's band on the Pre-Game Program (owner 2026-10-30: at the bottom, after his board): both teams' rows from the
    weekly table, the six unit matchups, when it was worked out and through which week. With no table, `available` is
    False and `message` says since when and why (the spec: never an empty chart). A side the table lacks (an FCS
    opponent) is named in `missing`; the matchups need both. A failure after the last good run is `lastFailure`."""
    good, last = run_state(data_dir, store.season)
    table = store.load()
    if table is None:
        return {"available": False, "season": store.season, "failed": bool(last and last.get("status") == "failed"), "message": unavailable_words(store.season, good, last)}
    a, b = _row(table, us), _row(table, them)
    failed = last if last is not None and last.get("status") == "failed" and good is not None else None  # the newest run failed: after the good one
    return {
        "available": True,
        "season": store.season,
        "computedWeek": table.get("computedWeek"),
        "computedAt": good.get("finishedAt") if good else None,
        "lastFailure": {"at": failed.get("startedAt"), "message": failed.get("message")} if failed else None,
        "of": len(table.get("teams") or {}),
        "us": a,
        "them": b,
        "missing": [name for name, row in ((us, a), (them, b)) if row is None and isinstance(name, str) and name],
        "cross": cross_units(a, b) if a and b else [],
    }


def summary_line(team_row: dict[str, Any] | None) -> str | None:
    """The one-line summary the map's hover card shows (A.7): "#8 talent · 0.92 avg · 63% BCR"."""
    if not isinstance(team_row, dict):
        return None
    talent = team_row.get("talent") if isinstance(team_row.get("talent"), dict) else {}
    tot = (team_row.get("groups") or {}).get("TOT") or {}
    parts = []
    if isinstance(talent.get("rank"), int):
        parts.append(f"#{talent['rank']} talent")
    if isinstance(tot.get("avgRating"), (int, float)):
        parts.append(f"{tot['avgRating']:.2f} avg")
    if isinstance(tot.get("bcrPct"), (int, float)):
        parts.append(f"{round(tot['bcrPct'])}% BCR")
    return " · ".join(parts) or None

