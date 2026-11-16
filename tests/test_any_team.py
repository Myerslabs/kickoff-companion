"""FEAT-5 (owner 2026-10-25: "I want it to be for my team, but I also want to see every team the way I see my team"): any
FBS team's Season page, Pre-Game Program from its side, Roster and Recruiting, against the simulated league of real
schools, where every team has a season. Our own team keeps the front page and the notes runs."""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import quote

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.demo.sites import DemoSites
from app.demo.upstream import DemoUpstream
from app.logging_setup import configure_logging, shutdown_logging
from app.main import create_app
from tests.conftest import league

OTHER = "Texas"
SATURDAY = datetime(2026, 9, 26, 22, 0, tzinfo=timezone.utc)  # the league's week 4


@pytest.fixture
def lclient(settings: Settings):
    world = league()
    upstream = DemoUpstream(world, lambda: SATURDAY, tier=2)
    sites = DemoSites(world, lambda: SATURDAY)
    configure_logging(settings)
    application = create_app(settings, cfbd_transport=httpx.MockTransport(upstream.handler), feeds_transport=httpx.MockTransport(sites.handler), weather_transport=httpx.MockTransport(sites.handler))
    application.state.cfbd._clock = lambda: SATURDAY
    try:
        with TestClient(application, base_url="https://testserver") as client:
            client.portal.call(application.state.live.stop_background)
            yield client
    finally:
        shutdown_logging()


def other_game(client: TestClient, team: str = OTHER) -> dict:
    season = client.get(f"/api/season/overview?team={quote(team)}").json()["data"]
    games = [g for g in season["schedule"] if isinstance(g.get("gameId"), int) and g["opponent"]["school"] != "Florida"]
    assert games, "the league gives the team a season of its own"
    return games[0]


def test_another_teams_game_opens_from_its_side_and_its_notes_stay_read_only(lclient: TestClient):
    game = other_game(lclient)
    seen = lclient.get(f"/api/program/{game['gameId']}?team={quote(OTHER)}")
    assert seen.status_code == 200, seen.text[:300]
    data = seen.json()["data"]
    assert data["us"]["school"] == OTHER and data["them"]["school"] == game["opponent"]["school"] and data["ours"] is False
    other_side = lclient.get(f"/api/program/{game['gameId']}?team={quote(game['opponent']['school'])}").json()["data"]
    assert other_side["us"]["school"] == game["opponent"]["school"], "the same game from the other side"
    default = lclient.get(f"/api/program/{game['gameId']}").json()["data"]
    assert default["us"]["school"] in (OTHER, game["opponent"]["school"]), "no side asked for: the home side"
    leaders = lclient.get(f"/api/program/{game['gameId']}/leaders?team={quote(OTHER)}")
    assert leaders.status_code == 200
    assert lclient.get("/api/program/999999999").status_code == 404


def test_our_games_stay_ours(lclient: TestClient):
    nxt = lclient.get("/api/program/next").json()["data"]
    mine = lclient.get(f"/api/program/{nxt['game']['gameId']}").json()["data"]
    assert mine["us"]["school"] == "Florida" and mine["ours"] is True
    asked = lclient.get(f"/api/program/{nxt['game']['gameId']}?team=Florida").json()["data"]
    assert asked["us"]["school"] == "Florida" and asked["ours"] is True


def test_any_teams_roster_and_recruiting(lclient: TestClient):
    roster = lclient.get(f"/api/roster?team={quote(OTHER)}")
    assert roster.status_code == 200 and roster.json()["data"]["team"]["school"] == OTHER
    ours = lclient.get("/api/roster").json()["data"]
    assert ours["team"]["school"] == "Florida"
    recruiting = lclient.get(f"/api/recruiting?team={quote(OTHER)}")
    assert recruiting.status_code == 200
    for path in ("/api/roster", "/api/recruiting"):
        refused = lclient.get(f"{path}?team=No%20Such%20School")
        assert refused.status_code == 404 and refused.json()["errors"][0]["code"] == "unknown_team"


def test_the_nightly_warm_loads_our_teams_then_opponents_then_the_top_25_within_the_target(lclient: TestClient, monkeypatch):
    """ENH-27: once a night, after three, paced to the month's target; a closed pace stops it before it asks anything."""
    warm = lclient.app.state.warm
    order = lclient.portal.call(warm.teams)
    assert order[0] == "Florida" and len(order) == len(set(order)) and len(order) > 10, order[:12]
    night = datetime(2026, 9, 27, 3, 30).astimezone()
    assert warm.due(night) and not warm.due(night.replace(hour=2))

    async def few() -> list[str]:
        return order[:3]

    monkeypatch.setattr(warm, "teams", few)
    record = lclient.portal.call(warm.run, night)
    assert record["warmed"] == 3 and record["teams"] == 3 and record["stoppedBy"] is None
    assert not warm.due(night), "once a day"
    assert lclient.get("/api/season/overview?team=" + quote(order[1])).json()["meta"]["source"] in ("cache", "live")
    monkeypatch.setattr(lclient.app.state.cfbd.quota.settings, "monthly_call_target", 0)
    (lclient.app.state.settings.data_dir / "warm.json").unlink()
    held = lclient.portal.call(warm.run, night)
    assert held["warmed"] == 0 and held["calls"] == 0 and "target" in held["stoppedBy"]


def test_in_game_follows_another_game_and_comes_back_to_ours(lclient: TestClient):
    """FEAT-1: the host picks any FBS game; the engine follows it from the side asked for, keeps the choice across a
    restart, and follows ours again on Back to our game, or once that game is over."""
    from app.live.engine import LiveEngine

    app = lclient.app
    engine = app.state.live
    parts = lclient.portal.call(app.state.program._core)
    now = SATURDAY
    on = [g for g in parts["games"].records if not g.completed and "Florida" not in (g.home_team, g.away_team) and g.start_date
          and datetime.fromisoformat(g.start_date.replace("Z", "+00:00")) <= now]
    assert on, "the league's week 4 has games under way"
    game = on[0]
    asked = lclient.post("/api/live/follow", json={"gameId": game.id, "team": game.away_team})
    assert asked.status_code == 200, asked.text[:300]
    status = asked.json()["data"]
    assert status["followed"]["gameId"] == game.id and status["followed"]["team"] == game.away_team
    assert engine.window is not None and engine.window.game_id == game.id and engine.mode == "live"
    assert engine.side_for(game.id) == game.away_team and engine.side_for(None) == "Florida"
    assert engine.follow_path.is_file()
    again = LiveEngine(engine.client, engine.settings, app.state.db, clock=lambda: now)
    assert again.followed["gameId"] == game.id, "the choice survives a restart"
    home_side = lclient.post("/api/live/follow", json={"gameId": game.id, "team": "Nobody"}).json()["data"]
    assert home_side["followed"]["team"] in (game.home_team, game.away_team), "a side not in the game: the home side (or the FBS one)"
    assert lclient.post("/api/live/follow", json={"gameId": 999999999}).status_code == 404
    back = lclient.delete("/api/live/follow").json()["data"]
    assert back["followed"] is None and not engine.follow_path.exists()
    assert engine.window is None or engine.window.game_id != game.id
    nxt = lclient.get("/api/program/next").json()["data"]
    ours = lclient.post("/api/live/follow", json={"gameId": nxt["game"]["gameId"]}).json()["data"]
    assert ours["followed"] is None, "our own game id is ours again"
    finished = next(g for g in parts["games"].records if g.completed and "Florida" not in (g.home_team, g.away_team))
    engine.followed = {"gameId": finished.id, "team": finished.home_team, "home": finished.home_team, "away": finished.away_team}
    assert lclient.portal.call(engine._followed_window) is None and engine.followed is None, "a game long over: ours again"


def test_the_warm_loads_our_and_the_next_opponents_player_cards(lclient: TestClient, monkeypatch):
    """Batch 1 (owner 2026-11-15, "Fetch overnight"): after the warm, a card of our team or the next opponent asks CFBD
    nothing (each finished game's box and play value already kept)."""
    warm = lclient.app.state.warm

    async def none() -> list[str]:
        return []

    monkeypatch.setattr(warm, "teams", none)  # the pages' warm is the test above; this is the cards
    cards = lclient.portal.call(warm.card_teams)
    assert cards[0] == "Florida" and len(cards) == 2, cards
    record = lclient.portal.call(warm.run, datetime(2026, 9, 27, 3, 30).astimezone())
    assert record["cards"] == cards and record["stoppedBy"] is None

    def calls() -> int:
        return lclient.app.state.cfbd.quota.status(lclient.app.state.cfbd._clock()).ledger_calls_this_month

    before = calls()
    for school in cards:
        parts, completed = lclient.portal.call(lclient.app.state.players.card_parts, school)
        assert completed and any(name.startswith("ppaGames_") for name in parts), school
    assert calls() == before, "every card part already kept"
