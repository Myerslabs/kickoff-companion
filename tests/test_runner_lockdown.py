"""Security review 2026-11-01: the notes, ask, season and writing runners cut Claude Code's built-in tools to web search and
fetch, load no MCP server and keep no session, using only the flags the installed command's --help lists."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.services import notes_task
from app.services.notes_task import ALLOWED_TOOLS, DENIED_TOOLS, lockdown_args

ROOT = Path(__file__).resolve().parent.parent
NEW_HELP = "Usage: claude\n  -p, --print\n  --output-format <format>\n  --tools <tools...>\n  --strict-mcp-config\n  --no-session-persistence\n"
OLD_HELP = "Usage: claude\n  -p, --print\n  --output-format <format>\n  --allowedTools <tools...>\n  --disallowedTools <tools...>\n"


@pytest.fixture(autouse=True)
def _fresh_cache():
    notes_task._help_cache.clear()
    yield
    notes_task._help_cache.clear()


def _with_help(monkeypatch: pytest.MonkeyPatch, text: str | None) -> None:
    monkeypatch.setattr(notes_task, "_read_help", lambda prefix: text)


def test_a_current_claude_gets_the_tool_list_and_both_hardening_flags(monkeypatch):
    _with_help(monkeypatch, NEW_HELP)
    assert asyncio.run(lockdown_args(["claude"])) == ["--tools", ALLOWED_TOOLS, "--strict-mcp-config", "--no-session-persistence"]


def test_an_older_claude_denies_the_file_and_shell_tools_by_name(monkeypatch):
    _with_help(monkeypatch, OLD_HELP)
    args = asyncio.run(lockdown_args(["claude"]))
    assert args == ["--disallowedTools", DENIED_TOOLS]
    assert {"Bash", "Edit", "Write", "Read"} <= set(DENIED_TOOLS.split(","))


def test_a_help_that_cannot_be_read_still_locks_the_tools_down(monkeypatch):
    _with_help(monkeypatch, None)
    args = asyncio.run(lockdown_args(["claude"]))
    assert args[:2] == ["--tools", ALLOWED_TOOLS]


def test_the_help_is_read_once_per_command(monkeypatch):
    calls: list[list[str]] = []
    monkeypatch.setattr(notes_task, "_read_help", lambda prefix: calls.append(prefix) or NEW_HELP)
    asyncio.run(lockdown_args(["claude"]))
    asyncio.run(lockdown_args(["claude"]))
    assert len(calls) == 1


def test_a_missing_command_gives_no_help(tmp_path):
    assert notes_task._read_help([str(tmp_path / "nope.exe")]) is None


def test_every_runner_adds_the_lockdown():
    for name in ("notes_task", "season_task", "writing", "ask"):
        text = (ROOT / "app" / "services" / f"{name}.py").read_text(encoding="utf-8")
        assert "await lockdown_args(prefix)" in text, f"{name} starts Claude Code without the lockdown"
