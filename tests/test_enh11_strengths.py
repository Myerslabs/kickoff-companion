"""ENH-11 (the owner's list of 2026-10-23 and his board of 2026-10-28, "Build
it"): strengths and weaknesses under Tale of the tape. Run and pass by CFBD's points added per play, special teams by SP+,
coaching by win percentage career and at the school, talent by the 247 composite, cost by the rumored roster budget.

The coach records: CFBD keeps the season under way at 0-0 (seen 2026-10-21 and 10-28), so this season always comes from the
games and CFBD's row for it is never read; a mid-season change takes the coach hired last; ranks share ties. The band: each
team's bar from the middle toward its own side, in the rank's tone, the cost in words with the way to load the rest."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.cfbd.models import Coach, Game
from app.services.stats_extra import rank_table
from app.services.strengths import COACH_MIN_YEAR, block, coach_records, cost_ranks, season_records
from tests.conftest import FakeCfbd
from tests.fakedom import needs_node, run_scenario
from tests.test_program import route_program

SEASON = 2026


def coach(cid: int, first: str, last: str, hired: str, *seasons: tuple[str, int, int, int]) -> Coach:
    return Coach.model_validate({"id": cid, "firstName": first, "lastName": last, "hireDate": hired, "seasons": [{"school": s, "year": y, "wins": w, "losses": lo} for s, y, w, lo in seasons]})


def game(gid: int, home: str, away: str, hp: int | None, ap: int | None, completed: bool = True, season: int = SEASON) -> Game:
    return Game.model_validate({"id": gid, "season": season, "homeTeam": home, "awayTeam": away, "homePoints": hp, "awayPoints": ap, "completed": completed})


GAMES = [
    game(1, "Florida", "Troy", 35, 10),
    game(2, "Miami", "Florida", 24, 21),
    game(3, "Florida", "Georgia", 20, 27),
    game(4, "Georgia", "Alabama", 31, 30),
    game(5, "Florida", "Kentucky", None, None, completed=False),  # not played yet
    game(6, "Florida", "LSU", 40, 3, season=2025),  # last season: not this one's
]


def test_this_season_comes_from_the_games_and_cfbds_row_for_it_is_never_read():
    coaches = [
        coach(1, "Jon", "Sumrall", "2025-11-30", ("Troy", 2022, 12, 2), ("Troy", 2023, 11, 2), ("Tulane", 2024, 9, 5), ("Tulane", 2025, 11, 3), ("Florida", SEASON, 0, 0)),
        coach(2, "Kirby", "Smart", "2015-12-06", ("Georgia", 2024, 11, 3), ("Georgia", 2025, 12, 2), ("Georgia", SEASON, 9, 9)),  # a filled-in row would double count
        coach(3, "Old", "Hand", "2010-01-01", ("Troy", 2019, 5, 7)),  # no season now: not a head coach this season
    ]
    lines = coach_records(coaches, GAMES, SEASON, {"Florida", "Georgia", "Alabama", "Miami"})
    assert set(lines) == {"Florida", "Georgia"}
    fl, ga = lines["Florida"], lines["Georgia"]
    assert fl["coach"] == "Jon Sumrall" and fl["career"] == (43 + 1, 12 + 2) and fl["school"] == (1, 2), "1-2 this season, from the games"
    assert ga["career"] == (23 + 2, 5) and ga["school"] == (25, 5), "Georgia's 2-0 from the games, never CFBD's 9-9"
    assert ga["careerRank"] == 1 and fl["careerRank"] == 2 and fl["of"] == 2
    assert ga["schoolPct"] == round(25 / 30, 3) and fl["schoolPct"] == round(1 / 3, 3)
    assert season_records(GAMES, SEASON)["Florida"] == (1, 2)


def test_a_mid_season_change_takes_the_coach_hired_last_and_ties_share_a_rank():
    coaches = [
        coach(1, "Fired", "Early", "2022-12-01", ("Miami", 2023, 6, 6), ("Miami", SEASON, 0, 0)),
        coach(2, "Interim", "Now", "2026-10-02", ("Miami", SEASON, 0, 0)),
        coach(3, "Even", "Steven", "2020-01-01", ("Alabama", 2024, 1, 1), ("Alabama", SEASON, 0, 0)),
        coach(4, "Twin", "Record", "2020-01-01", ("Troy", 2024, 2, 2), ("Troy", SEASON, 0, 0)),
        coach(5, "Not", "Fbs", "2020-01-01", ("Somewhere", 2024, 9, 0), ("Somewhere", SEASON, 0, 0)),
    ]
    games = [game(1, "Alabama", "Troy", 10, 7), game(2, "Troy", "Alabama", 10, 7)]
    lines = coach_records(coaches, games, SEASON, {"Miami", "Alabama", "Troy"})
    assert lines["Miami"]["coach"] == "Interim Now" and lines["Miami"]["careerPct"] is None and lines["Miami"]["careerRank"] is None, "no games yet: no percentage, no rank"
    assert "Somewhere" not in lines, "FBS schools only"
    assert lines["Alabama"]["careerPct"] == lines["Troy"]["careerPct"] == 0.5
    assert lines["Alabama"]["careerRank"] == lines["Troy"]["careerRank"] == 1 and lines["Alabama"]["careerTie"] and lines["Troy"]["careerTie"]
    assert lines["Alabama"]["of"] == 2, "ranked among the coaches who have a record"
    assert COACH_MIN_YEAR == 1990


def test_junk_never_breaks_the_records_or_the_costs():
    coaches = [
        coach(1, "", "", "", ("Florida", SEASON, 0, 0)),
        Coach.model_validate({"id": 2, "seasons": [{"school": None, "year": SEASON}, {"school": "Georgia", "year": "x"}]}),
        "not a coach",
    ]
    lines = coach_records(coaches, [game(1, "Florida", "Georgia", 3, 0), "junk"], SEASON, None)  # type: ignore[list-item]
    assert lines["Florida"]["coach"] is None and lines["Florida"]["career"] == (1, 0)
    costs = cost_ranks({"Florida": {"totalUsd": 31e6}, "Georgia": {"totalUsd": 31e6}, "Texas": {"totalUsd": 45e6}, "Bad": {"totalUsd": "lots"}, "Zero": {"totalUsd": 0}, "Nan": {"totalUsd": float("nan")}, "Row": "x"})
    assert set(costs) == {"Florida", "Georgia", "Texas"} and costs["Texas"]["rank"] == 1 and costs["Florida"] == {"totalUsd": 31e6, "rank": 2, "tie": True, "of": 3}
    assert cost_ranks(None) == {}  # type: ignore[arg-type]


def test_the_block_is_the_owners_order_with_both_teams_on_every_row():
    adv = lambda key, value, rank: {"key": key, "value": value, "nationalRank": rank, "nationalOf": 138, "metric": f"advanced:{key}"}  # noqa: E731
    us = [adv("offense_rushing_plays_ppa", 0.155, 41), adv("offense_passing_plays_ppa", 0.405, 21), adv("defense_rushing_plays_ppa", -0.04, 32), adv("defense_passing_plays_ppa", 0.254, 99)]
    them = [adv("offense_rushing_plays_ppa", 0.24, 9), adv("offense_passing_plays_ppa", 0.559, 2)]
    special = rank_table({"Florida": 0.6, "Georgia": 0.5, "Texas": -0.1}, True)
    talent = {"Florida": {"talent": 891.07, "rank": 10, "of": 138, "metric": "rating:talent"}}
    coaching = {"Florida": {"coach": "Jon Sumrall", "career": (48, 14), "school": (5, 2), "careerPct": 0.774, "careerRank": 10, "careerTie": False, "schoolPct": 0.714, "schoolRank": 22, "schoolTie": True, "of": 138}}
    costs = cost_ranks({"Florida": {"totalUsd": 31e6}, "Georgia": {"totalUsd": 31e6}})
    out = block(us, them, special, talent, coaching, costs, "Florida", "Georgia")
    assert [g["key"] for g in out["groups"]] == ["offense", "defense", "special", "coaching", "talent"]
    run = out["groups"][0]["rows"][0]
    assert run["label"] == "Run" and run["us"]["rank"] == 41 and run["them"]["rank"] == 9 and run["us"]["metric"] == "advanced:offense_rushing_plays_ppa" and run["words"] == "a run"
    d_pass = out["groups"][1]["rows"][1]
    assert d_pass["us"]["rank"] == 99 and d_pass["them"] == {"value": None, "rank": None, "of": None, "metric": None}, "a missing row is empty, never an error"
    st = out["groups"][2]["rows"][0]
    assert st["us"]["rank"] == 1 and st["them"]["rank"] == 2 and st["us"]["metric"] == "rating:spSpecial"
    co = out["groups"][3]
    assert co["coaches"] == {"us": "Jon Sumrall", "them": None}
    assert co["rows"][1]["us"] == {"value": 0.714, "rank": 22, "of": 138, "metric": None, "wins": 5, "losses": 2, "tie": True}
    assert co["rows"][0]["them"]["rank"] is None
    assert out["groups"][4]["rows"][0]["us"]["rank"] == 10 and out["groups"][4]["rows"][0]["them"]["rank"] is None
    assert out["cost"]["of"] == 2 and out["cost"]["us"]["rank"] == 1 and out["cost"]["us"]["tie"] is True
    assert "NaN" not in json.dumps(out)
    empty = block([], [], None, {}, {}, {}, "Florida", None)
    assert empty["cost"] == {"us": None, "them": None, "of": None} and all(r["us"]["rank"] is None for g in empty["groups"] for r in g["rows"])


def test_the_program_carries_the_strengths(client: TestClient, fake_cfbd: FakeCfbd):
    route_program(fake_cfbd)
    asked: list[dict] = []

    def coaches(request: httpx.Request) -> httpx.Response:
        asked.append(dict(request.url.params))
        return httpx.Response(200, json=[
            {"id": 1, "firstName": "Jon", "lastName": "Sumrall", "hireDate": "2025-11-30T00:00:00.000Z", "seasons": [{"school": "Troy", "year": 2023, "wins": 11, "losses": 2}, {"school": "Florida", "year": SEASON, "wins": 0, "losses": 0}]},
            {"id": 2, "firstName": None, "seasons": "not a list"},
        ])

    fake_cfbd.route("/coaches", handler=coaches)
    data = client.get("/api/program/next").json()["data"]
    s = data["strengths"]
    assert [g["key"] for g in s["groups"]] == ["offense", "defense", "special", "coaching", "talent"]
    assert {"minYear": "1990", "maxYear": str(SEASON)} in asked, "one answer for every coach since 1990"
    co = s["groups"][3]
    assert co["coaches"]["us"] == "Jon Sumrall"
    career = co["rows"][0]["us"]
    assert career["wins"] >= 11 and career["rank"] == 1 and career["of"] == 1, career
    offense = s["groups"][0]["rows"]
    assert all(isinstance(r["us"]["rank"], int) for r in offense), "the season's advanced stats rank both PPA rows"
    assert s["cost"]["of"] is None or isinstance(s["cost"]["of"], int)
    assert "NaN" not in json.dumps(s)


SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object Object\]/;
const text = (node) => (node ? node.textContent : "");
const side = (rank, value, extra = {}) => ({ value, rank, of: rank === null ? null : 138, metric: rank === null ? null : "advanced:x", ...extra });
const DATA = {
  us: { school: "Florida", abbreviation: "FLA" },
  them: { school: "Georgia", abbreviation: "UGA" },
  strengths: {
    groups: [
      { key: "offense", label: "Offense", rows: [{ key: "offenseRun", label: "Run", format: "+2f", words: "a run", us: side(41, 0.155), them: side(9, 0.24) }, { key: "offensePass", label: "Pass", format: "+2f", words: "a pass", us: side(21, 0.405), them: side(2, 0.559) }] },
      { key: "defense", label: "Defense", rows: [{ key: "defenseRun", label: "Run", format: "+2f", words: "allowed", us: side(32, -0.04), them: side(8, -0.135) }, { key: "defensePass", label: "Pass", format: "+2f", words: "allowed", us: side(130, 0.354), them: side(null, null) }] },
      { key: "special", label: "Special teams", rows: [{ key: "special", label: "SP+ special teams", format: "+1f", words: "", us: side(1, 0.6), them: side(2, 0.5) }] },
      { key: "coaching", label: "Coaching", coaches: { us: "Jon Sumrall", them: "Kirby Smart" }, rows: [{ key: "coachCareer", label: "Career", format: "pct3", words: "", us: { value: 0.774, rank: 10, of: 138, metric: null, wins: 48, losses: 14, tie: false }, them: { value: 0.848, rank: 5, of: 138, metric: null, wins: 123, losses: 22, tie: false } }, { key: "coachSchool", label: "At this school", format: "pct3", words: "", us: { value: 0.714, rank: 22, of: 138, metric: null, wins: 5, losses: 2, tie: true }, them: { value: 0.848, rank: 7, of: 138, metric: null, wins: 123, losses: 22, tie: false } }] },
      { key: "talent", label: "Talent", rows: [{ key: "talent", label: "247 composite", format: "0f", words: "", us: side(10, 891.07), them: side(1, 1003.67) }] },
    ],
    cost: { us: { totalUsd: 31e6, rank: 8, tie: true, of: 18 }, them: { totalUsd: 31e6, rank: 8, tie: true, of: 18 }, of: 18 },
  },
};

scenarios.band = async () => {
  installWindow();
  const { strengthsBand, barShare, costWords } = await import(moduleUrl("ui/strengths.js"));
  const section = strengthsBand(DATA);
  document.body.append(section);
  const words = text(section);
  assert.ok(!RAW.test(words), words.match(/.{0,40}(undefined|null|NaN|Infinity).{0,40}/)?.[0]);
  assert.equal(section.getAttribute("id"), "program-strengths");
  assert.ok(words.includes("FLA best: special teams 1st") && words.includes("UGA best: talent 1st"), "the summary");
  assert.ok(words.includes("Coaching · Sumrall and Smart") || words.includes("COACHING") || words.includes("Sumrall and Smart"));
  const rows = section.querySelectorAll(".strengths__row");
  assert.equal(rows.length, 9, "eight ranked rows and the cost");
  const run = rows[0];
  const bars = run.querySelectorAll(".strengths__bar");
  assert.equal(bars.length, 2);
  assert.ok(run.querySelector(".strengths__track--us .strengths__bar--mid") && run.querySelector(".strengths__track--them .strengths__bar--top"), "41st is the middle, 9th a strength");
  assert.equal(run.querySelector(".strengths__track--us .strengths__bar").style.width, `${barShare(41, 138).toFixed(1)}%`);
  assert.ok(text(run).includes("+0.16 a run") && text(run).includes("Run"));
  const chip = run.querySelector(".strengths__end--us a.rank-chip--link");
  assert.ok(chip && chip.getAttribute("href").startsWith("#national=advanced"), "the chip opens the national list");
  const weak = rows[3];
  assert.ok(weak.querySelector(".strengths__track--us .strengths__bar--bottom"), "130th is a weakness");
  assert.ok(!weak.querySelector(".strengths__track--them .strengths__bar") && text(weak.querySelector(".strengths__end--them")).includes("–"), "no rank: no bar, a dash");
  assert.ok(text(rows[5]).includes(".774 · 48-14") && text(rows[6]).includes("T22"), "the coaching record, a tie said so");
  assert.ok(!rows[5].querySelector("a.rank-chip--link"), "coaching has no national list");
  const cost = rows[8];
  assert.ok(text(cost).includes("both rumored at $31M, tied 8th of the 18 schools loaded") && cost.querySelector('a[href="#prompts"]'), text(cost));
  // the edges
  assert.equal(barShare(1, 138), 100);
  assert.ok(barShare(138, 138) >= 3 && barShare(138, 138) < 4);
  assert.equal(barShare(null, 138), 0);
  assert.equal(costWords({ us: { totalUsd: 31e6, rank: 8, tie: true }, them: null, of: 18 }, "FLA", "UGA"), "Roster budget: FLA rumored at $31M (tied 8th of the 18 schools loaded); UGA not loaded");
  assert.equal(costWords({ us: { totalUsd: 45e6, rank: 2 }, them: { totalUsd: 31e6, rank: 8, tie: true }, of: 18 }, "FLA", "UGA"), "Roster budget, rumored: FLA 2nd, UGA tied 8th of the 18 schools loaded");
  assert.equal(costWords(null, "FLA", "UGA"), "No roster budget loaded for either team");
  // an old lock has no strengths; an early week has no ranks yet
  assert.equal(strengthsBand({ ...DATA, strengths: undefined }), null);
  const early = strengthsBand({ ...DATA, strengths: { groups: [{ key: "offense", label: "Offense", rows: [{ key: "offenseRun", label: "Run", us: side(null, null), them: side(null, null) }] }], cost: null } });
  document.body.append(early);
  assert.ok(text(early).includes("The ranks appear once CFBD publishes"), text(early));
};

scenarios.program = async () => {
  const program = (await import("node:fs")).readFileSync(new URL(moduleUrl("views/program.js")), "utf8");
  // the season as one line, Wave 2 (the owner's board of 2026-10-30): the strengths lead The matchup box, the tape under them
  assert.ok(/matchupBox\(data, \{ view \}\), \/\/ 2 The matchup/.test(program), "The matchup is the second row of the program");
  assert.ok(program.includes("const strengths = strengthsParts(data);") && program.includes('el("h4", { class: "d2-head" }, "Strengths and weaknesses"), strengths.body()'), "the strengths' rows lead the box");
  assert.ok(program.includes('id: "program-matchup"') && program.includes('matchup: (data) => matchupBox(data, { view: "stats" })'), "the box has a flyout of its own");
  const { MENU } = await import(moduleUrl("ui/menu-tree.js"));
  const cat = await import(moduleUrl("ui/band-catalog.js"));
  const matchup = cat.bandEntry("program", cat.findBand("program", "program-matchup"));
  assert.ok(matchup.flyout === "program:matchup", "the box opens wide by itself, from its own head and from Search (ENH-46: the menu's list of the matchup went)");
  assert.equal(MENU.groups.find((g) => g.id === "new").items[0].flyout, "program:matchup", "and from New while he tests it");
};
"""


@needs_node
@pytest.mark.parametrize("scenario", ["band", "program"])
def test_the_band_in_a_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)
