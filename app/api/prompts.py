"""The Prompts page and the one run (the Prompts phase, owner 2026-10-13).

GET  /api/prompts        everything the page draws: each prompt's state, this week's notes, the runners, the one run and
                         the schedule. No CFBD call beyond the cached team list and schedule.
GET  /api/prompts/run    the one run's status (app/services/prompt_runs.py)
POST /api/prompts/run    {all}: start it (what is missing, or everything again); the command-line tool and the page's
                         button both come here. A guest is refused by the guard (app/guests.py), like every change.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.api.envelope import envelope
from app.api.season_notes import _context, _notes, _today
from app.services.notes import load_notes, notes_path
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
    return {**_game_dict(game), "opponent": opponent, "completed": bool(game.completed), "writtenAt": getattr(notes, "writtenAt", None) if notes is not None else None, "missing": gaps, "problem": problem, **notes_location(state.settings.data_dir, game.id)}


def notes_location(data_dir: Path, game_id: int) -> dict[str, Any]:
    """Where a game's notes file lives on the server computer, to copy and open for notes written by hand (owner
    2026-10-16), and the example to start from when there is no file yet (a packaged install may not have one)."""
    path = notes_path(data_dir, game_id)
    example = data_dir / "notes" / "_example.json"
    return {"file": str(path), "fileExists": path.is_file(), "example": str(example) if example.is_file() else None}


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


SEASON_LABELS = {"season": "The season load", "preseason": "The season load", "coaches": "Coaches", "costs": "Roster costs", "facts": "School history and facts"}
ENDED = ("done", "skipped", "failed", "stopped")


def progress(state: Any) -> dict[str, Any]:
    """Is Claude Code loading data, how far along, and when the last run ended (owner 2026-10-16: it runs silently in
    the background with a loading bar, and the pages refresh once when ALL of it is in). Three runners can be busy: the
    one run (its steps), a season run (its batches) and the notes run (no steps: the bar has no fraction then)."""
    command = state.settings.claude_command
    runs = state.prompt_runs.status()
    season = state.season_runner.status(command)
    notes = state.notes.status(command)
    batches = [b for b in season.get("batches") or [] if isinstance(b, dict)]
    stamps = [runs.get("finishedAt"), notes.get("finishedAt"), *(b.get("finishedAt") for b in batches)]
    last = max((s for s in stamps if isinstance(s, str)), default=None)  # one ISO format, so the strings sort as times
    out: dict[str, Any] = {"running": False, "label": None, "detail": None, "fraction": None, "startedAt": None, "lastFinishedAt": last, "run": runs}
    season_done = sum(1 for b in batches if b.get("state") in ("saved", "failed", "stopped"))
    season_now = next((b for b in batches if b.get("state") == "running"), None)
    if runs.get("running"):
        steps = [s for s in runs.get("steps") or [] if isinstance(s, dict)]
        of = len(steps) or 1
        done = sum(1 for s in steps if s.get("state") in ENDED)
        current = next((s for s in steps if s.get("state") == "running"), None)
        inner = season_done / len(batches) if current and current.get("kind") != "notes" and season.get("running") and batches else 0.0
        detail = f"step {min(done + 1, of)} of {of}"
        if inner and season_now:
            detail += f", {season_now.get('key')} ({season_done + 1} of {len(batches)})"
        out.update(running=True, label=current.get("label") if current else "Checking what is missing", detail=detail, fraction=min(1.0, (done + inner) / of), startedAt=runs.get("startedAt"))
    elif season.get("running"):
        of = len(batches) or 1
        detail = f"{season_now.get('key')}, {min(season_done + 1, of)} of {of}" if season_now else f"{season_done} of {of}"
        out.update(running=True, label=SEASON_LABELS.get(str(season.get("kind")), "The season load"), detail=detail, fraction=season_done / of, startedAt=next((b.get("startedAt") for b in batches if b.get("startedAt")), None))
    elif notes.get("running"):
        out.update(running=True, label="The injury report" if notes.get("mode") == "injuries" else "This week's notes", detail="a few minutes", startedAt=notes.get("startedAt"))
    return out


@router.get("/api/prompts/progress")
async def prompts_progress(request: Request) -> Any:
    """The loading bar's one question, cheap enough to ask every few seconds while a run goes: no CFBD call, no files."""
    return envelope(progress(request.app.state), source="live")


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
