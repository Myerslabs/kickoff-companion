"""FEAT-18 the Claude Code wrapper (spec C.2 and C.9): the command line from the installed command's own --help, the JSON
result read, the model guard (only Opus, never a fallback), the preflight without modelUsage, the timeout, a missing
command. No real Claude Code runs: a fake runner answers."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from app.llm import claude_cli
from app.llm.claude_cli import ClaudeCli, ClaudeFailed, ClaudeMissing, build_args, parse_result

HELP = """Usage: claude [options] [command] [prompt]
  -p, --print   Print response and exit
  --output-format <format>
  --max-turns <turns>
  --model <model>
  --tools <tools...>
  --disallowedTools, --disallowed-tools <tools...>
  --strict-mcp-config
  --no-session-persistence
  --system-prompt <prompt>
  --system-prompt-file <file>
  --settings <file-or-json>
"""
OLD_HELP = "Usage: claude\n  -p, --print\n  --model <model>\n  --output-format <format>\n  --max-turns <n>\n  --disallowedTools <tools...>\n  --system-prompt <prompt>\n"


def result(text: str = '{"ok": 1}', models: dict | None = None, subtype: str = "success", is_error: bool = False) -> str:
    body = {"type": "result", "subtype": subtype, "is_error": is_error, "result": text, "num_turns": 1, "total_cost_usd": 0.42, "duration_ms": 31000}
    if models is not None:
        body["modelUsage"] = models
    return json.dumps(body)


OPUS = {"claude-opus-5-5": {"inputTokens": 30000, "outputTokens": 1800, "costUSD": 0.4}}


class Fake:
    def __init__(self, *answers: tuple[int, str, str] | Exception, help_text: str = HELP) -> None:
        self.answers = list(answers)
        self.help = help_text
        self.calls: list[tuple[list[str], bytes]] = []

    async def __call__(self, args: list[str], stdin: bytes, cwd: str, timeout: float) -> tuple[int, str, str]:
        if args[-1] == "--help":
            return 0, self.help, ""
        self.calls.append((args, stdin))
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


@pytest.fixture
def found(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(claude_cli, "find_command", lambda command="claude": ("C:/tools/claude.exe", "C:/tools"))


def ask(fake: Fake, tmp_path: Path):
    cli = ClaudeCli("claude", tmp_path, runner=fake)
    return asyncio.run(cli.ask("Be an analyst.", tmp_path / "system.md", "The pack."))


def test_the_command_line_has_every_flag_the_command_lists(tmp_path: Path):
    args = build_args(["claude"], HELP, tmp_path / "s.md", "text")
    joined = " ".join(args)
    assert args[:5] == ["claude", "-p", claude_cli.PROMPT_LEAD, "--model", "opus"]
    assert "--output-format json" in joined and "--max-turns 1" in joined
    assert args[args.index("--tools") + 1] == "", "no built-in tools"
    assert "--strict-mcp-config" in args and "--no-session-persistence" in args
    assert args[args.index("--system-prompt-file") + 1] == str(tmp_path / "s.md") and "--system-prompt" not in args
    assert json.loads(args[args.index("--settings") + 1]) == {"switchModelsOnFlag": False}, "a flagged request ends, never moves to another model"


def test_an_older_command_gets_only_the_flags_it_has():
    args = build_args(["claude"], OLD_HELP, Path("s.md"), "the text")
    assert args[args.index("--disallowedTools") + 1] == "*"
    assert args[args.index("--system-prompt") + 1] == "the text"
    assert "--strict-mcp-config" not in args and "--settings" not in args and "--tools" not in args


def test_a_command_that_cannot_drop_its_tools_is_refused():
    with pytest.raises(ClaudeFailed, match="cannot run without tools"):
        build_args(["claude"], "Usage: claude\n  -p\n  --system-prompt <p>\n", None, "x")
    with pytest.raises(ClaudeFailed, match="no system prompt"):
        build_args(["claude"], "Usage: claude\n  --tools <t>\n", None, "x")


def test_the_result_is_read_and_the_biggest_writer_is_the_model():
    r = parse_result(result(models={"claude-haiku-4-5": {"outputTokens": 12}, "claude-opus-5-5": {"outputTokens": 1800, "canonicalModel": "claude-opus-5-5"}}))
    assert r.text == '{"ok": 1}' and r.model == "claude-opus-5-5" and r.cost_usd == 0.42 and r.duration_ms == 31000


def test_a_run_that_did_not_succeed_fails_with_its_words():
    with pytest.raises(ClaudeFailed, match="error_max_turns"):
        parse_result(json.dumps({"type": "result", "subtype": "error_max_turns", "is_error": True, "errors": ["Reached max turns (1)"]}))
    with pytest.raises(ClaudeFailed, match="is_error"):
        parse_result(result(is_error=True, models=OPUS))
    with pytest.raises(ClaudeFailed, match="no JSON result: Invalid flag"):
        parse_result("", "Invalid flag --nope")
    with pytest.raises(ClaudeFailed, match="empty"):
        parse_result(result(text="  ", models=OPUS))


def test_an_opus_answer_is_kept(found, tmp_path: Path):
    fake = Fake((0, result(models=OPUS), ""))
    answer = ask(fake, tmp_path)
    assert answer.model == "claude-opus-5-5" and answer.text == '{"ok": 1}'
    args, stdin = fake.calls[0]
    assert stdin == b"The pack." and "--system-prompt-file" in args


def test_a_sonnet_answer_fails_loud_and_nothing_is_kept(found, tmp_path: Path):
    fake = Fake((0, result(models={"claude-sonnet-5-5": {"outputTokens": 1500}}), ""))
    with pytest.raises(ClaudeFailed, match="came from claude-sonnet-5-5, not Opus"):
        ask(fake, tmp_path)


def test_without_model_usage_a_preflight_asks_the_model(found, tmp_path: Path):
    fake = Fake((0, result(), ""), (0, result(text="claude-opus-5-5"), ""))
    assert ask(fake, tmp_path).model == "claude-opus-5-5"
    assert fake.calls[1][1] == claude_cli.PREFLIGHT.encode()
    fake = Fake((0, result(), ""), (0, result(text="claude-haiku-4-5"), ""))
    with pytest.raises(ClaudeFailed, match="not Opus"):
        ask(fake, tmp_path)


def test_a_nonzero_exit_and_a_timeout_fail(found, tmp_path: Path):
    with pytest.raises(ClaudeFailed, match="exited with 1"):
        ask(Fake((1, result(models=OPUS), "boom")), tmp_path)
    with pytest.raises(TimeoutError):
        ask(Fake(TimeoutError()), tmp_path)


def test_no_command_on_this_computer_is_its_own_case(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(claude_cli.NotesRunner, "resolve_command", staticmethod(lambda command: None))
    monkeypatch.setenv("PATH", "C:/one;C:/two")
    with pytest.raises(ClaudeMissing) as missing:
        ask(Fake(), tmp_path)
    assert missing.value.searched == "C:/one;C:/two"
