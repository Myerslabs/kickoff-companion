"""The game notes from the app.

GET and POST /api/notes/run           start the Claude Code tool on the server and watch it (only where found); with
                                      "parts", only those parts of the notes, merged into the rest (post-freeze Wave 1).
GET /api/notes/prompt?gameId=         the prompt for one game, to copy into any AI chat (public release Phase 6);
                                      &parts=visitors,lineups for those parts alone.
POST /api/notes/preview               {gameId, text}: read a pasted answer and say what is in it; saves nothing.
POST /api/notes/save                  {gameId, text, parts?}: read it the same way and save data/notes/<game_id>.json,
                                      or with parts merge only those into the notes there.
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
from app.services.notes import notes_path
from app.services.notes_layout import program_figures
from app.services.notes_task import NotesRunner

router = APIRouter(tags=["notes"])


class RunRequest(BaseModel):
    gameId: int | None = Field(default=None, gt=0)
    parts: list[str] | None = Field(default=None, max_length=10)


async def _game(request: Request, game_id: int | None) -> tuple[Game | None, bool]:
    """A game on our schedule (the Game program's cached key), or the next one when no id is given, and whether the
    schedule itself could be read (when it could not, a missing game is CFBD's outage, not a wrong id)."""
    program = request.app.state.program
    schedule = await program.fetcher.fetch("schedule", "/games", {"year": program.year, "team": program.team}, Game, DataKind.SCHEDULE)
    return program._pick_game(schedule.records, game_id), bool(schedule.ok)


def _game_dict(game: Game) -> dict[str, Any]:
    return {"gameId": game.id, "home": game.home_team, "away": game.away_team, "kickoff": game.start_date}


async def with_figures(state: Any, info: dict[str, Any]) -> dict[str, Any]:
    """Wave 5: a full notes run or prompt names the program's figures it may put in the layout's strip."""
    return {**info, "figures": await program_figures(getattr(state, "program", None), info.get("gameId"))}


def _not_on_schedule(game_id: int | None, schedule_ok: bool = True) -> Any:
    if not schedule_ok:
        return error_response(503, "upstream", "The schedule could not be read from CFBD, so the game cannot be checked. Try again in a minute.")
    return error_response(404, "not_found", "That game is not on our schedule." if game_id else "No upcoming game on our schedule.")


@router.get("/api/notes/run")
async def notes_status(request: Request) -> Any:
    runner: NotesRunner = request.app.state.notes
    return envelope(runner.status(request.app.state.settings.claude_command), source="live")


@router.post("/api/notes/run")
async def notes_start(body: RunRequest, request: Request) -> Any:
    runner: NotesRunner = request.app.state.notes
    game, ok = await _game(request, body.gameId)
    if game is None:
        return _not_on_schedule(body.gameId, ok)
    parts = notes_paste.parse_parts(body.parts or [])
    info = _game_dict(game) if parts else await with_figures(request.app.state, _game_dict(game))
    status = await runner.start(info, request.app.state.settings.claude_command, mode=f"parts:{','.join(parts)}" if parts else "full")
    if status.get("error") and not status.get("running"):
        return envelope(status, source="live", errors=[{"code": "notes_not_started", "message": status["error"]}])
    return envelope(status, source="live")


# --- copy and paste (public release Phase 6) -------------------------------------------------------------


@router.get("/api/notes/prompt")
async def notes_prompt(request: Request, gameId: int | None = None, parts: str | None = None) -> Any:  # noqa: N803 - the query name the page sends
    game, ok = await _game(request, gameId if gameId and gameId > 0 else None)
    if game is None:
        return _not_on_schedule(gameId, ok)
    runner: NotesRunner = request.app.state.notes
    _template, custom = notes_paste.read_template(request.app.state.settings.data_dir)
    asked = notes_paste.parse_parts(parts or "")
    prompt = runner.build_prompt(_game_dict(game) if asked else await with_figures(request.app.state, _game_dict(game)), f"parts:{','.join(asked)}" if asked else "full")
    path = notes_path(request.app.state.settings.data_dir, game.id)  # Phase 17 #12: the path chip copies this
    return envelope({**_game_dict(game), "prompt": prompt, "custom": custom, "chars": len(prompt), "path": str(path)}, source="live")


class PasteRequest(BaseModel):
    gameId: int = Field(gt=0)
    text: str = Field(max_length=notes_paste.MAX_PASTE)
    parts: list[str] | None = Field(default=None, max_length=10)


@router.post("/api/notes/preview")
async def notes_preview(body: PasteRequest, request: Request) -> Any:
    game, ok = await _game(request, body.gameId)
    if game is None:
        return _not_on_schedule(body.gameId, ok)
    return envelope(notes_paste.read_answer(body.text, game.id).as_dict(), source="live")


@router.post("/api/notes/save")
async def notes_save(body: PasteRequest, request: Request) -> Any:
    game, ok = await _game(request, body.gameId)
    if game is None:
        return _not_on_schedule(body.gameId, ok)
    reading = notes_paste.read_answer(body.text, game.id)
    if reading.notes is None:
        return error_response(422, "notes_unreadable", reading.error or "The answer has no usable notes.")
    parts = notes_paste.parse_parts(body.parts or [])
    try:
        if parts:  # post-freeze Wave 1: one band's part, merged into the notes already there
            changed = notes_paste.merge_parts(request.app.state.settings.data_dir, game.id, reading.notes, parts)
            return envelope({**reading.as_dict(), "saved": True, "parts": parts, "changed": changed}, source="live")
        changed = notes_paste.merge_notes(request.app.state.settings.data_dir, game.id, reading.notes)  # owner 2026-10-30: a whole answer builds on the week's notes
        return envelope({**reading.as_dict(), "saved": True, "changed": changed}, source="live")
    except notes_paste.NotesUnreadable as exc:
        return error_response(409, "notes_unreadable", f"The notes already saved for this game could not be read, so nothing was merged: {exc}.")
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
