"""When the port is taken (post-freeze Wave 1, owner 2026-10-25: "say what holds the port, offer the next free port, and a
startup failure window with a Copy button").

A start that cannot have its port asks three things before it gives up:

    running_copy(port)          is it Kickoff Companion itself? Its /api/health names the app. Then that copy is
                                opened instead (exit ALREADY_RUNNING), never a second one.
    port_holder(port)           otherwise, which program: netstat and tasklist on Windows, lsof elsewhere; None when
                                the system will not say.
    next_free_port(host, port)  the first port above it that binds, for the offer.

What it found is the startup report, data/startup-failure.json, which the tray icon reads to draw its window (Use port
N, Copy the report) and which a successful start removes. A start in a console asks the same question there.

    write_report(data_dir, report) / clear_report(data_dir) / read_report(data_dir)
    describe(report) -> str     the report in words, for the console, the log and the Copy button
"""

from __future__ import annotations

import contextlib
import io
import json
import logging
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app import APP_NAME

log = logging.getLogger("kickoff.portcheck")

REPORT_FILE = "startup-failure.json"
ALREADY_RUNNING = 6  # exit code: another copy of the app holds the port and was opened instead (5 is the in-place restart)
HEALTH_TIMEOUT = 2.0
COMMAND_TIMEOUT = 5.0
NEXT_PORT_TRIES = 20
NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW: a helper command flashes no console behind the tray


def running_copy(port: int, timeout: float = HEALTH_TIMEOUT) -> dict[str, Any] | None:
    """The running copy's health when Kickoff Companion answers on the port, else None."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{int(port)}/api/health", timeout=timeout) as response:  # noqa: S310 - a fixed local address
            body = json.loads(response.read(200_000).decode("utf-8", "replace"))
    except (OSError, ValueError, urllib.error.URLError):
        return None
    data = body.get("data", body) if isinstance(body, dict) else None
    app = data.get("app") if isinstance(data, dict) else None
    if isinstance(app, dict) and app.get("name") == APP_NAME:
        return data
    return None


def _run(args: list[str]) -> str:
    flags = NO_WINDOW if sys.platform == "win32" else 0
    try:
        done = subprocess.run(args, capture_output=True, text=True, timeout=COMMAND_TIMEOUT, creationflags=flags, check=False)  # noqa: S603 - fixed system tools
    except (OSError, subprocess.SubprocessError) as exc:
        log.info("%s could not run: %s", args[0], exc)
        return ""
    return done.stdout or ""


LISTEN_LINE = re.compile(r"^\s*TCP\s+\S*:(\d+)\s+\S+\s+LISTENING\s+(\d+)\s*$", re.IGNORECASE | re.MULTILINE)


def parse_netstat(text: str, port: int) -> int | None:
    """The PID listening on port in `netstat -ano -p TCP` (and TCPv6) output."""
    for found, pid in LISTEN_LINE.findall(text or ""):
        if int(found) == int(port) and int(pid) > 0:
            return int(pid)
    return None


def parse_tasklist(text: str) -> str | None:
    """The image name from `tasklist /FO CSV /NH` output: the first quoted field."""
    match = re.match(r'^\s*"([^"]+)"', text or "")
    return match.group(1) if match else None


def parse_lsof(text: str) -> tuple[int | None, str | None]:
    """The PID and command from `lsof -Fpc` output (p<pid> and c<command> lines)."""
    pid: int | None = None
    name: str | None = None
    for line in (text or "").splitlines():
        if line.startswith("p") and pid is None and line[1:].isdigit():
            pid = int(line[1:])
        elif line.startswith("c") and name is None and line[1:].strip():
            name = line[1:].strip()
    return pid, name


def port_holder(port: int, system: str = sys.platform) -> dict[str, Any] | None:
    """{"pid", "name"} of the program listening on port, or None when the system will not say."""
    pid: int | None
    name: str | None
    if system == "win32":
        pid = parse_netstat(_run(["netstat", "-ano", "-p", "TCP"]), port) or parse_netstat(_run(["netstat", "-ano", "-p", "TCPv6"]), port)
        if pid is None:
            return None
        name = parse_tasklist(_run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"]))
    else:
        pid, name = parse_lsof(_run(["lsof", "-nP", f"-iTCP:{int(port)}", "-sTCP:LISTEN", "-Fpc"]))
        if pid is None:
            return None
    return {"pid": pid, "name": name}


def next_free_port(host: str, port: int, tries: int = NEXT_PORT_TRIES) -> int | None:
    """The first port above `port` this host can bind, or None within `tries`."""
    from app.serving import bind_listener

    for candidate in range(int(port) + 1, min(int(port) + 1 + tries, 65536)):
        try:
            sock = bind_listener(host, candidate)
        except OSError:
            continue
        sock.close()
        return candidate
    return None


def report_path(data_dir: Path) -> Path:
    return Path(data_dir) / REPORT_FILE


def write_report(data_dir: Path, report: dict[str, Any]) -> None:
    path = report_path(data_dir)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **report}, indent=2), encoding="utf-8")
    except OSError as exc:
        log.warning("The startup report could not be written to %s: %s", path, exc)


def clear_report(data_dir: Path) -> None:
    with contextlib.suppress(OSError):
        report_path(data_dir).unlink(missing_ok=True)


def read_report(data_dir: Path) -> dict[str, Any] | None:
    try:
        raw = json.loads(report_path(data_dir).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return raw if isinstance(raw, dict) else None


def describe(report: dict[str, Any]) -> str:
    """The report in words: what holds the port and what to do."""
    port = report.get("port")
    holder = report.get("holder") if isinstance(report.get("holder"), dict) else None
    nxt = report.get("nextPort")
    if holder and holder.get("name"):
        who = f"{holder['name']} (process {holder.get('pid', '?')})"
    elif holder:
        who = f"process {holder.get('pid', '?')}"
    else:
        who = "another program (Windows did not say which)" if sys.platform == "win32" else "another program (the system did not say which)"
    lines = [f"Port {port} is taken by {who}, so {APP_NAME} could not start."]
    if holder and isinstance(holder.get("name"), str) and holder["name"].lower().startswith(("python", "kickoffcompanion", "uv")):
        lines.append(f"It may be another copy of {APP_NAME} that is not answering: stop it from the Task Manager, or use another port.")
    if isinstance(nxt, int):
        lines.append(f"Port {nxt} is free. Starting on it changes the address your devices open: they scan the new QR code on the status page once.")
    else:
        lines.append("No free port was found just above it; set another PORT in .env.")
    return "\n".join(lines)


def interactive(stdin: Any, system: str = sys.platform, environ: Any = None) -> bool:
    """Someone can answer in this console. Never behind the tray icon or another hidden start (KICKOFF_NO_PAUSE, set by
    tools/tray.ps1): its console has no window and a question would wait forever. On Windows the NUL device passes isatty,
    so the input must also be a real console (GetConsoleMode)."""
    if (os.environ if environ is None else environ).get("KICKOFF_NO_PAUSE"):
        return False
    try:
        if stdin is None or not stdin.isatty():
            return False
    except (AttributeError, OSError, ValueError):
        return False
    if system != "win32":
        return True
    try:
        import ctypes
        import msvcrt

        mode = ctypes.c_uint32()
        return bool(ctypes.windll.kernel32.GetConsoleMode(msvcrt.get_osfhandle(stdin.fileno()), ctypes.byref(mode)))  # type: ignore[attr-defined]
    except (ImportError, AttributeError, OSError, ValueError, io.UnsupportedOperation):  # BUG-21: no msvcrt off Windows
        return False


def ask_in_console(report: dict[str, Any], stdin: Any = None, stdout: Any = None, *, system: str = sys.platform, environ: Any = None) -> bool:
    """In a console, offer the next free port; True when the reader takes it. Never asks without someone to answer."""
    stdin = sys.stdin if stdin is None else stdin
    stdout = sys.stdout if stdout is None else stdout
    nxt = report.get("nextPort")
    if not isinstance(nxt, int) or not interactive(stdin, system, environ):
        return False
    try:
        stdout.write(f"\n{describe(report)}\n\nStart on port {nxt} and keep it? [Y/n] ")
        stdout.flush()
        answer = stdin.readline()
    except (OSError, ValueError, KeyboardInterrupt):
        return False
    if not answer:  # the input closed
        return False
    return answer.strip().lower() in ("", "y", "yes")
