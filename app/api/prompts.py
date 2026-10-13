"""The Prompts page and the one run (the Prompts phase, owner 2026-10-13).

GET  /api/prompts        everything the page draws: each prompt's state, this week's notes, the runners, the one run and
                         the schedule. No CFBD call beyond the cached team list and schedule.
GET  /api/prompts/run    the one run's status (app/services/prompt_runs.py)
POST /api/prompts/run    {all}: start it (what is missing, or everything again); the command-line tool and the page's
                         button both come here. A guest is refused by the guard (app/guests.py), like every change.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.api.envelope import envelope
from app.api.season_notes import _context, _notes, _today
from app.services.notes import load_notes
from app.services.prompt_runs import PromptRuns
from app.services.readiness import missing_notes

router = APIRouter(tags=["prompts"])


class RunRequest(BaseModel):
    all: bool = False


async def _this_week(request: Request) -> dict[str, Any]:
    """The next game and what its notes hold: {gameId, opponent, home, away, kickoff, writtenAt, missing, error}."""
    from app.api.notes import _game, _game_dict

    state = request.app.state
    try:
        game, ok = await _game(request, None)
    except Exception:  # noqa: BLE001 - the page still draws the season prompts; the notes card says why
        return {"gameId": None, "error": "This week's game could not be read, so its notes are not checked."}
    if game is None:
        return {"gameId": None, "error": None if ok else "The schedule could not be read from CFBD.", "none": "No upcoming game on our schedule." if ok else None}
    team = state.settings.team
    opponent = game.away_team if game.home_team == team else game.home_team
    notes, problem = load_notes(state.settings.data_dir, game.id)
    gaps = missing_notes(notes) if notes is not None else ["the written notes", "the injury report", "both depth charts", "the TV crew", "the coaches"]
    return {**_game_dict(game), "opponent": opponent, "completed": bool(game.completed), "writtenAt": getattr(notes, "writtenAt", None) if notes is not None else None, "missing": gaps, "problem": problem}


@router.get("/api/prompts")
async def prompts_page(request: Request) -> Any:
    state = request.app.state
    primaries, conferences, _meta = await _context(request)
    command = state.settings.claude_command
    runs: PromptRuns = state.prompt_runs
    return envelope({
        "commandFound": bool(runs.command_found()),
        "command": command,
        "season": _notes(request).status(primaries, conferences, _today(request)),
        "seasonRun": state.season_runner.status(command),
        "notesRun": state.notes.status(command),
        "notes": await _this_week(request),
        "run": runs.status(),
        "schedule": await state.claude_schedule.status(),
    }, source="live")


@router.get("/api/prompts/run")
async def prompts_run_status(request: Request) -> Any:
    runs: PromptRuns = request.app.state.prompt_runs
    return envelope(runs.status(), source="live")


@router.post("/api/prompts/run")
async def prompts_run(body: RunRequest, request: Request) -> Any:
    runs: PromptRuns = request.app.state.prompt_runs
    status = await runs.start(all=body.all)
    if status.get("error") and not status.get("running"):
        return envelope(status, source="live", errors=[{"code": "prompts_not_started", "message": status["error"]}])
    return envelope(status, source="live")
