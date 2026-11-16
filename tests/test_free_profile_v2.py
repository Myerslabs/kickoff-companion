"""Kickoff Companion 2.0 (batch 2): the Free profile again, on top of everything added since 1.0. A Free key's month keeps a
third for the pages someone opens; the cache keeps the lifetimes from before ENH-27; the nightly warm never runs on it;
Talent Edge is rebuilt every four weeks, not every week. A paid key runs as before."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

from app.cache import DataKind, ttl_for
from app.config import load_settings
from app.jobs import JobRuns
from app.jobs.weekly import WeeklyJobs
from app.services.warm import NightlyWarm
from tests.conftest import TEST_KEY

THURSDAY = datetime(2026, 10, 15, 12, 0)
MONDAY = datetime(2026, 10, 12, 12, 0)


def test_the_free_profile_keeps_the_lifetimes_from_before_enh_27():
    assert ttl_for(DataKind.SCHEDULE, MONDAY) == timedelta(hours=1)
    assert ttl_for(DataKind.SCHEDULE, MONDAY, lean=True) == timedelta(hours=12), "Sunday to Wednesday: twice a day"
    assert ttl_for(DataKind.SCHEDULE, THURSDAY, lean=True) == timedelta(hours=1)
    assert ttl_for(DataKind.SCHEDULE, THURSDAY, game_day=True, lean=True) == timedelta(minutes=15), "game day as before"
    assert ttl_for(DataKind.SEASON_STATS, MONDAY, lean=True) == timedelta(hours=6)
    assert ttl_for(DataKind.LINES, MONDAY, lean=True) == timedelta(hours=3)
    assert ttl_for(DataKind.LINES, MONDAY, game_day=True, lean=True) == timedelta(minutes=30)
    assert ttl_for(DataKind.LINES, MONDAY) == timedelta(hours=1), "a paid key keeps ENH-27's"


class _Quota:
    def __init__(self, budget: int) -> None:
        self.budget = budget

    def status(self, now: datetime) -> Any:
        return SimpleNamespace(budget=self.budget)


def _client(tier: int | None, budget: int) -> Any:
    return SimpleNamespace(capabilities=SimpleNamespace(tier_level=tier), quota=_Quota(budget), _clock=lambda: datetime.now(timezone.utc), settings=SimpleNamespace(season=2026))


def test_the_nightly_warm_never_runs_on_a_free_key(tmp_path):
    def warm(client: Any) -> NightlyWarm:
        return NightlyWarm(tmp_path, client, season=None, players=None, program=None, team_set=lambda: [])

    late = datetime(2026, 10, 15, 23, 30)
    assert warm(_client(2, 30000)).due(late) is True, "Tier 2: the warm runs after its hour"
    assert warm(_client(0, 1000)).due(late) is False, "Free: never"
    assert warm(_client(1, 5000)).due(late) is False, "Tier 1 runs the Free profile"
    assert warm(SimpleNamespace(settings=SimpleNamespace(season=2026))).due(late) is True, "a client without a plan runs the full profile"


def test_talent_edge_waits_four_weeks_on_a_free_key(tmp_path):
    now = datetime.now(timezone.utc)
    clock = {"at": now - timedelta(days=10)}  # the first run, ten days ago: before this week's Sunday slot
    runs = JobRuns(tmp_path, clock=lambda: clock["at"])
    done: list[str] = []

    async def talent() -> dict[str, Any]:
        done.append("talent")
        return {"message": "built", "week": 8}

    async def other() -> dict[str, Any]:
        done.append("other")
        return {"message": "built", "week": 8}

    lean = {"on": True}
    jobs = WeeklyJobs(runs, 2026, {"talent-edge": talent, "imperialism": other}, lean=lambda: lean["on"], lean_every={"talent-edge": timedelta(days=28)})
    asyncio.run(jobs._all())
    assert done == ["talent", "other"], "the first run builds both"
    clock["at"] = now
    done.clear()
    result = asyncio.run(jobs._all())
    assert done == ["other"], "this week, on a free key: Talent Edge kept, the map built"
    kept = next(r for r in result["jobs"] if r["job"] == "talent-edge")
    assert kept["kept"] and "every 28 days" in kept["message"]
    lean["on"] = False
    clock["at"] = now + timedelta(days=8)
    done.clear()
    asyncio.run(jobs._all())
    assert "talent" in done, "a paid key builds it every week"


def test_the_target_is_two_thirds_of_a_free_month(tmp_path):
    from app.cfbd.quota import QuotaGuard
    from app.db import Database

    settings = load_settings(env_file=None, cfbd_api_key=TEST_KEY, monthly_call_budget=1000)
    db = Database(tmp_path / "q.db")
    try:
        assert QuotaGuard(db, settings).status(datetime(2026, 10, 15, 12, tzinfo=timezone.utc)).target == 666
    finally:
        db.close()
