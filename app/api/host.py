"""Friends and the big screen (Phase 18.6).

GET    /api/host                who is asking: {pinSet, isHost, serverComputer}
POST   /api/host/pin            {pin}: set or change the host PIN (the server computer, or a signed-in host)
POST   /api/host/login          {pin}: a device becomes a host (sets the host cookie); five wrong tries lock it out for a minute
POST   /api/host/logout         this device is a guest again
DELETE /api/host                remove the PIN: every device is the host again (the server computer, or a host)
GET    /api/invite              what Invite friends shows: the address by IP number, the guide and warnings
GET    /api/board/screens       the monitors on the server computer and whether a browser was found
POST   /api/board/open          {screen}: open the game-day board full screen on that monitor (the server computer)
POST   /api/board/close         close it again
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field

from app import REPO_IS_PUBLIC, REPO_URL
from app.api.envelope import envelope, error_response
from app.guests import is_host, on_server_computer
from app.netinfo import http_url, lan_ip
from app.services import screens
from app.services.host import COOKIE, COOKIE_SECONDS, HostAccess, LockedOut, PinError

router = APIRouter(tags=["host"])


def _access(request: Request) -> HostAccess:
    return request.app.state.host_access


def _who(request: Request) -> str:
    return request.client.host if request.client else "?"


def _status(request: Request) -> dict[str, Any]:
    access = _access(request)
    scope = request.scope
    return {"pinSet": access.pin_set, "isHost": is_host(scope, access), "serverComputer": on_server_computer(scope)}


@router.get("/api/host")
async def host_status(request: Request) -> Any:
    return envelope(_status(request), source="live")


class PinBody(BaseModel):
    pin: str = Field(max_length=32)


@router.post("/api/host/pin")
async def set_pin(body: PinBody, request: Request, response: Response) -> Any:
    access = _access(request)
    scope = request.scope
    if access.pin_set and not is_host(scope, access):
        return error_response(403, "view_only", "Only the host can change the PIN.")
    if not access.pin_set and not on_server_computer(scope):
        return error_response(403, "not_here", "Set the first PIN from the server computer itself.")
    try:
        access.set_pin(body.pin)
    except PinError as exc:
        return error_response(422, "bad_pin", str(exc))
    response.set_cookie(COOKIE, access.token(), max_age=COOKIE_SECONDS, httponly=True, samesite="strict", path="/")  # this device stays the host
    return envelope({**_status(request), "pinSet": True, "isHost": True}, source="live")


@router.post("/api/host/login")
async def login(body: PinBody, request: Request, response: Response) -> Any:
    access = _access(request)
    if not access.pin_set:
        return envelope({**_status(request), "isHost": True}, source="live")
    try:
        good = access.verify(body.pin, _who(request))
    except LockedOut as exc:
        return error_response(429, "locked_out", str(exc))
    if not good:
        return error_response(403, "wrong_pin", "That is not the host PIN.")
    response.set_cookie(COOKIE, access.token(), max_age=COOKIE_SECONDS, httponly=True, samesite="strict", path="/")
    return envelope({**_status(request), "isHost": True}, source="live")


@router.post("/api/host/logout")
async def logout(request: Request, response: Response) -> Any:
    response.delete_cookie(COOKIE, path="/")
    data = _status(request)
    return envelope({**data, "isHost": data["serverComputer"] or not data["pinSet"]}, source="live")


@router.delete("/api/host")
async def clear_pin(request: Request) -> Any:
    access = _access(request)
    if not is_host(request.scope, access):
        return error_response(403, "view_only", "Only the host can remove the PIN.")
    access.clear()
    return envelope(_status(request), source="live")


def _private(ip: str | None) -> bool:
    if not ip:
        return False
    parts = ip.split(".")
    try:
        a, b = int(parts[0]), int(parts[1])
    except (ValueError, IndexError):
        return False
    return a == 10 or (a == 192 and b == 168) or (a == 172 and 16 <= b <= 31) or (a == 169 and b == 254)


@router.get("/api/invite")
async def invite(request: Request) -> Any:
    settings = request.app.state.settings
    ip = lan_ip()
    url = f"{http_url(ip, settings.port)}/" if ip else None
    warnings: list[str] = []
    if ip is None:
        warnings.append("This computer has no network address right now, so no device can join. Connect it to Wi-Fi or a cable.")
    elif not _private(ip):
        warnings.append(f"This computer's address ({ip}) is not a home-network address. It may be on a public network, where other devices usually cannot reach it. Use your own router, a hotspot, or a travel router.")
    elif ip.startswith("192.168.137."):
        warnings.append("This computer is sharing its connection as a hotspot: friends join the hotspot's Wi-Fi, not the venue's.")
    access = _access(request)
    if not access.pin_set:
        warnings.append("No host PIN is set, so everyone who joins can change settings. Set a PIN in Settings to make guests view-only.")
    return envelope(
        {
            "url": url,
            "qrPath": f"/setup/qr.svg?url={url}" if url else None,
            "port": settings.port,
            "pinSet": access.pin_set,
            "warnings": warnings,
            "copyUrl": REPO_URL if REPO_IS_PUBLIC else None,  # "get your own copy" only once the project is public
        },
        source="live",
    )


@router.get("/api/board/screens")
async def board_screens(request: Request) -> Any:
    launcher = request.app.state.board
    return envelope({"screens": screens.list_screens(), "browser": screens.find_browser() is not None, "running": launcher.running, "serverComputer": on_server_computer(request.scope)}, source="live")


class OpenBody(BaseModel):
    screen: int | None = Field(default=None, ge=0, le=16)


@router.post("/api/board/open")
async def board_open(body: OpenBody, request: Request) -> Any:
    if not on_server_computer(request.scope):
        return error_response(403, "not_here", "The board opens on the server computer's own monitors. Open it from that computer.")
    port = request.app.state.settings.port
    result = request.app.state.board.open(f"{http_url('localhost', port)}/#board", body.screen)
    if result.get("error"):
        return error_response(500, "board_failed", result["error"])
    return envelope(result, source="live")


@router.post("/api/board/close")
async def board_close(request: Request) -> Any:
    if not on_server_computer(request.scope):
        return error_response(403, "not_here", "Close the board from the server computer.")
    return envelope({"closed": request.app.state.board.close()}, source="live")
