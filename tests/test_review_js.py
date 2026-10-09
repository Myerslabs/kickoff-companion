"""Phase 19 in the fake browser: Season in review (the facts from a schedule, every missing score skipped, nothing played)
and the game-notes panel."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fakedom import needs_node, run_scenario

SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object Object\]/;
const text = (node) => (node ? node.textContent : "");
const flush = async () => { for (let i = 0; i < 6; i += 1) await new Promise((resolve) => setImmediate(resolve)); };

const game = (id, date, result, us, them, school, extra = {}) => ({ gameId: id, date, completed: true, result, usPoints: us, themPoints: them, homeAway: "home", opponent: { school, apRank: null }, ...extra });
const SCHEDULE = [
  game(1, "2026-09-05T20:00:00Z", "W", 45, 10, "Alpha"),
  game(2, "2026-09-12T20:00:00Z", "W", 31, 28, "Bravo", { opponent: { school: "Bravo", apRank: 12 } }),
  game(3, "2026-09-19T20:00:00Z", "L", 14, 38, "Charlie", { homeAway: "away", opponent: { school: "Charlie", apRank: 3 } }),
  game(4, "2026-09-26T20:00:00Z", "W", 24, 17, "Delta"),
  game(5, "2026-10-03T20:00:00Z", "W", 20, 13, "Echo", { opponent: { school: "Echo", apRank: 20 } }),
  { gameId: 6, date: "2026-10-10T20:00:00Z", completed: false, result: null, usPoints: null, themPoints: null, opponent: { school: "Foxtrot" } },
  { gameId: 7, completed: true, result: "W", usPoints: null, themPoints: 3, opponent: { school: "Broken" } },
  null, "junk",
];

scenarios.facts = async () => {
  const { reviewFacts } = await import(moduleUrl("views/review.js"));
  const f = reviewFacts(SCHEDULE);
  assert.equal(f.games, 5, "an unplayed game, a game with no score and junk are skipped");
  assert.deepEqual([f.wins, f.losses, f.ties], [4, 1, 0]);
  assert.equal(f.pointsFor, 134);
  assert.equal(f.pointsAgainst, 106);
  assert.equal(Math.round(f.averageMargin * 10) / 10, 5.6);
  assert.equal(f.longestWin, 2);
  assert.equal(f.ending, "W2");
  assert.equal(f.bestWin.gameId, 1, "the biggest margin");
  assert.equal(f.hardestLoss.gameId, 3);
  assert.equal(f.bestRankedWin.gameId, 2, "the highest-ranked opponent beaten (#12 over #20)");
  assert.deepEqual(f.ranked, { games: 3, wins: 2 });
  assert.deepEqual(f.close, { games: 3, wins: 3 }, "31-28, 24-17 and 20-13");
  assert.deepEqual(reviewFacts([]), { games: 0 });
  assert.deepEqual(reviewFacts(null), { games: 0 });
  assert.equal(reviewFacts([game(1, "x", "L", 0, 7, "A")]).bestWin, null);
};

scenarios.body = async () => {
  const { reviewBody } = await import(moduleUrl("views/review.js"));
  const node = reviewBody({ schedule: SCHEDULE, record: { overall: { wins: 4, losses: 1, ties: 0 } } });
  document.body.append(node);
  const t = text(node);
  assert.ok(!RAW.test(t), t.slice(0, 500));
  assert.ok(t.includes("4-1") && t.includes("Best win"));
  assert.ok(t.includes("Alpha: W 45-10") && t.includes("at #3 Charlie: L 14-38"), t.slice(0, 700));
  assert.ok(t.includes("134 points scored and 106 allowed over 5 games"));
  assert.equal(node.querySelectorAll("tbody tr").length >= 5, true);
  const empty = text(reviewBody({ schedule: [] }));
  assert.ok(empty.includes("nothing to review") && !RAW.test(empty));
  assert.ok(!RAW.test(text(reviewBody(null))));
};

scenarios.notes = async () => {
  const { gameNotesPanel, periodWord } = await import(moduleUrl("ui/game-notes.js"));
  assert.deepEqual([1, 4, 5, 6, 0, null].map(periodWord), ["Q1", "Q4", "OT", "2OT", "", ""]);
  const db = [];
  const sent = [];
  globalThis.fetch = async (url, options = {}) => {
    sent.push({ url: String(url), method: options.method || "GET", body: options.body ? JSON.parse(options.body) : null });
    const respond = (status, data, errors) => ({ ok: status < 300, status, json: async () => ({ data, errors: errors || [] }) });
    if ((options.method || "GET") === "POST") {
      const body = JSON.parse(options.body);
      if (!String(body.text).trim()) return respond(422, null, [{ message: "Write something first." }]);
      db.push({ id: `n${db.length}`, at: "2026-10-10T20:00:00Z", text: body.text, ...(body.period ? { period: body.period, clock: body.clock, score: body.score } : {}) });
      return respond(200, { notes: db.slice() });
    }
    if ((options.method || "GET") === "DELETE") {
      const id = String(url).split("/").pop();
      const i = db.findIndex((n) => n.id === id);
      if (i < 0) return respond(404, null, [{ message: "No such note." }]);
      db.splice(i, 1);
      return respond(200, { notes: db.slice() });
    }
    return respond(200, { notes: db.slice() });
  };
  const host = gameNotesPanel({ gameId: 526001015, getContext: () => ({ period: 2, clock: "8:41", score: "SWT 7, OPP 3" }) });
  document.body.append(host);
  await flush();
  assert.ok(text(host).includes("No notes for this game yet."));
  const [input] = host.querySelectorAll("textarea");
  const add = host.querySelectorAll("button").find((b) => text(b) === "Add the note");
  add.click();
  await flush();
  assert.ok(text(host).includes("Write something first."));
  input.value = "Watch the left tackle";
  add.click();
  await flush();
  assert.deepEqual(sent.find((s) => s.method === "POST").body, { text: "Watch the left tackle", period: 2, clock: "8:41", score: "SWT 7, OPP 3" });
  const t = text(host);
  assert.ok(t.includes("Q2 · 8:41 · SWT 7, OPP 3") && t.includes("Watch the left tackle") && !RAW.test(t), t);
  assert.equal(input.value, "");
  host.querySelectorAll("button").find((b) => text(b) === "Remove").click();
  await flush();
  assert.ok(text(host).includes("No notes for this game yet."));
  assert.equal(gameNotesPanel({ gameId: null }).childNodes.length, 0);
};
"""


@needs_node
@pytest.mark.parametrize("scenario", ["facts", "body", "notes"])
def test_review_and_notes_in_a_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)
