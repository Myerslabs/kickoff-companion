"""Every prompt, one after another (the Prompts phase, owner 2026-10-13: "I want to be able to do all of the prompts in
one CLI command or the scheduled commands, so it starts running automatically").

One queue walks the prompts in the season's order: the preseason load, the coaches, the roster costs, the school
history and facts, then this week's notes. Each step asks its own runner (app/services/season_task.py,
notes_task.py) to start, waits for it to finish, and records what came of it; a step that fails is recorded and the
next one still runs. "What is missing" (the default) skips a step whose data is loaded; "all" runs every step again.
One queue at a time. The command-line tool (app/prompts_cli.py), the Prompts page's button and the schedule's
catch-up all come through here, so they are the same run.

    Step(kind, label, start, poll, missing)
        start(all) -> awaitable status dict ({running, error} at least)
        poll() -> {running, ok, error, changed}
        missing() -> awaitable str | None: what is missing, in words, or None when nothing is
    PromptRuns(steps, command_found, clock)
      await start(all=False) -> status    refused with "error" while a queue runs or the command is not found
      status() -> {running, all, startedAt, finishedAt, commandFound, steps: [...]}
      await stop()
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger("kickoff.prompts")

POLL_SECONDS = 5.0
MAX_STEP_SECONDS = 2 * 3600  # a runner that never answers is given up on, so the queue never hangs the server

STATES = ("waiting", "skipped", "running", "done", "failed", "stopped")


def _iso(value: datetime | None) -> str | None:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z") if value else None


@dataclass
class Step:
    kind: str
    label: str
    start: Callable[[bool], Awaitable[dict[str, Any]]]
    poll: Callable[[], dict[str, Any]]
    missing: Callable[[], Awaitable[str | None]]
    state: str = "waiting"
    detail: str | None = None
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    changed: Any = None

    def reset(self) -> None:
        self.state, self.detail, self.error, self.started_at, self.finished_at, self.changed = "waiting", None, None, None, None, None

    def as_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "label": self.label, "state": self.state, "detail": self.detail, "error": self.error, "startedAt": _iso(self.started_at), "finishedAt": _iso(self.finished_at), "changed": self.changed}


@dataclass
class PromptRuns:
    steps: list[Step]
    command_found: Callable[[], bool]
    clock: Callable[[], datetime] = field(default_factory=lambda: (lambda: datetime.now(timezone.utc)))
    poll_seconds: float = POLL_SECONDS
    all: bool = False
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
    task: asyncio.Task[Any] | None = None

    @property
    def running(self) -> bool:
        return self.task is not None and not self.task.done()

    def status(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "all": self.all,
            "startedAt": _iso(self.started_at),
            "finishedAt": _iso(self.finished_at),
            "commandFound": bool(self.command_found()),
            "error": self.error,
            "steps": [s.as_dict() for s in self.steps],
            "done": sum(1 for s in self.steps if s.state in ("done", "skipped")),
            "failed": sum(1 for s in self.steps if s.state == "failed"),
            "of": len(self.steps),
        }

    async def start(self, all: bool = False) -> dict[str, Any]:  # noqa: A002 - the API's word
        if self.running:
            return {**self.status(), "error": "the prompts are already running"}
        if not self.command_found():
            self.error = "Claude Code's command was not found on the server computer, so nothing can run. Copy and paste each prompt instead."
            return {**self.status(), "error": self.error}
        self.all = bool(all)
        self.error = None
        self.started_at = self.clock()
        self.finished_at = None
        for step in self.steps:
            step.reset()
        self.task = asyncio.create_task(self._run_all())
        return self.status()

    async def stop(self) -> None:
        if self.task is not None and not self.task.done():
            self.task.cancel()
            try:
                await self.task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001 - stopping must never raise
                pass
        self.task = None

    async def _run_all(self) -> None:
        log.info("The prompts run started (%s).", "everything again" if self.all else "what is missing")
        try:
            for step in self.steps:
                await self._run_step(step)
        except asyncio.CancelledError:
            for step in self.steps:
                if step.state in ("waiting", "running"):
                    step.state = "stopped"
            raise
        finally:
            self.finished_at = self.clock()
            log.info("The prompts run finished: %d done, %d failed of %d.", sum(1 for s in self.steps if s.state == "done"), sum(1 for s in self.steps if s.state == "failed"), len(self.steps))

    async def _run_step(self, step: Step) -> None:
        step.started_at = self.clock()
        try:
            if not self.all:
                gap = await step.missing()
                if gap is None:
                    step.state, step.detail, step.finished_at = "skipped", "nothing missing", self.clock()
                    return
                step.detail = gap
            step.state = "running"
            status = await step.start(self.all)
            if not isinstance(status, dict):
                status = {}
            if status.get("error") and not status.get("running"):
                step.state, step.error, step.finished_at = "failed", str(status["error"]), self.clock()
                return
            waited = 0.0
            while True:
                await asyncio.sleep(self.poll_seconds)
                waited += self.poll_seconds
                result = step.poll()
                if not (isinstance(result, dict) and result.get("running")):
                    break
                if waited > MAX_STEP_SECONDS:
                    step.state, step.error, step.finished_at = "failed", "the run did not finish in time", self.clock()
                    return
            ok = bool(isinstance(result, dict) and result.get("ok"))
            step.state = "done" if ok else "failed"
            step.error = None if ok else str((result or {}).get("error") or "the run did not finish") if isinstance(result, dict) else "the run did not answer"
            step.changed = result.get("changed") if isinstance(result, dict) else None
            step.finished_at = self.clock()
        except asyncio.CancelledError:
            step.state, step.finished_at = "stopped", self.clock()
            raise
        except Exception as exc:  # noqa: BLE001 - one step must not stop the queue; logged with the traceback
            log.exception("The prompts step %s failed", step.kind)
            step.state, step.error, step.finished_at = "failed", f"{exc.__class__.__name__}: {exc}", self.clock()
        finally:
            log.info("Prompts step %s: %s%s", step.kind, step.state, f" ({step.error})" if step.error else (f" ({step.detail})" if step.detail else ""))
