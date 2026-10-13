"""Phase 19 in the fake browser: Season in review (the facts from a schedule, every missing score skipped, nothing played;
tables wave 3: its three sized tables) and the game-notes panel."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fakedom import needs_node, run_scenario

SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object Object\]/;
const text = (node) => (node ? node.textContent : "");
const cls = (node) => String(node.getAttribute("class") || "");
const form = (cell, which) => { const t = cell.querySelector(`.sz-t--${which}`); return t ? t.textContent : text(cell); }; // a sized table's words
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
  const { reviewBody, reviewGameRow } = await import(moduleUrl("views/review.js"));
  const node = reviewBody({ schedule: SCHEDULE, record: { overall: { wins: 4, losses: 1, ties: 0 } }, polls: [{ poll: "AP" }, null] });
  document.body.append(node);
  const t = text(node);
  assert.ok(!RAW.test(t), t.slice(0, 500));
  assert.ok(t.includes("4-1") && t.includes("Best win"));
  assert.ok(t.includes("134 points scored and 106 allowed over 5 games"));
  assert.equal(node.querySelectorAll("tbody tr").length >= 5, true);
  // tables wave 3 (rule 3): the season in a few lines is two sized tables, every data point in its own column
  const wraps = node.querySelectorAll(".stat-table-wrap");
  assert.equal(wraps.length, 3, "the games that stood out, the splits, every game");
  assert.ok(wraps.every((w) => w.dataset.size === "large"), "each table sizes itself");
  assert.ok(wraps.slice(0, 2).every((w) => w.closest(".score-words")), "the facts keep the spoiler blur");
  const heads = (wrap) => [...wrap.querySelectorAll("thead th")];
  const words = (wrap, which) => heads(wrap).map((th) => form(th, which));
  assert.deepEqual(words(wraps[0], "long"), ["Fact", "Site", "AP rank", "Opponent", "Result", "Date"]);
  assert.deepEqual(words(wraps[0], "mid"), ["Fact", "Site", "AP", "Opponent", "Result", "Date"]);
  assert.ok(cls(heads(wraps[0])[2]).includes("st__min-medium") && cls(heads(wraps[0])[5]).includes("st__min-large"), "the AP rank from medium, the date at large");
  assert.deepEqual(words(wraps[1], "long"), ["Fact", "Value"]);
  assert.ok(!wraps[0].querySelector("thead button") && !wraps[1].querySelector("thead button"), "the facts keep their written order");
  const cells = (wrap, i) => [...wrap.querySelectorAll("tbody tr")[i].querySelectorAll("td")];
  const loss = cells(wraps[0], 2);
  assert.deepEqual([form(loss[0], "long"), form(loss[1], "long"), form(loss[1], "short"), text(loss[2]), text(loss[3]), text(loss[4]), text(loss[5])], ["Hardest loss", "Away", "A", "#3", "Charlie", "L 14-38", "Sep 19"]);
  assert.ok(loss[2].querySelector(".poll-badge") && loss[3].querySelector(".team-link") && loss[4].querySelector(".res--l"), "the poll's badge, the team's link, the result's color");
  assert.deepEqual([form(cells(wraps[0], 1)[0], "mid"), form(cells(wraps[0], 1)[0], "short")], ["Best ranked win", "Ranked win"], "the facts' shorter words below large");
  assert.equal(text(cells(wraps[0], 0)[2]), "NR", "an unranked opponent in a loaded poll");
  const split = wraps[1].querySelectorAll("tbody tr").map((tr) => tr.querySelectorAll("td").map((td) => form(td, "long")));
  assert.deepEqual(split, [["Against ranked teams", "2-1"], ["Games decided by 8 or fewer", "3-0"], ["Longest winning streak", "2 games"], ["Current streak", "W2"]], "a game still to play: the current streak");
  wraps[0].querySelectorAll("tbody tr")[2].click();
  assert.equal(window.location.hash, "box=3", "a game that stood out opens its box score");
  // every game: the season's order first; the result sorts by its margin, the date by its day
  const games = wraps[2];
  assert.deepEqual(words(games, "long"), ["#", "Date", "Wk", "Site", "AP rank", "Opponent", "Result", "Margin"]);
  assert.deepEqual(heads(games).map((th) => ["st__min-medium", "st__min-large"].find((c) => cls(th).includes(c)) || ""), ["st__min-medium", "st__min-large", "st__min-large", "", "st__min-medium", "", "", ""]);
  assert.equal(heads(games)[0].getAttribute("aria-sort"), "ascending");
  const order = () => games.querySelectorAll("tbody tr").map((tr) => text(tr.querySelectorAll("td")[5]));
  assert.deepEqual(order(), ["Alpha", "Bravo", "Charlie", "Delta", "Echo"]);
  heads(games)[6].querySelector("button").click();
  assert.deepEqual(order(), ["Alpha", "Delta", "Echo", "Bravo", "Charlie"], "the result sorts by its margin, the biggest win first");
  heads(games)[1].querySelector("button").click();
  assert.deepEqual(order(), ["Echo", "Delta", "Charlie", "Bravo", "Alpha"], "the date sorts by its day, the latest first");
  assert.ok(games.querySelectorAll(".score-words").length === 5, "every margin keeps the spoiler blur");
  // no poll loaded: an unranked opponent is a dash, never NR; the season over: the run it ended on
  const over = reviewBody({ schedule: SCHEDULE.filter((g) => g && g.gameId !== 6) });
  const [first, splits] = over.querySelectorAll(".stat-table-wrap");
  assert.equal(text(first.querySelectorAll("tbody tr")[0].querySelectorAll("td")[2]), "\u2013");
  assert.equal(form(splits.querySelectorAll("tbody tr")[3].querySelector("td"), "long"), "The season ended on");
  // a row from a damaged game never prints a raw value
  for (const junk of [null, "x", { opponent: "x", result: "W", usPoints: "7" }, { opponent: { school: 4, apRank: "1" }, homeAway: "moon" }]) {
    const row = reviewGameRow(junk, 1);
    assert.ok(!RAW.test(JSON.stringify([row.site, row.result, row.dateText])) && row.margin === null && row.apRank === null, JSON.stringify(row));
  }
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
