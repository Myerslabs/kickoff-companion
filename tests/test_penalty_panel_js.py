"""Phase 17 #21 in the fake browser: a play with a flag carries a button per foul after its text; a tap opens a
side panel with what the foul means, what it costs each side and a rule link into the rules book at its page.
Damaged fouls are skipped, a foul the book doesn't know still opens a panel, and a failed load says so."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fakedom import needs_node, run_scenario

SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object Object\]/;
const text = (node) => (node ? node.textContent : "");
const flush = async () => { for (let i = 0; i < 6; i += 1) await new Promise((resolve) => setImmediate(resolve)); };
const BOOK = { data: { source: { title: "2026 NCAA Football Rules Book", url: "https://example.org/rules.pdf" }, penalties: [
  { key: "holding", name: "Holding", aliases: ["holding"], what: "Grabbed an opponent.", calls: [{ who: "Offense", result: "10 yards", rule: "9-3-3", page: 111 }, { who: "Defense", result: "10 yards and an automatic first down", rule: "9-3-4", page: null }, null, "junk"] },
  null, "junk", { name: "No key" },
] } };

scenarios.flags = async () => {
  let calls = 0;
  globalThis.fetch = async (url) => { calls += 1; return { ok: true, status: 200, json: async () => BOOK }; };
  const { penaltyFlags, flagText } = await import(moduleUrl("ui/penalty-panel.js"));
  assert.equal(penaltyFlags({ penalties: [] }), null);
  assert.equal(penaltyFlags({}), null);
  assert.equal(penaltyFlags({ penalties: [null, "junk", { key: 5 }] }), null);
  const flags = penaltyFlags({ penalties: [{ key: "holding", name: "Holding", yards: 10, declined: false }, { key: "zorbing", name: "Zorbing", declined: true }, { key: "x" }] });
  document.body.append(flags);
  const buttons = flags.querySelectorAll("button");
  assert.deepEqual(buttons.map(text), ["Holding, 10 yards", "Zorbing, declined"]);
  assert.equal(flagText({ name: "Offside", offsetting: true }), "Offside, offsetting");
  assert.equal(flagText({ name: "Offside", yards: NaN }), "Offside");
  buttons[0].click();
  await flush();
  const sheet = document.querySelector(".side-sheet");
  const t = text(sheet);
  assert.ok(!RAW.test(t), t.slice(0, 300));
  assert.ok(t.includes("On this play: Holding, 10 yards.") && t.includes("Grabbed an opponent."));
  const links = sheet.querySelectorAll("a");
  assert.equal(links.length, 2);
  assert.equal(links[0].getAttribute("href"), "https://example.org/rules.pdf#page=111");
  assert.equal(links[1].getAttribute("href"), "https://example.org/rules.pdf", "no page: the book itself");
  assert.ok(t.includes("Rule 9-3-4") && t.includes("automatic first down"));
  // a foul the book doesn't know: the panel says so; the book was fetched once
  buttons[1].click();
  await flush();
  const sheets = document.querySelectorAll(".side-sheet");
  assert.ok(text(sheets[sheets.length - 1]).includes("No plain-words entry for this foul yet."));
  assert.equal(calls, 1, "the book loads once");
};

scenarios.failed = async () => {
  globalThis.fetch = async () => ({ ok: false, status: 500, json: async () => ({ errors: [{ message: "server down" }] }) });
  const { openPenaltyPanel } = await import(moduleUrl("ui/penalty-panel.js"));
  openPenaltyPanel({ key: "holding", name: "Holding" });
  await flush();
  const t = text(document.querySelector(".side-sheet"));
  assert.ok(t.includes("The rule did not load: server down"), t);
};

scenarios.log = async () => {
  globalThis.fetch = async () => ({ ok: true, status: 200, json: async () => BOOK });
  const { playLog } = await import(moduleUrl("ui/play-log.js"));
  const log = playLog({ plays: [{ id: "1", offense: "Us", period: 1, clock: { minutes: 10, seconds: 0 }, text: "PENALTY US Holding 10 yards", penalties: [{ key: "holding", name: "Holding", yards: 10 }] }, { id: "2", offense: "Them", text: "Rush for 3", penalties: null }], us: { name: "Us", abbr: "US" }, them: { name: "Them", abbr: "TH" } });
  document.body.append(log);
  assert.equal(log.querySelectorAll(".flag-chip").length, 1);
};
"""


@needs_node
@pytest.mark.parametrize("scenario", ["flags", "failed", "log"])
def test_penalty_panel_in_a_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)
