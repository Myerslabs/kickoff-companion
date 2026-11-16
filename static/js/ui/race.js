// What we need (the F8 talk-through, feature 1, owner 2026-10-21): the conference race as a band, from the server's
// `race` block (app/services/race.py: every team's conference line, the games left, the best record it can reach, clinched
// or out; our four lines in words; the week's games that help us and whom to pull for) and the playoff picture's line
// (`picture`: our seed and status, the twelve seeds). At the bottom of the Pre-Game Program until the owner places it;
// the Post-Game Program sets it beside its kickoff twin. The same `helps` block marks a game on the Top 25 page (a chip)
// and the ticker (a dot), and the standings tables wear each team's standing as a badge. Board 6 (ENH-31, 2026-10-25): each
// contender's range of finishes still possible sits above the four lines (static/js/ui/race-ranges.js). BUG-15 (the owner's
// board of 2026-10-27): the band takes a row of its own, our standing leads it, the ranges ride in the standings table as its
// last column (row for row, beside the table from a 600 px band; under it, as the chart, below that), the four lines sit
// under "Our way in" two by two, the twelve seeds in one row, and on a wide screen the lines move beside the table.
//
//   raceBand(race, picture, { id, title })   the band (a note when the race has not started)
//   raceBadge(status)                        "Clinched" | "Out" | "Tiebreaker" as a small badge, null for a team still alive
//   helpsChip(helps)                         "Helps us: pull for X" (its title says why), null for our own game or none
//   kickoffText(iso)                         "Sat 3:30 PM" in the device's zone (exported for the tests)

import { usLabel } from "../identity.js";
import { DASH, el, isNum, text } from "./dom.js";
import { placesFor, raceRanges, rangeAxis, rangeStrip } from "./race-ranges.js";
import { statTable } from "./stat-table.js";
import { band, note } from "./states.js";

const STATUS_WORDS = { clinched: "Clinched", out: "Out", tiebreaker: "Tiebreaker" };

export function raceBadge(status) {
  const word = STATUS_WORDS[status];
  if (!word) return null;
  return el("span", { class: `race-badge race-badge--${status}`, title: status === "tiebreaker" ? "A top-two finish unless a tie goes against it" : status === "out" ? "No top-two finish left" : "A top-two finish whatever happens" }, word);
}

export function helpsChip(helps) {
  if (!helps || typeof helps !== "object" || helps.ours === true || typeof helps.pullFor !== "string" || !helps.pullFor) return null;
  return el("span", { class: "helps-chip", title: text(helps.why) }, el("i", { class: "helps-chip__dot", "aria-hidden": "true" }), `Helps us: pull for ${helps.pullFor}`);
}

export function kickoffText(iso) {
  if (typeof iso !== "string" || !iso) return DASH;
  const when = new Date(iso);
  if (Number.isNaN(when.getTime())) return DASH;
  try {
    return when.toLocaleString(undefined, { weekday: "short", hour: "numeric", minute: "2-digit" });
  } catch {
    return DASH;
  }
}

function recordText(wins, losses) {
  return isNum(wins) && isNum(losses) ? `${wins}-${losses}` : DASH;
}

function usStatusLine(race) {
  const us = race.us && typeof race.us === "object" ? race.us : {};
  const place = isNum(us.place) ? us.place : null;
  const where = place ? `${ordinal(place)} in the ${text(race.conference)} at ${recordText(us.confWins, us.confLosses)}` : null;
  if (us.status === "clinched") return `${where ? where + ": " : ""}a spot in the title game is clinched.`;
  if (us.status === "tiebreaker") return `${where ? where + ": " : ""}a spot in the title game unless a tie goes against us.`;
  if (us.status === "out") return `${where ? where + ": " : ""}the title game is out of reach this year.`;
  if (race.settled) return `${where ? where + ": " : ""}the regular season is done.`;
  return where ? `${where}, ${isNum(us.left) ? us.left : DASH} left, ${isNum(us.best) ? us.best : DASH} wins the most we can reach.` : null;
}

function ordinal(n) {
  if (!isNum(n)) return DASH;
  const rest = n % 100;
  if (rest >= 11 && rest <= 13) return `${n}th`;
  return `${n}${{ 1: "st", 2: "nd", 3: "rd" }[n % 10] || "th"}`;
}

/** The standings; with the ranges (BUG-15) each row's range of finishes is the table's last column, row for row, and our
    own row is never left off (the program keeps the top six; ours comes from `us` when we are lower). { table, places }. */
function standingsTable(race, { ranges = false } = {}) {
  let list = (Array.isArray(race.standings) ? race.standings : []).filter((r) => r && typeof r === "object");
  const us = race.us && typeof race.us === "object" ? race.us : null;
  if (ranges && list.length && !list.some((r) => r.isUs === true) && us && typeof us.team === "string" && us.team) list = [...list, { ...us, isUs: true }];
  const rows = list.map((r) => ({
    ...r,
    confText: recordText(r.confWins, r.confLosses),
    overallText: recordText(r.wins, r.losses),
    leftText: isNum(r.left) ? String(r.left) : DASH,
    bestText: isNum(r.best) && isNum(r.confLosses) ? `${r.best}-${r.confLosses}` : DASH,
  }));
  if (!rows.length) return { table: null, places: null };
  const columns = [
    { key: "place", label: "#", dim: true },
    { key: "team", label: "Team", kind: "text", render: (row) => el("span", { class: "race__team" }, text(row.team), raceBadge(row.status)) },
    { key: "confText", label: "Conf" },
    { key: "overallText", label: "Overall", labelShort: "Ovr" },
    { key: "leftText", label: "Left" },
    { key: "bestText", label: "Best", labelShort: "Best" },
  ];
  const places = ranges ? placesFor(rows) : null;
  const spots = isNum(race.spots) ? race.spots : 2;
  if (places) columns.push({ key: "range", label: rangeAxis({ places, spots }), kind: "text", sortable: false, render: (row) => rangeStrip(row, { places, spots }) });
  const table = statTable({ compact: true, columns, rows, sortable: false, rowClass: (row) => (row.isUs ? "is-us" : null), caption: `The ${text(race.conference)} race: the top of the standings, the games left, the best record each can reach${places ? " and the places each can still finish" : ""}` });
  return { table: places ? el("div", { class: "race__table race__table--ranges" }, table) : table, places };
}

/** Under the table with the ranges: what the bars mean (the chart's own key, for the table's column). */
function rangesKey(race) {
  const spots = isNum(race.spots) ? race.spots : 2;
  return el(
    "p",
    { class: "race__ranges-key" },
    `Each bar runs from the best place a team can still finish to the worst, ties counted for it and against it; the ring is where it stands now; the shaded ${spots === 1 ? "column is the title-game spot" : `columns are the ${spots} title-game spots`}.`,
    race.rangeExact === false ? " With this many games left the ends are counted from the records, not played out game by game." : "",
  );
}

function linesList(race) {
  const lines = (Array.isArray(race.lines) ? race.lines : []).filter((l) => l && typeof l === "object" && typeof l.text === "string");
  if (!lines.length) return null;
  return el("ul", { class: "race__lines" }, lines.map((line) => el("li", {}, el("strong", {}, text(line.lead)), " ", text(line.text))));
}

function watchTable(race) {
  // post-freeze Wave 3 (ENH-7, tester report 2026-10-24): our own game is not one of the games that help us; it is the game
  const rows = (Array.isArray(race.watch) ? race.watch : []).filter((r) => r && typeof r === "object" && r.ours !== true).map((r) => ({
    ...r,
    gameText: `${text(r.away)} at ${text(r.home)}`,
    whenText: kickoffText(r.kickoff),
    pullText: text(r.pullFor),
    whyText: text(r.why),
  }));
  if (!rows.length) return note("No other game this week changes our path.", { kind: "empty" });
  const columns = [
    { key: "gameText", label: "Game", kind: "text" },
    { key: "whenText", label: "Kickoff", kind: "text" },
    { key: "pullText", label: "Pull for", kind: "text" },
    { key: "whyText", label: "Why", kind: "text" },
  ];
  return statTable({ compact: true, columns, rows, sortable: false, rowClass: (row) => (row.ours === true ? "is-us" : null), caption: "The games this week that help us, and whom to pull for" });
}

/** "Florida: out, 17th in the order" with the school in bold and a full stop; a line without a colon stays as it is. */
function playoffLine(line) {
  const words = typeof line === "string" ? line.trim() : "";
  if (!words) return `${usLabel()}: not in the picture yet.`;
  const ended = /[.!?]$/.test(words) ? words : `${words}.`;
  const cut = ended.indexOf(": ");
  return cut > 0 ? [el("strong", {}, ended.slice(0, cut + 1)), ended.slice(cut + 1)] : ended;
}

function pictureBlock(picture) {
  const p = picture && typeof picture === "object" ? picture : null;
  if (!p) return null;
  const us = p.us && typeof p.us === "object" ? p.us : {};
  const seeds = (Array.isArray(p.seeds) ? p.seeds : []).filter((s) => s && typeof s === "object" && isNum(s.seed));
  const strip = seeds.length
    ? el("div", { class: "race__seeds" }, seeds.map((s) => el("span", { class: `race__seed${s.isUs === true ? " race__seed--us" : ""}` }, el("small", {}, `${s.seed}${s.seed <= 4 ? " · bye" : ""}`), el("span", {}, text(s.abbreviation || s.school)))))
    : null;
  const outs = (Array.isArray(p.firstFourOut) ? p.firstFourOut : []).filter((s) => s && typeof s === "object").map((s) => text(s.abbreviation || s.school));
  return el(
    "div",
    { class: "race__picture" },
    el("p", { class: "race__picture-line" }, playoffLine(us.line)), // BUG-15: under its head, the school leads the line ("Florida: out, 17th in the order.")
    strip,
    el("p", { class: "race__picture-foot" }, `By ${text(p.sourceLabel || "the AP poll")}${isNum(p.week) ? `, week ${p.week}` : ""}. ${outs.length ? `First four out: ${outs.join(", ")}.` : ""} The whole bracket is on the Season page.`),
  );
}

/**
 * raceBand(race, picture, { id, title })
 * The race block from the program or the season overview, and the playoff picture's line; null race: a note.
 */
export function raceBand(race, picture, { id = "program-race", title = "What we need" } = {}) {
  const r = race && typeof race === "object" ? race : null;
  const summary = r ? `${text(r.conference)} title game and the playoff${isNum(r.week) ? `, week ${r.week}` : ""}` : "the conference race and the playoff";
  return band({
    id,
    title,
    collapsible: false,
    foldable: true,
    summary,
    state: { status: "ready" },
    body: () => {
      if (!r) return note(`The race appears once ${usLabel()} has played a conference game.`, { kind: "empty" });
      const status = usStatusLine(r);
      const { table, places } = standingsTable(r, { ranges: true });
      const others = isNum(r.others) && r.others > 0 ? el("p", { class: "race__others" }, `${r.others} more ${r.others === 1 ? "team" : "teams"}${isNum(r.outCount) && r.outCount > 0 ? `, ${r.outCount} of them out` : ""}; the whole table is on the Season page.`) : null;
      const lines = linesList(r);
      // BUG-15 (the owner's board of 2026-10-27): our standing first; the standings with each team's range beside it, row for
      // row (a narrow band draws the board 6 chart under the table instead); our way in; the playoff; the games that help
      return el(
        "div",
        { class: "race" },
        el(
          "div",
          { class: `race__grid${places ? " race__grid--ranges" : ""}` },
          status ? el("p", { class: "race__status" }, status) : null,
          el(
            "div",
            { class: "race__standings" },
            el("div", { class: "race__heads" }, el("h4", { class: "race__head" }, "The title game", el("small", {}, ` the top ${isNum(r.spots) ? r.spots : 2} by conference record`)), places ? el("h4", { class: "race__head race__head--ranges" }, "Where each can finish", el("small", {}, " best to worst place")) : null),
            table,
            el("div", { class: "race__feet" }, others || el("span"), places ? rangesKey(r) : null),
            places ? el("div", { class: "race__ranges-alone" }, raceRanges(r)) : raceRanges(r),
          ),
          lines ? el("div", { class: "race__way" }, el("h4", { class: "race__head" }, "Our way in"), lines) : null,
          el("div", { class: "race__playoff" }, el("h4", { class: "race__head" }, "The playoff", el("small", {}, " 12 teams: 5 champions, 7 at large")), pictureBlock(picture) || note("The picture appears with the first poll.", { kind: "empty" })),
          el("div", { class: "race__watch" }, el("h4", { class: "race__head" }, "Games that help us this week", el("small", {}, " a chip on the Top 25 page, a dot on the ticker")), watchTable(r)),
        ),
      );
    },
  });
}
