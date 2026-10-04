"""Command line entry: `python -m app [--check] [--reload] [--demo]`. The packaged program (tools/package/kickoff.py)
runs main() too, then pause_before_closing()."""

from __future__ import annotations

import argparse
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


def main(argv: list[str] | None = None, env_file: Path | None = DEFAULT_ENV_FILE) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--demo" in argv:
        # Demo mode has its own options (and reads no .env), so it takes over before parsing.
        from app.demo.run import main as demo_main

        return demo_main([a for a in argv if a != "--demo"])
    parser = argparse.ArgumentParser(prog="python -m app", description=f"Run the {APP_NAME} server.")
    parser.add_argument("--check", action="store_true", help="validate .env, print the settings, and exit")
    parser.add_argument("--reload", action="store_true", help="development mode: restart when code in app/ changes")
    parser.add_argument("--demo", action="store_true", help="run against the made-up league: no key, no network (--demo --help for its options)")
    parser.add_argument("--no-browser", action="store_true", help="do not open the app in this computer's browser once the server is up")
    parser.add_argument("--login", action="store_true", help="started at login (the start scripts pass it); opens the browser only if Settings say always")
    args = parser.parse_args(argv)

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
    from app.serving import run_server

    def serve(settings: Settings, *, first: bool) -> int:
        """One serve: the demo or this install's own team (public release Phase 9b: a fresh install starts in the
        demo; data/startup.json remembers a switch)."""
        opening = browser_url(settings, no_browser=args.no_browser or args.reload, login=args.login) if first else None
        if not args.reload and startmode.start_mode(settings) == startmode.DEMO:
            from app.demo.run import serve_embedded

            return serve_embedded(settings, open_url=f"{opening.rstrip('/')}/demo" if opening else None, restarting=not first)
        return run_server(settings, reload=args.reload, open_url=opening, restarting=not first)

    code = serve(settings, first=True)
    while code == restart.RESTART:  # setup finished, the team changed, or the demo was switched: serve again
        try:
            settings = load_settings(env_file)
        except SettingsError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        configure_logging(settings)
        code = serve(settings, first=False)
    return code


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
    if code == 0 or not (ROOTS.packaged if packaged is None else packaged) or not system.startswith("win"):
        return False
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
