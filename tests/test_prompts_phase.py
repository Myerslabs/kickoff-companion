"""The Prompts phase (owner 2026-10-13): the school history and facts prompt (its reader forgiving a year written as text, a
capacity with commas, a bad date, a stranger), its file and the team page that carries it; the one run of every prompt
in the season's order (skipping what is loaded, going on past a failure); the schedule on whenever Claude Code's command
is found, with its once-a-day catch-up; the Prompts page's envelope; and `python -m app prompts` against a stub server."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from app import prompts_cli
from app.services import season_prompts
from app.services.claude_schedule import CATCH_UP_KEY, ClaudeSchedule, Ledger
from app.services.prompt_runs import PromptRuns, Step
from app.services.season_notes import SeasonNotes, TeamFacts
from tests.conftest import CONFERENCE, TEAM, fixture_payload
from tests.test_season_notes import league  # noqa: F401 - routes the fake CFBD

SCHOOLS = sorted(t["school"] for t in fixture_payload("teams_fbs") if t["conference"] == CONFERENCE)


def facts_answer(schools=SCHOOLS[:3], extra=(), **first):
    teams = []
    for i, s in enumerate(schools):
        row: dict[str, Any] = {
            "school": s, "founded": 1853 + i, "stadium": f"Stadium {i}", "stadiumOpened": "1930", "capacity": "88,548", "conferenceSince": 1932,
            "allTimeRecord": "750-440-40", "nationalTitles": [1996, "2006", "never"], "conferenceTitles": 8, "heismans": ["Player One, 1966"], "bowlRecord": "24-23",
            "rivalries": [{"rival": "Rival U", "trophy": "The Cup", "firstMeeting": 1915, "record": "68-44-2"}, {"trophy": "no rival"}],
            "headCoachRecord": "30-20", "mascotOrigin": "A marsh.", "colorsOrigin": "The founders.", "fightSong": "Fight!", "nflAlumni": ["Pro One", 7, ""],
            "dates": [{"date": "1930-11-08", "event": "The stadium's first game"}, {"date": "1996", "event": "A title"}, {"date": "sometime", "event": "junk"}, {"event": "no date"}],
            "sources": [{"label": "Media guide", "url": "https://example.invalid/guide"}],
        }
        if i == 0:
            row.update(first)
        teams.append(row)
    return "```json\n" + json.dumps({"conference": CONFERENCE, "season": 2026, "author": "Test chat", "teams": [*teams, *extra]}) + "\n```"


# --- the reader and the file ----------------------------------------------------------------------------------------


def test_the_facts_reader_forgives_and_warns():
    reading = season_prompts.read_facts(facts_answer(extra=[{"school": "Nowhere U", "founded": 1900}]), CONFERENCE, SCHOOLS)
    assert reading.value is not None
    first = reading.value.teams[0]
    assert first.stadiumOpened == 1930 and first.capacity == 88548 and first.nationalTitles == [1996, 2006], "a year as text and a capacity with commas count; junk is dropped"
    assert [r.rival for r in first.rivalries] == ["Rival U"], "a rivalry without a rival is dropped"
    assert first.nflAlumni == ["Pro One", "7"] and [d.date for d in first.dates] == ["1930-11-08", "1996"], "a bad date is dropped, a year alone kept"
    assert reading.summary["teams"] == 3 and reading.summary["dates"] == 6
    assert any("Nowhere U" in w for w in reading.warnings) and any("No facts for" in w for w in reading.warnings)
    junk = season_prompts.read_facts(facts_answer(founded="unknown", capacity="full", conferenceTitles=None), CONFERENCE, SCHOOLS)
    assert junk.value is not None and junk.value.teams[0].founded is None and junk.value.teams[0].capacity is None, "junk in a number is None, the row stays"
    assert season_prompts.read_facts("```json\n{\"teams\": []}\n```", CONFERENCE, SCHOOLS).value is None
    assert season_prompts.read_facts(facts_answer(schools=["Nowhere U"]), CONFERENCE, SCHOOLS).value is None
    assert season_prompts.read_facts("nothing here", CONFERENCE, SCHOOLS).value is None
    assert TeamFacts.model_validate({"school": "X", "founded": True, "nationalTitles": "1996", "heismans": "one"}).founded is None


def test_the_facts_file_merges_by_batch_and_survives_damage(tmp_path: Path):
    notes = SeasonNotes(tmp_path / "data", 2026)
    reading = season_prompts.read_facts(facts_answer(), CONFERENCE, SCHOOLS)
    kept = notes.save_facts(reading.value, CONFERENCE, SCHOOLS)
    assert kept["kept"] == SCHOOLS[:3] and kept["missing"] == SCHOOLS[3:]
    row = notes.facts_for(SCHOOLS[0])
    assert row and row["founded"] == 1853 and row["conference"] == CONFERENCE and row["savedAt"] and row["rivalries"][0]["trophy"] == "The Cup"
    assert notes.facts_for("Nowhere U") is None and notes.facts_for(None) is None
    status = notes.status([TEAM], {CONFERENCE: SCHOOLS}, datetime(2026, 9, 1).date())
    batch_status = status["facts"][0]
    assert status["factsSaved"] == 3 and {k: batch_status[k] for k in ("conference", "schools", "saved", "savedAt")} == {"conference": CONFERENCE, "schools": len(SCHOOLS), "saved": 3, "savedAt": row["savedAt"]}
    assert batch_status["shipped"] == 0 and batch_status["checkedAt"] == row["savedAt"] and batch_status["stale"] is False, "the preloaded facts (2026-10-21): a batch says where its facts come from and whether they are a year old"
    # a second batch replaces only its own teams
    notes.save_facts(season_prompts.read_facts(facts_answer(schools=SCHOOLS[2:4], founded=1999), CONFERENCE, SCHOOLS).value, CONFERENCE, SCHOOLS)
    assert notes.facts_for(SCHOOLS[0])["founded"] == 1853 and notes.facts_for(SCHOOLS[2])["founded"] == 1999 and notes.facts_for(SCHOOLS[3])
    notes.facts_path.write_text("{ broken", encoding="utf-8")
    assert notes.facts() == {"teams": {}, "batches": {}, "shipped": []} and notes.facts_for(SCHOOLS[0]) is None
    assert season_prompts.template("facts", tmp_path).fill({"season": 2026, "conference": "C", "schools": "- A", "shape": "{}"}).startswith("You are loading school history")


# --- the routes -----------------------------------------------------------------------------------------------------


def test_the_facts_routes_and_the_team_page(client, league, app):  # noqa: F811
    prompt = client.get("/api/season-notes/prompt", params={"kind": "facts", "key": CONFERENCE}).json()["data"]["prompt"]
    assert "school history" in prompt and SCHOOLS[0] in prompt and '"dates"' in prompt and "{shape}" not in prompt
    assert client.get("/api/season-notes/prompt", params={"kind": "facts", "key": "No Such Conference"}).status_code == 404
    assert client.post("/api/season-notes/save", json={"kind": "facts", "key": CONFERENCE, "text": "nothing"}).status_code == 422
    saved = client.post("/api/season-notes/save", json={"kind": "facts", "key": CONFERENCE, "text": facts_answer()}).json()["data"]
    assert saved["saved"] is True
    team = client.get(f"/api/team/{SCHOOLS[0]}").json()["data"]
    assert team["facts"]["founded"] == 1853 and team["facts"]["fightSong"] == "Fight!" and team["facts"]["dates"][0]["date"] == "1930-11-08"
    assert client.get(f"/api/team/{SCHOOLS[-1]}").json()["data"]["facts"] is None, "not loaded: null, and the page says so"
    ready = client.get("/api/readiness").json()["data"]
    facts_item = next(i for i in ready["items"] if i["id"] == "facts")
    assert facts_item["href"] == "#prompts" and "3 of" in facts_item["detail"]
    assert all(i["href"] == "#prompts" for i in ready["items"]), "every dead end leads to the Prompts page"
    template = client.get("/api/season-notes/template", params={"kind": "facts"}).json()["data"]
    assert template["custom"] is False and "dates" in template["template"]
    page = client.get("/api/prompts").json()["data"]
    assert set(page) >= {"commandFound", "season", "seasonRun", "notesRun", "notes", "run", "schedule"}
    assert page["season"]["factsSaved"] == 3 and page["run"]["running"] is False and [s["kind"] for s in page["run"]["steps"]] == ["preseason", "coaches", "costs", "facts", "notes"]
    assert page["notes"]["gameId"] and isinstance(page["notes"]["missing"], list)
    assert client.get("/api/prompts/run").json()["data"]["of"] == 5


# --- the one run ---------------------------------------------------------------------------------------------------


def fake_step(kind: str, gap: str | None, *, fail: bool = False, polls: int = 1, calls: list[str] | None = None) -> Step:
    state = {"left": 0}

    async def start(all: bool) -> dict[str, Any]:  # noqa: A002
        (calls if calls is not None else []).append(f"{kind}:{'all' if all else 'missing'}")
        if fail == "start":
            return {"error": "could not start", "running": False}
        state["left"] = polls
        return {"running": True}

    def poll() -> dict[str, Any]:
        state["left"] -= 1
        if state["left"] > 0:
            return {"running": True}
        return {"running": False, "ok": not fail, "error": "it broke" if fail else None, "changed": True}

    async def missing() -> str | None:
        return gap

    return Step(kind, kind.title(), start, poll, missing)


def test_the_one_run_skips_the_loaded_and_goes_on_past_a_failure():
    calls: list[str] = []
    steps = [fake_step("preseason", None, calls=calls), fake_step("coaches", "3 of 16", calls=calls, polls=2), fake_step("costs", "0 of 16", fail=True, calls=calls), fake_step("facts", "0 of 16", fail="start", calls=calls), fake_step("notes", "missing the notes", calls=calls)]
    runs = PromptRuns(steps, command_found=lambda: True, poll_seconds=0)

    async def go(all: bool):  # noqa: A002
        status = await runs.start(all=all)
        assert status["running"] is True
        assert (await runs.start())["error"] == "the prompts are already running"
        await runs.task
        return runs.status()

    done = asyncio.run(go(False))
    assert [s["state"] for s in done["steps"]] == ["skipped", "done", "failed", "failed", "done"]
    assert done["steps"][0]["detail"] == "nothing missing" and done["steps"][1]["detail"] == "3 of 16" and done["steps"][2]["error"] == "it broke" and done["steps"][3]["error"] == "could not start"
    assert done["done"] == 3 and done["failed"] == 2 and done["of"] == 5 and done["running"] is False and done["finishedAt"]
    assert calls == ["coaches:missing", "costs:missing", "facts:missing", "notes:missing"], "the loaded step never started"
    again = asyncio.run(go(True))
    assert [s["state"] for s in again["steps"]][0] == "done" and calls[-5:] == ["preseason:all", "coaches:all", "costs:all", "facts:all", "notes:all"]
    none = PromptRuns(steps, command_found=lambda: False)
    refused = asyncio.run(none.start())
    assert refused["running"] is False and "not found" in refused["error"]


def test_the_schedule_is_on_when_the_command_is_found_and_catches_up_once_a_day(tmp_path: Path):
    ET = ZoneInfo("America/New_York")
    now = {"at": datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)}
    found = {"yes": True}
    choice: dict[str, bool | None] = {"value": None}
    started: list[str] = []
    busy = {"yes": False}

    def enabled() -> bool:  # what app/schedule_setup.py does with the preference
        return found["yes"] if choice["value"] is None else bool(choice["value"])

    async def catch_up() -> dict[str, Any]:
        started.append("catch-up")
        return {"running": True}

    async def no_game():
        return None

    async def current(_slot):
        return True

    async def start(_slot, _game):
        return {"error": "never"}

    schedule = ClaudeSchedule(ledger=Ledger(tmp_path / "ledger.json"), enabled=enabled, command_found=lambda: found["yes"], current_game=no_game, season=lambda: 2026, tz=ET, data_is_current=current, start=start, poll=lambda _s: {"running": False, "ok": True}, clock=lambda: now["at"], catch_up=catch_up, busy=lambda: busy["yes"])
    assert asyncio.run(schedule.tick()) == "catch-up started" and started == ["catch-up"]
    assert asyncio.run(schedule.tick()) == "nothing due", "once a day: the ledger remembers"
    assert schedule.ledger.last_attempt(CATCH_UP_KEY) == now["at"]
    busy["yes"] = True
    assert asyncio.run(schedule.tick()) == "busy"
    busy["yes"] = False
    now["at"] += timedelta(hours=21)
    assert asyncio.run(schedule.tick()) == "catch-up started" and len(started) == 2
    found["yes"] = False
    assert asyncio.run(schedule.tick()) == "off", "no command: off by itself"
    choice["value"] = True
    assert asyncio.run(schedule.tick()) == "no command"
    found["yes"] = True
    choice["value"] = False
    assert asyncio.run(schedule.tick()) == "off", "switched off in Settings"
    status = asyncio.run(schedule.status())
    assert status["enabled"] is False and status["commandFound"] is True


def test_the_app_wires_the_run_and_the_switch(client, league, app):  # noqa: F811
    assert app.state.claude_schedule.busy() is False and app.state.claude_schedule.catch_up is not None
    assert client.get("/api/claude-schedule").json()["data"]["enabled"] == app.state.claude_schedule.command_found(), "on when found, nothing set"
    client.put("/api/settings", json={"scheduledRuns": False})
    assert client.get("/api/claude-schedule").json()["data"]["enabled"] is False
    refused = client.post("/api/prompts/run", json={"all": False})
    body = refused.json()
    assert body["data"]["running"] is False and (body["errors"] or body["data"]["commandFound"]), "no command in the tests: refused with the reason"


# --- the command line -----------------------------------------------------------------------------------------------


def test_the_command_runs_against_the_server_and_prints_each_prompt(settings):
    lines: list[str] = []
    polls = {"n": 0}
    steps = [{"kind": "preseason", "label": "The season load", "state": "skipped", "detail": "nothing missing"}, {"kind": "notes", "label": "This week's notes", "state": "running"}]

    def http(method: str, path: str, body: dict[str, Any] | None):
        if path == "/api/health":
            return 200, {"data": {"ok": True}}
        if path == "/api/prompts/run" and method == "POST":
            assert body == {"all": False}
            return 200, {"data": {"running": True, "steps": steps, "of": 2}}
        polls["n"] += 1
        done = [{**steps[0]}, {**steps[1], "state": "done", "changed": True}]
        return 200, {"data": {"running": polls["n"] < 2, "steps": done if polls["n"] >= 2 else steps, "of": 2}}

    code = prompts_cli.main([], settings, http=http, sleep=lambda _s: None, out=lines.append)
    assert code == 0 and polls["n"] == 2
    assert lines[0].startswith("Running what is missing") and "  The season load: skipped (nothing missing)" in lines and "  This week's notes: done (new information)" in lines and lines[-1] == "Finished: 1 done, 1 skipped, 0 failed."
    failed = prompts_cli.main(["--all"], settings, http=lambda m, p, b: (200, {"data": {"running": False, "steps": [{"kind": "notes", "label": "Notes", "state": "failed", "error": "it broke"}], "of": 1}}) if p != "/api/health" else (200, {}), sleep=lambda _s: None, out=lines.append)
    assert failed == 1 and lines[-1] == "Finished: 0 done, 0 skipped, 1 failed." and "  Notes: FAILED (it broke)" in lines
    assert prompts_cli.main([], settings, http=lambda m, p, b: (403, {"errors": [{"message": "guest"}]}) if p != "/api/health" else (200, {}), out=lines.append) == 2 and "only the server computer or a host device" in lines[-1]
    assert prompts_cli.main([], settings, http=lambda m, p, b: (200, {"data": {"running": False, "error": "no command"}}) if p != "/api/health" else (200, {}), out=lines.append) == 2 and "no command" in lines[-1]

    def down(method, path, body):
        raise OSError("refused")

    assert prompts_cli.main([], settings, http=down, out=lines.append) == 2 and "No server answered" in lines[-1]


def test_python_m_app_prompts_dispatches(tmp_path: Path, capsys):
    from app.cli import main
    from tests.conftest import TEST_KEY

    env = tmp_path / ".env"
    env.write_text(f"CFBD_API_KEY={TEST_KEY}\nPORT=1\nDATA_DIR={(tmp_path / 'data').as_posix()}\n", encoding="utf-8")
    assert main(["prompts"], env_file=env) == 2, "no server on port 1: said, not crashed"
    assert "No server answered" in capsys.readouterr().out


@pytest.mark.parametrize("junk", ["", "plain\nwords", None])
def test_the_command_line_output_never_breaks_on_junk(junk):
    assert "undefined" not in prompts_cli._line({"kind": "x", "state": junk, "label": None, "detail": junk})
