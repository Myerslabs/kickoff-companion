"""FEAT-16 Talent Edge's band (the owner's board of 2026-10-30, "Keep FBS
percentile", no other marks): the program's `talentEdge` block in each of its states (never worked out, a failed first run,
both teams, an FCS opponent, a failure after a good run), the program's answer carrying it, Data status listing it, and the
band in a fake browser: the caveat, the totals beside the spider, every group mirrored, the six unit matchups, no raw
undefined, null or NaN on screen, and its place at the bottom of the program and in the menu's New."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.jobs import JobRuns
from app.services.talent_edge import GROUPS, PlayerTalent, TalentEdgeStore, build_table, player_rows, program_block
from tests.conftest import FakeCfbd
from tests.fakedom import needs_node, run_scenario
from tests.test_program import route_program

S = 2026


def players(team: str, rating: float, stars: int) -> list[PlayerTalent]:
    return [PlayerTalent(f"{team[:3]}{i}", team, f"P {i}", g, g, rating, stars, 2024, "recruit_id", i == 0) for i, g in enumerate(GROUPS)]


def save_table(data_dir: Path, *teams: tuple[str, float, int]) -> None:
    rows = [p for team, rating, stars in teams for p in players(team, rating, stars)]
    TalentEdgeStore(data_dir, S).save(build_table(rows, {}, {t: {"abbreviation": t[:3].upper()} for t, _r, _s in teams}, S, 9, {}), player_rows(rows))


def runs(data_dir: Path, *outcomes: tuple[str, str]) -> None:
    log = JobRuns(data_dir)
    for status, message in outcomes:
        run = log.start("talent_edge", S)
        log.finish(run["id"], status, message)


def test_never_worked_out_says_so(tmp_path: Path):
    block = program_block(TalentEdgeStore(tmp_path, S), tmp_path, "Florida", "Georgia")
    assert block["available"] is False and block["failed"] is False
    assert "has not been worked out yet" in block["message"]


def test_a_failed_first_run_says_since_when_and_why(tmp_path: Path):
    runs(tmp_path, ("failed", "CFBD data missing for 1 source (roster: HTTP 500)"))
    block = program_block(TalentEdgeStore(tmp_path, S), tmp_path, "Florida", "Georgia")
    assert block["available"] is False and block["failed"] is True
    assert "unavailable since" in block["message"] and "CFBD data missing" in block["message"]


def test_both_teams_the_matchups_and_a_later_failure(tmp_path: Path):
    save_table(tmp_path, ("Florida", 0.90, 4), ("Georgia", 0.93, 4), ("Troy", 0.84, 3))
    runs(tmp_path, ("ok", "fine"))
    block = program_block(TalentEdgeStore(tmp_path, S), tmp_path, "Florida", "Georgia")
    assert block["available"] is True and block["computedWeek"] == 9 and block["of"] == 3 and block["lastFailure"] is None
    assert block["us"]["team"] == "Florida" and block["them"]["team"] == "Georgia" and block["missing"] == []
    assert len(block["cross"]) == 6 and block["cross"][0]["a_rating"] == 0.9 and block["cross"][0]["b_rating"] == 0.93
    assert block["us"]["summaryLine"] == "0.90 avg · 100% BCR", "no 247 talent in this table: the rest of the line"
    runs(tmp_path, ("failed", "CFBD down"))
    later = program_block(TalentEdgeStore(tmp_path, S), tmp_path, "Florida", "Georgia")
    assert later["available"] is True and later["lastFailure"]["message"] == "CFBD down", "the last good numbers, said to be not updated"


def test_an_fcs_opponent_is_named_and_the_matchups_wait_for_both(tmp_path: Path):
    save_table(tmp_path, ("Florida", 0.90, 4))
    block = program_block(TalentEdgeStore(tmp_path, S), tmp_path, "Florida", "Campbell")
    assert block["us"] and block["them"] is None and block["missing"] == ["Campbell"] and block["cross"] == []
    assert program_block(TalentEdgeStore(tmp_path, S), tmp_path, "Florida", None)["missing"] == []


def test_the_program_carries_the_block_and_data_status_lists_it(client: TestClient, fake_cfbd: FakeCfbd):
    route_program(fake_cfbd)
    first = client.get("/api/program/next").json()["data"]
    assert first["talentEdge"]["available"] is False, "before the job: why, not an empty chart"
    us, them = first["us"]["school"], first["them"]["school"]
    data_dir = client.app.state.settings.data_dir
    save_table(data_dir, (us, 0.90, 4), (them, 0.92, 4))
    client.app.state.program.talent_edge._cache = None
    fresh = client.app.state.program.talent_edge.load()
    assert fresh is not None
    from app.services.talent_edge import program_block as block_of

    block = block_of(client.app.state.program.talent_edge, data_dir, us, them)
    assert block["us"]["team"] == us and block["them"]["team"] == them and len(block["cross"]) == 6
    assert "NaN" not in json.dumps(block)
    status = client.get("/api/datastatus?view=program").json()["data"]
    names = [b["band"] if isinstance(b, dict) and "band" in b else b.get("name") for b in status["bands"]]
    assert any("Talent Edge" in str(n) for n in names), names
    season_loads = client.get("/api/datastatus?view=prompts")
    assert season_loads.status_code == 200


SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object \w+\]/;
const text = (node) => (node ? node.textContent : "");
const g = (count, rated, avg, stars, years, bcr, transfers, rank, pct) => ({ count, ratedCount: rated, avgRating: avg, avgStars: stars, avgYears: years, bcrPct: bcr, unratedCount: count - rated, transferCount: transfers, rank, of: 138, pct });
const FLA = {
  team: "Florida", abbreviation: "FLA", summary: { roster: 117, rated: 75, ratedByRecruit: 69, ratedByPortal: 6, unrated: 42, transfers: 31, outsideGroups: 9 },
  talent: { talent: 891.07, rank: 10, of: 138, metric: "rating:talent" },
  groups: {
    QB: g(5, 2, 0.8937, 3.5, 1.5, 50, 1, 27, 81), RB: g(8, 5, 0.9164, 4, 2.4, 100, 2, 9, 94), WR: g(14, 10, 0.9087, 3.8, 1.62, 70, 5, 11, 93),
    TE: g(8, 5, 0.889, 3.2, 2, 20, 3, 14, 90), OL: g(20, 16, 0.8973, 3.44, 1.69, 43.8, 5, 13, 91), FRONT7: g(30, 20, 0.9085, 3.7, 2.05, 65, 6, 12, 92),
    SECONDARY: g(23, 16, 0.9103, 3.75, 1.88, 68.8, 5, 7, 96), O: g(55, 38, 0.9016, 3.58, 1.8, 55.3, 16, 12, 92), D: g(53, 36, 0.9093, 3.72, 1.97, 66.7, 11, 10, 93),
    TOT: g(108, 74, 0.9053, 3.65, 1.89, 60.8, 27, 11, 93),
  },
};
const UGA = {
  team: "Georgia", abbreviation: "UGA", summary: { roster: 128, rated: 105, ratedByRecruit: 103, ratedByPortal: 2, unrated: 23, transfers: 14, outsideGroups: 9 },
  talent: { talent: 1003.67, rank: 1, of: 138, metric: "rating:talent" },
  groups: {
    QB: g(7, 6, 0.9109, 3.67, 2, 66.7, 1, 15, 90), RB: g(9, 7, 0.9268, 4, 1.62, 100, 2, 5, 97), WR: g(19, 11, 0.9209, 4, 1, 90.9, 2, 7, 96),
    TE: g(9, 8, 0.9422, 4, 1.12, 87.5, 0, 1, 100), OL: g(21, 19, 0.9139, 3.74, 1.39, 68.4, 2, 3, 99), FRONT7: g(33, 30, 0.9318, 4.07, 1.33, 80, 2, 1, 100),
    SECONDARY: g(21, 19, 0.9302, 3.95, 1.42, 84.2, 5, 5, 97), O: g(65, 51, 0.9213, 3.86, 1.35, 80.4, 7, 1, 100), D: g(54, 49, 0.9312, 4.02, 1.37, 81.6, 7, 1, 100),
    TOT: g(119, 100, 0.9261, 3.94, 1.36, 81, 14, 1, 100),
  },
};
const cross = [
  ["a", "WR", "SECONDARY"], ["a", "OL", "FRONT7"], ["a", "RB", "FRONT7"], ["b", "SECONDARY", "WR"], ["b", "FRONT7", "OL"], ["b", "FRONT7", "RB"],
].map(([offense, a, b]) => ({ offense, a_group: a, b_group: b, a_rating: FLA.groups[a].avgRating, b_rating: UGA.groups[b].avgRating, a_pct: FLA.groups[a].pct, b_pct: UGA.groups[b].pct }));
const DATA = {
  us: { school: "Florida", abbreviation: "FLA" },
  them: { school: "Georgia", abbreviation: "UGA" },
  talentEdge: { available: true, season: 2026, computedWeek: 9, computedAt: "2026-10-30T10:04:23-04:00", lastFailure: null, of: 138, us: FLA, them: UGA, missing: [], cross },
};

scenarios.band = async () => {
  installWindow();
  const { talentEdgeBand, talentEdgeSummary, spiderPoints } = await import(moduleUrl("ui/talent-edge.js"));
  const section = talentEdgeBand(DATA);
  document.body.append(section);
  const words = text(section);
  assert.ok(!RAW.test(words), words.match(/.{0,40}(undefined|null|NaN|Infinity|object).{0,40}/)?.[0]);
  assert.equal(section.getAttribute("id"), "program-talent-edge");
  assert.ok(words.includes("Roster rating: FLA 11th · UGA 1st of 138"), "the head's summary");
  assert.ok(words.includes("Ratings available: Florida 75 of 117, Georgia 105 of 128. Blue chips are of rated players. Worked out through week 9."), "the caveat");
  // the totals: Georgia bold where higher is better, years and transfers never bold
  const totals = [...section.querySelectorAll(".te-totals__row")].slice(1);
  assert.equal(totals.length, 6);
  assert.ok(text(totals[0]).includes("0.905") && text(totals[0]).includes("0.926"));
  assert.ok(totals[0].querySelector(".te__v--them.te__v--better") && !totals[0].querySelector(".te__v--us.te__v--better"), "the better rating bold");
  assert.ok(!totals[2].querySelector(".te__v--better") && !totals[4].querySelector(".te__v--better"), "years and transfers never bold");
  assert.ok(text(totals[3]).includes("61%") && text(totals[3]).includes("81%"), "whole-number shares");
  assert.ok(text(totals[5]).includes("891") && text(totals[5]).includes("1,004"));
  const chip = totals[5].querySelector(".te-totals__end--us a.rank-chip--link");
  assert.ok(chip && chip.getAttribute("href").startsWith("#national=rating"), "the 247 rank opens its national list");
  // the spider: both shapes, percentiles printed at each spoke
  assert.ok(section.querySelector(".te-spider__us") && section.querySelector(".te-spider__them"));
  assert.equal(section.querySelectorAll(".te-spider__axis").length, 7);
  assert.ok(text(section.querySelector(".te-spider")).includes("Front 7") && text(section.querySelector(".te-spider")).includes("92 · 100"));
  assert.equal(section.querySelector(".te-spider__us").getAttribute("points"), spiderPoints([81, 94, 93, 90, 91, 92, 96]));
  assert.equal(spiderPoints([100, 100, 100, 100, 100, 100, 100]).split(" ")[0], "180.0,54.0", "100 at the rim, QB straight up");
  assert.equal(spiderPoints([null, "x", 50, 50, 50, 50, 50]).split(" ")[0], "180.0,172.0", "a missing value sits at the middle");
  // every group, mirrored
  const groups = section.querySelectorAll(".te-groups tbody tr");
  assert.equal(groups.length, 10);
  assert.ok(text(groups[0]).includes("QB") && text(groups[0]).includes("2 of 5 · 6 of 7"));
  assert.ok(groups[7].classList.contains("te-groups__rollup"), "the roll-ups set off");
  assert.ok(groups[1].querySelectorAll(".te__v--better").length >= 1 && text(groups[1]).split("100%").length === 3, "RB: both at 100%, neither bold there");
  // the unit matchups
  const units = section.querySelectorAll(".te-unit");
  assert.equal(units.length, 6);
  assert.ok(text(section).includes("When Florida has the ball") && text(section).includes("When Georgia has the ball"));
  assert.ok(text(units[0]).includes("Our receivers") && text(units[0]).includes("their secondary"));
  assert.equal(units[1].querySelector(".te-unit__track--them .te-unit__bar").style.width, "100%");
  assert.equal(units[0].querySelector(".te-unit__track--us .te-unit__bar").style.width, "93%");
  // another team's program says the schools, not "our"
  const other = talentEdgeBand({ ...DATA, ours: false });
  assert.ok(text(other.querySelector(".te-unit")).includes("FLA receivers"));
  assert.equal(talentEdgeSummary(UGA), "#1 talent · 0.93 avg · 81% BCR");
  assert.equal(talentEdgeSummary({}), null);
  assert.equal(talentEdgeSummary(null), null);
};

scenarios.states = async () => {
  installWindow();
  const { talentEdgeBand } = await import(moduleUrl("ui/talent-edge.js"));
  assert.equal(talentEdgeBand({ ...DATA, talentEdge: undefined }), null, "an old lock has no block");
  const never = talentEdgeBand({ ...DATA, talentEdge: { available: false, failed: false, message: "Talent Edge for 2026 has not been worked out yet." } });
  document.body.append(never);
  assert.ok(text(never).includes("has not been worked out yet") && !never.querySelector(".te-spider"), "words, never an empty chart");
  const failed = talentEdgeBand({ ...DATA, talentEdge: { available: false, failed: true, message: "Talent Edge for 2026 is unavailable since 2026-11-01T06:02:00-05:00: CFBD data missing" } });
  assert.ok(failed.querySelector(".note--error") && text(failed).includes("unavailable since"), "a failure is an error panel");
  const stale = talentEdgeBand({ ...DATA, talentEdge: { ...DATA.talentEdge, lastFailure: { at: "2026-11-08T06:01:00-05:00", message: "CFBD down." } } });
  assert.ok(text(stale).includes("Not updated") && text(stale).includes("CFBD down."), "the last good numbers, labeled");
  const fcs = talentEdgeBand({ ...DATA, them: { school: "Campbell" }, talentEdge: { ...DATA.talentEdge, them: null, missing: ["Campbell"], cross: [] } });
  document.body.append(fcs);
  const words = text(fcs);
  assert.ok(!RAW.test(words), words.match(/.{0,40}(undefined|null|NaN|Infinity|object).{0,40}/)?.[0]);
  assert.ok(words.includes("Campbell is not an FBS team") && !fcs.querySelector(".te-unit") && !fcs.querySelector(".te-spider__them"));
  assert.ok(words.includes("Roster rating: FLA 11th of 138"));
  const missingUs = talentEdgeBand({ ...DATA, talentEdge: { ...DATA.talentEdge, us: null } });
  assert.ok(text(missingUs).includes("is not in this week's Talent Edge table"));
};

scenarios.placed = async () => {
  const program = (await import("node:fs")).readFileSync(new URL(moduleUrl("views/program.js")), "utf8");
  // the season as one line, Wave 2 (the owner's board of 2026-10-30): Talent Edge leads the Talent box, the sixth row
  assert.ok(/talentBox\(data\), \/\/ 6 Talent/.test(program) && program.includes("const te = edge ? talentEdgeParts(data) : null;"), "Talent Edge leads the Talent box");
  assert.ok(program.includes("talent: (data) => talentBox(data)") && program.includes('id: "program-talent"'), "a flyout of its own, the page's width");
  const cat = await import(moduleUrl("ui/band-catalog.js"));
  const ids = cat.bandsOf("program").map((b) => b.id);
  assert.equal(ids[ids.indexOf("program-leaders") + 1], "program-talent", "the catalog in the page's order: Talent under Leaders side by side");
  const { MENU } = await import(moduleUrl("ui/menu-tree.js"));
  const fresh = MENU.groups.find((g) => g.id === "new").items.find((e) => e.id === "new:program:program-talent");
  assert.ok(fresh && fresh.flyout === "program:talent", "in New, his testing list, opening the Talent box's flyout (the line, Wave 2)");
};
"""


@needs_node
@pytest.mark.parametrize("scenario", ["band", "states", "placed"])
def test_the_band_in_a_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)
