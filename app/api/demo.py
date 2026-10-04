"""The demo page and the switch between the demo and this install's own team (public release Phase 9b).

GET /demo             the page: in the demo, what it is, what a CFBD key does, that nothing goes to Myers Labs and
                      nothing is paid to it, and the way to your own team; in the app, the way to the demo.
GET /api/demo         {demo, configured, ...}: which one is running.
POST /api/demo/leave  in the demo: next start is this install's own team (the setup page when there is no key yet).
POST /api/demo/enter  in the app: next start is the demo.

A switch saves data/startup.json (app/startmode.py) and restarts the server in place; the page waits for it."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse

from app import DATA_CREDIT, DATA_URL, PUBLISHER, REPO_URL, restart, startmode
from app.api.envelope import envelope, error_response
from app.config import STATIC_DIR
from app.services import plan

router = APIRouter(tags=["demo"])


def _state(request: Request) -> dict[str, Any]:
    demo = bool(getattr(request.app.state, "demo_mode", False))
    return {
        "demo": demo,
        "configured": bool(getattr(request.app.state, "home_configured", False)),
        "publisher": PUBLISHER,
        "repoUrl": REPO_URL,
        "dataCredit": DATA_CREDIT,
        "dataUrl": DATA_URL,
        "keyUrl": plan.KEY_URL,
        "plansUrl": plan.PLANS_URL,
    }


@router.get("/demo", include_in_schema=False)
async def demo_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "demo.html", media_type="text/html", headers={"Cache-Control": "no-cache"})


@router.get("/api/demo")
async def demo_state(request: Request) -> Any:
    return envelope(_state(request), source="live")


def _switch(request: Request, mode: str, reason: str) -> Any:
    try:
        startmode.save_mode(request.app.state.home_data_dir, mode)
    except OSError as exc:
        return error_response(500, "switch_failed", f"Could not save the choice: {exc}.")
    restart.request(reason)
    return envelope({**_state(request), "restarting": True, "next": mode}, source="live")


@router.post("/api/demo/leave")
async def leave_demo(request: Request) -> Any:
    if not getattr(request.app.state, "demo_mode", False):
        return error_response(409, "not_in_demo", "The demo is not running.")
    return _switch(request, startmode.APP, "leaving the demo for this install's own team")


@router.post("/api/demo/enter")
async def enter_demo(request: Request) -> Any:
    if getattr(request.app.state, "demo_mode", False):
        return error_response(409, "already_in_demo", "The demo is already running.")
    return _switch(request, startmode.DEMO, "showing the demo")
