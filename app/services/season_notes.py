"""The season's own notes (Phase 17 Part 3a, owner 2026-10-07): what CFBD does not have and the season prompts load.

  data/season/<year>/coaches.json    head coach, offensive and defensive coordinator for every FBS team, saved one
                                     conference batch at a time (CFBD's /coaches lists head coaches only)
  data/season/<year>/preseason.json  for the primary teams: the full staff, every roster player's birthdate (for
                                     ages), offseason moves, the outlook, injuries and suspensions, program facts
  data/season/<year>/costs.json      Part 3b: rumored roster costs (NIL and revenue sharing), a total for every team
                                     and, for the primary teams, position groups and players; one conference a batch
  data/facts.json                    Prompts phase (owner 2026-10-13): each school's history and facts (founded, the
                                     stadium, titles, Heismans, rivalries and trophies, the fight song, alumni in the
                                     NFL) and its dated events, for every FBS team, one conference a batch; outside the
                                     season folder since the preloaded facts (2026-10-21), laid over app/facts/schools.json

Both files are written by the app from a checked answer (pasted, or Claude Code's), never by hand-off: a new batch
replaces only the teams it holds. Reading is lenient: a damaged file is reported and treated as empty, one bad
row is dropped. No CFBD call.

    SeasonNotes(data_dir, season)
      coaches_for(school) -> {headCoach, offensiveCoordinator, defensiveCoordinator, conference, savedAt} | None
      preseason_for(school) -> PreseasonTeam | None
      birthdates(school) -> {name key: date}
      save_coaches(batch, conference, schools), save_preseason(file)
      status(primaries, conferences)
    age_on(born, today), name_key(name)
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Annotated, Any

from pydantic import ValidationError, field_validator

from app.cfbd.models import DropBad
from app.services.answers import atomic_write
from app.services.notes import NotesModel, NoteSource

log = logging.getLogger("kickoff.season")

SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


def name_key(name: Any) -> str | None:
    """A name to match on: accents, punctuation and suffixes off, lower case ("D'Andre Smith Jr." -> "dandre smith")."""
    if not isinstance(name, str):
        return None
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii").lower()
    words = [w for w in re.sub(r"[^a-z\s]", "", plain.replace("-", " ")).split() if w not in SUFFIXES]
    return " ".join(words) or None


def age_on(born: date, today: date) -> int:
    """Whole years: this year's birthday not yet reached counts one fewer."""
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


# --- the models the prompts ask for ---------------------------------------------------------------------------


class TeamCoaches(NotesModel):
    school: str
    headCoach: str | None = None
    offensiveCoordinator: str | None = None
    defensiveCoordinator: str | None = None


class CoachesBatch(NotesModel):
    conference: str | None = None
    season: int | None = None
    author: str | None = None
    teams: Annotated[list[TeamCoaches], DropBad] = []
    sources: Annotated[list[NoteSource], DropBad] = []


class Rivalry(NotesModel):
    rival: str
    trophy: str | None = None
    firstMeeting: int | None = None
    record: str | None = None  # from this school's side, "68-44-2"


class DatedEvent(NotesModel):
    """Something that happened on a day: the stadium's first game, a title, the rivalry's first meeting. The date is
    YYYY-MM-DD; a year alone (YYYY) is kept for the history and never makes an anniversary."""

    date: str
    event: str

    @field_validator("date")
    @classmethod
    def _date(cls, value: str) -> str:
        text = str(value).strip()
        if not re.fullmatch(r"\d{4}(-\d{2}-\d{2})?", text):
            raise ValueError("a date is YYYY-MM-DD or a year")
        return text


def _year_or_none(value: Any) -> int | None:
    """A year, from an int or a string with one in it ("1906", "1906 (as an agricultural college)"); junk is None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if 1600 <= value <= 2100 else None  # the oldest FBS schools were founded in the 1700s (the preloaded facts, 2026-10-21)
    if isinstance(value, float) and value.is_integer():
        return _year_or_none(int(value))
    if isinstance(value, str):
        found = re.search(r"\b(1[6-9]\d{2}|20\d{2})\b", value)
        return int(found.group(1)) if found else None
    return None


def _count_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if 0 <= value <= 1_000_000 else None
    if isinstance(value, float) and value.is_integer():
        return _count_or_none(int(value))
    if isinstance(value, str):
        digits = re.sub(r"[^\d]", "", value)
        return _count_or_none(int(digits)) if digits else None
    return None


class TeamFacts(NotesModel):
    """One school's history and facts. Every field but the school is optional and forgiving: a year written as text
    still counts, a capacity with commas still counts, anything else becomes None and the row stays."""

    school: str
    founded: int | None = None
    stadium: str | None = None
    stadiumNickname: str | None = None  # the preloaded facts (2026-10-21): what the trivia asks
    stadiumOpened: int | None = None
    capacity: int | None = None
    conferenceSince: int | None = None
    allTimeRecord: str | None = None
    nationalTitles: Annotated[list[int], DropBad] = []
    conferenceTitles: int | None = None
    heismans: Annotated[list[str], DropBad] = []
    bowlRecord: str | None = None
    rivalries: Annotated[list[Rivalry], DropBad] = []
    headCoachRecord: str | None = None
    firstSeason: int | None = None
    conferenceTitleYears: Annotated[list[int], DropBad] = []
    winningestCoach: str | None = None
    longestWinStreak: str | None = None
    recordCrowd: str | None = None
    retiredNumbers: Annotated[list[str], DropBad] = []
    mascotName: str | None = None
    traditions: Annotated[list[str], DropBad] = []
    mascotOrigin: str | None = None
    colorsOrigin: str | None = None
    fightSong: str | None = None
    nflAlumni: Annotated[list[str], DropBad] = []
    dates: Annotated[list[DatedEvent], DropBad] = []
    sources: Annotated[list[NoteSource], DropBad] = []

    @field_validator("founded", "stadiumOpened", "conferenceSince", mode="before")
    @classmethod
    def _years(cls, value: Any) -> int | None:
        return _year_or_none(value)

    @field_validator("capacity", "conferenceTitles", mode="before")
    @classmethod
    def _counts(cls, value: Any) -> int | None:
        return _count_or_none(value)

    @field_validator("nationalTitles", mode="before")
    @classmethod
    def _titles(cls, value: Any) -> Any:
        return [y for y in (_year_or_none(v) for v in value) if y is not None] if isinstance(value, list) else []

    @field_validator("heismans", "nflAlumni", mode="before")
    @classmethod
    def _names(cls, value: Any) -> Any:
        return [str(v).strip() for v in value if isinstance(v, (str, int)) and not isinstance(v, bool) and str(v).strip()] if isinstance(value, list) else []

    @field_validator("rivalries", "dates", "sources", mode="before")
    @classmethod
    def _lists(cls, value: Any) -> Any:
        return value if isinstance(value, list) else []  # a list written as one thing, or junk: nothing, and the row stays


class FactsBatch(NotesModel):
    conference: str | None = None
    season: int | None = None
    author: str | None = None
    teams: Annotated[list[TeamFacts], DropBad] = []
    sources: Annotated[list[NoteSource], DropBad] = []


class StaffMember(NotesModel):
    name: str
    role: str | None = None  # "Offensive line coach", "Special teams coordinator"


class Birthdate(NotesModel):
    name: str
    number: int | None = None
    position: str | None = None
    born: date  # YYYY-MM-DD; a row without a usable date is dropped

    @field_validator("born")
    @classmethod
    def _plausible(cls, value: date) -> date:
        if not 1985 <= value.year <= 2012:
            raise ValueError("not a college player's birth year")
        return value


class Move(NotesModel):
    name: str
    position: str | None = None
    kind: str | None = None  # "NFL draft", "Transfer", "Graduated", "Freshman", "Junior college"
    detail: str | None = None  # where to, where from, round and pick, the reason


class Item(NotesModel):
    title: str
    detail: str | None = None


class Injury(NotesModel):
    name: str
    position: str | None = None
    status: str | None = None  # "Out for the season", "Suspended 2 games", "Day to day"
    detail: str | None = None
    expectedReturn: str | None = None


class Outlook(NotesModel):
    summary: str | None = None
    predictions: Annotated[list[Item], DropBad] = []
    positionBattles: Annotated[list[Item], DropBad] = []
    storylines: Annotated[list[Item], DropBad] = []


class PreseasonTeam(NotesModel):
    school: str
    staff: Annotated[list[StaffMember], DropBad] = []
    birthdates: Annotated[list[Birthdate], DropBad] = []
    departures: Annotated[list[Move], DropBad] = []
    arrivals: Annotated[list[Move], DropBad] = []
    coachingChanges: Annotated[list[Item], DropBad] = []
    outlook: Outlook | None = None
    injuries: Annotated[list[Injury], DropBad] = []
    programFacts: Annotated[list[Item], DropBad] = []
    sources: Annotated[list[NoteSource], DropBad] = []


class SeasonAll(NotesModel):
    """The one-paste season load (Phase 18.3): the primary teams' deep preseason and every FBS team's coaches."""

    season: int | None = None
    author: str | None = None
    writtenAt: str | None = None
    teams: Annotated[list[PreseasonTeam], DropBad] = []
    coaches: Annotated[list[TeamCoaches], DropBad] = []
    sources: Annotated[list[NoteSource], DropBad] = []


class PreseasonFile(NotesModel):
    season: int | None = None
    author: str | None = None
    writtenAt: str | None = None
    teams: Annotated[list[PreseasonTeam], DropBad] = []


# Phase 17 Part 3b (owner 2026-10-07: "it's ok if they cant be found, or are guessed at the press articles"; "keep it
# as 'rumored' so the search isnt too deep"): every figure is a reported or rumored dollar amount with where it came from.


class CostPosition(NotesModel):
    group: str  # "Quarterbacks", "Offensive line"
    amountUsd: int | None = None
    note: str | None = None


class CostPlayer(NotesModel):
    name: str
    position: str | None = None
    amountUsd: int | None = None
    note: str | None = None  # "On3 NIL valuation", "reported revenue-share deal"


class TeamCosts(NotesModel):
    school: str
    totalUsd: int | None = None  # the whole roster this season, rumored
    note: str | None = None  # what the total covers: "revenue sharing cap plus collective NIL", "estimate"
    positions: Annotated[list[CostPosition], DropBad] = []
    players: Annotated[list[CostPlayer], DropBad] = []
    sources: Annotated[list[NoteSource], DropBad] = []
    asOf: str | None = None  # the date of the report


class CostsBatch(NotesModel):
    conference: str | None = None
    season: int | None = None
    author: str | None = None
    teams: Annotated[list[TeamCosts], DropBad] = []
    sources: Annotated[list[NoteSource], DropBad] = []


# --- the files ---------------------------------------------------------------------------------------------


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


SHIPPED_DIR = Path(__file__).resolve().parent.parent / "facts"
SHIPPED_FACTS = SHIPPED_DIR / "schools.json"  # every FBS school, researched once (2026-10-21)
# the preloading (owner 2026-10-22: "the preloaded data should show its date from the data that gets downloaded with the
# program"): every FBS team's coaches, rumored roster costs and season load, researched for one season and shipped with
# the app; laid under the install's own loads (a team loaded on the install wins) for that season only
SHIPPED_COACHES = SHIPPED_DIR / "coaches.json"
SHIPPED_COSTS = SHIPPED_DIR / "costs.json"
SHIPPED_PRESEASON = SHIPPED_DIR / "preseason.json"
FACTS_FRESH_DAYS = 365  # a school's facts older than this are asked for again by the schedule, once a year
_SHIPPED: dict[Path, tuple[tuple[int, int], dict[str, Any]]] = {}


def shipped_file(path: Path) -> dict[str, Any]:
    """A file shipped with the app: {"checkedAt", "author", "season", "teams": {school: row}}, decoded once per change of
    the file; {} when the file is missing or damaged (the install's own loads still work)."""
    try:
        stat = path.stat()
    except OSError:
        return {}
    stamp = (stat.st_mtime_ns, stat.st_size)
    kept = _SHIPPED.get(path)
    if kept is not None and kept[0] == stamp:
        return kept[1]
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        log.warning("The shipped file %s is unreadable (%s); the install's own loads only", path, exc)
        return {}
    raw = raw if isinstance(raw, dict) else {}
    teams = raw.get("teams") if isinstance(raw.get("teams"), dict) else {}
    season = raw.get("season")
    data = {
        "checkedAt": raw.get("checkedAt") if isinstance(raw.get("checkedAt"), str) else None,
        "author": raw.get("author") if isinstance(raw.get("author"), str) else None,
        "season": season if isinstance(season, int) and not isinstance(season, bool) else None,
        "teams": {k: v for k, v in teams.items() if isinstance(k, str) and isinstance(v, dict)},
    }
    _SHIPPED[path] = (stamp, data)
    return data


def shipped_facts(path: Path = SHIPPED_FACTS) -> dict[str, Any]:
    """The facts shipped with the app (every season: a school's history outlives one)."""
    return shipped_file(path)


def shipped_for_season(path: Path, season: int) -> dict[str, Any]:
    """A season's shipped file, or {} when it was researched for another season (last year's coaches are not this
    year's)."""
    data = shipped_file(path)
    return data if data and data.get("season") == season else {}


class SeasonNotes:
    def __init__(self, data_dir: Path, season: int) -> None:
        self.dir = Path(data_dir) / "season" / str(season)
        self.season = season
        self.facts_file = Path(data_dir) / "facts.json"  # the install's own facts, outside the season folder: they outlive a season (2026-10-21)
        self._files: dict[Path, tuple[tuple[int, int], dict[str, Any]]] = {}  # freeze wave F7: each file decoded once per change (by mtime and size)

    @property
    def coaches_path(self) -> Path:
        return self.dir / "coaches.json"

    @property
    def preseason_path(self) -> Path:
        return self.dir / "preseason.json"

    def _read(self, path: Path) -> dict[str, Any]:
        """A season file, decoded once per change (freeze wave F7, B8: coaches.json was read about 130 times per Top 25 request).
        The change is seen in the mtime or the size (Windows stamps two writes within its clock tick, about 15 ms, alike)."""
        try:
            stat = path.stat()
        except OSError:
            return {}
        stamp = (stat.st_mtime_ns, stat.st_size)
        files = self._files
        kept = files.get(path)
        if kept is not None and kept[0] == stamp:
            return kept[1]
        try:
            raw = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            log.warning("Season file %s is unreadable (%s); treated as empty", path, exc)
            return {}
        data = raw if isinstance(raw, dict) else {}
        files[path] = (stamp, data)
        return data

    # --- coaches ----------------------------------------------------------------------------------------

    def _own_coaches(self) -> dict[str, Any]:
        raw = self._read(self.coaches_path)
        teams = raw.get("teams") if isinstance(raw.get("teams"), dict) else {}
        batches = raw.get("batches") if isinstance(raw.get("batches"), dict) else {}
        return {"teams": {k: v for k, v in teams.items() if isinstance(k, str) and isinstance(v, dict)}, "batches": {k: v for k, v in batches.items() if isinstance(k, str) and isinstance(v, dict)}}

    def coaches(self) -> dict[str, Any]:
        """Every team's coaches: the shipped file under the install's own (2026-10-22); `shipped` marks the shipped rows."""
        own = self._own_coaches()
        shipped = shipped_for_season(SHIPPED_COACHES, self.season)
        teams = {school: {**row, "shipped": True, "checkedAt": row.get("checkedAt") or shipped.get("checkedAt")} for school, row in shipped.get("teams", {}).items()}
        teams.update({school: {**row, "shipped": False} for school, row in own["teams"].items()})
        return {"teams": teams, "batches": own["batches"]}

    def coaches_for(self, school: Any) -> dict[str, Any] | None:
        if not isinstance(school, str):
            return None
        row = self.coaches()["teams"].get(school)
        return row or None

    def save_coaches(self, batch: CoachesBatch, conference: str, schools: list[str]) -> dict[str, Any]:
        """Keep the teams of this conference the answer names (spelled as CFBD spells them); returns what was kept."""
        by_lower = {s.lower(): s for s in schools}
        data = self._own_coaches()  # the install's own file: the shipped rows stay in the shipped file
        kept: list[str] = []
        unknown: list[str] = []
        when = _now()
        for row in batch.teams:
            school = by_lower.get(row.school.strip().lower())
            if school is None:
                unknown.append(row.school)
                continue
            data["teams"][school] = {
                "conference": conference,
                "headCoach": row.headCoach,
                "offensiveCoordinator": row.offensiveCoordinator,
                "defensiveCoordinator": row.defensiveCoordinator,
                "savedAt": when,
                "sources": [s.model_dump(exclude_none=True) for s in batch.sources][:6],
            }
            kept.append(school)
        data["batches"][conference] = {"savedAt": when, "teams": len(kept), "of": len(schools), "author": batch.author}
        atomic_write(self.coaches_path, json.dumps(data, indent=1, ensure_ascii=False) + "\n")
        log.info("Coaches saved for %s: %d of %d teams", conference, len(kept), len(schools))
        return {"kept": kept, "unknown": unknown, "missing": [s for s in schools if s not in kept]}

    # --- school history and facts (the Prompts phase, owner 2026-10-13) -----------------------------------------

    @property
    def facts_path(self) -> Path:
        """The install's own facts (2026-10-21: outside the season folder, since a school's history outlives a season; a file
        left in this season's folder by the earlier layout is read once and copied over)."""
        return self.facts_file

    def _own_facts(self) -> dict[str, Any]:
        raw = self._read(self.facts_file)
        if not raw:
            old = self.dir / "facts.json"
            if old.is_file() and not self.facts_file.exists():
                raw = self._read(old)
                if raw:
                    try:
                        atomic_write(self.facts_file, json.dumps(raw, indent=1, ensure_ascii=False) + "\n")
                        log.info("The season's facts file moved to %s", self.facts_file)
                    except OSError as exc:
                        log.warning("The season's facts could not be copied to %s: %s", self.facts_file, exc)
        teams = raw.get("teams") if isinstance(raw.get("teams"), dict) else {}
        batches = raw.get("batches") if isinstance(raw.get("batches"), dict) else {}
        marks = raw.get("marks") if isinstance(raw.get("marks"), dict) else {}
        return {
            "teams": {k: v for k, v in teams.items() if isinstance(k, str) and isinstance(v, dict)},
            "batches": {k: v for k, v in batches.items() if isinstance(k, str) and isinstance(v, dict)},
            "marks": {k: [m for m in v if isinstance(m, dict)] for k, v in marks.items() if isinstance(k, str) and isinstance(v, list)},  # the trivia's "wrong? mark it" notes, until the school is saved again
        }

    def facts(self) -> dict[str, Any]:
        """Every school's facts: the shipped file under the install's own (a school the install loaded itself wins).
        `shipped` names the schools that come from the shipped file."""
        own = self._own_facts()
        shipped = shipped_facts(SHIPPED_FACTS)  # the module's path at call time, so a test can point it elsewhere
        teams = {school: {**row, "shipped": True, "checkedAt": row.get("checkedAt") or shipped.get("checkedAt")} for school, row in shipped.get("teams", {}).items()}
        teams.update({school: {**row, "shipped": False, "checkedAt": row.get("checkedAt") or row.get("savedAt")} for school, row in own["teams"].items()})
        return {"teams": teams, "batches": own["batches"], "shipped": sorted(s for s, row in teams.items() if row.get("shipped"))}

    def facts_for(self, school: Any) -> dict[str, Any] | None:
        """One school's facts (a plain dict, every key present with None or [] where the answer had nothing)."""
        if not isinstance(school, str):
            return None
        row = self.facts().get("teams", {}).get(school)
        if not row:
            return None
        try:
            facts = TeamFacts.model_validate({**row, "school": school})
        except ValidationError:
            log.warning("The saved facts for %s could not be read; shown as not loaded.", school)
            return None
        return {**facts.model_dump(), "conference": row.get("conference"), "savedAt": row.get("savedAt"), "checkedAt": row.get("checkedAt"), "shipped": bool(row.get("shipped")), "marks": self._own_facts()["marks"].get(school, [])}

    def save_facts(self, batch: FactsBatch, conference: str, schools: list[str]) -> dict[str, Any]:
        """Keep the teams of this conference the answer names (spelled as CFBD spells them) in the install's own file,
        over the shipped facts; returns what was kept."""
        by_lower = {s.lower(): s for s in schools}
        data = self._own_facts()
        kept: list[str] = []
        unknown: list[str] = []
        when = _now()
        for row in batch.teams:
            school = by_lower.get(row.school.strip().lower())
            if school is None:
                unknown.append(row.school)
                continue
            dump = row.model_dump(exclude_none=True)
            dump.pop("school", None)
            data["teams"][school] = {**dump, "conference": conference, "savedAt": when, "checkedAt": when, "sources": [s.model_dump(exclude_none=True) for s in (row.sources or batch.sources)][:8]}
            kept.append(school)
        data["batches"][conference] = {"savedAt": when, "teams": len(kept), "of": len(schools), "author": batch.author}
        for school in kept:
            data["marks"].pop(school, None)  # a fresh row answers the trivia's marks against the old one
        atomic_write(self.facts_file, json.dumps(data, indent=1, ensure_ascii=False) + "\n")
        log.info("School facts saved for %s: %d of %d teams", conference, len(kept), len(schools))
        return {"kept": kept, "unknown": unknown, "missing": [s for s in schools if s not in kept]}

    def mark_fact(self, school: str, kind: str, note: str, question: str, at: str) -> None:
        """The trivia's "wrong? mark it" (owner 2026-10-21): a note against one school's fact, kept in the install's own
        facts file beside the rows until that school is saved again (a paste or a run of the facts prompt), which
        clears it. The History band shows the marks."""
        if not isinstance(school, str) or not school:
            return
        data = self._own_facts()
        marks = data["marks"].setdefault(school, [])
        marks.append({"kind": str(kind or ""), "question": str(question or "")[:300], "note": str(note or "")[:300], "at": str(at or _now())})
        data["marks"][school] = marks[-20:]
        atomic_write(self.facts_file, json.dumps(data, indent=1, ensure_ascii=False) + "\n")
        log.info("A trivia mark against %s's %s was kept in the facts file", school, kind)

    @staticmethod
    def facts_stale(checked_at: Any, today: date) -> bool:
        """True when a school's facts were checked more than FACTS_FRESH_DAYS before today, or never."""
        if not isinstance(checked_at, str) or not checked_at:
            return True
        try:
            checked = datetime.fromisoformat(checked_at.replace("Z", "+00:00")).date() if "T" in checked_at else date.fromisoformat(checked_at[:10])
        except ValueError:
            return True
        return (today - checked).days > FACTS_FRESH_DAYS

    # --- roster costs (Part 3b) ---------------------------------------------------------------------------

    @property
    def costs_path(self) -> Path:
        return self.dir / "costs.json"

    def costs(self) -> dict[str, Any]:
        """Every team's rumored roster costs: the shipped file under the install's own (2026-10-22)."""
        raw = self._read(self.costs_path)
        teams = raw.get("teams") if isinstance(raw.get("teams"), dict) else {}
        batches = raw.get("batches") if isinstance(raw.get("batches"), dict) else {}
        shipped = shipped_for_season(SHIPPED_COSTS, self.season)
        good: dict[str, Any] = {}
        for source, rows in (("shipped", shipped.get("teams", {})), ("own", teams)):
            for school, value in rows.items():
                if not isinstance(school, str) or not isinstance(value, dict):
                    continue
                try:
                    row = {**TeamCosts.model_validate(value).model_dump(exclude_none=True), "conference": value.get("conference"), "savedAt": value.get("savedAt")}
                except ValidationError:
                    log.warning("Roster costs for %s (%s) are damaged; left out", school, source)
                    continue
                good[school] = {**row, "shipped": source == "shipped", **({"checkedAt": value.get("checkedAt") or shipped.get("checkedAt")} if source == "shipped" else {})}
        return {"teams": good, "batches": {k: v for k, v in batches.items() if isinstance(k, str) and isinstance(v, dict)}}

    def costs_for(self, school: Any) -> dict[str, Any] | None:
        return self.costs()["teams"].get(school) if isinstance(school, str) else None

    def save_costs(self, batch: CostsBatch, conference: str, schools: list[str], detailed: list[str]) -> dict[str, Any]:
        """Keep this conference's teams the answer names; position and player figures only for `detailed` (the
        primary teams), so a shallow search never fills the page with guesses about everyone's roster."""
        by_lower = {s.lower(): s for s in schools}
        wanted = {d.lower() for d in detailed}
        raw = self._read(self.costs_path)
        teams = raw.get("teams") if isinstance(raw.get("teams"), dict) else {}
        batches = raw.get("batches") if isinstance(raw.get("batches"), dict) else {}
        kept: list[str] = []
        when = _now()
        for row in batch.teams:
            school = by_lower.get(row.school.strip().lower())
            if school is None:
                continue
            if school.lower() not in wanted:
                row = row.model_copy(update={"positions": [], "players": []})
            sources = row.sources or batch.sources
            teams[school] = {**row.model_copy(update={"school": school, "sources": sources[:6]}).model_dump(exclude_none=True), "conference": conference, "savedAt": when}
            kept.append(school)
        batches[conference] = {"savedAt": when, "teams": len(kept), "of": len(schools), "author": batch.author}
        atomic_write(self.costs_path, json.dumps({"teams": teams, "batches": batches}, indent=1, ensure_ascii=False) + "\n")
        log.info("Roster costs saved for %s: %d of %d teams", conference, len(kept), len(schools))
        return {"kept": kept, "missing": [s for s in schools if s not in kept]}

    # --- preseason --------------------------------------------------------------------------------------

    def preseason(self) -> dict[str, PreseasonTeam]:
        """Every team's season load, read once per change of the files (a roster asks for each player's age): the shipped
        file under the install's own (2026-10-22)."""
        try:
            stamp = self.preseason_path.stat().st_mtime_ns
        except OSError:
            stamp = None
        shipped = shipped_for_season(SHIPPED_PRESEASON, self.season)
        key = (stamp, id(shipped.get("teams")) if shipped else None)
        cached = getattr(self, "_preseason_cache", None)
        if cached is not None and cached[0] == key:
            return cached[1]
        out = self._load_preseason(shipped.get("teams", {}) if shipped else {})
        self._preseason_cache = (key, out)
        return out

    def _load_preseason(self, shipped: dict[str, Any] | None = None) -> dict[str, PreseasonTeam]:
        raw = self._read(self.preseason_path)
        teams = raw.get("teams") if isinstance(raw.get("teams"), dict) else {}
        out: dict[str, PreseasonTeam] = {}
        for source, rows in (("shipped", shipped or {}), ("own", teams)):
            for school, value in rows.items():
                if not isinstance(school, str) or not isinstance(value, dict):
                    continue
                try:
                    out[school] = PreseasonTeam.model_validate({"school": school, **value})  # a row's own bad school still fails
                except ValidationError as exc:
                    log.warning("Preseason entry for %s (%s) is damaged (%s); left out", school, source, exc.errors()[0].get("msg") if exc.errors() else exc)
        return out

    def preseason_shipped(self) -> dict[str, Any]:
        """The shipped season load's schools and its date: {"schools": set, "checkedAt"} (empty for another season)."""
        shipped = shipped_for_season(SHIPPED_PRESEASON, self.season)
        return {"schools": set(shipped.get("teams", {})) if shipped else set(), "checkedAt": shipped.get("checkedAt") if shipped else None}

    def preseason_meta(self) -> dict[str, dict[str, Any]]:
        raw = self._read(self.preseason_path)
        meta = raw.get("meta") if isinstance(raw.get("meta"), dict) else {}
        return {k: v for k, v in meta.items() if isinstance(k, str) and isinstance(v, dict)}

    def preseason_for(self, school: Any) -> PreseasonTeam | None:
        return self.preseason().get(school) if isinstance(school, str) else None

    def save_preseason(self, team: PreseasonTeam, school: str, author: str | None) -> None:
        raw = self._read(self.preseason_path)
        teams = raw.get("teams") if isinstance(raw.get("teams"), dict) else {}
        meta = raw.get("meta") if isinstance(raw.get("meta"), dict) else {}
        team.school = school
        teams[school] = team.model_dump(mode="json", exclude_none=True)
        meta[school] = {"savedAt": _now(), "author": author}
        atomic_write(self.preseason_path, json.dumps({"season": self.season, "teams": teams, "meta": meta}, indent=1, ensure_ascii=False) + "\n")
        log.info("Preseason saved for %s", school)

    def age(self, school: Any, name: Any, today: date) -> tuple[int | None, str | None]:
        """(age, birthdate) of a player on a team's roster, from the preseason load; (None, None) when unknown."""
        key = name_key(name)
        born = self.birthdates(school).get(key) if key else None
        if born is None:
            return None, None
        return age_on(born, today), born.isoformat()

    def birthdates(self, school: Any) -> dict[str, date]:
        team = self.preseason_for(school)
        if team is None:
            return {}
        out: dict[str, date] = {}
        for row in team.birthdates:
            key = name_key(row.name)
            if key:
                out[key] = row.born
        return out

    # --- what's loaded ------------------------------------------------------------------------------------

    def status(self, primaries: list[str], conferences: dict[str, list[str]], today: date) -> dict[str, Any]:
        coaches = self.coaches()
        meta = self.preseason_meta()
        loaded = self.preseason()
        pre_shipped = self.preseason_shipped()
        rows = []
        for school in primaries:
            team = loaded.get(school)
            own_at = (meta.get(school) or {}).get("savedAt")
            rows.append({
                "school": school,
                "savedAt": own_at,
                "shipped": not own_at and school in pre_shipped["schools"],  # the preloading (2026-10-22): shipped with the app, not loaded here
                "checkedAt": None if own_at else pre_shipped["checkedAt"] if school in pre_shipped["schools"] else None,
                "counts": {
                    "staff": len(team.staff), "birthdates": len(team.birthdates), "departures": len(team.departures), "arrivals": len(team.arrivals),
                    "injuries": len(team.injuries), "programFacts": len(team.programFacts),
                } if team else None,
            })
        def shipped_of(rows: dict[str, Any], schools: list[str]) -> tuple[int, str | None]:
            mine = [rows[s] for s in schools if s in rows and rows[s].get("shipped")]
            return len(mine), max((r.get("checkedAt") for r in mine if isinstance(r.get("checkedAt"), str)), default=None)

        batches = []
        for conference, schools in sorted(conferences.items()):
            saved = coaches["batches"].get(conference) or {}
            have = sum(1 for s in schools if s in coaches["teams"])
            n, checked = shipped_of(coaches["teams"], schools)
            batches.append({"conference": conference, "schools": len(schools), "saved": have, "savedAt": saved.get("savedAt"), "shipped": n, "checkedAt": checked})
        costs = self.costs()
        cost_batches = []
        for conference, schools in sorted(conferences.items()):
            saved = costs["batches"].get(conference) or {}
            n, checked = shipped_of(costs["teams"], schools)
            cost_batches.append({"conference": conference, "schools": len(schools), "saved": sum(1 for s in schools if s in costs["teams"]), "savedAt": saved.get("savedAt"), "shipped": n, "checkedAt": checked})
        facts = self.facts()
        fact_batches = []
        for conference, schools in sorted(conferences.items()):
            saved = facts["batches"].get(conference) or {}
            fact_rows = [facts["teams"][s] for s in schools if s in facts["teams"]]
            checked = max((r.get("checkedAt") for r in fact_rows if isinstance(r.get("checkedAt"), str)), default=None)
            fact_batches.append({
                "conference": conference,
                "schools": len(schools),
                "saved": len(fact_rows),
                "savedAt": saved.get("savedAt"),
                "shipped": sum(1 for r in fact_rows if r.get("shipped")),  # from the file shipped with the app (2026-10-21)
                "checkedAt": checked,
                "stale": bool(fact_rows) and len(fact_rows) == len(schools) and all(self.facts_stale(r.get("checkedAt"), today) for r in fact_rows),  # a year old: the schedule asks again
            })
        missing = [r["school"] for r in rows if not r["savedAt"]]
        return {
            "costs": cost_batches,
            "costsSaved": sum(b["saved"] for b in cost_batches),
            "facts": fact_batches,
            "factsSaved": sum(b["saved"] for b in fact_batches),
            "season": self.season,
            "preseason": rows,
            "coaches": batches,
            "coachesSaved": sum(b["saved"] for b in batches),
            "coachesOf": sum(b["schools"] for b in batches),
            # the preloading (2026-10-22): how many of the followed teams' rows came with the program, and its date
            "shipped": {
                "coaches": sum(b["shipped"] for b in batches),
                "costs": sum(b["shipped"] for b in cost_batches),
                "facts": sum(b["shipped"] for b in fact_batches),
                "preseason": sum(1 for r in rows if r["shipped"]),
                "checkedAt": {
                    "coaches": max((b["checkedAt"] for b in batches if b["checkedAt"]), default=None),
                    "costs": max((b["checkedAt"] for b in cost_batches if b["checkedAt"]), default=None),
                    "facts": max((b["checkedAt"] for b in fact_batches if b["checkedAt"] and b["shipped"]), default=None),
                    "preseason": pre_shipped["checkedAt"] if any(r["shipped"] for r in rows) else None,
                },
            },
            "remind": bool(missing) and today.month >= 8 and today.year == self.season,
        }
