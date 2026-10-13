"""`python -m app prompts`: every prompt through Claude Code, in one command (the Prompts phase, owner 2026-10-13).

    .\\.venv\\Scripts\\python -m app prompts          what is missing or out of date, in the season's order
    .\\.venv\\Scripts\\python -m app prompts --all    everything again
    KickoffCompanion.exe prompts                   the packaged program, the same

It talks to the running server (the same locked runners, files and quota guard the buttons use), so the server must be
up; with no server it says so and stops. The run is app/services/prompt_runs.py; this command starts it over
/api/prompts/run and prints one line per prompt as each finishes. A guest cannot run it: the server refuses a change
from any device that is not the host, and that covers this command from another computer too.

Exit status: 0 when every prompt that ran finished, 1 when one failed, 2 when the server could not be reached or
refused the run.

    main(argv, settings, http=None, sleep=None, out=print) -> int   http(method, path, body) -> (status, json) is the seam the tests use
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

from app.config import Settings

POLL_SECONDS = 5.0
TIMEOUT = 15.0
STATE_WORDS = {"waiting": "waiting", "skipped": "skipped", "running": "running", "done": "done", "failed": "FAILED", "stopped": "stopped"}


def http_client(base: str) -> Callable[[str, str, dict[str, Any] | None], tuple[int, Any]]:
    """A tiny HTTP seam over urllib: (status, parsed JSON or None)."""

    def call(method: str, path: str, body: dict[str, Any] | None = None) -> tuple[int, Any]:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(base.rstrip("/") + path, data=data, method=method, headers={"Content-Type": "application/json", "Accept": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:  # noqa: S310 - the server's own address
                raw = response.read()
                status = response.status
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            status = exc.code
        try:
            return status, json.loads(raw.decode("utf-8")) if raw else None
        except ValueError:
            return status, None

    return call


def _line(step: dict[str, Any]) -> str:
    label = str(step.get("label") or step.get("kind") or "?")
    state = str(step.get("state") or "waiting")
    word = STATE_WORDS.get(state, state)
    extra = step.get("error") if state == "failed" else step.get("detail")
    if state == "done" and step.get("changed") is True:
        extra = "new information"
    elif state == "done" and step.get("changed") is False:
        extra = "nothing new"
    return f"  {label}: {word}" + (f" ({extra})" if extra else "")


def main(argv: list[str], settings: Settings, http: Callable[..., tuple[int, Any]] | None = None, sleep: Callable[[float], None] | None = None, out: Callable[[str], None] = print) -> int:
    parser = argparse.ArgumentParser(prog="python -m app prompts", description="Run every prompt through Claude Code on the server, in the season's order.")
    parser.add_argument("--all", action="store_true", help="run everything again, not only what is missing")
    parser.add_argument("--url", help=f"the server's address (default http://127.0.0.1:{settings.port})")
    args = parser.parse_args(argv)
    base = (args.url or f"http://127.0.0.1:{settings.port}").rstrip("/")
    call = http or http_client(base)
    wait = sleep or time.sleep

    try:
        status, _health = call("GET", "/api/health", None)
    except OSError as exc:
        out(f"No server answered at {base} ({exc.__class__.__name__}). Start it first, then run this again.")
        return 2
    if status != 200:
        out(f"The server at {base} answered {status} to a health check. Start it, then run this again.")
        return 2

    try:
        status, body = call("POST", "/api/prompts/run", {"all": bool(args.all)})
    except OSError as exc:
        out(f"The server at {base} stopped answering ({exc.__class__.__name__}).")
        return 2
    data = body.get("data") if isinstance(body, dict) and isinstance(body.get("data"), dict) else {}
    message = next((e.get("message") for e in (body or {}).get("errors", []) if isinstance(e, dict)), None) if isinstance(body, dict) else None
    if status == 403:
        out("Refused: only the server computer or a host device can run the prompts. " + (message or ""))
        return 2
    if status != 200 or (data.get("error") and not data.get("running")):
        out(f"The run did not start: {data.get('error') or message or f'the server answered {status}'}")
        return 2
    out(f"Running {'everything again' if args.all else 'what is missing'} through Claude Code on the server ({len(data.get('steps') or [])} prompts). Each one takes a few minutes.")

    said: dict[str, str] = {}
    while True:
        steps = [s for s in (data.get("steps") or []) if isinstance(s, dict)]
        for step in steps:
            key = str(step.get("kind"))
            if step.get("state") in ("skipped", "done", "failed", "stopped") and said.get(key) != step.get("state"):
                said[key] = str(step.get("state"))
                out(_line(step))
        if not data.get("running"):
            break
        wait(POLL_SECONDS)
        try:
            status, body = call("GET", "/api/prompts/run", None)
        except OSError as exc:
            out(f"The server stopped answering ({exc.__class__.__name__}); the run goes on there. Open the Prompts page to follow it.")
            return 2
        data = body.get("data") if isinstance(body, dict) and isinstance(body.get("data"), dict) else {}
    failed = sum(1 for s in (data.get("steps") or []) if isinstance(s, dict) and s.get("state") == "failed")
    done = sum(1 for s in (data.get("steps") or []) if isinstance(s, dict) and s.get("state") == "done")
    skipped = sum(1 for s in (data.get("steps") or []) if isinstance(s, dict) and s.get("state") == "skipped")
    out(f"Finished: {done} done, {skipped} skipped, {failed} failed.")
    return 1 if failed else 0
