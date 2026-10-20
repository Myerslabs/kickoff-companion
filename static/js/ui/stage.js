// In Game on one screen (freeze wave F5, the owner's mock of 2026-10-20: the big screen mirrors the tablet, so In Game
// itself fits one landscape screen with nothing to scroll). The pieces the one-screen "stage" is built from; views/live.js
// lays them out and keeps them fresh, on the tablet and on the board alike.
//
//   wpSummary(s, { usHome, pregame })                  { pct, kickoff } for us, 0..1 each, or nulls: the latest scoreboard
//                                                        reading (the series' last point), the pregame number before kickoff
//   lastPlayWords(play, { abbr })                      "TD pass, 29 yds, BLUE · +3.4 PPA · Q1 2:08", or null
//   playWords(play)                                    the short words for a play type ("TD pass", "Incomplete pass", "Run")
//   stripExtras({ wp, lastPlay, usAbbr })              the strip's right side: the percentage and the last play
//   lastPlaysList({ plays, us, them, limit })          the newest plays, one row each (clock, side, situation, PPA, words)
//   scoreCell({ s, us, them, usHome })                 Score by quarter over the four drive lines
//   boxHalves({ us, them, usTables, themTables })      both teams' box scores side by side, each half a stepping column
//   stageTools({ delayLabel, onDelay, onRadio, onNotes, onInvite })   the five tool buttons that sit with the panel buttons
//   driveLines(summary, usTeam, themTeam)              [{ label, us, them }] (exported for the tests)

import { DASH, el, fmtClock, fmtPct, fmtSigned, isNum, obj, period, records, situationText, text } from "./dom.js";
import { quarterLine } from "./team-stats.js";

const WORDS = [
  [/touchdown/i, /pass/i, "TD pass"],
  [/touchdown/i, /rush|run/i, "TD run"],
  [/touchdown/i, /interception/i, "Pick six"],
  [/touchdown/i, /fumble/i, "Fumble return TD"],
  [/touchdown/i, /kickoff|punt/i, "Return TD"],
  [/touchdown/i, null, "Touchdown"],
  [/interception/i, null, "Interception"],
  [/fumble/i, null, "Fumble"],
  [/sack/i, null, "Sack"],
  [/incompletion|incomplete/i, null, "Incomplete pass"],
  [/pass reception|completion|pass complete/i, null, "Pass complete"],
  [/^rush|rushing|^run/i, null, "Run"],
  [/field goal good/i, null, "Field goal good"],
  [/field goal missed|missed field goal/i, null, "Field goal missed"],
  [/blocked/i, null, "Blocked kick"],
  [/extra point/i, null, "Extra point"],
  [/two point|2pt|two-point/i, null, "Two-point try"],
  [/safety/i, null, "Safety"],
  [/punt/i, null, "Punt"],
  [/kickoff/i, null, "Kickoff"],
  [/penalty/i, null, "Penalty"],
  [/timeout/i, null, "Timeout"],
  [/end period|end of period|end of half|end of game/i, null, "End of the period"],
];

/** The short words for a play type; an unknown type keeps its own name, a missing one is "Play". */
export function playWords(play) {
  const type = typeof play?.playType === "string" ? play.playType.trim() : "";
  if (!type) return "Play";
  for (const [first, second, words] of WORDS) {
    if (first.test(type) && (!second || second.test(type))) return words;
  }
  return type;
}

const scrimmage = (play) => isNum(play?.down) && play.down > 0;

/** "TD pass, 29 yds, BLUE · +3.4 PPA · Q1 2:08": the play's words, its yards on a real down, who had the ball, its value and when. */
export function lastPlayWords(play, { abbr } = {}) {
  if (!play || typeof play !== "object") return null;
  const yards = scrimmage(play) && isNum(play.yardsGained) ? `${fmtSigned(play.yardsGained, 0)} yds` : null;
  const who = typeof abbr === "function" ? abbr(play.offense) : typeof play.offense === "string" ? play.offense : null;
  const first = [playWords(play), yards, who].filter((part) => typeof part === "string" && part).join(", ");
  const ppa = isNum(play.ppa) ? `${fmtSigned(play.ppa, 1)} PPA` : null;
  const when = isNum(play.period) ? `${period(play.period)} ${fmtClock(play.clock)}` : null;
  return [first, ppa, when].filter(Boolean).join(" · ");
}

/** Our win probability now and at kickoff, 0..1 each (null when unknown). The latest scoreboard reading wins over the series. */
export function wpSummary(s, { usHome = true, pregame = null } = {}) {
  const kickoff = isNum(pregame) && pregame >= 0 && pregame <= 1 ? pregame : null;
  const live = obj(s?.liveWinProbability);
  let home = isNum(live.homeWp) && live.homeWp >= 0 && live.homeWp <= 1 ? live.homeWp : null;
  if (home === null) {
    const series = records(live.series);
    const last = series.length ? series[series.length - 1] : null;
    home = last && isNum(last.homeWp) && last.homeWp >= 0 && last.homeWp <= 1 ? last.homeWp : null;
  }
  const pct = home === null ? null : usHome ? home : 1 - home;
  return { pct, kickoff };
}

/** The strip's right side on the stage: the percentage, then the last play. Nothing when neither is known. */
export function stripExtras({ wp = {}, lastPlay = null, usAbbr = DASH } = {}) {
  const pct = isNum(wp.pct) ? wp.pct : isNum(wp.kickoff) ? wp.kickoff : null;
  const wpNode = pct === null ? null : el(
    "span",
    { class: "strip__wp", "aria-label": `Win probability: ${fmtPct(pct)} ${text(usAbbr)}` },
    el("b", { class: "strip__wp-pct", dataset: { k: "strip:wp" } }, fmtPct(pct)),
    el("span", { class: "strip__wp-who" }, `${text(usAbbr)} to win`),
    isNum(wp.pct) && isNum(wp.kickoff) && fmtPct(wp.kickoff) !== fmtPct(wp.pct) ? el("small", { class: "strip__wp-kick" }, `${fmtPct(wp.kickoff)} at kickoff`) : isNum(wp.pct) ? null : el("small", { class: "strip__wp-kick" }, "at kickoff"),
  );
  const lastNode = lastPlay ? el("span", { class: "strip__last" }, el("b", { class: "strip__last-label" }, "Last play"), el("span", { class: "strip__last-words", dataset: { k: "strip:last" } }, lastPlay)) : null;
  if (!wpNode && !lastNode) return null;
  return el("span", { class: "strip__extras" }, wpNode, lastNode);
}

/**
 * The newest plays, one row each: when, whose, the down and distance, the value, and the words. `us` and `them` are
 * { name, abbr }; a play of neither side (a bad record) reads as theirs.
 */
export function lastPlaysList({ plays = [], us = {}, them = {}, limit = 5 } = {}) {
  const rows = records(plays).slice(0, Math.max(0, limit));
  if (!rows.length) return el("p", { class: "note stage-plays__empty" }, "Plays appear after kickoff.");
  return el(
    "ol",
    { class: "stage-plays", "aria-label": `The last ${rows.length} plays, newest first` },
    rows.map((play) => {
      const isUs = play.offense === us.name;
      const offense = isUs ? us : them;
      const defense = isUs ? them : us;
      const words = [playWords(play), scrimmage(play) && isNum(play.yardsGained) ? `${fmtSigned(play.yardsGained, 0)} yds` : null].filter(Boolean).join(", ");
      const situation = scrimmage(play) ? situationText({ down: play.down, distance: play.distance, yardsToGoal: play.yardsToGoal, offenseAbbr: offense.abbr, defenseAbbr: defense.abbr }) : typeof play.playType === "string" && /kickoff/i.test(play.playType) ? "kickoff" : "";
      return el(
        "li",
        { class: `stage-play stage-play--${isUs ? "us" : "them"}${play.scoring === true ? " stage-play--score" : ""}`, dataset: { play: play.id ?? "" } },
        el(
          "span",
          { class: "stage-play__line" },
          el("span", { class: "stage-play__clock" }, isNum(play.period) ? `${period(play.period)} ${fmtClock(play.clock)}` : DASH),
          el("b", { class: `stage-play__side stage-play__side--${isUs ? "us" : "them"}` }, text(offense.abbr)),
          situation ? el("span", { class: "stage-play__sit" }, situation) : null,
          isNum(play.ppa) ? el("b", { class: `stage-play__ppa${play.ppa > 0 ? " stage-play__ppa--gain" : play.ppa < 0 ? " stage-play__ppa--loss" : ""}`, title: "Predicted points added" }, fmtSigned(play.ppa, 1)) : null,
        ),
        el("span", { class: "stage-play__words", title: typeof play.text === "string" ? play.text : null }, words),
      );
    }),
  );
}

export const DRIVE_LINES = [
  ["Drives", "drives", 0],
  ["Points per drive", "pointsPerDrive", 1],
  ["Scoring chances", "opportunities", 0],
  ["Three and outs", "threeAndOuts", 0],
];

/** The four drive lines from the engine's drive summary ({team: {drives, pointsPerDrive, opportunities, threeAndOuts}}). */
export function driveLines(summary, usTeam, themTeam) {
  const all = obj(summary);
  const side = (team) => obj(all[team]);
  const show = (value, decimals) => (isNum(value) ? value.toFixed(decimals) : DASH);
  return DRIVE_LINES.map(([label, key, decimals]) => ({ label, us: show(side(usTeam)[key], decimals), them: show(side(themTeam)[key], decimals) }));
}

/** Score by quarter, then the drive lines. `us` and `them` are { name, abbr }. */
export function scoreCell({ s = {}, us = {}, them = {}, usHome = true } = {}) {
  const lines = driveLines(s.driveSummary, us.name, them.name);
  return el(
    "div",
    { class: "stage-score" },
    quarterLine({ us: { abbr: us.abbr, scores: usHome ? s.homeLineScores : s.awayLineScores, total: usHome ? s.homeScore : s.awayScore }, them: { abbr: them.abbr, scores: usHome ? s.awayLineScores : s.homeLineScores, total: usHome ? s.awayScore : s.homeScore } }),
    el(
      "div",
      { class: "stage-drives", role: "table", "aria-label": "Drives" },
      el("div", { class: "stage-drives__head", role: "row" }, el("span", {}, "Drives"), el("b", { class: "stage-drives__us" }, text(us.abbr)), el("b", { class: "stage-drives__them" }, text(them.abbr))),
      lines.map((line) => el("div", { class: "stage-drives__row", role: "row" }, el("span", { class: "stage-drives__label" }, line.label), el("span", { class: "stage-drives__val" }, line.us), el("span", { class: "stage-drives__val" }, line.them))),
    ),
  );
}

/** Both teams' box scores side by side (owner 2026-10-20: "right and left, not up and down"), each half its own stepping column. */
export function boxHalves({ us = {}, them = {}, usTables, themTables } = {}) {
  const half = (side, team, tables) =>
    el(
      "div",
      { class: `stage-box__half stage-box__half--${side}` },
      el("div", { class: `stage-box__team stage-box__team--${side}` }, el("b", {}, text(team.abbr)), el("span", {}, text(team.name))),
      el("div", { class: "stage-box__scroll stage-step" }, tables || null),
    );
  return el("div", { class: "stage-box" }, half("us", us, usTables), half("them", them, themTables));
}

/** The five tools as buttons of the panel row's kind (owner 2026-10-20: "where the touch is"); the Big screen one is a link. */
export function stageTools({ delayLabel = "Delay", onDelay, onRadio, onNotes, onInvite, boardHref = "#board" } = {}) {
  const button = (label, onclick, extra = {}) => el("button", { class: "remote__btn remote__btn--tool", type: "button", "aria-haspopup": "dialog", onclick, ...extra }, text(label));
  const delay = button(delayLabel, onDelay, { class: "remote__btn remote__btn--tool remote__delay" });
  const nodes = [delay, button("Radio", onRadio), button("Notes", onNotes), button("Invite", onInvite), el("a", { class: "remote__btn remote__btn--tool", href: boardHref }, "Big screen")];
  nodes.setDelayLabel = (label) => {
    delay.textContent = text(label);
  };
  return nodes;
}
