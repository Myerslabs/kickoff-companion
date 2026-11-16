"""P4: Claude Code's writing runs. Each kind's answer is read leniently (fences and chatter ignored, a damaged row
dropped, a wrong-typed field left out), lessons and prompt additions are kept with their reasons and can be undone, and the
runner starts the tool the notes runner's way, the prompt on stdin, web search only."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.services import writing as W

ANSWERS = {
    "review": {"lessons": ["Trust the SEC's availability report over beat writers on Thursday.", 5, ""], "promptAddition": "Check the team's game notes PDF for the depth chart.", "reason": "Two weeks in a row the chart came from a stale site."},
    "recap": {"headline": "Defense wins it late", "decidedBy": ["A fourth-quarter stop"], "paragraphs": ["One.", "Two."], "sources": [{"label": "Beat", "url": "https://x.example"}, {"url": "no label"}]},
    "scout": {"summary": "A run-first team.", "strengths": ["Run game"], "weaknesses": ["Deep passes"], "keys": ["Stop the run"], "sources": []},
    "paper": {"stories": [{"headline": "The lead", "dek": "One line", "paragraphs": ["A."]}, {"dek": "no headline"}], "picks": [{"gameId": 1, "pick": "Texas", "reason": "Better line."}, {"gameId": "x", "pick": "A"}]},
    "datacheck": {"findings": [{"subject": "Head coach", "appSays": "A", "webSays": "B", "source": "https://x"}], "checked": ["Coaches"]},
    "trivia": {"questions": [{"team": "Florida", "question": "Q?", "choices": ["A", "B", "C", "D"], "answer": "A", "source": "https://x"}, {"question": "no answer"}]},
}


@pytest.mark.parametrize("kind", sorted(ANSWERS))
def test_each_kinds_answer_is_read_from_chatter_and_fences(kind):
    text = f"Here you go.\n```json\n{json.dumps(ANSWERS[kind])}\n```\nThanks!"
    answer, warnings, error = W.read(kind, text)
    assert error is None and answer, (kind, error)
    if kind == "paper":
        assert [s["headline"] for s in answer["stories"]] == ["The lead"] and [p["gameId"] for p in answer["picks"]] == [1]
        assert any("damaged" in w for w in warnings)
    if kind == "recap":
        assert len(answer["sources"]) == 1
    if kind == "trivia":
        assert len(answer["questions"]) == 1


@pytest.mark.parametrize("text", [None, "", "no json here", "```json\n{\"something\": 1}\n```", "```json\n{\"lessons\": []}\n```", "too long"])
def test_an_answer_with_nothing_usable_is_refused_in_plain_words(text):
    answer, _warnings, error = W.read("review", "x" * (W.MAX_ANSWER + 1) if text == "too long" else text)
    assert answer is None and isinstance(error, str) and error


def test_a_wrong_typed_field_is_left_out_not_the_whole_answer():
    answer, warnings, error = W.read("scout", json.dumps({"summary": "Fine.", "strengths": "not a list", "keys": ["One"]}))
    assert error is None and answer["summary"] == "Fine." and answer.get("strengths") == [] and warnings
    assert W.read("nope", "{}")[2].startswith("no such kind")


def test_the_prompt_carries_the_task_the_shape_and_the_data():
    prompt = W.build_prompt("scout", "Florida", {"opponent": "Texas", "numbers": {"successRate": 0.45}})
    assert "scouting report on Texas, Florida's next opponent" in prompt and '"strengths"' in prompt and '"successRate": 0.45' in prompt
    assert "never invent" in prompt
    review = W.build_prompt("review", "Florida", {"x": 1})
    assert "You need no web search" in review
    long = W.build_prompt("paper", "Florida", {"blob": "y" * (W.MAX_PACKET_CHARS + 10)})
    assert "(cut short)" in long


def test_lessons_and_additions_are_kept_and_an_addition_can_be_undone(tmp_path: Path):
    lessons = W.Lessons(tmp_path)
    assert lessons.for_prompt() == ([], [])
    answer, _w, _e = W.read("review", json.dumps(ANSWERS["review"]))
    assert lessons.add_review(401, answer) is True
    texts, additions = lessons.for_prompt()
    assert texts == ["Trust the SEC's availability report over beat writers on Thursday."] and additions == [ANSWERS["review"]["promptAddition"]]
    assert lessons.add_review(402, answer) is False, "the same lesson and addition are not added twice"
    row = lessons.load()["additions"][0]
    assert row["reason"].startswith("Two weeks") and row["active"] is True and row["gameId"] == 401
    assert lessons.set_active(row["id"], False)["active"] is False and lessons.for_prompt()[1] == [], "undone"
    assert lessons.set_active(row["id"], True)["active"] is True and lessons.for_prompt()[1], "and back"
    assert lessons.set_active("nope", True) is None
    for i in range(W.MAX_LESSONS + 5):
        lessons.add_review(500 + i, {"lessons": [f"Lesson {i}."]})
    assert len(lessons.for_prompt()[0]) == W.MAX_LESSONS and lessons.for_prompt()[0][-1] == f"Lesson {W.MAX_LESSONS + 4}."
    lessons.path.write_text("{broken", encoding="utf-8")
    assert W.Lessons(tmp_path).load() == {"lessons": [], "additions": []}


def test_the_store_says_whether_an_answer_changed(tmp_path: Path):
    store = W.WritingStore(tmp_path, 2026)
    assert store.load("recap", "401") is None
    assert store.save("recap", "401", {"headline": "A"}) is True
    assert store.save("recap", "401", {"headline": "A"}) is False
    assert store.save("recap", "401", {"headline": "B"}) is True
    assert store.load("recap", "401")["headline"] == "B" and store.load("recap", "401")["author"]
    assert store.path("recap", "../../etc").name == "recap-etc.json", "a key never leaves the folder"
    store.path("recap", "9").write_text("[1]", encoding="utf-8")
    assert store.load("recap", "9") is None


def test_the_runner_sends_the_prompt_on_stdin_and_saves_through_the_job(tmp_path: Path, monkeypatch):
    calls: list = []

    class FakeProcess:
        returncode: int | None = None

        async def communicate(self, input: bytes | None = None):
            self.returncode = 0
            calls.append(input)
            log = next(tmp_path.glob("logs/writing-*.log"))
            with log.open("a", encoding="utf-8") as handle:
                handle.write("```json\n" + json.dumps(ANSWERS["scout"]) + "\n```\n")
            return None, None

        async def wait(self) -> int:
            return 0

        def kill(self) -> None:
            pass

    async def spawn(*args, **kwargs):
        calls.append(args)
        return FakeProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    tool = tmp_path / "claude.exe"
    tool.write_bytes(b"MZ")
    saved: list = []
    runner = W.WritingRunner(tmp_path / "data", tmp_path / "logs")
    job = W.Job("scout", "401", "Florida", {"opponent": "Texas"}, lambda answer: saved.append(answer) or True, "The scouting report")

    async def go():
        status = await runner.start(job, str(tool))
        assert status["running"] and status["kind"] == "scout"
        assert (await runner.start(job, str(tool)))["error"].startswith("a scout run is still going")
        await runner.task

    asyncio.run(go())
    args = calls[0]
    assert W.PROMPT_LEAD in args and "--allowedTools" in args and args[args.index("--allowedTools") + 1] == W.ALLOWED_TOOLS
    assert b"scouting report on Texas" in calls[1], "the prompt arrives on stdin"
    assert runner.saved and runner.changed is True and saved[0]["summary"] == "A run-first team."
    missing = W.WritingRunner(tmp_path / "data", tmp_path / "logs")
    assert "was not found" in asyncio.run(missing.start(job, str(tmp_path / "nope.exe")))["error"]
    assert asyncio.run(missing.start(W.Job("nope", "1", "F", {}, lambda a: True), str(tool)))["error"].startswith("no such kind")
    assert datetime.now(timezone.utc)  # the runner keeps its own clock; nothing here depends on today
