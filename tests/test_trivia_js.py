"""The trivia in the fake browser (owner 2026-10-21): the two popups and the join card (ui/trivia.js), the Trivia page's
pieces (views/trivia.js), and the boot flow: the join note on a game day, the question after a join, a pick that closes
it, the standings between questions, and nothing at all for a tablet that said Not today."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fakedom import needs_node, run_scenario

SCENARIOS = r"""
const DAY = { date: "2026-10-24", startedAt: "2026-10-24T15:40:00-04:00", endedAt: null, endedBy: null, asked: 3, playing: 2, next: "Next at 7:27 pm", context: "pre" };
const QUESTION = { id: "2026-10-24-3", n: 3, kind: "stadium", school: "Diner Tech", text: "Where does Diner Tech play its home games?", choices: ["Griddle Field", "The Skillet", "Biscuit Bowl"], askedAt: "2026-10-24T16:10:00-04:00", closesAt: new Date(Date.now() + 38000).toISOString(), secondsLeft: 38, context: "pre", period: null, open: true, yourPick: null };
const STANDINGS = [{ rank: 1, name: "Nana's Nachos", today: [2, 2], season: [16, 22], you: false }, { rank: 2, name: "Couch Coordinators", today: [1, 2], season: [14, 22], you: true }];
const RAW = /(undefined|null|NaN|Infinity)|\[object Object\]/;
const clean = (label, node) => {
  const t = node ? node.textContent : "";
  assert.ok(!RAW.test(t), `${label} printed ${JSON.stringify(t.slice(0, 400))}`);
  return t;
};
const base = (extra = {}) => ({ on: true, board: true, pace: "15", gameDay: true, ourGame: { home: "Home U", away: "Diner Tech", opponent: "Diner Tech" }, serverNow: new Date(Date.now()).toISOString(), day: DAY, team: null, question: null, standings: STANDINGS, ...extra });

scenarios.popups = async () => {
  const { questionPopup, standingsPopup, joinCard } = await import(moduleUrl("ui/trivia.js"));
  const picks = [];
  const q = questionPopup(base({ team: { name: "Couch Coordinators", joined: true }, question: QUESTION }), { onPick: (i) => picks.push(i) });
  document.body.append(q);
  const t = clean("question popup", q);
  assert.ok(t.includes("Where does Diner Tech play") && t.includes("Griddle Field") && t.includes("Playing as Couch Coordinators") && /Closes in 3\d s/.test(t), t);
  assert.ok(!t.includes("right answer") && !t.includes("answer:"), "the popup never carries the answer");
  assert.equal(q.querySelectorAll("button.trivia-pop__choice").length, 3);
  q.querySelectorAll("button.trivia-pop__choice")[1].click();
  assert.deepEqual(picks, [1]);
  const b = questionPopup(base({ question: QUESTION }), { board: true });
  assert.equal(b.querySelectorAll("button").length, 0, "the board has no buttons");
  assert.ok(clean("board question", b).includes("Answer on your tablet"));
  const s = standingsPopup(base({ team: { name: "Couch Coordinators", joined: true } }), { welcome: "Welcome back, Couch Coordinators: 13 of 20 this season before today" });
  const st = clean("standings popup", s);
  assert.ok(st.includes("2 playing") && st.includes("3 asked") && st.includes("1 Nana's Nachos") && st.includes("16 of 22") && st.includes("Welcome back") && st.includes("Next at 7:27 pm"), st);
  assert.equal(s.querySelectorAll("tr.is-you").length, 1);
  const empty = standingsPopup(base({ standings: [], day: { ...DAY, playing: 0 } }));
  assert.ok(clean("empty standings", empty).includes("Nobody on the board yet"));
  clean("junk popups", questionPopup({ question: { choices: "junk", text: 5 } }, {}));
  clean("junk standings", standingsPopup({ standings: "junk", day: 7 }, {}));
  const joined = [];
  const card = joinCard(base(), { onJoin: (d) => joined.push(d) });
  const jt = clean("join card", card);
  assert.ok(jt.includes("Names are case sensitive") && card.querySelector("input") && jt.includes("Not today"));
};

scenarios.page = async () => {
  const { scoreCells, boardTable, questionCard, seasonTable, rulesBand } = await import(moduleUrl("views/trivia.js"));
  const data = base({
    team: { name: "Couch Coordinators", joined: true, today: [1, 2], season: [14, 22], firstDay: "2026-09-05" },
    best: { date: "2026-09-05", right: 4, asked: 4, our: { opponent: "Crabtown" } },
    board: [{ rank: 1, name: "Nana's Nachos", today: [2, 2], season: [16, 22], you: false, here: true }, { rank: 2, name: "Couch Coordinators", today: [1, 2], season: [14, 22], you: true, here: true }, { rank: 3, name: "The Bye Week", today: null, season: [7, 14], you: false, here: false }],
    questions: [
      { ...QUESTION, open: false, answer: 1, fact: "The Skillet, since 1948.", answered: 3, yourPick: 0, checkedAt: "2026-10-21" },
      { ...QUESTION, id: "2026-10-24-4", n: 4, open: true, yourPick: null, period: 3, context: "game" },
    ],
    seasonTable: [{ date: "2026-09-05", our: { home: "Home U", away: "Crabtown" }, span: "11:30 am to 11:10 pm", right: 4, asked: 4, running: false }, { date: "2026-10-24", our: { home: "Home U", away: "Diner Tech" }, span: "since 3:40 pm", right: 1, asked: 2, running: true }],
    teamsThisSeason: 3,
  });
  const cells = clean("score cells", scoreCells(data));
  assert.ok(cells.includes("1 of 2") && cells.includes("14 of 22") && cells.includes("4 of 4") && cells.includes("Crabtown"), cells);
  const board = boardTable(data);
  const bt = clean("board table", board);
  assert.ok(bt.includes("Nana's Nachos") && bt.includes("this tablet") && bt.includes("not here today") && bt.includes("7 of 14"), bt);
  assert.equal(board.querySelectorAll("tr.is-you").length, 1);
  const marked = [];
  const card = questionCard(data.questions[0], data, { onMark: async (id) => marked.push(id) });
  const ct = clean("closed card", card);
  assert.ok(ct.startsWith("Wrong") && ct.includes("right answer") && ct.includes("your pick") && ct.includes("3 of 2 teams answered") && ct.includes("The Skillet, since 1948") && ct.includes("Diner Tech's facts, checked"), ct);
  card.querySelector(".trivia-card__mark").click();
  await settle();
  assert.deepEqual(marked, ["2026-10-24-3"]);
  const open = clean("open card", questionCard(data.questions[1], data));
  assert.ok(open.startsWith("Open") && open.includes("3rd quarter") && !open.includes("right answer") && open.includes("the answer shows here once it closes"), open);
  const season = clean("season table", seasonTable(data));
  assert.ok(season.includes("Crabtown at Home U") && season.includes("11:30 am to 11:10 pm") && season.includes("1 of 2 so far") && season.includes("14 of 22"), season);
  assert.ok(clean("empty season", seasonTable({})).includes("No game day played"));
  assert.ok(clean("empty board", boardTable({ board: [] })).includes("Nobody on the board yet"));
  assert.ok(clean("rules", rulesBand()).includes("case sensitive"));
  clean("junk card", questionCard("junk", null));
  clean("junk cells", scoreCells({ team: "junk", best: 5, day: "x" }));

  // the layout pass (owner 2026-10-22, "Ok" to the picks): the join card on game days only, Your score beside the
  // Leaderboard, How it plays folded
  installWindow();
  const { createTriviaView } = await import(moduleUrl("views/trivia.js"));
  const { clearEnvelopeCache } = await import(moduleUrl("views/common.js"));
  const mountWith = async (answer) => {
    clearEnvelopeCache();
    route("/api/trivia", () => envelope(answer));
    const main = document.createElement("main");
    document.body.append(main);
    const view = createTriviaView({});
    view.mount(main);
    await settle();
    return { main, view };
  };
  const gameDay = await mountWith(base({ questions: [], seasonTable: [] }));
  clean("game-day page", gameDay.main);
  assert.ok(gameDay.main.querySelector(".trivia-head .trivia-join"), "a game day, not joined: the join card");
  const twin = gameDay.main.querySelector(".trivia-pair");
  assert.ok(twin && twin.querySelector("#trivia-score") && twin.querySelector("#trivia-board"), "Your score beside the Leaderboard");
  assert.equal(gameDay.main.querySelector("#trivia-rules").getAttribute("data-collapsed"), "true", "How it plays folded");
  gameDay.view.unmount();
  const quiet = await mountWith(base({ gameDay: false, day: null, questions: [], seasonTable: [] }));
  assert.equal(quiet.main.querySelector(".trivia-head .trivia-join"), null, "another day: no join card");
  quiet.main.querySelector(".trivia-head__anyway").click();
  assert.ok(quiet.main.querySelector(".trivia-head .trivia-join"), "Start trivia anyway brings it");
  quiet.view.unmount();
};

scenarios.flow = async () => {
  installWindow();
  const { startTrivia, teamName, rememberName, forgetName, declineToday, POLL_MS } = await import(moduleUrl("ui/trivia.js"));
  const { noteCount } = await import(moduleUrl("ui/page-notes.js"));
  const joinUp = () => { const pop = document.querySelector(".trivia-pop"); return Boolean(pop && !pop.hasAttribute("hidden") && pop.querySelector(".trivia-pop__card--join")); };
  forgetName();
  let server = base();
  const posts = [];
  route("/api/trivia/now", () => envelope(server));
  route("/api/trivia/join", () => { posts.push("join"); server = base({ team: { name: "Couch Coordinators", joined: true, today: [0, 0], season: [0, 0] }, question: QUESTION }); return envelope({ name: "Couch Coordinators", new: true, welcome: null }); });
  route("/api/trivia/answer", () => { posts.push("answer"); server = base({ team: { name: "Couch Coordinators", joined: true, today: [0, 0], season: [0, 0] }, question: { ...QUESTION, yourPick: 1 } }); return envelope({ ok: true }); });
  const slot = document.createElement("div");
  slot.className = "page-notes";
  document.body.append(slot);
  window.location.hash = "#program";
  await startTrivia();
  await settle();
  // the layout pass (owner 2026-10-22): the join is the corner popup on every page, never an item of the To do
  assert.ok(joinUp(), "a game day and no name: the join popup in the corner of the Pre-Game Program");
  assert.equal(noteCount(), 0, "the To do has no trivia item");
  // Not today: the popup goes and nothing else shows
  document.querySelector(".trivia-join__decline").click();
  await settle();
  assert.ok(!joinUp() && document.querySelector(".trivia-pop").hasAttribute("hidden"));
  // the next day the tablet joins from the popup
  forgetName();
  localStorage.removeItem("trivia.declined");
  await advance(POLL_MS * 2);
  await settle();
  server = base();
  await advance(5 * 60 * 1000 + 10);
  await settle();
  assert.ok(joinUp(), "asked again on a day it did not decline");
  const input = document.querySelector(".trivia-join input");
  input.value = "Couch Coordinators";
  document.querySelector(".trivia-join__join").click();
  await settle();
  await advance(POLL_MS + 10);
  await settle();
  assert.deepEqual(posts, ["join"]);
  assert.equal(teamName(), "Couch Coordinators", "the name is kept on the tablet");
  const pop = document.querySelector(".trivia-pop");
  assert.ok(pop && !pop.hasAttribute("hidden") && pop.textContent.includes("Where does Diner Tech play"), "the open question shows after the join");
  // a pick posts the answer and closes the popup; the standings come next
  pop.querySelectorAll("button.trivia-pop__choice")[1].click();
  await settle();
  await advance(POLL_MS + 10);
  await settle();
  assert.deepEqual(posts, ["join", "answer"]);
  assert.ok(pop.textContent.includes("Trivia standings") && !pop.textContent.includes("Where does"), pop.textContent);
  // the × on the standings keeps them away until the next question is asked
  pop.querySelector(".trivia-pop__close").click();
  await advance(POLL_MS + 10);
  await settle();
  assert.ok(pop.hasAttribute("hidden"));
  server = base({ team: { name: "Couch Coordinators", joined: true, today: [0, 1], season: [0, 1] }, day: { ...DAY, asked: 4 } });
  await advance(POLL_MS + 10);
  await settle();
  assert.ok(!pop.hasAttribute("hidden") && pop.textContent.includes("4 asked"), "a new question asked: the standings are back");
  // the trivia turned off in Settings: nothing shows
  server = base({ on: false, team: { name: "Couch Coordinators", joined: true } });
  await advance(POLL_MS + 10);
  await settle();
  assert.ok(pop.hasAttribute("hidden") && !joinUp());
  assert.ok(errors.length === 0, errors.join("\n"));
};

// Not today before anyone has joined (2026-10-22): there is no trivia day yet, so the tablet keeps today's date as the day
// it said no to; the popup came back on every page before.
scenarios.declineBeforeDay = async () => {
  installWindow();
  const { startTrivia, forgetName } = await import(moduleUrl("ui/trivia.js"));
  const joinUp = () => { const pop = document.querySelector(".trivia-pop"); return Boolean(pop && !pop.hasAttribute("hidden") && pop.querySelector(".trivia-pop__card--join")); };
  forgetName();
  localStorage.removeItem("trivia.declined");
  route("/api/trivia/now", () => envelope(base({ day: null })));
  window.location.hash = "#program";
  await startTrivia();
  await settle();
  assert.ok(joinUp(), "a game day, no trivia day yet: the join popup");
  document.querySelector(".trivia-join__decline").click();
  await settle();
  assert.ok(/^\d{4}-\d{2}-\d{2}$/.test(localStorage.getItem("trivia.declined") || ""), "today's date kept");
  await advance(5 * 60 * 1000 + 10);
  await settle();
  assert.ok(!joinUp(), "not asked again today");
};

// The layout pass (owner 2026-10-22): the standings sit, static, at the foot of In Game's Score by quarter and on the board,
// which also shows the open question there (no buttons, never the answer); In Game gets no standings popup.
scenarios.panel = async () => {
  installWindow();
  const { triviaPanel, triviaRunning, PANEL_ROWS, startTrivia, rememberName } = await import(moduleUrl("ui/trivia.js"));
  const FOUR = [...STANDINGS, { rank: 3, name: "The Back Row", today: [0, 2], season: [3, 9], you: false }, { rank: 4, name: "Ted", today: [0, 2], season: [0, 2], you: false }];
  assert.equal(PANEL_ROWS, 3);
  const p = triviaPanel(base({ standings: FOUR }));
  const t = clean("standings panel", p);
  assert.equal(p.querySelectorAll("tbody tr").length, 3, "the top three");
  assert.ok(t.includes("Trivia") && t.includes("2 teams") && t.includes("next at 7:27 pm") && t.includes("2 of 2") && t.includes("16 of 22"), t);
  assert.equal(p.querySelectorAll("button").length, 0, "nothing to press: it is a static block");
  const lower = FOUR.map((r, i) => ({ ...r, you: i === 3 }));
  const withYou = triviaPanel(base({ standings: lower }));
  assert.equal(withYou.querySelectorAll("tbody tr").length, 4, "this tablet's line under the top three");
  assert.ok(withYou.querySelector("tr.is-you").textContent.includes("Ted"));
  // the board shows the open question in the same spot, plain, with its clock, never the answer
  const q = triviaPanel(base({ question: QUESTION }), { board: true });
  const qt = clean("board question", q);
  assert.ok(qt.includes("Where does Diner Tech play") && qt.includes("Griddle Field") && qt.includes("Answer on your tablet") && /3\d s/.test(qt), qt);
  assert.equal(q.querySelectorAll("button").length, 0, "no buttons on the board");
  assert.ok(q.querySelector(".trivia-clock"), "the clock counts down by itself");
  assert.ok(clean("tablet panel", triviaPanel(base({ question: QUESTION }))).includes("Couch Coordinators"), "a tablet's block keeps the standings; its question is a popup");
  // no trivia today, the trivia off, the day ended, the leaderboard off: nothing
  for (const data of [null, "junk", base({ day: null }), base({ on: false }), base({ day: { ...DAY, endedAt: "2026-10-24T23:00:00-04:00" } }), base({ board: false })]) assert.equal(triviaPanel(data), null, String(JSON.stringify(data)).slice(0, 80));
  assert.ok(triviaRunning(base()) && !triviaRunning(base({ day: null })));
  clean("junk rows", triviaPanel(base({ standings: [null, { rank: "x", name: null, today: "bad", season: [1] }, 7] })));
  // on In Game a joined tablet hears the answers (the static block) and gets no standings popup
  rememberName("Couch Coordinators");
  route("/api/trivia/now", () => envelope(base({ team: { name: "Couch Coordinators", joined: true, today: [1, 2], season: [14, 22] } })));
  const heard = [];
  document.addEventListener("kickoff:trivia-now", (event) => heard.push(event.detail));
  window.location.hash = "#live";
  await startTrivia();
  await settle();
  assert.ok(heard.length >= 1 && heard[heard.length - 1].standings.length === 2, "In Game hears every answer");
  assert.equal(document.querySelectorAll(".trivia-pop:not([hidden])").length, 0, `no standings popup on In Game: they sit in Score by quarter (${document.querySelector(".trivia-pop")?.textContent})`);
  assert.ok(errors.length === 0, errors.join("\n"));
};
"""


@needs_node
@pytest.mark.parametrize("scenario", ["popups", "page", "flow", "declineBeforeDay", "panel"])
def test_trivia_in_a_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)
