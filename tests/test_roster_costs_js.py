"""Phase 17 Part 3b in the fake browser: dollar amounts at a glance, the roster-costs band (total, positions,
players, sources, all marked rumored; an empty state that says where the load is run), and the costs row on the
Preseason page's loads. Tables wave 3: both tables size themselves (the group's short head, the player's surname at small,
the players' rumor note gone at small, a note column only where a row has one); the players sort, the groups keep their
order."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fakedom import needs_node, run_scenario

SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object Object\]/;
const text = (node) => (node ? node.textContent : "");

scenarios.money = async () => {
  const { fmtUsd, fmtStat } = await import(moduleUrl("ui/dom.js"));
  assert.deepEqual([20500000, 20000000, 850000, 1200, 2.4e9, 150e6, -5, NaN, null].map(fmtUsd), ["$20.5M", "$20M", "$850K", "$1,200", "$2.4B", "$150M", "–", "–", "–"]);
  assert.equal(fmtStat(4000000, "usd"), "$4M");
};

scenarios.band = async () => {
  const { costsBand } = await import(moduleUrl("ui/roster-costs.js"));
  const full = costsBand({ school: "Home U", totalUsd: 20500000, note: "Revenue sharing plus NIL", asOf: "2026-08-01", positions: [{ group: "Quarterbacks", amountUsd: 4000000 }, { group: "Line", amountUsd: null, note: "unknown" }, null], players: [{ name: "Star Passer", position: "QB", amountUsd: 2500000 }, { amountUsd: 3 }], sources: [{ label: "Report", url: "https://example.org/r" }, { label: "Paper" }] }, { team: "Home U" });
  document.body.append(full);
  const t = text(full);
  assert.ok(!RAW.test(t), t);
  assert.ok(t.includes("Roster costs (rumored)") && t.includes("Rumored total $20.5M") && t.includes("$20.5M total, rumored"));
  assert.ok(t.includes("Quarterbacks") && t.includes("$4M") && t.includes("Star Passer") && t.includes("$2.5M"));
  assert.ok(t.includes("Sources: Report, Paper"));
  const looked = costsBand({ school: "Away U", savedAt: "2026-08-02T00:00:00Z" }, { team: "Away U" });
  assert.ok(text(looked).includes("No figure was reported for Away U"));
  const none = costsBand(null);
  assert.ok(text(none).includes("Not loaded yet.") && none.querySelector('a[href="#prompts"]'), "the dead end leads to the Prompts page");
};

scenarios.sized = async () => {
  // wave 3: both tables size themselves by their own box
  const { groupsTable, playersTable } = await import(moduleUrl("ui/roster-costs.js"));
  const form = (node, which) => { const t = node.querySelector(`.sz-t--${which}`); return t ? t.textContent : text(node); };
  const marks = (ths) => ths.map((th) => (th.className.includes("st__min-large") ? "L" : th.className.includes("st__min-medium") ? "M" : ""));
  const groups = groupsTable([{ group: "Quarterbacks", amountUsd: 4000000, note: "Starter's reported deal" }, { group: "Line", amountUsd: -5 }, { group: " " }, null]);
  document.body.append(groups);
  assert.ok(!RAW.test(text(groups)), text(groups));
  assert.equal(groups.dataset.size, "large");
  const gh = groups.querySelectorAll("thead th");
  assert.deepEqual(gh.map((th) => th.dataset.term), ["Position group", "Amount", "Note"]);
  assert.equal(form(gh[0], "short"), "Group");
  assert.deepEqual(marks(gh), ["", "", ""], "the note wraps at every size: it never decides the size");
  assert.equal(gh.filter((th) => th.querySelector("button")).length, 0, "position groups keep the report's order");
  const g = groups.querySelectorAll("tbody tr");
  assert.equal(g.length, 2, "a blank group is left out");
  assert.deepEqual(g.map((tr) => text(tr.querySelectorAll("td")[1])), ["$4M", "–"], "usd, a negative figure is no figure");
  assert.ok(g[0].querySelectorAll("td")[2].className.includes("st__wrap"));
  const plain = groupsTable([{ group: "Quarterbacks", amountUsd: 1 }]);
  assert.deepEqual(plain.querySelectorAll("thead th").map((th) => th.dataset.term), ["Position group", "Amount"], "no notes: no note column");
  const players = playersTable([{ name: "Star Passer", position: "QB", amountUsd: 2500000, note: "On3 valuation" }, { name: "Big Tackle Jr.", position: null, amountUsd: 900000 }, { name: "Third Man", amountUsd: 3100000 }, { amountUsd: 3 }]);
  document.body.append(players);
  assert.ok(!RAW.test(text(players)), text(players));
  const ph = players.querySelectorAll("thead th");
  assert.deepEqual(ph.map((th) => th.dataset.term), ["Player", "Pos", "Amount", "Note"]);
  assert.deepEqual(marks(ph), ["", "", "", "M"], "a phone drops the rumor note (owner's call)");
  assert.ok(ph.slice(0, 3).every((th) => th.querySelector("button")) && !ph[3].querySelector("button"), "the players sort; the note keeps a plain head");
  const pr = players.querySelectorAll("tbody tr");
  assert.deepEqual(pr.map((tr) => pnText(tr.querySelectorAll("td")[0])), ["Third Man", "Star Passer", "Big Tackle Jr."], "the biggest figure first");
  assert.deepEqual(pr.map((tr) => pnText(tr.querySelectorAll("td")[0], "last")), ["Man", "Passer", "Tackle"], "item 6: the surname step (a suffix is not a name); the load's words shorten when they read cleanly");
  assert.equal(text(pr[2].querySelectorAll("td")[1]), "–");
  ph[0].querySelector("button").click();
  assert.equal(pnText(players.querySelectorAll("tbody tr")[0].querySelectorAll("td")[0]), "Big Tackle Jr.", "A to Z on a tap");
};

scenarios.loads = async () => {
  const { loadsBand } = await import(moduleUrl("views/preseason.js"));
  const node = loadsBand({ preseason: [], coaches: [{ conference: "Big Pie", schools: 2, saved: 2, savedAt: "2026-08-01T00:00:00Z" }], costs: [{ conference: "Big Pie", schools: 2, saved: 0, savedAt: null }], coachesSaved: 2, coachesOf: 2, costsSaved: 0 }, { commandFound: false }, () => {});
  document.body.append(node);
  const t = text(node);
  assert.ok(!RAW.test(t), t);
  assert.ok(t.includes("costs 0 of 2") && node.querySelector('a[href="#prompts"]'), "freeze wave F3: the counts and a link to Load data, where the batches live");
  assert.equal(node.getAttribute("data-collapsed"), "false", "a missing costs batch keeps the band open");
};
"""


@needs_node
@pytest.mark.parametrize("scenario", ["money", "band", "sized", "loads"])
def test_roster_costs_in_a_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)
