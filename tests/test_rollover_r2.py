"""The season rollover's switch and the Seasons list (R2; owner 2026-11-15: "On its own, when 2027 is listed", "Restart as
soon as due", "Also wait for title game", "The book and its games"; once a day: "it will only happen once a year right?").
No network: the switch's questions are fakes, the book is asked of the app's own routes."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app import rollover_setup
from app.cfbd.models import Game
from app.services import rollover as R
from app.services.claude_schedule import Ledger, switch_slots
from tests.conftest import quiet_background

ET = ZoneInfo("America/New_York")
ROOT = Path(__file__).resolve().parents[1]
JAN21 = datetime(2027, 1, 21, 15, 0, tzinfo=timezone.utc)


def game(gid: int, start: str, notes: str | None, completed: bool) -> Game:
    return Game.model_validate({"id": gid, "season": 2026, "seasonType": "postseason", "startDate": start, "notes": notes, "completed": completed, "homeTeam": "A", "awayTeam": "B"})


def test_the_title_game_is_the_one_cfbd_names_the_national_championship():
    semis = [game(1, "2027-01-09T00:30:00.000Z", "College Football Playoff Semifinal at the Fiesta Bowl", True)]
    title = game(3, "2027-01-20T00:30:00.000Z", "College Football Playoff National Championship Presented by AT&T", False)
    assert R.title_game_final([*semis, title], JAN21) is False, "to be played"
    assert R.title_game_final([*semis, title.model_copy(update={"completed": True})], JAN21) is True
    assert R.title_game_final([], JAN21) is False, "nothing listed is never final"
    unnamed = [game(4, "2027-01-12T00:30:00.000Z", None, True), game(5, "2027-01-02T00:30:00.000Z", "Bowl", True)]
    assert R.title_game_final(unnamed, JAN21) is True, "none named: every game final, the last one three days old"
    assert R.title_game_final(unnamed, datetime(2027, 1, 13, tzinfo=timezone.utc)) is False, "too soon after the last"
    assert R.title_game_final([*unnamed, game(6, "2027-01-15T00:30:00.000Z", None, False)], JAN21) is False


class Fakes:
    def __init__(self) -> None:
        self.closed, self.title, self.listed, self.busy_with = True, True, True, None
        self.asked: list[str] = []
        self.kept: list[int] = []
        self.written: list[int] = []
        self.restarts: list[str] = []
        self.keep_fails = False

    def make(self, tmp_path: Path, season: int = 2026) -> R.Rollover:
        async def closed_out() -> bool:
            self.asked.append("closed")
            return self.closed

        async def title_final() -> bool | None:
            self.asked.append("title")
            return self.title

        async def next_listed(year: int) -> bool | None:
            self.asked.append(f"listed {year}")
            return self.listed

        async def keep(year: int) -> None:
            if self.keep_fails:
                raise RuntimeError("the season in review's players answered 503")
            self.kept.append(year)

        return R.Rollover(data_dir=tmp_path, season=season, tz=ET, closed_out=closed_out, title_final=title_final, next_listed=next_listed,
                          busy=lambda: self.busy_with, keep_book=keep, set_season=self.written.append, restart=self.restarts.append)


@pytest.fixture(autouse=True)
def no_notice():
    R.reset_notice()
    yield
    R.reset_notice()


def test_once_a_day_the_cheapest_question_first(tmp_path: Path):
    f = Fakes()
    f.closed = False
    roll = f.make(tmp_path)
    assert asyncio.run(roll.tick(JAN21)) == "Our 2026 season is not closed out yet."
    assert f.asked == ["closed"], "no CFBD question while the season is open"
    assert asyncio.run(roll.tick(JAN21 + timedelta(hours=3))) == "checked today"
    f.closed, f.title = True, False
    assert asyncio.run(roll.tick(JAN21 + timedelta(days=1))) == "The national title game is still to be played."
    f.title, f.listed = True, False
    assert asyncio.run(roll.tick(JAN21 + timedelta(days=2))) == "CFBD does not list our 2027 schedule yet."
    f.listed = None
    assert "could not be read" in asyncio.run(roll.tick(JAN21 + timedelta(days=3)))
    assert f.kept == [] and f.written == [] and f.restarts == []
    state = json.loads((tmp_path / "rollover.json").read_text(encoding="utf-8"))
    assert state["due"] is None and state["checkedOn"] == "2027-01-24" and "could not be read" in state["waiting"]


def test_a_due_switch_waits_for_a_run_then_keeps_the_book_writes_the_season_and_restarts(tmp_path: Path):
    f = Fakes()
    f.busy_with = "a Claude run is writing"
    roll = f.make(tmp_path)
    assert asyncio.run(roll.tick(JAN21)) == "waiting"
    assert roll.status()["due"] == 2027 and "a Claude run is writing" in roll.status()["waiting"] and f.restarts == []
    f.asked.clear()
    f.busy_with = None
    assert asyncio.run(roll.tick(JAN21 + timedelta(hours=1))) == "switched", "due stays due: the next hour tries again, no new check"
    assert f.asked == [] and f.kept == [2026] and f.written == [2027] and f.restarts == ["The season moved to 2027"]
    status = roll.status()
    assert status["due"] is None and status["switched"][-1]["from"] == 2026 and status["switched"][-1]["to"] == 2027
    assert R.switched_at(tmp_path, 2027) == JAN21 + timedelta(hours=1)
    assert R.load_notice(tmp_path, 2027, JAN21 + timedelta(days=2)) == {"switched": {"from": 2026, "to": 2027, "at": "2027-01-21T16:00:00Z"}}
    assert R.load_notice(tmp_path, 2027, JAN21 + timedelta(days=15)) is None, "two weeks, then the To do is quiet"


def test_a_failed_step_switches_nothing_and_says_why(tmp_path: Path):
    f = Fakes()
    f.keep_fails = True
    roll = f.make(tmp_path)
    assert asyncio.run(roll.tick(JAN21)) == "failed"
    assert f.written == [] and f.restarts == []
    failed = R.notice()
    assert failed is not None and failed["failed"]["to"] == 2027 and "players answered 503" in failed["failed"]["error"]
    assert R.load_notice(tmp_path, 2026) == failed, "a restart still says so"
    f.keep_fails = False
    assert asyncio.run(roll.tick(JAN21 + timedelta(hours=1))) == "switched"
    assert R.notice() is None and roll.status()["error"] is None


def test_an_unreadable_rollover_file_starts_again(tmp_path: Path):
    (tmp_path / "rollover.json").write_text("{not json", encoding="utf-8")
    assert R.RolloverStore(tmp_path).load() == {"checkedOn": None, "due": None, "waiting": None, "error": None, "switched": []}
    (tmp_path / "rollover.json").write_text(json.dumps({"due": "2027", "switched": [{"from": 2026}, "x", {"from": 2026, "to": 2027, "at": "2027-01-21T16:00:00Z"}]}), encoding="utf-8")
    loaded = R.RolloverStore(tmp_path).load()
    assert loaded["due"] is None and loaded["switched"] == [{"from": 2026, "to": 2027, "at": "2027-01-21T16:00:00Z"}]


def test_the_winter_runs_the_switch_came_too_late_for_run_once_after_it(tmp_path: Path):
    ledger = Ledger(tmp_path / "ledger.json")
    late = datetime(2027, 2, 20, 15, 0, tzinfo=timezone.utc)
    keys = {s.key: s for s in switch_slots(2027, late, ledger, ET)}
    assert "coaches:after-switch-2027" in keys and keys["coaches:after-switch-2027"].season == 2027
    assert "costs:after-switch-2027" not in keys, "May's costs are still to come"
    assert switch_slots(2027, datetime(2027, 1, 22, 15, 0, tzinfo=timezone.utc), ledger, ET) == [], "January's staffs still open: they run themselves"
    assert switch_slots(2027, None, ledger, ET) == []
    ledger.add({"key": "coaches:2026-12", "ok": False, "finishedAt": "2026-12-15T14:05:00Z"})
    assert switch_slots(2027, late, ledger, ET) == [], "December's run was tried: no second one"
    source = (ROOT / "app" / "schedule_setup.py").read_text(encoding="utf-8")
    assert "switched_at=lambda: switched_at(state.settings.data_dir, state.settings.season)" in source


def test_the_book_is_asked_of_the_apps_own_routes_and_read_back_by_season(app, client, monkeypatch, tmp_path: Path):
    monkeypatch.setattr(rollover_setup, "BOOK_PARTS", {"overview": "/api/seasons", "players": "/api/seasons", "blame": "/api/no-such-route"})
    kept = client.portal.call(rollover_setup.keep_book, app, 2025)
    assert kept == ["overview", "players"], "a part that does not answer is left out"
    listed = client.get("/api/seasons").json()["data"]
    assert listed["current"] == 2026 and [r["season"] for r in listed["seasons"]] == [2026, 2025]
    past = listed["seasons"][1]
    assert past["book"] is True and past["href"] == "#review=2025" and past["current"] is False
    answer = client.get("/api/seasons/2025/book/overview")
    assert answer.status_code == 200 and answer.json()["data"]["current"] == 2026 and answer.json()["meta"]["source"] == "cache"
    assert client.get("/api/seasons/2025/book/blame").json()["errors"][0]["code"] == "not_kept"
    assert client.get("/api/seasons/2026/book/overview").json()["errors"][0]["code"] == "current_season"
    assert client.get("/api/seasons/2025/book/..%2Fsettings").status_code == 404
    monkeypatch.setattr(rollover_setup, "BOOK_PARTS", {"overview": "/api/no-such-route"})
    with pytest.raises(RuntimeError, match="overview answered 404"):
        client.portal.call(rollover_setup.keep_book, app, 2024)


def test_the_envelope_carries_the_switch_and_the_app_wires_it(client):
    meta = client.get("/api/seasons").json()["meta"]
    assert "seasonSwitch" in meta and meta["seasonSwitch"] is None
    main = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    assert "rollover=lambda now: None if app.state.demo_mode or app.state.rollover is None else app.state.rollover.tick(now)" in main
    maint = (ROOT / "app" / "maintenance.py").read_text(encoding="utf-8")
    assert "if self.rollover is not None and not self.window_open():" in maint


def test_without_an_env_file_the_season_cannot_be_written(app):
    roll = rollover_setup.build_rollover(app)
    if app.state.settings.env_path is None:
        with pytest.raises(RuntimeError, match="no .env file"):
            roll.set_season(2027)
    else:
        roll.set_season(2027)
        assert "SEASON=2027" in Path(app.state.settings.env_path).read_text(encoding="utf-8")


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_a_past_seasons_game_is_read_from_its_kept_files_alone(app, client, fake_cfbd):
    data_dir = Path(app.state.settings.data_dir)
    program = {"game": {"gameId": 9001, "completed": True, "week": 4}, "us": {"school": "Florida"}, "them": {"school": "Texas State"}, "ours": True}
    _write(data_dir / "season" / "2025" / "postgame" / "9001.json", {"gameId": 9001, "lockedAt": "2025-09-28T15:00:00Z", "program": program, "news": []})
    _write(data_dir / "season" / "2025" / "program" / "9002.json", {"gameId": 9002, "lockedAt": "2025-10-04T19:30:00Z", "program": {**program, "game": {"gameId": 9002, "completed": False}}})
    _write(data_dir / "season" / "2025" / "writing" / "recap-9001.json", {"headline": "Florida ran away with it", "writtenAt": "2025-09-28T12:00:00Z"})
    quiet_background(app, client)
    calls = len(fake_cfbd.requests)
    closed = client.get("/api/seasons/2025/game/9001").json()
    assert closed["data"]["past"] == 2025 and closed["data"]["keptFrom"] == "postgame" and closed["meta"]["source"] == "cache"
    assert client.get("/api/seasons/2025/game/9002").json()["data"]["keptFrom"] == "kickoff", "no Post-Game lock: the program as it stood at kickoff"
    assert client.get("/api/seasons/2025/game/9003").json()["errors"][0]["code"] == "not_kept"
    assert client.get("/api/seasons/2026/game/9001").json()["errors"][0]["code"] == "current_season"
    assert client.get("/api/program/9001/postgame?season=2025").status_code == 200
    assert client.get("/api/program/9001/postgame").status_code == 404, "without the season: this season's folder"
    assert client.get("/api/program/9002/locked?season=2025").json()["data"]["gameId"] == 9002
    recap = client.get("/api/writing/recap/9001?season=2025").json()["data"]
    assert recap["written"]["headline"] == "Florida ran away with it" and recap["commandFound"] is False and recap["running"] is False
    assert client.get("/api/writing/recap/9001").json()["data"]["written"] is None
    assert len(fake_cfbd.requests) == calls, "a past season's game makes no CFBD call"


def test_the_pages_read_a_past_season_by_its_own_addresses():
    past = (ROOT / "static" / "js" / "ui" / "past.js").read_text(encoding="utf-8")
    assert "`#program=${id}?tab=pre&season=${season}`" in past and "`#postgame=${id}?season=${season}`" in past and "`#archive=${id}`" in past
    program = (ROOT / "static" / "js" / "views" / "program.js").read_text(encoding="utf-8")
    assert "`/api/seasons/${state.past}/game/${encodeURIComponent(state.gameId)}`" in program
    assert "withSeason(`/api/program/${encodeURIComponent(text(id))}/locked`, state.past)" in program
    assert "...(past ? archiveLate(data) : postLate(data))" in program and "ours && !past ? blameHost(state) : null" in program
    season = (ROOT / "static" / "js" / "views" / "season.js").read_text(encoding="utf-8")
    assert 'url: pastSeason ? bookUrl(pastSeason, "overview")' in season and 'createBlameView({ embedded: true, url: bookUrl(season, "blame"), kept: true })' in season
    app_js = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
    assert "past: pastYear(arg)" in app_js and "seasons: (opts) => createSeasonsView(opts)" in app_js and 'addEventListener("kickoff:season-switch"' in app_js
    demo = (ROOT / "app" / "demo" / "run.py").read_text(encoding="utf-8")
    assert "state.demo_mode = True" in demo, "the test league never switches a season"
