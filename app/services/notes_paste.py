"""Notes by copy and paste (public release Phase 6). The app writes a prompt for one game; the owner copies it
into any AI chat that can search the web, pastes the answer back, sees a preview, and saves it as
`data/notes/<game_id>.json`. The app never calls an AI and spends no CFBD call.

- The prompt carries the whole notes shape inline (a chat cannot read files), filled from the game and the
  team settings. The template lives in data/notes/PROMPT.md when the owner edits it in Settings, else the
  default below. Placeholders are replaced by name only, so a stray brace in an edited prompt is harmless.
- The answer is read leniently: code fences and chatter around the JSON are ignored, a trailing comma is
  forgiven, and a bad row is skipped and counted instead of refusing the whole answer.
- Warnings, never refusals: a different game number (the notes are saved for this game), no sources, a
  source without a link, rows skipped. Only an answer with no JSON object at all, or nothing usable in it,
  is refused.

The Claude Code button (app/services/notes_task.py) uses the same prompt and reads the tool's answer the same
way, so both paths save through save_notes()."""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.cfbd import models as cfbd_models
from app.services.notes import NotesFile, notes_path

log = logging.getLogger("kickoff.notes")

PROMPT_FILE = "PROMPT.md"
MAX_PASTE = 400_000  # characters; a full notes answer is about 10,000
MAX_TEMPLATE = 20_000
PASTED_AUTHOR = "An AI chat, pasted in the app"
PLACEHOLDERS = ("team", "team_name", "conference", "season", "game_id", "home", "away", "opponent", "kickoff", "shape")
PLACEHOLDER = re.compile(r"\{(" + "|".join(PLACEHOLDERS) + r")\}")
LEGACY_MARKS = ("{notes_path}", "{example_path}")  # the file-writing prompt before Phase 6

DEFAULT_PROMPT = """You are writing the pre-game notes for a second-screen app that follows {team} ({team_name}, {conference}).

The game: {away} at {home}, kickoff {kickoff} (the app's game id is {game_id}, season {season}). The opponent is {opponent}.

Search the web and answer with ONE JSON object in a single ```json code block, nothing else. Use exactly this shape; every field is optional, so leave out what you cannot find, but keep these keys and types:

{shape}

What to fill:
1. "schemes": one short label each for {team}'s offense and defense (for example "Spread, 11 personnel, up-tempo" or "4-2-5, quarters coverage").
2. "sections": program notes. A section each for the coaching matchup, key matchups, the betting line and how it moved, and anything notable this week. Plain football language, one or two short paragraphs per section.
3. "availability": the {conference} availability report where the conference publishes one, else the latest injury news, for both teams. One row per player with name, position, status (Out, Doubtful, Questionable or Probable) and a short note. Fill "availabilitySource" and "availabilityUpdatedAt".
4. "visitors": recruits reported to be visiting for this game, under "home" or "away", with the source.
5. "lineups": both teams' published depth charts, {team} under "us" and {opponent} under "them". Copy the chart the team released this week (its game notes, or a beat report of it) or a depth-chart site. One entry per slot with the slot label as printed (QB, WR-X, LT, JACK, STAR, NB, PK, P, KR) and the names in the printed order, the starter first, with jersey number and class where printed.
6. "broadcast": the TV crew calling this game: the network, the play-by-play voice, the analyst and the sideline reporter(s). TV only, not radio.
7. "coaches": each team's head coach, offensive coordinator and defensive coordinator by name, {team} under "us" and {opponent} under "them".
8. "sources": every page you used, with its real URL.

Rules: never invent a player, a status or a number; leave a list empty when nothing reliable is published. Set "gameId" to {game_id}, "author" to the name of the assistant writing it, and "writtenAt" to the current UTC time. Valid JSON only: no comments, no trailing commas.
"""


def shape_example(team: str, opponent: str, conference: str) -> str:
    """The notes shape with sample values, as the prompt shows it. Built from the team settings, so it names
    no real school."""
    example = {
        "gameId": 0,
        "author": "Assistant name",
        "writtenAt": "2026-01-01T12:00:00Z",
        "sources": [{"label": f"{conference} availability report", "url": "https://..."}],
        "schemes": {"offense": "Spread, 11 personnel, up-tempo", "defense": "4-2-5, quarters coverage", "source": "Where the labels come from"},
        "sections": [{"heading": "Coaching matchup", "paragraphs": ["One or two short paragraphs."]}],
        "availability": [{"name": "Player Name", "position": "WR", "status": "Questionable", "note": "ankle"}],
        "availabilitySource": f"{conference} availability report, Thursday",
        "availabilityUpdatedAt": "2026-01-01",
        "visitors": {"home": [{"name": "Recruit Name", "position": "WR", "stars": 4, "highSchool": "School", "hometown": "City, ST", "classYear": 2027, "status": "confirmed"}], "away": [], "source": "Where the list comes from", "sourceUrl": "https://...", "updatedAt": "2026-01-01"},
        "lineups": {
            "us": {"team": team, "scheme": "The chart's own heading", "source": "Where the chart comes from", "sourceUrl": "https://...", "updatedAt": "2026-01-01",
                   "slots": [{"unit": "Offense", "slot": "QB", "players": [{"name": "Starter Name", "number": 12, "classYear": "JR"}, {"name": "Backup Name", "number": 7, "classYear": "FR"}]}]},
            "them": {"team": opponent, "slots": []},
        },
        "broadcast": {"network": "Network", "playByPlay": "Play-by-play voice", "analyst": "Analyst", "sideline": ["Sideline reporter"], "source": "Where the crew is listed"},
        "coaches": {
            "us": {"team": team, "headCoach": "Head coach", "offensiveCoordinator": "Offensive coordinator", "defensiveCoordinator": "Defensive coordinator"},
            "them": {"team": opponent, "headCoach": "Head coach", "offensiveCoordinator": "Offensive coordinator", "defensiveCoordinator": "Defensive coordinator"},
            "source": "Where the staffs come from",
        },
    }
    return json.dumps(example, indent=2)


def kickoff_text(value: Any, tz: Any = None) -> str:
    """'Saturday, October 24, 7:00 PM EDT' in the server's time zone; the raw value when it does not parse."""
    if not isinstance(value, str) or not value.strip():
        return "time to be announced"
    try:
        when = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return value.strip()
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    local = when.astimezone(tz) if tz is not None else when
    hour = local.hour % 12 or 12
    return f"{local:%A, %B} {local.day}, {hour}:{local.minute:02d} {'AM' if local.hour < 12 else 'PM'} {local.tzname() or 'UTC'}"


def prompt_values(who: Any, game: dict[str, Any], season: int | None, tz: Any = None) -> dict[str, Any]:
    """The placeholder values for one game. `who` is the team identity (app/services/identity.py); `game`
    has gameId, home, away and kickoff; `tz` is the server's time zone for the kickoff."""
    team = getattr(who, "school", None) or "our team"
    conference = getattr(who, "conference", None) or "its conference"
    home, away = game.get("home") or "the home team", game.get("away") or "the away team"
    opponent = away if home == team else home if away == team else "the opponent"
    return {
        "team": team,
        "team_name": getattr(who, "name", None) or team,
        "conference": conference,
        "season": season if season is not None else "this",
        "game_id": game.get("gameId"),
        "home": home,
        "away": away,
        "opponent": opponent,
        "kickoff": kickoff_text(game.get("kickoff"), tz),
        "shape": shape_example(team, opponent, conference),
    }


def build_prompt(data_dir: Path, who: Any, game: dict[str, Any], season: int | None, tz: Any = None) -> str:
    template, _custom = read_template(data_dir)
    return fill(template, prompt_values(who, game, season, tz))


def fill(template: str, values: dict[str, Any]) -> str:
    """Replace the known {placeholders} by name; any other brace is left as written."""
    return PLACEHOLDER.sub(lambda m: str(values.get(m.group(1), m.group(0))), template)


# --- the template on disk --------------------------------------------------------------------------------


def prompt_path(data_dir: Path) -> Path:
    return Path(data_dir) / "notes" / PROMPT_FILE


def read_template(data_dir: Path) -> tuple[str, bool]:
    """(template, custom). A missing, empty, unreadable or pre-Phase 6 file means the default."""
    path = prompt_path(data_dir)
    if not path.is_file():
        return DEFAULT_PROMPT, False
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        log.warning("Notes prompt %s is unreadable (%s); the default applies", path, exc)
        return DEFAULT_PROMPT, False
    if not text.strip():
        return DEFAULT_PROMPT, False
    if any(mark in text for mark in LEGACY_MARKS):
        log.warning("Notes prompt %s is the old file-writing prompt; the default applies (save a new one in Settings)", path)
        return DEFAULT_PROMPT, False
    return text, True


def write_template(data_dir: Path, text: str | None) -> None:
    """Save an edited template, or remove the file (None) to go back to the default."""
    path = prompt_path(data_dir)
    if text is None:
        with contextlib.suppress(FileNotFoundError):
            path.unlink()
        return
    _atomic_write(path, text)


# --- reading an answer -----------------------------------------------------------------------------------

FENCE = re.compile(r"```(?:json|JSON)?\s*\n(.*?)```", re.DOTALL)
TRAILING_COMMA = re.compile(r",(\s*[}\]])")


def _objects(text: str) -> list[Any]:
    """Every JSON object the text holds: inside code fences first, then anywhere a "{" starts one."""
    decoder = json.JSONDecoder()
    found: list[Any] = []
    candidates = [m.group(1) for m in FENCE.finditer(text)] + [text]
    for chunk in candidates:
        for attempt in dict.fromkeys((chunk, TRAILING_COMMA.sub(r"\1", chunk))):
            index = attempt.find("{")
            while index != -1:
                try:
                    value, end = decoder.raw_decode(attempt, index)
                except ValueError:
                    index = attempt.find("{", index + 1)
                    continue
                if isinstance(value, dict):
                    found.append(value)
                index = attempt.find("{", end)
        if any(_score(obj) for obj in found):
            return found  # a fenced block that holds notes wins over the rest of the text
    return found


def _score(obj: dict[str, Any]) -> int:
    keys = {"sections", "availability", "visitors", "lineups", "schemes", "sources", "gameId"}
    return len(keys & set(obj))


@dataclass
class Reading:
    """What an answer holds: the notes to save (or None), what is in them, and what to tell the owner."""

    notes: NotesFile | None
    summary: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"ok": self.notes is not None, "summary": self.summary, "warnings": self.warnings, "error": self.error}


def _count(raw: Any) -> int:
    return len(raw) if isinstance(raw, list) else 0


def read_answer(text: Any, game_id: int, *, now: datetime | None = None) -> Reading:
    """Read a pasted answer for one game. Never raises."""
    if not isinstance(text, str) or not text.strip():
        return Reading(None, error="Paste the AI's answer first.")
    if len(text) > MAX_PASTE:
        return Reading(None, error=f"That is {len(text):,} characters; a notes answer is far shorter. Paste only the answer.")
    objects = _objects(text.lstrip("﻿"))
    if not objects:
        return Reading(None, error="No JSON object in the answer. Ask the chat to answer with the JSON block only, then paste it again.")
    raw = max(objects, key=_score)
    if _score(raw) == 0:
        return Reading(None, error="The JSON in the answer is not notes: it has none of sections, availability, visitors, lineups, schemes or sources.")
    problems: list[str] = []
    warnings: list[str] = []
    raw = dict(raw)
    notes: NotesFile | None = None
    token = cfbd_models._dropped.set(problems)  # the notes models drop bad rows through the same collector as CFBD's
    try:
        for _ in range(len(raw) + 1):  # a top-level field of the wrong type is left out, never the whole answer
            problems.clear()  # each attempt notes its own dropped rows
            try:
                notes = NotesFile.model_validate(raw)
                break
            except ValidationError as exc:
                first = exc.errors()[0] if exc.errors() else {}
                key = (first.get("loc") or (None,))[0]
                if not isinstance(key, str) or key not in raw:
                    return Reading(None, error=f"The notes could not be read: {first.get('msg', 'invalid')}.")
                del raw[key]
                warnings.append(f'"{key}" could not be read ({first.get("msg", "invalid")}) and was left out.')
    finally:
        cfbd_models._dropped.reset(token)
    if notes is None:
        return Reading(None, error="The notes could not be read.")
    asked = raw.get("gameId")
    if isinstance(asked, int) and not isinstance(asked, bool) and asked not in (0, game_id):
        warnings.append(f"The answer is for game {asked}, not this game ({game_id}). Saving puts it on this game.")
    notes.gameId = game_id
    if not notes.author:
        notes.author = PASTED_AUTHOR
    if not notes.writtenAt:
        notes.writtenAt = (now or datetime.now(timezone.utc)).isoformat(timespec="seconds").replace("+00:00", "Z")
    if problems:
        warnings.append(f"{len(problems)} row{'s' if len(problems) != 1 else ''} or block{'s' if len(problems) != 1 else ''} could not be read and {'were' if len(problems) != 1 else 'was'} left out (first: {problems[0]}).")
    if not notes.sources:
        warnings.append("No sources are listed. Ask the chat for the pages it used.")
    elif any(not (s.url or "").startswith(("http://", "https://")) for s in notes.sources):
        warnings.append("Some sources have no link.")
    lineups = notes.lineups
    summary = {
        "gameId": game_id,
        "author": notes.author,
        "writtenAt": notes.writtenAt,
        "sections": [s.heading for s in notes.sections],
        "availability": len(notes.availability),
        "availabilityRows": [a.model_dump() for a in notes.availability[:6]],
        "visitors": {"home": len(notes.visitors.home), "away": len(notes.visitors.away)} if notes.visitors else {"home": 0, "away": 0},
        "lineups": {"us": len(lineups.us.slots) if lineups and lineups.us else 0, "them": len(lineups.them.slots) if lineups and lineups.them else 0},
        "schemes": notes.schemes.model_dump() if notes.schemes else None,
        "broadcast": notes.broadcast.model_dump() if notes.broadcast else None,
        "coaches": sum(1 for s in ((notes.coaches.us, notes.coaches.them) if notes.coaches else ()) for name in ((s.headCoach, s.offensiveCoordinator, s.defensiveCoordinator) if s else ()) if name),
        "sources": len(notes.sources),
        "skipped": len(problems),
        "rawCounts": {k: _count(raw.get(k)) for k in ("sections", "availability", "sources")},
    }
    has_crew = bool(notes.broadcast and (notes.broadcast.playByPlay or notes.broadcast.analyst or notes.broadcast.sideline))
    if not (notes.sections or notes.availability or (notes.visitors and (notes.visitors.home or notes.visitors.away)) or (lineups and ((lineups.us and lineups.us.slots) or (lineups.them and lineups.them.slots))) or (notes.schemes and (notes.schemes.offense or notes.schemes.defense)) or has_crew or summary["coaches"]):
        return Reading(None, summary, warnings, "The answer has no notes in it: no sections, availability, visitors, lineups or schemes.")
    return Reading(notes, summary, warnings)


# --- saving ------------------------------------------------------------------------------------------------


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.stem}-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except OSError:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def save_notes(data_dir: Path, game_id: int, notes: NotesFile) -> Path:
    """Write the notes for a game, replacing any there (owner answer 2026-10-03: no confirm, no backup)."""
    path = notes_path(Path(data_dir), game_id)
    _atomic_write(path, json.dumps(notes.model_dump(exclude_none=True), indent=2, ensure_ascii=False) + "\n")
    log.info("Notes saved for game %s (%s)", game_id, notes.author or "no author")
    return path
