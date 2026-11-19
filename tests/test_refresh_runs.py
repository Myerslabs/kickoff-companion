"""Run with Claude's queue (batch 4 part 3, owner 2026-11-19): every Claude piece of a page, inside its window, one after
another through its own runner with what it holds now, each leaving a line in the log; busy, closed and empty pages say why.
No network and no Claude Code: the runners are stand-ins."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.cfbd.models import Game
from app.refresh_setup import RefreshRuns
from app.services.page_refresh import Page, RefreshLog
from app.services.writing import WritingStore

ET = timezone(timedelta(hours=-5))
NOW = datetime(2026, 11, 19, 12, 0, tzinfo=ET)


def game(gid: int, week: int, kickoff: datetime, completed: bool) -> Game:
    return Game(id=gid, season=2026, week=week, season_type="regular", start_date=kickoff.isoformat(), completed=completed, home_team="Florida", away_team="Vanderbilt", venue_id=3949, home_points=21 if completed else None, away_points=14 if completed else None)


PLAYED = game(11, 11, datetime(2026, 11, 14, 12, 0, tzinfo=ET), True)
NEXT = game(12, 12, datetime(2026, 11, 21, 12, 0, tzinfo=ET), False)


class Runner:
    """A writing runner that finishes at once and saves what the job's save() is given."""

    def __init__(self) -> None:
        self.running = False
        self.saved = False
        self.error: str | None = None
        self.changed: bool | None = None
        self.jobs: list[Any] = []

    async def start(self, job: Any, command: str, model: Any = None) -> dict[str, Any]:
        self.jobs.append(job)
        self.saved = bool(job.save({"summary": f"refreshed {job.kind}"}))
        self.changed = self.saved
        return {"running": False}


class Notes(Runner):
    async def start(self, info: dict[str, Any], command: str, mode: str = "full", model: Any = None) -> dict[str, Any]:  # type: ignore[override]
        self.jobs.append((info, mode))
        self.saved = True
        return {"running": False}


def make(tmp_path: Path, *, found: bool = True, games: list[Game] | None = None) -> tuple[RefreshRuns, SimpleNamespace]:
    settings = SimpleNamespace(data_dir=tmp_path, season=2026, team="Florida", tzinfo=ET, claude_command="claude" if found else "", claude_lookup_model=None)
    schedule = games if games is not None else [PLAYED, NEXT]
    program = SimpleNamespace(year=2026, team="Florida", _pick_game=lambda records, gid: next((g for g in records if g.id == gid), None) if gid else next((g for g in records if not g.completed), None))
    state = SimpleNamespace(settings=settings, program=program, writing=Runner(), notes=Notes(), season_runner=SimpleNamespace(running=False, batches=[], error=None), prompt_runs=SimpleNamespace(running=False), jobs=SimpleNamespace(running=False, current=None))
    runs = RefreshRuns(SimpleNamespace(state=state))
    runs.poll_seconds = 0.01

    async def schedule_of() -> list[Game]:
        return schedule

    runs._schedule = schedule_of  # type: ignore[method-assign]
    runs.command_found = lambda: found  # type: ignore[method-assign]
    return runs, state


@pytest.fixture
def jobs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> list[tuple[str, str]]:
    """build_job stands in: a job for every kind but the weekly review (standing in for a piece with nothing to write from yet: skipped), saving to the writing store."""
    asked: list[tuple[str, str]] = []
    store = WritingStore(tmp_path, 2026)

    async def build_job(app: Any, kind: str, key: str) -> Any:
        asked.append((kind, key))
        if kind == "review":
            return None
        return SimpleNamespace(kind=kind, key=key, so_far=None, save=lambda answer: store.save(kind, key, answer))

    monkeypatch.setattr("app.writing_setup.build_job", build_job)

    async def with_figures(state: Any, info: dict[str, Any]) -> dict[str, Any]:
        return info

    monkeypatch.setattr("app.api.notes.with_figures", with_figures)
    return asked


def run(coro: Any) -> Any:
    return asyncio.run(coro)


async def finish(runs: RefreshRuns) -> None:
    for _ in range(500):
        if not runs.running:
            return
        await asyncio.sleep(0.01)
    raise AssertionError("the queue never finished")


def test_the_pre_game_refreshes_every_piece_with_what_it_holds(tmp_path: Path, jobs: list[tuple[str, str]]) -> None:
    runs, state = make(tmp_path)
    WritingStore(tmp_path, 2026).save("scout", "12", {"summary": "Vandy is solid."})

    async def go() -> dict[str, Any]:
        status = await runs.start("#program=12", NOW)
        await finish(runs)
        return status

    status = run(go())
    assert not status.get("error"), status
    kinds = [s["kind"] for s in runs.status()["steps"]]
    assert kinds == ["notes", "scout", "trivia", "numbers", "trip"]
    assert all(s["state"] == "done" for s in runs.status()["steps"]), runs.status()["steps"]
    assert state.notes.jobs[0][1] == "full", "the full notes run, which carries the notes so far"
    scout = next(j for j in state.writing.jobs if j.kind == "scout")
    assert scout.so_far and scout.so_far.get("summary") == "Vandy is solid.", "the piece as it stands goes with the run"
    assert ("numbers", "week-12") in jobs and ("trip", "3949") in jobs
    rows = RefreshLog(tmp_path).rows()
    assert [r["piece"] for r in rows] == kinds, "a line a piece"
    scout_row = next(r for r in rows if r["piece"] == "scout")
    assert scout_row["route"] == "#program=12" and scout_row["changes"]["changed"] >= 1, scout_row
    assert runs.status()["label"] == "The Pre-Game Program"


def test_the_post_game_skips_what_has_nothing_to_write_from(tmp_path: Path, jobs: list[tuple[str, str]]) -> None:
    runs, _state = make(tmp_path)
    called: list[str] = []

    def blame() -> Any:
        from app.refresh_setup import Piece

        async def start() -> dict[str, Any]:
            called.append("blame")
            return {"running": False}

        return Piece("blame", "The Circle of Blame", start, lambda: {"running": False, "ok": True}, lambda: None)

    runs._blame_piece = blame  # type: ignore[method-assign]
    later = NOW.replace(day=15)  # the Sunday after Week 11: the Post-Game still open

    async def go() -> None:
        await runs.start("#postgame=11", later)
        await finish(runs)

    run(go())
    steps = {s["kind"]: s for s in runs.status()["steps"]}
    assert list(steps) == ["recap", "review", "blame"], "the blame too: Week 11 is our latest final"
    assert steps["review"]["state"] == "skipped" and "nothing to write from" in steps["review"]["detail"]
    assert steps["recap"]["state"] == "done" and called == ["blame"]


def test_closed_windows_and_empty_pages_say_why(tmp_path: Path, jobs: list[tuple[str, str]]) -> None:
    runs, _state = make(tmp_path)
    shut = run(runs.check("#postgame=11", NOW))  # Thursday after the game: kept on Monday
    assert not shut["available"] and "Monday" in shut["reason"]
    kicked = run(runs.check("#program=12", NEXT_KICK_AFTER))
    assert not kicked["available"] and "kickoff" in kicked["reason"]
    assert run(runs.check("#standings", NOW))["reason"] == "Claude wrote nothing on this page."
    assert not run(runs.check("#program=999", NOW))["available"]
    started = run(runs.start("#postgame=11", NOW))
    assert started["error"] and not started["running"], "a closed window never starts a run"
    assert RefreshLog(tmp_path).rows() == [], "nothing ran, nothing logged"


NEXT_KICK_AFTER = datetime(2026, 11, 21, 12, 1, tzinfo=ET)


def test_the_row_line_and_the_command(tmp_path: Path, jobs: list[tuple[str, str]]) -> None:
    runs, _state = make(tmp_path)
    open_now = run(runs.check("#program=12", NOW))
    assert open_now["available"] and open_now["detail"] == "Refresh this week's notes, the scouting report, the trivia, by the numbers and getting there"
    off, _ = make(tmp_path, found=False)
    assert "not found" in run(off.check("#program=12", NOW))["reason"]


def test_one_run_at_a_time(tmp_path: Path, jobs: list[tuple[str, str]]) -> None:
    runs, state = make(tmp_path)
    state.writing.running = True
    busy = run(runs.start("#program=12", NOW))
    assert busy["error"] and "busy" in busy["error"]
    state.writing.running = False
    state.jobs.running = True
    assert "busy" in run(runs.start("#program=12", NOW))["error"], "a weekly job counts as busy"


def test_a_broken_schedule_hides_the_row(tmp_path: Path) -> None:
    runs, _state = make(tmp_path)

    async def broken() -> list[Game]:
        raise RuntimeError("CFBD is down")

    runs._schedule = broken  # type: ignore[method-assign]
    out = run(runs.check("#program=12", NOW))
    assert not out["available"] and "CFBD is down" in out["reason"]


def test_trivia_and_the_page_kinds(tmp_path: Path, jobs: list[tuple[str, str]]) -> None:
    runs, _state = make(tmp_path)
    out = run(runs.check("#trivia", NOW))
    assert out["available"] and out["detail"] == "Refresh the trivia"
    assert Page("trivia").label == "The trivia"


def test_the_api_is_the_hosts(client: Any) -> None:
    """The menu's row asks GET /api/refresh; a guest's answer is never available and a guest's POST is refused."""
    quiet = client.get("/api/refresh", params={"route": "#standings"}).json()["data"]
    assert quiet["available"] is False and quiet["reason"] == "Claude wrote nothing on this page."
    assert client.post("/api/refresh/run", json={"route": "#standings"}).status_code == 409
    client.app.state.host_access.set_pin("4321")
    guest = client.get("/api/refresh", params={"route": "#program"}).json()["data"]
    assert guest["available"] is False and guest["reason"] == "View only."
    refused = client.post("/api/refresh/run", json={"route": "#program"})
    assert refused.status_code == 403 and refused.json()["errors"][0]["code"] == "view_only"


def test_two_taps_start_one_queue(tmp_path: Path, jobs: list[tuple[str, str]]) -> None:
    """The reviewer's find: two starts at once both passed the busy check before either queue existed."""
    runs, _state = make(tmp_path)

    async def go() -> list[dict[str, Any]]:
        both = await asyncio.gather(runs.start("#program=12", NOW), runs.start("#program=12", NOW))
        await finish(runs)
        return list(both)

    first, second = run(go())
    assert not first.get("error") and second["error"] in ("Claude is already starting a refresh.", "Claude is already refreshing a page."), second
    assert len(RefreshLog(tmp_path).rows()) == 5, "one queue: a line a piece, once"


def test_a_busy_runner_is_no_start(tmp_path: Path, jobs: list[tuple[str, str]]) -> None:
    """A runner busy with another job refuses with running: True; the piece fails, never credited with that job's result."""
    runs, state = make(tmp_path)

    async def refuse(job: Any, command: str, model: Any = None) -> dict[str, Any]:
        return {"running": True, "error": "a run is already going"}

    state.writing.start = refuse

    async def go() -> None:
        await runs.start("#program=12", NOW)
        await finish(runs)

    run(go())
    steps = {s["kind"]: s for s in runs.status()["steps"]}
    assert steps["scout"]["state"] == "failed" and "already going" in steps["scout"]["error"]
    lines = [r for r in RefreshLog(tmp_path).rows() if r["piece"] == "scout"]
    assert len(lines) == 1 and lines[0]["ok"] is False and lines[0]["changes"] is None


def test_the_post_game_window_is_local(tmp_path: Path, jobs: list[tuple[str, str]]) -> None:
    """A 7:30 PM Saturday kick is Sunday in UTC; the window still closes at 6 AM local on Monday, not 1 AM."""
    late = Game(id=21, season=2026, week=12, season_type="regular", start_date="2026-11-22T00:30:00.000Z", completed=True, home_team="Florida", away_team="Vanderbilt", home_points=21, away_points=14)
    runs, _state = make(tmp_path, games=[late])
    two_am = datetime(2026, 11, 23, 2, 0, tzinfo=ET)
    assert run(runs.check("#postgame=21", two_am))["available"], "still open at 2 AM Monday local"
    assert not run(runs.check("#postgame=21", datetime(2026, 11, 23, 6, 0, tzinfo=ET)))["available"]


def test_the_editor_is_asked_with_the_layout_the_page_shows(tmp_path: Path, jobs: list[tuple[str, str]], monkeypatch: pytest.MonkeyPatch) -> None:
    runs, state = make(tmp_path)
    WritingStore(tmp_path, 2026).save("editor", "week-12", {"lead": "story-1"})

    async def paper_week(app: Any) -> tuple[str, list[Any], dict[str, Any]]:
        return "week-12", [], {}

    monkeypatch.setattr("app.writing_setup.paper_week", paper_week)

    async def go() -> None:
        await runs.start("#newspaper", NOW)
        await finish(runs)

    run(go())
    editor = next(j for j in state.writing.jobs if j.kind == "editor")
    assert editor.key == "2026-11-19-12" and editor.so_far and editor.so_far.get("lead") == "story-1"
    kinds = [s["kind"] for s in runs.status()["steps"]]
    assert kinds == ["paper", "editor", "art", "numbers"]
