"""Shared fixtures. Tests never read the real .env, never write outside tmp_path, and never
touch the network: the CFBD upstream is always a scripted fake. The one-port server tests in
test_serving.py use loopback only.

Since public release Phase 3 the CFBD answers come from the made-up league (app/demo), by the names
the private recordings had: load_fixture("games_team") is the demo team's schedule. The league is
built once per run (about ten seconds) and kept in pytest's cache folder. ROLES names the league's
stand-ins: ROLES["US"] the demo team, ROLES["OPP"] its next opponent, ROLES["LASTGAME"] its last
final game, and so on (app/demo/fixtures.py, roles)."""

from __future__ import annotations

import copy
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import PROJECT_ROOT, Settings, load_settings
from app.logging_setup import configure_logging, shutdown_logging
from app.main import create_app

# A distinctive fake key so tests can prove it never leaks into output.
TEST_KEY = "TESTKEY-" + "q7" * 20

# The demo team the tests follow (app/demo/names.py), and its conference.
TEAM = "Swampwater Tech"
CONFERENCE = "Biscuit Belt"
TEAM_FEED_URL = "https://swampwatertech.example.invalid/rss?path=football"  # the school's own feed (made-up host)

CACHE = PROJECT_ROOT / ".pytest_cache" / "demo-league"

ENV_KEYS = [
    "CFBD_API_KEY", "CFBD_BASE_URL", "TEAM", "SEASON", "CONFERENCE", "HOST", "PORT", "LAN_HOSTNAME", "TIMEZONE",
    "MONTHLY_CALL_BUDGET", "QUOTA_HARD_STOP_PCT", "LIVE_POLL_SECONDS", "RADIO_SOURCES", "LOG_LEVEL",
    "LOG_DIR", "DATA_DIR", "TEAM_FEED_URL", "MDNS_NAME",
]


_LEAGUE: dict[str, Any] = {}


def league() -> Any:
    """The made-up league the fixtures come from, built once per run."""
    if "world" not in _LEAGUE:
        from app.demo.fixtures import roles
        from app.demo.upstream import load_world

        _LEAGUE["world"] = load_world(cache_dir=CACHE)
        _LEAGUE["roles"] = roles(_LEAGUE["world"])
        _LEAGUE["twins"] = {}
    return _LEAGUE["world"]


class _Roles(dict):
    """ROLES["US"] and friends, filled on first use (building the league takes a few seconds)."""

    def __getitem__(self, key: str) -> str:
        league()
        return _LEAGUE["roles"][key]

    def get(self, key: str, default: Any = None) -> Any:
        league()
        return _LEAGUE["roles"].get(key, default)


ROLES = _Roles()


def role_int(key: str) -> int:
    return int(ROLES[key])


CATEGORIES = ("defensive", "interceptions", "kicking", "passing", "punting", "receiving", "rushing")


def team_player_stats(team: str) -> list[dict[str, Any]]:
    """/stats/player/season?team=<team> for any FBS team, from the national per-category answers
    (the league's next opponent is outside our conference, so the conference answer lacks it)."""
    return [row for category in CATEGORIES for row in fixture_payload(f"stats_player_season_all_{category}") if row.get("team") == team]


def load_fixture(name: str) -> dict[str, Any]:
    """The league's answer by a recording's name: {'endpoint', 'params', 'status', 'payload', ...}.
    A copy, so a test that changes it cannot change the next test's."""
    from app.demo.fixtures import league_fixture

    league()
    twins = _LEAGUE["twins"]
    if name not in twins:
        twins[name] = league_fixture(_LEAGUE["world"], name, values=_LEAGUE["roles"])
    return copy.deepcopy(twins[name])


def fixture_payload(name: str) -> Any:
    return load_fixture(name)["payload"]


class FakeCfbd:
    """A scripted CFBD upstream for httpx. Routes by path; records every request."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.routes: dict[str, Callable[[httpx.Request], httpx.Response]] = {}
        self.route("/info", json=fixture_payload("info"))

    def route(
        self,
        path: str,
        *,
        status: int = 200,
        json: Any = None,
        text: str | None = None,
        headers: dict[str, str] | None = None,
        sequence: list[httpx.Response] | None = None,
        handler: Callable[[httpx.Request], httpx.Response] | None = None,
    ) -> None:
        if handler is not None:
            self.routes[path] = handler
            return
        if sequence is not None:
            responses = list(sequence)
            state = {"index": 0}

            def next_response(_: httpx.Request) -> httpx.Response:
                response = responses[min(state["index"], len(responses) - 1)]
                state["index"] += 1
                return response

            self.routes[path] = next_response
            return
        kwargs: dict[str, Any] = {"headers": headers or {}}
        if json is not None:
            kwargs["json"] = json
        elif text is not None:
            kwargs["text"] = text
        self.routes[path] = lambda _: httpx.Response(status, **kwargs)

    def fixture(self, path: str, name: str) -> None:
        """Route a path to a recorded fixture, including a recorded error."""
        recorded = load_fixture(name)
        if recorded.get("status") == 200:
            self.route(path, json=recorded["payload"])
        else:
            self.route(path, status=int(recorded.get("status") or 500), text=recorded.get("body") or "")

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        route = self.routes.get(request.url.path)
        if route is None:
            return httpx.Response(404, json={"message": f"no fake route for {request.url.path}"})
        return route(request)

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)

    def count(self, path: str | None = None) -> int:
        return len([r for r in self.requests if path is None or r.url.path == path])


class FakeClock:
    def __init__(self, start: datetime | None = None) -> None:
        self.now = start or datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)  # a Monday

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs: float) -> None:
        self.now += timedelta(**kwargs)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make sure nothing in the developer's environment leaks into a test. TEAM and CONFERENCE are
    required settings, so every test starts with the demo team's (a test of a missing one deletes it)."""
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("TEAM", TEAM)
    monkeypatch.setenv("CONFERENCE", CONFERENCE)
    monkeypatch.setenv("TEAM_FEED_URL", TEAM_FEED_URL)
    monkeypatch.setenv("MDNS_NAME", "off")  # tests never announce on the network


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return load_settings(
        env_file=None,
        cfbd_api_key=TEST_KEY,
        team=TEAM,
        conference=CONFERENCE,
        log_dir=str(tmp_path / "logs"),
        data_dir=str(tmp_path / "data"),
    )


@pytest.fixture
def fake_cfbd() -> FakeCfbd:
    return FakeCfbd()


@pytest.fixture
def app(settings: Settings, fake_cfbd: FakeCfbd):
    configure_logging(settings)
    application = create_app(settings, cfbd_transport=fake_cfbd.transport)
    yield application
    shutdown_logging()


@pytest.fixture
def client(app: FastAPI):
    """A client that arrives over HTTPS, like a device that trusts the CA. The live engine's background
    loop is stopped: its schedule check at start would race any test that counts CFBD calls (a test of
    the loop starts it itself)."""
    with TestClient(app, base_url="https://testserver") as test_client:
        test_client.portal.call(app.state.live.stop_background)
        yield test_client


@pytest.fixture
def plain_client(app: FastAPI):
    """A client that arrives over plain HTTP, like a new device or an old bookmark."""
    with TestClient(app, base_url="http://testserver") as test_client:
        yield test_client


def route_depth2(fake: FakeCfbd) -> None:
    """The Phase 13 sources from the league. The opponent-adjusted metrics and SRS are still empty
    for the season early on, so last season's stand in for a season that has them."""
    import httpx

    fake.fixture("/ratings/core", "ratings_core")
    fake.fixture("/ratings/srs", "ratings_srs_2025")
    fake.fixture("/ratings/sp/conferences", "ratings_sp_conferences")
    fake.fixture("/wepa/team/season", "wepa_team_season_2025")
    fake.fixture("/wepa/players/passing", "wepa_players_passing_2025")
    fake.fixture("/wepa/players/rushing", "wepa_players_rushing_2025")
    fake.fixture("/wepa/players/kicking", "wepa_players_kicking")
    fake.fixture("/player/portal", "player_portal")
    fake.route("/recruiting/teams", handler=lambda r: httpx.Response(200, json=fixture_payload("recruiting_teams") if r.url.params.get("year") != ROLES["S+1"] else []))
    fake.fixture("/rushing/plays", "rushing_plays_opponent")
    fake.fixture("/passing/plays", "passing_plays_opponent")
    fake.fixture("/game/box/advanced", "game_box_advanced")
