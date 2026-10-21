"""The trivia's routes (owner 2026-10-21): what the popups and the Trivia page read, and the writes a joined tablet
makes. Joining, leaving, renaming, answering and marking stay open to guests (app/guests.py GUEST_WRITES): they change
only that team's own line on the board. Ending the day is the host's.

    GET  /api/trivia?name=            the Trivia page
    GET  /api/trivia/now?name=        the popups: the open question (no answer), the standings, the welcome; opens the
                                      next question when one is due
    POST /api/trivia/join             {"name"}            -> the welcome and the season score so far
    POST /api/trivia/leave            {"name"}
    POST /api/trivia/rename           {"name", "newName"}
    POST /api/trivia/answer           {"name", "questionId", "choice"}
    POST /api/trivia/mark             {"questionId", "note"}   "wrong? mark it"
    POST /api/trivia/end              host only: ends today"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field

from app.api.envelope import envelope, error_response
from app.guests import is_host
from app.services.trivia import TriviaError, TriviaService

router = APIRouter(tags=["trivia"])


class Join(BaseModel):
    name: str = Field(max_length=200)


class Rename(BaseModel):
    name: str = Field(max_length=200)
    newName: str = Field(max_length=200)


class Answer(BaseModel):
    name: str = Field(max_length=200)
    questionId: str = Field(max_length=40)
    choice: int = Field(ge=0, le=2)


class Mark(BaseModel):
    questionId: str = Field(max_length=40)
    note: str = Field(default="", max_length=300)


def _service(request: Request) -> TriviaService:
    return request.app.state.trivia


def _now(request: Request):
    return request.app.state.cfbd._clock()


async def _games_on(request: Request) -> list[dict[str, Any]]:
    ticker = getattr(request.app.state, "ticker", None)
    if ticker is None:
        return []
    delay = float(getattr(request.app.state.prefs.prefs, "delaySeconds", 0) or 0)
    assembled = await ticker.ticker(delay)
    games = (assembled.data or {}).get("games") if isinstance(getattr(assembled, "data", None), dict) else None
    return [g for g in games if isinstance(g, dict)] if isinstance(games, list) else []


@router.get("/api/trivia")
async def trivia_page(request: Request, name: str = Query("", max_length=200)) -> Any:
    service = _service(request)
    now = _now(request)
    await service.tick(now, lambda: _games_on(request))
    return envelope(service.page_for(name or None, now, is_host=is_host(request.scope, request.app.state.host_access)), source="live")


@router.get("/api/trivia/now")
async def trivia_now(request: Request, name: str = Query("", max_length=200)) -> Any:
    service = _service(request)
    now = _now(request)
    await service.tick(now, lambda: _games_on(request))
    return envelope(service.now_for(name or None, now), source="live")


@router.post("/api/trivia/join")
async def trivia_join(body: Join, request: Request) -> Any:
    try:
        return envelope(_service(request).join(body.name, _now(request)), source="live")
    except TriviaError as exc:
        return error_response(400, "trivia", str(exc))


@router.post("/api/trivia/leave")
async def trivia_leave(body: Join, request: Request) -> Any:
    try:
        return envelope(_service(request).leave(body.name), source="live")
    except TriviaError as exc:
        return error_response(400, "trivia", str(exc))


@router.post("/api/trivia/rename")
async def trivia_rename(body: Rename, request: Request) -> Any:
    try:
        return envelope(_service(request).rename(body.name, body.newName), source="live")
    except TriviaError as exc:
        return error_response(400, "trivia", str(exc))


@router.post("/api/trivia/answer")
async def trivia_answer(body: Answer, request: Request) -> Any:
    try:
        return envelope(_service(request).answer(body.name, body.questionId, body.choice, _now(request)), source="live")
    except TriviaError as exc:
        return error_response(400, "trivia", str(exc))


@router.post("/api/trivia/mark")
async def trivia_mark(body: Mark, request: Request) -> Any:
    try:
        return envelope(_service(request).mark(body.questionId, body.note, _now(request)), source="live")
    except TriviaError as exc:
        return error_response(400, "trivia", str(exc))


@router.post("/api/trivia/end")
async def trivia_end(request: Request) -> Any:
    if not is_host(request.scope, request.app.state.host_access):
        return error_response(403, "view_only", "Only the host ends the trivia for the day.")
    ended = _service(request).end_day(_now(request), by="host")
    return envelope(ended or {"ended": False, "note": "No trivia is running."}, source="live")
