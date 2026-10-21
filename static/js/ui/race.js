// What we need (the F8 talk-through, feature 1, owner 2026-10-21): the conference race as a band, from the server's
// `race` block (app/services/race.py: every team's conference line, the games left, the best record it can reach, clinched
// or out; our four lines in words; the week's games that help us and whom to pull for) and the playoff picture's line
// (`picture`: our seed and status, the twelve seeds). At the bottom of the Pre-Game Program until the owner places it;
// the Post-Game Program sets it beside its kickoff twin. The same `helps` block marks a game on the Top 25 page (a chip)
// and the ticker (a dot), and the standings tables wear each team's standing as a badge.
//
//   raceBand(race, picture, { id, title })   the band (a note when the race has not started)
//   raceBadge(status)                        "Clinched" | "Out" | "Tiebreaker" as a small badge, null for a team still alive
//   helpsChip(helps)                         "Helps us: pull for X" (its title says why), null for our own game or none
//   kickoffText(iso)                         "Sat 3:30 PM" in the device's zone (exported for the tests)

import { usLabel } from "../identity.js";
import { DASH, el, isNum, text } from "./dom.js";
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

function standingsTable(race) {
  const rows = (Array.isArray(race.standings) ? race.standings : []).filter((r) => r && typeof r === "object").map((r) => ({
    ...r,
    confText: recordText(r.confWins, r.confLosses),
    overallText: recordText(r.wins, r.losses),
    leftText: isNum(r.left) ? String(r.left) : DASH,
    bestText: isNum(r.best) && isNum(r.confLosses) ? `${r.best}-${r.confLosses}` : DASH,
  }));
  if (!rows.length) return null;
  const columns = [
    { key: "place", label: "#", dim: true },
    { key: "team", label: "Team", kind: "text", render: (row) => el("span", { class: "race__team" }, text(row.team), raceBadge(row.status)) },
    { key: "confText", label: "Conf" },
    { key: "overallText", label: "Overall", labelShort: "Ovr" },
    { key: "leftText", label: "Left" },
    { key: "bestText", label: "Best", labelShort: "Best" },
  ];
  return statTable({ compact: true, columns, rows, sortable: false, rowClass: (row) => (row.isUs ? "is-us" : null), caption: `The ${text(race.conference)} race: the top of the standings, the games left and the best record each can reach` });
}

function linesList(race) {
  const lines = (Array.isArray(race.lines) ? race.lines : []).filter((l) => l && typeof l === "object" && typeof l.text === "string");
  if (!lines.length) return null;
  return el("ul", { class: "race__lines" }, lines.map((line) => el("li", {}, el("strong", {}, text(line.lead)), " ", text(line.text))));
}

function watchTable(race) {
  const rows = (Array.isArray(race.watch) ? race.watch : []).filter((r) => r && typeof r === "object").map((r) => ({
    ...r,
    gameText: `${text(r.away)} at ${text(r.home)}`,
    whenText: kickoffText(r.kickoff),
    pullText: r.ours === true ? "Win it" : text(r.pullFor),
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
    el("p", { class: "race__picture-line" }, el("strong", {}, "The playoff: "), text(us.line) || "not in the picture yet"),
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
      const standings = standingsTable(r);
      const others = isNum(r.others) && r.others > 0 ? el("p", { class: "race__others" }, `${r.others} more ${r.others === 1 ? "team" : "teams"}${isNum(r.outCount) && r.outCount > 0 ? `, ${r.outCount} of them out` : ""}; the whole table is on the Season page.`) : null;
      return el(
        "div",
        { class: "race" },
        el(
          "div",
          { class: "race__top" },
          el("div", { class: "race__standings" }, el("h4", { class: "race__head" }, "The title game", el("small", {}, ` the top ${isNum(r.spots) ? r.spots : 2} by conference record`)), standings, others, status ? el("p", { class: "race__status" }, status) : null, linesList(r)),
          el("div", { class: "race__playoff" }, el("h4", { class: "race__head" }, "The playoff", el("small", {}, " 12 teams: 5 champions, 7 at large")), pictureBlock(picture) || note("The picture appears with the first poll.", { kind: "empty" })),
        ),
        el("div", { class: "race__watch" }, el("h4", { class: "race__head" }, "Games that help us this week", el("small", {}, " the same games wear a chip on the Top 25 page and a dot on the ticker")), watchTable(r)),
      );
    },
  });
}
