"""Phase 17 #2 in the fake browser (tests/fakedom.py): the TV crew and the coaches from the game's notes, as
the Game program's header and the Live sheet's game line draw them, over full, partial and damaged notes
(no undefined, null or NaN; a missing name is left out)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fakedom import needs_node, run_scenario

SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object Object\]/;
const text = (node) => (node ? node.textContent : "");

scenarios.links = async () => {
  const { staffParts, staffLine } = await import(moduleUrl("ui/game-staff.js"));
  const { fillWiki } = await import(moduleUrl("ui/wiki-links.js"));
  const notes = { coaches: { us: { headCoach: "Ann Head", offensiveCoordinator: "Bo Offense", defensiveCoordinator: null }, them: { headCoach: "Dee Head" } } };
  const line = staffLine(notes, { usAbbr: "SWT", themAbbr: "BLUE", usSchool: "Swampwater Tech", themSchool: "Bluegrass Bottoms" });
  document.body.append(line);
  const links = line.querySelectorAll("a.wiki-link--coach");
  assert.deepEqual(links.map((a) => a.textContent), ["Ann Head", "Bo Offense", "Dee Head"], "every coach named is a link; a missing one is left out");
  assert.ok(links.every((a) => a.getAttribute("href").startsWith("https://en.wikipedia.org/w/index.php?search=")), "a search until the server answers, so a tap never dead-ends");
  assert.deepEqual(links.map((a) => a.dataset.team), ["Swampwater Tech", "Swampwater Tech", "Bluegrass Bottoms"]);
  assert.ok(text(line).includes("SWT HC Ann Head · OC Bo Offense") && text(line).includes("BLUE HC Dee Head"));
  // the server's answer points each link at the coach's own page
  const asked = [];
  globalThis.fetch = async (url) => {
    asked.push(String(url));
    return { ok: true, status: 200, json: async () => ({ data: { coaches: { "Ann Head|Swampwater Tech": { page: "https://en.wikipedia.org/wiki/Ann_Head" } } } }) };
  };
  await fillWiki(line);
  assert.ok(asked[0].includes("coach=Ann+Head%7CSwampwater+Tech") || asked[0].includes("coach=Ann%20Head%7CSwampwater%20Tech"), asked[0]);
  assert.equal(links[0].getAttribute("href"), "https://en.wikipedia.org/wiki/Ann_Head");
  assert.ok(links[1].getAttribute("href").includes("search="), "a coach the server has no page for keeps its search");
  assert.deepEqual(staffParts({}, "us", "X"), []);
  assert.deepEqual(staffParts(null, "them"), []);
};

scenarios.staff = async () => {
  const { crewText, staffText, staffLine } = await import(moduleUrl("ui/game-staff.js"));
  const { cover } = await import(moduleUrl("ui/cover.js"));
  const notes = {
    broadcast: { network: "ESPN", playByPlay: "Pat Caller", analyst: "Lee Analyst", sideline: ["Sam Sideline", "", null] },
    coaches: {
      us: { headCoach: "Ann Head", offensiveCoordinator: "Bo Offense", defensiveCoordinator: "Cy Defense" },
      them: { headCoach: "Dee Head", offensiveCoordinator: null, defensiveCoordinator: "  " },
    },
  };
  assert.equal(crewText(notes, { tv: "ABC" }), "ESPN: Pat Caller, Lee Analyst, Sam Sideline (sideline)");
  assert.equal(crewText({ broadcast: { playByPlay: "Pat Caller" } }, { tv: "ABC" }), "ABC: Pat Caller", "the network falls back to the game's TV");
  assert.equal(crewText({ broadcast: { network: "ESPN" } }, {}), null, "a network with no voices is no crew");
  assert.equal(staffText(notes, "us"), "HC Ann Head · OC Bo Offense · DC Cy Defense");
  assert.equal(staffText(notes, "them"), "HC Dee Head");
  const line = staffLine(notes, { usAbbr: "SWT", themAbbr: "DT" });
  assert.equal(text(line), "SWT HC Ann Head · OC Bo Offense · DC Cy Defense | DT HC Dee Head");
  for (const bad of [null, undefined, "junk", 7, [], { coaches: "x" }, { coaches: { us: [], them: 5 } }, { broadcast: { sideline: "x", playByPlay: 9 } }]) {
    assert.equal(staffLine(bad), null);
    assert.equal(crewText(bad, null), null);
  }
  // the program header: the crew joins the when line, the coaches sit under it
  const node = cover({ us: { school: "Swampwater Tech", abbreviation: "SWT" }, them: { school: "Diner Tech", abbreviation: "DT" }, date: "2026-10-10T16:45:00Z", venue: "Example Field", tv: "ABC", crew: crewText(notes, { tv: "ABC" }), details: line });
  assert.ok(text(node.querySelector(".cover__when")).includes("on ESPN: Pat Caller, Lee Analyst"));
  assert.ok(text(node.querySelector(".cover__details")).includes("DT HC Dee Head"));
  const plain = cover({ us: { school: "Swampwater Tech" }, them: { school: "Diner Tech" }, date: "2026-10-10T16:45:00Z", tv: "ABC", crew: "  ", details: "not a node" });
  assert.ok(text(plain.querySelector(".cover__when")).includes("on ABC") && !plain.querySelector(".cover__details"));
  assert.ok(!RAW.test(text(node)) && !RAW.test(text(plain)));
};
"""


@needs_node
@pytest.mark.parametrize("scenario", ["staff", "links"])
def test_game_staff_in_a_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)
