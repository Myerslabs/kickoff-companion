"""The game notes from the app.

GET and POST /api/notes/run           start the Claude Code tool on the server and watch it (only where found).
GET /api/notes/prompt?gameId=         the prompt for one game, to copy into any AI chat (public release Phase 6).
POST /api/notes/preview               {gameId, text}: read a pasted answer and say what is in it; saves nothing.
POST /api/notes/save                  {gameId, text}: read it the same way and save data/notes/<game_id>.json.
GET, PUT and DELETE /api/notes/template  the prompt template: read it, save an edit, go back to the default.

Any device on the home network may paste (owner answer 2026-10-03). A save replaces the game's notes. An
answer for another game number is a warning, not a refusal; it is saved for the game asked about."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.api.envelope import envelope, error_response
from app.cache import DataKind
from app.cfbd.models import Game
from app.services import notes_paste
from app.services.notes_task import NotesRunner
from app.services.prefs import PrefsStore

router = APIRouter(tags=["notes"])


class RunRequest(BaseModel):
    gameId: int | None = Field(default=None, gt=0)


async def _game(request: Request, game_id: int | None) -> Game | None:
    """A game on our schedule (the Game program's cached key), or the next one when no id is given."""
    program = request.app.state.program
    schedule = await program.fetcher.fetch("schedule", "/games", {"year": program.year, "team": program.team}, Game, DataKind.SCHEDULE)
    return program._pick_game(schedule.records, game_id)


def _game_dict(game: Game) -> dict[str, Any]:
    return {"gameId": game.id, "home": game.home_team, "away": game.away_team, "kickoff": game.start_date}


def _not_on_schedule(game_id: int | None) -> Any:
    return error_response(404, "not_found", "That game is not on our schedule." if game_id else "No upcoming game on our schedule.")


@router.get("/api/notes/run")
async def notes_status(request: Request) -> Any:
    runner: NotesRunner = request.app.state.notes
    prefs: PrefsStore = request.app.state.prefs
    return envelope(runner.status(prefs.prefs.notesCommand), source="live")


@router.post("/api/notes/run")
async def notes_start(body: RunRequest, request: Request) -> Any:
    runner: NotesRunner = request.app.state.notes
    prefs: PrefsStore = request.app.state.prefs
    game = await _game(request, body.gameId)
    if game is None:
        return _not_on_schedule(body.gameId)
    status = await runner.start(_game_dict(game), prefs.prefs.notesCommand)
    if status.get("error") and not status.get("running"):
        return envelope(status, source="live", errors=[{"code": "notes_not_started", "message": status["error"]}])
    return envelope(status, source="live")


# --- copy and paste (public release Phase 6) -------------------------------------------------------------


@router.get("/api/notes/prompt")
async def notes_prompt(request: Request, gameId: int | None = None) -> Any:  # noqa: N803 - the query name the page sends
    game = await _game(request, gameId if gameId and gameId > 0 else None)
    if game is None:
        return _not_on_schedule(gameId)
    runner: NotesRunner = request.app.state.notes
    _template, custom = notes_paste.read_template(request.app.state.settings.data_dir)
    prompt = runner.build_prompt(_game_dict(game))
    return envelope({**_game_dict(game), "prompt": prompt, "custom": custom, "chars": len(prompt)}, source="live")


class PasteRequest(BaseModel):
    gameId: int = Field(gt=0)
    text: str = Field(max_length=notes_paste.MAX_PASTE)


@router.post("/api/notes/preview")
async def notes_preview(body: PasteRequest, request: Request) -> Any:
    game = await _game(request, body.gameId)
    if game is None:
        return _not_on_schedule(body.gameId)
    return envelope(notes_paste.read_answer(body.text, game.id).as_dict(), source="live")


@router.post("/api/notes/save")
async def notes_save(body: PasteRequest, request: Request) -> Any:
    game = await _game(request, body.gameId)
    if game is None:
        return _not_on_schedule(body.gameId)
    reading = notes_paste.read_answer(body.text, game.id)
    if reading.notes is None:
        return error_response(422, "notes_unreadable", reading.error or "The answer has no usable notes.")
    try:
        notes_paste.save_notes(request.app.state.settings.data_dir, game.id, reading.notes)
    except OSError as exc:
        return error_response(500, "notes_not_saved", f"The notes could not be saved: {exc}.")
    return envelope({**reading.as_dict(), "saved": True}, source="live")


def _template_payload(request: Request) -> dict[str, Any]:
    template, custom = notes_paste.read_template(request.app.state.settings.data_dir)
    return {
        "template": template,
        "custom": custom,
        "default": notes_paste.DEFAULT_PROMPT,
        "placeholders": list(notes_paste.PLACEHOLDERS),
        "file": str(notes_paste.prompt_path(request.app.state.settings.data_dir)),
        "maxChars": notes_paste.MAX_TEMPLATE,
    }


class TemplateRequest(BaseModel):
    template: str = Field(max_length=notes_paste.MAX_TEMPLATE)


@router.get("/api/notes/template")
async def template_get(request: Request) -> Any:
    return envelope(_template_payload(request), source="live")


@router.put("/api/notes/template")
async def template_put(body: TemplateRequest, request: Request) -> Any:
    text = body.template.replace("\r\n", "\n")
    if not text.strip():
        return error_response(422, "bad_template", "The prompt is empty. Use 'Back to the default' to restore it.")
    if "{game_id}" not in text:
        return error_response(422, "bad_template", "Keep {game_id} in the prompt: it ties the answer to the game.")
    data_dir = request.app.state.settings.data_dir
    try:
        notes_paste.write_template(data_dir, None if text.strip() == notes_paste.DEFAULT_PROMPT.strip() else text)
    except OSError as exc:
        return error_response(500, "template_not_saved", f"The prompt could not be saved: {exc}.")
    return envelope(_template_payload(request), source="live")


@router.delete("/api/notes/template")
async def template_reset(request: Request) -> Any:
    try:
        notes_paste.write_template(request.app.state.settings.data_dir, None)
    except OSError as exc:
        return error_response(500, "template_not_saved", f"The prompt could not be reset: {exc}.")
    return envelope(_template_payload(request), source="live")
