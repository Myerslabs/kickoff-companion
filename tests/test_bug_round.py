"""The bug round (owner 2026-11-15, "Build the bug round"; his answers: all four groups, "Add this season's games", "Retry the
failed job only", the test league's Claude "Off unless asked"). From the host's own log, Claude's data check of
2026-10-27 and the test runs. No network."""

from __future__ import annotations

import asyncio
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from app.cfbd.models import Game
from app.jobs import JobFailed, JobRuns
from app.jobs.weekly import WeeklyJobs
from app.logging_setup import DroppedConnectionFilter
from app.services import classes
from app.services.archive import ArchiveService
from app.services.facts_now import tally, with_this_season
from tests.test_season_notes import league  # noqa: F401 - routes the fake CFBD

ROOT = Path(__file__).resolve().parents[1]


def played(gid: int, home: str, away: str, hp: int, ap: int, completed: bool = True) -> Game:
    return Game.model_validate({"id": gid, "season": 2026, "week": gid, "startDate": "2026-09-05T23:30:00Z", "completed": completed, "homeTeam": home, "awayTeam": away, "homePoints": hp, "awayPoints": ap})


SEASON = [played(1, "Florida", "Akron", 59, 13), played(2, "Fresno State", "Florida", 27, 35), played(3, "Florida", "Ole Miss", 37, 41), played(4, "Florida", "Texas", 20, 20), played(5, "Florida", "Vanderbilt", 0, 0, completed=False)]
FACTS = {"school": "Florida", "allTimeRecord": "771-459-40", "headCoachRecord": "Jon Sumrall, 0-0 at Florida entering 2026, since 2026", "checkedAt": "2026-10-21", "savedAt": None}


def test_the_records_count_this_seasons_games():
    assert tally(SEASON, "Florida") == (2, 1, 1), "two wins, a loss, a tie; the game not played does not count"
    counted = with_this_season(FACTS, SEASON, 2026, "Jon Sumrall")
    assert counted["allTimeRecord"] == "773-460-41"
    assert counted["headCoachRecord"] == "Jon Sumrall, 2-1-1 at Florida with 2026's games, since 2026"
    assert FACTS["allTimeRecord"] == "771-459-40", "the facts themselves are never changed"
    assert with_this_season({**FACTS, "checkedAt": "2025-10-01"}, SEASON, 2026, "Jon Sumrall") == {**FACTS, "checkedAt": "2025-10-01"}, "facts of another season: as researched"
    assert with_this_season(FACTS, SEASON, 2026, "Somebody Else")["headCoachRecord"] == FACTS["headCoachRecord"], "a new coach: the old coach's record stays"
    assert with_this_season({**FACTS, "allTimeRecord": "about 770 wins"}, SEASON, 2026)["allTimeRecord"] == "about 770 wins", "a record that is not W-L-T stays"
    assert with_this_season(FACTS, [], 2026) == FACTS and with_this_season(None, SEASON, 2026) is None
    prompt = (ROOT / "app" / "services" / "season_prompts.py").read_text(encoding="utf-8")
    assert '"allTimeRecord" as wins-losses-ties entering the {season} season' in prompt and "at this school entering the {season} season" in prompt
    api = (ROOT / "app" / "api" / "program.py").read_text(encoding="utf-8")
    assert api.count("_counted(request, facts_with_venue(") == 2, "the program's two schools and a team's page"


def test_the_archive_reads_games_only(tmp_path: Path):
    folder = tmp_path / "archive"
    folder.mkdir()
    (folder / ".refreshed.json").write_text('{"401": "2026-11-01"}', encoding="utf-8")
    archive = ArchiveService(tmp_path, SimpleNamespace(), SimpleNamespace(), "Florida")

    async def no_names() -> dict:
        return {}

    archive._abbreviations = no_names  # the team list is not what this is about
    listed = asyncio.run(archive.list())
    assert listed["skipped"] == 0 and listed["games"] == [], "the second look's memory is not a game, nor a skipped file"


def test_a_weekly_retry_runs_only_the_failed_job(tmp_path: Path):
    ran: list[str] = []
    state = {"blame": "fail"}

    def job(name: str):
        async def work() -> dict:
            ran.append(name)
            if name == "circle_of_blame" and state["blame"] == "fail":
                raise JobFailed("Claude Code stopped: Failed to authenticate")
            return {"message": f"{name} done"}
        return work

    weekly = WeeklyJobs(JobRuns(tmp_path), 2026, {n: job(n) for n in ("talent_edge", "imperialism", "circle_of_blame")})
    first = asyncio.run(weekly.run())
    assert first["status"] == "failed" and ran == ["talent_edge", "imperialism", "circle_of_blame"]
    ran.clear()
    state["blame"] = "ok"
    second = asyncio.run(weekly.run())
    assert ran == ["circle_of_blame"], "the two that finished this week are not redone"
    assert second["status"] == "ok" and "(done earlier this week)" in second["message"]


def test_the_test_league_uses_claude_only_when_asked():
    run = (ROOT / "app" / "demo" / "run.py").read_text(encoding="utf-8")
    assert '**({} if claude else {"claude_command": NO_CLAUDE})' in run and '"--claude", action="store_true"' in run and "claude=args.claude" in run
    from app.demo.run import NO_CLAUDE
    from app.services.notes_task import NotesRunner

    assert NotesRunner.resolve_command(NO_CLAUDE) is None


def test_the_logs_say_a_thing_once():
    try:
        raise OSError(22, "The specified network name is no longer available", None, 64)
    except OSError:
        info = sys.exc_info()
    record = logging.LogRecord("asyncio", logging.ERROR, __file__, 1, "Task exception was never retrieved", (), info)
    assert getattr(info[1], "winerror", None) == 64 or sys.platform != "win32"
    if getattr(info[1], "winerror", None) == 64:
        assert DroppedConnectionFilter().filter(record) is False, "the server's own Accept failed warning says it"
    other = logging.LogRecord("asyncio", logging.ERROR, __file__, 1, "something else", (), None)
    assert DroppedConnectionFilter().filter(other) is True
    said: list[str] = []
    log = SimpleNamespace(warning=lambda msg, *args: said.append(msg % args))
    classes._SAID.discard((2099, "Nowhere State"))
    for _ in range(3):
        classes.say_inferred(log, 2099, "Nowhere State")
    assert said == ["CFBD's 2099 roster for Nowhere State lists nearly every player in one class; inferring the classes"]


def test_the_wiring_test_never_starts_claude():
    source = (ROOT / "tests" / "test_prompts_phase.py").read_text(encoding="utf-8")
    assert 'monkeypatch.setattr(NotesRunner, "resolve_command", staticmethod(lambda command: None))' in source
    extras = (ROOT / "tests" / "test_p16_extras.py").read_text(encoding="utf-8")
    assert 'season=2026, claude_command="no-claude-in-these-tests"' in extras and "quiet_background(app, client)" in extras


def test_utc_dates_from_the_facts():
    from app.services.facts_now import _date

    assert _date("2026-10-21") == datetime(2026, 10, 21, tzinfo=timezone.utc).date() and _date("2026-10-21T14:00:00Z").isoformat() == "2026-10-21" and _date("soon") is None


def test_the_pages_show_the_records_with_this_seasons_games(client, league, app):  # noqa: F811
    from tests.conftest import CONFERENCE, TEAM
    from tests.test_prompts_phase import facts_answer

    assert client.post("/api/season-notes/save", json={"kind": "facts", "key": CONFERENCE, "text": facts_answer(schools=[TEAM])}).status_code == 200
    core = client.portal.call(app.state.program._core)
    wins, losses, ties = tally(core["games"].records, TEAM)
    assert wins + losses + ties > 0, "the fixtures have games played"
    expected = f"{750 + wins}-{440 + losses}-{40 + ties}"
    program = client.get("/api/program/next").json()["data"]
    assert program["facts"]["us"]["allTimeRecord"] == expected
    team = client.get(f"/api/team/{TEAM}").json()["data"]
    assert team["facts"]["allTimeRecord"] == expected
