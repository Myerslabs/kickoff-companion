"""Command line entry: `python -m app [--check] [--reload] [--demo]`. The packaged program (tools/package/kickoff.py)
runs main() too, then pause_before_closing()."""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app import APP_NAME, __version__
from app.config import DEFAULT_ENV_FILE, Settings, SettingsError, load_settings
from app.logging_setup import LOG_FILE_NAME, configure_logging
from app.netinfo import http_url, lan_ip, other_urls, preferred_host, tablet_url
from app.paths import ROOTS


def check_report(settings: Settings) -> str:
    """A secret-free summary of the loaded settings. Reads only; creates nothing."""
    from app.tls import describe_certificates

    ip = lan_ip()
    host = preferred_host(settings, ip)
    rows: list[tuple[str, str]] = [
        ("Settings file", str(settings.env_file_used) if settings.env_file_used else "(environment variables only)"),
        ("CFBD_API_KEY", "configured" if settings.api_key_configured else "not yet (the /welcome page asks for it)"),
        ("Team", f"{settings.team} {settings.season} ({settings.conference})" if settings.team and settings.conference else f"not picked yet (the /welcome page asks); season {settings.season}"),
        ("Time zone", settings.timezone),
        ("Listen on", f"{settings.host}:{settings.port}"),
        ("Tablet URL", tablet_url(settings, ip)),
    ]
    rows += [("Also at", url) for url in other_urls(settings, ip)]
    rows.append(("Network name", f"{settings.mdns_host} (announced while the server runs)" if settings.mdns_host else "off (MDNS_NAME)"))
    rows += [
        ("HTTPS", describe_certificates(settings.data_dir / "certs") if settings.https else (
            "off: plain HTTP, nothing to install on a device"
            + ("; old certificates kept so https:// links are sent to http://" if (settings.data_dir / "certs" / "ca.crt").is_file() else "")
        )),
        ("Setup page", f"{http_url(host, settings.port)}/setup (plain http, for new devices)"),
        ("Quota", f"{settings.monthly_call_budget:,} calls per month, hard stop at {settings.quota_hard_stop_pct}%"),
        ("Live poll", f"every {settings.live_poll_seconds} s"),
        ("Radio sources", ", ".join(source.name for source in settings.radio_sources) or "none (add RADIO_SOURCES to .env)"),
        ("Log file", f"{settings.log_dir / LOG_FILE_NAME} ({settings.log_level})"),
        ("Data folder", str(settings.data_dir)),
    ]
    if ROOTS.packaged:  # public release Phase 10
        rows += [("Program", str(ROOTS.program)), ("Files", f"{ROOTS.install} ({'beside the program' if ROOTS.portable else 'the app-data folder; a file named portable beside the program keeps them there instead'})")]
    width = max(len(label) for label, _ in rows)
    lines = [f"{APP_NAME} {__version__} settings check", ""]
    lines += [f"  {label:<{width}}  {value}" for label, value in rows]
    lines += ["", "All settings valid."]
    return "\n".join(lines)


RULE = "=" * 76


def console_banner(settings: Settings, *, demo: bool) -> str:
    """The server window's first lines, in plain words. A tester (2026-10-19) took the quiet half minute of a first start
    for a crash, and closed the window as soon as the browser opened, which stops the server for every device."""
    lines = [
        RULE,
        f" {APP_NAME} {__version__}: this window is the server.",
        " Keep it open while you watch. Closing it stops the app on every phone and tablet.",
        (" Starting the demo. The first start builds its league, about half a minute; the window is not stuck."
         if demo else " Starting. The browser opens by itself once the server is ready."),
        f" Log file: {settings.log_dir / LOG_FILE_NAME}",
        RULE,
        "",
    ]
    return "\n".join(lines)


def ready_note(settings: Settings, *, demo: bool) -> str:
    """What the window says once the server listens (printed by app/serving.py), with both addresses."""
    ip = lan_ip()
    what = "The demo is" if demo else "The app is"
    lines = [
        "",
        RULE,
        f" READY. {what} at {http_url('localhost', settings.port)} on this computer,",
        f" and at {tablet_url(settings, ip)} on a phone or tablet on this Wi-Fi (or scan the QR code above).",
        " Keep this window open. To hide it behind a tray icon: Settings, Start and the server, Desktop icon (tray).",
        RULE,
        "",
    ]
    return "\n".join(lines)


def set_console_title(title: str, system: str = sys.platform) -> bool:
    """Name the server window on Windows, so the taskbar says what it is. Returns True when it did."""
    if not system.startswith("win"):
        return False
    try:
        import ctypes

        return bool(ctypes.windll.kernel32.SetConsoleTitleW(title))  # type: ignore[attr-defined]
    except (OSError, AttributeError, ValueError, TypeError):
        return False


def main(argv: list[str] | None = None, env_file: Path | None = DEFAULT_ENV_FILE) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "prompts":  # the Prompts phase (2026-10-13): every prompt through Claude Code on the running server
        from app.prompts_cli import main as prompts_main

        try:
            settings = load_settings(env_file)
        except SettingsError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        return prompts_main(argv[1:], settings)
    if "--demo" in argv:
        # Demo mode has its own options (and reads no .env), so it takes over before parsing.
        from app.demo.run import main as demo_main

        return demo_main([a for a in argv if a != "--demo"])
    parser = argparse.ArgumentParser(prog="python -m app", description=f"Run the {APP_NAME} server. `python -m app prompts [--all]` runs every prompt through Claude Code on the running server.")
    parser.add_argument("--check", action="store_true", help="validate .env, print the settings, and exit")
    parser.add_argument("--reload", action="store_true", help="development mode: restart when code in app/ changes")
    parser.add_argument("--demo", action="store_true", help="run against the test league (invented games and players): no key, no network (--demo --help for its options)")
    parser.add_argument("--no-browser", action="store_true", help="do not open the app in this computer's browser once the server is up")
    parser.add_argument("--login", action="store_true", help="started at login (the start scripts pass it); opens the browser only if Settings say always")
    parser.add_argument("--use-port", type=int, metavar="N", help="save PORT=N in .env and exit (the tray icon's \"Use port N\" when the port is taken)")
    parser.add_argument("--restarted", action="store_true", help="the launcher starts the server again after a restart: no browser, and the port may take a moment to come free")
    args = parser.parse_args(argv)

    if args.use_port is not None:
        return use_port(args.use_port, env_file)

    try:
        settings = load_settings(env_file)
    except SettingsError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.check:
        print(check_report(settings))
        if settings.setup_needed:  # public release Phase 5a: the browser finishes the setup
            print(f"\nSetup needed: start the server, then open http://localhost:{settings.port}/welcome to add a CFBD key and pick a team.")
        return 0

    # In reload mode this process only watches files; the worker it spawns writes the log file.
    configure_logging(settings, to_file=not args.reload)

    from app import restart, startmode
    from app.serving import PORT_CHANGED, run_server

    def demo_start(settings: Settings) -> bool:
        return not args.reload and startmode.start_mode(settings) == startmode.DEMO

    def serve(settings: Settings, *, first: bool) -> int:
        """One serve: the demo or this install's own team (public release Phase 9b: a fresh install starts in the
        demo; data/startup.json remembers a switch)."""
        opening = browser_url(settings, no_browser=args.no_browser or args.reload, login=args.login) if first else None
        if demo_start(settings):
            from app.demo.run import serve_embedded

            return serve_embedded(settings, open_url=f"{opening.rstrip('/')}/demo" if opening else None, restarting=not first, ready_note=ready_note(settings, demo=True))
        return run_server(settings, reload=args.reload, open_url=opening, restarting=not first, ready_note=ready_note(settings, demo=False))

    set_console_title(f"{APP_NAME} server (keep this window open)")
    print(console_banner(settings, demo=demo_start(settings)), flush=True)
    code = serve(settings, first=not args.restarted)
    while code in (restart.RESTART, PORT_CHANGED):  # setup finished, the team changed, the demo was switched, an update, or a new port: serve again
        if code == restart.RESTART and restart.relaunch_available():
            print("Restarting in a fresh process, which loads any new code.", flush=True)
            return restart.RELAUNCH  # BUG-22: the launcher starts the server again
        if code == restart.RESTART:
            from app.build import code_changed

            if code_changed():
                logging.getLogger("kickoff.restart").warning("The server's code changed on disk; this restart keeps the code it started with. Start it again with start.ps1 to load the new code.")
        try:
            settings = load_settings(env_file)
        except SettingsError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        configure_logging(settings)
        code = serve(settings, first=code == PORT_CHANGED)  # a new port is a new address: the browser opens it as on a first start
    return code


def use_port(port: int, env_file: Path | None) -> int:
    """`--use-port N` (post-freeze Wave 1): save PORT in .env for the tray icon's "Use port N", then exit."""
    from app.services import envfile

    if not 1024 <= port <= 65535:
        print(f"{port} is not a port this app can use (1024 to 65535).", file=sys.stderr)
        return 2
    path = Path(env_file) if env_file is not None else DEFAULT_ENV_FILE
    try:
        envfile.set_values(path, {"PORT": str(port)})
    except (OSError, ValueError, envfile.EnvFileError) as exc:
        print(f"PORT could not be saved: {exc}", file=sys.stderr)
        return 1
    print(f"PORT={port} saved in {path}.")
    return 0


def console_owners(default: int = 1) -> int:
    """How many processes share this console (Windows). One means the console is ours alone, as after a double-click,
    and closes with the program. More means a shell started us and keeps the window."""
    if not sys.platform.startswith("win"):
        return default
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        buffer = (ctypes.c_uint32 * 64)()
        count = int(kernel32.GetConsoleProcessList(buffer, 64))
        return count if count > 0 else default
    except (OSError, AttributeError, ValueError, TypeError):
        return default


def pause_before_closing(
    code: int,
    *,
    packaged: bool | None = None,
    system: str = sys.platform,
    owners: int | None = None,
    ask: Callable[[str], Any] = input,
) -> bool:
    """The packaged program on Windows, started by a double-click and stopping with a message (a busy port, a bad
    .env): wait for Enter so the message can be read before the window closes (public release Phase 10). A clean
    stop, a shell start, a checkout or another system never waits. Returns True when it waited."""
    from app.portcheck import ALREADY_RUNNING

    if code in (0, ALREADY_RUNNING) or not (ROOTS.packaged if packaged is None else packaged) or not system.startswith("win"):
        return False  # a running copy was opened instead: nothing to read
    if (console_owners() if owners is None else owners) != 1:
        return False
    try:
        ask("\nPress Enter to close this window. ")
    except (EOFError, OSError, KeyboardInterrupt):
        pass
    return True


def browser_url(settings: Settings, *, no_browser: bool, login: bool) -> str | None:
    """The address to open on this computer once the server is up, or None. The Settings choice
    (data/settings.json, openBrowser) decides: "manual" opens for a start by hand, "always" also at
    login, "never" not at all. --no-browser and the development mode never open."""
    if no_browser:
        return None
    from app.services.connect import local_address
    from app.services.prefs import PrefsStore

    choice = PrefsStore(settings.data_dir).prefs.openBrowser
    if choice == "never" or (login and choice != "always"):
        return None
    return local_address(settings)
