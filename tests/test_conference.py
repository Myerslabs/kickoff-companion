"""The conference page (owner 2026-11-02: "Lets do the conference page first"; "Any conference, ours first"; the board
"Build as drawn"): the chip list's order and the name lookup, each
band's rows over made-up and damaged records, the route against the recorded test app (no network), the page in the fake
browser, and its rows in the catalog, the menu and the data status."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.cfbd.models import Game, TeamRecords
from app.services import conference as svc
from app.services.data_status import PAGE_BANDS
from tests.conftest import FakeCfbd
from tests.fakedom import needs_node, run_scenario
from tests.test_national import route_all

TEAMS = {
    "Florida": {"school": "Florida", "abbreviation": "FLA", "conference": "SEC", "logo": "/media/logo/57"},
    "Georgia": {"school": "Georgia", "abbreviation": "UGA", "conference": "SEC", "logo": "/media/logo/61"},
    "Vanderbilt": {"school": "Vanderbilt", "abbreviation": "VAN", "conference": "SEC"},
    "Ohio State": {"school": "Ohio State", "abbreviation": "OSU", "conference": "Big Ten"},
    "Toledo": {"school": "Toledo", "abbreviation": "TOL", "conference": "Mid-American"},
    "Notre Dame": {"school": "Notre Dame", "abbreviation": "ND", "conference": "FBS Independents"},
    "Boise State": {"school": "Boise State", "abbreviation": "BSU", "conference": "Mountain West"},
    "Ghost": {"school": "Ghost", "conference": None},
    "Junk": "not a dict",
}


def test_the_chip_row_is_ours_then_the_power_conferences_then_the_rest_with_the_independents_last():
    rows = svc.conference_list(TEAMS, "Mid-American")
    assert [r["name"] for r in rows] == ["Mid-American", "SEC", "Big Ten", "Mountain West", "FBS Independents"]
    assert rows[0]["isOurs"] is True and rows[0]["short"] == "MAC" and rows[0]["teams"] == 1
    assert [r["name"] for r in svc.conference_list(TEAMS, "SEC")][:2] == ["SEC", "Big Ten"]
    assert svc.conference_list({}, "SEC") == []


def test_a_conference_by_its_name_or_its_short_name_any_case():
    names = ["SEC", "Big Ten", "Big 12", "Mid-American"]
    assert svc.resolve_conference(names, "sec") == "SEC"
    assert svc.resolve_conference(names, "b1g") == "Big Ten"
    assert svc.resolve_conference(names, "MAC") == "Mid-American"
    assert svc.resolve_conference(names, "  Big 12 ") == "Big 12"
    assert svc.resolve_conference(names, "Pac-12") is None
    assert svc.resolve_conference(names, None) is None and svc.resolve_conference(names, "") is None and svc.resolve_conference(names, 7) is None


def _listing(category: str, offense: list[dict], allowed: list[dict], players: list[dict] | None = None, lead: str = "yds") -> dict[str, Any]:
    return {
        "category": category,
        "teams": {"offense": {"rows": offense, "lead": "ypg"}, "allowed": {"rows": allowed, "lead": "ypg"}},
        "players": {"lead": lead, "columns": [{"key": lead, "label": "Yds" if lead == "yds" else "Tkl"}], "rows": players or []},
    }


def test_the_numbers_table_averages_each_conference_and_ranks_them_each_way():
    listings = {
        "passing": _listing("passing", [{"team": "A", "conference": "SEC", "ypg": 300}, {"team": "B", "conference": "SEC", "ypg": 200}, {"team": "C", "conference": "Big Ten", "ypg": 240}, {"team": "D", "conference": None, "ypg": 999}, {"team": "E", "conference": "ACC", "ypg": "nope"}, None, 4],
                             [{"team": "A", "conference": "SEC", "ypg": 180}, {"team": "C", "conference": "Big Ten", "ypg": 220}]),
        "rushing": _listing("rushing", [{"team": "A", "conference": "SEC", "ypg": 150}], [{"team": "C", "conference": "Big Ten", "ypg": 100}]),
        "defense": {"teams": {"offense": {"rows": [{"team": "A", "conference": "SEC", "spg": 3.0, "take": 12, "games": 6}, {"team": "C", "conference": "Big Ten", "spg": 2.0, "take": 10, "games": 0}]}, "allowed": {"rows": [{"team": "A", "conference": "SEC", "spg": 1.5}]}}},
        "receiving": None,
    }
    table = svc.numbers_table(listings, "SEC", ["Big Ten", "SEC"])
    assert [c["key"] for c in table["columns"]][:2] == ["passYpg", "rushYpg"] and table["columns"][2]["higherIsBetter"] is False
    by = {r["conference"]: r for r in table["rows"]}
    assert [r["conference"] for r in table["rows"]] == ["Big Ten", "SEC"], "the SP+ table's order"
    assert by["SEC"]["passYpg"] == 250.0 and by["SEC"]["passYpgRank"] == 1 and by["Big Ten"]["passYpgRank"] == 2
    assert by["SEC"]["passAllowed"] == 180.0 and by["SEC"]["passAllowedRank"] == 1 and by["Big Ten"]["passAllowedRank"] == 2, "lower allowed ranks first"
    assert by["SEC"]["takeawaysPerGame"] == 2.0 and by["Big Ten"]["takeawaysPerGame"] is None, "no games: no per-game figure"
    assert by["SEC"]["isUs"] is True and by["SEC"]["teams"] == 2 and by["SEC"]["short"] == "SEC"
    assert "ACC" not in by, "a conference with no number read is left out"
    assert svc.numbers_table({}, "SEC")["rows"] == []


def _game(gid: int, home: str, away: str, hp: int | None, ap: int | None, week: int, date: str, conference: bool = True, done: bool = True) -> Game:
    return Game.model_validate({"id": gid, "week": week, "seasonType": "regular", "startDate": date, "homeTeam": home, "awayTeam": away, "homeConference": "SEC", "awayConference": "SEC" if conference else "Big Ten", "conferenceGame": conference, "completed": done, "homePoints": hp, "awayPoints": ap})


GAMES = [
    _game(1, "Florida", "Georgia", 27, 24, 1, "2026-09-05T20:00:00Z"),
    _game(2, "Vanderbilt", "Florida", 10, 31, 2, "2026-09-12T20:00:00Z"),
    _game(3, "Georgia", "Vanderbilt", 40, 7, 3, "2026-09-19T20:00:00Z"),
    _game(4, "Florida", "Ohio State", 14, 35, 4, "2026-09-26T20:00:00Z", conference=False),
    _game(5, "Georgia", "Florida", None, None, 5, "2026-10-03T20:00:00Z", done=False),
    _game(6, "Vanderbilt", "Georgia", 3, 0, 0, "2026-08-29T20:00:00Z"),
]


def _records() -> list[TeamRecords]:
    rec = lambda team, cw, cl, w, losses: TeamRecords.model_validate({"team": team, "conference": "SEC", "total": {"games": w + losses, "wins": w, "losses": losses, "ties": 0}, "conferenceGames": {"games": cw + cl, "wins": cw, "losses": cl, "ties": 0}})  # noqa: E731
    return [rec("Georgia", 1, 2, 1, 2), rec("Florida", 2, 0, 2, 1), rec("Vanderbilt", 1, 2, 1, 2), TeamRecords.model_validate({"team": "Ohio State", "conference": "Big Ten"})]


def test_the_standings_carry_the_race_and_the_last_five_ours_with_the_lines():
    block = svc.standings_block(_records(), TEAMS, {"Florida": 9}, "SEC", "Florida", GAMES, 5)
    rows = block["rows"]
    assert [r["team"] for r in rows] == ["Florida", "Georgia", "Vanderbilt"], "conference record first; the Big Ten row left out"
    us = rows[0]
    assert us["isUs"] is True and us["apRank"] == 9 and us["logo"] == "/media/logo/57"
    assert [g["result"] for g in us["form"]] == ["W", "W", "L"] and us["form"][-1]["opponent"] == "Ohio State" and us["form"][-1]["homeAway"] == "home"
    assert us["form"][0]["points"] == 27 and us["form"][0]["opponentPoints"] == 24
    assert isinstance(us["bestPlace"], int) and isinstance(us["worstPlace"], int) and us["raceStatus"] in ("alive", "clinched", "tiebreaker", "out")
    assert block["ours"] is True and block["race"]["us"]["team"] == "Florida" and isinstance(block["race"]["lines"], list)
    assert isinstance(block["helps"], dict)
    georgia = rows[1]
    assert [g["result"] for g in georgia["form"]] == ["L", "L", "W"], "oldest first, the week-0 game first"


def test_another_conferences_standings_have_no_lines_and_the_form_caps_at_five():
    block = svc.standings_block(_records(), TEAMS, {}, "SEC", None, GAMES, 5)
    assert block["ours"] is False and block["race"] is None and block["helps"] == {}
    assert block["rows"][0]["raceStatus"] is not None, "the race still says where each team stands"
    many = [_game(100 + i, "Florida", "Georgia", 20, 10, i, f"2026-09-{i + 1:02d}T20:00:00Z") for i in range(8)]
    assert len(svc.form_of(many, "Florida")) == 5 and svc.form_of(many, "Nobody") == []
    assert svc.form_of([_game(9, "Florida", "Georgia", None, None, 1, "2026-09-05T20:00:00Z")], "Florida") == [], "no score: no result"
    assert svc.standings_block([], TEAMS, {}, "SEC", "Florida", [], None) == {"rows": [], "ours": False, "race": None, "helps": {}}


def test_the_week_keeps_the_games_with_a_team_of_the_conference_in_kickoff_order_with_the_helps():
    picks = {
        "week": 10, "label": "Week 10", "key": "week-10", "picksBy": "claude", "ready": True, "note": None,
        "slots": [
            {"id": "late", "games": [{"gameId": 3, "kickoff": "2026-11-08T00:30:00Z", "home": {"school": "Georgia"}, "away": {"school": "Ole Miss"}, "right": True}]},
            {"id": "early", "games": [{"gameId": 1, "kickoff": "2026-11-07T17:00:00Z", "home": {"school": "Florida"}, "away": {"school": "Toledo"}, "right": False}, {"gameId": 2, "kickoff": "2026-11-07T18:00:00Z", "home": {"school": "Ohio State"}, "away": {"school": "Toledo"}}, "junk", None]},
            "junk",
        ],
        "unscheduled": [{"gameId": 4, "kickoff": None, "home": {"school": "Vanderbilt"}, "away": {"school": "Ghost"}}, 7],
    }
    week = svc.week_games(picks, {"Florida", "Georgia", "Vanderbilt", "Ole Miss"}, {3: {"pullFor": "Ole Miss", "why": "a loss by Georgia", "ours": False}, "x": 1})
    assert [g["gameId"] for g in week["games"]] == [1, 3, 4], "kickoff order, the unscheduled last, the Big Ten game out"
    assert week["games"][0]["conferenceGame"] is False and week["games"][1]["conferenceGame"] is True
    assert week["games"][1]["helps"]["pullFor"] == "Ole Miss" and week["games"][0]["helps"] is None
    assert week["record"] == {"right": 1, "wrong": 1} and week["label"] == "Week 10" and week["picksBy"] == "claude"
    assert svc.week_games({}, set(), {})["games"] == []


def test_the_rated_rows_by_sp_with_talent_edge_and_the_logos_and_damage_skipped():
    ratings = [
        {"team": "Georgia", "abbreviation": "UGA", "sp": {"rating": 27.1, "rank": 2}, "elo": {"rating": 2037, "rank": 3}, "fpi": {"rating": 25.4, "rank": 4}, "talent": {"talent": 1003.7, "rank": 1, "of": 138}},
        {"team": "Florida", "sp": {"rating": 10.6, "rank": 31}},
        {"team": "Vanderbilt", "sp": None},
        {"team": "Ohio State", "sp": {"rating": 30, "rank": 1}},
        {"team": None}, "junk", None,
    ]
    talent = {"teams": {"Georgia": {"groups": {"TOT": {"rank": 1, "of": 138, "pct": 100}}}, "Florida": {"groups": "junk"}, "Vanderbilt": None}}
    rows = svc.rated_rows(ratings, {"Georgia", "Florida", "Vanderbilt"}, talent, "Florida", TEAMS)
    assert [r["team"] for r in rows] == ["Georgia", "Florida", "Vanderbilt"] and [r["place"] for r in rows] == [1, 2, 3], "by SP+, no rating last"
    assert rows[0]["talentEdge"] == {"rank": 1, "of": 138, "pct": 100} and rows[0]["sp"] == {"rating": 27.1, "rank": 2}
    assert rows[1]["isUs"] is True and rows[1]["talentEdge"] is None and rows[1]["abbreviation"] == "FLA" and rows[1]["logo"] == "/media/logo/57", "the FBS list's abbreviation and logo fill in"
    assert rows[2]["sp"] is None and rows[2]["talentEdge"] is None
    assert svc.rated_rows(ratings, {"Georgia"}, None, None)[0]["talentEdge"] is None


def test_the_leaders_are_the_conferences_top_five_of_the_list_in_its_order():
    players = [{"playerId": str(i), "player": f"P{i}", "position": "QB", "team": "Georgia" if i % 2 else "Ohio State", "abbreviation": "UGA", "yds": 3000 - i, "ydsRank": i + 1, "isUs": False} for i in range(14)] + ["junk", {"player": None, "team": "Georgia"}]
    block = svc.leaders_of(_listing("passing", [], [], players), {"Georgia"})
    assert block["lead"] == "yds" and block["label"] == "Yds" and block["category"] == "passing" and block["available"] is True
    assert [r["player"] for r in block["rows"]] == ["P1", "P3", "P5", "P7", "P9"]
    assert block["rows"][0] == {"playerId": "1", "player": "P1", "position": "QB", "team": "Georgia", "abbreviation": "UGA", "headshotUrl": None, "isUs": False, "value": 2999, "rank": 2}
    assert svc.leaders_of(None, {"Georgia"}) == {"lead": None, "label": None, "rows": [], "available": False}
    assert svc.leaders_of({"players": {"lead": "tot", "rows": "junk"}}, {"Georgia"})["rows"] == []


def test_the_land_counts_each_schools_cells_its_rank_and_the_weeks_change():
    table = {
        "computedWeek": 9,
        "teams": [{"team": "Florida"}, {"team": "Georgia"}, {"team": "Ohio State"}, "junk"],
        "snapshots": [
            {"label": "Wk 8", "owners": [0, 0, 1, 2, 2, 2, 2, 2]},
            {"label": "Wk 9", "owners": [0, 0, 0, 1, 2, 2, 2, 9]},
            "junk",
        ],
    }
    land = svc.land_rows(table, {"Florida", "Georgia"})
    assert land["available"] is True and land["label"] == "Wk 9" and land["cells"] == 8 and land["held"] == 4 and land["pct"] == 50.0 and land["of"] == 3
    assert land["rows"] == [{"team": "Florida", "cells": 3, "pct": 37.5, "rank": 1, "change": 1}, {"team": "Georgia", "cells": 1, "pct": 12.5, "rank": 3, "change": 0}], "ties share a rank; the stray index is nobody"
    one = svc.land_rows({"teams": [{"team": "Florida"}], "snapshots": [{"label": "Start", "owners": [0]}]}, {"Florida"})
    assert one["rows"][0]["change"] is None, "no snapshot before: no change"
    assert svc.land_rows(None, {"Florida"})["available"] is False and "Sundays" in svc.land_rows({}, set())["words"]
    assert svc.land_rows({"teams": [], "snapshots": [{"owners": "junk"}]}, set())["available"] is False


# --- the route, against the recorded test app --------------------------------------------------------------------------


def test_the_route_answers_ours_another_by_its_short_name_and_a_wrong_name(client: TestClient, fake_cfbd: FakeCfbd):
    route_all(fake_cfbd)
    fake_cfbd.fixture("/ratings/sp/conferences", "ratings_sp_conferences")
    ours = client.get("/api/conference")
    assert ours.status_code == 200, ours.text[:300]
    data = ours.json()["data"]
    assert data["conference"]["name"] == "SEC" and data["conference"]["isOurs"] is True and data["conference"]["ourTeam"] == "Florida"
    assert [c["name"] for c in data["conferences"]][0] == "SEC" and len(data["conferences"]) >= 10
    for key in ("against", "standings", "week", "rated", "leaders", "land", "parts"):
        assert key in data, key
    assert any(r["team"] == "Florida" and r["isUs"] for r in data["standings"]["rows"]) and data["standings"]["race"]["us"]["team"] == "Florida"
    assert all(r["team"] in data["conference"]["members"] for r in data["rated"]) and len(data["rated"]) == data["conference"]["teams"]
    assert data["against"]["sp"] and any(c["isUs"] for c in data["against"]["sp"]) and data["against"]["numbers"]["rows"]
    assert set(data["leaders"]) == {"passing", "rushing", "receiving", "defense"} and all(r["team"] in data["conference"]["members"] for r in data["leaders"]["passing"]["rows"])
    assert data["land"]["available"] is False, "no map in the test app: the band says so"
    other = client.get("/api/conference/b1g")
    assert other.status_code == 200 and other.json()["data"]["conference"]["name"] == "Big Ten" and other.json()["data"]["conference"]["isOurs"] is False
    assert other.json()["data"]["standings"]["race"] is None, "the lines are ours alone"
    assert client.get("/api/conference/Nope").status_code == 404
    status = client.get("/api/datastatus?view=conference")
    assert status.status_code == 200 and [b["band"] for b in status.json()["data"]["bands"]] == [b for b, _s in PAGE_BANDS["conference"]]


# --- the page, in the fake browser --------------------------------------------------------------------------------------------

SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object Object\]/;
const text = (node) => (node ? node.textContent : "");

function answer() {
  return {
    season: 2026,
    conference: { name: "SEC", short: "SEC", teams: 16, members: ["Florida", "Georgia"], ranked: 8, isOurs: true, ourTeam: "Florida", spRank: 2, spOf: 11 },
    conferences: [{ name: "SEC", short: "SEC", teams: 16, isOurs: true }, { name: "Big Ten", short: "B1G", teams: 18, isOurs: false }, { name: null }, "junk"],
    against: {
      sp: [{ conference: "SEC", rank: 2, rating: 12.7, offense: 32.5, defense: 20.1, specialTeams: 0.28 }, { conference: "Big Ten", rank: 3, rating: 10, offense: null, defense: undefined, specialTeams: NaN }, null],
      numbers: { of: 2, columns: [{ key: "passYpg", label: "Pass Y/G", higherIsBetter: true }, { key: "rushYpg", label: "Rush Y/G" }, "junk"], rows: [{ conference: "SEC", short: "SEC", teams: 16, passYpg: 239.8, passYpgRank: 1, rushYpg: null }, { conference: "Big Ten", short: "B1G", teams: 18, passYpg: 236.1, passYpgRank: 2, rushYpg: 149 }, 4] },
    },
    standings: {
      ours: true,
      rows: [
        { place: 1, team: "Georgia", abbreviation: "UGA", conference: { wins: 5, losses: 1 }, overall: { wins: 7, losses: 1 }, apRank: 2, isUs: false, raceStatus: "alive", bestPlace: 1, worstPlace: 15, form: [{ result: "W" }, { result: "L" }] },
        { place: 2, team: "Florida", abbreviation: "FLA", conference: { wins: 3, losses: 3 }, overall: { wins: 5, losses: 3 }, apRank: null, isUs: true, raceStatus: "alive", bestPlace: 1, worstPlace: 16, form: "junk" },
        { place: 3, team: "Vanderbilt", abbreviation: "VAN", conference: null, overall: undefined, raceStatus: "out", bestPlace: 3, worstPlace: 16 },
        { team: null }, null,
      ],
      race: { us: { team: "Florida" }, lines: [{ lead: "Win out (3 left)", text: "in only if Texas loses once more." }, { lead: "Junk" }, null] },
      helps: {},
    },
    week: {
      week: 10, label: "Week 10", picksBy: null, ready: true, note: null, record: { right: 0, wrong: 0 },
      games: [
        { gameId: 1, kickoff: "2026-11-08T00:45:00Z", tv: "SEC Network", home: { school: "Florida", abbreviation: "FLA", rank: 25 }, away: { school: "Oklahoma", abbreviation: "OU" }, line: { formatted: "Florida -6", short: "FLA -6" }, pick: null, isUs: true, helps: { pullFor: "Florida", why: "Our own game", ours: true }, conferenceGame: true },
        { gameId: 2, kickoff: "2026-11-08T00:30:00Z", tv: "ABC", home: { school: "Ole Miss", rank: 12 }, away: { school: "Georgia", rank: 2 }, line: null, helps: { pullFor: "Ole Miss", why: "a loss by Georgia helps most", ours: false }, conferenceGame: true },
        { gameId: 3, kickoff: null, home: { school: "Vanderbilt" }, away: { school: "Toledo" }, conferenceGame: false },
        "junk",
      ],
    },
    rated: [
      { place: 1, team: "Georgia", abbreviation: "UGA", isUs: false, sp: { rating: 27.1, rank: 2 }, spOffense: { rating: 39.6, rank: 2 }, spDefense: { rating: 12.9, rank: 4 }, elo: { rating: 2037, rank: 3 }, fpi: { rating: 25.4, rank: 4 }, talent: { talent: 1003.7, rank: 1, of: 138 }, talentEdge: { rank: 1, of: 138, pct: 100 } },
      { place: 2, team: "Florida", abbreviation: "FLA", isUs: true, sp: { rating: 10.6, rank: 31 }, talentEdge: null },
      { team: null }, "junk",
    ],
    talentEdge: { available: true, computedWeek: 9 },
    leaders: {
      passing: { lead: "yds", label: "Yds", rows: [{ playerId: "1", player: "Trinidad Chambliss", position: "QB", team: "Ole Miss", abbreviation: "MISS", value: 2189, rank: 13 }, { playerId: null, player: "No Id", position: null, team: "Georgia", value: null, rank: null }, "junk"] },
      rushing: { lead: "yds", label: "Yds", rows: [] },
      receiving: { available: false, rows: [] },
      defense: "junk",
    },
    land: { available: true, computedWeek: 9, label: "Wk 9", cells: 12050, held: 2510, pct: 20.8, of: 72, rows: [{ team: "Texas", cells: 500, pct: 4.1, rank: 1, change: 12 }, { team: "Florida", cells: 120, pct: 1.0, rank: 26, change: -3, isUs: true }, { team: "Vanderbilt", cells: 0, pct: 0, rank: null, change: 0 }, { team: null }, 9] },
    parts: { records: { status: "ok" }, ratings: { status: "ok" }, stats: { status: "stale", ageSeconds: 4000 } },
  };
}

async function mountPage(arg) {
  installWindow();
  const { setIdentity } = await import(moduleUrl("identity.js"));
  setIdentity({ school: "Florida", mascot: "Gators", abbreviation: "FLA", conference: "SEC", conferenceShort: "SEC", color: "#0021a5", altColor: "#fa4616" });
  const { createConferenceView } = await import(moduleUrl("views/conference.js"));
  const { clearEnvelopeCache } = await import(moduleUrl("views/common.js"));
  clearEnvelopeCache();
  const main = document.createElement("main");
  document.body.append(main);
  const view = createConferenceView({ arg });
  view.mount(main);
  await settle();
  return { main, view };
}

scenarios.page = async () => {
  route("/api/conference", () => envelope(answer()));
  const { main, view } = await mountPage(null);
  const t = text(main);
  assert.ok(!RAW.test(t), t.slice(0, 600));
  for (const id of ["conf-against", "conf-standings", "conf-week", "conf-rated", "conf-leaders", "conf-land"]) assert.ok(main.querySelector(`#${id}`), id);
  const chips = main.querySelectorAll(".conf-chips__chip");
  assert.equal(chips.length, 2, "a chip a conference with a name");
  assert.ok(chips[0].className.includes("is-on") && chips[0].getAttribute("href") === "#conference" && chips[1].getAttribute("href") === "#conference=Big%20Ten", "ours is #conference, the others carry their name");
  assert.ok(text(main.querySelector(".conf-head__name")) === "SEC" && t.includes("2nd") && t.includes("8") && t.includes("21%"), "the facts strip");
  // the standings: Can finish, the race's lines on ours, the form squares
  const standings = main.querySelector("#conf-standings");
  assert.ok(text(standings).includes("1st to 15th") && text(standings).includes("Out") && text(standings).includes("Win out (3 left)"), text(standings).slice(0, 400));
  assert.ok(standings.querySelector("tr.is-us"), "our row marked");
  // the week: the picks rows with the pull-for chips
  const week = main.querySelector("#conf-week");
  assert.equal(week.querySelectorAll("li.picks__row").length, 3);
  assert.ok(text(week).includes("Our game") && text(week).includes("pull for Ole Miss") && text(week).includes("FLA -6") && text(week).includes("TV to be set"), text(week).slice(0, 500));
  assert.ok(week.querySelector("li.conf-week__cross"), "a game against another conference reads lighter");
  // the teams, rated: the Talent Edge column when any team has it
  const rated = main.querySelector("#conf-rated");
  assert.ok(text(rated).includes("27.1") && text(rated).includes("100") && rated.querySelector("tr.is-us"), text(rated).slice(0, 400));
  // the leaders: one list with rows, the empty ones say so, the junk one too
  const leaders = main.querySelector("#conf-leaders");
  assert.ok(text(leaders).includes("Chambliss") && text(leaders).includes("Nobody from the conference") && text(leaders).includes("could not be read"), text(leaders).slice(0, 600));
  // the land: the bars, the change, the share
  const land = main.querySelector("#conf-land");
  assert.ok(land.querySelectorAll(".conf-bar").length === 3 && text(land).includes("+12") && text(land).includes("-3") && text(land).includes("held") && text(land).includes("21% of the map"), text(land).slice(0, 400));
  // the switch redraws the first band by the numbers and remembers it
  const numbers = main.querySelector("#conf-against .box__switch").querySelectorAll("button").find((b) => text(b) === "By the numbers");
  numbers.click();
  await settle();
  const against = main.querySelector("#conf-against");
  assert.ok(text(against).includes("Pass Y/G") && text(against).includes("239.8") && !RAW.test(text(against)), text(against).slice(0, 400));
  assert.equal(view.state.view, "numbers");
  view.unmount();
};

scenarios.another = async () => {
  const other = { ...answer(), conference: { name: "Big Ten", short: "B1G", teams: 18, members: [], ranked: 5, isOurs: false, ourTeam: null, spRank: 3, spOf: 11 }, standings: { ours: false, rows: [], race: null, helps: {} }, week: { games: [], label: "Week 10" }, land: { available: false, words: "The Imperialism Map has not been worked out yet." }, rated: [{ place: 1, team: "Ohio State", sp: { rating: 30, rank: 1 } }] };
  route("/api/conference/Big%20Ten", () => envelope(other));
  const { main, view } = await mountPage("Big Ten");
  const t = text(main);
  assert.ok(!RAW.test(t), t.slice(0, 600));
  assert.ok(text(main.querySelector(".conf-head__name")) === "Big Ten" && !t.includes("Our conference"));
  assert.ok(text(main.querySelector("#conf-standings")).includes("Standings appear after the first conference game."));
  assert.ok(text(main.querySelector("#conf-week")).includes("No games with a team of the conference this week."));
  assert.ok(text(main.querySelector("#conf-land")).includes("has not been worked out yet"));
  view.unmount();
};

scenarios.damaged = async () => {
  route("/api/conference", () => envelope({ conference: "junk", conferences: "junk", against: null, standings: 4, week: "x", rated: "x", leaders: null, land: "x", parts: "x" }));
  const { main, view } = await mountPage(null);
  const t = text(main);
  assert.ok(!RAW.test(t), t.slice(0, 600));
  for (const id of ["conf-against", "conf-standings", "conf-week", "conf-rated", "conf-leaders", "conf-land"]) assert.ok(main.querySelector(`#${id}`), id);
  view.unmount();
  const { flatRated, conferenceHref, headBlock } = await import(moduleUrl("views/conference.js"));
  assert.deepEqual(flatRated("junk"), []);
  assert.equal(flatRated([{ team: "A", sp: null, talentEdge: null }])[0].edge, undefined);
  assert.equal(conferenceHref("Big 12"), "#conference=Big%2012");
  assert.equal(conferenceHref("SEC", { ours: true }), "#conference");
  assert.equal(conferenceHref(null), "#conference");
  assert.ok(!RAW.test(text(headBlock({}))));
};

scenarios.catalog = async () => {
  const cat = await import(moduleUrl("ui/band-catalog.js"));
  const page = cat.BAND_PAGES.conference;
  assert.ok(page && page.route === "conference" && page.bands.map((b) => b.id).join() === "conf-against,conf-against-numbers,conf-standings,conf-week,conf-rated,conf-leaders,conf-land");
  assert.equal(cat.bandHref("conference", "conf-standings"), "#band=conference:conf-standings");
  assert.equal(cat.bandHref("conference", "conf-against-numbers"), "#band=conference:conf-against-numbers?view=numbers");
  const { MENU } = await import(moduleUrl("ui/menu-tree.js"));
  const national = MENU.groups.find((g) => g.id === "national");
  const row = national.items.find((i) => i && i.id === "conference");
  assert.ok(row && row.page === "conference" && !row.items, "under National, one row that opens the page (ENH-46, owner 2026-11-10: its bands are on the page)");
  const fresh = MENU.groups.find((g) => g.id === "new");
  assert.ok(fresh.items.some((i) => i && i.id === "new:conference"), "in New for his test");
};
"""


@needs_node
@pytest.mark.parametrize("scenario", ["page", "another", "damaged", "catalog"])
def test_the_page_in_the_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)
