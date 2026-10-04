"""FastAPI app factory. Mounts the API routes, serves the static front end, and sends
plain-HTTP requests to HTTPS."""

from __future__ import annotations

import asyncio
import logging
import mimetypes
import sys
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import URL, MutableHeaders
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Receive, Scope, Send

from app import APP_NAME, BUILD_PHASE, __version__, restart
from app import shutdown as shutdown_signal
from app.api import analytics, archive, client_log, grades, health, identity, live, media, myteams, national, notes, players, program, radio, ratings, season, setup, ticker, welcome
from app.api import demo as demo_api
from app.api import matchup as matchup_api  # Phase 16 BX
from app.api import search as search_api
from app.api import settings as settings_api
from app.api.envelope import error_response
from app.api.health import format_duration
from app.cfbd.client import CfbdClient
from app.config import PROJECT_ROOT, STATIC_DIR, Settings, SettingsError, load_settings
from app.db import Database, database_path
from app.feeds import FeedStore, team_feeds, team_matcher
from app.live.engine import LiveEngine
from app.logging_setup import LOG_FILE_NAME, configure_logging
from app.netinfo import http_url, lan_ip, other_urls, preferred_host, tablet_url
from app.services.analytics import AnalyticsService
from app.services.archive import ArchiveService
from app.services.connect import print_qr
from app.services.grades import GradeService
from app.services.identity import IdentityService
from app.services.launcher import Launcher
from app.services.logos import LogoStore
from app.services.matchup import MatchupService  # Phase 16 BX
from app.services.mdns import Announcer
from app.services.media import HeadshotStore
from app.services.myteams import MyTeamsService
from app.services.national import NationalService
from app.services.notes_task import NotesRunner
from app.services.players import PlayerService
from app.services.prefs import PrefsStore
from app.services.program import ProgramService
from app.services.ratings import RatingsService
from app.services.search import SearchService
from app.services.season import SeasonService
from app.services.ticker import TickerService
from app.tls import TlsState
from app.weather import NwsClient

CERT_RECHECK_SECONDS = 6 * 3600
QUOTA_CHECK_SECONDS = 5 * 60
PREWARM_SECONDS = 10 * 60  # Phase 14: how often the server looks for published data to refresh
STARTUP_QUOTA_TIMEOUT = 60
log = logging.getLogger("kickoff.main")

_HTTP_CODES = {400: "bad_request", 404: "not_found", 405: "method_not_allowed", 422: "invalid_request"}

# Windows can map these extensions to odd types in the registry. Module scripts and fonts
# refuse to load with the wrong type, so pin them here.
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("image/svg+xml", ".svg")
mimetypes.add_type("application/manifest+json", ".webmanifest")
mimetypes.add_type("video/mp4", ".mp4")  # the keep-awake clip (Phase 4b, static/js/awake.js)
mimetypes.add_type("video/webm", ".webm")  # the home-screen install (Phase 12)


def allowed_over_plain_http(path: str) -> bool:
    """Paths a device needs before it trusts the certificate authority (HTTPS on), the QR code among them."""
    return path == "/setup" or path.startswith("/setup/") or path == "/api/setup" or path.startswith("/static/")


class PlainHttpRedirect:
    """With HTTPS on: plain-HTTP requests go to HTTPS, except the pages a device needs before it
    trusts the CA. With HTTPS off (the default since public release Phase 4b): an https:// request,
    which only arrives on an install that kept its old certificates, goes to the same page over HTTP,
    so a home-screen icon saved before the change still opens the app."""

    def __init__(self, app: ASGIApp, https: bool = True, legacy_tls: bool = False) -> None:
        self.app = app
        self.https = https
        self.legacy_tls = legacy_tls  # HTTPS off, old certificates kept: answer https:// links with a redirect

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            scheme = scope.get("scheme")
            if self.https and scheme == "http" and not allowed_over_plain_http(scope.get("path", "")):
                target = URL(scope=scope).replace(scheme="https")
                await RedirectResponse(str(target), status_code=302)(scope, receive, send)
                return
            if not self.https and self.legacy_tls and scheme == "https":
                target = URL(scope=scope).replace(scheme="http")
                await RedirectResponse(str(target), status_code=301)(scope, receive, send)
                return
        await self.app(scope, receive, send)


SETUP_OPEN = ("/welcome", "/api/welcome", "/demo", "/api/demo", "/static/", "/setup", "/api/setup", "/api/health", "/status", "/manifest.webmanifest", "/icons/", "/api/identity", "/favicon")


def setup_open(path: str) -> bool:
    """Whether a path answers in setup mode: a listed path itself, or anything under it."""
    return any(path.startswith(p) if p.endswith("/") or p == "/favicon" else path == p or path.startswith(p + "/") for p in SETUP_OPEN)


class SetupGate:
    """Setup mode (public release Phase 5a: no CFBD key or team yet): every page leads to /welcome, and
    the data API answers 503 setup_needed instead of calling CFBD with no key. The welcome page, the
    connect page, the status page and the static files stay open."""

    def __init__(self, app: ASGIApp, active: bool = False) -> None:
        self.app = app
        self.active = active

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if self.active and scope["type"] in ("http", "websocket"):
            path = scope.get("path", "")
            if not setup_open(path):
                if path.startswith("/api/"):
                    response = error_response(503, "setup_needed", "Finish setup first: open /welcome in a browser.")
                else:
                    response = RedirectResponse("/welcome", status_code=302)
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


class StaticCacheHeaders:
    """Static files revalidate on every load (cheap with ETags) so a device never runs a stale
    script after an update. Fonts never change and cache for a year."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "") if scope["type"] == "http" else ""
        if not path.startswith("/static/"):
            await self.app(scope, receive, send)
            return
        value = "public, max-age=31536000, immutable" if path.startswith("/static/fonts/") else "no-cache"

        async def send_with_cache_header(message):
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)["cache-control"] = value
            await send(message)

        await self.app(scope, receive, send_with_cache_header)


async def _recheck_certificates(app: FastAPI) -> None:
    """Re-issue the server certificate before it expires, even if the server runs for months."""
    while True:
        await asyncio.sleep(CERT_RECHECK_SECONDS)
        try:
            app.state.tls.refresh(app.state.settings)
        except Exception:  # noqa: BLE001 - the loop must survive; the failure is logged
            log.exception("Certificate check failed. Will try again in %d hours.", CERT_RECHECK_SECONDS // 3600)


async def _watch_quota(app: FastAPI) -> None:
    """Let the client reconcile with CFBD on its adaptive schedule."""
    while True:
        await asyncio.sleep(QUOTA_CHECK_SECONDS)
        try:
            await app.state.cfbd.maybe_reconcile()
        except Exception:  # noqa: BLE001 - the loop must survive; the failure is logged
            log.exception("Quota check failed. Will try again in %d minutes.", QUOTA_CHECK_SECONDS // 60)


async def _prewarm_published(app: FastAPI) -> None:
    """Phase 14: refresh the polls and weekly ratings soon after they are published, so a page opened
    later makes no call. The client decides which keys (app/cfbd/publish.py)."""
    while True:
        await asyncio.sleep(PREWARM_SECONDS)
        try:
            await app.state.cfbd.prewarm()
        except Exception:  # noqa: BLE001 - the loop must survive; the failure is logged
            log.exception("Prewarm of published data failed. Will try again in %d minutes.", PREWARM_SECONDS // 60)


def _describe_key(cfbd: CfbdClient) -> str:
    caps = cfbd.capabilities
    quota = cfbd.quota.status(datetime.now(timezone.utc))
    if not quota.reconciled:
        return f"CFBD key not checked yet; assuming a budget of {quota.budget:,} calls. {quota.reason}"
    features = ", ".join(
        f"{name} {'on' if value else 'off' if value is False else 'unknown'}"
        for name, value in (("weather", caps.weather), ("scoreboard", caps.scoreboard), ("live plays", caps.live_plays))
    )
    reset = f", resets {caps.reset_at[:10]}" if caps.reset_at else ""
    return (
        f"CFBD key: {caps.tier_name or 'unknown tier'}, {quota.remaining:,} of {quota.budget:,} calls left{reset}."
        f" Features: {features}. Cache lifetimes x{cfbd.ttl_scale(quota)}."
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = app.state.settings
    tls: TlsState | None = app.state.tls
    cfbd: CfbdClient = app.state.cfbd
    app.state.started_at = datetime.now(timezone.utc)
    ip = lan_ip()
    host = preferred_host(settings, ip)
    log.info("%s %s starting (phase %d)", APP_NAME, __version__, BUILD_PHASE)
    log.info(
        "Team %s, season %s, %s. Times shown in %s.",
        settings.team, settings.season, settings.conference, settings.timezone,
    )
    log.info("Tablet URL: %s", tablet_url(settings, ip))
    for url in other_urls(settings, ip):
        log.info("Also reachable at %s", url)
    if settings.setup_needed:
        welcome = f"{tablet_url(settings, ip)}/welcome"
        log.info("Setup needed: open %s (or http://localhost:%s/welcome on this computer) to add a CFBD key and pick a team.", welcome, settings.port)
        print_qr(welcome)
        mdns: Announcer = app.state.mdns
        mdns.start()  # so a phone can finish the setup at kickoff.local
        try:
            yield {"tls": tls, "https": settings.https}
        finally:
            await mdns.stop()
            await cfbd.aclose()
            await app.state.headshots.aclose()
            await app.state.logos.aclose()
            await app.state.feeds.aclose()
            await app.state.weather.aclose()
            app.state.db.close()
            log.info("%s stopped (setup mode)", APP_NAME)
        return
    if settings.https and tls is not None:
        log.info(
            "HTTPS certificate covers %s, valid until %s", ", ".join(tls.server.names), tls.server.not_after.date()
        )
        log.info("Certificate authority fingerprint (SHA-256): %s", tls.ca.fingerprint_sha256)
        log.info("New device? Open %s/setup on it first.", http_url(host, settings.port))
    else:
        log.info("Plain HTTP on the home network: a phone or tablet opens the address above, nothing to install.")
        if tls is not None:
            log.info("Old https:// addresses still answer and are sent to http:// (certificates kept in %s).", tls.cert_dir)
        print_qr(f"{tablet_url(settings, ip)}/")
    log.info("Log file: %s (%s)", settings.log_dir / LOG_FILE_NAME, settings.log_level)

    try:
        await asyncio.wait_for(cfbd.reconcile(), timeout=STARTUP_QUOTA_TIMEOUT)
    except Exception:  # noqa: BLE001 - startup must not die on a quota check; health will show it
        log.exception("CFBD quota check at startup failed")
    log.info("%s", _describe_key(cfbd))
    try:
        found = await asyncio.wait_for(app.state.identity.load(), timeout=STARTUP_QUOTA_TIMEOUT)
        log.info("Following %s%s (%s)", found.school, f" {found.mascot}" if found.mascot else "", found.conference or "conference unknown")
    except Exception:  # noqa: BLE001 - the fallback identity keeps every page working; health shows the rest
        log.exception("Team identity at startup failed; using TEAM as written")

    mdns: Announcer = app.state.mdns
    mdns.title = app.state.identity.current.title  # "Mudpuppies Kickoff Companion" in a network browser
    mdns.start()
    recheck = asyncio.create_task(_recheck_certificates(app)) if tls is not None else None
    quota_watch = asyncio.create_task(_watch_quota(app))
    prewarm = asyncio.create_task(_prewarm_published(app))
    app.state.live.start_background()
    log.info("Live engine watching the schedule; polls every %d s inside a game window while a client is connected", settings.live_poll_seconds)
    try:
        yield {"tls": tls, "https": settings.https}
    finally:
        await app.state.live.stop_background()
        await app.state.notes.stop()
        await app.state.mdns.stop()
        await app.state.myteams.close()
        for task in (recheck, quota_watch, prewarm):
            if task is None:
                continue
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        await cfbd.aclose()
        await app.state.headshots.aclose()
        await app.state.logos.aclose()
        await app.state.feeds.aclose()
        await app.state.weather.aclose()
        app.state.db.close()
        uptime = (datetime.now(timezone.utc) - app.state.started_at).total_seconds()
        log.info("%s stopped after %s", APP_NAME, format_duration(uptime))


def create_app(
    settings: Settings | None = None,
    tls: TlsState | None = None,
    cfbd_transport: httpx.AsyncBaseTransport | None = None,
    media_transport: httpx.AsyncBaseTransport | None = None,
    feeds_transport: httpx.AsyncBaseTransport | None = None,
    weather_transport: httpx.AsyncBaseTransport | None = None,
    logo_transport: httpx.AsyncBaseTransport | None = None,
) -> FastAPI:
    """Build the app. With no settings, loads and validates .env; a bad .env exits with a message.

    cfbd_transport and media_transport let tests script the upstreams; the real app leaves them None.
    logo_transport scripts CFBD's logo CDN (defaults to media_transport).
    """
    if settings is None:
        try:
            settings = load_settings()
        except SettingsError as exc:
            print(str(exc), file=sys.stderr)
            raise SystemExit(2) from None
    configure_logging(settings)

    if tls is None and settings.https:
        try:
            tls = TlsState.prepare(settings)
        except OSError as exc:
            message = (
                f"{APP_NAME} cannot start. Could not create the HTTPS certificates in "
                f"{settings.data_dir / 'certs'}: {exc.strerror or exc}"
            )
            log.error(message)
            print(message, file=sys.stderr)
            raise SystemExit(2) from None
    elif tls is None:
        try:
            tls = TlsState.existing(settings)  # an install that had HTTPS on keeps answering its old https:// links
        except (OSError, ValueError) as exc:
            log.warning("The old HTTPS certificates could not be loaded (%s); https:// links will not answer.", exc)
            tls = None

    db = Database(database_path(settings.data_dir))
    cfbd = CfbdClient(settings, db, transport=cfbd_transport)

    app = FastAPI(
        title=APP_NAME, version=__version__, lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None
    )
    app.state.settings = settings
    app.state.tls = tls
    app.state.db = db
    app.state.cfbd = cfbd
    app.state.season = SeasonService(cfbd, settings)
    app.state.players = PlayerService(cfbd, settings)
    agent = f"{APP_NAME.replace(' ', '')}/{__version__} (personal second screen)"
    app.state.feeds = FeedStore(settings.data_dir, transport=feeds_transport, user_agent=agent, clock=lambda: cfbd._clock())
    app.state.identity = IdentityService(cfbd, settings)
    app.state.identity.on_change(lambda who: app.state.feeds.configure(team_feeds(who.school, who.mascot, settings.team_feed_url or None), team_matcher(who.school, who.mascot, who.rivals)))
    app.state.weather = NwsClient(settings.data_dir, transport=weather_transport, user_agent=agent, clock=lambda: cfbd._clock())
    app.state.program = ProgramService(cfbd, settings, app.state.feeds, app.state.weather)
    app.state.live = LiveEngine(cfbd, settings, db)
    shutdown_signal.reset()
    restart.reset()
    shutdown_signal.on_begin(app.state.live.wake_streams)
    app.state.prefs = PrefsStore(settings.data_dir)
    app.state.ticker = TickerService(cfbd, settings, app.state.live, app.state.prefs)  # public release Phase 5b: the ticker mode
    app.state.analytics = AnalyticsService(cfbd, settings)
    app.state.ratings = RatingsService(cfbd, settings)
    app.state.national = NationalService(cfbd, settings, app.state.season.fetcher, app.state.players.fetcher, app.state.ratings.fetcher, app.state.prefs)  # Phase 16: zero-call national lists; Phase 5b: My teams scope
    app.state.search = SearchService(cfbd, settings)  # Phase 15
    app.state.grades = GradeService(cfbd, settings, app.state.players.fetcher)  # public release Phase 7: stat grades on the Leaders keys
    app.state.myteams = MyTeamsService(cfbd, settings, app.state.prefs, app.state.program, app.state.ratings.fetcher)  # public release Phase 5b
    app.state.matchup = MatchupService(cfbd, settings)  # Phase 16 BX: UX-12
    app.state.archive = ArchiveService(settings.data_dir, app.state.analytics, app.state.program, settings.team)
    app.state.launcher = Launcher(PROJECT_ROOT)
    app.state.mdns = Announcer(settings.mdns_host, settings.port)  # public release Phase 4: kickoff.local
    app.state.notes = NotesRunner(settings.data_dir, settings.log_dir, who=lambda: app.state.identity.current, season=settings.season, tz=settings.tzinfo)
    app.state.headshots = HeadshotStore(settings.data_dir, transport=media_transport, user_agent=f"{APP_NAME.replace(' ', '')}/{__version__} (personal second screen)")
    app.state.logos = LogoStore(settings.data_dir, transport=logo_transport or media_transport, user_agent=agent)  # Phase 16: logos served from our own route
    app.state.started_at = datetime.now(timezone.utc)
    app.state.demo_mode = False  # public release Phase 9b: app/demo/run.py serve_embedded sets these for the demo
    app.state.home_data_dir = settings.data_dir
    app.state.home_configured = not settings.setup_needed

    app.add_middleware(SetupGate, active=settings.setup_needed)
    app.add_middleware(PlainHttpRedirect, https=settings.https, legacy_tls=tls is not None and not settings.https)
    app.add_middleware(StaticCacheHeaders)
    app.include_router(health.router)
    app.include_router(setup.router)
    app.include_router(welcome.router)
    app.include_router(demo_api.router)  # public release Phase 9b: the demo page and the switch  # public release Phase 5a: first-run setup
    app.include_router(season.router)
    app.include_router(players.router)
    app.include_router(media.router)
    app.include_router(program.router)
    app.include_router(live.router)
    app.include_router(ticker.router)
    app.include_router(radio.router)
    app.include_router(identity.router)  # public release Phase 3
    app.include_router(analytics.router)
    app.include_router(settings_api.router)
    app.include_router(archive.router)
    app.include_router(notes.router)
    app.include_router(ratings.router)
    app.include_router(national.router)
    app.include_router(myteams.router)  # public release Phase 5b
    app.include_router(grades.router)  # public release Phase 7
    app.include_router(search_api.router)
    app.include_router(matchup_api.router)  # Phase 16 BX
    app.include_router(client_log.router)

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html", media_type="text/html", headers={"Cache-Control": "no-cache"})

    @app.get("/status", include_in_schema=False)
    async def status_page() -> FileResponse:
        """The Phase 0 server status page, kept as a diagnostics screen."""
        return FileResponse(STATIC_DIR / "status.html", media_type="text/html", headers={"Cache-Control": "no-cache"})

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        if request.url.path.startswith("/api/"):
            code = _HTTP_CODES.get(exc.status_code, "http_error")
            return error_response(exc.status_code, code, str(exc.detail))
        return PlainTextResponse(str(exc.detail), status_code=exc.status_code, headers=getattr(exc, "headers", None))

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        return error_response(422, "invalid_request", "A request parameter is missing or has the wrong type.")

    @app.exception_handler(Exception)
    async def unhandled_error(request: Request, exc: Exception):
        log.exception("Unhandled error on %s %s", request.method, request.url.path)
        if request.url.path.startswith("/api/"):
            return error_response(500, "server_error", "The server hit an unexpected error. It is in the log.")
        return PlainTextResponse("Server error. See logs/app.log.", status_code=500)

    return app
