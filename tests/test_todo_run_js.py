"""Post-freeze Wave 1 (owner 2026-10-25): the To do's items each get Run (where Claude Code is found) and Open, and a short
roster-costs list says it is partial; in the fake browser (tests/fakedom.py)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fakedom import needs_node, run_scenario

SCENARIOS = r"""
const text = (node) => (node ? node.textContent : "");

scenarios.run = async () => {
  const { readinessList } = await import(moduleUrl("ui/readiness.js"));
  const posted = [];
  route("/api/notes/run", (url) => { posted.push(String(url)); return envelope({ running: true }); });
  route("/api/prompts/run", (url) => { posted.push(String(url)); return envelope({ running: true }); });
  const items = [
    { id: "season", title: "The 2026 season load", detail: "Not loaded: coaches.", href: "#prompts", run: { kind: "prompts" }, canRun: true },
    { id: "notes", title: "This week's notes, Diner Tech", detail: "Missing: both depth charts.", href: "#prompts", run: { kind: "notes", gameId: 41, parts: ["lineups"] }, canRun: true },
    { id: "costs", title: "Roster costs", detail: "Rumored costs for 18 of 136 teams.", href: "#prompts", run: { kind: "prompts" }, canRun: false },
    { id: "odd", title: "Odd", detail: "No run here.", href: "#prompts", run: { kind: "nonsense" }, canRun: true },
  ];
  const list = readinessList(items);
  document.body.append(list);
  const rows = list.querySelectorAll(".readiness__item");
  const labels = (row) => row.querySelectorAll("button, a").map((b) => text(b));
  assert.deepEqual(labels(rows[0]), ["Run with Claude", "Open Load data"], "Run beside Open");
  assert.deepEqual(labels(rows[2]), ["Open Load data"], "no Claude Code on the server: Open only");
  assert.deepEqual(labels(rows[3]), ["Open Load data"], "an unknown run is no button");
  rows[1].querySelector("button").click();
  await settle();
  assert.ok(posted.some((u) => u.startsWith("/api/notes/run")), posted.join(" "));
  assert.ok(text(rows[1]).includes("in the background"));
  rows[0].querySelector("button").click();
  await settle();
  assert.ok(posted.some((u) => u.startsWith("/api/prompts/run")));
  route("/api/notes/run", () => ({ status: 409, body: { data: null, errors: [{ message: "a run for game 40 is still going" }] } }));
  const again = readinessList([items[1]]);
  document.body.append(again);
  again.querySelector("button").click();
  await settle();
  assert.ok(text(again).includes("a run for game 40 is still going") && text(again.querySelector("button")) === "Run with Claude", "a refusal is said and the button comes back");
};

scenarios.partWithoutClaude = async () => {
  // no Claude Code on the server: Copy and Paste only, and no Run drawn at all (a hidden button still showed under .btn)
  route("/api/notes/run", () => envelope({ running: false, commandFound: false }));
  const { partLoad, forgetCommand } = await import(moduleUrl("ui/part-load.js"));
  forgetCommand();
  const block = partLoad({ gameId: 41, parts: ["visitors"], lead: "No visitor list for this game yet.", detail: "It comes from the recruiting sites." });
  document.body.append(block);
  await settle();
  const labels = block.querySelectorAll("button").map((b) => text(b));
  assert.ok(labels.includes("Copy the prompt") && labels.includes("Paste the answer") && !labels.includes("Run with Claude"), labels.join(", "));
  const later = partLoad({ gameId: 41, parts: ["availability"], lead: "No availability report for this game yet.", detail: "It comes from the report.", due: { due: false, from: "2026-10-29T23:00:00Z" } });
  assert.equal(later.querySelectorAll("button").length, 0, "not published yet: nothing to press");
  assert.ok(text(later).includes("It is published from"));
};

scenarios.costs = async () => {
  const { costsBand } = await import(moduleUrl("ui/roster-costs.js"));
  const few = costsBand({ school: "Swampwater Tech", totalUsd: 31000000, players: [{ name: "A Passer", position: "QB", amountUsd: 1800000 }, { name: "B Runner", position: "RB", amountUsd: 1300000 }, { name: "C Rusher", position: "EDGE", amountUsd: 1100000 }] });
  document.body.append(few);
  assert.ok(text(few).includes("A rumored figure was reported for 3 players; the rest of the roster has none."), text(few));
  assert.equal(few.querySelector(".costs__partial a").getAttribute("href"), "#prompts");
  const many = costsBand({ school: "Swampwater Tech", totalUsd: 31000000, players: Array.from({ length: 30 }, (_, i) => ({ name: `Player ${i}`, position: "WR", amountUsd: 100000 })) });
  assert.equal(many.querySelector(".costs__partial"), null, "a full list says nothing more");
};
"""


@needs_node
@pytest.mark.parametrize("scenario", ["run", "partWithoutClaude", "costs"])
def test_todo_run_and_costs_in_a_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)
