"""Public release Phase 5b: primary and secondary teams. The home team (primary #1) alone themes the app and
drives Season, Game program and Live; up to four more primaries get their team pages warmed when a device
connects; secondary schools, conferences and states fill the My teams ticker, the My teams page and the My
teams scope of a ranked list. All of it needs a Tier 2 key and none of it costs a call a page would not make.
Also: the opponents scope (every plan), and radio for any team (saved stations, the repo list, the help
links and the GitHub request form)."""

from __future__ import annotations

import json
import time
from datetime import timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import restart
from app.cfbd.models import Game, Team, parse_records
from app.services import stations, teamset
from app.services.prefs import Prefs
from tests.conftest import TEST_KEY, FakeCfbd, fixture_payload
from tests.test_national import load_pages, route_all
from tests.test_phase8 import KICKOFF, quiet_engine, route_week, set_clock
from tests.test_welcome import NEW_KEY, info, setup_app  # noqa: F401 (setup_app is a fixture)

HOME = "Florida"
OPPONENT = "Texas State"  # week 4, on our schedule
SLATE_SCHOOL = "Houston"  # plays in week 4, not us
OTHER_CONF = "Big Ten"
STATE = "CO"
TEAMS = parse_records(Team, fixture_payload("teams_fbs"), context="test").records
GAMES = parse_records(Game, fixture_payload("games_team"), context="test").records


def in_conference(conference: str) -> set[str]:
    return {t.school for t in TEAMS if t.conference == conference}


def in_state(state: str) -> set[str]:
    return {t.school for t in TEAMS if teamset.state_of(t) == state}


def tier(app, level: int) -> None:
    app.state.cfbd.capabilities.tier_level = level


# --- the team set ---------------------------------------------------------------------------------------


def test_a_free_key_follows_the_home_team_alone_and_keeps_the_saved_picks():
    prefs = Prefs(primaryTeams=[OPPONENT], likedTeams=[SLATE_SCHOOL], likedConferences=[OTHER_CONF])
    chosen = teamset.resolve(HOME, prefs, False, TEAMS)
    assert chosen.primaries == (HOME,) and chosen.secondary == () and chosen.mine() == {HOME}
    assert chosen.locked == {"primaries": 1, "teams": 1, "conferences": 1}
    assert chosen.role(HOME) == "home" and chosen.role(OPPONENT) is None


def test_a_tier2_set_spells_names_as_cfbd_and_expands_conferences_and_states():
    prefs = Prefs(primaryTeams=["texas state", HOME], likedTeams=[SLATE_SCHOOL, OPPONENT], likedConferences=[OTHER_CONF], likedStates=[STATE])
    chosen = teamset.resolve(HOME, prefs, True, TEAMS)
    assert chosen.primaries == (HOME, OPPONENT) and chosen.extra == (OPPONENT,)  # CFBD's spelling; the home team once
    assert OPPONENT not in chosen.secondary and HOME not in chosen.secondary  # a team is primary or secondary, never both
    assert chosen.secondary[0] == SLATE_SCHOOL  # the liked schools first
    assert in_conference(OTHER_CONF) - {HOME, OPPONENT} <= set(chosen.secondary)
    assert in_state(STATE) - {HOME, OPPONENT} <= set(chosen.secondary)
    assert len(chosen.secondary) == len(set(chosen.secondary))
    gravy = next(iter(in_conference(OTHER_CONF) - in_state(STATE) - {SLATE_SCHOOL}))
    assert chosen.why[gravy] == (OTHER_CONF,) and chosen.why[OPPONENT] == ("Primary team",) and chosen.role(gravy) == "secondary"
    assert teamset.resolve(HOME, prefs, True, None).secondary == (SLATE_SCHOOL,)  # no team list: no expansion, no crash


def test_opponents_come_in_schedule_order():
    assert teamset.opponents(GAMES, HOME)[:3] == ["Akron", "Fresno State", OPPONENT]
    assert HOME not in teamset.opponents(GAMES, HOME) and teamset.opponents([], HOME) == []


def test_the_new_settings_are_validated():
    with pytest.raises(ValidationError):
        Prefs(primaryTeams=["A", "B", "C", "D", "E"])  # four more at most
    with pytest.raises(ValidationError):
        Prefs(tickerMode="everything")
    with pytest.raises(ValidationError):
        Prefs(radioStations=[{"name": "Station", "kind": "link", "url": "ftp://x"}])
    with pytest.raises(ValidationError):
        Prefs(radioStations=[{"name": "<b>Station</b>", "kind": "link", "url": "https://x.example"}])
    with pytest.raises(ValidationError):
        Prefs(radioStations=[{"name": "Station", "kind": "podcast", "url": "https://x.example"}])
    station = Prefs(radioStations=[{"name": " Station ", "kind": "stream", "url": "https://x.example/live", "team": "  "}]).radioStations[0]
    assert station.name == "Station" and station.team is None


# --- settings and setup ---------------------------------------------------------------------------------


# Batch 3 (owner 2026-11-19: "Let's just have one team listed, and a change team for the switch"): the welcome page and
# Settings no longer save more teams or the My teams ticker; tests/test_welcome.py checks they clear them.


def test_setup_with_a_free_key_takes_the_home_team_alone(setup_app):  # noqa: F811
    app, client, fake, env = setup_app
    fake.route("/info", json=info(0))
    assert client.post("/api/welcome/key", json={"key": NEW_KEY}).status_code == 200
    for extra in ({"primaryTeams": [OPPONENT]}, {"tickerMode": "mine"}, {"liked": {"states": [STATE]}}):
        done = client.post("/api/welcome/finish", json={"team": HOME, **extra})
        assert done.status_code == 200, extra  # 2.1, one team on every plan: an old page's extra fields are ignored, never refused
        restart.reset()
        assert client.post("/api/welcome/key", json={"key": NEW_KEY}).status_code == 200  # no restart in a test: check the key again
    prefs = app.state.prefs.prefs
    assert prefs.primaryTeams == [] and prefs.likedStates == [] and prefs.tickerMode == "national"
    assert "Pick one school." in client.get("/welcome").text  # one team, said plainly in the setup


# --- the ticker -----------------------------------------------------------------------------------------




def listing(client: TestClient, metric: str, status: int = 200, **params: Any) -> dict[str, Any]:
    query = "&".join(f"{k}={quote(str(v))}" for k, v in params.items())
    response = client.get(f"/api/national/{metric}" + (f"?{query}" if query else ""))
    assert response.status_code == status, (metric, params, response.text[:300])
    return response.json()["data"] if status == 200 else response.json()


def test_the_opponents_list_is_the_national_list_cut_down(app, client: TestClient, fake_cfbd: FakeCfbd):
    route_all(fake_cfbd)
    load_pages(client)
    tier(app, 0)
    national = listing(client, "rating:sp")
    assert "opponents" in national["scopes"] and "mine" not in national["scopes"], "batch 3 (2026-11-19), one team: no My teams scope"
    calls = len(fake_cfbd.requests)
    opponents = listing(client, "rating:sp", scope="opponents")
    keep = {HOME, *teamset.opponents(GAMES, HOME)}
    nat = {r["team"]: r["rank"] for r in national["rows"]}
    assert opponents["rows"] and {r["team"] for r in opponents["rows"]} <= keep and any(r["isUs"] for r in opponents["rows"])
    assert all(r["rank"] == nat[r["team"]] for r in opponents["rows"])  # ranks stay national
    assert opponents["of"] == national["of"] and opponents["us"] == national["us"] and opponents["scopeTeams"] == len(keep)
    assert "opponents" in opponents["population"]
    app.state.prefs.update({"likedConferences": [OTHER_CONF]})
    old = listing(client, "rating:sp", scope="mine")
    assert [r["team"] for r in old["rows"]] == [r["team"] for r in national["rows"]], "an old My teams link reads the national list"
    assert len(fake_cfbd.requests) == calls  # no call for any scope


def wait_for_warm(app, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        task = app.state.myteams._warming
        if task is None or task.done():
            return
        time.sleep(0.05)
    raise AssertionError("the warm-up did not finish")



ENV_STATION = {"name": "Home network", "kind": "stream", "url": "https://radio.example.invalid/home.mp3"}


def test_stations_come_from_env_then_settings_then_the_list(tmp_path: Path, monkeypatch, fake_cfbd: FakeCfbd):
    from app.config import load_settings
    from app.main import create_app

    listed = tmp_path / "radio_stations.json"
    listed.write_text(json.dumps({"stations": [
        {"team": OPPONENT, "name": "Diner Radio", "kind": "link", "url": "https://radio.example.invalid/diner"},
        {"team": "Far Away", "name": "Not mine", "kind": "link", "url": "https://radio.example.invalid/far"},
        {"team": OPPONENT, "name": "Broken", "kind": "podcast", "url": "https://radio.example.invalid/bad"},
        {"name": "No team", "kind": "link", "url": "https://radio.example.invalid/none"},
        "junk",
    ]}), encoding="utf-8")
    monkeypatch.setattr(stations, "STATIONS_FILE", listed)
    monkeypatch.setenv("RADIO_SOURCES", json.dumps([ENV_STATION]))
    settings = load_settings(env_file=None, cfbd_api_key=TEST_KEY, data_dir=str(tmp_path / "data"), log_dir=str(tmp_path / "logs"))
    with TestClient(create_app(settings, cfbd_transport=fake_cfbd.transport), base_url="https://testserver") as client:
        app = client.app
        tier(app, 2)
        app.state.prefs.update({"primaryTeams": [OPPONENT, SLATE_SCHOOL], "radioStations": [{"team": SLATE_SCHOOL, "name": "Gulch Radio", "kind": "embed", "url": "https://radio.example.invalid/gulch"}]})
        body = client.get("/api/radio/sources").json()["data"]
        settings_data = client.get("/api/settings").json()["data"]
    sources = body["sources"]
    # batch 3 (owner 2026-11-19), one team: the list's stations are offered for our team alone, an older file's primaries left out
    assert [(s["name"], s["origin"]) for s in sources] == [("Home network", "env"), ("Gulch Radio", "settings")]
    assert [s["id"] for s in sources] == ["1-home-network", "2-gulch-radio"]  # .env ids never move
    assert body["help"] == []  # our team has a station
    assert [s["id"] for s in settings_data["radioSources"]] == [s["id"] for s in sources] and settings_data["radioHelp"] == []
    assert TEST_KEY not in json.dumps(body)


def test_a_team_without_a_station_gets_search_links_and_the_request_form(app, client: TestClient, monkeypatch, tmp_path: Path):
    monkeypatch.setattr(stations, "STATIONS_FILE", tmp_path / "missing.json")
    tier(app, 2)
    app.state.prefs.update({"primaryTeams": [OPPONENT]})
    body = client.get("/api/radio/sources").json()["data"]
    assert body["sources"] == []
    help_rows = {h["school"]: h for h in body["help"]}
    assert set(help_rows) == {HOME}, "one team: the help is ours alone"
    request = help_rows[HOME]["requestUrl"]
    assert request.startswith("https://github.com/Myerslabs/kickoff-companion/issues/new?template=radio-station.yml")
    assert [link["label"] for link in help_rows[HOME]["search"]] == ["Search the web", "Search TuneIn"]
    assert all(link["url"].startswith("https://") for h in body["help"] for link in h["search"])


def test_an_install_with_no_station_gets_the_lists_stream_as_a_sample(app, client: TestClient, monkeypatch, tmp_path: Path):
    """Owner 2026-10-16: "we need an initial station to show off the feature". With no station of its own (no .env
    sources, none in Settings, none listed for a primary team) the radio offers the list's first stream as a sample;
    the team's own help (search links, the request form) still shows."""
    listed = tmp_path / "radio_stations.json"
    listed.write_text(json.dumps({"stations": [
        {"team": "Far Away", "name": "Far page", "kind": "link", "url": "https://radio.example.invalid/far-page"},
        {"team": "Far Away", "name": "Far stream", "kind": "stream", "url": "https://radio.example.invalid/far.mp3"},
    ]}), encoding="utf-8")
    monkeypatch.setattr(stations, "STATIONS_FILE", listed)
    body = client.get("/api/radio/sources").json()["data"]
    assert [(s["name"], s["origin"], s["team"]) for s in body["sources"]] == [("Far stream", "sample", "Far Away")]
    assert [h["school"] for h in body["help"]] == [HOME], "the sample is not the home team's station"
    app.state.prefs.update({"radioStations": [{"team": HOME, "name": "Our own", "kind": "link", "url": "https://radio.example.invalid/ours"}]})
    again = client.get("/api/radio/sources").json()["data"]["sources"]
    assert [(s["name"], s["origin"]) for s in again] == [("Our own", "settings")], "a station of your own replaces the sample"


def test_the_station_list_and_the_issue_form_ship_with_the_repo():
    root = Path(__file__).resolve().parent.parent
    listed = json.loads((root / "app" / "radio_stations.json").read_text(encoding="utf-8"))
    # owner 2026-10-16: it ships the initial station (one team's, to show the feature off), then grows as people ask
    assert listed["stations"] and len(stations.known_stations()) == len(listed["stations"]), "every shipped entry is valid"
    assert any(s.kind == "stream" for s in stations.known_stations()), "the sample can play in the bar"
    assert all(s["url"].startswith("https://") for s in listed["stations"])
    form = (root / ".github" / "ISSUE_TEMPLATE" / "radio-station.yml").read_text(encoding="utf-8")
    assert "id: school" in form and "official" in form.lower()
    assert stations.request_url(None).endswith("template=radio-station.yml")


def test_the_new_routes_wait_for_setup(setup_app):  # noqa: F811
    app, client, fake, env = setup_app
    for path in ("/api/myteams",):
        response = client.get(path)
        assert response.status_code == 503 and response.json()["errors"][0]["code"] == "setup_needed", path
    assert client.post("/api/myteams/warm").status_code == 503


@pytest.mark.parametrize("when", [KICKOFF])
def test_ticker_entries_say_whether_they_are_mine(app, client: TestClient, fake_cfbd: FakeCfbd, when):
    route_week(fake_cfbd)
    quiet_engine(app, client)
    set_clock(app, when - timedelta(hours=3))
    games = client.get("/api/ticker").json()["data"]["games"]
    assert games and all(isinstance(g["isMine"], bool) for g in games)
