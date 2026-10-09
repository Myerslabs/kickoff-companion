"""Your own notes during a game (Phase 19).

GET    /api/gamenotes/{game_id}              the notes, oldest first
POST   /api/gamenotes/{game_id}              {text, period?, clock?, score?}: add one
DELETE /api/gamenotes/{game_id}/{note_id}    remove one

A guest (view-only device, app/guests.py) can read and not write: the guard refuses its POST and DELETE before they get here."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.api.envelope import envelope, error_response
from app.services.gamenotes import GameNotes, NoteError

router = APIRouter(tags=["gamenotes"])


def _service(request: Request) -> GameNotes:
    return request.app.state.gamenotes


def _game(game_id: str) -> int | None:
    return int(game_id) if game_id.isdigit() and len(game_id) <= 12 else None


@router.get("/api/gamenotes/{game_id}")
async def list_notes(game_id: str, request: Request) -> Any:
    gid = _game(game_id)
    if gid is None:
        return error_response(404, "not_found", "No such game.")
    return envelope({"gameId": gid, "notes": _service(request).list(gid)}, source="live")


class NoteBody(BaseModel):
    text: str = Field(max_length=5000)
    period: int | None = None
    clock: str | None = Field(default=None, max_length=24)
    score: str | None = Field(default=None, max_length=60)


@router.post("/api/gamenotes/{game_id}")
async def add_note(game_id: str, body: NoteBody, request: Request) -> Any:
    gid = _game(game_id)
    if gid is None:
        return error_response(404, "not_found", "No such game.")
    try:
        note = _service(request).add(gid, body.text, {"period": body.period, "clock": body.clock, "score": body.score})
    except NoteError as exc:
        return error_response(422, "bad_note", str(exc))
    return envelope({"gameId": gid, "note": note, "notes": _service(request).list(gid)}, source="live")


@router.delete("/api/gamenotes/{game_id}/{note_id}")
async def delete_note(game_id: str, note_id: str, request: Request) -> Any:
    gid = _game(game_id)
    if gid is None or len(note_id) > 32:
        return error_response(404, "not_found", "No such note.")
    if not _service(request).delete(gid, note_id):
        return error_response(404, "not_found", "No such note.")
    return envelope({"gameId": gid, "notes": _service(request).list(gid)}, source="live")
