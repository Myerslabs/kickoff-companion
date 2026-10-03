"""First-run setup in the browser (public release Phase 5a): the /welcome page and its API.

The server starts without a CFBD key or a team (setup mode, Settings.setup_needed) and every page leads
here. The steps:

1. The key. POST /api/welcome/key checks it with one /info call (app/cfbd/client.py try_key) and keeps
   it in memory; the page shows the plan it brings. While no key is configured any device on the home
   network may enter one; replacing a configured key is allowed only from the server computer itself.
   The key is never sent back to a browser.
2. The teams. GET /api/welcome/teams lists every FBS school (one /teams/fbs call, cached as reference
   data), with the conferences and states for the secondary pickers. The home team (primary #1) is the
   one the Season page, the Game program and the Live sheet follow, and the only one whose colors and
   mascot theme the app. Up to four more primary teams, the secondary teams (schools, conferences,
   states) and the My teams ticker need a Tier 2 key (public release Phase 5b; app/services/teamset.py).
3. POST /api/welcome/finish writes CFBD_API_KEY, TEAM and CONFERENCE (the home team's, from CFBD) into
   .env (app/services/envfile.py), saves the other picks with the settings, and restarts the server in
   place (app/restart.py) when the key or the home team changed; the page waits for it and opens the app.

Settings uses the same routes after setup: the team can change from any device, the key only from the
server computer. Every refusal is a readable error envelope."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse

from app import restart
from app.api.envelope import envelope, error_response
from app.cache import DataKind
from app.cfbd.client import CfbdError
from app.cfbd.models import Team, parse_records
from app.cfbd.quota import QuotaBlocked
from app.config import STATIC_DIR, Settings
from app.netinfo import lan_ip
from app.services import plan
from app.services.envfile import EnvFileError, set_values
from app.services.prefs import MAX_EXTRA_PRIMARIES, PrefsError, PrefsStore
from app.services.teamset import state_of

router = APIRouter(tags=["welcome"])
log = logging.getLogger("kickoff.welcome")

MAX_KEY = 200


def on_server_computer(request: Request) -> bool:
    """The request comes from the server computer itself: its loopback or its own LAN address."""
    host = request.client.host if request.client else ""
    return host in ("127.0.0.1", "::1", "localhost") or (bool(host) and host == lan_ip())


def _pending(request: Request) -> str | None:
    return getattr(request.app.state, "pending_key", None)


def _has_key(request: Request) -> bool:
    return request.app.state.settings.api_key_configured or bool(_pending(request))


def _state(request: Request) -> dict[str, Any]:
    settings: Settings = request.app.state.settings
    prefs: PrefsStore = request.app.state.prefs
    client = request.app.state.cfbd
    configured = settings.api_key_configured
    return {
        "setupNeeded": settings.setup_needed,
        "keyConfigured": configured,
        "keyChecked": bool(_pending(request)),
        "canSetKey": (not configured) or on_server_computer(request),
        "team": settings.team or None,
        "conference": settings.conference or None,
        "season": settings.season,
        "primaryTeams": prefs.prefs.primaryTeams,
        "maxPrimaryTeams": MAX_EXTRA_PRIMARIES,
        "liked": {"teams": prefs.prefs.likedTeams, "conferences": prefs.prefs.likedConferences, "states": prefs.prefs.likedStates},
        "tickerMode": prefs.prefs.tickerMode,
        "plan": plan.summary(client) if (configured or _pending(request)) else None,
        "envWritable": settings.env_path is not None,
    }


@router.get("/welcome", include_in_schema=False)
async def welcome_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "welcome.html", media_type="text/html", headers={"Cache-Control": "no-cache"})


@router.get("/api/welcome")
async def welcome_state(request: Request) -> Any:
    return envelope(_state(request), source="live")


@router.post("/api/welcome/key")
async def check_key(request: Request) -> Any:
    settings: Settings = request.app.state.settings
    if settings.api_key_configured and not on_server_computer(request):
        return error_response(403, "server_computer_only", "A key is already set. Change it on the server computer itself, so nobody else on the network can swap it.")
    try:
        body = await request.json()
    except ValueError:
        return error_response(400, "bad_json", "The request must be JSON with a key.")
    key = body.get("key") if isinstance(body, dict) else None
    key = key.strip().strip('"').strip("'") if isinstance(key, str) else ""
    if not key:
        return error_response(422, "bad_key", f"Paste your CFBD key. Get one free at {plan.KEY_URL}.")
    if len(key) > MAX_KEY or any(ch.isspace() for ch in key) or len(key) < 16:
        return error_response(422, "bad_key", "That does not look like a CFBD key: paste the whole key, with no spaces or line breaks.")
    client = request.app.state.cfbd
    status, payload, error = await client.try_key(key)
    if status is None:
        return error_response(503, "cfbd_unreachable", f"Could not reach CFBD to check the key ({error}). Check the internet connection and try again.")
    if status in (401, 403):
        return error_response(422, "key_refused", "CFBD did not accept this key. Copy it again from the email CFBD sent, or get a new one.")
    if payload is None:
        return error_response(502, "cfbd_error", f"CFBD answered the check oddly ({error}). Try again in a minute.")
    client._apply_info(payload, client._clock())  # the plan and the quota guard both learn the key's limit
    if settings.setup_needed or not settings.api_key_configured:
        request.app.state.pending_key = key
        client.use_key(key)  # setup mode: the team list comes with this key
        return envelope(_state(request), source="live")
    # Settings: a new key for a running install goes straight into .env, then the server restarts.
    if settings.env_path is None:
        return error_response(409, "env_read_only", "This server reads its settings from environment variables; set CFBD_API_KEY there.")
    try:
        set_values(settings.env_path, {"CFBD_API_KEY": key})
    except EnvFileError as exc:
        return error_response(500, "env_write_failed", f"The key is fine, but {exc}.")
    restart.request("a new CFBD key was saved")
    return envelope({**_state(request), "restarting": True}, source="live")


async def _teams(request: Request) -> tuple[list[Team], str | None]:
    settings: Settings = request.app.state.settings
    try:
        fetched = await request.app.state.cfbd.get("/teams/fbs", {"year": settings.season}, kind=DataKind.TEAMS)
    except (QuotaBlocked, CfbdError) as exc:
        return [], str(exc)
    return parse_records(Team, fetched.payload, context="welcome /teams/fbs").records, None


@router.get("/api/welcome/teams")
async def team_list(request: Request) -> Any:
    if not _has_key(request):
        return error_response(409, "key_needed", "Check a CFBD key first; the team list comes from CFBD.")
    teams, error = await _teams(request)
    if not teams:
        return error_response(503, "teams_unavailable", f"The team list did not load ({error or 'empty answer'}). Try again in a minute.")
    rows = sorted(
        (
            {"school": t.school, "mascot": t.mascot, "conference": t.conference, "abbreviation": t.abbreviation,
             "color": t.color, "altColor": t.alternate_color, "state": state_of(t)}
            for t in teams if isinstance(t.school, str) and t.school.strip()
        ),
        key=lambda r: r["school"].lower(),
    )
    conferences = sorted({r["conference"] for r in rows if isinstance(r["conference"], str) and r["conference"]})
    states = sorted({r["state"] for r in rows if r["state"]})
    return envelope({"teams": rows, "conferences": conferences, "states": states}, source="live")


@router.post("/api/welcome/finish")
async def finish(request: Request) -> Any:
    settings: Settings = request.app.state.settings
    prefs: PrefsStore = request.app.state.prefs
    if not _has_key(request):
        return error_response(409, "key_needed", "Check a CFBD key first.")
    try:
        body = await request.json()
    except ValueError:
        return error_response(400, "bad_json", "The request must be JSON.")
    if not isinstance(body, dict):
        return error_response(400, "bad_json", "The request must be a JSON object.")
    teams, error = await _teams(request)
    if not teams:
        return error_response(503, "teams_unavailable", f"The team list did not load ({error or 'empty answer'}). Try again in a minute.")
    by_name = {t.school.lower(): t for t in teams if isinstance(t.school, str)}
    chosen = by_name.get(str(body.get("team") or "").strip().lower())
    if chosen is None or not chosen.conference:
        return error_response(422, "bad_team", "Pick your team from the list.")
    liked = body.get("liked") if isinstance(body.get("liked"), dict) else {}
    strings = lambda values: [v for v in (values if isinstance(values, list) else []) if isinstance(v, str)]  # noqa: E731
    patch: dict[str, Any] = {
        "primaryTeams": strings(body.get("primaryTeams")),
        "likedTeams": strings(liked.get("teams")),
        "likedConferences": strings(liked.get("conferences")),
        "likedStates": strings(liked.get("states")),
    }
    ticker_mode = body.get("tickerMode", "national")
    if ticker_mode not in ("national", "mine"):
        return error_response(422, "bad_ticker", "The ticker is either every game (national) or my teams (mine).")
    tier2 = plan.allows_liked(request.app.state.cfbd.capabilities)
    if (any(patch.values()) or ticker_mode == "mine") and not tier2:
        return error_response(422, "tier2_needed", "More primary teams, secondary teams and the My teams ticker need a Tier 2 key. Pick just your home team for now.")
    unknown = [t for t in patch["primaryTeams"] + patch["likedTeams"] if t.strip().lower() not in by_name]
    if unknown:
        return error_response(422, "bad_liked", f"Not FBS schools in CFBD's list: {', '.join(unknown[:5])}.")
    primaries: list[str] = []
    for name in patch["primaryTeams"]:
        school = by_name[name.strip().lower()].school
        if school != chosen.school and school not in primaries:
            primaries.append(school)
    if len(primaries) > MAX_EXTRA_PRIMARIES:
        return error_response(422, "too_many_primaries", f"Up to {MAX_EXTRA_PRIMARIES} more primary teams besides your home team. Make the rest secondary teams.")
    patch["primaryTeams"] = primaries
    patch["likedTeams"] = [s for s in (by_name[t.strip().lower()].school for t in patch["likedTeams"]) if s != chosen.school and s not in primaries]
    patch["tickerMode"] = ticker_mode
    if settings.env_path is None:
        return error_response(409, "env_read_only", "This server reads its settings from environment variables; set TEAM and CONFERENCE there.")
    values = {"TEAM": chosen.school, "CONFERENCE": chosen.conference}
    pending = _pending(request)
    if pending:
        values["CFBD_API_KEY"] = pending
    changed = settings.setup_needed or chosen.school != settings.team or chosen.conference != settings.conference or bool(pending)
    try:
        prefs.update(patch)
        if changed:
            set_values(settings.env_path, values)
    except PrefsError as exc:
        return error_response(422, "bad_liked", str(exc))
    except EnvFileError as exc:
        return error_response(500, "env_write_failed", f"Could not save the setup: {exc}.")
    if changed:
        request.app.state.pending_key = None
        restart.request(f"setup saved for {chosen.school}")
    log.info("Setup saved: %s (%s), %d more primary teams, %d secondary schools, %d conferences, %d states, %s ticker", chosen.school, chosen.conference,
             len(patch["primaryTeams"]), len(patch["likedTeams"]), len(patch["likedConferences"]), len(patch["likedStates"]), patch["tickerMode"])
    return envelope({**_state(request), "restarting": changed, "team": chosen.school, "conference": chosen.conference}, source="live")
