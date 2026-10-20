"""Phase 17 Part 3a in the fake browser: the Preseason page (the season loads with a row per batch, Copy the prompt
and Save, the Claude Code run's progress, a reminder; each primary team's outlook, moves, injuries, facts and staff;
damaged rows as dashes or left out), the team page's staff band, and the player card's age."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fakedom import needs_node, run_scenario

SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object Object\]/;
const text = (node) => (node ? node.textContent : "");
const clean = (label, node) => {
  const t = text(node);
  assert.ok(!RAW.test(t), `${label} printed ${JSON.stringify(t.slice(0, 400))}`);
  return t;
};
Object.getPrototypeOf(document.body).scrollIntoView = function () {};

const PAGE = {
  season: 2026,
  status: { season: 2026, remind: true, coachesSaved: 3, coachesOf: 16, preseason: [{ school: "Home U", savedAt: "2026-08-02T10:00:00Z", counts: { birthdates: 80, staff: 22 } }, { school: "Second U", savedAt: null, counts: null }, null], coaches: [{ conference: "Big Pie", schools: 16, saved: 3, savedAt: "2026-08-02T10:00:00Z" }, { conference: "Small Pie", schools: 12, saved: 0, savedAt: null }] },
  teams: [
    { school: "Home U", conference: "Big Pie", savedAt: "2026-08-02T10:00:00Z", author: "Test chat", coaches: { headCoach: "Coach A", offensiveCoordinator: "Coach B", defensiveCoordinator: null },
      preseason: { outlook: { summary: "A good year.", predictions: [{ title: "Poll", detail: "No. 20" }, { detail: "no title" }], storylines: [], positionBattles: null }, departures: [{ name: "Gone Guy", position: "WR", kind: "NFL draft", detail: "Round 2" }, { kind: "no name" }], arrivals: [], injuries: [{ name: "Hurt Guy", status: null }], programFacts: [{ title: "Tradition" }], staff: [{ name: "Coach A", role: "Head coach" }, { role: "nameless" }], sources: [{ label: "Roster", url: "https://example.org/r" }, { label: "No link" }] } },
    { school: "Second U", conference: "Small Pie", savedAt: null, coaches: null, preseason: null },
    null,
  ],
};

scenarios.page = async () => {
  installWindow();
  route("/api/preseason", () => envelope(clone(PAGE)));
  route("/api/season-notes/run", () => envelope({ commandFound: true, running: true, kind: "coaches", done: 1, of: 2, batches: [{ key: "Big Pie", state: "saved" }, { key: "Small Pie", state: "running", error: null }] }));
  route("/api/season-notes/prompt", () => envelope({ prompt: "THE PROMPT" }));
  const { createPreseasonView } = await import(moduleUrl("views/preseason.js"));
  const { clearEnvelopeCache } = await import(moduleUrl("views/common.js"));
  clearEnvelopeCache();
  const main = document.createElement("main");
  document.body.append(main);
  const view = createPreseasonView({});
  view.mount(main);
  await settle();
  await settle();
  const t = clean("preseason", main);
  assert.ok(t.includes("2026 preseason") && t.includes("isn't saved yet"), "the reminder");
  assert.ok(t.includes("preseason 1 of 2 teams") && t.includes("coaches 3 of 16") && t.includes("costs 0 of 16"));
  // freeze wave F3 (one fact, one source): the copy, paste and run of every batch live on the Load data page; this band counts and points
  assert.equal(main.querySelectorAll(".season-load__row").length, 0, "no batch rows here any more");
  assert.ok(t.includes("Preseason 1 of 2 primary teams") && t.includes("coaches 3 of 16 conferences"), t.slice(0, 400));
  assert.ok(main.querySelector('#preseason-loads a[href="#prompts"]'), "the band leads to Load data");
  assert.ok(t.includes("A good year.") && t.includes("Gone Guy (WR): NFL draft, Round 2") && t.includes("Hurt Guy: Status not reported"));
  assert.ok(t.includes("HC Coach A · OC Coach B") && !t.includes("DC "));
  assert.ok(t.includes("Not loaded yet. Copy the prompt"), "the team with no load says how");
  assert.equal(main.querySelectorAll(".preseason a").length >= 1, true);
  view.unmount();
};

scenarios.loads = async () => {
  // freeze wave F3: the loads band is a pointer to the Load data page, with the counts; no paste here
  const { loadsBand } = await import(moduleUrl("views/preseason.js"));
  const node = loadsBand({ preseason: [{ school: "Home U" }], coaches: [], season: 2026, remind: true }, { commandFound: false }, () => {});
  document.body.append(node);
  const t = clean("loads", node);
  assert.ok(t.includes("isn't saved yet") && t.includes("Preseason 0 of 1 primary teams"), t);
  assert.ok(node.querySelector('a[href="#prompts"]') && t.includes("Copy and paste each load there"), "Claude Code not found: copy and paste on Load data");
  assert.equal(node.querySelectorAll("button").filter((b) => /Copy|Paste|Run/.test(text(b))).length, 0, "no Copy, Paste or Run buttons here (the band's fold button stays)");
  const withClaude = loadsBand({ preseason: [], coaches: [] }, { commandFound: true }, () => {});
  assert.ok(text(withClaude).includes("Copy, paste or run each load there"));
};
"""


@needs_node
@pytest.mark.parametrize("scenario", ["page", "loads"])
def test_preseason_in_a_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)
