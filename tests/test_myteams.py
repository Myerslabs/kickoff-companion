"""Public release Phase 5b: primary and secondary teams. The home team (primary #1) alone themes the app and
drives Season, Game program and Live; up to four more primaries get their team pages warmed when a device
connects; secondary schools, conferences and states fill the My teams ticker, the My teams page and the My
teams scope of a ranked list. All of it needs a Tier 2 key and none of it costs a call a page would not make.
Also: the opponents scope (every plan), and radio for any team (saved stations, the repo list, the help
links and the GitHub request form)."""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
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

HOME = "Swampwater Tech"
OPPONENT = "Diner Tech"  # week 4, on our schedule
SLATE_SCHOOL = "Cactus Gulch"  # plays in week 4, not us
OTHER_CONF = "Gravy Ten"
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
    prefs = Prefs(primaryTeams=["diner tech", HOME], likedTeams=[SLATE_SCHOOL, OPPONENT], likedConferences=[OTHER_CONF], likedStates=[STATE])
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
    assert teamset.opponents(GAMES, HOME)[:3] == ["Rhubarb State", "Silver Dollar", OPPONENT]
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


def test_settings_keep_tier2_picks_for_a_tier2_key(app, client: TestClient):
    tier(app, 0)
    refused = client.put("/api/settings", json={"tickerMode": "mine"})
    assert refused.status_code == 422 and refused.json()["errors"][0]["code"] == "tier2_needed"
    assert client.put("/api/settings", json={"primaryTeams": [OPPONENT]}).status_code == 422
    assert client.put("/api/settings", json={"primaryTeams": [], "tickerMode": "national"}).status_code == 200  # clearing is always fine
    tier(app, 2)
    saved = client.put("/api/settings", json={"primaryTeams": [OPPONENT], "tickerMode": "mine"})
    assert saved.status_code == 200
    data = saved.json()["data"]
    assert data["prefs"]["tickerMode"] == "mine" and data["teamSet"]["extraPrimaries"] == [OPPONENT] and data["teamSet"]["primaries"][0] == HOME
    tier(app, 0)
    after = client.get("/api/settings").json()["data"]
    assert after["teamSet"]["extraPrimaries"] == [] and after["teamSet"]["locked"] == {"primaries": 1}  # kept, but quiet on a free key


def test_setup_saves_primaries_secondaries_and_the_ticker_with_a_tier2_key(setup_app):  # noqa: F811
    app, client, fake, env = setup_app
    fake.route("/info", json=info(2))
    assert client.post("/api/welcome/key", json={"key": NEW_KEY}).status_code == 200
    body = {"team": HOME, "primaryTeams": [OPPONENT, HOME, "diner tech", SLATE_SCHOOL], "liked": {"teams": [SLATE_SCHOOL, "Silver Dollar"], "conferences": [OTHER_CONF], "states": [STATE]}, "tickerMode": "mine"}
    done = client.post("/api/welcome/finish", json=body)
    assert done.status_code == 200, done.text
    prefs = app.state.prefs.prefs
    assert prefs.primaryTeams == [OPPONENT, SLATE_SCHOOL] and prefs.likedTeams == ["Silver Dollar"] and prefs.tickerMode == "mine"
    state = client.get("/api/welcome").json()["data"]
    assert state["primaryTeams"] == [OPPONENT, SLATE_SCHOOL] and state["maxPrimaryTeams"] == 4 and state["tickerMode"] == "mine"
    restart.reset()
    assert client.post("/api/welcome/key", json={"key": NEW_KEY}).status_code == 200  # no restart in a test: check the key again
    five = client.post("/api/welcome/finish", json={**body, "primaryTeams": [t["school"] for t in fixture_payload("teams_fbs")[:6] if t["school"] != HOME][:5]})
    assert five.status_code == 422 and five.json()["errors"][0]["code"] == "too_many_primaries"
    junk = client.post("/api/welcome/finish", json={**body, "primaryTeams": ["Not A School"]})
    assert junk.status_code == 422 and junk.json()["errors"][0]["code"] == "bad_liked"
    odd = client.post("/api/welcome/finish", json={**body, "tickerMode": "loud"})
    assert odd.status_code == 422 and odd.json()["errors"][0]["code"] == "bad_ticker"


def test_setup_with_a_free_key_takes_the_home_team_alone(setup_app):  # noqa: F811
    app, client, fake, env = setup_app
    fake.route("/info", json=info(0))
    assert client.post("/api/welcome/key", json={"key": NEW_KEY}).status_code == 200
    for extra in ({"primaryTeams": [OPPONENT]}, {"tickerMode": "mine"}, {"liked": {"states": [STATE]}}):
        refused = client.post("/api/welcome/finish", json={"team": HOME, **extra})
        assert refused.status_code == 422 and refused.json()["errors"][0]["code"] == "tier2_needed", extra
    assert client.post("/api/welcome/finish", json={"team": HOME, "tickerMode": "national"}).status_code == 200
    assert "only this team's colors and mascot theme the app" in client.get("/welcome").text  # said plainly in the setup


# --- the ticker -----------------------------------------------------------------------------------------


def test_the_my_teams_ticker_keeps_my_games_on_the_same_calls(app, client: TestClient, fake_cfbd: FakeCfbd):
    route_week(fake_cfbd)
    quiet_engine(app, client)
    set_clock(app, datetime(2026, 9, 23, 16, 0, tzinfo=timezone.utc))
    tier(app, 2)
    national = client.get("/api/ticker").json()["data"]
    calls = len(fake_cfbd.requests)
    assert national["mode"] == "national" and national["refreshMinutes"] == 5
    assert all(g["isMine"] == g["isUs"] for g in national["games"])  # only the home team so far
    app.state.prefs.update({"tickerMode": "mine", "likedTeams": [SLATE_SCHOOL]})
    mine = client.get("/api/ticker").json()["data"]
    assert len(fake_cfbd.requests) == calls  # the same slate, no new call
    assert mine["mode"] == "mine" and mine["modeNote"] is None and all(g["isMine"] for g in mine["games"])
    schools = {s for g in mine["games"] for s in (g["home"]["school"], g["away"]["school"])}
    assert {HOME, SLATE_SCHOOL} <= schools and len(mine["games"]) == 2 < len(national["games"])
    lean = next(g for g in national["games"] if g["home"]["school"] == SLATE_SCHOOL or g["away"]["school"] == SLATE_SCHOOL)
    assert lean["isMine"] is False
    tier(app, 0)
    free = client.get("/api/ticker").json()["data"]
    assert free["mode"] == "national" and free["modeAsked"] == "mine" and "Tier 2" in free["modeNote"] and free["refreshMinutes"] == 20
    assert len(free["games"]) == len(national["games"])


def test_a_slate_without_my_teams_shows_every_game_with_a_note(app, client: TestClient, fake_cfbd: FakeCfbd):
    route_week(fake_cfbd)
    quiet_engine(app, client)
    set_clock(app, datetime(2026, 9, 23, 16, 0, tzinfo=timezone.utc))
    tier(app, 2)
    app.state.prefs.update({"tickerMode": "mine"})
    app.state.settings.team = "Nobody Plays Here"  # a home team with no game on the slate
    data = client.get("/api/ticker").json()["data"]
    assert data["mode"] == "national" and data["modeAsked"] == "mine" and "None of your teams" in data["modeNote"] and data["games"]


# --- ranked lists ---------------------------------------------------------------------------------------


def listing(client: TestClient, metric: str, status: int = 200, **params: Any) -> dict[str, Any]:
    query = "&".join(f"{k}={quote(str(v))}" for k, v in params.items())
    response = client.get(f"/api/national/{metric}" + (f"?{query}" if query else ""))
    assert response.status_code == status, (metric, params, response.text[:300])
    return response.json()["data"] if status == 200 else response.json()


def test_the_opponents_and_my_teams_lists_are_the_national_list_cut_down(app, client: TestClient, fake_cfbd: FakeCfbd):
    route_all(fake_cfbd)
    load_pages(client)
    tier(app, 0)
    national = listing(client, "rating:sp")
    assert "opponents" in national["scopes"] and "mine" not in national["scopes"]
    calls = len(fake_cfbd.requests)
    opponents = listing(client, "rating:sp", scope="opponents")
    keep = {HOME, *teamset.opponents(GAMES, HOME)}
    nat = {r["team"]: r["rank"] for r in national["rows"]}
    assert opponents["rows"] and {r["team"] for r in opponents["rows"]} <= keep and any(r["isUs"] for r in opponents["rows"])
    assert all(r["rank"] == nat[r["team"]] for r in opponents["rows"])  # ranks stay national
    assert opponents["of"] == national["of"] and opponents["us"] == national["us"] and opponents["scopeTeams"] == len(keep)
    assert "opponents" in opponents["population"]
    assert listing(client, "rating:sp", 404, scope="mine")["errors"][0]["message"].endswith("Tier 2 key.")
    tier(app, 2)
    app.state.prefs.update({"likedConferences": [OTHER_CONF]})
    mine = listing(client, "rating:sp", scope="mine")
    teams = {r["team"] for r in mine["rows"]}
    assert HOME in teams and teams - {HOME} <= in_conference(OTHER_CONF) and len(teams) > 8 and "mine" in mine["scopes"]
    assert len(fake_cfbd.requests) == calls  # no call for any scope
    passers = listing(client, "board:passing:YDS")
    mine_passers = listing(client, "board:passing:YDS", scope="mine")  # a player board cuts by the player's team
    allowed = {HOME} | in_conference(OTHER_CONF)
    assert mine_passers["rows"] and all(r["team"] in allowed for r in mine_passers["rows"])
    national_ranks = {r["playerId"]: r["rank"] for r in passers["rows"] + passers["beyond"]}
    assert all(national_ranks.get(r["playerId"], r["rank"]) == r["rank"] for r in mine_passers["rows"])


# --- the My teams page and the warm-up ------------------------------------------------------------------


def test_my_teams_lists_records_ranks_and_games_from_cached_answers(app, client: TestClient, fake_cfbd: FakeCfbd):
    route_all(fake_cfbd)
    load_pages(client)
    tier(app, 2)
    app.state.prefs.update({"primaryTeams": [OPPONENT], "likedTeams": [SLATE_SCHOOL, "No Such School"]})
    calls = len(fake_cfbd.requests)
    body = client.get("/api/myteams").json()
    assert len(fake_cfbd.requests) == calls  # every part was already cached by the pages
    rows = body["data"]["rows"]
    assert [r["school"] for r in rows[:2]] == [HOME, OPPONENT] and [r["role"] for r in rows[:2]] == ["home", "primary"]
    by = {r["school"]: r for r in rows}
    assert by[SLATE_SCHOOL]["role"] == "secondary" and by[SLATE_SCHOOL]["why"] == ["Liked school"]
    assert by["No Such School"]["known"] is False and by["No Such School"]["record"] is None  # a saved name CFBD no longer lists
    sp_rank = next(r["ranking"] for r in fixture_payload("ratings_sp") if r["team"] == HOME)
    assert by[HOME]["sp"]["rank"] == sp_rank and isinstance(by[HOME]["record"]["wins"], int)
    assert by[HOME]["last"]["opponent"] == "Silver Dollar" and by[HOME]["next"]["opponent"] == OPPONENT
    assert body["data"]["note"] is None and body["data"]["teamSet"]["extraPrimaries"] == [OPPONENT]
    tier(app, 0)
    free = client.get("/api/myteams").json()["data"]
    assert [r["school"] for r in free["rows"]] == [HOME] and "Tier 2" in free["note"]


def test_my_teams_survives_junk_parts(app, client: TestClient, fake_cfbd: FakeCfbd):
    route_all(fake_cfbd)
    fake_cfbd.route("/records", json=[{"team": None}, "junk", {"team": HOME, "total": "nine"}])
    fake_cfbd.route("/ratings/elo", json={"not": "a list"})
    fake_cfbd.route("/ratings/fpi", status=500, text="down")
    tier(app, 2)
    app.state.prefs.update({"likedTeams": [SLATE_SCHOOL]})
    response = client.get("/api/myteams")
    assert response.status_code == 200
    rows = response.json()["data"]["rows"]
    assert [r["school"] for r in rows] == [HOME, SLATE_SCHOOL] and rows[0]["elo"]["rank"] is None and rows[0]["fpi"]["rank"] is None
    assert "NaN" not in response.text


def wait_for_warm(app, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        task = app.state.myteams._warming
        if task is None or task.done():
            return
        time.sleep(0.05)
    raise AssertionError("the warm-up did not finish")


def test_primary_team_pages_warm_when_a_device_connects(app, client: TestClient, fake_cfbd: FakeCfbd):
    route_all(fake_cfbd)
    tier(app, 0)
    app.state.prefs.prefs = Prefs(primaryTeams=[OPPONENT])  # saved under a Tier 2 key earlier
    assert client.post("/api/myteams/warm").json()["data"] == {"warming": [], "reason": "free_key"}
    tier(app, 2)
    started = client.post("/api/myteams/warm").json()["data"]
    assert started == {"warming": [OPPONENT], "reason": None}
    wait_for_warm(app)
    calls = len(fake_cfbd.requests)
    assert client.get(f"/api/team/{quote(OPPONENT)}").status_code == 200
    assert len(fake_cfbd.requests) == calls  # the page was ready before anyone opened it
    assert client.post("/api/myteams/warm").json()["data"]["reason"] == "recent"
    app.state.cfbd._clock = lambda: datetime.now(timezone.utc) + timedelta(minutes=11)
    assert client.post("/api/myteams/warm").json()["data"]["reason"] is None
    wait_for_warm(app)
    app.state.prefs.prefs = Prefs()
    assert client.post("/api/myteams/warm").json()["data"]["reason"] == "no_primaries"


# --- radio for any team ---------------------------------------------------------------------------------


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
    assert [(s["name"], s["origin"]) for s in sources] == [("Home network", "env"), ("Gulch Radio", "settings"), ("Diner Radio", "list")]
    assert [s["id"] for s in sources] == ["1-home-network", "2-gulch-radio", "3-diner-radio"]  # .env ids never move
    assert body["help"] == []  # every primary team has a station
    assert [s["id"] for s in settings_data["radioSources"]] == [s["id"] for s in sources] and settings_data["radioHelp"] == []
    assert TEST_KEY not in json.dumps(body)


def test_a_team_without_a_station_gets_search_links_and_the_request_form(app, client: TestClient, monkeypatch, tmp_path: Path):
    monkeypatch.setattr(stations, "STATIONS_FILE", tmp_path / "missing.json")
    tier(app, 2)
    app.state.prefs.update({"primaryTeams": [OPPONENT]})
    body = client.get("/api/radio/sources").json()["data"]
    assert body["sources"] == []
    help_rows = {h["school"]: h for h in body["help"]}
    assert set(help_rows) == {HOME, OPPONENT}
    request = help_rows[OPPONENT]["requestUrl"]
    assert request.startswith("https://github.com/Myerslabs/kickoff-companion/issues/new?template=radio-station.yml")
    assert "school=Diner%20Tech" in request and "title=Radio%20station%3A%20Diner%20Tech" in request
    assert [link["label"] for link in help_rows[HOME]["search"]] == ["Search the web", "Search TuneIn"]
    assert all(link["url"].startswith("https://") for h in body["help"] for link in h["search"])


def test_the_station_list_and_the_issue_form_ship_with_the_repo():
    root = Path(__file__).resolve().parent.parent
    listed = json.loads((root / "app" / "radio_stations.json").read_text(encoding="utf-8"))
    assert listed["stations"] == []  # it grows as people ask; nothing is researched up front
    assert stations.known_stations() == []
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
