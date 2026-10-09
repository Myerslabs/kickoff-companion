"""Phase 15: bowl and playoff games (A), against the made-up league's previous postseason, followed
as its champion (ROLES["POSTTEAM"]): every playoff round it played, all CFBD "postseason week 1"."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from app.cfbd.models import CalendarWeek, Drive, Game, Play, PollWeek, parse_records
from app.config import load_settings
from app.logging_setup import configure_logging, shutdown_logging
from app.main import create_app
from app.services import gamekeys
from app.services.parts import calendar_slot
from app.services.playoff import playoff_block
from tests.conftest import ROLES, TEST_KEY, FakeCfbd, fixture_payload


def games(name: str) -> list[Game]:
    return parse_records(Game, fixture_payload(name), context="test").records


POST_TEAM = ROLES["POSTTEAM"]  # the champion of the league's previous season
TITLE_GAME = int(ROLES["POSTGAME"])
TITLE_ROW = next(g for g in fixture_payload("games_post_2025") if g["id"] == TITLE_GAME)
TITLE_OPP = TITLE_ROW["awayTeam"] if TITLE_ROW["homeTeam"] == POST_TEAM else TITLE_ROW["homeTeam"]
POST_GAMES = [g.id for g in sorted(games("games_team_2025_default"), key=gamekeys.order) if gamekeys.is_post(g)]
POST_CONFERENCE = next(t["conference"] for t in fixture_payload("teams_fbs") if t["school"] == POST_TEAM)


# --- keys ----------------------------------------------------------------------------------------


def test_cfbds_default_schedule_already_holds_the_postseason():
    default, both = games("games_team_2025_default"), games("games_team_2025_both")
    assert [g.id for g in default] == [g.id for g in both]
    played = [g for g in fixture_payload("games_post_2025") if POST_TEAM in (g["homeTeam"], g["awayTeam"])]
    assert sum(gamekeys.is_post(g) for g in default) == len(played) >= 2
    assert {g.week for g in default if gamekeys.is_post(g)} == {1}


def test_postseason_games_sort_after_the_regular_season_and_have_their_own_keys():
    ordered = sorted(games("games_team_2025_default"), key=gamekeys.order)
    n = len(POST_GAMES)
    assert [g.id for g in ordered[-n:]] == POST_GAMES and POST_GAMES[-1] == TITLE_GAME
    regular = [g for g in ordered if not gamekeys.is_post(g)]
    assert ordered[-n - 1].id == regular[-1].id and regular[-1].week == max(g.week for g in regular)
    tags = [gamekeys.tag(g) for g in ordered]
    assert len(set(tags)) == len(tags)  # regular week 1 and the postseason games never collide
    assert tags[0] == "1" and tags[-1] == f"p{TITLE_GAME}"


def test_parameters_for_a_bowl():
    title = next(g for g in games("games_team_2025_default") if g.id == TITLE_GAME)
    regular = next(g for g in games("games_team_2025_default") if g.week == 3 and not gamekeys.is_post(g))
    assert gamekeys.box_params(title, 2025, POST_TEAM) == {"id": TITLE_GAME}
    assert gamekeys.week_params(title, 2025, POST_TEAM) == {"year": 2025, "week": 1, "team": POST_TEAM, "seasonType": "postseason"}
    assert gamekeys.week_params(regular, 2025, POST_TEAM) == {"year": 2025, "week": 3, "team": POST_TEAM}
    assert gamekeys.season_params(2025, POST_TEAM, [regular]) == {"year": 2025, "team": POST_TEAM}
    assert gamekeys.season_params(2025, POST_TEAM, [regular, title]) == {"year": 2025, "team": POST_TEAM, "seasonType": "both"}


def test_a_week_keyed_bowl_answer_is_cut_to_the_one_game():
    title = next(g for g in games("games_team_2025_default") if g.id == TITLE_GAME)
    plays = parse_records(Play, fixture_payload("plays_post"), context="test").records
    drives = parse_records(Drive, fixture_payload("drives_post"), context="test").records
    assert len({p.game_id for p in plays}) == len(POST_GAMES)
    assert {p.game_id for p in gamekeys.only_game(plays, title)} == {TITLE_GAME}
    assert {d.game_id for d in gamekeys.only_game(drives, title)} == {TITLE_GAME}


def test_bowl_labels_and_rounds():
    by_id = {g.id: g for g in games("games_post_2025")}
    title = by_id[TITLE_GAME]
    assert gamekeys.playoff_round(title) == "National Championship"
    assert "National Championship" in gamekeys.label(title)
    bowl = next(g for g in by_id.values() if g.notes and g.playoff is None)
    assert gamekeys.playoff_round(bowl) is None and gamekeys.label(bowl) == bowl.notes
    assert gamekeys.label(games("games_team_2025_default")[0]) is None


def test_a_malformed_playoff_block_never_drops_the_game():
    raw = [dict(fixture_payload("games_post_2025")[-1], playoff="not an object"), dict(fixture_payload("games_post_2025")[-1], id=1, playoff={"homeSeed": "one"})]
    parsed = parse_records(Game, raw, context="test")
    assert len(parsed.records) == 2 and parsed.records[0].playoff is None and parsed.records[1].playoff is None


def test_the_postseason_calendar_week():
    weeks = parse_records(CalendarWeek, fixture_payload("calendar_2025"), context="test").records
    assert calendar_slot(weeks, datetime(2026, 1, 5, tzinfo=timezone.utc)) == (1, "postseason")
    assert calendar_slot(weeks, datetime(2025, 9, 10, tzinfo=timezone.utc))[1] == "regular"
    assert calendar_slot(weeks, datetime(2026, 3, 1, tzinfo=timezone.utc)) is None


def test_the_final_poll_is_the_latest():
    weeks = parse_records(PollWeek, fixture_payload("rankings_2025_both"), context="test").records
    latest = max(weeks, key=gamekeys.poll_order)
    assert latest.season_type == "postseason"


# --- the playoff band ----------------------------------------------------------------------------


def test_playoff_block_bracket_and_committee():
    weeks = parse_records(PollWeek, fixture_payload("rankings_2025_both"), context="test").records
    block = playoff_block(weeks, games("games_post_2025"), POST_TEAM, {})
    assert block["week"] == 16  # the committee's selection-day ranking; the final poll has none
    assert block["rankings"][0]["rank"] == 1 and len(block["rankings"]) == 25
    assert [r["round"] for r in block["rounds"]] == ["First Round", "Quarterfinal", "Semifinal", "National Championship"]
    assert [len(r["games"]) for r in block["rounds"]] == [4, 4, 2, 1]
    assert [g["slot"] for g in block["rounds"][0]["games"]] == ["FR1", "FR2", "FR3", "FR4"]
    title = block["rounds"][-1]["games"][0]
    seeds = TITLE_ROW["playoff"]
    assert title["home"]["seed"] == seeds["homeSeed"] and title["away"]["seed"] == seeds["awaySeed"]
    assert title["winner"] == POST_TEAM and title["isUs"]  # the league's champion
    assert sum(g["isUs"] for r in block["rounds"] for g in r["games"]) == len(POST_GAMES)


def test_the_selection_day_ranking_orders_the_seeds():
    weeks = parse_records(PollWeek, fixture_payload("rankings_2025_both"), context="test").records
    block = playoff_block(weeks, games("games_post_2025"), POST_TEAM, {})
    committee = [r["school"] for r in block["rankings"]]
    seed = {}
    for g in fixture_payload("games_post_2025"):
        if g.get("playoff"):
            seed[g["homeTeam"]], seed[g["awayTeam"]] = g["playoff"]["homeSeed"], g["playoff"]["awaySeed"]
    ranked = [t for t in sorted(seed, key=seed.get) if t in committee]
    assert len(ranked) >= 11  # at most one champion seeded from outside the top 25
    assert [committee.index(t) for t in ranked] == sorted(committee.index(t) for t in ranked)


def test_no_playoff_band_before_the_committee_ranks_anyone():
    assert playoff_block([], games("games_team_2025_default")[:5], POST_TEAM, {}) is None


# --- through the app, as the champion's 2025 season --------------------------------------------------


@pytest.fixture
def champion(tmp_path):
    fake = FakeCfbd()

    def games_route(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("team"):
            return httpx.Response(200, json=fixture_payload("games_team_2025_default"))
        return httpx.Response(200, json=fixture_payload("games_post_2025"))

    fake.route("/games", handler=games_route)
    fake.fixture("/rankings", "rankings_2025_both")
    fake.fixture("/calendar", "calendar_2025")
    fake.fixture("/games/teams", "games_teams_post")
    fake.fixture("/games/players", "games_players_post")
    fake.fixture("/metrics/wp/pregame", "metrics_wp_pregame_post")
    fake.fixture("/ppa/players/games", "ppa_players_games_post")
    fake.fixture("/ppa/games", "ppa_games_post")
    fake.fixture("/game/box/advanced", "game_box_advanced_post")
    settings = load_settings(env_file=None, cfbd_api_key=TEST_KEY, log_dir=str(tmp_path / "logs"), data_dir=str(tmp_path / "data"), team=POST_TEAM, season=2025, conference=POST_CONFERENCE)
    configure_logging(settings)
    app = create_app(settings, cfbd_transport=fake.transport)
    with TestClient(app, base_url="https://testserver") as client:
        client.portal.call(app.state.live.stop_background)
        yield client, fake
    shutdown_logging()


def requests_to(fake: FakeCfbd, path: str) -> list[dict[str, str]]:
    return [dict(r.url.params) for r in fake.requests if r.url.path == path]


def test_the_title_game_program_asks_for_the_one_game(champion):
    client, fake = champion
    body = client.get(f"/api/program/{TITLE_GAME}").json()
    game = body["data"]["game"]
    assert game["playoffRound"] == "National Championship" and "Championship" in game["postseason"]
    assert requests_to(fake, "/games/teams") == [{"id": str(TITLE_GAME)}]
    assert requests_to(fake, "/games/players") == [{"id": str(TITLE_GAME)}]
    assert all(p.get("seasonType") == "postseason" for p in requests_to(fake, "/metrics/wp/pregame"))
    assert all(p.get("seasonType") == "both" for p in requests_to(fake, "/ppa/games"))
    players = body["data"]["ppa"]["players"]["us"]
    assert players and {p["opponent"] for p in players} == {TITLE_OPP}


def test_the_season_page_lists_the_bowls_and_the_bracket(champion):
    client, _ = champion
    data = client.get("/api/season/overview").json()["data"]
    rows = data["schedule"]
    assert [r["gameId"] for r in rows[-len(POST_GAMES):]] == POST_GAMES
    assert rows[-1]["playoffRound"] == "National Championship" and rows[0]["postseason"] is None
    playoff = data["playoff"]
    assert playoff and [r["round"] for r in playoff["rounds"]][-1] == "National Championship"


def test_the_game_analytics_of_a_bowl_keep_its_players(champion):
    client, fake = champion
    data = client.get(f"/api/games/{TITLE_GAME}/analytics").json()["data"]
    assert all(p.get("seasonType") == "postseason" for p in requests_to(fake, "/ppa/players/games"))
    players = data["ppa"]["players"]["us"]
    assert players and {p["opponent"] for p in players} == {TITLE_OPP}


# --- B: search ------------------------------------------------------------------------------------


OUR_QB = next(p for p in fixture_payload("roster") if p["lastName"] == ROLES["QB"] and p["position"] == "QB")
QB_NAME = f"{OUR_QB['firstName']} {OUR_QB['lastName']}"
MASCOT = next(t["mascot"] for t in fixture_payload("teams_fbs") if t["school"] == ROLES["US"])


def former_player() -> str:
    """A name from the wide search answer whose playing days ended before this season."""
    return next(p["name"] for p in fixture_payload("player_search_name") if p["activeEndYear"] < 2026)


def route_search(fake: FakeCfbd) -> None:
    fake.fixture("/teams/fbs", "teams_fbs")
    fake.fixture("/games", "games_team")
    fake.fixture("/roster", "roster")
    fake.fixture("/player/search", "player_search_name")


def test_typing_searches_teams_and_rosters_without_calling_cfbd_search(client, fake_cfbd):
    route_search(fake_cfbd)
    data = client.get("/api/search", params={"q": ROLES["QB"][:3].lower()}).json()["data"]
    assert any(p["name"] == QB_NAME and p["canOpen"] for p in data["players"])
    assert data["wide"] is None
    teams = client.get("/api/search", params={"q": MASCOT.lower()}).json()["data"]["teams"]
    assert teams[0]["school"] == ROLES["US"]
    assert client.get("/api/search", params={"q": "a"}).json()["data"]["players"] == []
    assert fake_cfbd.count("/player/search") == 0


def test_a_misspelled_name_suggests_close_spellings_without_a_call(client, fake_cfbd):
    # Phase 17 #8: a near miss offers the real name instead of a dead end
    route_search(fake_cfbd)
    last = QB_NAME.split()[-1]
    typo = last[:-1] + ("x" if last[-1].lower() != "x" else "q")
    data = client.get("/api/search", params={"q": typo.lower()}).json()["data"]
    assert data["teams"] == [] and data["players"] == [] and last in data["suggest"]
    assert len(data["suggest"]) <= 3
    # a real match never carries suggestions, and nonsense gets none
    assert client.get("/api/search", params={"q": last.lower()}).json()["data"]["suggest"] == []
    assert client.get("/api/search", params={"q": "qzxwv"}).json()["data"]["suggest"] == []
    assert fake_cfbd.count("/player/search") == 0


def test_suggestions_guard_their_input():
    from app.services.search import suggestions

    assert suggestions("ab", ["Abc"]) == []  # too short to guess from
    assert suggestions("sanches", [None, 7, "", "  ", "Sánchez", "Sanchez", "Smith"]) == ["Sánchez"]  # folded duplicates once


def test_a_jersey_number_finds_players(client, fake_cfbd):
    route_search(fake_cfbd)
    players = client.get("/api/search", params={"q": str(OUR_QB["jersey"])}).json()["data"]["players"]
    assert any(p["name"] == QB_NAME for p in players)


def test_search_every_player_asks_cfbd_once_and_ranks_this_seasons_fbs_players_first(client, fake_cfbd):
    route_search(fake_cfbd)
    data = client.get("/api/search", params={"q": ROLES["QB"], "wide": 1}).json()["data"]
    wide = data["wide"]
    assert all(p["name"] != QB_NAME for p in wide)  # already listed from the roster
    opens = [p["canOpen"] for p in wide]
    assert opens == sorted(opens, reverse=True)  # cards first
    former = next(p for p in wide if p["name"] == former_player())
    assert former["canOpen"] is False and former["current"] is False
    client.get("/api/search", params={"q": ROLES["QB"], "wide": 1})
    assert fake_cfbd.count("/player/search") == 1  # kept a week like a roster


def test_search_every_player_needs_three_letters(client, fake_cfbd):
    route_search(fake_cfbd)
    data = client.get("/api/search", params={"q": ROLES["QB"][:2], "wide": 1}).json()["data"]
    assert data["wide"] == [] and "3 letters" in data["wideNote"]
    assert fake_cfbd.count("/player/search") == 0


def test_a_damaged_player_search_answer_keeps_the_good_rows(client, fake_cfbd):
    route_search(fake_cfbd)
    good = fixture_payload("player_search_name")
    fake_cfbd.route("/player/search", json=[{"name": "No Id"}, "junk", None, *good[:2]])
    wide = client.get("/api/search", params={"q": ROLES["QB"], "wide": 1}).json()["data"]["wide"]
    assert {p["name"] for p in wide} <= {g["name"] for g in good[:2]}


def test_ratings_is_in_the_menu():
    from pathlib import Path

    shell_js = Path("static/js/ui/shell.js").read_text(encoding="utf-8")
    assert '{ id: "ratings", label: "Ratings" }' in shell_js


# --- D: context tables ------------------------------------------------------------------------------


def test_road_ahead_lists_each_remaining_opponent_with_form():
    from app.cfbd.models import TeamSP
    from app.services.offday import road_ahead

    schedule = games("games_team")
    league = schedule
    sp = parse_records(TeamSP, fixture_payload("ratings_sp"), context="test").records
    rows = road_ahead(schedule, league, "Swampwater Tech", sp, {"Diner Tech": 8})
    remaining = [g for g in schedule if not g.completed]
    assert [r["gameId"] for r in rows] == [g.id for g in sorted(remaining, key=gamekeys.order)]
    assert all(set(r) >= {"opponent", "site", "record", "apRank", "sp", "spRank", "spOf", "lastThree"} for r in rows)
    assert all(len(r["lastThree"]) <= 3 for r in rows)


def _result(row: dict, team: str) -> dict:
    ours, theirs = (row["homePoints"], row["awayPoints"]) if row["homeTeam"] == team else (row["awayPoints"], row["homePoints"])
    return {"result": "W" if ours > theirs else "L", "score": f"{ours}-{theirs}", "margin": ours - theirs}


def _opponents(rows: list[dict], team: str) -> set[str]:
    return {t for g in rows if team in (g["homeTeam"], g["awayTeam"]) for t in (g["homeTeam"], g["awayTeam"])} - {team}


def test_common_opponents_from_the_2025_postseason():
    from app.services.offday import common_opponents

    post = fixture_payload("games_post_2025")
    assert _opponents(post, POST_TEAM) & _opponents(post, TITLE_OPP) == set()  # the finalists met only each other
    assert common_opponents(games("games_post_2025"), POST_TEAM, TITLE_OPP) == []
    # a team the runner-up beat on its way to the title game: it and the champion both played the runner-up
    beaten = next(g for g in post if g.get("playoff") and TITLE_OPP in (g["homeTeam"], g["awayTeam"]) and g["id"] != TITLE_GAME)
    other = beaten["awayTeam"] if beaten["homeTeam"] == TITLE_OPP else beaten["homeTeam"]
    assert _opponents(post, POST_TEAM) & _opponents(post, other) == {TITLE_OPP}
    us, them = _result(TITLE_ROW, POST_TEAM), _result(beaten, other)
    rows = common_opponents(games("games_post_2025"), POST_TEAM, other)
    assert rows == [{"opponent": TITLE_OPP, "us": [us], "them": [them], "usMargin": us["margin"], "themMargin": them["margin"]}]


def test_common_opponents_margins():
    from app.services.offday import common_opponents

    base = fixture_payload("games_post_2025")[0]
    made = [
        dict(base, id=1, homeTeam="Swampwater Tech", awayTeam="Gravy Boat State", homePoints=31, awayPoints=10, completed=True, seasonType="regular", week=2),
        dict(base, id=2, homeTeam="Gravy Boat State", awayTeam="Front Porch State", homePoints=20, awayPoints=24, completed=True, seasonType="regular", week=3),
        dict(base, id=3, homeTeam="Swampwater Tech", awayTeam="Front Porch State", homePoints=None, awayPoints=None, completed=False, seasonType="regular", week=9),
    ]
    rows = common_opponents(parse_records(Game, made, context="test").records, "Swampwater Tech", "Front Porch State")
    assert rows == [{"opponent": "Gravy Boat State", "us": [{"result": "W", "score": "31-10", "margin": 21}], "them": [{"result": "W", "score": "24-20", "margin": 4}], "usMargin": 21, "themMargin": 4}]
    assert common_opponents([], "Swampwater Tech", None) == []


def test_last_season_rows_compare_values_by_direction():
    from app.cfbd.models import TeamStat
    from app.services.offday import last_season
    from app.services.profiles import Profiles

    stats = parse_records(TeamStat, fixture_payload("stats_season_fbs"), context="test").records
    league = games("games_team")
    now = Profiles(stats, league, "Biscuit Belt", team="Swampwater Tech").rows("Swampwater Tech")
    rows = last_season(now, Profiles(stats, league, "Biscuit Belt", team="Swampwater Tech"), "Swampwater Tech")
    assert len(rows) == len(now) and all(r["better"] is None for r in rows)  # the same numbers: no change
    shifted = [dict(r, value=(r["value"] + 1) if isinstance(r["value"], (int, float)) else None) for r in now]
    rows = last_season(shifted, Profiles(stats, league, "Biscuit Belt", team="Swampwater Tech"), "Swampwater Tech")
    ppg = next(r for r in rows if r["key"] == "ppg")
    assert ppg["better"] is True  # more points than last season
    allowed = next((r for r in rows if r["key"] == "opp_ppg" and r["now"]["value"] is not None), None)
    assert allowed is None or allowed["better"] is False  # more points allowed is worse
    assert last_season(now, None, "Swampwater Tech") == []
