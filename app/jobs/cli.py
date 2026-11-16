"""The jobs' command line (spec 0.2): `python -m app.jobs.weekly` and `python -m app.jobs.talent_edge`.

With the server up, the command asks it to run the job (POST /api/jobs/<job>/run) and follows the run until it
ends, so the job uses the server's own client, cache and quota guard. With no server answering, it runs the job in
this process (nothing else is using the database then). A guest's computer is refused by the server, as for every
change.

Exit status: 0 when the job finished well, 1 when it failed (the reason is printed and the traceback is in the
log), 2 when it could not be started (settings, a season the server does not run, another run going).

    main(job, argv, settings=None, http=None, sleep=None, out=print) -> int    http and sleep are the tests' seams
"""

from __future__ import annotations

import argparse
import asyncio
import time
from collections.abc import Callable
from typing import Any

from app.config import Settings, SettingsError, load_settings
from app.prompts_cli import http_client

POLL_SECONDS = 3.0
WAIT_SECONDS = 1800.0


def _line(run: dict[str, Any]) -> str:
    status = str(run.get("status") or "?")
    word = {"ok": "finished", "failed": "FAILED", "running": "still running", "skipped": "skipped"}.get(status, status)
    week = f", week {run['week']}" if isinstance(run.get("week"), int) else ""
    return f"{run.get('job')} {word}{week}: {run.get('message') or '(no message)'}"


async def _here(job: str, settings: Settings) -> dict[str, Any]:
    from app.cfbd.client import CfbdClient
    from app.db import Database, database_path
    from app.jobs.setup import build_weekly

    db = Database(database_path(settings.data_dir))
    client = CfbdClient(settings, db)
    try:
        return await build_weekly(client, settings).run(job)
    finally:
        await client.aclose()
        db.close()


def main(job: str, argv: list[str], settings: Settings | None = None, http: Callable[..., tuple[int, Any]] | None = None, sleep: Callable[[float], None] | None = None, out: Callable[[str], None] = print) -> int:
    parser = argparse.ArgumentParser(prog=f"python -m app.jobs.{job}", description=f"Run the {job} job: on the running server when one answers, else here.")
    parser.add_argument("--season", type=int, help="the season (default: the one in .env)")
    parser.add_argument("--url", help="the server's address (default http://127.0.0.1:<PORT>)")
    args = parser.parse_args(argv)
    try:
        settings = settings or load_settings()
    except SettingsError as exc:
        out(str(exc))
        return 2
    season = args.season or settings.season
    base = (args.url or f"http://127.0.0.1:{settings.port}").rstrip("/")
    call = http or http_client(base)
    wait = sleep or time.sleep

    try:
        status, _health = call("GET", "/api/health", None)
    except OSError:
        status = 0
    if status != 200:
        out(f"No server answered at {base}; running {job} here.")
        if season != settings.season:
            settings = settings.model_copy(update={"season": season})
        from app.logging_setup import configure_logging

        configure_logging(settings, to_file=True)
        run = asyncio.run(_here(job, settings))
        out(_line(run))
        return 0 if run.get("status") in ("ok", "skipped") else 1

    if season != settings.season:
        out(f"The server runs the {settings.season} season, not {season}. Stop it to run another season here.")
        return 2
    status, body = call("POST", f"/api/jobs/{job}/run", {"confirm": True})
    data = body.get("data") if isinstance(body, dict) else None
    if status != 200 or not isinstance(data, dict) or not isinstance(data.get("run"), dict):
        errors = body.get("errors") if isinstance(body, dict) else None
        message = errors[0].get("message") if isinstance(errors, list) and errors and isinstance(errors[0], dict) else f"HTTP {status}"
        out(f"The server did not start {job}: {message}")
        return 2
    run = data["run"]
    out(f"Started {job} on the server ({run.get('id')}).")
    waited = 0.0
    while run.get("status") == "running" and waited < WAIT_SECONDS:
        wait(POLL_SECONDS)
        waited += POLL_SECONDS
        try:
            status, body = call("GET", f"/api/jobs/runs/{run.get('id')}", None)
        except OSError as exc:
            out(f"Lost the server while {job} ran ({exc.__class__.__name__}); its log has the rest.")
            return 1
        latest = body.get("data") if isinstance(body, dict) else None
        if status == 200 and isinstance(latest, dict):
            run = latest
    out(_line(run))
    return 0 if run.get("status") in ("ok", "skipped") else 1
