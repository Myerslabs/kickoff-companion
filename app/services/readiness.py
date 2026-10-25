"""What is not loaded yet (Phase 18.3): the data that comes from a pasted or Claude-written prompt and has gaps.

The first screen after a server start lists them once ("Not loaded yet"), and the same list is the Settings readiness
card. Nothing here fetches: it reads what the season loads and this week's notes already hold.

    readiness(status, notes, game, now, command_found) -> {"items": [...], "ready": bool}
    missing_parts(notes) -> ["availability", ...]      what this week's notes lack, as the notes' part names
    missing_notes(notes) -> ["the injury report", ...] the same in words
    part_due(part, kickoff, now) -> (due, from)        whether a part can be had yet, and from when

An item: {"id", "title", "detail", "href", "run"}. `href` is the app route with the prompt for it: the Prompts page (the
Prompts phase, owner 2026-10-13), which every dead end leads to. `run` (post-freeze Wave 1, owner 2026-10-25: "each item
gets its Run button and an Open link") says what the To do's Run starts when Claude Code is found: {"kind": "prompts"} for
the season loads (the Load data run), {"kind": "notes", "gameId", "parts"} for this week's notes (parts None: the whole
notes). An item is listed only when its data can be had: a part of the notes that is published later in the game week
(the injury report two days before kickoff, the depth charts and the TV crew from the Monday) waits until then and is
named under "Later" instead (the rule of 2026-10-23: show Run, Copy and alerts only when the data can plausibly be had).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from app.services.notes_paste import PARTS, parts_words

# Days before kickoff from which a part is published. The rest (the written notes, the schemes, the coaches) can be had any
# time. The conference availability reports come two days out at the earliest; the depth charts and the TV crews with the
# game week; the visitor lists in the days before a home game.
DUE_DAYS = {"availability": 2, "visitors": 5, "lineups": 6, "broadcast": 6}


def _filled(value: Any) -> bool:
    """A notes block (lineups, broadcast, coaches) with anything in it."""
    if value is None:
        return False
    dump = value.model_dump(exclude_none=True) if hasattr(value, "model_dump") else value
    if isinstance(dump, dict):
        return any(_filled(v) for v in dump.values())
    if isinstance(dump, list):
        return any(_filled(v) for v in dump)
    return bool(str(dump).strip()) if dump is not None else False


def missing_parts(notes: Any) -> list[str]:
    """What this week's notes lack, as part names (app/services/notes_paste.py PARTS). The schemes and the visitors are
    not gaps: a visitor list is not published for every game, and the schemes come with the written notes."""
    if notes is None:
        return ["sections", "availability", "lineups", "broadcast", "coaches"]
    gaps: list[str] = []
    if not getattr(notes, "sections", None):
        gaps.append("sections")
    if not getattr(notes, "availability", None):
        gaps.append("availability")
    if not _filled(getattr(notes, "lineups", None)):
        gaps.append("lineups")
    if not _filled(getattr(notes, "broadcast", None)):
        gaps.append("broadcast")
    if not _filled(getattr(notes, "coaches", None)):
        gaps.append("coaches")
    return gaps


def missing_notes(notes: Any) -> list[str]:
    """What this week's notes lack, in words. `notes` is a NotesFile."""
    return [PARTS[p]["label"] for p in missing_parts(notes)]


def _kickoff(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        when = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


def part_due(part: str, kickoff: Any, now: datetime | None = None) -> tuple[bool, str | None]:
    """(due, from): whether the part can be had now, and the UTC time it can from (None when always). An unknown kickoff
    counts as due, since nothing says otherwise."""
    days = DUE_DAYS.get(part)
    when = _kickoff(kickoff)
    if days is None or when is None:
        return True, None
    start = when - timedelta(days=days)
    clock = now or datetime.now(timezone.utc)
    return clock >= start, start.isoformat(timespec="seconds").replace("+00:00", "Z")


def notes_due(kickoff: Any, now: datetime | None = None) -> dict[str, dict[str, Any]]:
    """Every part's (due, from), for the Pre-Game Program's bands."""
    return {part: dict(zip(("due", "from"), part_due(part, kickoff, now), strict=True)) for part in PARTS}


def _later_words(parts: list[str], kickoff: Any, tz: Any = None) -> str:
    bits = []
    for part in parts:
        _due, start = part_due(part, kickoff)
        when = _kickoff(start)
        day = f"{(when.astimezone(tz) if tz else when):%A}" if when else "later"
        bits.append(f"{PARTS[part]['label']} from {day}")
    return "; ".join(bits)


def readiness(status: dict[str, Any] | None, notes: Any, game: dict[str, Any] | None, today: date | datetime | None = None, *, command_found: bool = False, tz: Any = None) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    now = today if isinstance(today, datetime) else None
    s = status if isinstance(status, dict) else {}
    pre = [r for r in (s.get("preseason") or []) if isinstance(r, dict)]
    absent = [str(r.get("school")) for r in pre if not r.get("savedAt") and not r.get("shipped")]  # a season load shipped with the app counts (2026-10-22)
    coaches_saved, coaches_of = s.get("coachesSaved"), s.get("coachesOf")
    loads = {"kind": "prompts"}
    if absent or (isinstance(coaches_of, int) and coaches_of and coaches_saved != coaches_of):
        bits = []
        if absent:
            bits.append(f"preseason for {', '.join(absent[:3])}{'…' if len(absent) > 3 else ''}")
        if isinstance(coaches_of, int) and coaches_of and coaches_saved != coaches_of:
            bits.append(f"coaches for {coaches_saved or 0} of {coaches_of} teams")
        items.append({"id": "season", "title": f"The {s.get('season', '')} season load".replace("  ", " "), "detail": "Not loaded: " + " and ".join(bits) + ". One prompt loads it all.", "href": "#prompts", "run": loads})
    costs_saved = s.get("costsSaved")
    if isinstance(coaches_of, int) and coaches_of and costs_saved != coaches_of:
        items.append({"id": "costs", "title": "Roster costs", "detail": f"Rumored costs for {costs_saved or 0} of {coaches_of} teams. One more prompt.", "href": "#prompts", "run": loads})
    facts_saved = s.get("factsSaved")
    if isinstance(coaches_of, int) and coaches_of and facts_saved != coaches_of:
        items.append({"id": "facts", "title": "School history and facts", "detail": f"Loaded for {facts_saved or 0} of {coaches_of} teams. One prompt per conference.", "href": "#prompts", "run": loads})
    if game:
        name = game.get("opponent") or "the next game"
        kickoff = game.get("kickoff")
        gaps = missing_parts(notes)
        due = [p for p in gaps if part_due(p, kickoff, now)[0]]
        later = [p for p in gaps if p not in due]
        later_text = f" Later: {_later_words(later, kickoff, tz)}." if later else ""
        if due:
            whole = notes is None
            detail = f"{'Not loaded' if whole else 'Missing'}: {parts_words(due)}.{later_text}"
            items.append({"id": "notes", "title": f"This week's notes, {name}", "detail": detail, "href": "#prompts", "run": {"kind": "notes", "gameId": game.get("gameId"), "parts": None if whole else due}})
    for item in items:
        item["canRun"] = command_found
    return {"items": items, "ready": not items, "commandFound": command_found}
