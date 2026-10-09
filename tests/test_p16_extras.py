"""Phase 16 stream BX: the owner's picked ideas, backend side. Every pure function on the recorded
fixtures and on junk (missing keys, nulls, wrong types, empty arrays, a payload that is a dict, a
string or null): no crash, bad records skipped and counted, no NaN in the JSON. Then the routes:
the new fields are there, the matchup sheet and the recaps cost no CFBD call, and loading every
affected page asks CFBD for exactly the same calls with and without the new fields."""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.cfbd.models import (
    Game,
    Matchup,
    PassingPlay,
    PlayWinProbability,
    PollWeek,
    Recruit,
    RushingPlay,
    Team,
    TeamElo,
    TeamSP,
    TeamTalent,
    Venue,
    parse_records,
)
from app.config import load_settings
from app.live.engine import LiveEngine
from app.logging_setup import configure_logging, shutdown_logging
from app.main import create_app
from app.services import context16, recap16
from app.services.analytics import wp_series
from app.services.archive import ArchiveService
from app.services.matchup import slate_game, talent_ranks
from app.services.season import SeasonService
from tests import league_facts as facts
from tests.conftest import ROLES, TEST_KEY, FakeCfbd, fixture_payload
from tests.test_phase8 import quiet_engine
from tests.test_program import FakeSites, route_program

US = "Swampwater Tech"
LAST = facts.last_game()  # our last game, the archived final
LAST_GAME = LAST["id"]
HOME_IS_US = LAST["homeTeam"] == US
LAST_OPP = LAST["awayTeam"] if HOME_IS_US else LAST["homeTeam"]
KICKOFF = datetime.fromisoformat(LAST["startDate"].replace("Z", "+00:00"))
SAVED = KICKOFF + timedelta(hours=4)  # when the archive was written
NEXT = facts.next_game_row()
NEXT_GAME = NEXT["id"]
NEXT_KICKOFF = datetime.fromisoformat(NEXT["startDate"].replace("Z", "+00:00"))
PLAYED = sorted((g for g in fixture_payload("games_team") if g["completed"]), key=lambda g: g["week"])
JUNK_PAYLOADS: list[Any] = [
    None,
    "not json at all",
    {"unexpected": "object"},
    [],
    [None, 7, "x", [], {}],
    [{"id": "abc"}, {"id": None}, {"week": "three"}, {"team": 5}, {"school": None, "rank": "1"}],
]


def recs(name: str, model: Any) -> list[Any]:
    parsed = parse_records(model, fixture_payload(name), context=name)
    assert parsed.skipped == 0, parsed.problems
    return parsed.records


def strict_json(value: Any) -> str:
    """Serializes like the envelope does: NaN or infinity anywhere fails the test."""
    return json.dumps(value, allow_nan=False)


def series() -> list[dict[str, Any]]:
    return wp_series(recs("metrics_wp", PlayWinProbability))


def archived_state() -> dict[str, Any]:
    from app.cfbd.models import LiveGame, parse_one
    from app.live.events import events_from_live
    from app.live.state import derive_state

    game = parse_one(LiveGame, fixture_payload("live_plays"), context="t")
    events = events_from_live(game, SAVED)
    return derive_state(events, game_id=LAST_GAME, home=LAST["homeTeam"], away=LAST["awayTeam"], mode="archive")


def archive_body(**changes: Any) -> dict[str, Any]:
    body = {"gameId": LAST_GAME, "week": LAST["week"], "home": LAST["homeTeam"], "away": LAST["awayTeam"], "kickoff": KICKOFF.isoformat(), "savedAt": SAVED.isoformat(), "partial": False, "winProbability": None, "state": archived_state()}
    body.update(changes)
    return body


def side(game: dict[str, Any], team: str = US) -> dict[str, Any]:
    """A game row from one team's side: its points, the other's, the opponent and where."""
    home = game["homeTeam"] == team
    return {"points": game["homePoints" if home else "awayPoints"], "against": game["awayPoints" if home else "homePoints"],
            "opponent": game["awayTeam" if home else "homeTeam"], "homeAway": "home" if home else "away",
            "pre": game["homePregameElo" if home else "awayPregameElo"], "post": game["homePostgameElo" if home else "awayPostgameElo"],
            "wp": game["homePostgameWinProbability" if home else "awayPostgameWinProbability"]}


def result(game: dict[str, Any], team: str = US) -> str:
    row = side(game, team)
    return "W" if row["points"] > row["against"] else "L" if row["points"] < row["against"] else "T"


def record_through_last() -> dict[str, int]:
    results = [result(g) for g in PLAYED]
    return {"wins": results.count("W"), "losses": results.count("L"), "ties": results.count("T")}


def next_row() -> dict[str, Any]:
    return {"gameId": NEXT_GAME, "week": NEXT["week"], "postseason": None, "date": NEXT["startDate"], "startTimeTbd": False,
            "opponent": side(NEXT)["opponent"], "homeAway": side(NEXT)["homeAway"]}


def top_swing() -> dict[str, Any]:
    points = series()
    recap16.attach_game_time(points)
    return recap16.biggest_swings(points, HOME_IS_US)[0]


def at_venue(venue: str) -> dict[str, Any]:
    """Our record against the next opponent at a venue, read straight from the /teams/matchup answer."""
    games = fixture_payload("teams_matchup")["games"]
    here = [g for g in games if g.get("venue") == venue]
    return {"venue": venue, "opponent": fixture_payload("teams_matchup")["team2"], "wins": sum(g["winner"] == US for g in here),
            "losses": sum(g["winner"] not in (US, None) for g in here), "ties": sum(g["winner"] is None for g in here), "games": len(here),
            "gamesWithoutVenue": sum(not g.get("venue") for g in games)}


def in_state() -> tuple[str, list[dict[str, Any]], int]:
    state = next(t["location"]["state"] for t in fixture_payload("teams_fbs") if t["school"] == US)
    signed = [r for r in fixture_payload("recruiting_players") if r["committedTo"] == US]
    return state, [r for r in signed if r["stateProvince"] == state], len(signed)


# --- GX-17 form guide ------------------------------------------------------------------------------------------


def test_form_is_the_last_five_newest_last_and_counts_a_game_once():
    ours = recs("games_team", Game)
    table = context16.form_table(ours + ours)  # the all-FBS list plus the team's own schedule
    assert [r["result"] for r in table[US]] == [result(g) for g in PLAYED]
    assert [r["opponent"] for r in table[US]] == [side(g)["opponent"] for g in PLAYED]
    last = side(LAST)
    assert table[US][-1] == {"gameId": LAST_GAME, "week": LAST["week"], "postseason": None, "result": result(LAST), "points": last["points"], "opponentPoints": last["against"], "opponent": LAST_OPP, "homeAway": last["homeAway"]}
    assert table[LAST_OPP][-1]["result"] == result(LAST, LAST_OPP) and "Diner Tech" not in table  # an unplayed game is no form
    champion = context16.form_table(recs("games_team_2025_default", Game))[ROLES["POSTTEAM"]]
    assert len(champion) == 5 and champion[-1]["postseason"]  # newest last: the bowl season closes it
    assert context16.form_for(table, None) == [] and context16.form_for(table, "Nowhere") == []


# --- GX-06 rank paths -------------------------------------------------------------------------------------------


def season_polls(settings, weeks: list[PollWeek]) -> list[dict[str, Any]]:
    blocks, _ = SeasonService(None, settings)._polls(weeks, {})  # type: ignore[arg-type]
    return blocks


def test_poll_rows_gain_previous_rank_movement_and_the_ap_path(settings):
    weeks = recs("rankings_2025_default", PollWeek)
    blocks = season_polls(settings, weeks)
    context16.attach_poll_paths(blocks, weeks)
    ap = next(b for b in blocks if b["poll"] == "AP")
    assert len(ap["pathWeeks"]) == 17 and ap["pathWeeks"][-1] == {"week": 1, "seasonType": "postseason"} and ap["previousWeek"] == {"week": 16, "seasonType": "regular"}
    # independent reading of the raw answer: the AP poll of regular week 16 and of the final poll
    raw = fixture_payload("rankings_2025_default")
    def ap_ranks(week: int, season_type: str) -> dict[str, int]:
        w = next(x for x in raw if x["week"] == week and x["seasonType"] == season_type)
        return {r["school"]: r["rank"] for r in next(p for p in w["polls"] if p["poll"] == "AP Top 25")["ranks"]}
    before, final = ap_ranks(16, "regular"), ap_ranks(1, "postseason")
    for row in ap["ranks"]:
        assert row["apPath"][-1] == row["rank"] == final[row["school"]] and len(row["apPath"]) == 17
        prev = before.get(row["school"])
        assert row["previousRank"] == prev
        assert row["movement"] == ("new" if prev is None else "0" if prev == row["rank"] else f"{prev - row['rank']:+d}")
    assert any(r["movement"].startswith("+") for r in ap["ranks"]) and any(r["movement"].startswith("-") for r in ap["ranks"])
    regular = [w for w in weeks if w.season_type == "regular"]  # week 16, when the committee still ranked
    blocks = season_polls(settings, regular)
    context16.attach_poll_paths(blocks, regular)
    cfp = next(b for b in blocks if b["poll"] == "CFP")
    assert cfp["previousWeek"] == {"week": 15, "seasonType": "regular"} and len(cfp["pathWeeks"]) == 16
    assert all(len(r["apPath"]) == 16 for r in cfp["ranks"])  # the path is always the AP path
    one_week = recs("rankings", PollWeek)
    blocks = season_polls(settings, one_week)
    context16.attach_poll_paths(blocks, one_week)
    assert all(r["movement"] is None and r["previousRank"] is None and r["apPath"] == [r["rank"]] for r in blocks[0]["ranks"])


def test_movement_text():
    assert context16.movement(8, 5, True) == (3, "+3")
    assert context16.movement(5, 7, True) == (-2, "-2")
    assert context16.movement(5, 5, True) == (0, "0")
    assert context16.movement(None, 12, True) == (None, "new")
    assert context16.movement(None, 12, False) == (None, None)


def test_elo_path_from_the_games_answer():
    ours = recs("games_team", Game)
    path = context16.elo_path(ours, US)
    assert path["current"] == side(LAST)["post"] and [p["post"] for p in path["points"]] == [side(g)["post"] for g in PLAYED]
    assert path["points"][0]["pre"] == side(PLAYED[0])["pre"]
    assert context16.elo_path(ours, "Diner Tech") == {"current": side(NEXT, "Diner Tech")["pre"], "points": []}  # before its first game here: the pregame Elo
    assert context16.elo_path(ours, "Nowhere") is None and context16.elo_path(ours, None) is None


# --- GX-08 season strip -------------------------------------------------------------------------------------------


def test_strip_uses_postgame_expectancy_then_an_elo_estimate():
    games = recs("games_team", Game)
    rows = [{"gameId": g.id} for g in games] + [{"gameId": 1}]
    fcs = Game.model_validate({"id": 2, "homeTeam": US, "awayTeam": "Pebble Creek", "completed": False})  # an FCS opponent
    rows.insert(-1, {"gameId": 2})
    context16.attach_strip(rows, games + [fcs], US, recs("ratings_sp", TeamSP), recs("ratings_elo", TeamElo))
    last = next(r for r in rows if r["gameId"] == LAST_GAME)
    sp_rank = next(r["ranking"] for r in fixture_payload("ratings_sp") if r["team"] == LAST_OPP)
    home_wp = LAST["homePostgameWinProbability"]
    assert last["winPct"] == {"value": round(home_wp if HOME_IS_US else 1 - home_wp, 3), "estimate": False, "source": "postgame"} and last["opponentSp"]["rank"] == sp_rank
    upcoming = next(r for r in rows if r["gameId"] == NEXT_GAME)
    ours, theirs = side(NEXT)["pre"], side(NEXT, "Diner Tech")["pre"]
    assert upcoming["winPct"] == {"value": context16.elo_expectation(ours, theirs), "estimate": True, "source": "pregame Elo"}
    assert (upcoming["winPct"]["value"] > 0.5) == (ours > theirs)
    assert next(r for r in rows if r["gameId"] == 2)["opponentSp"] is None  # an FCS team has no SP+
    assert rows[-1] == {"gameId": 1, "opponentSp": None, "winPct": None}
    assert context16.elo_expectation(1500, 1500) == 0.5 and context16.elo_expectation(1900, 1500) == round(1 / (1 + 10 ** -1), 3)
    assert context16.elo_expectation(None, 1500) is None


def test_strip_falls_back_to_current_elo_and_never_emits_nan():
    game = Game.model_validate({"id": 9, "homeTeam": "Swampwater Tech", "awayTeam": "Silo City", "completed": False})
    played = Game.model_validate({"id": 10, "homeTeam": "Swampwater Tech", "awayTeam": "Silo City", "completed": True, "homePostgameWinProbability": float("nan")})
    elo = [TeamElo.model_validate({"team": "Swampwater Tech", "elo": 1700}), TeamElo.model_validate({"team": "Silo City", "elo": 1900})]
    rows = [{"gameId": 9}, {"gameId": 10}]
    context16.attach_strip(rows, [game, played], "Swampwater Tech", [], elo)
    assert rows[0]["winPct"] == {"value": context16.elo_expectation(1700, 1900), "estimate": True, "source": "current Elo"}
    assert rows[1]["winPct"] is None
    strict_json(rows)


# --- GX-15 throw and run tables ---------------------------------------------------------------------------------------


def test_pass_zones_and_run_lanes_from_the_plays():
    passes, rushes = recs("passing_plays_opponent", PassingPlay), recs("rushing_plays_opponent", RushingPlay)
    tables = context16.throw_run_tables(rushes, passes, "Diner Tech")
    raw_passes = [p for p in fixture_payload("passing_plays_opponent") if p["offense"] == "Diner Tech" and not p["isSpike"]]
    assert raw_passes
    for zone in tables["passZones"]:
        mine = [p for p in raw_passes if p.get("passLocation") == f"{zone['depth']} {zone['direction']}"]  # CFBD's passLocation agrees with depth x direction
        assert zone["attempts"] == len(mine) and zone["completions"] == sum(p["outcome"] == "completion" for p in mine)
        assert zone["success"] == {"made": sum(p["success"] is True for p in mine), "of": sum(isinstance(p["success"], bool) for p in mine)}
    assert [z["key"] for z in tables["passZones"]] == ["deep_left", "deep_middle", "deep_right", "short_left", "short_middle", "short_right"]
    assert sum(z["attempts"] for z in tables["passZones"]) + tables["unplacedPasses"] == len(raw_passes)
    raw_runs = [r for r in fixture_payload("rushing_plays_opponent") if r["offense"] == "Diner Tech" and not r["isSack"] and not r["isKneel"]]
    assert raw_runs
    for lane in tables["runLanes"]:
        mine = [r for r in raw_runs if r["rushDirection"] == lane["key"]]
        yards = [r["rushingYards"] for r in mine if isinstance(r["rushingYards"], int)]
        assert lane["carries"] == len(mine) and lane["yardsPerCarry"] == (round(sum(yards) / len(yards), 1) if yards else None)
    assert sum(lane["carries"] for lane in tables["runLanes"]) + tables["unplacedRuns"] == len(raw_runs)
    empty = context16.throw_run_tables(rushes, passes, "Sweet Tea State")  # a team with no plays in the answer
    assert all(z["attempts"] == 0 and z["completionPct"] is None for z in empty["passZones"])
    strict_json(tables)


# --- GX-19 venue facts and UX-14 radar ------------------------------------------------------------------------------------


def test_venue_facts_and_the_radar_link():
    raw = next(v for v in fixture_payload("venues") if v["name"] == "Swampwater Tech Memorial Stadium")
    venue = next(v for v in recs("venues", Venue) if v.name == raw["name"])
    series = recs("teams_matchup", Matchup)
    found = context16.venue_facts(venue, series, US, raw["name"])
    metres = round(float(raw["elevation"]), 1)
    assert found == {"elevationM": metres, "elevationFt": round(metres * 3.28084), "yearBuilt": raw["constructionYear"], "recordAtVenue": at_venue(raw["name"])}
    assert found["recordAtVenue"]["games"] >= 1
    theirs = next(t["location"]["name"] for t in fixture_payload("teams_fbs") if t["school"] == "Diner Tech")
    assert context16.record_at_venue(series, US, theirs)["games"] == at_venue(theirs)["games"] >= 1
    assert context16.radar_url(venue) == f"https://forecast.weather.gov/MapClick.php?lat={raw['latitude']:.4f}&lon={raw['longitude']:.4f}"
    assert context16.radar_url(venue.model_copy(update={"latitude": None})) is None
    assert context16.radar_url(venue.model_copy(update={"country_code": "IE"})) is None
    assert context16.radar_url(venue.model_copy(update={"latitude": float("nan")})) is None
    assert context16.radar_url(None) is None
    assert [context16.elevation_m(v) for v in ("1634.041138", "abc", "NaN", None, 12, "99999")] == [1634.0, None, None, None, 12.0, None]
    assert context16.venue_facts(None, [], "Swampwater Tech", None) == {"elevationM": None, "elevationFt": None, "yearBuilt": None, "recordAtVenue": None}


# --- GX-20 where they're from -----------------------------------------------------------------------------------------------


def test_where_they_are_from():
    recruits = recs("recruiting_players", Recruit)
    state, commits, signed = in_state()
    assert context16.home_state(recs("teams_fbs", Team), US) == state
    table = context16.where_from(recruits, US, state)
    home = next(r for r in table["byState"] if r["state"] == state)
    assert home["commits"] == len(commits) >= 1
    assert home["stars"] == {"5": sum(r["stars"] == 5 for r in commits), "4": sum(r["stars"] == 4 for r in commits), "3": sum(r["stars"] == 3 for r in commits)}
    assert home["averageRating"] == round(sum(r["rating"] for r in commits) / len(commits), 4)
    assert table["inState"] == {"state": state, "commits": len(commits), "of": signed, "share": round(len(commits) / signed, 3)} and table["unknownState"] == 0
    assert sum(r["commits"] for r in table["byState"]) == signed
    assert [r["commits"] for r in table["byState"]] == sorted((r["commits"] for r in table["byState"]), reverse=True)
    assert context16.where_from(recruits, US, None)["inState"] is None
    assert context16.where_from([], US, state) == {"byState": [], "inState": None, "unknownState": 0}


# --- GX-02 game time and GX-09 swings -----------------------------------------------------------------------------------------


def test_the_series_runs_on_game_time_from_its_own_text():
    points = series()
    assert recap16.attach_game_time(points)
    elapsed = [p["elapsedSeconds"] for p in points]
    assert all(e is not None for e in elapsed) and all(b >= a - recap16.BACKWARDS_TOLERANCE for a, b in zip(elapsed, elapsed[1:], strict=False))
    first = points[0]
    assert first["period"] == 1 and first["elapsedSeconds"] == 900 - (first["clock"]["minutes"] * 60 + first["clock"]["seconds"])
    ends = {p["text"]: p["elapsedSeconds"] for p in points if p["text"].startswith("End of")}
    assert ends == {"End of 1st quarter.": 900, "End of 2nd quarter.": 1800, "End of 3rd quarter.": 2700}
    assert points[-1]["text"] == "Game ended" and points[-1]["elapsedSeconds"] == 3600 and points[-1]["period"] == 4
    assert {p["period"] for p in points} == {1, 2, 3, 4}


def test_a_series_without_quarter_ends_gets_no_game_time():
    points = [p for p in series() if not p["text"].startswith("End of")]
    assert recap16.attach_game_time(points) is False
    assert all(p["elapsedSeconds"] is None and p["period"] is None for p in points)


def test_overtime_is_untimed():
    points = [{"homeWp": 0.5, "text": "End of 3rd quarter."}, {"homeWp": 0.5, "text": "(01:00) run"}, {"homeWp": 0.5, "text": "End of 4th quarter."}, {"homeWp": 0.6, "text": "(15:00) OT run"}, {"homeWp": 1.0, "text": "Game ended"}]
    assert recap16.attach_game_time(points)
    assert [p["elapsedSeconds"] for p in points] == [2700, 3540, 3600, None, None] and points[3]["period"] == 5 and points[4]["period"] == 5


def test_biggest_swings_credit_the_play_that_caused_them():
    points = series()
    recap16.attach_game_time(points)
    swings = recap16.biggest_swings(points, home_is_us=HOME_IS_US)
    rows = recap16.play_swings(points, HOME_IS_US)
    moved = [r for r in rows if r["change"] != 0]
    assert swings and [s["rank"] for s in swings] == list(range(1, min(5, len(moved)) + 1))
    assert [abs(s["change"]) for s in swings] == sorted((abs(s["change"]) for s in swings), reverse=True)
    top = swings[0]
    assert abs(top["change"]) == max(abs(r["change"]) for r in rows) and top["text"] and top["period"] in (1, 2, 3, 4)
    assert top["change"] == round(top["usWpAfter"] - top["usWpBefore"], 4)
    assert (top["usScore"], top["themScore"]) == ((top["homeScore"], top["awayScore"]) if HOME_IS_US else (top["awayScore"], top["homeScore"]))
    other_view = recap16.biggest_swings(points, home_is_us=not HOME_IS_US)
    assert other_view[0]["change"] == -top["change"] and other_view[0]["homeWpBefore"] == top["homeWpBefore"]
    thrown = next((p for d in facts.live_doc()["drives"] for p in d["plays"] if p["playType"] == "Pass Interception Return"), None)
    if thrown is not None:  # a pick swings the game toward the defense (CFBD shows a turnover on the next point)
        pick = next(r for r in rows if r["text"] and "intercepted" in r["text"])
        assert pick["change"] >= 0 if thrown["team"] != US else pick["change"] <= 0
    assert not any(r["text"].startswith(("End of", "Game ended")) for r in rows)


def test_the_win_probability_block_is_enriched_in_place():
    block = {"available": True, "series": series()}
    recap16.enrich_win_probability(block, False)
    assert block["gameTime"] is True and 1 <= len(block["swings"]) <= 5 and block["series"][5]["elapsedSeconds"] is not None
    empty = {"available": False, "series": []}
    recap16.enrich_win_probability(empty, True)
    assert empty == {"available": False, "series": [], "gameTime": False, "swings": []}
    recap16.enrich_win_probability(None, True)
    strict_json(block)


# --- UX-07 recap -------------------------------------------------------------------------------------------------------------


def test_the_recap_of_our_last_final():
    schedule = recs("games_team", Game)
    advanced = {"players": [{"player": "Lucas Griffin", "team": "Swampwater Tech", "position": "RB", "totalPpa": 10.7}, {"player": "Somebody Else", "team": "Diner Tech", "totalPpa": 40.0}]}
    recap = recap16.recap(archive_body(), series(), team=US, schedule=schedule, advanced=advanced)
    last = side(LAST)
    assert recap["final"] == {"usScore": last["points"], "themScore": last["against"], "homeScore": LAST["homePoints"], "awayScore": LAST["awayPoints"], "result": result(LAST)}
    assert recap["record"] == record_through_last() and recap["opponent"] == LAST_OPP and recap["homeIsUs"] is HOME_IS_US
    top = top_swing()
    assert recap["turningPoint"]["play"] == top["play"] and recap["turningPoint"]["period"] == top["period"] and recap["turningPoint"]["usWpAfter"] == top["usWpAfter"]
    assert recap["playerOfGame"] == {"name": "Lucas Griffin", "team": "Swampwater Tech", "position": "RB", "isUs": True, "value": 10.7, "basis": "total play value (PPA)"}  # another game's player never wins it
    stats = recap["keyStats"]
    assert len(stats) == 3 and [s["weight"] for s in stats] == sorted((s["weight"] for s in stats), reverse=True)
    for stat in stats:  # the edge goes to the side the stat favors
        assert stat["edge"] == ("us" if (stat["us"] > stat["them"]) == stat["higherIsBetter"] else "them"), stat
    assert recap["next"] == next_row()
    strict_json(recap)


def test_recap_player_falls_back_to_play_value_per_play():
    ppa = {"players": {"us": [{"name": "A", "position": "QB", "all": 0.4}], "them": [{"name": "B", "position": "WR", "all": 0.9}, {"name": "C", "all": float("nan")}]}}
    assert recap16.player_of_game(None, ppa, "Swampwater Tech") == {"name": "B", "team": None, "position": "WR", "isUs": False, "value": 0.9, "basis": "play value per play (PPA)"}
    assert recap16.player_of_game({"players": "junk"}, {"players": None}, "Swampwater Tech") is None


def test_no_recap_for_a_partial_a_live_or_someone_elses_game():
    assert recap16.recap(archive_body(partial=True), [], team="Swampwater Tech", schedule=[]) is None
    live = archive_body()
    live["state"] = {**live["state"], "status": "in"}
    assert recap16.recap(live, [], team="Swampwater Tech", schedule=[]) is None
    assert recap16.recap(archive_body(home=LAST_OPP, away="Silo City"), [], team="Swampwater Tech", schedule=[]) is None
    bare = recap16.recap(archive_body(), [], team="Swampwater Tech", schedule=[])
    assert bare["record"] is None and bare["next"] is None and bare["turningPoint"] is None and bare["final"]["result"] == result(LAST)


def test_the_36_hour_window():
    body = archive_body()
    saved = SAVED
    assert recap16.recent(body, saved + timedelta(hours=35))
    assert not recap16.recent(body, saved + timedelta(hours=37))
    assert not recap16.recent(body, saved - timedelta(hours=1))
    assert recap16.recent({**body, "savedAt": None}, KICKOFF + timedelta(hours=13))  # the kickoff stands in
    assert not recap16.recent({"savedAt": "yesterday"}, saved) and not recap16.recent(None, saved)


# --- UX-12 helpers --------------------------------------------------------------------------------------------------------------


def test_matchup_helpers():
    games = recs("games_team", Game)
    now = NEXT_KICKOFF - timedelta(days=3)
    game = slate_game(games, "Diner Tech", US, now)
    assert game["gameId"] == NEXT_GAME and game["status"] == "scheduled" and game["homeTeam"] == NEXT["homeTeam"]
    assert slate_game(games, US, "Diner Tech", now)["gameId"] == NEXT_GAME  # either order finds it
    assert slate_game(games, "Diner Tech", US, now + timedelta(days=12)) is None  # not this week's slate
    assert slate_game(games, "Diner Tech", US, NEXT_KICKOFF + timedelta(minutes=30))["status"] == "underway"
    assert slate_game(games, LAST_OPP, US, KICKOFF + timedelta(hours=17))["status"] == "final"
    ranks = talent_ranks([TeamTalent(team="A", talent=900), TeamTalent(team="B", talent=900), TeamTalent(team="C", talent=800), TeamTalent(team="D", talent=float("inf"))])
    assert ranks == {"A": {"talent": 900.0, "rank": 1, "of": 3}, "B": {"talent": 900.0, "rank": 1, "of": 3}, "C": {"talent": 800.0, "rank": 3, "of": 3}}


# --- junk for every parser --------------------------------------------------------------------------------------------------------


PARSERS: list[tuple[str, Any, Any]] = [
    ("form", Game, lambda r: context16.form_table(r)),
    ("elo path", Game, lambda r: context16.elo_path(r, "Swampwater Tech")),
    ("strip", Game, lambda r: _strip(r)),
    ("slate game", Game, lambda r: slate_game(r, "Diner Tech", "Swampwater Tech", datetime(2026, 9, 23, tzinfo=timezone.utc))),
    ("recap schedule", Game, lambda r: recap16.recap(archive_body(), series(), team="Swampwater Tech", schedule=r)),
    ("polls", PollWeek, lambda r: _polls(r)),
    ("sp", TeamSP, lambda r: context16.sp_rank_lookup(r)),
    ("talent", TeamTalent, lambda r: talent_ranks(r)),
    ("passes", PassingPlay, lambda r: context16.throw_run_tables([], r, "Diner Tech")),
    ("rushes", RushingPlay, lambda r: context16.throw_run_tables(r, [], "Diner Tech")),
    ("venues", Venue, lambda r: [context16.venue_facts(v, [], "Swampwater Tech", v.name) for v in r] + [context16.radar_url(v) for v in r]),
    ("series", Matchup, lambda r: context16.record_at_venue(r, "Swampwater Tech", "Swampwater Tech Memorial Stadium")),
    ("recruits", Recruit, lambda r: context16.where_from(r, "Swampwater Tech", "AL")),
    ("teams", Team, lambda r: context16.home_state(r, "Swampwater Tech")),
    ("wp", PlayWinProbability, lambda r: _wp(r)),
]


def _strip(games: list[Game]) -> list[dict[str, Any]]:
    rows = [{"gameId": g.id} for g in games] + [None, "row"]
    context16.attach_strip(rows, games, "Swampwater Tech", [], [])
    return rows


def _polls(weeks: list[PollWeek]) -> list[dict[str, Any]]:
    blocks = [{"poll": "AP", "week": 3, "ranks": [{"rank": 1, "school": "Magnolia Flats"}, None, {"school": 5}]}, "junk", None]
    context16.attach_poll_paths(blocks, weeks)
    return blocks


def _wp(records: list[PlayWinProbability]) -> dict[str, Any]:
    block = {"series": wp_series(records)}
    recap16.enrich_win_probability(block, False)
    return block


@pytest.mark.parametrize("label, model, run", PARSERS, ids=[p[0] for p in PARSERS])
def test_junk_payloads_never_crash_and_bad_records_are_counted(label, model, run):
    for payload in JUNK_PAYLOADS:
        parsed = parse_records(model, payload, context=f"junk {label}")
        if isinstance(payload, list):
            assert len(parsed.records) + parsed.skipped == len(payload)  # every bad record is counted
        elif isinstance(payload, str):
            assert parsed.records == [] and parsed.skipped == 1
        strict_json(run(parsed.records))


def test_junk_inside_dict_payloads():
    for junk in (None, "x", 3, [], {}, [None, "x", {"homeWp": "0.4"}, {"homeWp": float("nan")}, {"homeWp": 2}], [{"homeWp": 0.5, "text": 7, "homeScore": "3"}, {"homeWp": 0.9}]):
        assert isinstance(recap16.attach_game_time(junk), bool)
        strict_json(recap16.biggest_swings(junk, True))
        strict_json(recap16.play_swings(junk, False))
    for box in (None, "x", {}, {"Swampwater Tech": "x"}, {"Swampwater Tech": {}, LAST_OPP: {"successRate": float("nan"), "thirdDown": "7-9", "explosive": 3}}):
        assert strict_json(recap16.key_stats(box, "Swampwater Tech", LAST_OPP)) == "[]"
    for raw in (None, "x", [], {"gameId": "1"}, {"gameId": 1, "state": "x"}, {"gameId": 1, "state": {"status": "final"}, "home": None}):
        assert recap16.recap(raw, None, team="Swampwater Tech", schedule=[]) is None
    state_junk = archive_body()
    state_junk["state"] = {"status": "final", "homeScore": "39", "awayScore": None, "box": "junk"}
    recap = recap16.recap(state_junk, "junk", team="Swampwater Tech", schedule=recs("games_team", Game))
    assert recap["final"]["result"] is None and recap["record"] is None and recap["keyStats"] == []
    for data in ({}, {"standings": "x", "polls": None, "schedule": [None]}, {"standings": [None, {"team": 5}]}):
        context16.season_extras(data, {"games": "x", "schedule": None}, "Swampwater Tech")
        strict_json(data)
    data = {"us": "x", "them": None, "game": {"venueDetail": "x"}, "weather": None, "tendencies": {"x": 1}}
    context16.program_extras(data, {}, team="Swampwater Tech", opponent="Diner Tech", venue=None)
    assert data["tendencies"]["passZones"][0]["attempts"] == 0
    context16.team_extras({"team": None}, {}, "Swampwater Tech")
    context16.newspaper_extras({"slate": [None, {"home": "x", "away": {"school": None}}]}, {})


def test_a_failing_extra_is_logged_and_shown_without_killing_the_page(caplog, monkeypatch):
    def boom(*_: Any, **__: Any) -> Any:
        raise RuntimeError("boom")

    monkeypatch.setattr(context16, "form_table", boom)
    data: dict[str, Any] = {"standings": [], "parts": {}}
    context16.season_extras(data, {}, "Swampwater Tech")
    assert data["parts"]["extras"]["status"] == "error" and "RuntimeError" in data["parts"]["extras"]["error"]
    assert "Season extras failed" in caplog.text


# --- the routes ---------------------------------------------------------------------------------------------------------------------


SUNDAY = SAVED + timedelta(hours=9)  # the morning after our last game
SATURDAY = NEXT_KICKOFF.replace(hour=12, minute=0)  # the next game day: the slate


def route_all(fake: FakeCfbd) -> None:
    route_program(fake)
    fake.fixture("/ratings/elo", "ratings_elo")
    fake.fixture("/ratings/fpi", "ratings_fpi")
    fake.fixture("/metrics/wp", "metrics_wp")
    fake.fixture("/calendar", "calendar")


def write_archive(data_dir: Path) -> None:
    folder = data_dir / "archive"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{LAST_GAME}.json").write_text(json.dumps(archive_body()), encoding="utf-8")


PAGES = ["/api/season/overview", "/api/program/next", f"/api/program/{LAST_GAME}", "/api/team/Diner%20Tech", "/api/recruiting", f"/api/games/{LAST_GAME}/analytics", f"/api/archive/{LAST_GAME}", "/api/newspaper"]


def load_pages(tmp: Path, *, with_extras: bool, monkeypatch: pytest.MonkeyPatch) -> tuple[list[tuple[str, str]], dict[str, Any]]:
    """Every affected page on a fresh app and cache: the calls CFBD saw, and the answers."""
    with monkeypatch.context() as patch:
        # Counted calls must come from the pages only: the live engine's loop never starts (on a slow machine it
        # could check the schedule before being stopped), and the clock is fixed before the app starts
        # (public release Phase 9: the macOS CI run).
        patch.setattr(LiveEngine, "start_background", lambda self: None)
        if not with_extras:
            async def nothing(*_: Any, **__: Any) -> None:
                return None

            for name in ("season_extras", "program_extras", "team_extras", "newspaper_extras"):
                patch.setattr(context16, name, lambda *_, **__: None)
            patch.setattr(context16, "recruiting_extras", nothing)
            patch.setattr(recap16, "enrich_win_probability", lambda *_, **__: None)
            patch.setattr(ArchiveService, "_recap", nothing)
            patch.setattr(ArchiveService, "attach_recent_recap", nothing)
        settings = load_settings(env_file=None, cfbd_api_key=TEST_KEY, log_dir=str(tmp / "logs"), data_dir=str(tmp / "data"))
        fake, sites = FakeCfbd(), FakeSites()
        route_all(fake)
        transport = httpx.MockTransport(sites.handler)
        app = create_app(settings, cfbd_transport=fake.transport, feeds_transport=transport, weather_transport=transport)
        app.state.cfbd._clock = lambda: SUNDAY
        write_archive(settings.data_dir)
        answers: dict[str, Any] = {}
        with TestClient(app, base_url="https://testserver") as client:
            quiet_engine(app, client)
            app.state.cfbd._clock = lambda: SUNDAY
            for page in PAGES:
                response = client.get(page)
                assert response.status_code == 200, (page, response.text[:300])
                assert "NaN" not in response.text and "Infinity" not in response.text
                answers[page] = response.json()
            app.state.cfbd._clock = lambda: SATURDAY
            answers["saturday"] = client.get("/api/newspaper").json()
        calls = sorted((r.url.path, str(r.url.params)) for r in fake.requests)
        return calls, answers


def test_the_new_fields_cost_no_cfbd_call(tmp_path: Path, settings, monkeypatch: pytest.MonkeyPatch):
    configure_logging(settings)
    try:
        without_calls, without = load_pages(tmp_path / "without", with_extras=False, monkeypatch=monkeypatch)
        with_calls, answers = load_pages(tmp_path / "with", with_extras=True, monkeypatch=monkeypatch)
    finally:
        shutdown_logging()
    assert with_calls == without_calls and len(with_calls) > 40  # the very same calls, one for one

    # the fields are there with the extras and absent without them (so the patch above really took them out)
    season = answers["/api/season/overview"]["data"]
    assert "form" in season["standings"][0] and "movement" in season["polls"][0]["ranks"][0] and "winPct" in season["schedule"][0]
    assert "form" not in without["/api/season/overview"]["data"]["standings"][0]
    ours = next(r for r in season["standings"] if r["team"] == US)
    assert [f["result"] for f in ours["form"]] == [result(g) for g in PLAYED]
    program = answers["/api/program/next"]["data"]
    assert program["us"]["eloPath"]["current"] == side(LAST)["post"] and program["them"]["eloPath"]["current"] == side(NEXT, "Diner Tech")["pre"]
    stadium = next(v for v in fixture_payload("venues") if v["name"] == "Swampwater Tech Memorial Stadium")
    assert program["game"]["venueDetail"]["yearBuilt"] == stadium["constructionYear"] and program["game"]["venueDetail"]["recordAtVenue"]["games"] == at_venue(stadium["name"])["games"]
    assert program["weather"]["radarUrl"].startswith(f"https://forecast.weather.gov/MapClick.php?lat={stadium['latitude']:.4f}")
    assert len(program["tendencies"]["passZones"]) == 6 and len(program["tendencies"]["runLanes"]) == 3
    assert "radarUrl" not in without["/api/program/next"]["data"]["weather"]
    their_games = sorted((g for g in fixture_payload("games_opponent") if g["completed"]), key=lambda g: g["week"])
    assert [f["opponent"] for f in answers["/api/team/Diner%20Tech"]["data"]["team"]["form"]] == [side(g, "Diner Tech")["opponent"] for g in their_games]
    classes = answers["/api/recruiting"]["data"]["classes"]
    state, commits, signed = in_state()
    assert classes[0]["inState"] == {"state": state, "commits": len(commits), "of": signed, "share": round(len(commits) / signed, 3)}  # /teams/fbs was cached by the season page
    top = top_swing()
    wp = answers[f"/api/games/{LAST_GAME}/analytics"]["data"]["winProbability"]
    assert wp["gameTime"] is True and wp["swings"][0]["play"] == top["play"] and wp["series"][-1]["elapsedSeconds"] == 3600
    archive = answers[f"/api/archive/{LAST_GAME}"]["data"]
    assert archive["recap"]["turningPoint"]["play"] == top["play"] and archive["recap"]["record"] == record_through_last() and archive["winProbability"]["swings"]
    assert without[f"/api/archive/{LAST_GAME}"]["data"].get("recap") is None
    news = answers["/api/newspaper"]["data"]
    assert news["recap"]["gameId"] == LAST_GAME and news["recap"]["turningPoint"]["period"] == top["period"] and news["recap"]["next"]["opponent"] == "Diner Tech"
    assert "recap" not in without["/api/newspaper"]["data"]
    saturday = answers["saturday"]["data"]
    assert "recap" not in saturday  # days on: absent
    our_card = saturday["slate"][0]
    assert our_card["isUs"] and [f["result"] for f in our_card["home"]["form"]] == [result(g) for g in PLAYED] and our_card["away"]["form"] == []


# --- UX-12 matchup route ----------------------------------------------------------------------------------------------------------------


def test_the_matchup_sheet_costs_nothing_once_the_season_page_has_loaded(app, client: TestClient, fake_cfbd: FakeCfbd):
    quiet_engine(app, client)
    route_all(fake_cfbd)
    app.state.cfbd._clock = lambda: NEXT_KICKOFF - timedelta(days=3)
    assert client.get("/api/season/overview").status_code == 200
    client.get("/api/program/next")  # the talent table comes with the program
    before = fake_cfbd.count()
    body = client.get("/api/matchup", params={"away": "diner tech", "home": US}).json()
    assert fake_cfbd.count() == before  # every part is a cache hit
    data = body["data"]
    assert body["errors"] == []
    sp = {r["team"]: r for r in fixture_payload("ratings_sp")}
    assert data["away"]["school"] == "Diner Tech" and data["away"]["apRank"] == facts.ap_rank("Diner Tech")
    assert data["away"]["record"]["wins"] == facts.record("Diner Tech")["total"]["wins"] and data["away"]["sp"]["rank"] == sp["Diner Tech"]["ranking"]
    talent = {r["team"]: r["talent"] for r in fixture_payload("talent")}
    assert data["home"]["isUs"] and data["home"]["talent"]["rank"] == 1 + sum(v > talent[US] for v in talent.values())
    assert data["home"]["sp"]["defense"]["rank"] == sp[US]["defense"]["ranking"]
    assert [f["result"] for f in data["home"]["form"]] == [result(g) for g in PLAYED] and data["home"]["eloPath"]["current"] == side(LAST)["post"]
    rows = {r["key"]: r for r in data["rows"]}
    stats: dict[str, dict[str, float]] = {}
    for r in fixture_payload("stats_season_fbs"):
        stats.setdefault(r["team"], {})[r["statName"]] = r["statValue"]
    ypg = {t: round(v["totalYards"] / v["games"], 3) for t, v in stats.items() if v.get("games") and "totalYards" in v}
    assert len(data["rows"]) == 26 + 6 and rows["ypg"]["home"] == {"value": ypg[US], "rank": 1 + sum(v > ypg[US] for v in ypg.values())}
    assert rows["ypg"]["away"]["rank"] == 1 + sum(v > ypg["Diner Tech"] for v in ypg.values()) and rows["ypg"]["of"] == len(ypg)
    assert rows["offense_success_rate"]["group"] == "Offense" and rows["offense_success_rate"]["home"]["rank"]
    assert data["game"]["gameId"] == NEXT_GAME and data["game"]["status"] == "scheduled" and data["game"]["homePoints"] is None
    assert data["parts"]["teams"]["status"] == "ok" and "NaN" not in json.dumps(body)


def test_matchup_refusals_cost_no_call(app, client: TestClient, fake_cfbd: FakeCfbd):
    quiet_engine(app, client)
    route_all(fake_cfbd)
    before = fake_cfbd.count()
    for params in ({}, {"away": "Swampwater Tech"}, {"away": " ", "home": "Swampwater Tech"}, {"away": "x" * 61, "home": "Swampwater Tech"}):
        response = client.get("/api/matchup", params=params)
        assert response.status_code == 404 and response.json()["data"] is None
    assert fake_cfbd.count() == before  # nothing asked for a request that names no two teams
    assert client.get("/api/matchup", params={"away": "Swampwater Tech", "home": "Diner Tech"}).status_code == 200  # warms the teams list
    before = fake_cfbd.count()
    response = client.get("/api/matchup", params={"away": "Nowhere State", "home": "Swampwater Tech"})
    assert response.status_code == 404 and "Nowhere State" in response.json()["errors"][0]["message"]
    assert client.get("/api/matchup", params={"away": "swampwater", "home": "Swampwater Tech"}).status_code == 404
    assert fake_cfbd.count() == before


def test_matchup_without_a_teams_list_is_a_503(app, client: TestClient, fake_cfbd: FakeCfbd):
    quiet_engine(app, client)
    fake_cfbd.route("/teams/fbs", status=500, text="down")
    response = client.get("/api/matchup", params={"away": "Swampwater Tech", "home": "Diner Tech"})
    assert response.status_code == 503 and fake_cfbd.count("/stats/season") == 0


def test_matchup_survives_junk_parts(app, client: TestClient, fake_cfbd: FakeCfbd):
    quiet_engine(app, client)
    fake_cfbd.fixture("/teams/fbs", "teams_fbs")
    junk = [None, "x", {"team": 5}, {"team": "Swampwater Tech", "talent": "lots", "rating": "high", "statValue": "abc"}]
    for path in ("/stats/season", "/stats/season/advanced", "/ratings/sp", "/talent", "/rankings", "/records", "/games"):
        fake_cfbd.route(path, json=junk)
    body = client.get("/api/matchup", params={"away": "Swampwater Tech", "home": "Diner Tech"}).json()
    data = body["data"]
    assert data["home"]["talent"] is None and data["home"]["sp"] is None and data["game"] is None and data["home"]["form"] == []
    assert any(e["code"] == "records_skipped" for e in body["errors"])
    assert all(r["away"]["value"] is None or not (isinstance(r["away"]["value"], float) and math.isnan(r["away"]["value"])) for r in data["rows"])
