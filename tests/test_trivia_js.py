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
};

scenarios.flow = async () => {
  installWindow();
  const { startTrivia, teamName, rememberName, forgetName, declineToday, POLL_MS } = await import(moduleUrl("ui/trivia.js"));
  const { noteShowing } = await import(moduleUrl("ui/page-notes.js"));
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
  assert.ok(noteShowing("trivia-join"), "a game day and no name: the join note");
  assert.equal(document.querySelectorAll(".trivia-pop:not([hidden])").length, 0, "no popup before a join");
  // Not today: the note goes and nothing else shows
  document.querySelector(".trivia-join__decline").click();
  await settle();
  assert.ok(!noteShowing("trivia-join"));
  // the next day the tablet joins from the note
  forgetName();
  localStorage.removeItem("trivia.declined");
  await advance(POLL_MS * 2);
  await settle();
  server = base();
  await advance(5 * 60 * 1000 + 10);
  await settle();
  assert.ok(noteShowing("trivia-join"), "asked again on a day it did not decline");
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
  assert.ok(pop.hasAttribute("hidden") && !noteShowing("trivia-join"));
  assert.ok(errors.length === 0, errors.join("\n"));
};
"""


@needs_node
@pytest.mark.parametrize("scenario", ["popups", "page", "flow"])
def test_trivia_in_a_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)
