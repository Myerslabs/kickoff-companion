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
  assert.equal(main.querySelectorAll(".season-load__row").length, 5, "the one-paste row, two teams and two conferences; the damaged row is left out");
  assert.ok(t.includes("Show each conference (2, 1 not loaded)"), "the conferences sit behind one button");
  assert.ok(t.includes("Not loaded") && t.includes("80 birthdates, 22 staff"));
  assert.ok(t.includes("Claude Code is working: 1 of 2 done") && t.includes("Small Pie: running"));
  assert.ok(t.includes("A good year.") && t.includes("Gone Guy (WR): NFL draft, Round 2") && t.includes("Hurt Guy: Status not reported"));
  assert.ok(t.includes("HC Coach A · OC Coach B") && !t.includes("DC "));
  assert.ok(t.includes("Not loaded yet. Copy the prompt"), "the team with no load says how");
  assert.equal(main.querySelectorAll(".preseason a").length >= 1, true);
  view.unmount();
};

scenarios.save = async () => {
  const sent = [];
  globalThis.fetch = async (url, options = {}) => {
    sent.push({ url: String(url), body: options.body ? JSON.parse(options.body) : null });
    if (String(url).startsWith("/api/season-notes/save")) {
      const body = JSON.parse(options.body);
      if (body.text.includes("bad")) return { ok: false, status: 422, json: async () => ({ errors: [{ message: "The answer lists no teams." }] }) };
      return { ok: true, status: 200, json: async () => ({ data: { saved: true, warnings: ["No staff for X."] } }) };
    }
    return { ok: true, status: 200, json: async () => ({ data: { prompt: "P" } }) };
  };
  const { loadsBand } = await import(moduleUrl("views/preseason.js"));
  let changed = 0;
  const node = loadsBand({ preseason: [{ school: "Home U" }], coaches: [] }, { commandFound: false }, () => { changed += 1; });
  document.body.append(node);
  const clip = { text: "", wrote: null, canRead: true };
  Object.defineProperty(globalThis, "navigator", { configurable: true, value: { clipboard: { readText: async () => { if (!clip.canRead) throw new Error("no"); return clip.text; }, writeText: async (v) => { clip.wrote = v; } } } });
  const [copy, paste] = node.querySelectorAll(".season-load__row button");
  assert.equal(text(copy), "Copy the prompt");
  assert.equal(text(paste), "Paste the answer");
  assert.equal(node.querySelectorAll("textarea").filter((b) => b.getAttribute("hidden") === null).length, 0, "no text box is open: the prompt is never shown, the paste needs no box");
  paste.click();
  await settle();
  assert.ok(text(node).includes("There is nothing to paste yet"));
  clip.text = "bad answer";
  paste.click();
  await settle();
  assert.ok(text(node).includes("Not saved. The answer lists no teams."), text(node).slice(-200));
  clip.text = "good answer";
  paste.click();
  await settle();
  assert.ok(text(node).includes("Saved, with 1 note.") && text(node).includes("No staff for X.") && changed === 1);
  assert.deepEqual(sent.filter((s) => s.body).map((s) => s.body.kind), ["season", "season"]);
  copy.click();
  await settle();
  assert.ok(sent.some((s) => s.url.startsWith("/api/season-notes/prompt?kind=season&key=all")));
  assert.equal(clip.wrote, "P", "the prompt went to the clipboard");
  assert.ok(node.querySelectorAll("textarea").every((b) => b.getAttribute("hidden") !== null), "and was never shown");
  // a browser that will not let the page read the clipboard (plain HTTP): one small box opens, and a paste into it saves by itself
  clip.canRead = false;
  const before = sent.filter((s) => s.body).length;
  paste.click();
  await settle();
  const box = node.querySelectorAll("textarea").find((b) => b.getAttribute("hidden") === null);
  assert.ok(box && text(node).includes("Press and hold in the box"));
  box.dispatchEvent({ type: "paste", clipboardData: { getData: () => "a pasted answer" }, preventDefault() {} });
  await settle();
  assert.equal(sent.filter((s) => s.body).length, before + 1, "saved without another tap");
  assert.ok(text(node).includes("Claude Code isn't installed"));
};
"""


@needs_node
@pytest.mark.parametrize("scenario", ["page", "save"])
def test_preseason_in_a_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)
