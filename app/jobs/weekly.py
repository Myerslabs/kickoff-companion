"""The weekly runner (Feature Set v2, spec 0.2): every job in order, A then B then C, each Sunday from 06:00 local,
from the server's housekeeping loop (app/maintenance.py, the hourly slow jobs, never inside a game window).

When it is due:
  - a job that has never finished well this season makes the run due at once (so a new install, or a new job
    added by a later phase, does not wait for Sunday);
  - otherwise once a week: the latest Sunday 06:00 at or before now is the slot, and a run is due when no
    weekly run has finished well since that slot;
  - a failed run is tried again RETRY_HOURS after it started, not every hour; the retry runs only the jobs that have not
    finished well since the week's slot (the bug round, 2026-11-15).

One run at a time, the weekly run or one job: start() records the run and hands it back at once (the answer and the
command line poll it by id), and the work goes on in the background.

    python -m app.jobs.weekly [--season 2026] [--url ...]

    WeeklyJobs(runs, season, jobs)    jobs: {name: work} in run order
      due(now) -> bool
      start(name) -> run                 JobBusy while another runs, KeyError for an unknown job
      await run(name="weekly") -> run    start() and wait (the housekeeping loop, the command without a server)
      running, status()
"""

from __future__ import annotations

import asyncio
import logging
import sys
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from app.jobs import DONE, JobFailed, JobRuns, run_job

log = logging.getLogger("kickoff.jobs.weekly")

NAME = "weekly"
SLOT_WEEKDAY = 6  # Sunday (Monday is 0)
SLOT_HOUR = 6
RETRY_HOURS = 3


class JobBusy(Exception):
    """Another run is going; its record is the argument."""


def slot_start(now: datetime) -> datetime:
    """The latest Sunday 06:00 (in now's own zone) at or before `now`."""
    back = (now.weekday() - SLOT_WEEKDAY) % 7
    slot = (now - timedelta(days=back)).replace(hour=SLOT_HOUR, minute=0, second=0, microsecond=0)
    return slot if slot <= now else slot - timedelta(days=7)


def _started(run: dict[str, Any] | None) -> datetime | None:
    if not run or not isinstance(run.get("startedAt"), str):
        return None
    try:
        when = datetime.fromisoformat(run["startedAt"])
    except ValueError:
        return None
    return when if when.tzinfo is not None else None


class WeeklyJobs:
    def __init__(
        self,
        runs: JobRuns,
        season: int,
        jobs: dict[str, Callable[[], Awaitable[dict[str, Any]]]],
        *,
        lean: Callable[[], bool] | None = None,
        lean_every: dict[str, timedelta] | None = None,
    ) -> None:
        self.runs = runs
        self.season = season
        self.jobs = dict(jobs)
        self.lean = lean  # the Free profile (Kickoff Companion 2.0): the jobs named in lean_every run less often
        self.lean_every = dict(lean_every or {})
        self.current: dict[str, Any] | None = None
        self._task: asyncio.Task[Any] | None = None

    def _lean(self) -> bool:
        if self.lean is None:
            return False
        try:
            return bool(self.lean())
        except Exception:  # noqa: BLE001 - the plan unreadable: the job runs as on a paid key, the calls stay paced
            log.warning("The weekly run could not read the plan; every job runs this week", exc_info=True)
            return False

    @property
    def running(self) -> bool:
        return self.current is not None

    def names(self) -> list[str]:
        return [NAME, *self.jobs]

    def due(self, now: datetime) -> bool:
        if self.running:
            return False
        last = self.runs.last(NAME, self.season)
        last_try = _started(last)
        retry_ok = last_try is None or (last or {}).get("status") == "ok" or now - last_try >= timedelta(hours=RETRY_HOURS)
        if any(all(self.runs.last(name, self.season, status) is None for status in DONE) for name in self.jobs):
            return retry_ok
        slot = slot_start(now)
        last_ok = _started(self.runs.last(NAME, self.season, "ok"))
        if last_ok is not None and last_ok >= slot:
            return False
        return last_try is None or last_try < slot or retry_ok

    async def _all(self) -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        slot = slot_start(datetime.now().astimezone())
        for name, work in self.jobs.items():
            # the bug round (owner 2026-11-15, "Retry the failed job only"): a job that finished well since this week's slot
            # is not run again when the run is retried for another (Talent Edge's 15,800 players and the map's replay were
            # redone every three hours while the Circle of Blame waited for Claude Code's sign-in)
            done = self.runs.last(name, self.season, "ok")
            when = _started(done)
            if done is not None and when is not None and when >= slot:
                results.append({"job": name, "id": done.get("id"), "status": "ok", "message": f"{done.get('message') or 'ok'} (done earlier this week)", "week": done.get("week"), "kept": True})
                continue
            every = self.lean_every.get(name)
            if every is not None and done is not None and when is not None and self._lean() and datetime.now(timezone.utc) - when < every:
                days = every.days
                results.append({"job": name, "id": done.get("id"), "status": "ok", "message": f"{done.get('message') or 'ok'} (kept: on a Free key it is rebuilt every {days} days)", "week": done.get("week"), "kept": True})
                continue
            run = await run_job(self.runs, name, self.season, work)
            results.append({"job": name, "id": run.get("id"), "status": run.get("status"), "message": run.get("message"), "week": run.get("week")})
        summary = "; ".join(f"{r['job']}: {r['message'] or r['status']}" for r in results)
        failed = [r for r in results if r["status"] not in DONE]  # a skipped job (no Claude Code here) is not a failure
        if failed:
            raise JobFailed(f"{len(failed)} of {len(results)} job{'s' if len(results) != 1 else ''} failed. {summary}")
        week = next((r["week"] for r in results if isinstance(r["week"], int)), None)
        return {"week": week, "message": summary, "jobs": results}

    def start(self, name: str = NAME, **options: Any) -> dict[str, Any]:
        """`options` go to one job's own work (FEAT-18's Regenerate: force=True); the weekly run takes none."""
        if self.current is not None:
            raise JobBusy(self.current)
        if name == NAME:
            work: Callable[[], Awaitable[dict[str, Any]]] = self._all
        elif name in self.jobs:
            job = self.jobs[name]
            work = (lambda: job(**options)) if options else job
        else:
            raise KeyError(name)
        run = self.runs.start(name, self.season)
        self.current = run
        self._task = asyncio.create_task(self._execute(name, work, run))
        return run

    async def _execute(self, name: str, work: Callable[[], Awaitable[dict[str, Any]]], run: dict[str, Any]) -> None:
        try:
            await run_job(self.runs, name, self.season, work, run)
        finally:
            self.current = None

    async def run(self, name: str = NAME) -> dict[str, Any]:
        run = self.start(name)
        if self._task is not None:
            await self._task
        return self.runs.get(run["id"]) or run

    def status(self) -> dict[str, Any]:
        return {"jobs": self.runs.status(), "running": self.current.get("job") if self.current else None, "runningId": self.current.get("id") if self.current else None, "schedule": "Sundays from 6 AM"}


if __name__ == "__main__":
    from app.jobs.cli import main

    raise SystemExit(main(NAME, sys.argv[1:]))
