"""Program (P1 to P10), Newspaper (N1 to N4), and team page (T1) routes."""

from __future__ import annotations

from typing import Any
from urllib.parse import unquote

from fastapi import APIRouter, Request

from app.api.envelope import error_response
from app.api.players import respond
from app.api.season import archived_ids, mark_archived
from app.services.parts import Assembled
from app.services.program import ProgramService

router = APIRouter(tags=["program"])


def _mark_program(result: Assembled, request: Request) -> None:
    """Phase 16 (audit P-03): game.archived says the Archive holds this game, so the cover can link
    to it; the picker rows carry the same flag."""
    archived = archived_ids(request)
    game = result.data.get("game")
    if isinstance(game, dict):
        game["archived"] = game.get("gameId") in archived
    mark_archived(result.data.get("picker"), archived)


@router.get("/api/program/next")
async def program_next(request: Request) -> Any:
    service: ProgramService = request.app.state.program
    result = await service.program(None)
    if result is None:
        return error_response(404, "not_found", "No games on the schedule.")
    _mark_program(result, request)
    return respond(result)


@router.get("/api/program/{game_id}")
async def program_game(game_id: str, request: Request) -> Any:
    service: ProgramService = request.app.state.program
    if not game_id.isdigit() or len(game_id) > 12:
        return error_response(404, "not_found", "No game with that id.")
    result = await service.program(int(game_id))
    if result is None:
        return error_response(404, "not_found", "That game is not on our schedule.")
    _mark_program(result, request)
    return respond(result)


@router.get("/api/newspaper")
async def newspaper(request: Request) -> Any:
    service: ProgramService = request.app.state.program
    result = await service.newspaper()
    await request.app.state.archive.attach_recent_recap(result.data)  # Phase 16 BX: UX-07, the last final within 36 hours
    return respond(result)


@router.get("/api/team/{school}")
async def team_page(school: str, request: Request) -> Any:
    service: ProgramService = request.app.state.program
    name = unquote(school).strip()
    if not name or len(name) > 60:
        return error_response(404, "not_found", "No team with that name.")
    result = await service.team_page(name)
    if result is None:
        return error_response(404, "not_found", f"No FBS team called {name}.")
    if (result.data.get("team") or {}).get("isUs"):  # Phase 16 (G3-05): our schedule rows open the Archive too
        mark_archived(result.data.get("schedule"), archived_ids(request))
    return respond(result)
