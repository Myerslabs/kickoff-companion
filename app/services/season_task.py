"""Running the season prompts with Claude Code (Phase 17 Part 3a): a queue of batches, one at a time. Like the notes
task (app/services/notes_task.py) the server starts Claude Code's command-line tool with web search only; each
batch's answer is read and saved the way a pasted one is, and a batch that fails is marked and skipped so the
others still save. One queue runs at a time; the Preseason page polls its status.

    SeasonRunner(log_dir)
      start(kind, batches, command)   batches: [Batch(key, prompt, save)], save(answer text) -> (saved, error, warnings)
      status(command)                 {running, kind, batches: [{key, state, error, warnings, startedAt, finishedAt}]}
      stop()
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.notes_task import ALLOWED_TOOLS, MAX_RUN_SECONDS, NotesRunner

log = logging.getLogger("kickoff.season")


def _iso(value: datetime | None) -> str | None:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z") if value else None


@dataclass
class Batch:
    key: str
    prompt: str
    save: Callable[[str], tuple[bool, str | None, list[str]]]
    state: str = "waiting"  # waiting, running, saved, failed, stopped
    error: str | None = None
    warnings: list[str] = field(default_factory=list)
    started_at: datetime | None = None
    finished_at: datetime | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"key": self.key, "state": self.state, "error": self.error, "warnings": list(self.warnings), "startedAt": _iso(self.started_at), "finishedAt": _iso(self.finished_at)}


class SeasonRunner:
    def __init__(self, log_dir: Path, cwd: Path | None = None, clock: Callable[[], datetime] | None = None) -> None:
        self.log_dir = Path(log_dir)
        self.cwd = cwd
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self.kind: str | None = None
        self.batches: list[Batch] = []
        self.task: asyncio.Task[Any] | None = None
        self.process: asyncio.subprocess.Process | None = None
        self.error: str | None = None

    @property
    def running(self) -> bool:
        return self.task is not None and not self.task.done()

    def status(self, command: str) -> dict[str, Any]:
        resolved = NotesRunner.resolve_command(command)
        return {
            "command": command,
            "commandFound": resolved is not None,
            "running": self.running,
            "kind": self.kind,
            "error": self.error,
            "batches": [b.as_dict() for b in self.batches],
            "done": sum(1 for b in self.batches if b.state in ("saved", "failed", "stopped")),
            "of": len(self.batches),
        }

    def log_path(self, kind: str, key: str) -> Path:
        safe = re.sub(r"[^A-Za-z0-9]+", "-", key).strip("-")[:60] or "batch"
        return self.log_dir / f"season-{kind}-{safe}.log"

    async def start(self, kind: str, batches: list[Batch], command: str) -> dict[str, Any]:
        if self.running:
            return {**self.status(command), "error": f"the {self.kind} run is still going"}
        resolved = NotesRunner.resolve_command(command)
        if resolved is None:
            self.error = f"{command!r} was not found. Install Claude Code's command-line tool, or set its full path in Settings."
            return self.status(command)
        if not batches:
            return {**self.status(command), "error": "nothing to run"}
        self.kind = kind
        self.batches = batches
        self.error = None
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.task = asyncio.create_task(self._run_all(resolved, kind))
        return self.status(command)

    async def _run_all(self, executable: str, kind: str) -> None:
        log.info("Season %s run started: %d batches", kind, len(self.batches))
        for batch in self.batches:
            if batch.state != "waiting":
                continue
            batch.state = "running"
            batch.started_at = self._clock()
            try:
                text = await self._run_one(executable, kind, batch)
                if text is None:
                    batch.state = "failed"
                else:
                    saved, error, warnings = batch.save(text)
                    batch.warnings = warnings
                    batch.state = "saved" if saved else "failed"
                    batch.error = None if saved else (error or "the answer could not be saved")
            except asyncio.CancelledError:
                batch.state = "stopped"
                raise
            except Exception as exc:  # noqa: BLE001 - one batch must not stop the queue; logged with the traceback
                log.exception("Season %s batch %s failed", kind, batch.key)
                batch.state = "failed"
                batch.error = f"{exc.__class__.__name__}: {exc}"
            finally:
                batch.finished_at = self._clock()
            log.info("Season %s batch %s: %s%s", kind, batch.key, batch.state, f" ({batch.error})" if batch.error else "")
        log.info("Season %s run finished: %d saved of %d", kind, sum(1 for b in self.batches if b.state == "saved"), len(self.batches))

    async def _run_one(self, executable: str, kind: str, batch: Batch) -> str | None:
        """The tool's answer, or None with batch.error set."""
        path = self.log_path(kind, batch.key)
        header = f"# season {kind} batch {batch.key}, started {_iso(batch.started_at)}\n"
        args = [executable, "-p", batch.prompt, "--allowedTools", ALLOWED_TOOLS, "--output-format", "text"]
        try:
            with path.open("w", encoding="utf-8") as handle:
                handle.write(header)
                handle.flush()
                self.process = await asyncio.create_subprocess_exec(*args, stdout=handle, stderr=asyncio.subprocess.STDOUT, cwd=str(self.cwd) if self.cwd else None)
                try:
                    code = await asyncio.wait_for(self.process.wait(), timeout=MAX_RUN_SECONDS)
                except TimeoutError:
                    self.process.kill()
                    await self.process.wait()
                    batch.error = f"stopped after {MAX_RUN_SECONDS // 60} minutes without finishing"
                    return None
        except (OSError, ValueError) as exc:
            batch.error = f"could not start {executable}: {exc}"
            return None
        finally:
            self.process = None
        if code != 0:
            batch.error = f"the tool exited with code {code}; see {path.name}"
            return None
        try:
            return path.read_text(encoding="utf-8", errors="replace").removeprefix(header)
        except OSError as exc:
            batch.error = f"the tool's answer could not be read: {exc}"
            return None

    async def stop(self) -> None:
        if self.process is not None:
            try:
                self.process.kill()
            except ProcessLookupError:
                pass
        if self.task is not None and not self.task.done():
            self.task.cancel()
            try:
                await self.task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001 - shutdown must not raise
                pass
        for batch in self.batches:
            if batch.state in ("waiting", "running"):
                batch.state = "stopped"
