"""The weekly jobs (Feature Set v2, owner 2026-10-30): Talent Edge (FEAT-16), then the Imperialism Map (FEAT-17) and
Circle of Blame (FEAT-18) as they are built, run in that order by the server's housekeeping loop each Sunday from
06:00 local (app/jobs/weekly.py). Owner 2026-10-30, "App's way": the server's own loop, not Windows Task Scheduler,
so one process owns the database, the quota guard and the memory cache; the commands below ask the running server
and run in their own process only when no server answers (app/jobs/cli.py).

    python -m app.jobs.weekly --season 2026     every job, in order
    python -m app.jobs.talent_edge              one job

Every run is recorded in data/jobs.json (the spec's job_runs: job, season, week, started, finished, status,
message), the last RUNS_KEPT of each job; the status page and Settings show each job's last run. A job that cannot
do its work raises JobFailed with a one-line reason: the run is marked failed, the traceback logged, and the files
it would have written stay as they were.

    JobRuns(data_dir, clock)       start(job, season) -> run; finish(run, status, message, week, detail); last(job)
    run_job(runs, name, season, work) -> run     work() -> {"week", "message", ...}; never raises
    read_runs(data_dir) -> runs    the log as it is on disk, read only (a page reading it never touches a run)
    last_of(runs, job, season=None, status=None) -> the newest matching run, or None
"""

from __future__ import annotations

import json
import logging
import secrets
import threading
from collections.abc import Awaitable, Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from app.services.answers import atomic_write

log = logging.getLogger("kickoff.jobs")

RUNS_KEPT = 20
JOB_LABELS = {"weekly": "Weekly jobs", "talent_edge": "Talent Edge", "imperialism": "Imperialism Map", "circle_of_blame": "Circle of Blame"}
DONE = ("ok", "skipped")  # a run that needs no retry: it did its work, or there was nothing it could do here


class JobFailed(Exception):
    """A job could not do its work. The message is the one line the run log, the status page and the command show."""


class JobSkipped(Exception):
    """There is nothing the job can do on this computer or this week (FEAT-18, owner 2026-10-30: where Claude Code is not
    found the run is skipped with a note, not failed). Recorded as "skipped" with the reason; never retried before its
    next slot."""


def _now() -> datetime:
    return datetime.now().astimezone()


def read_runs(data_dir: Path) -> list[dict[str, Any]]:
    """data/jobs.json's runs, oldest first; [] when the file is missing or unreadable (logged)."""
    path = Path(data_dir) / "jobs.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except (OSError, ValueError) as exc:
        log.warning("The job log %s could not be read (%s)", path, exc)
        return []
    runs = raw.get("runs") if isinstance(raw, dict) else None
    return [r for r in runs if isinstance(r, dict) and isinstance(r.get("id"), str) and isinstance(r.get("job"), str)] if isinstance(runs, list) else []


def last_of(runs: list[dict[str, Any]], job: str, season: int | None = None, status: str | None = None) -> dict[str, Any] | None:
    for run in reversed(runs):
        if run["job"] == job and (season is None or run.get("season") == season) and (status is None or run.get("status") == status):
            return dict(run)
    return None


class JobRuns:
    """data/jobs.json: {"runs": [...]}, newest last, RUNS_KEPT per job. Written whole after every change."""

    def __init__(self, data_dir: Path, clock: Callable[[], datetime] | None = None) -> None:
        self.path = Path(data_dir) / "jobs.json"
        self._clock = clock or _now
        self._lock = threading.Lock()
        self._runs = read_runs(data_dir)
        self._abandon()

    def _abandon(self) -> None:
        """A run still marked running when the server starts was cut off by a stop: it failed."""
        changed = False
        for run in self._runs:
            if run.get("status") == "running":
                run.update({"status": "failed", "message": "The server stopped during the run.", "finishedAt": None})
                changed = True
        if changed:
            self._save()

    def _save(self) -> None:
        kept: list[dict[str, Any]] = []
        counts: dict[str, int] = {}
        for run in reversed(self._runs):
            counts[run["job"]] = counts.get(run["job"], 0) + 1
            if counts[run["job"]] <= RUNS_KEPT:
                kept.append(run)
        self._runs = list(reversed(kept))
        try:
            atomic_write(self.path, json.dumps({"runs": self._runs}, indent=1) + "\n")
        except OSError as exc:
            log.warning("Could not keep the job log: %s", exc)

    def start(self, job: str, season: int) -> dict[str, Any]:
        run = {"id": f"{job}-{secrets.token_hex(4)}", "job": job, "season": season, "week": None, "startedAt": self._clock().isoformat(timespec="seconds"), "finishedAt": None, "status": "running", "message": None, "detail": None}
        with self._lock:
            self._runs.append(run)
            self._save()
        return dict(run)

    def finish(self, run_id: str, status: str, message: str | None, week: int | None = None, detail: dict[str, Any] | None = None) -> dict[str, Any] | None:
        with self._lock:
            run = next((r for r in self._runs if r["id"] == run_id), None)
            if run is None:
                return None
            run.update({"status": status, "message": message, "week": week, "detail": detail, "finishedAt": self._clock().isoformat(timespec="seconds")})
            self._save()
            return dict(run)

    def get(self, run_id: str) -> dict[str, Any] | None:
        run = next((r for r in self._runs if r["id"] == run_id), None)
        return dict(run) if run is not None else None

    def last(self, job: str, season: int | None = None, status: str | None = None) -> dict[str, Any] | None:
        return last_of(self._runs, job, season, status)

    def status(self) -> dict[str, Any]:
        """{job: its last run} for every job that has run, with its label; the status page and Settings read it."""
        out: dict[str, Any] = {}
        for run in self._runs:
            out[run["job"]] = {**run, "label": JOB_LABELS.get(run["job"], run["job"])}
        return dict(sorted(out.items()))


async def run_job(runs: JobRuns, name: str, season: int, work: Callable[[], Awaitable[dict[str, Any]]], run: dict[str, Any] | None = None) -> dict[str, Any]:
    """One recorded run of `work` (`run`: one already started, so its id could be handed out first). JobFailed is
    the job's own one-line reason; anything else is logged with its traceback and recorded by its type. Never
    raises: the housekeeping loop and the answers read the record."""
    run = run or runs.start(name, season)
    label = JOB_LABELS.get(name, name)
    try:
        result = await work()
    except JobSkipped as exc:
        log.info("%s skipped: %s", label, exc)
        return runs.finish(run["id"], "skipped", str(exc)) or run
    except JobFailed as exc:
        log.error("%s failed: %s", label, exc, exc_info=True)
        return runs.finish(run["id"], "failed", str(exc)) or run
    except Exception as exc:  # noqa: BLE001 - recorded and logged with the traceback; the next run tries again
        log.exception("%s failed unexpectedly", label)
        return runs.finish(run["id"], "failed", f"Unexpected error: {exc.__class__.__name__}: {exc}") or run
    week = result.get("week") if isinstance(result.get("week"), int) else None
    message = result.get("message") if isinstance(result.get("message"), str) else None
    log.info("%s finished: %s", label, message or "done")
    return runs.finish(run["id"], "ok", message, week, result) or run
