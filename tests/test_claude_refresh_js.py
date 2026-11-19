"""Run with Claude's row in the menu (batch 4 part 3, owner 2026-11-19: "add it in the top layer of the menu"): hidden until
the server says the page has Claude's writing to refresh, its line saying what, a tap starting the run; never for a guest;
a refused start said on the row and in a page note."""
from __future__ import annotations

import pytest

from tests.fakedom import needs_node, run_scenario

SCENARIOS = r"""
const settleRow = async () => { for (let i = 0; i < 6; i += 1) await Promise.resolve(); await advance(10); };

scenarios.shown = async () => {
  const { refreshRow } = await import(moduleUrl("ui/claude-refresh.js"));
  route("/api/refresh?", envelope({ available: true, running: false, label: "My Team", detail: "Refresh the coaches and roster costs" }));
  route("/api/refresh/run", envelope({ running: true }));
  route("/api/prompts/progress", envelope({ running: true, label: "The coaches" }));
  let started = null;
  const row = refreshRow({ route: "#season", onStart: (r) => { started = r; } });
  document.body.append(row);
  assert.ok(row.hasAttribute("hidden"), "hidden until the server answers");
  await settleRow();
  assert.ok(!row.hasAttribute("hidden"));
  assert.ok(row.textContent.includes("Run with Claude") && row.textContent.includes("Refresh the coaches and roster costs"), row.textContent);
  assert.equal(callsTo("/api/refresh?route=%23season"), 1, "the page's own address, encoded");
  row.click();
  await settleRow();
  assert.deepEqual(started, { ok: true, error: null });
  assert.equal(callsTo("/api/refresh/run"), 1);
  console.log("ok shown");
};

scenarios.hidden = async () => {
  const { refreshRow } = await import(moduleUrl("ui/claude-refresh.js"));
  route("/api/refresh?", envelope({ available: false, reason: "This Pre-Game was kept at kickoff." }));
  const row = refreshRow({ route: "#program=9" });
  await settleRow();
  assert.ok(row.hasAttribute("hidden"), "a closed window: no row");
  route("/api/refresh?", { status: 500, body: { errors: [] } });
  const broken = refreshRow({ route: "#season" });
  await settleRow();
  assert.ok(broken.hasAttribute("hidden"), "a server error: no row, never a crash");
  console.log("ok hidden");
};

scenarios.guest = async () => {
  document.body.dataset.role = "guest";
  const { refreshRow } = await import(moduleUrl("ui/claude-refresh.js"));
  route("/api/refresh?", envelope({ available: true, detail: "x" }));
  const row = refreshRow({ route: "#season" });
  await settleRow();
  assert.ok(row.hasAttribute("hidden"));
  assert.equal(callsTo("/api/refresh"), 0, "a guest never asks");
  console.log("ok guest");
};

scenarios.refused = async () => {
  const { refreshRow } = await import(moduleUrl("ui/claude-refresh.js"));
  route("/api/refresh?", envelope({ available: true, detail: "Refresh the trivia" }));
  route("/api/refresh/run", { status: 409, body: { data: null, errors: [{ code: "not_started", message: "busy" }] } });
  let started = null;
  const row = refreshRow({ route: "#trivia", onStart: (r) => { started = r; } });
  document.body.append(row);
  await settleRow();
  row.click();
  await settleRow();
  assert.equal(started.ok, false);
  assert.equal(row.disabled, false, "it can be tried again");
  assert.ok(!row.textContent.includes("undefined") && !row.textContent.includes("null"), row.textContent);
  console.log("ok refused");
};
"""


@needs_node
@pytest.mark.parametrize("scenario", ["shown", "hidden", "guest", "refused"])
def test_the_menu_row(tmp_path, scenario):
    run_scenario(tmp_path, SCENARIOS, scenario)
