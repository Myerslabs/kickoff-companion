"""First-run setup in the browser (public release Phase 5a): the /welcome page and its API.

The server starts without a CFBD key or a team (setup mode, Settings.setup_needed) and every page leads
here. The steps:

1. The key. POST /api/welcome/key checks it with one /info call (app/cfbd/client.py try_key) and keeps
   it in memory; the page shows the plan it brings. While no key is configured any device on the home
   network may enter one; replacing a configured key is allowed only from the server computer itself.
   The key is never sent back to a browser.
2. The team. GET /api/welcome/teams lists every FBS school (one /teams/fbs call, cached as reference
   data). The one team picked is the one the Season page, the Game program and the Live sheet follow,
   and its colors and mascot theme the app. Batch 3 (owner 2026-11-19: "I want to take out all the
   secondary teams. The initial idea was to have them so they warm loaded, but now we do that a
   different way. Let's just have one team listed, and a change team for the switch."): no more primary
   teams after it, no secondary teams (schools, conferences, states) and no My teams ticker. Another
   team is seen through Change team in the app, on one device.
3. POST /api/welcome/finish writes CFBD_API_KEY, TEAM and CONFERENCE (the team's, from CFBD) into .env
   (app/services/envfile.py), clears any team picks an older build saved with the settings and sets the
   ticker to every game (prefs.one_team), and restarts the server in place (app/restart.py) when the
   key or the team changed; the page waits for it and opens the app. Old fields in the body
   (primaryTeams, liked, tickerMode) are ignored.

Settings uses the same routes after setup: the team can change from any device, the key only from the
server computer. Every refusal is a readable error envelope.

FEAT-13 (owner 2026-10-26): on a computer that runs the packaged program, a fresh clone first offers to bring over that install's
key, team and data (app/services/public_import.py); POST /api/welcome/import copies them and restarts. Team picks in the
copied settings beyond the one team are dropped (batch 3)."""

from __future__ import annotations

import logging
from pathlib import Path
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
from app.services import plan, public_import
from app.services.envfile import EnvFileError, set_values
from app.services.prefs import PrefsError, PrefsStore, one_team
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
        "plan": plan.summary(client) if (configured or _pending(request)) else None,
        "envWritable": settings.env_path is not None,
        "publicInstall": public_import.summary(_other_install(settings)) if settings.setup_needed and settings.env_path is not None else None,
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
        return error_response(422, "key_refused", _refused_message(status, error))
    if payload is None:
        return error_response(502, "cfbd_error", f"CFBD answered the check oddly ({error}). Try again in a minute.")
    client._apply_info(payload, client._clock())  # the plan and the quota guard both learn the key's limit
    caps = client.capabilities  # the numbers, never the key (tester 2026-10-19: the log had nothing to say about a key "out of calls")
    log.info(
        "A new CFBD key checked: %s, %s of %s calls left this month, resets %s",
        caps.tier_name or "tier unknown", "?" if caps.remaining_calls is None else f"{caps.remaining_calls:,}", "?" if caps.monthly_limit is None else f"{caps.monthly_limit:,}", caps.reset_at or "?",
    )
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


BARE_REFUSALS = {"unauthorized", "forbidden"}


def _refused_message(status: int, reason: str | None) -> str:
    """What the page says when CFBD answers 401 or 403. A bare "Unauthorized" means CFBD does not
    know the key, so the advice is to copy it again. Anything else is CFBD's own reason (owner
    2026-10-13: "Account has been blacklisted." was hidden behind the generic line) and is shown as
    it is, since the fix is on CFBD's side, not in the paste."""
    reason = " ".join((reason or "").split())
    if not reason or reason.rstrip(".").lower() in BARE_REFUSALS or reason.lower() == f"http {status}":
        return "CFBD did not accept this key. Copy it again from the email CFBD sent, or get a new one."
    return f'CFBD did not accept this key and says: "{reason}" That is about the account the key belongs to, so ask CFBD about it, or use another key.'


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
    return envelope({"teams": rows}, source="live")  # the conference and state lists went with the secondary pickers (batch 3)


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
    # Batch 3 (owner 2026-11-19): one team. A page opened before the change may still send primaryTeams, liked and
    # tickerMode; they are ignored, and the save clears whatever an older build kept.
    ignored = sorted(k for k in ("primaryTeams", "liked", "tickerMode") if k in body)
    if ignored:
        log.info("Setup: ignored the retired field(s) %s; the app follows one team", ", ".join(ignored))
    patch = one_team()
    if settings.env_path is None:
        return error_response(409, "env_read_only", "This server reads its settings from environment variables; set TEAM and CONFERENCE there.")
    values = {"TEAM": chosen.school, "CONFERENCE": chosen.conference}
    pending = _pending(request)
    if pending:
        values["CFBD_API_KEY"] = pending
    changed = settings.setup_needed or chosen.school != settings.team or chosen.conference != settings.conference or bool(pending)
    try:
        if patch:
            prefs.update(patch)
        if changed:
            set_values(settings.env_path, values)
    except PrefsError as exc:
        return error_response(500, "settings_write_failed", f"Could not save the setup: {exc}.")
    except EnvFileError as exc:
        return error_response(500, "env_write_failed", f"Could not save the setup: {exc}.")
    if changed:
        request.app.state.pending_key = None
        restart.request(f"setup saved for {chosen.school}")
    log.info("Setup saved: %s (%s), one team, the national ticker", chosen.school, chosen.conference)
    return envelope({**_state(request), "restarting": changed, "team": chosen.school, "conference": chosen.conference}, source="live")


def _other_install(settings: Settings) -> Any:
    """The packaged program's folder when it is another install than this one (2.0: the packaged program keeps its own
    files there, so it never offers to bring itself over)."""
    source = public_import.find_public()
    if source is None or settings.env_path is None:
        return None
    try:
        if source.resolve() == Path(settings.env_path).resolve().parent:
            return None
    except OSError:
        return None
    return source


@router.post("/api/welcome/import")
async def bring_over(request: Request) -> Any:
    """FEAT-13: copy the packaged install's key, team and data into this project, once, while setup is still needed."""
    settings: Settings = request.app.state.settings
    if not settings.setup_needed:
        return error_response(409, "set_up", "This server is set up already; nothing is brought over now.")
    if settings.env_path is None:
        return error_response(409, "env_read_only", "This server reads its settings from environment variables.")
    source = _other_install(settings)
    if source is None:
        return error_response(404, "no_public_install", "No other Kickoff Companion install was found on this computer.")
    try:
        result = public_import.copy_into(source, settings.env_path, settings.data_dir)
    except (OSError, ValueError, EnvFileError) as exc:
        log.warning("Bringing over the other install failed: %s", exc)
        return error_response(500, "import_failed", f"Could not bring it over: {exc}.")
    restart.request("brought over the other install")
    return envelope({**result, "restarting": True}, source="live")
