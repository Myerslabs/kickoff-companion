"""The per-game notes file, `data/notes/<game_id>.json`, written by the scheduled pre-game task
or by hand. Phase 4 reads the visitors list (R2); Phase 5 renders the rest (program notes,
availability). Validated with Pydantic; a bad file is reported, never raised, and one bad
entry is dropped and counted rather than killing the file."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, ValidationError

from app.cfbd.models import DropBad

log = logging.getLogger("kickoff.notes")


class NotesModel(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class NoteSource(NotesModel):
    label: str
    url: str | None = None


class NoteSection(NotesModel):
    heading: str
    paragraphs: list[str] = []


class AvailabilityRow(NotesModel):
    name: str
    position: str | None = None
    status: str | None = None  # Phase 17: a chat that finds no published status leaves it out; the row is kept, "Not reported"
    note: str | None = None


class Visitor(NotesModel):
    name: str
    position: str | None = None
    stars: int | None = None
    highSchool: str | None = None
    hometown: str | None = None
    classYear: int | None = None
    status: str | None = None  # confirmed, expected, reported


class Visitors(NotesModel):
    home: Annotated[list[Visitor], DropBad] = []
    away: Annotated[list[Visitor], DropBad] = []
    source: str | None = None
    sourceUrl: str | None = None
    updatedAt: str | None = None


class Schemes(NotesModel):
    """Scheme labels the sim showed and CFBD does not carry: written by the weekly task or by hand."""

    offense: str | None = None  # e.g. "Spread, 11 personnel, up-tempo"
    defense: str | None = None  # e.g. "4-2-5, quarters"
    source: str | None = None


class LineupPlayer(NotesModel):
    """One name on a depth chart slot, in the published order (the first is the starter)."""

    name: str
    number: int | None = None
    classYear: str | None = None  # as printed: "JR", "RS SO", "GR"
    note: str | None = None  # "questionable, ankle"


class LineupSlot(NotesModel):
    """One slot of a published depth chart: its unit, its label as printed (QB, WR-X, JACK, STAR, PK), its names."""

    unit: str | None = None  # Offense, Defense, Special teams
    slot: str
    players: Annotated[list[LineupPlayer], DropBad] = []


class TeamLineup(NotesModel):
    """One team's published depth chart (2026-10-02 owner request: depth charts and starting lineups on the
    live program). CFBD publishes no depth order, so the weekly task copies the chart the team or a depth-chart
    site published; the starting lineup is the first name at every slot."""

    team: str | None = None
    scheme: str | None = None  # the chart's own heading: "Spread option", "3-4"
    slots: Annotated[list[LineupSlot], DropBad] = []
    source: str | None = None
    sourceUrl: str | None = None
    updatedAt: str | None = None


class Lineups(NotesModel):
    us: TeamLineup | None = None
    them: TeamLineup | None = None
    source: str | None = None
    sourceUrl: str | None = None
    updatedAt: str | None = None


class Broadcast(NotesModel):
    """The TV crew for the game (public release Phase 7b; CFBD has only the network). Radio is left out."""

    network: str | None = None
    playByPlay: str | None = None
    analyst: str | None = None
    sideline: Annotated[list[str], DropBad] = []
    source: str | None = None


class Staff(NotesModel):
    """One team's coaches by name (public release Phase 7b; CFBD has head coaches only, no coordinators)."""

    team: str | None = None
    headCoach: str | None = None
    offensiveCoordinator: str | None = None
    defensiveCoordinator: str | None = None


class Coaches(NotesModel):
    us: Staff | None = None
    them: Staff | None = None
    source: str | None = None


class NotesFile(NotesModel):
    gameId: int | None = None
    author: str | None = None
    writtenAt: str | None = None
    sources: Annotated[list[NoteSource], DropBad] = []
    sections: Annotated[list[NoteSection], DropBad] = []
    availability: Annotated[list[AvailabilityRow], DropBad] = []
    availabilitySource: str | None = None
    availabilityUpdatedAt: str | None = None
    visitors: Visitors | None = None
    schemes: Schemes | None = None
    lineups: Lineups | None = None
    broadcast: Broadcast | None = None
    coaches: Coaches | None = None


def notes_path(data_dir: Path, game_id: int | str) -> Path:
    return data_dir / "notes" / f"{game_id}.json"


def load_notes(data_dir: Path, game_id: int | str | None) -> tuple[NotesFile | None, str | None]:
    """(notes, error). Both None when there is simply no file yet."""
    if game_id is None:
        return None, None
    path = notes_path(data_dir, game_id)
    if not path.exists():
        return None, None
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        log.warning("Notes file %s is unreadable: %s", path, exc)
        return None, f"{path.name} is not valid JSON: {exc}"
    if not isinstance(raw, dict):
        log.warning("Notes file %s is not an object", path)
        return None, f"{path.name} must hold a JSON object"
    try:
        notes = NotesFile.model_validate(raw)
    except ValidationError as exc:
        first = exc.errors()[0] if exc.errors() else {}
        where = ".".join(str(p) for p in first.get("loc", ())) or "file"
        log.warning("Notes file %s failed validation at %s: %s", path, where, first.get("msg"))
        return None, f"{path.name}: {where}: {first.get('msg', 'invalid')}"
    return notes, None
