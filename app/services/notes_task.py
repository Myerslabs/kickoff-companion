"""The weekly notes task, run from the app (owner question 2026-09-23: "Can it be called from the
app?"). The server runs on the same desktop as Claude Code, so a button can start the command-line
tool with the notes prompt. One run at a time, the output goes to `logs/notes-<game_id>.log`, and the
status is readable while it runs. The app never calls an AI itself: the tool does the work.

Public release Phase 6: the tool gets the same prompt as the copy-and-paste path (app/services/notes_paste.py,
editable in Settings) with web search only, and its answer is read and saved the same way, so a pasted
answer and a tool's answer land in `data/notes/<game_id>.json` through one reader. The button shows only
where the command is found."""

from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services import notes_paste

log = logging.getLogger("kickoff.notes")

LOG_TAIL_LINES = 40
MAX_RUN_SECONDS = 20 * 60
ALLOWED_TOOLS = "WebSearch,WebFetch"  # the tool researches and answers; the app writes the file


def scratch_dir(data_dir: Path) -> Path:
    """An empty folder for the tool to run in (Phase 18.1): it starts with nothing around it to read, not the project.
    Final pass: under the system's temp folder, never under the install, so a checkout's own CLAUDE.md (a parent of
    data/) is not read into every run; `data_dir` only names the folder."""
    path = Path(tempfile.gettempdir()) / "kickoff-companion" / f"ai-scratch-{abs(hash(str(Path(data_dir).resolve()))) % 100000:05d}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z") if value else None


class NotesRunner:
    def __init__(self, data_dir: Path, log_dir: Path, who: Any = None, season: int | None = None, tz: Any = None) -> None:
        """`who` returns the team identity (app/services/identity.py) the prompt names; `tz` dates the kickoff."""
        self.who = who
        self.season = season
        self.tz = tz
        self.data_dir = Path(data_dir)
        self.notes_dir = self.data_dir / "notes"
        self.log_dir = Path(log_dir)
        self.process: asyncio.subprocess.Process | None = None
        self.task: asyncio.Task[Any] | None = None
        self.game_id: int | None = None
        self.started_at: datetime | None = None
        self.finished_at: datetime | None = None
        self.exit_code: int | None = None
        self.error: str | None = None
        self.warnings: list[str] = []
        self.saved = False
        self.command: str | None = None
        self.mode = "full"  # "full" notes, or "injuries" only (Phase 18.7: merges the report into the notes already there)
        self.changed: bool | None = None  # did the saved answer differ from what was there
        self.model: str | None = None  # CLAUDE_LOOKUP_MODEL from .env for the small runs; None: the tool's own default

    # --- the prompt ------------------------------------------------------------------------------------

    @property
    def prompt_path(self) -> Path:
        return notes_paste.prompt_path(self.data_dir)

    def build_prompt(self, game: dict[str, Any], mode: str = "full") -> str:
        who = self.who() if callable(self.who) else None
        if mode == "injuries":
            return notes_paste.build_injury_prompt(who, game, self.season, self.tz)
        return notes_paste.build_prompt(self.data_dir, who, game, self.season, self.tz)

    # --- the command ------------------------------------------------------------------------------------

    @staticmethod
    def resolve_command(command: str) -> str | None:
        """The executable for the configured command: a full path that exists, or a name on PATH."""
        candidate = Path(command)
        if candidate.is_file():
            return str(candidate)
        return shutil.which(command)

    @property
    def running(self) -> bool:
        return self.task is not None and not self.task.done()

    def log_path(self, game_id: int) -> Path:
        return self.log_dir / f"notes-{game_id}.log"

    def _log_tail(self, game_id: int | None) -> list[str]:
        if game_id is None:
            return []
        path = self.log_path(game_id)
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return []
        return lines[-LOG_TAIL_LINES:]

    def status(self, command: str) -> dict[str, Any]:
        resolved = self.resolve_command(command)
        written = self.game_id is not None and (self.notes_dir / f"{self.game_id}.json").is_file()
        return {
            "command": command,
            "commandFound": resolved is not None,
            "commandPath": resolved,
            "running": self.running,
            "gameId": self.game_id,
            "startedAt": _iso(self.started_at),
            "finishedAt": _iso(self.finished_at),
            "exitCode": self.exit_code,
            "mode": self.mode,
            "changed": self.changed,
            "error": self.error,
            "warnings": list(self.warnings),
            "fileWritten": bool(written and self.saved),
            "logTail": self._log_tail(self.game_id),
            "promptFile": str(self.prompt_path),
        }

    async def start(self, game: dict[str, Any], command: str, mode: str = "full", model: str | None = None) -> dict[str, Any]:
        """Start one run. Refused while another runs or when the command is missing."""
        game_id = game.get("gameId")
        if not isinstance(game_id, int):
            return {**self.status(command), "error": "no game id"}
        if self.running:
            return {**self.status(command), "error": f"a run for game {self.game_id} is still going"}
        resolved = self.resolve_command(command)
        if resolved is None:
            self.error = f"{command!r} was not found. Install Claude Code's command-line tool, or set its full path in Settings."
            return self.status(command)
        prompt = self.build_prompt(game, mode)
        self.mode = mode
        self.model = model if mode == "injuries" else None
        self.changed = None
        self.game_id = game_id
        self.started_at = _now()
        self.finished_at = None
        self.exit_code = None
        self.error = None
        self.warnings = []
        self.saved = False
        self.command = resolved
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.task = asyncio.create_task(self._run(resolved, prompt, game_id))
        return self.status(command)

    async def _run(self, executable: str, prompt: str, game_id: int) -> None:
        args = [executable, "-p", prompt, "--allowedTools", ALLOWED_TOOLS, "--output-format", "text"]
        if self.model:
            args += ["--model", self.model]
        log.info("Notes task started for game %s with %s", game_id, executable)
        header = f"# notes task for game {game_id}, started {_iso(self.started_at)}\n"
        path = self.log_path(game_id)
        try:
            with path.open("w", encoding="utf-8") as handle:
                handle.write(header)
                handle.flush()
                self.process = await asyncio.create_subprocess_exec(*args, stdout=handle, stderr=asyncio.subprocess.STDOUT, cwd=str(scratch_dir(self.data_dir)))
                try:
                    self.exit_code = await asyncio.wait_for(self.process.wait(), timeout=MAX_RUN_SECONDS)
                except TimeoutError:
                    self.process.kill()
                    self.error = f"stopped after {MAX_RUN_SECONDS // 60} minutes without finishing"
                    self.exit_code = await self.process.wait()
        except (OSError, ValueError) as exc:
            self.error = f"could not start {executable}: {exc}"
            log.warning("Notes task failed to start: %s", exc)
        finally:
            self.process = None
            if self.error is None and self.exit_code not in (0, None):
                self.error = f"the tool exited with code {self.exit_code}"
            if self.error is None:
                self._save_answer(path, header, game_id)
            self.finished_at = _now()
            log.info("Notes task for game %s finished: exit %s, %s", game_id, self.exit_code, "notes saved" if self.saved else f"not saved ({self.error})")

    def _save_answer(self, path: Path, header: str, game_id: int) -> None:
        """Read the tool's answer from its log the way a pasted one is read, and save it."""
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            self.error = f"the tool's answer could not be read: {exc}"
            return
        reading = notes_paste.read_answer(text.removeprefix(header), game_id)
        self.warnings = reading.warnings
        if reading.notes is None:
            self.error = f"the tool finished but its answer had no usable notes: {reading.error} See the log."
            return
        try:
            if self.mode == "injuries":
                self.changed = notes_paste.merge_availability(self.data_dir, game_id, reading.notes)
            else:
                notes_paste.save_notes(self.data_dir, game_id, reading.notes)
        except notes_paste.NotesUnreadable as exc:
            self.error = f"the injury report was not merged: {exc}"
            return
        except OSError as exc:
            self.error = f"the notes could not be saved: {exc}"
            return
        self.saved = True

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
