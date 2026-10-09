"""What is not loaded yet (Phase 18.3): the data that comes from a pasted or Claude-written prompt and has gaps.

The first screen after a server start lists them once ("Not loaded yet"), and the same list is the Settings readiness
card. Nothing here fetches: it reads what the season loads and this week's notes already hold.

    readiness(status, notes, game, today) -> {"items": [...], "ready": bool}

An item: {"id", "title", "detail", "href"}. `href` is the app route that opens the prompt for it.
"""

from __future__ import annotations

from datetime import date
from typing import Any


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


def missing_notes(notes: Any) -> list[str]:
    """What this week's notes lack, in words. `notes` is a NotesFile."""
    gaps: list[str] = []
    if not getattr(notes, "sections", None):
        gaps.append("the written notes")
    if not getattr(notes, "availability", None):
        gaps.append("the injury report")
    if not _filled(getattr(notes, "lineups", None)):
        gaps.append("both depth charts")
    if not _filled(getattr(notes, "broadcast", None)):
        gaps.append("the TV crew")
    if not _filled(getattr(notes, "coaches", None)):
        gaps.append("the coaches")
    return gaps


def readiness(status: dict[str, Any] | None, notes: Any, game: dict[str, Any] | None, today: date | None = None) -> dict[str, Any]:
    items: list[dict[str, str]] = []
    s = status if isinstance(status, dict) else {}
    pre = [r for r in (s.get("preseason") or []) if isinstance(r, dict)]
    absent = [str(r.get("school")) for r in pre if not r.get("savedAt")]
    coaches_saved, coaches_of = s.get("coachesSaved"), s.get("coachesOf")
    if absent or (isinstance(coaches_of, int) and coaches_of and coaches_saved != coaches_of):
        bits = []
        if absent:
            bits.append(f"preseason for {', '.join(absent[:3])}{'…' if len(absent) > 3 else ''}")
        if isinstance(coaches_of, int) and coaches_of and coaches_saved != coaches_of:
            bits.append(f"coaches for {coaches_saved or 0} of {coaches_of} teams")
        items.append({"id": "season", "title": f"The {s.get('season', '')} season load".replace("  ", " "), "detail": "Not loaded: " + " and ".join(bits) + ". One prompt loads it all.", "href": "#preseason"})
    costs_saved = s.get("costsSaved")
    if isinstance(coaches_of, int) and coaches_of and costs_saved != coaches_of:
        items.append({"id": "costs", "title": "Roster costs", "detail": f"Rumored costs for {costs_saved or 0} of {coaches_of} teams. One more prompt.", "href": "#preseason"})
    if game:
        name = game.get("opponent") or "the next game"
        if notes is None:
            items.append({"id": "notes", "title": f"This week's notes, {name}", "detail": "Not loaded: the written notes, injury report, depth charts, TV crew and coaches.", "href": "#program"})
        else:
            gaps = missing_notes(notes)
            if gaps:
                items.append({"id": "notes", "title": f"This week's notes, {name}", "detail": "Missing: " + ", ".join(gaps) + ".", "href": "#program"})
    return {"items": items, "ready": not items}
