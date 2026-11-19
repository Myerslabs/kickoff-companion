"""Another game on one device (batch 3, owner 2026-11-16: "Stays on host's game, each client can view another game").

`GET /api/live/state?game=<id>` reads a game other than the room's for one device and is its heartbeat: the game is polled
alongside (app/live/side.py) only while asked for, at most three at once, and the room's game is never touched."""

from __future__ import annotations

import time
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.live import side as side_mod
from tests.test_any_team import SATURDAY, lclient  # noqa: F401 - the league client fixture


def games_on(lclient: TestClient) -> list:  # noqa: F811
    parts = lclient.portal.call(lclient.app.state.program._core)
    return [g for g in parts["games"].records if not g.completed and "Florida" not in (g.home_team, g.away_team) and g.start_date and datetime.fromisoformat(g.start_date.replace("Z", "+00:00")) <= SATURDAY]


def settle(lclient: TestClient) -> None:  # noqa: F811
    """Let the background polls the reads started finish."""
    sides = lclient.app.state.side_games

    async def wait():
        import asyncio

        for task in list(sides._tasks.values()):
            if not task.done():
                await asyncio.wait_for(task, 10)

    lclient.portal.call(wait)


def test_a_device_watches_another_game_and_the_room_stays(lclient: TestClient):  # noqa: F811
    on = games_on(lclient)
    assert on, "the league's week 4 has games under way"
    game = on[0]
    engine = lclient.app.state.live
    room_before = engine.current_game_id
    first = lclient.get(f"/api/live/state?game={game.id}&team={game.away_team}").json()["data"]
    assert first["side"] is True and first["gameId"] == game.id and first["team"] == game.away_team
    assert first.get("plays") and first.get("status") != "waiting", "the review (2026-11-19): the first answer waits for the first poll, so a live game never reads Pregame"
    settle(lclient)
    later = lclient.get(f"/api/live/state?game={game.id}&team={game.away_team}").json()["data"]
    assert later["plays"], "the side poll stored the game's plays"
    assert later["home"] == game.home_team and later["away"] == game.away_team
    assert engine.current_game_id == room_before, "the room's game is not moved"
    assert engine.followed is None, "nothing is followed for every screen"
    assert lclient.app.state.side_games.watching() == [game.id]


def test_a_poll_runs_at_most_every_thirty_seconds(lclient: TestClient):  # noqa: F811
    game = games_on(lclient)[0]
    sides = lclient.app.state.side_games
    for _ in range(4):
        lclient.get(f"/api/live/state?game={game.id}")
        settle(lclient)
    assert sides.polls == 1, "four reads within the half minute share one poll"


def test_a_fourth_game_is_told_which_are_on(lclient: TestClient, monkeypatch):  # noqa: F811
    on = games_on(lclient)
    assert len(on) >= 4
    for g in on[:3]:
        assert lclient.get(f"/api/live/state?game={g.id}").json()["data"]["status"] != "full"
    full = lclient.get(f"/api/live/state?game={on[3].id}").json()["data"]
    assert full["status"] == "full" and sorted(full["watching"]) == sorted(g.id for g in on[:3])
    settle(lclient)
    monkeypatch.setattr(side_mod, "IDLE_SECONDS", 0)  # nobody asked in a while: let go
    time.sleep(0.01)
    assert lclient.app.state.side_games.watching() == []
    assert lclient.get(f"/api/live/state?game={on[3].id}").json()["data"]["status"] != "full"


def test_unknown_future_and_unplayable_games_say_why(lclient: TestClient, monkeypatch):  # noqa: F811
    unknown = lclient.get("/api/live/state?game=999999999").json()["data"]
    assert unknown["status"] == "unknown"
    parts = lclient.portal.call(lclient.app.state.program._core)
    later = next(g for g in parts["games"].records if g.start_date and datetime.fromisoformat(g.start_date.replace("Z", "+00:00")) > SATURDAY.replace(day=30))
    assert lclient.get(f"/api/live/state?game={later.id}").json()["data"]["status"] == "pregame"
    game = games_on(lclient)[0]
    monkeypatch.setattr(lclient.app.state.cfbd.capabilities, "live_plays", False, raising=False)
    no_key = lclient.get(f"/api/live/state?game={game.id}").json()["data"]
    assert no_key["status"] == "unavailable" and "Tier 2" in no_key["reason"]


def test_the_rooms_own_game_is_the_rooms_state(lclient: TestClient):  # noqa: F811
    engine = lclient.app.state.live
    plain = lclient.get("/api/live/state").json()["data"]
    if engine.current_game_id is not None:
        same = lclient.get(f"/api/live/state?game={engine.current_game_id}").json()["data"]
        assert same.get("side") is not True and same.get("gameId") == plain.get("gameId")


# --- the review of 2026-11-19 -----------------------------------------------------------------------------------------


def test_a_final_side_game_is_not_polled_again(lclient: TestClient, monkeypatch):  # noqa: F811
    """A finished side game answers from its stored plays; nothing more is asked of CFBD for it."""
    from app.live.events import LiveEvent

    game = games_on(lclient)[0]
    sides = lclient.app.state.side_games
    store = lclient.app.state.live.store
    assert lclient.get(f"/api/live/state?game={game.id}").json()["data"].get("plays")
    settle(lclient)
    assert sides.polls == 1
    status = dict(store.latest(game.id, "status") or {})
    status["status"] = "final"
    store.append([LiveEvent("status", "status", game.id, SATURDAY, status, version=2)])
    monkeypatch.setattr(side_mod, "SIDE_POLL_SECONDS", 0)  # a poll would be due on every ask
    for _ in range(3):
        later = lclient.get(f"/api/live/state?game={game.id}").json()["data"]
        settle(lclient)
        assert later.get("plays") and later["side"] is True, "the stored plays answer"
    assert sides.polls == 1, "a final game is never polled again"
    assert game.id not in sides.watching() and game.id not in sides._tasks and game.id not in sides._teams, "its bookkeeping is let go"


def test_side_polls_are_plain_calls_not_the_rooms_live_lane(lclient: TestClient, monkeypatch):  # noqa: F811
    """A side game is optional: the quota guard's RESTRICTED mode holds it back (live=False) and its failures land on the
    general breaker, never the live lane the room's poll answers to."""
    game = games_on(lclient)[0]
    client = lclient.app.state.cfbd
    real = client.get
    seen: list[dict] = []

    async def spy(endpoint, params=None, **kwargs):
        seen.append({"endpoint": endpoint, **kwargs})
        return await real(endpoint, params, **kwargs)

    monkeypatch.setattr(client, "get", spy)
    lclient.get(f"/api/live/state?game={game.id}")
    settle(lclient)
    calls = [c for c in seen if c["endpoint"] == "/live/plays"]
    assert calls and all(c.get("live") is False and c.get("use_cache") is False for c in calls), calls
    assert client.lane(False) is client.breaker and client.lane(False) is not client.live_breaker


def test_shutdown_cancels_the_side_polls(lclient: TestClient, monkeypatch):  # noqa: F811
    import asyncio

    game = games_on(lclient)[0]
    sides = lclient.app.state.side_games
    started = []
    real = lclient.app.state.cfbd.get

    async def hang(endpoint, params=None, **kwargs):
        if endpoint != "/live/plays":
            return await real(endpoint, params, **kwargs)
        started.append(1)
        await asyncio.sleep(3600)

    monkeypatch.setattr(lclient.app.state.cfbd, "get", hang)
    monkeypatch.setattr(side_mod, "FIRST_WAIT_SECONDS", 0.01)
    assert lclient.get(f"/api/live/state?game={game.id}").json()["data"]["status"] == "waiting"
    task = sides._tasks[game.id]
    assert started and not task.done()
    lclient.portal.call(sides.close)
    assert task.cancelled() and sides._tasks == {}
    lclient.get(f"/api/live/state?game={game.id}")
    assert sides._tasks == {}, "no poll starts once closed"


def test_a_game_with_no_kickoff_time_stops_when_no_plays_come(lclient: TestClient, monkeypatch):  # noqa: F811
    from types import SimpleNamespace

    from app.cfbd.client import CfbdUnavailable

    sides = lclient.app.state.side_games
    ghost = SimpleNamespace(id=987654321, home_team="Texas", away_team="Rice", start_date=None)

    async def find(game_id):
        return ghost if game_id == ghost.id else None

    real = lclient.app.state.cfbd.get

    async def nothing(endpoint, params=None, **kwargs):
        if endpoint != "/live/plays":
            return await real(endpoint, params, **kwargs)
        raise CfbdUnavailable("no plays")

    now = [SATURDAY]
    monkeypatch.setattr(sides, "_game", find)
    monkeypatch.setattr(sides, "_clock", lambda: now[0])
    monkeypatch.setattr(lclient.app.state.cfbd, "get", nothing)
    monkeypatch.setattr(side_mod, "SIDE_POLL_SECONDS", 0)
    first = lclient.get(f"/api/live/state?game={ghost.id}").json()["data"]
    settle(lclient)
    assert first["status"] == "waiting"
    polls = sides.polls
    assert polls >= 1
    now[0] = SATURDAY + side_mod.QUIET + timedelta(minutes=1)
    done = lclient.get(f"/api/live/state?game={ghost.id}").json()["data"]
    settle(lclient)
    assert done["status"] == "noplays" and "postponed" in done["reason"], done
    lclient.get(f"/api/live/state?game={ghost.id}")
    settle(lclient)
    assert sides.polls == polls, "no more polls for a game that never sent a play"
    assert ghost.id not in sides.watching()
