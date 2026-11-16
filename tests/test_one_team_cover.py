"""The cover on one team (owner 2026-11-07: "Lets try a my team cover, and for the match-up or pregame program, its our
cover vs their cover?"): ui/cover.js draws our side alone with the page's own block where the opponent stood, every side
carries Elo, FPI and talent chips when the page hands them, the Magazine's front is our cover, and the Program's answer
carries each side's ratings. The phone bug of the same day (the Program wider than the screen) is tests/test_page_check_menu.py."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.conftest import FakeCfbd
from tests.fakedom import needs_node, run_scenario
from tests.test_program import route_program


def test_the_program_answer_carries_each_sides_ratings(client: TestClient, fake_cfbd: FakeCfbd):
    route_program(fake_cfbd)
    data = client.get("/api/program/next").json()["data"]
    for side in ("us", "them"):
        ratings = data[side]["ratings"]
        assert set(ratings) == {"elo", "fpi", "talent"}
        for key in ("elo", "fpi"):
            block = ratings[key]
            assert block is None or (isinstance(block["rank"], int) and block["metric"] == f"rating:{key}" and isinstance(block["rating"], (int, float)))
    assert isinstance(data["us"]["ratings"]["elo"]["rank"], int), "our Elo from the recorded table"


SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object Object\]/;
const text = (node) => (node ? node.textContent : "");

const US = {
  school: "Florida", abbreviation: "FLA", mascot: "Gators", conference: "SEC", logo: "/media/logo/57",
  record: { wins: 5, losses: 3 }, conferenceRecord: { wins: 3, losses: 3 }, apRank: 25,
  sp: { rating: 10.6, rank: 31, of: 138, metric: "rating:sp" },
  ratings: { elo: { rating: 1629, rank: 43, of: 136 }, fpi: { rating: 13.9, rank: 22, of: 136, metric: "rating:fpi" }, talent: { talent: 891, rank: 10, of: 138 }, junk: "x" },
  form: [{ gameId: 1, result: "W", points: 27, opponentPoints: 24, opponent: "Texas", homeAway: "away" }, { gameId: 2, result: "L", points: 8, opponentPoints: 27, opponent: "Georgia", homeAway: "neutral" }, "junk"],
};

scenarios.one = async () => {
  installWindow();
  await useTeam();
  const { cover } = await import(moduleUrl("ui/cover.js"));
  const middle = document.createElement("div");
  middle.className = "test-middle";
  middle.textContent = "the page's block";
  const extra = document.createElement("span");
  extra.textContent = "the foot's extra";
  const section = cover({ one: true, us: US, kicker: "My Team · SEC · Home team", label: "Florida: the season right now", middle, extra, prev: { href: "#season", label: "Florida" }, next: null });
  document.body.append(section);
  assert.ok(section.className.includes("cover--one") && !section.className.includes("cover--compact"));
  assert.equal(section.getAttribute("aria-label"), "Florida: the season right now");
  assert.equal(section.dataset.state, "one");
  const t = text(section);
  assert.ok(!RAW.test(t), t);
  assert.equal(section.querySelectorAll(".cover__side").length, 1, "our side alone");
  assert.equal(text(section.querySelector(".cover__name")), "Florida");
  const chips = section.querySelectorAll(".cover-chip").map(text);
  assert.deepEqual(chips, ["5-3", "3-3 conf", "SP+ #31", "Elo #43", "FPI #22", "Talent #10"], chips.join(" | "));
  assert.ok(section.querySelector(".poll-badge"), "the AP badge");
  assert.ok(section.querySelector(".form-guide"), "the last results");
  assert.ok(section.querySelector(".cover__center--one .test-middle"), "the page's block where the opponent stood");
  assert.equal(section.querySelector(".cover__line"), null, "no line of its own");
  assert.equal(section.querySelector(".cover__countdown"), null, "no countdown of its own");
  assert.ok(section.querySelector(".cover__staff--us") && text(section.querySelector(".cover__staff--us")) === "", "an empty staff slot the page fills");
  assert.equal(section.querySelector(".cover__when"), null, "no when line unless given");
  assert.ok(text(section.querySelector(".cover__foot")).includes("the foot's extra"));
  assert.equal(section.querySelector("a.cover__nav--prev").getAttribute("href"), "#season", "the kicker row's arrows without a rail");
  assert.ok(section.querySelector(".cover__nav--next.cover__nav--off"));
  assert.equal(section.tick(), "one");
  // the chips link to the national lists
  const elo = section.querySelectorAll(".cover-chip--link").find((a) => text(a) === "Elo #43");
  assert.ok(elo && elo.getAttribute("href").includes("rating%3Aelo") && elo.getAttribute("href").includes("team=Florida"), elo && elo.getAttribute("href"));
  // with a rail, no arrows; with words for the when line, the line
  const rail = document.createElement("div");
  rail.className = "rail-host";
  const two = cover({ one: true, us: US, rail, when: "Season 2026 · 12 games" });
  assert.ok(two.className.includes("cover--railed") && two.querySelector(".rail-host") && !two.querySelector(".cover__nav"));
  assert.equal(text(two.querySelector(".cover__when")), "Season 2026 · 12 games");
  assert.equal(text(two.querySelector(".cover__kicker")), "My Team", "the kicker's fallback");
  // damage: no team, junk ratings, a string middle
  const bare = cover({ one: true, us: null, middle: "not a node", actions: ["junk", null], extra: 7 });
  assert.ok(!RAW.test(text(bare)), text(bare));
  assert.equal(bare.querySelectorAll(".cover-chip").length, 0);
  // the two-team cover is unchanged in shape, with the new chips on each side
  const both = cover({ us: US, them: { ...US, school: "Oklahoma", abbreviation: "OU", apRank: null, ratings: { elo: { rank: 36 } } }, date: "2026-11-08T00:45:00Z", homeIsUs: true });
  assert.equal(both.querySelectorAll(".cover__side").length, 2);
  assert.ok(both.querySelector(".cover__center .cover__line") && !both.className.includes("cover--one"));
  assert.ok(both.querySelectorAll(".cover__side--them .cover-chip").map(text).includes("Elo #36"), "their side's chips too: our cover vs their cover");
};

scenarios.chips = async () => {
  // his "Keep All" (2026-11-07): more chips after the ratings from answers of their own (a rating, the Magazine's facts)
  await useTeam();
  const { cover, ratingChip, addSideChips } = await import(moduleUrl("ui/cover.js"));
  const sp = ratingChip("SP+", { value: 24.1, rank: 34, of: 138, href: "#season-numbers" });
  assert.equal(text(sp), "SP+ 24.1 #34");
  assert.equal(sp.tagName, "A");
  assert.ok(sp.className.includes("cover-chip--link") && sp.getAttribute("href") === "#season-numbers");
  assert.equal(text(ratingChip("All-time", { value: "771-459-40" })), "All-time 771-459-40");
  assert.equal(text(ratingChip("National titles", { value: 3 })), "National titles 3");
  assert.equal(text(ratingChip("Talent", { rank: 10, of: 138 })), "Talent #10");
  assert.equal(ratingChip("Nothing", {}), null, "nothing to say: no chip");
  assert.equal(ratingChip("", { value: NaN }), null);
  const section = cover({ one: true, us: US, middle: document.createElement("div") });
  assert.equal(addSideChips(section, "us", [sp, "junk", null, ratingChip("Blue chips", { value: "71%" })]), 2);
  const chips = section.querySelectorAll(".cover__side--us .cover-chip").map(text);
  assert.deepEqual(chips.slice(-2), ["SP+ 24.1 #34", "Blue chips 71%"], chips.join(" | "));
  assert.equal(addSideChips(section, "them", [sp]), 0, "no such side on a one-team cover");
  const bare = cover({ one: true, us: { school: "Nobody" }, middle: document.createElement("div") });
  addSideChips(bare, "us", [ratingChip("SP+", { value: 70 })]);
  assert.equal(text(bare.querySelector(".cover__rec")), "SP+ 70", "a side with no record keeps the chip alone");
};

scenarios.magazine = async () => {
  installWindow();
  await useTeam();
  const { magazineCover } = await import(moduleUrl("views/preseason.js"));
  const team = {
    school: "Florida", abbreviation: "FLA", mascot: "Gators", conference: "SEC", logo: "/media/logo/57", savedAt: "2026-10-08T21:21:43Z", author: "ChatGPT",
    coaches: { headCoach: "Jon Sumrall", offensiveCoordinator: "Buster Faulkner", defensiveCoordinator: "Brad White" },
    now: { overall: { wins: 5, losses: 3 }, conference: { wins: 3, losses: 3 }, apRank: 25, pace: "8-4", versus: "ahead" },
    preseason: { outlook: { predictedRecord: { overall: "7-5", conference: "4-4", source: "ESPN FPI" }, predictions: [{ title: "Preseason AP poll", detail: "unranked, 27th" }, "junk"] } },
  };
  const section = magazineCover(team, 2026);
  document.body.append(section);
  const t = text(section);
  assert.ok(!RAW.test(t), t);
  assert.ok(section.className.includes("cover--one") && section.className.includes("preseason-cover") && section.className.includes("flow-full"));
  assert.equal(text(section.querySelector(".cover__kicker")), "2026 Preseason Magazine · SEC");
  assert.ok(section.querySelector(".rail-host"), "the rail across the top");
  assert.equal(text(section.querySelector(".cover__name")), "Florida");
  assert.deepEqual(section.querySelectorAll(".cover-chip").map(text), ["5-3", "3-3 conf"], "the cost chip needs the load's figure; the facts' chips come with the program's answer");
  assert.ok(section.querySelector(".poll-badge"));
  assert.ok(t.includes("Predicted") && t.includes("7-5") && t.includes("So far") && t.includes("on pace for 8-4"), "the picks and where it stands in the middle");
  assert.ok(text(section.querySelector(".cover__staff--us")).includes("HC Jon Sumrall"));
  assert.ok(t.includes("written by ChatGPT") && /Loaded /.test(t));
  const shipped = magazineCover({ ...team, savedAt: null, author: null }, 2026);
  assert.ok(text(shipped).includes("Preloaded with the app"));
  const empty = magazineCover({ school: "Florida", preseason: null, now: null }, 2026);
  assert.ok(text(empty).includes("Not loaded yet") && !RAW.test(text(empty)), text(empty));
};
"""


@needs_node
@pytest.mark.parametrize("scenario", ["one", "chips", "magazine"])
def test_the_cover_on_one_team_in_the_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)
