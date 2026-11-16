"""Claude Code signed out (owner 2026-11-15, "Yes, fix it first"): his reports of 2026-11-11 and 2026-11-14 read "the tool
exited with code 1" while Claude Code's own sign-in on the server computer had expired. A failed run's output is read for
Claude Code's sign-in words; the run's error says so in plain words, the server remembers it until a run gets through, and
every answer carries it (meta.claudeSignedOut) for the To do and the Data status card. No real Claude Code runs: fake
processes write what Claude Code wrote into the logs of 2026-11-10 to 2026-11-14."""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.api.envelope import envelope
from app.llm import claude_cli
from app.llm.claude_cli import ClaudeCli, ClaudeFailed
from app.services import claude_signin
from app.services import writing as W
from app.services.ask import AskRunner
from app.services.notes_task import NotesRunner

ROOT = Path(__file__).resolve().parents[1]
REAL = "Failed to authenticate: OAuth session expired and could not be refreshed"  # logs/writing-*.log, 2026-11-10 to 2026-11-14
HELP = "Usage: claude\n  -p, --print\n  --model <model>\n  --output-format <format>\n  --max-turns <n>\n  --tools <tools...>\n  --system-prompt <prompt>\n"
OPUS = {"claude-opus-5-5": {"outputTokens": 900}}


@pytest.fixture(autouse=True)
def fresh():
    claude_signin.reset()
    yield
    claude_signin.reset()


@pytest.mark.parametrize(
    "text",
    [REAL, "OAuth token has expired. Please obtain a new token or refresh your existing token.", "Invalid API key · Please run /login", "Not logged in · Please run /login", '{"type":"error","error":{"type":"authentication_error"}}'],
)
def test_claude_codes_own_sign_in_words_are_known(text):
    assert claude_signin.is_sign_in_failure(f"# trivia for 1, started 2026-11-14T18:33:58Z\n{text}\n")


@pytest.mark.parametrize("text", ["", "Error: Reached max turns (1)", "API Error: 529 Overloaded", None, 42, ["Failed to authenticate"], {"error": REAL}])
def test_other_failures_and_wrong_types_are_not_a_sign_in(text):
    assert not claude_signin.is_sign_in_failure(text)
    assert claude_signin.failed(text) is None and claude_signin.signed_out_since() is None


def test_only_the_tail_is_read_so_an_answer_that_mentions_a_sign_in_never_counts():
    assert not claude_signin.is_sign_in_failure("Invalid API key, the story said.\n" + "x" * claude_signin.TAIL)


def test_a_sign_in_failure_is_remembered_until_a_run_gets_through():
    assert claude_signin.failed(REAL) == claude_signin.SIGNED_OUT
    since = claude_signin.signed_out_since()
    assert since and since.endswith("Z") and datetime.fromisoformat(since.replace("Z", "+00:00")) <= datetime.now(timezone.utc)
    claude_signin.failed(REAL)
    assert claude_signin.signed_out_since() == since, "the first failure's time is kept"
    claude_signin.succeeded()
    assert claude_signin.signed_out_since() is None
    claude_signin.succeeded()  # signed in already: nothing changes
    assert claude_signin.signed_out_since() is None


def test_the_words_say_what_happened_and_what_to_do():
    words = claude_signin.SIGNED_OUT
    assert "signed out" in words and "/login" in words and "server computer" in words and "exited with code" not in words


def test_a_log_is_read_for_its_reason_and_one_that_cannot_be_read_says_nothing(tmp_path: Path):
    log = tmp_path / "writing-trivia-1.log"
    log.write_text(f"# trivia for 1, started 2026-11-14T18:33:58Z\n{REAL}\n", encoding="utf-8")
    assert claude_signin.from_log(log) == claude_signin.SIGNED_OUT
    claude_signin.reset()
    assert claude_signin.from_log(tmp_path / "gone.log") is None and claude_signin.signed_out_since() is None
    (tmp_path / "empty.log").write_text("", encoding="utf-8")
    assert claude_signin.from_log(tmp_path / "empty.log") is None


def test_every_answer_of_the_server_carries_the_word():
    assert envelope({})["meta"]["claudeSignedOut"] is None
    claude_signin.failed(REAL)
    assert envelope({})["meta"]["claudeSignedOut"] == claude_signin.signed_out_since()
    claude_signin.succeeded()
    assert envelope(None)["meta"]["claudeSignedOut"] is None


def fake_tool(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *runs: tuple[int, str]) -> str:
    """A Claude Code that, run after run, writes its text into the run's log (its stdout) and exits with its code."""
    queue = list(runs)

    class FakeProcess:
        def __init__(self, handle) -> None:
            self.handle = handle
            self.returncode: int | None = None

        async def communicate(self, input: bytes | None = None):
            code, text = queue.pop(0)
            self.handle.write(text)
            self.handle.flush()
            self.returncode = code
            return None, None

        async def wait(self) -> int:
            return self.returncode or 0

        def kill(self) -> None:
            pass

    async def spawn(*args, **kwargs):
        return FakeProcess(kwargs["stdout"])

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    tool = tmp_path / "claude.exe"
    tool.write_bytes(b"MZ")
    return str(tool)


def test_the_writing_runner_says_signed_out_and_a_run_that_gets_through_clears_it(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    tool = fake_tool(tmp_path, monkeypatch, (1, REAL + "\n"), (1, "API Error: 529 Overloaded\n"), (0, "Nothing usable here.\n"))
    runner = W.WritingRunner(tmp_path / "data", tmp_path / "logs")
    job = W.Job("scout", "401", "Florida", {"opponent": "Texas"}, lambda answer: True, "The scouting report")

    def run() -> None:
        async def go() -> None:
            await runner.start(job, tool)
            await runner.task

        asyncio.run(go())

    run()
    assert runner.error == claude_signin.SIGNED_OUT and not runner.saved
    since = claude_signin.signed_out_since()
    assert since
    run()
    assert runner.error == "the tool exited with code 1", "any other failure keeps its code"
    assert claude_signin.signed_out_since() == since, "a failure for another reason proves nothing about the sign-in"
    run()
    assert runner.error and runner.error.startswith("the tool finished but"), "the sign-in worked; the answer is another matter"
    assert claude_signin.signed_out_since() is None


def test_the_notes_runner_says_signed_out(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    tool = fake_tool(tmp_path, monkeypatch, (1, REAL + "\n"))
    runner = NotesRunner(tmp_path / "data", tmp_path / "logs", who=lambda: None, season=2026)
    runner.log_dir.mkdir(parents=True)  # start() makes it before a run
    runner.started_at = datetime.now(timezone.utc)
    asyncio.run(runner._run(tool, "Write the notes.", 401856884))
    assert runner.exit_code == 1 and runner.error == claude_signin.SIGNED_OUT and not runner.saved
    assert claude_signin.signed_out_since()


def test_the_ask_runner_says_signed_out(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    tool = fake_tool(tmp_path, monkeypatch, (1, REAL + "\n"))
    runner = AskRunner(tmp_path / "data", tmp_path / "logs")

    async def go() -> None:
        await runner.start("Who starts at quarterback?", "#program", "The page.", "Florida", tool)
        await runner.task

    asyncio.run(go())
    assert runner.error == claude_signin.SIGNED_OUT


def test_the_season_runner_reads_its_log_too():
    season = (ROOT / "app" / "services" / "season_task.py").read_text(encoding="utf-8")
    assert "claude_signin.from_log(path)" in season and "claude_signin.succeeded()" in season


def json_tool(monkeypatch: pytest.MonkeyPatch, *answers: tuple[int, str, str]):
    monkeypatch.setattr(claude_cli, "find_command", lambda command="claude": ("C:/tools/claude.exe", "C:/tools"))
    queue = list(answers)

    async def runner(args: list[str], stdin: bytes, cwd: str, timeout: float) -> tuple[int, str, str]:
        return (0, HELP, "") if args[-1] == "--help" else queue.pop(0)

    return runner


def test_the_json_client_says_signed_out_and_a_good_answer_clears_it(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    signed_out = json.dumps({"type": "result", "subtype": "success", "is_error": True, "result": REAL})  # the Circle of Blame's 2026-11-11 answer
    good = json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": '{"ok": 1}', "modelUsage": OPUS})
    cli = ClaudeCli("claude", tmp_path, runner=json_tool(monkeypatch, (1, signed_out, ""), (1, "", "Error: something else"), (0, good, "")))
    with pytest.raises(ClaudeFailed) as caught:
        asyncio.run(cli.ask("Be an analyst.", None, "The pack."))
    assert str(caught.value) == claude_signin.SIGNED_OUT and caught.value.stdout == signed_out
    assert claude_signin.signed_out_since()
    with pytest.raises(ClaudeFailed, match="no JSON result: Error: something else"):
        asyncio.run(cli.ask("Be an analyst.", None, "The pack."))
    assert claude_signin.signed_out_since(), "another failure leaves the word as it was"
    assert asyncio.run(cli.ask("Be an analyst.", None, "The pack.")).text == '{"ok": 1}'
    assert claude_signin.signed_out_since() is None


NODE_SCRIPT = """
import assert from "node:assert/strict";
const { noteClaude, claudeSignedOutSince, signedOutWords, resetBuild } = await import(process.argv[2]);
resetBuild();
assert.equal(noteClaude(undefined), false, "no meta: nothing known");
assert.equal(noteClaude(null), false, "signed in, as the page already thought");
assert.equal(claudeSignedOutSince(), null);
assert.equal(noteClaude("2026-11-14T17:58:20Z"), true);
assert.equal(noteClaude("2026-11-14T17:58:20Z"), false, "said once");
assert.equal(claudeSignedOutSince(), "2026-11-14T17:58:20Z");
assert.equal(noteClaude(undefined), false, "an answer without the word changes nothing");
assert.equal(claudeSignedOutSince(), "2026-11-14T17:58:20Z");
assert.equal(noteClaude(null), true, "a run got through");
assert.equal(claudeSignedOutSince(), null);
assert.equal(noteClaude(""), false);
assert.equal(noteClaude(42), false);
const words = signedOutWords("2026-11-14T17:58:20Z");
assert.ok(words.includes("/login") && words.includes("(since ") && words.includes("server computer"), words);
for (const bad of [null, undefined, "nonsense", 7]) {
  const plain = signedOutWords(bad);
  assert.ok(plain.includes("/login") && !plain.includes("since") && !/undefined|null|NaN|Invalid/.test(plain), plain);
}
noteClaude("2026-11-15T01:00:00Z");
resetBuild();
assert.equal(claudeSignedOutSince(), null);
console.log("ok");
"""


def test_the_page_hears_the_word_once_each_time_it_changes(tmp_path: Path):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    script = tmp_path / "claude_signin.mjs"
    script.write_text(NODE_SCRIPT, encoding="utf-8")
    result = subprocess.run([node, str(script), (ROOT / "static" / "js" / "build.js").as_uri()], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    assert result.returncode == 0 and "ok" in result.stdout, result.stderr[-1200:]


def test_the_to_do_and_the_data_status_card_say_it_on_the_hosts_devices():
    js = ROOT / "static" / "js"
    app = (js / "app.js").read_text(encoding="utf-8")
    assert '"kickoff:claude-signin"' in app and 'id: "claude-signin"' in app and 'removeNote("claude-signin")' in app
    # the first answers come before the listener and before guest mode answers: the boot shows what was already said
    assert "claudeRoleKnown = true" in app and "showClaudeSignin(claudeSignedOutSince())" in app
    shell = (js / "ui" / "shell.js").read_text(encoding="utf-8")
    assert "claudeLine()" in shell and "claudeSignedOutSince()" in shell
    common = (js / "views" / "common.js").read_text(encoding="utf-8")
    assert "noteClaude(body.meta?.claudeSignedOut)" in common
