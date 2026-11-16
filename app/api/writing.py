"""Claude Code's writing (P4): the post-game piece, the scouting report, the paper's stories and picks, the trivia, the
weekly data check, and the weekly review's lessons.

GET  /api/writing/status                 the runner: what runs now, the last result, whether the command is found
GET  /api/writing/{kind}/{key}           what was written (404 not_written), and whether a run for it is going
                                         (trip: a stadium's Getting there, keyed by venue id; a shipped one until the install's own)
POST /api/writing/{kind}/{key}/run       write it now (the host's; JSON {"confirm": true})
GET  /api/claude/lessons                 the weekly review's lessons and the notes prompt's additions, each with its reason
POST /api/claude/additions/{id}          {"active": false} undoes an addition, {"active": true} brings it back
POST /api/ask, GET /api/ask              FEAT-12: a question about the page open, and the last answer

The schedule (app/services/claude_schedule.py) runs these by itself at their times; these routes are the page's way in."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

from app.api.envelope import envelope, error_response
from app.services.notes_task import NotesRunner
from app.services.trip import shipped_trip
from app.services.writing import KINDS, Lessons, WritingStore
from app.writing_setup import build_job

router = APIRouter(tags=["writing"])

READABLE = ("recap", "scout", "paper", "datacheck", "trivia", "trip")  # review answers go into the lessons, not a page of their own


class RunRequest(BaseModel):
    confirm: bool = False


class AdditionRequest(BaseModel):
    active: bool


def _key_ok(key: str) -> bool:
    return 0 < len(key) <= 40 and all(c.isalnum() or c in "-_" for c in key)


@router.get("/api/writing/status")
async def writing_status(request: Request) -> Any:
    command = request.app.state.settings.claude_command
    return envelope({**request.app.state.writing.status(), "commandFound": NotesRunner.resolve_command(command) is not None}, source="live")


@router.get("/api/writing/{kind}/{key}")
async def written(kind: str, key: str, request: Request, season: int | None = Query(default=None, ge=2000, le=2999)) -> Any:
    if kind not in READABLE or not _key_ok(key):
        return error_response(404, "not_found", "No such writing.")
    settings = request.app.state.settings
    if season is not None and season != settings.season:  # rollover R2: a past season's piece, read only (nothing to write now)
        record = WritingStore(settings.data_dir, season).load(kind, key) if key != "latest" else None
        return envelope({"kind": kind, "key": key, "season": season, "written": record, "running": False, "commandFound": False}, source="cache", fetched_at=record.get("writtenAt") if record else None)
    runner = request.app.state.writing
    store = WritingStore(settings.data_dir, settings.season)
    record = store.latest(kind) if key == "latest" else store.load(kind, key)  # "latest": the newest of a kind (the data check)
    if record is None and kind == "trip":
        record = shipped_trip(key)  # ENH-15: a stadium researched for the app, until this install's own run lands
    running = runner.running and runner.job is not None and runner.job.kind == kind and runner.job.key == key
    found = NotesRunner.resolve_command(settings.claude_command) is not None
    if record is None:
        return envelope({"kind": kind, "key": key, "written": None, "running": running, "commandFound": found}, source="cache")
    return envelope({"kind": kind, "key": key, "written": record, "running": running, "commandFound": found}, source="cache", fetched_at=record.get("writtenAt"))


@router.post("/api/writing/{kind}/{key}/run")
async def write_now(kind: str, key: str, body: RunRequest, request: Request) -> Any:
    if kind not in KINDS or not _key_ok(key):
        return error_response(404, "not_found", "No such writing.")
    if not body.confirm:
        return error_response(422, "confirm", "Confirm the run.")
    state = request.app.state
    job = await build_job(request.app, kind, key)
    if job is None:
        return error_response(409, "nothing_to_write", "There is nothing to write about yet (the game is not ours, or not played).")
    status = await state.writing.start(job, state.settings.claude_command)
    if status.get("error") and not status.get("running"):
        return error_response(409, "not_started", str(status["error"]))
    return envelope(status, source="live")


@router.get("/api/claude/lessons")
async def lessons(request: Request) -> Any:
    return envelope(Lessons(request.app.state.settings.data_dir).load(), source="cache")


@router.post("/api/claude/additions/{addition_id}")
async def set_addition(addition_id: str, body: AdditionRequest, request: Request) -> Any:
    if not _key_ok(addition_id):
        return error_response(404, "not_found", "No such addition.")
    row = Lessons(request.app.state.settings.data_dir).set_active(addition_id, body.active)
    if row is None:
        return error_response(404, "not_found", "No such addition.")
    return envelope(row, source="live")


class AskRequest(BaseModel):
    question: str
    route: str | None = None
    text: str | None = None


@router.post("/api/ask")
async def ask(body: AskRequest, request: Request) -> Any:
    """FEAT-12: a question about the page open, answered by Claude Code on the server (the host's; a guest cannot ask)."""
    state = request.app.state
    status = await state.ask.start(body.question, body.route, body.text, state.settings.team, state.settings.claude_command)
    if status.get("error") and not status.get("running"):
        return error_response(409, "not_started", str(status["error"]))
    return envelope(status, source="live")


@router.get("/api/ask")
async def ask_status(request: Request) -> Any:
    command = request.app.state.settings.claude_command
    return envelope({**request.app.state.ask.status(), "commandFound": NotesRunner.resolve_command(command) is not None}, source="live")

