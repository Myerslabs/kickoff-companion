// The trivia on every page (owner 2026-10-21): the join note on connect, then the question popup and the standings popup
// in the corner of whatever page is open, for the tablets that joined with a team name. Only a joined tablet (or the
// board) asks the server; a tablet that said Not today sees nothing until it joins from the Trivia page.
//
//   startTrivia()                 at boot: learns whether it is a game day and the trivia is on, shows the join note
//                                 once per tablet per day, polls /api/trivia/now while joined (10 s, visible pages only)
//   teamName() / rememberName() / forgetName()   this tablet's team name, kept in localStorage
//   join(name) / leave() / answer(id, choice) / endDay()   the writes, each a POST the guest guard allows
//   questionPopup(data, handlers) / standingsPopup(data)   the two popups' markup (exported for the tests)
//
// Rules from the mocks: the question shows for forty seconds, a pick, the × or the clock closes it, and no answer ever
// shows here (the Trivia page has them); the standings sit in the corner between questions and the × closes them until
// the next question; on the board the same popups show larger with no buttons. The join prompt is a page note like the
// others (ui/page-notes.js), which never shows on In Game or the board, so In Game gets a compact join card in the
// corner instead.

import { el, isNum, records, str, text } from "./dom.js";
import { addNote, noteShowing, removeNote, routeIdOf } from "./page-notes.js";
import { fetchJson } from "../views/common.js";

const NAME_KEY = "trivia.name";
const DECLINED_KEY = "trivia.declined";
export const POLL_MS = 10 * 1000;
export const CHECK_MS = 5 * 60 * 1000;
const ORDINALS = ["1st", "2nd", "3rd", "4th"];

const state = {
  pop: null, // the one corner popup, built once
  data: null, // the last /api/trivia/now answer
  timer: null,
  countdown: null,
  offsetMs: 0, // server clock minus this tablet's
  closedQuestion: null, // the question id the × closed
  closedStandingsAt: -1, // the day's asked count when the × closed the standings
  welcome: null, // the join's welcome line, shown on the standings for a minute
  welcomeUntil: 0,
  shownKey: null, // what the corner shows now, so a poll that brings nothing new leaves the buttons alone
  started: false,
};

function storage() {
  try {
    return globalThis.localStorage || null;
  } catch {
    return null;
  }
}

export function teamName() {
  const name = storage()?.getItem(NAME_KEY);
  return typeof name === "string" ? name : "";
}

export function rememberName(name) {
  try {
    storage()?.setItem(NAME_KEY, String(name));
  } catch {
    /* a private window keeps nothing; the tablet plays until it closes the page */
  }
}

export function forgetName() {
  try {
    storage()?.removeItem(NAME_KEY);
  } catch {
    /* nothing to forget */
  }
}

export function declinedToday(date) {
  try {
    return !!date && storage()?.getItem(DECLINED_KEY) === String(date);
  } catch {
    return false;
  }
}

export function declineToday(date) {
  try {
    if (date) storage()?.setItem(DECLINED_KEY, String(date));
  } catch {
    /* then the note comes back next time; no harm */
  }
}

async function post(path, body) {
  const response = await fetch(path, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  if (!response.ok) {
    const message = payload?.errors?.[0]?.message || `The server answered ${response.status}`;
    throw new Error(message);
  }
  return payload?.data ?? null;
}

export async function join(name) {
  const data = await post("/api/trivia/join", { name });
  if (data && str(data.name)) rememberName(data.name);
  state.welcome = str(data?.welcome) ? data.welcome : null;
  state.welcomeUntil = state.welcome ? Date.now() + 60 * 1000 : 0;
  state.closedQuestion = null;
  state.closedStandingsAt = -1;
  return data;
}

export async function leave() {
  const name = teamName();
  forgetName();
  if (name) await post("/api/trivia/leave", { name });
  hidePop();
}

export async function rename(newName) {
  const data = await post("/api/trivia/rename", { name: teamName(), newName });
  if (data && str(data.name)) rememberName(data.name);
  return data;
}

export async function answer(questionId, choice) {
  return post("/api/trivia/answer", { name: teamName(), questionId, choice });
}

export async function endDay() {
  return post("/api/trivia/end", {});
}

export async function mark(questionId, note = "") {
  return post("/api/trivia/mark", { questionId, note });
}

// --- the markup ---------------------------------------------------------------------------------------------------

function onBoard() {
  return typeof document !== "undefined" && !!document.body?.classList?.contains("board-mode");
}

function serverNow() {
  return Date.now() + state.offsetMs;
}

function secondsLeft(question) {
  const closes = Date.parse(question?.closesAt);
  return isNum(closes) ? Math.max(0, Math.round((closes - serverNow()) / 1000)) : isNum(question?.secondsLeft) ? question.secondsLeft : 0;
}

function questionSub(question) {
  const n = isNum(question?.n) ? question.n : null;
  const nth = n ? `the ${n}${n % 10 === 1 && n !== 11 ? "st" : n % 10 === 2 && n !== 12 ? "nd" : n % 10 === 3 && n !== 13 ? "rd" : "th"} today` : "";
  const period = isNum(question?.period) && question.period >= 1 && question.period <= 4 ? `${ORDINALS[question.period - 1]} quarter` : null;
  return [period, nth].filter(Boolean).join(" · ");
}

function closeButton(onClose) {
  return el("button", { type: "button", class: "icon-btn trivia-pop__close", "aria-label": "Close", onclick: onClose }, "×");
}

/** The question popup: three choices, the clock, no answer. `onPick(index)` and `onClose()` come from the caller. */
export function questionPopup(data, { onPick = () => {}, onClose = () => {}, board = false } = {}) {
  const question = data?.question && typeof data.question === "object" ? data.question : {};
  const choices = records(question.choices).length ? question.choices : Array.isArray(question.choices) ? question.choices : [];
  const left = el("span", { class: "trivia-pop__clock" }, `Closes in ${secondsLeft(question)} s`);
  const picked = isNum(question.yourPick) ? question.yourPick : null;
  return el(
    "div",
    { class: `trivia-pop__card trivia-pop__card--question${board ? " trivia-pop__card--board" : ""}`, dataset: { question: str(question.id) ? question.id : "" } },
    el("div", { class: "trivia-pop__head" }, el("b", { class: "trivia-pop__title" }, "Trivia"), el("span", { class: "trivia-pop__sub" }, questionSub(question)), board ? null : closeButton(onClose)),
    el("p", { class: "trivia-pop__q" }, text(question.text)),
    el(
      "div",
      { class: "trivia-pop__choices", role: board ? "list" : "group", "aria-label": "Your pick" },
      choices.slice(0, 3).map((choice, index) =>
        board
          ? el("div", { class: "trivia-pop__choice trivia-pop__choice--plain", role: "listitem" }, el("span", { class: "trivia-pop__letter" }, "ABC"[index]), text(choice))
          : el("button", { type: "button", class: `trivia-pop__choice${picked === index ? " is-picked" : ""}`, dataset: { choice: String(index) }, onclick: () => onPick(index) }, el("span", { class: "trivia-pop__letter" }, "ABC"[index]), text(choice)),
      ),
    ),
    el("div", { class: "trivia-pop__foot" }, el("span", {}, board ? "Answer on your tablet" : str(data?.team?.name) ? `Playing as ${data.team.name}` : ""), left),
  );
}

/** The standings popup: the room's teams, today and the season, this tablet in the team's color. */
export function standingsPopup(data, { onClose = () => {}, board = false, welcome = null } = {}) {
  const rows = records(data?.standings);
  const day = data?.day && typeof data.day === "object" ? data.day : {};
  const started = Date.parse(day.startedAt);
  const since = isNum(started) ? new Date(started).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }) : null;
  const sub = [isNum(day.playing) ? `${day.playing} playing` : null, isNum(day.asked) ? `${day.asked} asked${since ? ` since ${since}` : ""}` : null].filter(Boolean).join(" · ");
  const cell = (pair) => (Array.isArray(pair) && isNum(pair[0]) && isNum(pair[1]) ? `${pair[0]} of ${pair[1]}` : "–");
  return el(
    "div",
    { class: `trivia-pop__card trivia-pop__card--standings${board ? " trivia-pop__card--board" : ""}` },
    el("div", { class: "trivia-pop__head" }, el("b", { class: "trivia-pop__title" }, "Trivia standings"), el("span", { class: "trivia-pop__sub" }, sub), board ? null : closeButton(onClose)),
    rows.length
      ? el(
          "table",
          { class: "trivia-pop__table", "aria-label": "Trivia standings" },
          el("thead", {}, el("tr", {}, el("th", { scope: "col" }, "Team"), el("th", { scope: "col", class: "num" }, "Today"), el("th", { scope: "col", class: "num" }, "Season"))),
          el("tbody", {}, rows.map((r) => el("tr", { class: r.you ? "is-you" : "" }, el("td", {}, `${isNum(r.rank) ? `${r.rank} ` : ""}${text(r.name)}`), el("td", { class: "num" }, cell(r.today)), el("td", { class: "num" }, cell(r.season))))),
        )
      : el("p", { class: "trivia-pop__q" }, "Nobody on the board yet. Join from the Trivia page."),
    el("div", { class: "trivia-pop__foot" }, el("span", {}, str(welcome) ? welcome : ""), el("span", {}, str(day.next) ? day.next : "")),
  );
}

/** The join card: a team name, Join, Not today. `compact` is the corner version for In Game. */
export function joinCard(data, { onJoin = () => {}, onDecline = () => {}, compact = false } = {}) {
  const remembered = teamName();
  const input = el("input", { type: "text", class: "trivia-join__name", maxlength: "40", placeholder: "Team name", "aria-label": "Team name", value: remembered, autocomplete: "off" });
  const status = el("span", { class: "trivia-join__status", "aria-live": "polite" });
  const submit = async (event) => {
    event?.preventDefault?.();
    const name = input.value.trim();
    if (!name) {
      status.textContent = "Type a team name.";
      input.focus?.();
      return;
    }
    status.textContent = "Joining…";
    try {
      const joined = await join(name);
      status.textContent = "";
      onJoin(joined);
    } catch (error) {
      status.textContent = error?.message || "Could not join.";
    }
  };
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") submit(event);
  });
  return el(
    "form",
    { class: `trivia-join${compact ? " trivia-join--compact" : ""}`, onsubmit: submit },
    el("span", { class: "trivia-join__lead" }, remembered ? `Play again as ${remembered}? Your season score comes back with the name.` : "Join with a team name and the trivia runs on this tablet all day. Names are case sensitive."),
    el("div", { class: "trivia-join__row" }, input, el("button", { type: "button", class: "btn btn--primary trivia-join__join", onclick: submit }, "Join"), el("button", { type: "button", class: "btn trivia-join__decline", onclick: () => onDecline() }, "Not today")),
    status,
  );
}

// --- the corner popup on this tablet -----------------------------------------------------------------------------

function ensurePop() {
  if (state.pop) return state.pop;
  if (typeof document === "undefined" || !document.body) return null;
  state.pop = el("div", { class: "trivia-pop", hidden: true });
  document.body.append(state.pop);
  return state.pop;
}

function hidePop() {
  if (!state.pop) return;
  state.pop.setAttribute("hidden", "");
  state.pop.replaceChildren();
  state.shownKey = null;
  stopCountdown();
}

function showPop(card, key = null) {
  const pop = ensurePop();
  if (!pop) return;
  if (key && state.shownKey === key && !pop.hasAttribute("hidden")) return; // the same thing is up already
  state.shownKey = key;
  pop.replaceChildren(card);
  pop.classList.toggle("trivia-pop--board", onBoard());
  pop.removeAttribute("hidden");
}

function stopCountdown() {
  if (state.countdown) clearInterval(state.countdown);
  state.countdown = null;
}

function startCountdown(question) {
  stopCountdown();
  state.countdown = setInterval(() => {
    const clock = state.pop?.querySelector(".trivia-pop__clock");
    const left = secondsLeft(question);
    if (clock) clock.textContent = `Closes in ${left} s`;
    if (left <= 0) {
      stopCountdown();
      tick(); // the clock ran out: ask the server what is on now
    }
  }, 1000);
}

function currentRoute() {
  return typeof location !== "undefined" ? routeIdOf(location.hash || "") : "";
}

function showJoinNote(data) {
  if (noteShowing("trivia-join")) return; // up already: a poll must not redraw the form under the reader's fingers
  const date = data?.day?.date || new Date(serverNow()).toISOString().slice(0, 10);
  addNote({
    id: "trivia-join",
    title: "Trivia today?",
    body: () =>
      joinCard(data, {
        onJoin: () => {
          removeNote("trivia-join");
          tick();
        },
        onDecline: () => {
          declineToday(date);
          removeNote("trivia-join");
          hidePop();
        },
      }),
    onDismiss: () => declineToday(date),
  });
}

function render(data) {
  state.data = data;
  const serverAt = Date.parse(data?.serverNow);
  if (isNum(serverAt)) state.offsetMs = serverAt - Date.now();
  const board = onBoard();
  const name = teamName();
  const joined = data?.team?.joined === true;
  const date = data?.day?.date || null;
  if (data?.on !== true) {
    removeNote("trivia-join");
    hidePop();
    return;
  }
  // a tablet without a name, or with one from an earlier game day: the question of joining, once per day
  if (!board && !joined && data?.gameDay === true && !declinedToday(date || new Date(serverNow()).toISOString().slice(0, 10))) {
    if (currentRoute() === "live") {
      removeNote("trivia-join");
      showPop(el("div", { class: "trivia-pop__card trivia-pop__card--join" }, el("div", { class: "trivia-pop__head" }, el("b", { class: "trivia-pop__title" }, "Trivia today?"), closeButton(() => { declineToday(date); hidePop(); })), joinCard(data, { compact: true, onJoin: () => tick(), onDecline: () => { declineToday(date); hidePop(); } })), "join");
    } else {
      hidePop();
      showJoinNote(data);
    }
    return;
  }
  removeNote("trivia-join");
  if (!joined && !board) {
    hidePop();
    return;
  }
  if (!data?.day || data.day.endedAt) {
    hidePop();
    return;
  }
  const question = data.question && typeof data.question === "object" && str(data.question.id) ? data.question : null;
  if (question && question.id !== state.closedQuestion && (board || !isNum(question.yourPick))) {
    if (state.shownKey === `q:${question.id}`) return; // still up; the clock ticks on its own
    showPop(
      questionPopup(data, {
        board,
        onClose: () => {
          state.closedQuestion = question.id;
          hidePop();
        },
        onPick: async (index) => {
          const buttons = state.pop?.querySelectorAll(".trivia-pop__choice") || [];
          buttons.forEach((b) => b.setAttribute("disabled", ""));
          try {
            await answer(question.id, index);
          } catch (error) {
            console.warn("The trivia answer did not land.", error);
          }
          state.closedQuestion = question.id;
          hidePop();
          tick();
        },
      }),
      `q:${question.id}`,
    );
    startCountdown(question);
    return;
  }
  stopCountdown();
  const asked = isNum(data.day.asked) ? data.day.asked : 0;
  if (currentRoute() === "trivia" && !board) {
    hidePop(); // the Trivia page draws the board itself
    return;
  }
  if (data.board === true && asked > state.closedStandingsAt && (records(data.standings).length || board)) {
    const welcome = state.welcome && Date.now() < state.welcomeUntil ? state.welcome : null;
    const key = `s:${asked}:${welcome || ""}:${str(data.day.next) ? data.day.next : ""}:${JSON.stringify(records(data.standings).map((r) => [r.rank, r.name, r.today, r.season]))}`;
    showPop(
      standingsPopup(data, {
        board,
        welcome,
        onClose: () => {
          state.closedStandingsAt = asked;
          hidePop();
        },
      }),
      key,
    );
    return;
  }
  hidePop();
}

async function tick() {
  if (typeof document !== "undefined" && document.visibilityState === "hidden") return;
  const name = teamName();
  try {
    const envelope = await fetchJson(`/api/trivia/now?name=${encodeURIComponent(name)}`);
    render(envelope?.data && typeof envelope.data === "object" ? envelope.data : null);
  } catch (error) {
    console.warn("The trivia could not be read.", error);
  }
  schedule();
}

function schedule() {
  if (state.timer) clearTimeout(state.timer);
  const active = !!teamName() || onBoard();
  state.timer = setTimeout(tick, active ? POLL_MS : CHECK_MS);
}

/** Boot: one look at the server, then the polling while this tablet plays. Safe to call once. */
export async function startTrivia() {
  if (state.started) return;
  state.started = true;
  if (typeof document !== "undefined" && typeof document.addEventListener === "function") {
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible") tick();
    });
    document.addEventListener("kickoff:route", () => {
      if (state.data) render(state.data); // the join prompt moves between the note and the In Game corner
    });
    document.addEventListener("kickoff:trivia", () => tick()); // the Trivia page joined, left or ended the day
  }
  await tick();
}

/** For the tests and the Trivia page: the last answer this tablet saw. */
export function lastTriviaData() {
  return state.data;
}
