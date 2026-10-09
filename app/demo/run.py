"""Demo mode: the real app against the made-up league, on a simulated clock.

`python -m app --demo` and `tools/live_sim.py` both run this. Nothing here calls CFBD or any other
site, reads .env, or touches the project's data folder (the app gets a fresh scratch folder; the
league itself is cached in data/demo/). The clock starts a little before the demo team's next
kickoff and runs `speed` simulated seconds per real second, so a whole game plays out on the Live
sheet in about twenty minutes at the default speed.

Known limits: the browser's own clock (Date.now) runs in real time, so "x minutes ago" labels drift
from the simulated time; dates shown are the league's season, not today's.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import shutil
import socket
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.config import PROJECT_ROOT  # this install's folder: the project from a checkout, the app-data folder as the packaged program
from app.demo import names as N
from app.demo.season import World
from app.demo.sites import DemoSites
from app.demo.upstream import DemoUpstream, load_world

CACHE_DIR = PROJECT_ROOT / "data" / "demo"  # the league, built once and pickled
DEMO_KEY = "DEMOKEY-" + "d0" * 16  # never a real key
FAKE_BASE_URL = "http://cfbd.demo.invalid"  # never resolvable, so a missed transport cannot reach CFBD
DEFAULT_PORT = 8650

log = logging.getLogger("kickoff.demo")


def say(message: str) -> None:
    print(f"[demo] {message}", flush=True)


def demo_season(today: datetime | None = None) -> int:
    """The season the demo plays: this year's from March on, last year's before."""
    today = today or datetime.now(timezone.utc)
    return today.year if today.month >= 3 else today.year - 1


class SimClock:
    """Simulated UTC time: starts at `start`, runs `speed` simulated seconds per real second."""

    def __init__(self, start: datetime, speed: float) -> None:
        self.speed = speed
        self.mono0 = time.monotonic()
        self.sim0 = start

    def __call__(self) -> datetime:
        return self.sim0 + timedelta(seconds=(time.monotonic() - self.mono0) * self.speed)

    def real_at(self, moment: datetime) -> float:
        """The monotonic real time at which the simulated clock reaches `moment`."""
        return self.mono0 + (moment - self.sim0).total_seconds() / self.speed

    async def sleep(self, seconds: float) -> None:
        """The app's sleeps are simulated seconds; wait the real equivalent."""
        try:
            seconds = float(seconds)
        except (TypeError, ValueError):
            seconds = 0.0
        await asyncio.sleep(max(0.0, seconds) / self.speed)


def next_game(world: World, after: datetime | None = None):
    """The game the demo opens on: by default the demo team's closest-matched game of weeks 4 to
    9 (a few results behind it, and a game worth watching); with `after`, its next game then."""
    league = world.league
    us = league.team(N.OUR_SCHOOL)
    data = world.seasons[world.season]
    ours = sorted((r for r in data.records if us.id in (r.slot.home, r.slot.away) and r.slot.season_type == "regular"), key=lambda r: r.slot.start)
    if after is None:
        window = [r for r in ours if 4 <= r.slot.week <= 9] or ours
        return min(window, key=lambda r: (abs(r.home_expected), r.slot.start))
    return next((r for r in ours if r.end > after), ours[-1])


class FailWindow:
    """Makes /live/plays answer 500 for a while, to exercise retries and the circuit breaker."""

    def __init__(self, clock: SimClock, start: datetime | None, real_seconds: float) -> None:
        self.start = clock.real_at(start) if start is not None else None
        self.end = self.start + real_seconds if self.start is not None else None
        self.state = "before"

    def __call__(self, path: str) -> bool:
        if path != "/live/plays" or self.start is None:
            return False
        now = time.monotonic()
        active = self.start <= now < (self.end or 0)
        if active and self.state == "before":
            self.state = "active"
            say(f"failure injection ON: /live/plays answers HTTP 500 for {self.end - self.start:.0f} real seconds")
        elif not active and self.state == "active":
            self.state = "after"
            say("failure injection OFF: /live/plays answers normally again")
        return active


def build(world: World, clock: SimClock, data_dir: Path, port: int, host: str, tier: int, fail: FailWindow | None, mdns_name: str = "off"):
    import httpx

    import app.main as app_main
    from app.config import Settings, load_settings
    from app.main import create_app

    for name in list(getattr(Settings, "model_fields", {}) or {}):  # nothing from this shell's environment
        os.environ.pop(name.upper(), None)
    us = world.league.team(N.OUR_SCHOOL)
    settings = load_settings(
        env_file=None, cfbd_api_key=DEMO_KEY, cfbd_base_url=FAKE_BASE_URL, team=us.school, conference=us.conference,
        season=world.season, host=host, port=port, lan_hostname="", mdns_name=mdns_name, data_dir=str(data_dir), log_dir=str(data_dir / "logs"),
        monthly_call_budget={0: 1000, 1: 5000}.get(tier, 30000),
    )
    upstream = DemoUpstream(world, clock, tier=tier, fail=fail)
    sites = DemoSites(world, clock)
    application = create_app(
        settings,
        cfbd_transport=httpx.MockTransport(upstream.handler),
        media_transport=httpx.MockTransport(DemoSites.media_handler),
        feeds_transport=httpx.MockTransport(sites.handler),
        weather_transport=httpx.MockTransport(sites.handler),
        logo_transport=httpx.MockTransport(DemoSites.media_handler),
        wiki_transport=httpx.MockTransport(DemoSites.media_handler),
        wiki_lookups=False,  # Phase 17 #4: the made-up teams are not on Wikipedia; every header link is a search
        updates_transport=httpx.MockTransport(DemoSites.media_handler),
        update_checks=False,  # Phase 16 wave 3: the demo never asks GitHub
    )
    state = application.state
    state.cfbd._clock = clock  # the engine, feeds, weather and every service read the client's clock
    state.cfbd._sleep = clock.sleep  # retry backoff in simulated seconds
    state.live._sleep = clock.sleep  # poll intervals, backoff and schedule checks in simulated seconds
    launcher = getattr(state, "launcher", None)
    if launcher is not None:
        try:
            launcher.runner = lambda _args: (1, "disabled in demo mode")
            launcher.appdata = str(data_dir / "appdata")
            launcher.home = data_dir / "home"  # Linux and macOS write their files under the home folder
        except AttributeError:
            pass
    notes = getattr(state, "notes", None)
    if notes is not None and hasattr(notes, "start") and hasattr(notes, "status"):
        async def refuse_notes(game: Any, command: str) -> dict[str, Any]:
            return {**notes.status(command), "error": "The notes task is off in demo mode."}

        notes.start = refuse_notes
    # Plain HTTP: drop the HTTP-to-HTTPS redirect (the demo has no certificate).
    redirect_cls = getattr(app_main, "PlainHttpRedirect", None)
    before = len(application.user_middleware)
    application.user_middleware = [m for m in application.user_middleware if redirect_cls is None or getattr(m, "cls", None) is not redirect_cls]
    asgi = application
    if len(application.user_middleware) == before:
        async def as_https(scope, receive, send):
            if scope.get("type") in ("http", "websocket"):
                scope = {**scope, "scheme": "https" if scope["type"] == "http" else "wss"}
            await application(scope, receive, send)

        asgi = as_https
    return application, asgi, upstream, settings


class ConsoleFilter(logging.Filter):
    """Errors from anywhere; warnings from the live engine, the CFBD client and the server."""

    WATCHED = ("kickoff.live", "kickoff.cfbd", "kickoff.main", "kickoff.serving", "kickoff.demo", "uvicorn")

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno >= logging.ERROR:
            return True
        return record.levelno >= logging.WARNING and record.name.startswith(self.WATCHED)


def fmt_offset(seconds: float) -> str:
    sign = "-" if seconds < 0 else "+"
    seconds = abs(int(seconds))
    return f"K{sign}{seconds // 3600}:{(seconds % 3600) // 60:02d}:{seconds % 60:02d}"


def status_line(application, upstream: DemoUpstream, clock: SimClock, game, settings) -> str:
    engine = application.state.live
    try:
        state = engine.state(0) if hasattr(engine, "state") else None
    except Exception as exc:  # noqa: BLE001 - a report must never stop the demo
        state = {"error": str(exc)}
    now = clock()
    since = (now - game.slot.start).total_seconds()
    parts = [f"sim {now.astimezone(settings.tzinfo):%a %H:%M:%S} ({fmt_offset(since)})", f"mode {getattr(engine, 'mode', '?')}"]
    if isinstance(state, dict) and state.get("homeScore") is not None:
        parts.append(f"{state.get('away') or 'away'} {state.get('awayScore')} at {state.get('home') or 'home'} {state.get('homeScore')} [{state.get('status') or '-'}]")
    parts.append(f"calls {upstream.total_calls}")
    return " | ".join(parts)


async def reporter(application, upstream: DemoUpstream, clock: SimClock, game, settings, every: float) -> None:
    last_mode = None
    next_line = 0.0
    while True:
        try:
            mode = getattr(application.state.live, "mode", None)
            if mode != last_mode:
                say(f"engine mode {last_mode or '-'} -> {mode} at {fmt_offset((clock() - game.slot.start).total_seconds())}")
                last_mode = mode
            if time.monotonic() >= next_line:
                next_line = time.monotonic() + every
                print(await asyncio.to_thread(status_line, application, upstream, clock, game, settings), flush=True)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            say(f"status unavailable: {exc.__class__.__name__}: {exc}")
        await asyncio.sleep(1.0)


def port_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind((host if host != "0.0.0.0" else "127.0.0.1", port))
        except OSError:
            return False
    return True


PORT_TRIES = 20


def pick_port(host: str, wanted: int | None) -> int | None:
    """The port to serve on: the one asked for if it is free; with none asked for, the first free
    one from DEFAULT_PORT up. None when nothing suitable is free."""
    if wanted is not None:
        return wanted if port_free(host, wanted) else None
    return next((p for p in range(DEFAULT_PORT, DEFAULT_PORT + PORT_TRIES) if port_free(host, p)), None)


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--port", type=int, default=None, help=f"port (default: {DEFAULT_PORT}, or the next free one up to {DEFAULT_PORT + PORT_TRIES - 1})")
    parser.add_argument("--host", default="127.0.0.1", help="address to listen on (default 127.0.0.1; 0.0.0.0 to reach it from a tablet)")
    parser.add_argument("--speed", type=float, default=10.0, help="simulated seconds per real second (default 10)")
    parser.add_argument("--start", type=float, default=-30.0, help="simulated minutes relative to the next kickoff at launch (default -30)")
    parser.add_argument("--tier", type=int, default=2, choices=(0, 1, 2), help="the CFBD plan to imitate: 0 Free, 1 Tier 1, 2 Tier 2 (default)")
    parser.add_argument("--season", type=int, default=None, help="the league's season (default: this season)")
    parser.add_argument("--data", default=None, help="data folder for the app (default: a new temp folder)")
    parser.add_argument("--fail-at", type=float, default=None, help="simulated minute after kickoff when /live/plays starts failing")
    parser.add_argument("--fail-for", type=float, default=60.0, help="real seconds the failure lasts (default 60)")
    parser.add_argument("--report", type=float, default=30.0, help="real seconds between status lines (default 30)")
    parser.add_argument("--verbose", action="store_true", help="show the app's INFO log lines on the console")
    parser.add_argument("--clean", action="store_true", help="delete the temp data folder on exit")
    parser.add_argument("--no-browser", action="store_true", help="do not open the demo in this computer's browser once it is up")


def run(args: argparse.Namespace) -> int:
    if args.speed <= 0:
        print("--speed must be greater than 0", file=sys.stderr)
        return 2
    if args.port is not None and not 1 <= args.port <= 65535:
        print("--port must be 1-65535", file=sys.stderr)
        return 2
    port = pick_port(args.host, args.port)
    if port is None:
        if args.port is not None:
            print(f"Port {args.port} is in use. Stop the other process or pass another --port.", file=sys.stderr)
        else:
            print(f"Ports {DEFAULT_PORT} to {DEFAULT_PORT + PORT_TRIES - 1} are all in use. Pass a free one with --port.", file=sys.stderr)
        return 2
    if args.port is None and port != DEFAULT_PORT:
        say(f"port {DEFAULT_PORT} is in use (another demo or simulator?); using {port}")
    args.port = port
    created = args.data is None
    data_dir = Path(tempfile.mkdtemp(prefix="kickoff-demo-")) if created else Path(args.data).expanduser().resolve()
    project_data = (PROJECT_ROOT / "data").resolve()
    if data_dir == PROJECT_ROOT or data_dir == project_data or (project_data in data_dir.parents and CACHE_DIR.resolve() not in (data_dir, *data_dir.parents)):
        print(f"Refusing to use {data_dir}: it is the project's own data folder. Pick a scratch folder.", file=sys.stderr)
        return 2
    data_dir.mkdir(parents=True, exist_ok=True)
    season = args.season or demo_season()
    started = time.monotonic()
    say(f"building the made-up {season} league (cached in {CACHE_DIR} after the first run)...")
    world = load_world(season=season, seed=2026, cache_dir=CACHE_DIR)
    say(f"league ready in {time.monotonic() - started:.1f} s")
    game = next_game(world)
    clock = SimClock(game.slot.start + timedelta(minutes=args.start), args.speed)
    fail = FailWindow(clock, game.slot.start + timedelta(minutes=args.fail_at), args.fail_for) if args.fail_at is not None else None
    application, asgi, upstream, settings = build(world, clock, data_dir, args.port, args.host, args.tier, fail)
    if not args.verbose:
        for handler in logging.getLogger().handlers:
            if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
                handler.addFilter(ConsoleFilter())

    import uvicorn

    config = uvicorn.Config(asgi, host=args.host, port=args.port, log_config=None, access_log=False, lifespan="on", timeout_graceful_shutdown=3)
    server = uvicorn.Server(config)
    league = world.league
    home, away = league.by_id[game.slot.home], league.by_id[game.slot.away]
    shown = "127.0.0.1" if args.host in ("0.0.0.0", "127.0.0.1") else args.host
    say(f"Kickoff Companion demo on http://{shown}:{args.port}/  (made-up league, no key, no network)")
    say(f"data in {data_dir}; log {data_dir / 'logs' / 'app.log'}; CFBD plan imitated: {('Free', 'Tier 1', 'Tier 2')[args.tier]}")
    say(f"{away.school} at {home.school} kicks off {game.slot.start.astimezone(settings.tzinfo):%a %b %d %H:%M %Z} (league time); "
        f"clock starts at {fmt_offset(args.start * 60)}, speed x{args.speed:g}")
    final_in = max(0.0, game.duration - args.start * 60) / args.speed / 60
    say(f"the final arrives about {final_in:.0f} real minutes from now. Ctrl+C stops the demo.")

    async def open_when_up() -> None:
        from app.serving import open_in_browser

        while not server.started and not server.should_exit:
            await asyncio.sleep(0.1)
        if server.started:
            open_in_browser(f"http://{shown}:{args.port}/")

    async def serve() -> None:
        task = asyncio.create_task(reporter(application, upstream, clock, game, settings, args.report))
        opener = None if args.no_browser else asyncio.create_task(open_when_up())
        try:
            await server.serve()
        finally:
            for job in (task, opener):
                if job is None:
                    continue
                job.cancel()
                try:
                    await job
                except asyncio.CancelledError:
                    pass

    try:
        asyncio.run(serve())
    except KeyboardInterrupt:
        pass
    finally:
        say(f"stopped. upstream calls {upstream.total_calls} ({upstream.calls.get('/live/plays', 0)} live)")
        if created and args.clean:
            shutil.rmtree(data_dir, ignore_errors=True)
            say(f"deleted {data_dir}")
    return 0


EMBEDDED_START = 25.0  # simulated minutes after kickoff: a fresh install opens on a game already under way
EMBEDDED_SPEED = 6.0  # about half an hour of live game before the final


def serve_embedded(home: Any, *, open_url: str | None = None, restarting: bool = False) -> int:
    """The demo on this install's own address and port (public release Phase 9b): a fresh install, or the menu's
    Demo item, starts here. Phones reach it as they would the app (the QR code, the network name). The demo's
    data is a scratch folder deleted at the end; `home` (this install's settings) only gives the address and
    the folder where the start mode is saved. Returns a process exit code, or restart.RESTART on a switch."""
    from app.serving import run_server

    season = demo_season()
    say(f"Starting the demo: the made-up {season} league (built once, then cached in {CACHE_DIR}).")
    world = load_world(season=season, seed=2026, cache_dir=CACHE_DIR)
    game = next_game(world)
    clock = SimClock(game.slot.start + timedelta(minutes=EMBEDDED_START), EMBEDDED_SPEED)
    data_dir = Path(tempfile.mkdtemp(prefix="kickoff-demo-"))
    try:
        application, asgi, _upstream, _settings = build(world, clock, data_dir, home.port, home.host, 2, None, mdns_name=home.mdns_name)
        application.state.demo_mode = True
        application.state.home_data_dir = Path(home.data_dir)
        application.state.home_configured = not home.setup_needed
        for handler in logging.getLogger().handlers:
            if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
                handler.addFilter(ConsoleFilter())
        say("This is the demo: a made-up league with a game under way. The demo page in the browser explains how to use your own team.")
        return run_server(home, open_url=open_url, restarting=restarting, asgi=asgi)
    finally:
        shutil.rmtree(data_dir, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app --demo", description="Run the app against the made-up league.")
    add_arguments(parser)
    return run(parser.parse_args(argv))
