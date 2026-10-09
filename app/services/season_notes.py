"""The season's own notes (Phase 17 Part 3a, owner 2026-10-07): what CFBD does not have and the season prompts load.

  data/season/<year>/coaches.json    head coach, offensive and defensive coordinator for every FBS team, saved one
                                     conference batch at a time (CFBD's /coaches lists head coaches only)
  data/season/<year>/preseason.json  for the primary teams: the full staff, every roster player's birthdate (for
                                     ages), offseason moves, the outlook, injuries and suspensions, program facts
  data/season/<year>/costs.json      Part 3b: rumored roster costs (NIL and revenue sharing), a total for every team
                                     and, for the primary teams, position groups and players; one conference a batch

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


class SeasonNotes:
    def __init__(self, data_dir: Path, season: int) -> None:
        self.dir = Path(data_dir) / "season" / str(season)
        self.season = season

    @property
    def coaches_path(self) -> Path:
        return self.dir / "coaches.json"

    @property
    def preseason_path(self) -> Path:
        return self.dir / "preseason.json"

    def _read(self, path: Path) -> dict[str, Any]:
        if not path.is_file():
            return {}
        try:
            raw = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            log.warning("Season file %s is unreadable (%s); treated as empty", path, exc)
            return {}
        return raw if isinstance(raw, dict) else {}

    # --- coaches ----------------------------------------------------------------------------------------

    def coaches(self) -> dict[str, Any]:
        raw = self._read(self.coaches_path)
        teams = raw.get("teams") if isinstance(raw.get("teams"), dict) else {}
        batches = raw.get("batches") if isinstance(raw.get("batches"), dict) else {}
        return {"teams": {k: v for k, v in teams.items() if isinstance(k, str) and isinstance(v, dict)}, "batches": {k: v for k, v in batches.items() if isinstance(k, str) and isinstance(v, dict)}}

    def coaches_for(self, school: Any) -> dict[str, Any] | None:
        if not isinstance(school, str):
            return None
        row = self.coaches()["teams"].get(school)
        return row or None

    def save_coaches(self, batch: CoachesBatch, conference: str, schools: list[str]) -> dict[str, Any]:
        """Keep the teams of this conference the answer names (spelled as CFBD spells them); returns what was kept."""
        by_lower = {s.lower(): s for s in schools}
        data = self.coaches()
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

    # --- roster costs (Part 3b) ---------------------------------------------------------------------------

    @property
    def costs_path(self) -> Path:
        return self.dir / "costs.json"

    def costs(self) -> dict[str, Any]:
        raw = self._read(self.costs_path)
        teams = raw.get("teams") if isinstance(raw.get("teams"), dict) else {}
        batches = raw.get("batches") if isinstance(raw.get("batches"), dict) else {}
        good: dict[str, Any] = {}
        for school, value in teams.items():
            if not isinstance(school, str) or not isinstance(value, dict):
                continue
            try:
                good[school] = {**TeamCosts.model_validate(value).model_dump(exclude_none=True), "conference": value.get("conference"), "savedAt": value.get("savedAt")}
            except ValidationError:
                log.warning("Roster costs for %s are damaged; left out", school)
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
        """Every saved team, read once per change of the file (a roster asks for each player's age)."""
        try:
            stamp = self.preseason_path.stat().st_mtime_ns
        except OSError:
            stamp = None
        cached = getattr(self, "_preseason_cache", None)
        if cached is not None and cached[0] == stamp and stamp is not None:
            return cached[1]
        out = self._load_preseason()
        self._preseason_cache = (stamp, out)
        return out

    def _load_preseason(self) -> dict[str, PreseasonTeam]:
        raw = self._read(self.preseason_path)
        teams = raw.get("teams") if isinstance(raw.get("teams"), dict) else {}
        out: dict[str, PreseasonTeam] = {}
        for school, value in teams.items():
            if not isinstance(school, str) or not isinstance(value, dict):
                continue
            try:
                out[school] = PreseasonTeam.model_validate(value)
            except ValidationError as exc:
                log.warning("Preseason entry for %s is damaged (%s); left out", school, exc.errors()[0].get("msg") if exc.errors() else exc)
        return out

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
        rows = []
        for school in primaries:
            team = loaded.get(school)
            rows.append({
                "school": school,
                "savedAt": (meta.get(school) or {}).get("savedAt"),
                "counts": {
                    "staff": len(team.staff), "birthdates": len(team.birthdates), "departures": len(team.departures), "arrivals": len(team.arrivals),
                    "injuries": len(team.injuries), "programFacts": len(team.programFacts),
                } if team else None,
            })
        batches = []
        for conference, schools in sorted(conferences.items()):
            saved = coaches["batches"].get(conference) or {}
            have = sum(1 for s in schools if s in coaches["teams"])
            batches.append({"conference": conference, "schools": len(schools), "saved": have, "savedAt": saved.get("savedAt")})
        costs = self.costs()
        cost_batches = []
        for conference, schools in sorted(conferences.items()):
            saved = costs["batches"].get(conference) or {}
            cost_batches.append({"conference": conference, "schools": len(schools), "saved": sum(1 for s in schools if s in costs["teams"]), "savedAt": saved.get("savedAt")})
        missing = [r["school"] for r in rows if not r["savedAt"]]
        return {
            "costs": cost_batches,
            "costsSaved": sum(b["saved"] for b in cost_batches),
            "season": self.season,
            "preseason": rows,
            "coaches": batches,
            "coachesSaved": sum(b["saved"] for b in batches),
            "coachesOf": sum(b["schools"] for b in batches),
            "remind": bool(missing) and today.month >= 8 and today.year == self.season,
        }
