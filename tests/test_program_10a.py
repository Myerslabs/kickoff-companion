"""Phase 10a, the program builder's items: season PPA play counts derived from total over average
(P1), an opponent's player card built from the opponent's own games (P2), no betting news on any
feed, fresh or stored, with a count on the Newspaper (P3), and the ride-alongs (P4): the team
page's location, Elo ranks that share ties like the Season page, and one radio source id."""

from __future__ import annotations

import asyncio
import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.cfbd.models import PlayerSeasonPpa, Team, TeamElo, TeamFPI, TeamSP, TeamTalent, parse_records
from app.feeds import FeedResult, FeedSpec, FeedStore, Headline, drop_betting, is_betting, merge_headlines, parse_feed, team_feeds, team_matcher
from app.services.parts import Part
from app.services.players import PPA_MIN_PLAYS, PPA_MIN_PLAYS_NATIONAL_CHECK
from app.services.profiles import rank_teams
from app.services.program import ProgramService
from app.services.stats_extra import num, ppa_plays, ppa_season_rows, ratings_rows, talent_lookup
from tests import league_facts as facts
from tests.conftest import ROLES, FakeCfbd, fixture_payload
from tests.test_players import route_players
from tests.test_program import route_program, set_clock
from tests.test_season import route_season

SPECS = {spec.id: spec for spec in team_feeds("Swampwater Tech", "Mudpuppies", "https://news.example.invalid/rss?path=football")}
MATCHER = team_matcher("Swampwater Tech", "Mudpuppies")
FEEDS = Path(__file__).parent / "fixtures" / "feeds"

# The two headlines that started P3 (The Athletic and Action Network, week of 2026-09-21), retold
# with the league's teams.
ACTION_NETWORK = ("College Football Picks, Predictions: Week 4 Expert Best Bets for Silo City vs Magnolia Flats, Diner Tech vs Swampwater Tech, More", "Action Network")
ATHLETIC = ("College football best bets Week 4: Should Diner Tech be an underdog at Swampwater Tech?", "The Athletic")

THEIR_QB_ID = ROLES["OPPQBID"]  # the opponent's starting quarterback, from the league
OUR_QB_ID = ROLES["QBID"]  # our starting quarterback, in the box of our last game
OPPONENT = next(t for t in fixture_payload("teams_fbs") if t["school"] == "Diner Tech")
OPP_PLAYED = sorted((g for g in fixture_payload("games_opponent") if g["completed"]), key=lambda g: g["week"])
OPP_GAMES = {g["week"]: g["id"] for g in OPP_PLAYED}  # Diner Tech's games before ours
BOX_WEEK = max(OPP_GAMES)  # the week whose box is made from our last game's
BOX_GAME = next(g for g in OPP_PLAYED if g["week"] == BOX_WEEK)
BOX_OPP = BOX_GAME["awayTeam"] if BOX_GAME["homeTeam"] == "Diner Tech" else BOX_GAME["homeTeam"]
LAST = facts.last_game()
LAST_OPP = LAST["awayTeam"] if LAST["homeTeam"] == "Swampwater Tech" else LAST["homeTeam"]


def _opponent(game: dict) -> str:
    return game["awayTeam"] if game["homeTeam"] == "Diner Tech" else game["homeTeam"]


def _result(game: dict) -> str:
    ours, theirs = (game["homePoints"], game["awayPoints"]) if game["homeTeam"] == "Diner Tech" else (game["awayPoints"], game["homePoints"])
    return f"{'W' if ours > theirs else 'L'} {ours}-{theirs}"


def _hamilton_passing() -> dict[str, str]:
    """Hamilton's passing line in the box of our last game, which the relabelled box gives Webb."""
    side = next(t for t in fixture_payload("games_players")[0]["teams"] if t["team"] == "Swampwater Tech")
    passing = next(c for c in side["categories"] if c["name"] == "passing")
    return {t["name"]: next(a["stat"] for a in t["athletes"] if a["id"] == OUR_QB_ID) for t in passing["types"]}


def run(coro):
    return asyncio.run(coro)


# --- P1: season PPA play counts ------------------------------------------------------------------


def _ppa(**fields) -> PlayerSeasonPpa:
    records = parse_records(PlayerSeasonPpa, [{"id": "1", "team": "Swampwater Tech", **fields}], context="t").records
    assert records, fields
    return records[0]


def test_ppa_plays_come_from_total_over_average_on_the_recording():
    records = parse_records(PlayerSeasonPpa, fixture_payload("ppa_players_season"), context="t").records
    plays = {r.name: ppa_plays(r) for r in records}
    truth = facts.ppa_play_counts()
    assert plays and all(plays[name] == truth[name] for name in plays if name in truth)
    assert all(isinstance(p, int) and p >= 1 for p in plays.values())
    assert all(r.countable_plays is None for r in records)  # CFBD never sends it, which is why the count is derived


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        ({"averagePPA": {"all": 0.5}, "totalPPA": {"all": 10.0}}, 20),
        ({"averagePPA": {"all": -0.25}, "totalPPA": {"all": -2.0}}, 8),  # a negative average still divides
        ({"averagePPA": {"all": 0}, "totalPPA": {"all": 3.0}}, None),  # average 0: no count
        ({"averagePPA": {"all": 0.004}, "totalPPA": {"all": 0.4}}, None),  # too small to divide by
        ({"averagePPA": {"all": 0.5}, "totalPPA": {}}, None),  # missing total
        ({"averagePPA": {"all": 0.5}}, None),  # no total block at all
        ({"averagePPA": {"all": "0.5"}, "totalPPA": {"all": "10"}}, None),  # strings are not numbers
        ({"averagePPA": {"all": True}, "totalPPA": {"all": 10.0}}, None),  # nor are booleans
        ({"averagePPA": {"all": 0.5}, "totalPPA": {"all": -10.0}}, None),  # signs disagree: not a count
        ({"averagePPA": {"all": 0.5}, "totalPPA": {"all": 0.0}}, None),  # zero total: not a count
        ({"averagePPA": {"all": 0}, "totalPPA": {"all": 3.0}, "countablePlays": 12}, 12),  # falls back to CFBD's count
        ({"countablePlays": 7}, 7),
        ({"averagePPA": {"all": 0.5}, "totalPPA": {"all": 10.0}, "countablePlays": 99}, 20),  # derived first
        ({"averagePPA": {"all": float("inf")}, "totalPPA": {"all": 10.0}}, None),  # the JSON reader accepts Infinity
        ({"averagePPA": {"all": 0.5}, "totalPPA": {"all": float("inf")}}, None),
        ({"averagePPA": {"all": 0.5}, "totalPPA": {"all": float("nan")}}, None),  # and NaN
        ({"averagePPA": {"all": float("nan")}, "totalPPA": {"all": float("nan")}, "countablePlays": 9}, 9),
        ({"averagePPA": {"all": 0.01}, "totalPPA": {"all": 1e307}}, None),  # the quotient overflows to inf
    ],
)
def test_ppa_plays_malformed_and_edge_cases(fields, expected):
    assert ppa_plays(_ppa(**fields)) == expected


def test_ppa_plays_survives_junk_blocks():
    junk = PlayerSeasonPpa.model_construct(id="1", team="Swampwater Tech", average_ppa="bad", total_ppa=["x"], countable_plays="12")
    assert ppa_plays(junk) is None
    rows = ppa_season_rows([junk], "Swampwater Tech", 10)
    assert len(rows) == 1 and rows[0]["plays"] is None and rows[0]["all"] is None


def test_num_reads_only_finite_numbers():
    assert num(1) == 1.0 and num(-0.5) == -0.5 and num(0) == 0.0
    assert num(float("inf")) is None and num(float("-inf")) is None and num(float("nan")) is None
    assert num(True) is None and num("1") is None and num(None) is None


def _json_with_nan(payload) -> httpx.Response:
    # httpx refuses to encode NaN; CFBD's answer reaches the client as bytes, and json.loads reads them.
    return httpx.Response(200, content=json.dumps(payload).encode(), headers={"content-type": "application/json"})


def test_non_finite_ppa_values_do_not_break_any_answer(client: TestClient, fake_cfbd: FakeCfbd):
    route_players(fake_cfbd)
    swt = copy.deepcopy(fixture_payload("ppa_players_season"))
    qb = next(r for r in swt if r["id"] == OUR_QB_ID)
    qb["averagePPA"]["all"] = float("nan")
    qb["totalPPA"]["all"] = float("inf")
    national = fixture_payload("ppa_players_season_all")

    def ppa_season(request: httpx.Request) -> httpx.Response:
        team = request.url.params.get("team")
        if team == "Swampwater Tech":
            return _json_with_nan(swt)
        if team:
            return httpx.Response(200, json=fixture_payload("ppa_players_season_opponent") if team == "Diner Tech" else [])
        return httpx.Response(200, json=national)

    fake_cfbd.route("/ppa/players/season", handler=ppa_season)
    leaders = client.get("/api/season/leaders")
    assert leaders.status_code == 200
    ppa = next(b for b in leaders.json()["data"]["extraBoards"] if b["id"] == "ppa:all")
    assert ppa["team"] and OUR_QB_ID not in [e["playerId"] for e in ppa["team"]]  # no average, so no place on the board
    roster = client.get("/api/roster")
    assert roster.status_code == 200
    row = next(p for p in roster.json()["data"]["players"] if p["playerId"] == OUR_QB_ID)
    assert row["ppaPlays"] is None
    assert client.get(f"/api/players/{OUR_QB_ID}").status_code == 200


def test_national_board_keeps_a_fifty_play_player_whose_count_reads_low(client: TestClient, fake_cfbd: FakeCfbd):
    """CFBD passed this player at threshold=50, but 0.475 over an average rounded to 0.010 derives 48.
    The local floor sits under that, so the national board and his national rank keep him."""
    route_players(fake_cfbd)
    low = {"season": 2026, "id": "990001", "name": "Low Average", "position": "RB", "team": "Diner Tech", "conference": OPPONENT["conference"], "averagePPA": {"all": 0.010, "pass": None, "rush": 0.010}, "totalPPA": {"all": 0.475, "pass": None, "rush": 0.475}}
    record = parse_records(PlayerSeasonPpa, [low], context="t").records[0]
    assert ppa_plays(record) == 48 and PPA_MIN_PLAYS_NATIONAL_CHECK < 48 < PPA_MIN_PLAYS
    national = fixture_payload("ppa_players_season_all") + [low]

    def ppa_season(request: httpx.Request) -> httpx.Response:
        team = request.url.params.get("team")
        if team == "Swampwater Tech":
            return httpx.Response(200, json=fixture_payload("ppa_players_season"))
        if team == "Diner Tech":
            return httpx.Response(200, json=[low])
        return httpx.Response(200, json=national)

    fake_cfbd.route("/ppa/players/season", handler=ppa_season)
    ppa = next(b for b in client.get("/api/season/leaders").json()["data"]["extraBoards"] if b["id"] == "ppa:all")
    entry = next(e for e in ppa["opponent"] if e["playerId"] == "990001")
    assert entry["detail"]["plays"] == 48 and isinstance(entry["nationalRank"], int)
    assert isinstance(entry["conferenceRank"], int) == (OPPONENT["conference"] == "Biscuit Belt")  # the conference column is ours
    assert all(e["detail"]["plays"] is None or e["detail"]["plays"] >= PPA_MIN_PLAYS_NATIONAL_CHECK for e in ppa["national"])


def test_leaders_play_value_board_honours_the_ten_play_minimum(client: TestClient, fake_cfbd: FakeCfbd):
    route_players(fake_cfbd)
    body = client.get("/api/season/leaders").json()
    ppa = next(b for b in body["data"]["extraBoards"] if b["id"] == "ppa:all")
    assert ppa["team"] and all(e["detail"]["plays"] >= 10 for e in ppa["team"])
    truth = facts.ppa_play_counts()
    averages = {r["name"]: r["averagePPA"]["all"] for r in fixture_payload("ppa_players_season")}
    few = {name for name, plays in truth.items() if plays < 10}
    assert few and few.isdisjoint(e["player"] for e in ppa["team"])  # a few-play player once led the board
    leader = max((name for name, plays in truth.items() if plays >= 10 and name in averages), key=lambda name: averages[name])
    assert ppa["team"][0]["player"] == leader and ppa["team"][0]["detail"]["plays"] == truth[leader]
    assert all(e["detail"]["plays"] is None or e["detail"]["plays"] >= 50 for e in ppa["national"])
    roster = client.get("/api/roster").json()["data"]["players"]
    qb = next(p for p in roster if p["playerId"] == OUR_QB_ID)
    assert qb["ppaPlays"] == truth[qb["name"]]


# --- P2: an opponent's player card ---------------------------------------------------------------


def _relabeled_box(game_id: int, player_id: str) -> list[dict]:
    """The box of our last game as Diner Tech's BOX_WEEK game: Swampwater Tech becomes Diner Tech, our
    opponent becomes theirs, and Hamilton's lines become the chosen Diner Tech player's."""
    box = copy.deepcopy(fixture_payload("games_players"))
    box[0]["id"] = game_id
    for side in box[0]["teams"]:
        side["team"] = {"Swampwater Tech": "Diner Tech", LAST_OPP: BOX_OPP}.get(side["team"], side["team"])
        for category in side["categories"]:
            for stat_type in category["types"]:
                for athlete in stat_type["athletes"]:
                    if athlete["id"] == OUR_QB_ID:
                        athlete["id"], athlete["name"] = player_id, "Cole Webb"
    return box


def _relabeled_ppa(player_id: str) -> list[dict]:
    rows = copy.deepcopy(fixture_payload("ppa_players_games"))
    rows[0].update({"id": player_id, "name": "Cole Webb", "position": "QB", "team": "Diner Tech", "opponent": BOX_OPP, "week": BOX_WEEK})
    return rows


def route_opponent_card(fake: FakeCfbd, league: list[dict] | None = None) -> None:
    """route_players plus a league-wide /games answer that holds Diner Tech's games, and a Diner Tech
    box score and per-game PPA for BOX_WEEK made from those of our last game."""
    route_players(fake)
    league = league if league is not None else fixture_payload("games_week") + fixture_payload("games_team") + fixture_payload("games_opponent")

    def games(request: httpx.Request) -> httpx.Response:
        team = request.url.params.get("team")
        if team == "Swampwater Tech":
            return httpx.Response(200, json=fixture_payload("games_team"))
        if team:
            return httpx.Response(200, json=fixture_payload("games_opponent"))
        return httpx.Response(200, json=league)

    swt_boxes = fake.routes["/games/players"]

    def boxes(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("team") == "Diner Tech":
            week = request.url.params.get("week")
            return httpx.Response(200, json=_relabeled_box(OPP_GAMES[BOX_WEEK], THEIR_QB_ID) if week == str(BOX_WEEK) else [])
        return swt_boxes(request)

    swt_ppa = fake.routes["/ppa/players/games"]

    def ppa_games(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("team") == "Diner Tech":
            return httpx.Response(200, json=_relabeled_ppa(THEIR_QB_ID) if request.url.params.get("week") == str(BOX_WEEK) else [])
        return swt_ppa(request)

    fake.route("/games", handler=games)
    fake.route("/games/players", handler=boxes)
    fake.route("/ppa/players/games", handler=ppa_games)


def _requests(fake: FakeCfbd, path: str) -> list[httpx.QueryParams]:
    return [r.url.params for r in fake.requests if r.url.path == path]


def test_opponent_card_game_log_comes_from_the_opponents_own_games(client: TestClient, fake_cfbd: FakeCfbd):
    route_opponent_card(fake_cfbd)
    body = client.get(f"/api/players/{THEIR_QB_ID}").json()
    assert body["errors"] == []
    data = body["data"]
    assert data["player"]["team"] == "Diner Tech" and data["player"]["isUs"] is False
    log = data["gameLog"]
    assert len(OPP_GAMES) >= 2 and [g["week"] for g in log] == sorted(OPP_GAMES) and [g["gameId"] for g in log] == [OPP_GAMES[w] for w in sorted(OPP_GAMES)]
    assert [g["opponent"] for g in log] == [_opponent(g) for g in OPP_PLAYED] and log[-1]["result"] == _result(BOX_GAME)
    assert log[-1]["homeAway"] == ("home" if BOX_GAME["homeTeam"] == "Diner Tech" else "away")
    passing = next(line for line in log[-1]["lines"] if line["category"] == "passing")
    hamilton = _hamilton_passing()
    assert passing["stats"]["YDS"] == float(hamilton["YDS"]) and passing["stats"]["C/ATT"] == hamilton["C/ATT"]
    assert log[0]["lines"] == [] and data["missingWeeks"] == []
    average = fixture_payload("ppa_players_games")[0]["averagePPA"]
    assert data["ppa"]["games"] == [{"week": BOX_WEEK, "opponent": BOX_OPP, "all": average["all"], "pass": average["pass"], "rush": average["rush"]}]
    assert data["parts"]["games"]["status"] == "ok" and data["parts"][f"box_Diner Tech_{BOX_WEEK}"]["status"] == "ok"
    # Box scores and per-game PPA for Diner Tech only, never Swampwater Tech's; the schedule is the league-wide answer, no new call.
    assert {p.get("team") for p in _requests(fake_cfbd, "/games/players")} == {"Diner Tech"}
    assert {p.get("team") for p in _requests(fake_cfbd, "/ppa/players/games")} == {"Diner Tech"}
    games_calls = _requests(fake_cfbd, "/games")
    assert all(p.get("team") in (None, "Swampwater Tech") for p in games_calls) and sum(1 for p in games_calls if p.get("team") is None) == 1


def test_opponent_card_follows_the_opponents_weeks_not_ours(client: TestClient, fake_cfbd: FakeCfbd):
    # Diner Tech with an open date in its first week while Swampwater Tech played: its card must skip that week.
    first = min(OPP_GAMES)
    assert first in {g["week"] for g in fixture_payload("games_team") if g["completed"]}
    league = [g for g in fixture_payload("games_week") + fixture_payload("games_team") + fixture_payload("games_opponent") if g.get("id") != OPP_GAMES[first]]
    route_opponent_card(fake_cfbd, league)
    data = client.get(f"/api/players/{THEIR_QB_ID}").json()["data"]
    weeks = [w for w in sorted(OPP_GAMES) if w != first]
    assert [g["week"] for g in data["gameLog"]] == weeks
    assert sorted(p.get("week") for p in _requests(fake_cfbd, "/games/players")) == [str(w) for w in weeks]
    assert sorted(p.get("week") for p in _requests(fake_cfbd, "/ppa/players/games")) == [str(w) for w in weeks]
    assert data["ppa"]["games"][0]["week"] == BOX_WEEK


def test_opponent_card_uses_the_same_cache_entry_as_the_season_view(app, client: TestClient, fake_cfbd: FakeCfbd):
    route_opponent_card(fake_cfbd)
    client.get(f"/api/players/{THEIR_QB_ID}")
    first = sum(1 for p in _requests(fake_cfbd, "/games") if p.get("team") is None)
    client.get(f"/api/players/{fixture_payload('roster_opponent')[0]['id']}")  # a second opponent card
    assert sum(1 for p in _requests(fake_cfbd, "/games") if p.get("team") is None) == first == 1


def test_opponent_card_survives_a_dead_league_wide_schedule(client: TestClient, fake_cfbd: FakeCfbd):
    route_opponent_card(fake_cfbd)
    original = fake_cfbd.routes["/games"]
    fake_cfbd.route("/games", handler=lambda r: httpx.Response(500, text="down") if r.url.params.get("team") is None else original(r))
    response = client.get(f"/api/players/{THEIR_QB_ID}")
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["gameLog"] == [] and body["data"]["parts"]["games"]["status"] == "error"
    assert any(e["message"].startswith("games:") for e in body["errors"])
    assert _requests(fake_cfbd, "/games/players") == []  # no Swampwater Tech box scores stand in for the opponent's


def test_opponent_card_skips_malformed_league_games(client: TestClient, fake_cfbd: FakeCfbd):
    junk = [None, "x", {"id": "not-an-int"}, {"id": 1, "week": None, "completed": True, "homeTeam": "Diner Tech", "awayTeam": "X"}, {"id": 2, "week": 2, "completed": None, "homeTeam": "Diner Tech", "awayTeam": "Y"}]
    route_opponent_card(fake_cfbd, junk + fixture_payload("games_opponent") + fixture_payload("games_opponent"))  # every game twice
    data = client.get(f"/api/players/{THEIR_QB_ID}").json()["data"]
    assert [g["gameId"] for g in data["gameLog"]] == [OPP_GAMES[w] for w in sorted(OPP_GAMES)]
    assert data["parts"]["games"]["skipped"] >= 3


def test_our_card_still_reads_our_schedule_and_boxes(client: TestClient, fake_cfbd: FakeCfbd):
    route_opponent_card(fake_cfbd)
    data = client.get(f"/api/players/{OUR_QB_ID}").json()["data"]
    played = sorted((g for g in fixture_payload("games_team") if g["completed"]), key=lambda g: g["week"])
    assert [g["gameId"] for g in data["gameLog"]] == [g["id"] for g in played] and "games" not in data["parts"]
    assert {p.get("team") for p in _requests(fake_cfbd, "/games/players")} == {"Swampwater Tech"} and data["parts"][f"box_Swampwater Tech_{LAST['week']}"]["status"] == "ok"
    # the card's own game log reads our schedule only; the stat grade (public release Phase 7) reads the season's
    # games, the Season page's shared key, for each team's games played
    assert all(p.get("team") == "Swampwater Tech" for p in _requests(fake_cfbd, "/games") if set(p.keys()) != {"year"})


# --- P3: no betting news ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("title", "source"),
    [
        ACTION_NETWORK,
        ATHLETIC,
        ("Diner Tech vs Swampwater Tech Odds: Should Mudpuppies Really Be Favored Over Rebels?", "Yahoo Sports"),
        ("Diner Tech vs. Swampwater Tech: Mudpuppies open as 2.5 point favorites", "Yahoo Sports"),
        ("Swampwater Tech a 3-point underdog at Sweet Tea State", "Swamp County Sun"),
        ("Swampwater Tech favored by 3 over Diner Tech", "On3"),
        ("Swampwater Tech vs. Diner Tech predictions, picks, odds: Early lines for Week 4", "mudpuppieswire.usatoday.com"),
        ("Swampwater Tech's College Football Playoff Odds Skyrocket After 3-0 Start", "Yahoo Sports"),
        ("Is it time to bet on Swampwater Tech?", "ESPN"),
        ("Week 4 betting guide: Swampwater Tech vs Diner Tech", "ESPN"),
        ("DraftKings promo code: $200 in bonus bets for Swampwater Tech-Diner Tech", "Sports Site"),
        ("FanDuel Sportsbook boosts Mudpuppies", "Sports Site"),
        ("BetMGM bonus code for Saturday", "Sports Site"),
        ("Caesars Sportsbook offer for Biscuit Belt Week 4", "Sports Site"),
        ("bet365 Swampwater Tech promo", "Sports Site"),
        ("ESPN BET markets move on Swampwater Tech", "ESPN"),
        ("Fanatics Sportsbook adds Biscuit Belt boosts", "Sports Site"),
        ("BetRivers weekend offer", "Sports Site"),
        ("Hard Rock Bet Swampwater Tech launch", "Sports Site"),
        ("Bovada lists Mudpuppies", "Sports Site"),
        ("Lucas Griffin player props for Week 4", "Sports Site"),
        ("Swampwater Tech vs Diner Tech prop bets", "Sports Site"),
        ("Swampwater Tech moneyline pick", "Sports Site"),
        ("Swampwater Tech-Diner Tech over/under: 61.5", "Sports Site"),
        ("Swampwater Tech vs Diner Tech O/U lean", "Sports Site"),
        ("Swampwater Tech vs Diner Tech point spread", "Sports Site"),
        ("Mudpuppies are 3-0 against the spread", "Sports Site"),
        ("Swampwater Tech is 3-0 ATS this season", "Sports Site"),
        ("Can Swampwater Tech cover the spread against Diner Tech?", "Sports Site"),
        ("Sharp money is on the Mudpuppies", "Sports Site"),
        ("A four-leg Biscuit Belt parlay with Swampwater Tech", "Sports Site"),
        ("Where to wager on Mudpuppies-Cooks", "Sports Site"),
        ("Mudpuppies an underdog on the opening line", "Sports Site"),
        ("Diner Tech favored, but the spread keeps moving toward Swampwater Tech", "Sports Site"),
        ("Week 4 expert picks for Swampwater Tech vs Diner Tech", "Covers"),
        ("Diner Tech vs Swampwater Tech pick", "covers.com"),
        ("Swampwater Tech vs Diner Tech pick", "actionnetwork.com"),
        ("Swampwater Tech vs. Diner Tech prediction", "SportsLine"),
        ("Swampwater Tech vs. Diner Tech prediction", "VegasInsider"),
        ("Swampwater Tech vs. Diner Tech prediction", "Pickswise"),
        ("Swampwater Tech vs. Diner Tech prediction", "OddsShark"),
        ("Swampwater Tech vs. Diner Tech prediction", "BetQL"),
        ("Swampwater Tech vs. Diner Tech prediction", "Sportsbook Review"),
        ("Mudpuppies computer picks from SportsLine's model", "CBS Sports"),
        # A line's size with a word or two before the side, or sized in words.
        ("Swampwater Tech opens as 6.5-point home underdog vs Diner Tech", "Yahoo Sports"),
        ("Swampwater Tech Mudpuppies are 7-point road underdogs", "Swamp County Sun"),
        ("Diner Tech opens as double-digit favorite over Swampwater Tech", "On3"),
        ("Diner Tech a touchdown favorite at Swampwater Tech", "247Sports"),
        ("Swampwater Tech a field goal home underdog against Diner Tech", "On3"),
        # The USA Today form, and signed lines.
        ("Diner Tech vs. Swampwater Tech prediction, pick, spread", "mudpuppieswire.usatoday.com"),
        ("Swampwater Tech vs. Diner Tech picks: spread and total for Week 4", "Sports Site"),
        ("Diner Tech vs Swampwater Tech prediction: Cooks -6.5 on the road", "Sports Site"),
        ("Diner Tech vs Swampwater Tech prediction: Cooks −6.5 on the road", "Sports Site"),  # a typographic minus
        ("Swampwater Tech (+3) at Diner Tech: what to know", "Sports Site"),
        # Typographic apostrophes in a brand, in the title or as the source.
        ("Doc’s Sports Swampwater Tech pick", "Sports Site"),
        ("Swampwater Tech vs Diner Tech pick", "Doc’s Sports"),
    ],
)
def test_betting_headlines_are_dropped(title, source):
    assert is_betting(title, source), (title, source)


@pytest.mark.parametrize(
    ("title", "source"),
    [
        ("Swampwater Tech's spread offense takes shape under Pettibone", "Swamp County Sun"),
        ("Mudpuppies Position Preview: Offensive Line", "Swampwater Tech Mudpuppies"),
        ("Mudpuppies Position Preview: Defensive Line", "Swampwater Tech Mudpuppies"),
        ("Moore Named Biscuit Belt Offensive Lineman of the Week", "SWT Athletics"),
        ("Griffin picks up where he left off", "On3"),
        ("Swampwater Tech picks up a four-star commitment", "On3"),
        ("Pebble Creek added to 2028 schedule", "SWT Athletics"),
        ("Mudpuppies get better between the tackles", "MudpuppyCountry.com"),
        ("College Football Straight Up Picks for Every Top 25 Game in Week 4 (Swampwater Tech Will Beat Diner Tech in Biscuit Belt Showdown)", "Sports Illustrated"),
        ("Our staff picks for Swampwater Tech vs Diner Tech", "Swamp County Sun"),
        ("Swampwater Tech vs. Diner Tech predictions from our staff", "Swamp County Sun"),
        ("Jon Pettibone has brash response to Swampwater Tech being favored over Diner Tech", "mudpuppieswire.usatoday.com"),
        ("Mudpuppies coach surprised to be favored vs. No. 4 Diner Tech", "ESPN"),
        ("Fan favorite returns to the Swamp", "Swampwater Tech Mudpuppies"),
        ("Swampwater Tech, an underdog story, climbs the rankings", "USA Today"),
        ("Against all odds, Swampwater Tech rallies at Silver Dollar", "USA Today"),
        ("Mudpuppies defy the odds in the fourth quarter", "USA Today"),
        ("Swampwater Tech holds the line of scrimmage", "USA Today"),
        ("Goal-line stand seals it for Swampwater Tech", "USA Today"),
        ("Swampwater Tech's defense runs the spread option out of Swamp County", "On3"),
        ("Halvorsen gives props to Swampwater Tech's defense", "On3"),
        ("Swampwater Tech Mudpuppies football: Tracking the transfers", "On3"),
        ("Swampwater Tech-Diner Tech Game Set for 3:30 Kick on ABC", "Swampwater Tech Mudpuppies"),
        ("Gravy Bowl at Caesars Superdome in Swampwater Tech's sights", "ESPN"),
        ("Biscuit Belt Network covers Swampwater Tech's practice", "Biscuit Belt Network"),
        ("Alphabet soup: Swampwater Tech's new formations", "On3"),
        ("Swampwater Tech's offensive line holds up as the Mudpuppies are favored to win the East", "On3"),
        ("Mudpuppies' secondary props up a young defense", "On3"),
        ("Swampwater Tech wins 24-17 on a late field goal", "SWT Athletics"),
        ("Swampwater Tech (3-0) hosts Diner Tech on 2026-09-26", "SWT Athletics"),
        ("Swampwater Tech lost a 21-point lead to the favorite", "USA Today"),
        ("Griffin touchdown run a fan favorite", "On3"),
        ("Swampwater Tech vs. Diner Tech: prediction and three things to watch", "Swamp County Sun"),
        ("Swampwater Tech's total offense ranks first in the Biscuit Belt; our predictions for Saturday", "On3"),
        ("Mudpuppies spread the wealth in the passing game; predictions for Week 4", "On3"),
        ("Swampwater Tech picks off three passes and spreads out the defense", "On3"),
        ("Swampwater Tech picks up a total of five commitments", "On3"),
    ],
)
def test_ordinary_headlines_stay(title, source):
    assert not is_betting(title, source), (title, source)


def test_betting_inputs_of_any_type_never_raise():
    assert is_betting(None) is False and is_betting(7, ["x"], {"url": 1}) is False
    assert is_betting("", "", "") is False and is_betting("Mudpuppies win", None, "not a url") is False
    assert is_betting("Mudpuppies win", "Site", "https://www.actionnetwork.com/ncaaf/swampwater-tech") is True  # a betting site's story
    assert is_betting("Mudpuppies win", "Site", "https://sportsbook.draftkings.com/x") is True  # a subdomain counts
    assert is_betting("Mudpuppies win", "Site", "https://news.google.com/rss/articles/CBMi-odds-bets") is False  # redirect ids are not read
    assert is_betting("Mudpuppies win", "Site", "https://www.espn.com/college-football/story/_/id/1/betting-odds") is False  # slugs are not read
    assert is_betting("Mudpuppies win", "Site", "http://[::1") is False  # an address that does not parse


def test_real_headlines_are_dropped_with_their_sources():
    assert is_betting(*ACTION_NETWORK) and is_betting(ACTION_NETWORK[0]) and is_betting("Week 4 picks", ACTION_NETWORK[1])
    assert is_betting(*ATHLETIC) and is_betting(ATHLETIC[0])


def _rss(*items: tuple[str, str | None]) -> bytes:
    body = "".join(f"<item><title>{t}</title><link>https://x/{i}</link>{f'<source>{s}</source>' if s else ''}<pubDate>Tue, 22 Sep 2026 1{i}:00:00 GMT</pubDate></item>" for i, (t, s) in enumerate(items))
    return f"<rss><channel>{body}</channel></rss>".encode()


def test_parse_drops_and_counts_betting_headlines():
    body = _rss(
        (ACTION_NETWORK[0], ACTION_NETWORK[1]),
        (ATHLETIC[0], None),
        ("Swampwater Tech names a starter", None),
        ("Week 4 picks - Action Network", None),  # Google's " - Source" suffix names the betting site
        ("Silo City vs Magnolia Flats odds", None),  # not about Swampwater Tech: the national filter drops it first, uncounted
    )
    general = parse_feed(body, FeedSpec("t", "T", "https://x"))
    assert [h.title for h in general.headlines] == ["Swampwater Tech names a starter"] and general.betting == 4 and general.skipped == 0
    national = parse_feed(body, FeedSpec("n", "N", "https://x", team_only=True), MATCHER)
    assert [h.title for h in national.headlines] == ["Swampwater Tech names a starter"] and national.betting == 2


def test_feed_fixtures_hold_betting_headlines_and_lose_them():
    athletic = parse_feed((FEEDS / "athletic.xml").read_bytes(), SPECS["athletic"], MATCHER)
    google = parse_feed((FEEDS / "google.xml").read_bytes(), SPECS["google"], MATCHER)
    assert athletic.betting >= 1 and google.betting >= 1
    assert ATHLETIC[0] not in [h.title for h in athletic.headlines]
    for h in athletic.headlines + google.headlines:
        assert not is_betting(h.title, h.source, h.url)


def _store(tmp_path: Path, handler, now: datetime) -> FeedStore:
    return FeedStore(tmp_path, feeds=(SPECS["team"],), transport=httpx.MockTransport(handler), clock=lambda: now)


def _write_stored(tmp_path: Path, fetched_at: datetime, headlines: list[dict], **extra) -> None:
    (tmp_path / "feeds").mkdir(parents=True, exist_ok=True)
    (tmp_path / "feeds" / "team.json").write_text(json.dumps({"fetchedAt": fetched_at.isoformat(), "skipped": 0, "headlines": headlines, **extra}), encoding="utf-8")


STORED = [
    {"title": ATHLETIC[0], "url": "https://x/1", "source": "The Athletic", "publishedAt": "2026-09-22T10:00:00Z"},
    {"title": "Week 4 expert picks", "url": "https://x/2", "source": "Action Network", "publishedAt": "2026-09-22T11:00:00Z"},
    {"title": "SOLD OUT: Diner Tech Game Marks 21st-Straight Sellout for Mudpuppies", "url": "https://x/3", "source": "SWT Athletics", "publishedAt": "2026-09-23T10:00:00Z"},
    {"title": None, "url": "https://x/4"},
    "junk",
    {"title": "Moore Named Biscuit Belt Offensive Lineman of the Week", "url": 7, "source": ["x"], "publishedAt": 5},
]


def test_stored_betting_headlines_are_hidden_when_read_back(tmp_path: Path):
    now = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)
    _write_stored(tmp_path, now - timedelta(minutes=5), STORED)  # saved before the rule, still fresh
    calls: list[str] = []
    store = _store(tmp_path, lambda r: calls.append(str(r.url)) or httpx.Response(503), now)

    async def scenario():
        result = await store.get(SPECS["team"])
        await store.aclose()
        return result

    result = run(scenario())
    assert calls == []  # served from disk, no fetch
    assert [h.title for h in result.headlines] == ["SOLD OUT: Diner Tech Game Marks 21st-Straight Sellout for Mudpuppies", "Moore Named Biscuit Belt Offensive Lineman of the Week"]
    assert result.headlines[1].url is None and result.headlines[1].source == SPECS["team"].name and result.headlines[1].published_at is None
    assert result.betting == 2 and result.status(now)["betting"] == 2


def test_stale_feed_keeps_its_betting_count_and_a_fresh_one_stores_it(tmp_path: Path):
    now = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)
    _write_stored(tmp_path, now - timedelta(hours=3), STORED, betting="lots")  # a junk stored count reads as 0
    store = _store(tmp_path, lambda r: httpx.Response(503), now)

    async def stale():
        result = await store.get(SPECS["team"])
        await store.aclose()
        return result

    result = run(stale())
    assert result.stale and result.betting == 2 and result.status(now)["status"] == "stale" and len(result.headlines) == 2

    body = _rss(("Mudpuppies win", None), (ACTION_NETWORK[0], ACTION_NETWORK[1]), ("Swampwater Tech odds shift", None))
    fresh_dir = tmp_path / "fresh"
    fresh_store = _store(fresh_dir, lambda r: httpx.Response(200, content=body), now)

    async def fresh():
        first = await fresh_store.get(SPECS["team"])
        fresh_store._memory.clear()
        again = await fresh_store.get(SPECS["team"])  # read back from disk: the count is kept, not doubled
        await fresh_store.aclose()
        return first, again

    first, again = run(fresh())
    assert first.betting == 2 and [h.title for h in first.headlines] == ["Mudpuppies win"]
    assert json.loads((fresh_dir / "feeds" / "team.json").read_text(encoding="utf-8"))["betting"] == 2
    assert again.betting == 2 and [h.title for h in again.headlines] == ["Mudpuppies win"]


def test_a_feed_holding_only_betting_news_is_working_not_broken(tmp_path: Path):
    now = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)
    body = b"<rss><channel><item><link>https://x/no-title</link></item><item><title>Swampwater Tech odds for Week 4</title></item></channel></rss>"
    store = _store(tmp_path, lambda r: httpx.Response(200, content=body), now)

    async def scenario():
        result = await store.get(SPECS["team"])
        await store.aclose()
        return result

    result = run(scenario())
    assert result.error is None and not result.stale and result.headlines == [] and result.skipped == 1 and result.betting == 1
    assert result.status(now)["status"] == "ok"


def test_merge_is_the_last_gate():
    result = FeedResult(SPECS["team"], [Headline(ATHLETIC[0], None, "The Athletic", "team", "2026-09-22T00:00:00Z"), Headline("Mudpuppies win", None, "SWT", "team", "2026-09-21T00:00:00Z")])
    assert [h["title"] for h in merge_headlines([result])] == ["Mudpuppies win"]
    kept, dropped = drop_betting(result.headlines)
    assert [h.title for h in kept] == ["Mudpuppies win"] and dropped == 1


@pytest.fixture
def program_client(settings, fake_cfbd: FakeCfbd):
    from app.logging_setup import configure_logging, shutdown_logging
    from app.main import create_app
    from tests.test_program import FakeSites

    configure_logging(settings)
    route_program(fake_cfbd)
    transport = httpx.MockTransport(FakeSites().handler)
    application = create_app(settings, cfbd_transport=fake_cfbd.transport, feeds_transport=transport, weather_transport=transport)
    with TestClient(application, base_url="https://testserver") as test_client:
        set_clock(application, datetime(2026, 9, 23, 16, 0, tzinfo=timezone.utc))
        yield test_client, application
    shutdown_logging()


def test_newspaper_shows_no_betting_news_and_counts_it(program_client):
    client, application = program_client
    feeds_dir: Path = application.state.settings.data_dir / "feeds"
    feeds_dir.mkdir(parents=True, exist_ok=True)
    (feeds_dir / "team.json").write_text(json.dumps({"fetchedAt": "2026-09-23T15:55:00+00:00", "skipped": 0, "headlines": STORED}), encoding="utf-8")
    data = client.get("/api/newspaper").json()["data"]
    assert data["news"] and all(not is_betting(h["title"], h["source"], h["url"]) for h in data["news"])
    assert ATHLETIC[0] not in [h["title"] for h in data["news"]]
    feeds = data["feeds"]
    assert feeds["team"]["betting"] == 2 and feeds["team"]["count"] == 2  # the stored copy, read back through the filter
    assert feeds["athletic"]["betting"] >= 1 and feeds["google"]["betting"] >= 1 and all(isinstance(f["betting"], int) for f in feeds.values())


# --- P4: ride-alongs ---------------------------------------------------------------------------------


def test_team_page_carries_its_location(program_client):
    client, _ = program_client
    data = client.get("/api/team/Diner%20Tech").json()["data"]
    where = OPPONENT["location"]
    assert data["location"] == {"city": where["city"], "state": where["state"], "venue": where["name"], "capacity": where["capacity"]}
    ours = next(t["location"] for t in fixture_payload("teams_fbs") if t["school"] == "Swampwater Tech")
    assert client.get("/api/team/Swampwater Tech").json()["data"]["location"]["city"] == ours["city"]


@pytest.mark.parametrize(
    ("location", "expected"),
    [
        (None, None),
        ({}, None),
        ({"name": "Stadium"}, None),  # no city or state to show
        ({"city": " Oxford ", "state": None, "capacity": "big"}, {"city": "Oxford", "state": None, "venue": None, "capacity": None}),
        ({"city": 5, "state": "MS", "name": ["x"], "capacity": True}, {"city": None, "state": "MS", "venue": None, "capacity": None}),
    ],
)
def test_team_location_guards_every_field(location, expected):
    team = Team.model_construct(id=1, school="Diner Tech", location=location)
    assert ProgramService._location(Part("teams", [team]), "Diner Tech") == expected
    assert ProgramService._location(Part("teams", [team]), "Nowhere") is None
    assert ProgramService._location(Part("teams", [Team.model_construct(id=2, school="Diner Tech", location="Oxford, MS")]), "Diner Tech") is None


def test_ratings_elo_ranks_share_ties_like_the_season_page():
    elo = parse_records(TeamElo, fixture_payload("ratings_elo"), context="t").records
    rows = ratings_rows(
        parse_records(TeamSP, fixture_payload("ratings_sp"), context="t").records,
        elo,
        parse_records(TeamFPI, fixture_payload("ratings_fpi"), context="t").records,
        parse_records(TeamTalent, fixture_payload("talent"), context="t").records,
    )
    season_ranks, _ = rank_teams({r.team: float(r.elo) for r in elo if r.elo is not None}, True)  # what season.py computes
    by_team = {r["team"]: r for r in rows}
    ours = by_team["Swampwater Tech"]["elo"]
    assert ours["rank"] == season_ranks["Swampwater Tech"]
    level = next(value for value in sorted({r.elo for r in elo if r.elo is not None}) if sum(r.elo == value for r in elo) >= 2)
    tied = [r.team for r in elo if r.elo == level and r.team in by_team]
    assert len(tied) >= 2  # the league has teams level on Elo
    assert len({by_team[t]["elo"]["rank"] for t in tied}) == 1 and by_team[tied[0]]["elo"]["rank"] == season_ranks[tied[0]]
    assert all(row["elo"]["rank"] == season_ranks.get(row["team"]) for row in rows)
    tie = talent_lookup([TeamTalent(team="A", talent=900.0), TeamTalent(team="B", talent=900.0), TeamTalent(team="C", talent=800.0)])
    assert [tie[t]["rank"] for t in "ABC"] == [1, 1, 3]


def test_ratings_page_and_season_page_agree_on_our_elo_rank(client: TestClient, fake_cfbd: FakeCfbd):
    route_season(fake_cfbd)
    fake_cfbd.fixture("/talent", "talent")
    season = client.get("/api/season/overview").json()["data"]["ratings"]["elo"]
    ratings = next(r for r in client.get("/api/ratings").json()["data"]["rows"] if r["team"] == "Swampwater Tech")["elo"]
    assert isinstance(season["rank"], int) and season["rank"] == ratings["rank"]


RADIO = '[{"name": "WSTS 98.1 stream", "kind": "stream", "url": "https://radio.example.org/wsts"}, {"name": "WSTS player", "kind": "link", "url": "https://radio.example.org/player"}]'


def test_settings_picker_uses_the_players_radio_source_ids(tmp_path: Path, fake_cfbd: FakeCfbd):
    from app.config import load_settings
    from app.logging_setup import configure_logging, shutdown_logging
    from app.main import create_app
    from tests.conftest import CONFERENCE, TEAM, TEST_KEY

    settings = load_settings(env_file=None, cfbd_api_key=TEST_KEY, team=TEAM, conference=CONFERENCE, log_dir=str(tmp_path / "logs"), data_dir=str(tmp_path / "data"), radio_sources=RADIO)
    configure_logging(settings)
    try:
        with TestClient(create_app(settings, cfbd_transport=fake_cfbd.transport), base_url="https://testserver") as client:
            player_ids = [s["id"] for s in client.get("/api/radio/sources").json()["data"]["sources"]]
            picker_ids = [s["id"] for s in client.get("/api/settings").json()["data"]["radioSources"]]
            assert picker_ids == player_ids and picker_ids[0] == "1-wsts-98-1-stream" and len(picker_ids) == 2
            saved = client.put("/api/settings", json={"radioSourceId": player_ids[1]}).json()["data"]
            assert saved["prefs"]["radioSourceId"] == player_ids[1] and saved["prefs"]["radioSourceId"] in [s["id"] for s in saved["radioSources"]]
    finally:
        shutdown_logging()
