"""Ask about this page (FEAT-12): a question about the page the reader has open goes to Claude Code
on the server with the page's own text, and the answer comes back in plain words. The notes runner's way (app/services/
notes_task.py): an empty scratch folder, the prompt on stdin, web search the only tool; one question at a time, kept until
the next one so every device sees the last answer.

    AskRunner(data_dir, log_dir)
      await start(question, route, page_text, team, command) -> status
      status() -> {running, question, route, answer, error, startedAt, finishedAt}
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services import claude_signin
from app.services.notes_task import ALLOWED_TOOLS, PROMPT_LEAD, NotesRunner, lockdown_args, scratch_dir

log = logging.getLogger("kickoff.ask")

MAX_QUESTION = 500
MAX_PAGE = 30_000
MAX_ANSWER = 8_000
MAX_SECONDS = 6 * 60


def _iso(value: datetime | None) -> str | None:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z") if value else None


def build_prompt(question: str, route: str, page_text: str, team: str) -> str:
    return (
        f"You are answering a question about one page of a private college football second-screen app that follows {team}."
        f" The page open is \"{route}\"; its text is below, as the reader sees it.\n\n"
        "Answer the question in plain words, briefly: a few short paragraphs at most, no headings, no JSON. Work from the page"
        " first; search the web only when the question needs more than the page holds, and say so when you did. Never invent a"
        " number, a name or a quote; when the page and the web do not say, answer that.\n\n"
        f"The question: {question}\n\n"
        f"The page:\n```text\n{page_text}\n```\n"
    )


class AskRunner:
    def __init__(self, data_dir: Path, log_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.log_path = Path(log_dir) / "ask.log"
        self.task: asyncio.Task[Any] | None = None
        self.process: asyncio.subprocess.Process | None = None
        self.question: str | None = None
        self.route: str | None = None
        self.answer: str | None = None
        self.error: str | None = None
        self.started_at: datetime | None = None
        self.finished_at: datetime | None = None

    @property
    def running(self) -> bool:
        return self.task is not None and not self.task.done()

    def status(self) -> dict[str, Any]:
        return {"running": self.running, "question": self.question, "route": self.route, "answer": self.answer, "error": self.error,
                "startedAt": _iso(self.started_at), "finishedAt": _iso(self.finished_at)}

    async def start(self, question: Any, route: Any, page_text: Any, team: str, command: str) -> dict[str, Any]:
        words = " ".join(str(question or "").split())[:MAX_QUESTION]
        if not words:
            return {**self.status(), "error": "Ask a question first."}
        if self.running:
            return {**self.status(), "error": "Claude is still answering the last question."}
        resolved = NotesRunner.resolve_command(command)
        if resolved is None:
            return {**self.status(), "error": f"{command!r} was not found on the server computer, so nothing can answer here."}
        page = str(page_text or "").strip()[:MAX_PAGE]
        where = " ".join(str(route or "the page").split())[:80] or "the page"
        self.question, self.route, self.answer, self.error = words, where, None, None
        self.started_at, self.finished_at = datetime.now(timezone.utc), None
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.task = asyncio.create_task(self._run(resolved, build_prompt(words, where, page, team)))
        return self.status()

    async def _run(self, executable: str, prompt: str) -> None:
        prefix = NotesRunner.command_args(executable)
        args = [*prefix, "-p", PROMPT_LEAD, "--allowedTools", ALLOWED_TOOLS, "--output-format", "text", *await lockdown_args(prefix)]
        header = f"# ask, started {_iso(self.started_at)}\n"
        exit_code: int | None = None
        try:
            with self.log_path.open("w", encoding="utf-8") as handle:
                handle.write(header)
                handle.flush()
                self.process = await asyncio.create_subprocess_exec(*args, stdin=asyncio.subprocess.PIPE, stdout=handle, stderr=asyncio.subprocess.STDOUT, cwd=str(scratch_dir(self.data_dir)))
                try:
                    await asyncio.wait_for(self.process.communicate(prompt.encode("utf-8")), timeout=MAX_SECONDS)
                    exit_code = self.process.returncode
                except TimeoutError:
                    self.process.kill()
                    self.error = f"no answer after {MAX_SECONDS // 60} minutes"
                    exit_code = await self.process.wait()
        except (OSError, ValueError) as exc:
            self.error = f"could not start {executable}: {exc}"
        finally:
            self.process = None
            if exit_code == 0:
                claude_signin.succeeded()
            elif self.error is None and exit_code is not None:
                self.error = claude_signin.from_log(self.log_path) or f"the tool exited with code {exit_code}"  # 2026-11-15: signed out, said so
            if self.error is None:
                try:
                    text = self.log_path.read_text(encoding="utf-8", errors="replace").removeprefix(header).strip()
                except OSError as exc:
                    text = ""
                    self.error = f"the answer could not be read: {exc}"
                if text:
                    self.answer = text[:MAX_ANSWER]
                elif self.error is None:
                    self.error = "the tool finished without an answer"
            self.finished_at = datetime.now(timezone.utc)
            log.info("Ask about %s answered: %s", self.route, "yes" if self.answer else self.error)

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
