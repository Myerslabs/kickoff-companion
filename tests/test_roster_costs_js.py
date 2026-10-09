"""Phase 17 Part 3b in the fake browser: dollar amounts at a glance, the roster-costs band (total, positions,
players, sources, all marked rumored; an empty state that says where the load is run), and the costs row on the
Preseason page's loads."""

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
  assert.ok(text(none).includes("Not loaded yet.") && none.querySelector('a[href="#preseason"]'));
};

scenarios.loads = async () => {
  const { loadsBand } = await import(moduleUrl("views/preseason.js"));
  const node = loadsBand({ preseason: [], coaches: [{ conference: "Big Pie", schools: 2, saved: 2, savedAt: "2026-08-01T00:00:00Z" }], costs: [{ conference: "Big Pie", schools: 2, saved: 0, savedAt: null }], coachesSaved: 2, coachesOf: 2, costsSaved: 0 }, { commandFound: false }, () => {});
  document.body.append(node);
  const t = text(node);
  assert.ok(!RAW.test(t), t);
  assert.ok(t.includes("Roster costs, one batch per conference") && t.includes("costs 0 of 2"));
  assert.equal(node.getAttribute("data-collapsed"), "false", "a missing costs batch keeps the band open");
};
"""


@needs_node
@pytest.mark.parametrize("scenario", ["money", "band", "loads"])
def test_roster_costs_in_a_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)
