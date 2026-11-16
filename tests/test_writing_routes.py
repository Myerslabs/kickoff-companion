"""P4 over HTTP and on the page: the writing routes (what was written, write it now, nothing to write about), the lessons
and the additions' undo, Ask about this page (its runner with a stand-in for Claude Code, its routes, a guest's refusal),
and Claude's checked trivia questions in the game-day trivia."""

from __future__ import annotations

import asyncio
import json
import random
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.services.ask import AskRunner, build_prompt
from app.services.trivia_questions import pick_question, written_question
from app.services.writing import Lessons, WritingStore
from tests.fakedom import needs_node, run_scenario


def test_what_was_written_and_the_latest_check(app, client: TestClient):
    settings = app.state.settings
    store = WritingStore(settings.data_dir, settings.season)
    none = client.get("/api/writing/recap/401").json()["data"]
    assert none["written"] is None and none["running"] is False and "commandFound" in none
    store.save("recap", "401", {"headline": "Late stop"})
    got = client.get("/api/writing/recap/401").json()["data"]
    assert got["written"]["headline"] == "Late stop" and got["written"]["author"].startswith("Claude Code")
    store.save("datacheck", "2026-10-20", {"findings": [{"subject": "Coach"}]})
    assert client.get("/api/writing/datacheck/latest").json()["data"]["written"]["findings"][0]["subject"] == "Coach"
    assert client.get("/api/writing/nope/1").status_code == 404 and client.get("/api/writing/recap/..%2F").status_code == 404
    assert client.get("/api/writing/status").json()["data"]["running"] is False


def test_write_it_now_needs_a_confirm_and_something_to_write_about(app, client: TestClient):
    assert client.post("/api/writing/recap/401/run", json={}).json()["errors"][0]["code"] == "confirm"
    refused = client.post("/api/writing/recap/999999/run", json={"confirm": True})
    assert refused.status_code == 409 and refused.json()["errors"][0]["code"] == "nothing_to_write"
    assert client.post("/api/writing/nope/1/run", json={"confirm": True}).status_code == 404


def test_the_lessons_and_an_additions_undo_over_http(app, client: TestClient):
    lessons = Lessons(app.state.settings.data_dir)
    lessons.add_review(401, {"lessons": ["Check the PDF."], "promptAddition": "Read the game notes PDF.", "reason": "Stale charts."})
    data = client.get("/api/claude/lessons").json()["data"]
    row = data["additions"][0]
    assert data["lessons"][0]["text"] == "Check the PDF." and row["active"] is True
    off = client.post(f"/api/claude/additions/{row['id']}", json={"active": False}).json()["data"]
    assert off["active"] is False and lessons.for_prompt()[1] == []
    assert client.post("/api/claude/additions/nope", json={"active": True}).status_code == 404


def test_the_notes_prompt_carries_the_lessons_and_the_last_games_notes(app, client: TestClient):
    from app.services import notes_paste

    settings = app.state.settings
    Lessons(settings.data_dir).add_review(401, {"lessons": ["Trust the conference's report."], "promptAddition": "Copy the chart from the team's own notes."})
    (settings.data_dir / "notes").mkdir(parents=True, exist_ok=True)
    (settings.data_dir / "notes" / "400.json").write_text(json.dumps({"gameId": 400, "availability": [{"team": "Florida", "name": "A Player", "status": "Out"}], "sections": [{"heading": "Coaching", "paragraphs": ["x"]}]}), encoding="utf-8")
    text = notes_paste.learning_text(settings.data_dir, 402)
    assert "Trust the conference's report." in text and "Copy the chart from the team's own notes." in text and '"gameId": 400' in text and "A Player" in text
    assert notes_paste.learning_text(settings.data_dir, 400).count('"gameId": 400') == 0, "never the game's own notes"


def test_ask_answers_from_the_page_with_a_stand_in_for_claude(tmp_path: Path, monkeypatch):
    sent: list = []

    class FakeProcess:
        returncode: int | None = None

        async def communicate(self, input: bytes | None = None):
            sent.append(input)
            self.returncode = 0
            with (tmp_path / "logs" / "ask.log").open("a", encoding="utf-8") as handle:
                handle.write("Florida leads the SEC in success rate.\n\nThat is from the page.\n")
            return None, None

        async def wait(self) -> int:
            return 0

        def kill(self) -> None:
            pass

    async def spawn(*args, **kwargs):
        return FakeProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    tool = tmp_path / "claude.exe"
    tool.write_bytes(b"MZ")
    runner = AskRunner(tmp_path / "data", tmp_path / "logs")

    async def go():
        assert (await runner.start("  ", "#season", "x", "Florida", str(tool)))["error"] == "Ask a question first."
        status = await runner.start("Who leads in success rate?", "#season", "The page text " + "y" * 40000, "Florida", str(tool))
        assert status["running"] and status["question"] == "Who leads in success rate?"
        assert (await runner.start("Again?", "#season", "", "Florida", str(tool)))["error"].startswith("Claude is still answering")
        await runner.task

    asyncio.run(go())
    assert runner.status()["answer"].startswith("Florida leads") and runner.status()["error"] is None
    assert b"Who leads in success rate?" in sent[0] and len(sent[0]) < 32000, "the page is cut to its limit"
    assert "#season" in build_prompt("Q?", "#season", "page", "Florida") and "no JSON" in build_prompt("Q?", "#season", "page", "Florida")
    missing = AskRunner(tmp_path / "data", tmp_path / "logs")
    assert "was not found" in asyncio.run(missing.start("Q?", "#x", "", "Florida", str(tmp_path / "nope.exe")))["error"]


def test_the_ask_routes(app, client: TestClient):
    status = client.get("/api/ask").json()["data"]
    assert status["running"] is False and "commandFound" in status
    app.state.settings.claude_command = "no-such-claude-here"
    refused = client.post("/api/ask", json={"question": "Why?", "route": "#program", "text": "page"})
    assert refused.status_code == 409 and "was not found" in refused.json()["errors"][0]["message"]


def test_claudes_checked_trivia_comes_first_every_other_question_and_never_twice():
    extra = [
        {"team": "Florida", "question": "What is the stadium's nickname?", "choices": ["The Swamp", "A", "B", "C"], "answer": "The Swamp", "source": "https://x"},
        {"team": "Florida", "question": "Bad?", "choices": ["A", "B"], "answer": "A"},  # not four choices
        {"team": "Nowhere", "question": "Not ours?", "choices": ["A", "B", "C", "D"], "answer": "A"},
        {"team": "Texas", "question": "Answer not a choice?", "choices": ["A", "B", "C", "D"], "answer": "E"},
        "junk",
    ]
    rng = random.Random(1)
    q = written_question(extra, ["Florida", "Texas"], [], rng, "q1")
    assert q is not None and q.kind == "written" and q.choices[q.answer] == "The Swamp" and q.fact == "https://x"
    asked = [{"text": q.text, "school": "Florida", "kind": "written"}]
    assert written_question(extra, ["Florida", "Texas"], asked, rng, "q2") is None, "asked once today"
    first = pick_question({}, ["Florida"], [], random.Random(2), "q3", extra=extra)
    assert first is not None and first.kind == "written"


SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object Object\]/;
const text = (node) => (node ? node.textContent : "");
const flush = async () => { for (let i = 0; i < 8; i += 1) await new Promise((resolve) => setImmediate(resolve)); };

scenarios.band = async () => {
  installWindow();
  await useTeam();
  const { writingBand, bullets, sourcesLine } = await import(moduleUrl("ui/writing-band.js"));
  route("/api/writing/scout/401", () => envelope({ kind: "scout", key: "401", written: { summary: "A run-first team.", strengths: ["Run game", 5, ""], writtenAt: "2026-10-19T17:00:00Z" }, running: false, commandFound: true }));
  route("/api/writing/scout/402", () => envelope({ kind: "scout", key: "402", written: null, running: false, commandFound: true }));
  route("/api/writing/scout/403", () => envelope({ kind: "scout", key: "403", written: null, running: false, commandFound: false }));
  const draw = (w) => el("div", {}, el("p", {}, w.summary), bullets(w.strengths));
  const { el } = await import(moduleUrl("ui/dom.js"));
  const one = writingBand({ id: "a", title: "Scouting report", kind: "scout", key: 401, when: "Monday.", draw });
  const two = writingBand({ id: "b", title: "Scouting report", kind: "scout", key: 402, when: "Claude Code writes it Monday.", draw });
  const three = writingBand({ id: "c", title: "Scouting report", kind: "scout", key: 403, when: "Claude Code writes it Monday.", draw });
  document.body.append(one, two, three);
  await flush();
  assert.ok(text(one).includes("A run-first team.") && text(one).includes("Run game") && text(one).includes("Written by Claude Code") && !RAW.test(text(one)), text(one));
  assert.equal(one.querySelectorAll("li").length, 1, "a line that is not text is left out");
  assert.ok(text(two).includes("Claude Code writes it Monday.") && two.querySelectorAll("button").find((b) => text(b) === "Write it now"), text(two));
  assert.ok(!three.querySelectorAll("button").find((b) => text(b) === "Write it now"), "no Claude Code on the server: no button");
  assert.ok(two.querySelector(".band"), "a band, foldable like every program band");
  assert.equal(writingBand({ id: "d", title: "x", kind: "scout", key: null, draw }), null);
  assert.equal(sourcesLine([{ label: "Beat", url: "javascript:alert(1)" }]).querySelector("a"), null, "only https links");
};

scenarios.ask = async () => {
  installWindow();
  const { pageText } = await import(moduleUrl("ui/ask.js"));
  const main = document.createElement("main");
  main.textContent = "  Florida   leads \n\n\n\n the SEC.  ";
  document.body.append(main);
  assert.ok(pageText(main).startsWith("Florida") && !pageText(main).includes("\n\n\n"));
  assert.equal(pageText(null), "");
};
"""


@needs_node
@pytest.mark.parametrize("scenario", ["band", "ask"])
def test_the_writing_band_and_ask_in_a_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)
