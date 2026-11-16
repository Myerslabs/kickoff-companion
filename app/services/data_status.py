"""What the status pill and its Data status card say (ENH-4, the owner's board of 2026-10-27,
"the status pill ALWAYS shows data age + server connected + how often the
band polls (e.g. AP poll weekly)"). For each band of a page: when its source changes, when the app looks, and how old the
app's copy is; for the pill, how often the page's lead band is checked. Nothing here calls CFBD: it reads the cache's and the publication
log's own records, the feeds', notes' and writing's files, and the schedules the app keeps in code (app/cache.py ttl_for,
app/cfbd/publish.py, app/services/readiness.py DUE_DAYS, the Claude schedule's days).

    SOURCES                      id -> Source: what changes it, and where its copy's time is kept
    PAGE_BANDS                   view -> [(band, source ids)]: the bands each page lists, in the page's order
    checks(source, local_now, game_day, live_seconds) -> (words, seconds)   seconds None: not a polled source
    cadence_words(seconds)       "every 12 s", "every 15 min", "hourly", "daily", "weekly"
    page_status(view, ctx)       {bands, cadenceSeconds, cadence}: the cadence is the lead band's (the first polled one)
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.cache import SATURDAY, THURSDAY
from app.services.readiness import part_due

log = logging.getLogger("kickoff.datastatus")

MINUTE = 60
HOUR = 3600
DAY = 86400
WEEK = 7 * DAY


@dataclass(frozen=True)
class Source:
    changes: str
    endpoints: tuple[str, ...] = ()  # cache endpoints: the newest fetch dates the copy
    published: bool = False  # date it by the publication log's last change (the poll came out Sunday), else the last fetch
    claude: str | None = None  # "notes", a notes part ("availability", "visitors", "lineups"), or a writing kind ("scout", "paper")


SOURCES: dict[str, Source] = {
    "scores": Source("as games end", ("/games", "/records", "/scoreboard")),
    "polls": Source("weekly, Sun about 2 PM", ("/rankings",), published=True),
    "ratings": Source("weekly, early in the week", ("/ratings/sp", "/ratings/elo", "/ratings/fpi", "/ratings/srs", "/ratings/core"), published=True),
    "stats": Source("after each game day", ("/stats/season", "/stats/season/advanced", "/stats/player/season", "/ppa/players/season", "/ppa/games"), published=True),
    "plays": Source("after each game day", ("/rushing/plays", "/passing/plays", "/ppa/games", "/player/usage"), published=True),
    "lines": Source("through the week", ("/lines",)),
    "weather": Source("through the day"),
    "media": Source("6 to 12 days ahead", ("/games/media",), published=True),
    "talent": Source("yearly; recruits weekly", ("/talent", "/recruiting/teams"), published=True),
    "roster": Source("through the season", ("/roster",)),
    "recruiting": Source("as players commit", ("/recruiting/players", "/recruiting/teams")),
    "history": Source("after each meeting", ("/teams/matchup",)),
    "headlines": Source("any time"),
    "articles": Source("as the publishers post"),  # FEAT-14: the whole stories and photos copied onto this computer
    "notes": Source("Claude, game week", claude="notes"),
    "availability": Source("Claude, Wed and Thu", claude="availability"),
    "visitors": Source("Claude, Friday", claude="visitors"),
    "lineups": Source("Claude, Monday", claude="lineups"),
    "scout": Source("Claude, Monday", claude="scout"),
    "recap": Source("Claude, the morning after", claude="recap"),  # the Post-Game stop (the line, Wave 3): What decided it
    "paper": Source("Claude, Thursday", claude="paper"),
    "editor": Source("Claude, as stories arrive", claude="editor"),  # FEAT-14 wave 4: the paper laid out by Claude Code
    "art": Source("Claude, 10 AM and 4 PM", claude="art"),  # FEAT-14 wave 4: drawings for stories with no photo
    "facts": Source("yearly"),
    "season_loads": Source("Claude, once a day when missing"),
    "numbers": Source("after each game day"),
    "talent_edge": Source("as rosters and classes change"),  # FEAT-16: the weekly job's table
    "blame": Source("Claude, the Sunday after each game"),  # FEAT-18: the Circle of Blame
    "imperialism": Source("as games end; worked out weekly"),  # FEAT-17: the weekly job's every-week map
    "trip": Source("each season; this game's times in game week"),  # ENH-15: Getting there, one stadium a run
    "picks": Source("Claude, Thursday afternoon"),  # FEAT-2: Picks of the week
    "live": Source("every play"),
    "finished": Source("settled after the final", ("/games/teams", "/games/players", "/game/box/advanced")),
}


def checks(source: str, local_now: datetime, *, game_day: bool = False, live_seconds: int = 12, ticker_seconds: int | None = None) -> tuple[str, int | None]:
    """(the card's words for when the app looks, the seconds between looks today; None when nothing is polled)."""
    weekend = THURSDAY <= local_now.weekday() <= SATURDAY or game_day
    quick = 15 * MINUTE if weekend else HOUR
    table: dict[str, tuple[str, int | None]] = {
        "scores": ("hourly; every 15 min Thu to Sat", quick),
        "polls": ("Sun, every 20 min until it is out", WEEK),
        "ratings": ("every 3 h from Sun until it moves", WEEK),
        "stats": ("4 AM the next morning", DAY),
        "plays": ("4 AM the next morning", DAY),
        "lines": ("hourly; every 15 min on game day", 15 * MINUTE if game_day else HOUR),
        "weather": ("every 3 h", 3 * HOUR),
        "media": ("4 AM and 4 PM", 12 * HOUR),
        "talent": ("Mon 4 AM", WEEK),
        "roster": ("weekly", WEEK),
        "recruiting": ("weekly", WEEK),
        "history": ("monthly", 30 * DAY),
        "headlines": ("every 30 min", 30 * MINUTE),
        "articles": ("as each new headline arrives", 30 * MINUTE),
        "notes": ("Mon to Fri, and 2 h before kickoff", None),
        "availability": ("Wednesday, Thursday", None),
        "visitors": ("Friday", None),
        "lineups": ("Monday", None),
        "scout": ("Monday", None),
        "paper": ("Thursday", None),
        "editor": ("every 2 h, 7 AM to 9 PM, when new stories came in", None),
        "art": ("10 AM and 4 PM, when a story needs one", None),
        "facts": ("yearly, by Claude", None),
        "season_loads": ("daily, by Claude", None),
        "numbers": ("nightly after 3 AM", DAY),
        "talent_edge": ("Sundays from 6 AM", WEEK),
        "blame": ("Sundays from 6 AM, by Claude", None),
        "imperialism": ("Sundays from 6 AM", WEEK),
        "trip": ("once a season a stadium, by Claude", None),
        "picks": ("Thursday 2 PM, by Claude", None),
        "live": (f"every {live_seconds} s while the game is on", live_seconds),
        "finished": ("kept for good once settled", None),
    }
    if source == "ticker":
        seconds = ticker_seconds or 5 * MINUTE
        return (f"every {cadence_words(seconds).removeprefix('every ')} while games are on", seconds)
    return table.get(source, ("when the page opens", None))


def cadence_words(seconds: int | None) -> str | None:
    """The pill's "how often": the shortest look among the page's bands."""
    if not isinstance(seconds, int) or seconds <= 0:
        return None
    if seconds < MINUTE:
        return f"every {seconds} s"
    if seconds < HOUR:
        return f"every {round(seconds / MINUTE)} min"
    if seconds == HOUR:
        return "hourly"
    if seconds < DAY:
        return f"every {round(seconds / HOUR)} h"
    if seconds < WEEK:
        return "daily"
    return "weekly"


# The bands each page lists, in the page's order (the board: the Pre-Game Program's; the other pages the same way).
PAGE_BANDS: dict[str, list[tuple[str, tuple[str, ...]]]] = {
    "program": [
        ("Cover: records, scores", ("scores",)),
        ("Cover: AP rank", ("polls",)),
        ("Cover: SP+ rank", ("ratings",)),
        ("Cover: betting line", ("lines",)),
        ("Cover: weather", ("weather",)),
        ("Cover: TV", ("media",)),
        ("Program notes", ("notes",)),
        ("Headlines", ("headlines",)),
        # the season as one line, Wave 2 (the owner's board of 2026-10-30): the like bands in their boxes
        ("The matchup: Strengths and weaknesses, the tape, last season", ("stats", "ratings", "talent", "scores")),
        ("Week by week: the poll path, the margins, play value by game", ("polls", "scores", "plays")),
        ("Recruits on hand", ("visitors",)),
        ("Availability report", ("availability",)),
        ("Leaders side by side", ("stats",)),
        ("Talent: Talent Edge, returning production, the cost, the classes", ("talent_edge", "talent")),
        ("Lineups", ("lineups",)),
        ("Tendencies", ("plays",)),
        ("The two schools and the series, the common opponents", ("facts", "history", "scores")),
        ("Getting there", ("trip",)),
        ("What we need", ("scores",)),
        ("Scouting report", ("scout",)),
    ],
    "postgame": [  # the Post-Game stop (the season as one line, Wave 3, 2026-10-30)
        ("Cover: the final and the ranks of the day", ("scores", "polls")),
        ("Closing checklist", ("scores", "polls", "recap")),
        ("What decided it", ("recap",)),
        ("Box score and the advanced box", ("finished",)),
        ("Expectations and results", ("scores", "stats")),
        ("Circle of Blame", ("blame",)),
        ("The game in the news", ("headlines",)),
    ],
    "newspaper": [
        ("Our game and the scoreboard", ("ticker",)),
        ("AP ranks", ("polls",)),
        ("Headlines and briefs", ("headlines",)),
        ("Whole stories and photos", ("articles",)),
        ("The paper laid out by Claude", ("editor",)),
        ("Drawings for stories with no photo", ("art",)),
        ("The week's stories and picks", ("paper",)),
    ],
    "live": [
        ("Score, plays and win probability", ("live",)),
        ("Box score, shot chart, down and distance", ("live",)),
        ("The ticker", ("ticker",)),
        ("Weather and the TV crew", ("weather", "notes")),
    ],
    "board": [
        ("Score, plays and win probability", ("live",)),
        ("The ticker", ("ticker",)),
    ],
    "season": [
        ("Schedule and results", ("scores",)),
        ("Standings and the race", ("scores",)),
        ("AP rank", ("polls",)),
        ("Team stats and leaders", ("stats",)),
        ("SP+ and ratings", ("ratings",)),
        ("Coaches, costs, the season's notes", ("season_loads",)),
        ("The numbers: advanced and the app's own count", ("stats", "numbers")),  # the Season stop (Wave 4)
        ("Our land", ("imperialism",)),
    ],
    "top25": [
        ("Games and scores", ("ticker",)),
        ("AP Top 25", ("polls",)),
        ("Lines", ("lines",)),
    ],
    "picks": [  # FEAT-2
        ("The week's games and kickoffs", ("scores",)),
        ("TV", ("media",)),
        ("Lines", ("lines",)),
        ("Claude's picks", ("picks",)),
    ],
    "conference": [  # the conference page (owner 2026-11-02): no source of its own
        ("Conference SP+ and the teams rated", ("ratings", "talent")),
        ("By the numbers and the leaders", ("stats",)),
        ("Standings and the race", ("scores",)),
        ("This week's games, lines and TV", ("scores", "lines", "media")),
        ("Claude's picks", ("picks",)),
        ("Talent Edge", ("talent_edge",)),
        ("Its land", ("imperialism",)),
    ],
    "imperialism": [  # FEAT-17
        ("The map, every week", ("imperialism",)),
        ("Records and results", ("scores",)),
        ("Talent Edge lines", ("talent_edge",)),
    ],
    "blame": [  # FEAT-18
        ("The report", ("blame",)),
        ("Scores and the season's stats", ("scores", "stats")),
        ("Headlines considered", ("headlines",)),
    ],
    "leaders": [("Leaders and grades", ("stats",))],
    "national": [("The national lists", ("stats",))],
    "stats": [("Team totals and player lines", ("stats",))],  # ENH-10: the full lists
    "roster": [("Roster", ("roster",)), ("Stats and grades on the rows", ("stats",))],
    "recruiting": [("Recruits and class ranks", ("recruiting",))],
    "ratings": [("SP+, Elo, FPI", ("ratings",)), ("Talent", ("talent",))],
    "team": [
        ("Schedule and results", ("scores",)),
        ("Roster", ("roster",)),
        ("Recruiting", ("recruiting",)),
        ("History", ("facts",)),
        ("The app's own numbers", ("numbers",)),
    ],
    "archive": [("Box scores and plays", ("finished",))],
    "box": [("Box score", ("finished",))],
    "injuries": [("The availability reports", ("availability",))],
}
PAGE_BANDS["myteams"] = PAGE_BANDS["season"]
PAGE_BANDS["story"] = [("The whole story, copied", ("articles",))]  # FEAT-14: the reader


@dataclass
class Context:
    """What page_status reads, so the tests can hand it their own."""

    now: datetime
    tz: Any
    game_day: bool = False
    live_seconds: int = 12
    ticker_seconds: int | None = None
    fetched: Callable[[Iterable[str]], datetime | None] = lambda _endpoints: None  # the newest cache fetch of these endpoints
    changed: Callable[[Iterable[str]], datetime | None] = lambda _endpoints: None  # the newest publication-log change
    files: dict[str, datetime | None] = field(default_factory=dict)  # "headlines", "weather", "facts", "numbers", "season_loads": the copy's time
    notes: Any = None  # this game's NotesFile, or None
    notes_saved: datetime | None = None
    kickoff: Any = None  # this game's kickoff (ISO or datetime), for what is due
    writing: dict[str, datetime | None] = field(default_factory=dict)  # "scout", "paper": when Claude wrote it
    live_at: datetime | None = None  # the live feed's last answer


def iso_z(value: datetime | None) -> str | None:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z") if isinstance(value, datetime) else None


def parse_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        when = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


def _has_part(notes: Any, part: str) -> bool:
    if notes is None:
        return False
    value = getattr(notes, part, None)
    if hasattr(value, "model_dump"):
        value = value.model_dump(exclude_none=True)
    if isinstance(value, dict):
        return any(v not in (None, [], {}, "") for v in value.values())
    return bool(value)


def _due_words(part: str, ctx: Context) -> str:
    """"Due Wed" while a part is not published yet, "Not loaded" once it could be had and is still missing."""
    due, start = part_due(part, ctx.kickoff, ctx.now)
    when = parse_time(start)
    if not due and when is not None:
        return f"Due {when.astimezone(ctx.tz):%a}"
    return "Not loaded"


def _claude_copy(kind: str, ctx: Context) -> tuple[datetime | None, str | None]:
    """(the time of Claude's copy, the words when there is none)."""
    if kind in ("scout", "paper", "editor", "art", "recap"):
        written = ctx.writing.get(kind)
        return (written, None) if written else (None, "Not written" if kind in ("scout", "paper", "recap") else "Not yet")
    if kind == "notes":
        return (ctx.notes_saved, None) if ctx.notes is not None else (None, "Not loaded")
    if _has_part(ctx.notes, kind):
        updated = None
        if kind == "availability":
            updated = parse_time(getattr(ctx.notes, "availabilityUpdatedAt", None))
        return (updated or ctx.notes_saved, None)
    return (None, _due_words(kind, ctx))


def source_copy(source: str, ctx: Context) -> tuple[datetime | None, str | None]:
    """(how old the app's copy of a source is, words in place of a time: "Due Wed", "Not written")."""
    spec = SOURCES.get(source)
    if source == "ticker":
        return ctx.fetched(("/scoreboard", "/games")), None
    if spec is None:
        return None, None
    if spec.claude:
        return _claude_copy(spec.claude, ctx)
    if source == "live":
        return ctx.live_at, None
    if source in ctx.files:
        return ctx.files.get(source), None
    if spec.published:
        return ctx.changed(spec.endpoints) or ctx.fetched(spec.endpoints), None
    return ctx.fetched(spec.endpoints), None


def page_status(view: str, ctx: Context) -> dict[str, Any]:
    """The Data status card's rows for a page, and the pill's "how often": the page's lead band, the first one the app
    polls (the program's scores, In Game's live feed), since that is the data whose age the pill shows."""
    local = ctx.now.astimezone(ctx.tz)
    bands = []
    lead: int | None = None
    for label, sources in PAGE_BANDS.get(view, []):
        first = sources[0]
        spec = SOURCES.get(first)
        words, seconds = checks(first, local, game_day=ctx.game_day, live_seconds=ctx.live_seconds, ticker_seconds=ctx.ticker_seconds)
        times = [source_copy(s, ctx) for s in sources]
        stamps = [t for t, _w in times if t is not None]
        missing = next((w for _t, w in times if w), None)
        if lead is None and isinstance(seconds, int):
            lead = seconds
        bands.append({
            "band": label,
            "changes": spec.changes if spec else ("while games are on" if first == "ticker" else "—"),
            "checks": words,
            "dataFrom": iso_z(max(stamps)) if stamps and not missing else None,
            "due": missing,
        })
    return {"view": view, "bands": bands, "cadenceSeconds": lead, "cadence": cadence_words(lead)}


# --- the server's records ---------------------------------------------------------------------------------------------


def newest(db: Any, table: str, column: str, endpoints: Iterable[str]) -> datetime | None:
    """The newest `column` of `table` (cache.fetched_at, publications.changed_at) among these endpoints."""
    names = [e for e in endpoints if isinstance(e, str)]
    if db is None or not names:
        return None
    marks = ",".join("?" for _ in names)
    try:
        with db.read() as conn:
            row = conn.execute(f"SELECT MAX({column}) FROM {table} WHERE endpoint IN ({marks})", names).fetchone()  # noqa: S608 - fixed table and column names
    except Exception as exc:  # noqa: BLE001 - a status card must not break on a helper table
        log.warning("Could not read %s.%s for the data status: %s", table, column, exc)
        return None
    return parse_time(row[0]) if row else None


def file_time(path: Path) -> datetime | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    except OSError:
        return None


def newest_file(folder: Path, pattern: str = "*.json", skip: tuple[str, ...] = ()) -> datetime | None:
    try:
        stamps = [file_time(p) for p in folder.glob(pattern) if not p.name.startswith(skip)]
    except OSError:
        return None
    stamps = [s for s in stamps if s is not None]
    return max(stamps) if stamps else None


def feeds_time(folder: Path) -> datetime | None:
    """The newest fetchedAt among the news feeds' saved copies (the season's headline file is not a feed)."""
    stamps = []
    try:
        paths = [p for p in folder.glob("*.json") if not p.name.startswith("season-")]
    except OSError:
        return None
    for path in paths:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        when = parse_time(raw.get("fetchedAt")) if isinstance(raw, dict) else None
        if when is not None:
            stamps.append(when)
    return max(stamps) if stamps else None
