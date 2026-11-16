"""Freeze wave F6 (2026-10-21): npm's claude.cmd shim resolved to node and the script, with the prompt on stdin (B7).
The wave's package, other systems and workflows left with ENH-26 (owner 2026-10-25: Windows only)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

from app.services import notes_task
from app.services.notes_task import PROMPT_LEAD, NotesRunner

ROOT = Path(__file__).resolve().parents[1]

SHIM = r"""@ECHO off
GOTO start
:find_dp0
SET dp0=%~dp0
EXIT /b
:start
SETLOCAL
CALL :find_dp0

IF EXIST "%dp0%\node.exe" (
  SET "_prog=%dp0%\node.exe"
) ELSE (
  SET "_prog=node"
  SET PATHEXT=%PATHEXT:;.JS;=;%
)

endLocal & goto #_undefined_# 2>NUL || title %COMSPEC% & "%_prog%"  "%dp0%\node_modules\@anthropic-ai\claude-code\cli.js" %*
"""


# --- the claude.cmd shim and the prompt on stdin (B7) -------------------------------------------------------------------------


def test_npms_shim_resolves_to_node_and_the_script(tmp_path: Path, monkeypatch):
    shim = tmp_path / "claude.cmd"
    shim.write_text(SHIM, encoding="utf-8")
    script = tmp_path / "node_modules" / "@anthropic-ai" / "claude-code" / "cli.js"
    script.parent.mkdir(parents=True)
    script.write_text("// cli\n", encoding="utf-8")
    monkeypatch.setattr(notes_task.shutil, "which", lambda name: "/usr/bin/node" if name == "node" else None)
    assert NotesRunner.command_args(str(shim)) == ["/usr/bin/node", str(script)], "node from the path when none sits beside the shim"
    beside = tmp_path / "node.exe"
    beside.write_bytes(b"MZ")
    assert NotesRunner.command_args(str(shim)) == [str(beside), str(script)], "the node beside the shim first, as the shim itself does"
    monkeypatch.setattr(notes_task.shutil, "which", lambda name: None)
    beside.unlink()
    assert NotesRunner.command_args(str(shim)) == [str(shim)], "no node to be found: the shim runs as it is"
    script.unlink()
    assert NotesRunner.command_args(str(shim)) == [str(shim)], "the script gone: the shim as it is"
    plain = tmp_path / "claude.exe"
    plain.write_bytes(b"MZ")
    assert NotesRunner.command_args(str(plain)) == [str(plain)]
    odd = tmp_path / "other.cmd"
    odd.write_text("@echo off\r\nsomething else\r\n", encoding="utf-8")
    assert NotesRunner.command_args(str(odd)) == [str(odd)]


def test_the_notes_runner_sends_the_prompt_on_stdin(tmp_path: Path, monkeypatch):
    calls: list = []

    class FakeProcess:
        def __init__(self) -> None:
            self.returncode: int | None = None
            self.given: bytes | None = None
            self.killed = False

        async def communicate(self, input: bytes | None = None):
            self.given = input
            self.returncode = 0
            return None, None

        async def wait(self) -> int:
            return self.returncode or 0

        def kill(self) -> None:
            self.killed = True

    fake = FakeProcess()

    async def spawn(*args, **kwargs):
        calls.append((args, kwargs))
        return fake

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    runner = NotesRunner(tmp_path / "data", tmp_path / "logs", who=lambda: None, season=2026)
    runner.log_dir.mkdir(parents=True)  # start() makes it before a run
    runner.started_at = datetime.now(timezone.utc)
    tool = tmp_path / "claude.exe"
    tool.write_bytes(b"MZ")
    prompt = "Write the notes.\n" + "x" * 20000  # longer than a cmd.exe line could carry
    asyncio.run(runner._run(str(tool), prompt, 526000600))
    args, kwargs = calls[0]
    assert list(args[:3]) == [str(tool), "-p", PROMPT_LEAD] and prompt not in args and "--output-format" in args
    assert kwargs["stdin"] is asyncio.subprocess.PIPE and fake.given == prompt.encode("utf-8")
    assert runner.exit_code == 0 and not fake.killed and runner.finished_at is not None
    assert runner.error and "no usable notes" in runner.error, "the fake wrote no answer, and that is said plainly"
    season = (ROOT / "app" / "services" / "season_task.py").read_text(encoding="utf-8")
    assert "stdin=asyncio.subprocess.PIPE" in season and "communicate(batch.prompt.encode" in season and "NotesRunner.command_args(executable)" in season and "PROMPT_LEAD" in season
