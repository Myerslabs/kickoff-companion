"""Connects the Claude schedule (app/services/claude_schedule.py) to this app's pieces: the next game, the notes files, the
two runners and the settings. Kept apart so the schedule itself stays testable without an app."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import FastAPI

from app.services.claude_schedule import ClaudeSchedule, Ledger, Slot
from app.services.notes import notes_path
from app.services.notes_task import NotesRunner

log = logging.getLogger("kickoff.schedule")


def _parse(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def build_schedule(app: FastAPI) -> ClaudeSchedule:
    state = app.state
    shim = SimpleNamespace(app=app)  # the API helpers want something with `.app.state`

    def command() -> str:
        return state.settings.claude_command

    async def current_game() -> dict[str, Any] | None:
        from app.api.notes import _game

        try:
            game = await _game(shim, None)
        except Exception:  # noqa: BLE001 - no schedule is a quiet "nothing to run", not a crash; logged once per tick at most
            log.warning("The Claude schedule could not read the schedule; no game runs are planned.", exc_info=True)
            return None
        kickoff = _parse(getattr(game, "start_date", None)) if game is not None else None
        if game is None or game.completed or kickoff is None or getattr(game, "start_time_tbd", False):
            return None
        return {"gameId": game.id, "home": game.home_team, "away": game.away_team, "kickoff": kickoff}

    def notes_file(game_id: int) -> dict[str, Any]:
        try:
            raw = json.loads(notes_path(state.settings.data_dir, game_id).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return raw if isinstance(raw, dict) else {}

    async def data_is_current(slot: Slot) -> bool:
        if slot.game_id is not None:
            raw = notes_file(slot.game_id)
            stamp = _parse(raw.get("availabilityUpdatedAt")) if slot.kind == "injuries" else None
            stamp = stamp or _parse(raw.get("writtenAt"))
            return stamp is not None and stamp >= slot.at
        if slot.only_if_missing:
            from app.api.season_notes import _context

            primaries, conferences, _meta = await _context(shim)
            status = state.season_notes.status(primaries, conferences, datetime.now(settings_tz()).date())
            return all(r.get("savedAt") for r in status["preseason"]) and status["coachesSaved"] == status["coachesOf"]
        return False

    def settings_tz() -> Any:
        return state.settings.tzinfo

    async def start(slot: Slot, game: dict[str, Any] | None) -> dict[str, Any]:
        if slot.kind in ("notes", "injuries"):
            if game is None or game["gameId"] != slot.game_id:
                return {"error": "the game is not on the schedule any more"}
            info = {"gameId": game["gameId"], "home": game["home"], "away": game["away"], "kickoff": game["kickoff"].isoformat()}
            mode = "injuries" if slot.kind == "injuries" else "full"
            return await state.notes.start(info, command(), mode, state.settings.claude_lookup_model or None)
        from app.api.season_notes import start_season_run

        return await start_season_run(shim, slot.kind, None, slot.only_if_missing)

    def poll(slot: Slot) -> dict[str, Any]:
        if slot.kind in ("notes", "injuries"):
            runner: NotesRunner = state.notes
            if runner.running:
                return {"running": True}
            return {"running": False, "ok": bool(runner.saved and not runner.error), "error": runner.error or ("no usable answer saved" if not runner.saved else None), "changed": runner.changed}
        season = state.season_runner
        if season.running:
            return {"running": True}
        saved = [b for b in season.batches if b.state == "saved"]
        return {"running": False, "ok": bool(season.batches) and len(saved) == len(season.batches), "error": season.error or next((b.error for b in season.batches if b.error), None), "changed": None}

    return ClaudeSchedule(
        ledger=Ledger(state.settings.data_dir / "claude" / "ledger.json"),
        enabled=lambda: bool(state.prefs.prefs.scheduledRuns),
        command_found=lambda: NotesRunner.resolve_command(command()) is not None,
        current_game=current_game,
        season=lambda: state.settings.season,
        tz=ZoneInfo("America/New_York"),  # the publishers' times are Eastern, wherever this computer is
        data_is_current=data_is_current,
        start=start,
        poll=poll,
    )
