"""GET and PUT /api/settings (X6): the owner's options, the quota readout, and the start-at-login
switch. Secrets never appear here."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from fastapi import APIRouter, Request

from app import APP_NAME, DATA_CREDIT, DATA_URL, PUBLISHER, REPO_URL, __version__
from app.api.envelope import envelope, error_response
from app.api.radio import all_sources, radio_help
from app.config import PROJECT_ROOT
from app.paths import ROOTS
from app.services import plan, stations, teamset
from app.services.launcher import Launcher, open_folder
from app.services.notes_task import NotesRunner
from app.services.prefs import PrefsError, PrefsStore

router = APIRouter(tags=["settings"])


def _on_server_computer(request: Request) -> bool:
    from app.api.welcome import on_server_computer

    return on_server_computer(request)


def _same_origin(request: Request) -> bool:
    """False when another site's page sent the request (its Origin names another host), so a page open in the server
    computer's browser cannot reach a route that acts on that computer. No Origin (curl, a test) is allowed."""
    origin = request.headers.get("origin")
    if origin is None:
        return True
    return urlsplit(origin).netloc.lower() == request.headers.get("host", "").lower()


def _payload(request: Request) -> dict[str, Any]:
    settings = request.app.state.settings
    prefs: PrefsStore = request.app.state.prefs
    launcher: Launcher = request.app.state.launcher
    notes: NotesRunner = request.app.state.notes
    cfbd = request.app.state.cfbd.status()
    quota = cfbd["quota"]
    sources = all_sources(request)
    return {
        "prefs": prefs.as_dict(),
        "prefsError": prefs.error,
        "radioSources": [{"id": s["id"], "name": s["name"], "kind": s["kind"], "team": s["team"], "origin": s["origin"]} for s in sources],  # the same ids the player saves
        "radioHelp": radio_help(request, sources),  # public release Phase 5b: find or request a team's station
        "radioRequestUrl": stations.request_url(None),
        "teamSet": teamset.current(settings, prefs, request.app.state.cfbd).as_dict(),  # primaries for the menu (Phase 5b)
        "quota": {
            "used": quota.get("used"),
            "remaining": quota.get("remaining"),
            "budget": quota.get("budget"),
            "pctUsed": quota.get("pct_used"),
            "mode": quota.get("mode"),
            "reason": quota.get("reason"),
            "resetAt": quota.get("reset_at"),
            "tierName": quota.get("tier_name"),
            "reconciledAt": quota.get("reconciled_at"),
        },
        "capabilities": cfbd["capabilities"],
        "server": {"team": settings.team, "season": settings.season, "conference": settings.conference, "timezone": settings.timezone, "port": settings.port, "livePollSeconds": settings.live_poll_seconds, "dataDir": str(settings.data_dir), "logDir": str(settings.log_dir)},
        "autoStart": launcher.status(),
        "plan": plan.summary(request.app.state.cfbd),  # public release Phase 5a
        "canChangeKey": _on_server_computer(request),
        "notes": notes.status(prefs.prefs.notesCommand),
        "files": {**ROOTS.describe(), "envFile": str(settings.env_file_used) if settings.env_file_used else None, "dataDir": str(settings.data_dir), "logDir": str(settings.log_dir)},  # public release Phase 10: where this install keeps its files
        "about": {"name": APP_NAME, "version": __version__, "publisher": PUBLISHER, "repoUrl": REPO_URL, "dataCredit": DATA_CREDIT, "dataUrl": DATA_URL},  # public release Phase 8
    }


TIER2_LISTS = ("primaryTeams", "likedTeams", "likedConferences", "likedStates")


def _tier2_refusal(request: Request, patch: Any) -> str | None:
    """Primary teams beyond the home team, secondary teams and the My teams ticker need a Tier 2 key
    (public release Phase 5b). Clearing them is always allowed."""
    if not isinstance(patch, dict) or plan.allows_liked(request.app.state.cfbd.capabilities):
        return None
    if patch.get("tickerMode") == "mine":
        return "The My teams ticker needs a Tier 2 key. The national ticker shows every game."
    if any(isinstance(patch.get(k), list) and patch.get(k) for k in TIER2_LISTS):
        return "More primary teams and secondary teams need a Tier 2 key."
    return None


@router.get("/api/settings")
async def get_settings(request: Request) -> Any:
    return envelope(_payload(request), source="live")


@router.put("/api/settings")
async def put_settings(request: Request) -> Any:
    prefs: PrefsStore = request.app.state.prefs
    launcher: Launcher = request.app.state.launcher
    try:
        patch = await request.json()
    except ValueError:
        return error_response(400, "bad_json", "The settings body must be JSON.")
    refused = _tier2_refusal(request, patch)
    if refused:
        return error_response(422, "tier2_needed", refused)
    try:
        before = prefs.as_dict()
        prefs.update(patch)
    except PrefsError as exc:
        return error_response(422, "bad_setting", str(exc))
    errors: list[dict[str, str]] = []
    after = prefs.as_dict()
    if after["autoStart"] != before["autoStart"] or (after["autoStart"] and after["trayMode"] != before["trayMode"]):
        result = launcher.set_enabled(after["autoStart"], tray=after["trayMode"])
        if result.get("error"):
            errors.append({"code": "autostart_failed", "message": result["error"]})
    return envelope(_payload(request), source="live", errors=errors)


@router.post("/api/settings/open-folder")
async def open_folder_route(request: Request) -> Any:
    """Show this install's folder in the file manager (public release Phase 10). Only from the server computer itself,
    where the window opens, and only from this app's own pages."""
    if not _on_server_computer(request):
        return error_response(403, "not_here", "Open the folder from the server computer itself; this device cannot open a window there.")
    if not _same_origin(request):
        return error_response(403, "cross_site", "Another site's page cannot open folders on this computer.")
    error = open_folder(PROJECT_ROOT)
    if error:
        return error_response(500, "open_failed", error)
    return envelope({"opened": str(PROJECT_ROOT)}, source="live")


@router.post("/api/settings/desktop-shortcut")
async def desktop_shortcut(request: Request) -> Any:
    prefs: PrefsStore = request.app.state.prefs
    launcher: Launcher = request.app.state.launcher
    result = launcher.desktop_shortcut(tray=prefs.prefs.trayMode)
    if result.get("error"):
        return error_response(500, "shortcut_failed", result["error"])
    return envelope(result, source="live")
