"""The season rollover, first wave (owner 2026-11-15, "Start them in the order 1,2,3,4"; the answers: the switch on its own once
2027 is listed, the 2027 Magazine early, a weekly off-season paper, a Seasons list). Before the bowl: the bowl's runs keyed by
its edition, never Week 1's; the next season's staffs and costs wait for the app to be on it; no preseason load before
August; the weekly jobs wait for a new season's rosters; lessons carry their season; the backups take what they left out;
the tests' season pinned. No network."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from app.maintenance import _backup_members
from app.services.claude_schedule import ClaudeSchedule, Ledger, season_slots, week_slots
from app.services.writing import LEGACY_SEASON, Lessons

ET = ZoneInfo("America/New_York")
ROOT = Path(__file__).resolve().parents[1]
BOWL = datetime(2026, 12, 30, 20, 0, tzinfo=timezone.utc)  # a Wednesday bowl


def test_a_bowls_paper_numbers_and_picks_are_keyed_by_its_edition_never_week_1():
    slots = {s.kind: s for s in week_slots(402, BOWL, ET, week=1, season_type="postseason")}
    for kind in ("numbers", "paper", "picks"):
        if kind in slots:
            assert slots[kind].writing_key == "postseason" and slots[kind].key == f"{kind}:postseason", kind
    regular = {s.kind: s for s in week_slots(401, datetime(2026, 9, 5, 23, 0, tzinfo=timezone.utc), ET, week=1)}
    assert regular["paper"].writing_key == "week-1" and regular["numbers"].key == "numbers:week-1", "a regular Week 1 keeps its key"
    assert not any(s.kind in ("paper", "numbers", "picks") for s in week_slots(403, BOWL, ET, week=None, season_type="regular")), "no week: no paper runs"
    setup = (ROOT / "app" / "writing_setup.py").read_text(encoding="utf-8")
    assert 'key != key_for(game.get("week"), game.get("seasonType"))' in setup, "By the numbers' week check knows a bowl"


def test_the_next_seasons_staffs_and_costs_are_for_the_next_season():
    by = {(s.kind, s.at.astimezone(ET).month): s for s in season_slots(2026, ET)}
    assert by[("season", 8)].season == 2026, "August's load is the season's own"
    assert by[("coaches", 12)].season == 2027 and by[("coaches", 1)].season == 2027 and by[("costs", 1)].season == 2027 and by[("costs", 5)].season == 2027


def schedule(tmp_path: Path, season: int, now: datetime) -> ClaudeSchedule:
    async def nothing():
        return None

    async def current(slot):
        return False

    async def start(slot, game):
        return {"running": True}

    return ClaudeSchedule(ledger=Ledger(tmp_path / f"ledger-{season}.json"), enabled=lambda: True, command_found=lambda: True, current_game=nothing, last_game=nothing,
                          writing=False, season=lambda: season, tz=ET, data_is_current=current, start=start, poll=lambda slot: {"running": False, "ok": True}, clock=lambda: now)


def test_a_run_for_the_next_season_waits_while_the_app_is_on_this_one(tmp_path: Path):
    dec16 = datetime(2026, 12, 16, 15, 0, tzinfo=timezone.utc)
    on_2026 = schedule(tmp_path, 2026, dec16)
    assert on_2026.due(None, dec16) is None, "December's staffs are 2027's: never written over 2026's"
    jan21 = datetime(2027, 1, 21, 15, 0, tzinfo=timezone.utc)
    on_2027 = schedule(tmp_path, 2027, jan21)
    due = on_2027.due(None, jan21)
    assert due is not None and due.kind == "coaches" and due.season == 2027, "once the app is on 2027 they run"
    assert asyncio.run(on_2026.tick()) == "nothing due"


def test_no_preseason_load_before_august_of_its_season():
    setup = (ROOT / "app" / "schedule_setup.py").read_text(encoding="utf-8")
    block = setup[setup.index('if kind == "preseason":'):setup.index('if kind == "preseason":') + 600]
    assert "date(state.settings.season, 8, 1)" in block and "return None" in block


def test_the_weekly_jobs_wait_for_a_new_seasons_rosters():
    job = (ROOT / "app" / "jobs" / "talent_edge.py").read_text(encoding="utf-8")
    assert 'raise JobSkipped(f"CFBD has no {self.season} FBS roster yet' in job and "has no players" not in job


def test_a_lesson_keeps_its_season_and_the_prompt_reads_the_seasons_own(tmp_path: Path):
    path = tmp_path / "claude" / "lessons.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"lessons": [{"text": "An old 2026 lesson.", "gameId": 1, "at": "2026-10-01T00:00:00Z"}], "additions": [{"id": "a1", "text": "A rule.", "active": True}]}), encoding="utf-8")
    assert LEGACY_SEASON == 2026
    Lessons(tmp_path, 2027).add_review(9, {"lessons": ["A 2027 lesson."]})
    saved = json.loads(path.read_text(encoding="utf-8"))["lessons"]
    assert saved[-1]["season"] == 2027 and "season" not in saved[0]
    assert Lessons(tmp_path, 2027).for_prompt() == (["A 2027 lesson."], ["A rule."]), "the rules carry over; 2026's lessons do not"
    assert Lessons(tmp_path, 2026).for_prompt()[0] == ["An old 2026 lesson."], "a lesson written before seasons were kept is 2026's"
    assert Lessons(tmp_path).for_prompt()[0] == ["An old 2026 lesson.", "A 2027 lesson."], "no season asked: every lesson, as before"


def test_the_backups_take_what_they_left_out(tmp_path: Path):
    data = tmp_path / "data"
    for name in ("claude/lessons.json", "claude/ledger.json", "facts.json", "jobs.json", "trivia.json", "trivia-2025.json", "season/2026/x.json", "settings.json"):
        (data / name).parent.mkdir(parents=True, exist_ok=True)
        (data / name).write_text("{}", encoding="utf-8")
    kept = {p.relative_to(data).as_posix() for p in _backup_members(data)}
    assert {"claude/lessons.json", "claude/ledger.json", "facts.json", "jobs.json", "trivia.json", "trivia-2025.json", "season/2026/x.json", "settings.json"} <= kept


def test_the_tests_season_is_pinned(settings):
    assert settings.season == 2026, "the fixtures are 2026's; the calendar would move the suite to 2027 on March 1"
