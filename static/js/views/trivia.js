// The Trivia page (owner 2026-10-21, menu > Views > Trivia, #trivia): game-day trivia for the tablets that joined. The
// answers and the scores live here, never on In Game: this tablet's team and its day, the three score cells (today,
// the season, the best day), the room's leaderboard by team name, today's questions with the right answer and the
// pick, the season table and the rules. The host ends the day from here. Reads /api/trivia?name=; the joins, the
// answers and the marks go through ui/trivia.js.
//
//   createTriviaView({ onStatus })   the view (mount, refresh, unmount)
//   scoreCells(data), boardTable(data), questionCard(q, data), seasonTable(data), rulesBand()   exported for the tests

import { el, fmtDate, isNum, records, str, text } from "../ui/dom.js";
import { band, note } from "../ui/states.js";
import { pollMs } from "../prefs.js";
import { endDay, forgetName, join, joinCard, leave, mark, rename, teamName } from "../ui/trivia.js";
import { errorPanel, fetchJson, poller } from "./common.js";

const ORDINALS = ["1st", "2nd", "3rd", "4th"];

function pair(value) {
  return Array.isArray(value) && isNum(value[0]) && isNum(value[1]) ? `${value[0]} of ${value[1]}` : "–";
}

function nth(n) {
  if (!isNum(n)) return "";
  const suffix = n % 100 >= 11 && n % 100 <= 13 ? "th" : n % 10 === 1 ? "st" : n % 10 === 2 ? "nd" : n % 10 === 3 ? "rd" : "th";
  return `the ${n}${suffix}`;
}

function clock(iso) {
  const at = Date.parse(iso);
  return isNum(at) ? new Date(at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }) : null;
}

function ourGameText(our) {
  const g = our && typeof our === "object" ? our : null;
  if (!g || !str(g.home) || !str(g.away)) return "no game of ours";
  return `${g.away} at ${g.home}`;
}

function announce() {
  try {
    document.dispatchEvent(new CustomEvent("kickoff:trivia"));
  } catch {
    /* the popups catch up on their next poll */
  }
}

/** The three cells: today, this season, the best day. */
export function scoreCells(data) {
  const team = data?.team && typeof data.team === "object" ? data.team : null;
  const best = data?.best && typeof data.best === "object" ? data.best : null;
  const day = data?.day && typeof data.day === "object" ? data.day : null;
  const cell = (label, value, detail) => el("div", { class: "trivia-cell" }, el("span", { class: "trivia-cell__label" }, label), el("b", { class: "trivia-cell__value" }, value), el("span", { class: "trivia-cell__detail" }, detail || ""));
  return el(
    "div",
    { class: "trivia-cells" },
    cell("Today", team ? pair(team.today) : "–", day && isNum(day.asked) ? `${day.asked} asked` : "no day running"),
    cell("This season", team ? pair(team.season) : "–", isNum(data?.seasonTable?.length) ? `${data.seasonTable.length} game day${data.seasonTable.length === 1 ? "" : "s"}` : ""),
    cell("Best day", best ? `${best.right} of ${best.asked}` : "–", best ? `${fmtDate(best.date, "short")}${str(best.our?.opponent) ? `, ${best.our.opponent}` : ""}` : ""),
  );
}

/** The room's leaderboard by team name: rank, team, today, this season; this tablet marked. */
export function boardTable(data) {
  const rows = records(data?.board);
  if (!rows.length) return note("Nobody on the board yet this season. The first team to join starts it.");
  return el(
    "table",
    { class: "stat-table trivia-board", "aria-label": "Trivia leaderboard" },
    el("thead", {}, el("tr", {}, el("th", { scope: "col", class: "num" }, "Rank"), el("th", { scope: "col", class: "txt" }, "Team"), el("th", { scope: "col", class: "num" }, "Today"), el("th", { scope: "col", class: "num" }, "This season"))),
    el(
      "tbody",
      {},
      rows.map((r) =>
        el(
          "tr",
          { class: r.you ? "is-you" : r.here === false ? "is-away" : "" },
          el("td", { class: "num" }, isNum(r.rank) ? String(r.rank) : "–"),
          el("td", { class: "txt" }, text(r.name), r.you ? el("small", { class: "trivia-board__tag" }, " · this tablet") : r.here === false ? el("small", { class: "trivia-board__tag" }, " · not here today") : str(r.firstDay) && r.firstDay === data?.day?.date ? el("small", { class: "trivia-board__tag" }, " · joined today") : null),
          el("td", { class: "num" }, r.today ? pair(r.today) : "–"),
          el("td", { class: "num" }, pair(r.season)),
        ),
      ),
    ),
  );
}

/** One of today's questions with the right answer, the pick and how many teams got it; open ones show no answer yet. */
export function questionCard(q, data, { onMark = null } = {}) {
  const question = q && typeof q === "object" ? q : {};
  const choices = Array.isArray(question.choices) ? question.choices.slice(0, 3) : [];
  const picked = isNum(question.yourPick) ? question.yourPick : null;
  const right = isNum(question.answer) ? question.answer : null;
  const open = question.open === true;
  const verdict = open ? "Open" : right === null ? "Closed" : picked === null ? "No pick" : picked === right ? "Right" : "Wrong";
  const period = isNum(question.period) && question.period >= 1 && question.period <= 4 ? `${ORDINALS[question.period - 1]} quarter` : null;
  const got = isNum(question.answered) && !open ? `${question.answered} of ${isNum(data?.day?.playing) ? data.day.playing : "the"} teams answered` : null;
  const sub = [nth(question.n), period, got].filter(Boolean).join(" · ");
  const marked = el("span", { class: "trivia-card__marked" }, question.marked ? "Marked as wrong" : "");
  const markButton = onMark && right !== null && !question.marked
    ? el("button", { type: "button", class: "btn btn--quiet trivia-card__mark", onclick: async () => {
        const button = markButton;
        button.setAttribute("disabled", "");
        try {
          await onMark(question.id);
          marked.textContent = "Marked as wrong";
          button.remove();
        } catch (error) {
          button.removeAttribute("disabled");
          marked.textContent = error?.message || "Could not mark it.";
        }
      } }, "Wrong? Mark it")
    : null;
  return el(
    "div",
    { class: `trivia-card trivia-card--${verdict.toLowerCase().replace(" ", "-")}`, dataset: { question: str(question.id) ? question.id : "" } },
    el("div", { class: "trivia-card__head" }, el("b", { class: "trivia-card__verdict" }, verdict), el("span", { class: "trivia-card__sub" }, sub)),
    el("p", { class: "trivia-card__q" }, text(question.text)),
    el(
      "div",
      { class: "trivia-card__choices" },
      choices.map((choice, index) => {
        const tags = [];
        if (right === index) tags.push("right answer");
        if (picked === index) tags.push("your pick");
        return el("div", { class: `trivia-card__choice${right === index ? " is-right" : ""}${picked === index && right !== index && right !== null ? " is-wrong" : ""}` }, el("span", { class: "trivia-pop__letter" }, "ABC"[index]), text(choice), tags.length ? el("span", { class: "trivia-card__tag" }, tags.join(" · ")) : null);
      }),
    ),
    right !== null && str(question.fact) ? el("p", { class: "trivia-card__fact" }, text(question.fact)) : open ? el("p", { class: "trivia-card__fact" }, "Open on the tablets now; the answer shows here once it closes.") : null,
    right !== null ? el("div", { class: "trivia-card__foot" }, el("span", {}, `From ${text(question.school)}'s facts${str(question.checkedAt) ? `, checked ${fmtDate(question.checkedAt, "short")}` : ""}`), markButton, marked) : null,
  );
}

/** The season table for this tablet: each game day, our game, the day's span and the score. */
export function seasonTable(data) {
  const rows = records(data?.seasonTable);
  if (!rows.length) return note("No game day played on this tablet yet this season.");
  return el(
    "table",
    { class: "stat-table trivia-season", "aria-label": "This season, on this tablet" },
    el("thead", {}, el("tr", {}, el("th", { scope: "col", class: "txt" }, "Day"), el("th", { scope: "col", class: "txt" }, "Our game"), el("th", { scope: "col", class: "txt" }, "The day"), el("th", { scope: "col", class: "num" }, "Trivia"))),
    el("tbody", {}, rows.map((r) => el("tr", {}, el("td", { class: "txt" }, fmtDate(r.date, "short")), el("td", { class: "txt" }, ourGameText(r.our)), el("td", { class: "txt" }, str(r.span) ? r.span : "–"), el("td", { class: "num" }, isNum(r.right) && isNum(r.asked) ? `${r.right} of ${r.asked}${r.running ? " so far" : ""}` : "–")))),
    el("tfoot", {}, el("tr", {}, el("td", { class: "txt", colspan: "3" }, "This season"), el("td", { class: "num" }, pair(data?.team?.season)))),
  );
}

/** How it plays, as the mock says it. */
export function rulesBand() {
  const rule = (lead, body) => el("p", { class: "trivia-rule" }, el("b", {}, `${lead} `), body);
  return band({
    id: "trivia-rules",
    title: "How it plays",
    collapsible: false,
    foldable: true,
    state: { status: "ready" },
    body: () =>
      el(
        "div",
        { class: "trivia-rules" },
        rule("Who.", 'Only the tablets that joined. When a tablet connects on a game day a note at the top asks for a team name and Join, or Not today; Not today means no question, no standings, nothing, until it joins here. A name is case sensitive ("Couch Coordinators" and "couch coordinators" are two teams), and the host keeps a master file on the server with every team\'s name and every answer by game day, so every tablet sees the same board and a team that joins again in a later week gets its season score back.'),
        rule("When.", "All game day, not just the game: it starts at the first join and runs until the host ends it here or no tablet has answered the last three (the room went home). Before our kickoff and after the final, a question every fifteen minutes about the teams in the games on then, from the ticker, in the corner of whatever page is open; during our game one a quarter, the way the announcers drop theirs in, at the first look after the eight-minute mark and never in the last two minutes of a half. Forty seconds, then it closes; no answer shows there."),
        rule("What.", "Three choices, one right, built from the schools' facts: the stadium and its nickname, the year it opened, who founded the school when, the trophy and the series, the fight song, the mascot's name, the Heisman winners, the national title years, the winningest coach, the longest streak, the record crowd, the retired numbers, and the dated events. The wrong choices are other schools' facts of the same kind, so they read as real. Every tablet in the room gets the same question at the same moment; the standings popup shows the room's teams, today and the season."),
        rule("The answers and the score.", "Here, never on In Game: every question asked today with the right answer, your pick and how many teams answered, then today, this season and your best day for this tablet. The board resets with the season."),
        rule("On the big screen.", "The question alone, larger, in the board's corner, with no buttons, for forty seconds; the standings between questions. The room answers on its tablets; the host reads the answer here."),
        rule("Settings.", el("span", {}, "A Trivia band in ", el("a", { href: "#settings" }, "Settings"), ': "Trivia during the game" on or off, "Leaderboard" on or off, and "Before and after our game": every 15 minutes, every 30 minutes, or only during the game. Off is off for every tablet. Guests can answer and join the board; nothing else on the server changes for them.')),
        rule("Where the facts come from.", 'The facts shipped with the app for every FBS school, under any facts this install has loaded itself; a yearly refresh from the schedule. "Wrong? Mark it" under an answer writes a note to the facts file until the next refresh overwrites the school.'),
      ),
  });
}

function headBand(data, { remake }) {
  const team = data?.team && typeof data.team === "object" ? data.team : null;
  const day = data?.day && typeof data.day === "object" ? data.day : null;
  const joined = team?.joined === true;
  const status = el("span", { class: "trivia-head__status", "aria-live": "polite" });
  const act = async (label, fn) => {
    status.textContent = `${label}…`;
    try {
      await fn();
      status.textContent = "";
      announce();
      remake();
    } catch (error) {
      status.textContent = error?.message || `Could not ${label.toLowerCase()}.`;
    }
  };
  const playAs = joined
    ? el(
        "div",
        { class: "trivia-head__team" },
        el("span", { class: "note" }, "This tablet plays as "),
        el("b", { class: "trivia-head__name" }, text(team.name)),
        el("span", { class: "note" }, str(team?.firstDay) ? ` · on the board since ${fmtDate(team.firstDay, "short")}` : ""),
        el("span", { class: "grow" }),
        el("button", { type: "button", class: "btn btn--quiet", onclick: () => {
          const input = el("input", { type: "text", maxlength: "40", value: team.name, "aria-label": "New team name" });
          const row = el("div", { class: "trivia-join__row" }, input, el("button", { type: "button", class: "btn btn--primary", onclick: () => act("Rename", () => rename(input.value.trim())) }, "Save"), el("button", { type: "button", class: "btn", onclick: () => row.replaceWith(playAs) }, "Cancel"));
          playAs.replaceWith(row);
        } }, "Change the name"),
        el("button", { type: "button", class: "btn btn--quiet", onclick: () => act("Leave", () => leave()) }, "Leave the board"),
      )
    : joinCard(data, { onJoin: () => { announce(); remake(); }, onDecline: () => { forgetName(); remake(); } });
  const dayLine = day
    ? el(
        "div",
        { class: "trivia-head__day" },
        el("b", {}, day.endedAt ? "Ended for today" : "Today"),
        el("span", {}, ` · ${day.endedAt ? `ran ${clock(day.startedAt) || "?"} to ${clock(day.endedAt) || "?"}` : `running since ${clock(day.startedAt) || "the first join"}`} · ${isNum(day.asked) ? day.asked : 0} asked · ${isNum(day.playing) ? day.playing : 0} tablet${day.playing === 1 ? "" : "s"} playing`),
        el("span", { class: "note" }, str(day.next) && !day.endedAt ? ` · ${day.next}` : ""),
        el("span", { class: "grow" }),
        data?.isHost === true && !day.endedAt ? el("button", { type: "button", class: "btn btn--quiet", onclick: () => act("End", () => endDay()) }, "End trivia for today") : null,
      )
    : el("p", { class: "note" }, data?.gameDay === true ? `Game day: ${ourGameText(data.ourGame)}. The trivia starts with the first join.` : "No game of ours today. A join starts the trivia any day; on game days every tablet is asked when it connects.");
  const off = data?.on !== true ? note("The trivia is off in Settings. Turn it on there for every tablet.", { kind: "empty" }) : null;
  return band({
    id: "trivia-head",
    title: "Trivia",
    collapsible: false,
    summary: joined ? `playing as ${text(team.name)}` : "join with a team name",
    state: { status: "ready" },
    body: () => el("div", { class: "trivia-head" }, el("p", { class: "note" }, "Game-day trivia for the tablets that joined: before, during and after our game. The answers, your score and the room's board live here; the questions pop up in the corner of any page."), off, playAs, dayLine, status),
  });
}

function render(envelope, container, state) {
  const data = envelope?.data && typeof envelope.data === "object" ? envelope.data : {};
  const questions = records(data.questions);
  const page = el(
    "div",
    { class: "page trivia-page" },
    headBand(data, state),
    band({ id: "trivia-score", title: "Your score", collapsible: false, state: { status: "ready" }, summary: data.team ? `today ${pair(data.team.today)}` : "join to keep one", body: () => scoreCells(data) }),
    band({ id: "trivia-board", title: "Leaderboard", collapsible: false, foldable: true, summary: `${isNum(data.day?.playing) ? data.day.playing : 0} playing today, ${isNum(data.teamsThisSeason) ? data.teamsThisSeason : 0} this season`, state: { status: "ready" }, body: () => el("div", {}, data.board === false ? note("The leaderboard is off in Settings; every tablet keeps its own score.") : boardTable(data)) }),
    band({
      id: "trivia-today",
      title: "Today's questions",
      collapsible: false,
      foldable: true,
      summary: questions.length ? `${questions.length} asked${str(data.day?.next) ? ` · ${data.day.next}` : ""}` : "none yet",
      state: { status: "ready" },
      body: () => (questions.length ? el("div", { class: "trivia-cards" }, [...questions].reverse().map((q) => questionCard(q, data, { onMark: (id) => mark(id, "") }))) : note(data.day ? "The first question comes with the first join." : "No day running. The questions of a day show here as they close.")),
    }),
    band({ id: "trivia-season", title: "This season, on this tablet", collapsible: false, foldable: true, summary: pair(data.team?.season), state: { status: "ready" }, body: () => seasonTable(data) }),
    rulesBand(),
  );
  container.replaceChildren(page);
}

export function createTriviaView({ onStatus } = {}) {
  let container = null;
  let view = null;
  const state = { refresh: () => view?.refresh?.(), remake: () => remake() };
  const make = () =>
    poller({
      url: `/api/trivia?name=${encodeURIComponent(teamName())}`,
      refreshMs: Math.min(pollMs(), 30 * 1000),
      staleAfterMs: 30 * 1000,
      onStatus,
      render: (envelope, target) => render(envelope, target, state),
      renderError: (message, target, retry) => target.replaceChildren(errorPanel("Trivia", message, retry)),
      renderLoading: () => el("div", { class: "page" }, band({ title: "Trivia", collapsible: false, state: { status: "loading" } })),
      loadingDetail: "The board, today's questions and your score",
      holdDuringRuns: false,
    });
  function remake() {
    if (!container) return;
    view?.unmount?.();
    view = make();
    view.mount(container);
  }
  return {
    mount(target) {
      container = target;
      view = make();
      view.mount(target);
    },
    refresh: () => view?.refresh?.(),
    unmount() {
      view?.unmount?.();
      view = null;
      container = null;
    },
  };
}

/** One quiet read for the tests and other pages: the page's data for this tablet. */
export async function loadTrivia() {
  const envelope = await fetchJson(`/api/trivia?name=${encodeURIComponent(teamName())}`);
  return envelope?.data && typeof envelope.data === "object" ? envelope.data : null;
}
