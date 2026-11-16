"""Claude Code for one analysis call with no tools (FEAT-18, Circle of Blame; spec C.2): Opus, the answer as JSON, the model
that answered checked before anything is kept. Every flag lives here.

The command is found the way the notes and writing runners find it (a configured name or path, then `claude.cmd` on
Windows) and run through `NotesRunner.command_args` (npm's shim read, node run on the script). Flags confirmed against Claude
Code's CLI reference (2026-10-30): `-p`, `--model`, `--output-format json`, `--max-turns`, `--tools ""` (no built-in tools),
`--strict-mcp-config` (no MCP servers), `--no-session-persistence`, `--system-prompt-file` (replaces the default prompt),
`--settings '{"switchModelsOnFlag": false}'` (a flagged request ends as an error instead of moving to another model). The
installed command's own `--help` is read once and only the optional flags it lists are passed; a command that cannot run
without tools or take a system prompt is refused, never run with them.

The JSON result (`type` "result"): `subtype` "success" and `is_error` false, else the run failed; `result` is the reply;
`modelUsage` is keyed by the model name, each entry with `outputTokens` and, in newer versions, `canonicalModel`. The model
that wrote the most is the one that answered; it must be an Opus model or the call fails (never a fallback). Without
`modelUsage`, a one-line preflight asks the model for its own id.

    MODEL, TIMEOUT_S
    ClaudeMissing(searched)            the command is not on this computer: a skip, not a failure (owner 2026-10-30)
    ClaudeFailed(message, stdout, stderr)
    find_command(command)              (executable | None, the PATH searched)
    build_args(prefix, help_text, system_file, system_text)   the command line
    parse_result(stdout)               ClaudeResult, or ClaudeFailed
    is_opus(model)
    ClaudeCli(command, cwd, runner)    .ask(system_text, system_file, prompt) -> ClaudeResult (the model checked)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.services import claude_signin
from app.services.notes_task import PROMPT_LEAD, NotesRunner

log = logging.getLogger("kickoff.claude_cli")

MODEL = "opus"  # the alias for the newest Opus model (spec C.2)
TIMEOUT_S = 300
HELP_TIMEOUT_S = 60
NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW: no console flashes behind the tray
NO_SWITCH = json.dumps({"switchModelsOnFlag": False})
PREFLIGHT = "Reply with your exact model id and nothing else."


class ClaudeMissing(Exception):
    def __init__(self, searched: str) -> None:
        super().__init__("Claude Code isn't on this computer")
        self.searched = searched


class ClaudeFailed(Exception):
    def __init__(self, message: str, stdout: str = "", stderr: str = "") -> None:
        super().__init__(message)
        self.stdout = stdout
        self.stderr = stderr


@dataclass
class ClaudeResult:
    text: str
    model: str | None
    models: dict[str, Any] = field(default_factory=dict)
    stdout: str = ""
    stderr: str = ""
    cost_usd: float | None = None
    duration_ms: int | None = None


Runner = Callable[[list[str], bytes, str, float], Awaitable[tuple[int, str, str]]]


def find_command(command: str = "claude") -> tuple[str | None, str]:
    """The executable for `command` (a full path or a name on PATH; `claude.cmd` too on Windows), and the PATH searched."""
    searched = os.environ.get("PATH", "")
    for name in (command, "claude.cmd") if sys.platform == "win32" and command == "claude" else (command,):
        found = NotesRunner.resolve_command(name)
        if found:
            return found, searched
    return None, searched


def has_flag(help_text: str, flag: str) -> bool:
    return any(token.strip(",[]") == flag for token in help_text.split())


def build_args(prefix: list[str], help_text: str, system_file: Path | None, system_text: str) -> list[str]:
    """The command line: print mode, Opus, JSON, one turn, no tools, the system prompt; optional flags only where listed."""
    args = [*prefix, "-p", PROMPT_LEAD, "--model", MODEL, "--output-format", "json", "--max-turns", "1"]
    if has_flag(help_text, "--tools"):
        args += ["--tools", ""]
    elif has_flag(help_text, "--disallowedTools"):
        args += ["--disallowedTools", "*"]
    else:
        raise ClaudeFailed("This Claude Code cannot run without tools (no --tools or --disallowedTools in its --help); update it with `claude update`.")
    if has_flag(help_text, "--strict-mcp-config"):
        args.append("--strict-mcp-config")
    if has_flag(help_text, "--no-session-persistence"):
        args.append("--no-session-persistence")
    if system_file is not None and has_flag(help_text, "--system-prompt-file"):
        args += ["--system-prompt-file", str(system_file)]
    elif has_flag(help_text, "--system-prompt"):
        args += ["--system-prompt", system_text]
    else:
        raise ClaudeFailed("This Claude Code takes no system prompt (no --system-prompt in its --help); update it with `claude update`.")
    if has_flag(help_text, "--settings"):
        args += ["--settings", NO_SWITCH]
    return args


def is_opus(model: str | None) -> bool:
    return isinstance(model, str) and "opus" in model.lower()


def _result_object(stdout: str) -> dict[str, Any] | None:
    text = stdout.strip()
    candidates = [text] + [line for line in reversed(text.splitlines()) if line.strip().startswith("{")]
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(value, dict) and value.get("type") == "result":
            return value
    return None


def parse_result(stdout: str, stderr: str = "") -> ClaudeResult:
    """Claude Code's JSON result: the reply and the model that wrote it. A run that did not succeed is ClaudeFailed."""
    result = _result_object(stdout)
    if result is None:
        tail = (stderr or stdout).strip()[-600:]
        raise ClaudeFailed(f"Claude Code gave no JSON result{f': {tail}' if tail else ''}", stdout, stderr)
    subtype = result.get("subtype")
    if subtype != "success" or result.get("is_error") is True:
        errors = result.get("errors") if isinstance(result.get("errors"), list) else []
        why = "; ".join(str(e) for e in errors[:3]) or str(result.get("result") or result.get("stop_reason") or "")
        raise ClaudeFailed(f"Claude Code stopped ({subtype or 'no subtype'}{', is_error' if result.get('is_error') else ''}){f': {why}' if why else ''}", stdout, stderr)
    text = result.get("result")
    if not isinstance(text, str) or not text.strip():
        raise ClaudeFailed("Claude Code's result was empty", stdout, stderr)
    usage = result.get("modelUsage") if isinstance(result.get("modelUsage"), dict) else {}
    model = None
    most = -1
    for name, entry in usage.items():
        row = entry if isinstance(entry, dict) else {}
        out = row.get("outputTokens") if isinstance(row.get("outputTokens"), int) else 0
        label = row.get("canonicalModel") if isinstance(row.get("canonicalModel"), str) and row.get("canonicalModel") else name
        if out > most:
            most, model = out, label
    cost = result.get("total_cost_usd")
    took = result.get("duration_ms")
    return ClaudeResult(text=text, model=model, models=usage, stdout=stdout, stderr=stderr, cost_usd=cost if isinstance(cost, int | float) else None, duration_ms=took if isinstance(took, int) else None)


async def run_process(args: list[str], stdin: bytes, cwd: str, timeout: float) -> tuple[int, str, str]:
    """Run the command with the prompt on stdin; (exit code, stdout, stderr). A timeout kills it and raises TimeoutError."""
    process = await asyncio.create_subprocess_exec(*args, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, cwd=cwd, creationflags=NO_WINDOW)
    try:
        out, err = await asyncio.wait_for(process.communicate(stdin), timeout=timeout)
    except TimeoutError:
        process.kill()
        await process.wait()
        raise
    return process.returncode or 0, out.decode("utf-8", errors="replace"), err.decode("utf-8", errors="replace")


class ClaudeCli:
    """One configured Claude Code. `runner` is replaced in tests."""

    def __init__(self, command: str, cwd: Path, runner: Runner | None = None, timeout: float = TIMEOUT_S) -> None:
        self.command = command or "claude"
        self.cwd = Path(cwd)
        self.runner = runner or run_process
        self.timeout = timeout
        self._help: tuple[str, str] | None = None  # (executable, its --help)

    def prefix(self) -> list[str]:
        executable, searched = find_command(self.command)
        if executable is None:
            raise ClaudeMissing(searched)
        return NotesRunner.command_args(executable)

    async def help_text(self, prefix: list[str]) -> str:
        if self._help is not None and self._help[0] == prefix[-1]:
            return self._help[1]
        try:
            code, out, err = await self.runner([*prefix, "--help"], b"", str(self.cwd), HELP_TIMEOUT_S)
        except TimeoutError as exc:
            raise ClaudeFailed(f"`claude --help` took more than {HELP_TIMEOUT_S} s") from exc
        text = out + "\n" + err
        if code != 0 and "--model" not in text:
            raise ClaudeFailed(f"`claude --help` failed (exit {code}): {err.strip()[-400:]}", out, err)
        self._help = (prefix[-1], text)
        return text

    async def ask(self, system_text: str, system_file: Path | None, prompt: str) -> ClaudeResult:
        """One call; the model that answered is checked. Raises ClaudeMissing, ClaudeFailed or TimeoutError."""
        prefix = self.prefix()
        args = build_args(prefix, await self.help_text(prefix), system_file, system_text)
        code, out, err = await self.runner(args, prompt.encode("utf-8"), str(self.cwd), self.timeout)
        try:
            result = parse_result(out, err)
            if code != 0:
                raise ClaudeFailed(f"Claude Code exited with {code}", out, err)
        except ClaudeFailed as exc:
            # 2026-11-15: a signed-out Claude Code ("Failed to authenticate: ...") says so in plain words
            signed_out = claude_signin.failed(f"{out}\n{err}")
            if signed_out:
                raise ClaudeFailed(signed_out, out, err) from exc
            raise
        claude_signin.succeeded()
        if result.model is None:
            result.model = await self.preflight(prefix, await self.help_text(prefix), system_file, system_text)
        if not is_opus(result.model):
            raise ClaudeFailed(f"The answer came from {result.model or 'an unnamed model'}, not Opus; nothing was kept", out, err)
        return result

    async def preflight(self, prefix: list[str], help_text: str, system_file: Path | None, system_text: str) -> str | None:
        """Without modelUsage: ask the model its own id (spec C.2)."""
        args = build_args(prefix, help_text, None, "Answer in one line.")
        code, out, err = await self.runner(args, PREFLIGHT.encode("utf-8"), str(self.cwd), HELP_TIMEOUT_S)
        if code != 0:
            raise ClaudeFailed(f"The model check failed (exit {code})", out, err)
        answer = parse_result(out, err)
        return answer.model or answer.text.strip().splitlines()[0][:80]
