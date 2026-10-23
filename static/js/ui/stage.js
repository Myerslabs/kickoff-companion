// In Game on one screen (freeze wave F5, the owner's mock of 2026-10-20: the big screen mirrors the tablet, so In Game
// itself fits one landscape screen with nothing to scroll). The pieces the one-screen "stage" is built from; views/live.js
// lays them out and keeps them fresh, on the tablet and on the board alike.
//
// The layout pass (owner 2026-10-22, https://claude.ai/artifact/Mrt8VH6khBN5GNZ1Mrzbdt): the score line sits at the bottom
// above the ticker on one line, dropping its least-needed parts by width; the panels have no title bars; the box score
// keeps one passer, two rushers and three receivers a team and holds still; the shot chart follows the offense on the field.
//
//   wpSummary(s, { usHome, pregame })                  { pct, kickoff } for us, 0..1 each, or nulls: the latest scoreboard
//                                                        reading (the series' last point), the pregame number before kickoff
//   lastPlayParts(play, { abbr })                      { words, who, ppa, when } or null: the line drops ppa and when first
//   lastPlayWords(play, { abbr })                      "TD pass, 29 yds, BLUE · +3.4 PPA · Q1 2:08", or null
//   playWords(play)                                    the short words for a play type ("TD pass", "Incomplete pass", "Run")
//   stripExtras({ wp, lastPlay, usAbbr })              the line's right side: the percentage and the last play (lastPlay is
//                                                        lastPlayParts' answer, or a string)
//   lastPlaysList({ plays, us, them, limit })          the newest plays, one row each (clock, side, situation, PPA, words)
//   scoreCell({ s, us, them, usHome, extra })          Score by quarter over the four drive lines, `extra` (the trivia) under
//   stageBox({ us, them, usCats, themCats, onTap })    both teams' short box scores side by side
//   shortBox(categories, { team, side, onTap })        one team's: the leaders by yards, one passer, two rushers, three receivers
//   offenseHead({ abbr, side, counts })                the shot chart's end zone: whose offense, its passes and runs
//   stageTools({ delayLabel, onDelay, onRadio, onNotes, onInvite })   the five tool buttons, pinned at the row's right end
//   driveLines(summary, usTeam, themTeam)              [{ label, us, them }] (exported for the tests)

import { DASH, el, fmtClock, fmtPct, fmtSigned, isNum, obj, period, records, situationText, text } from "./dom.js";
import { BOX_COLUMNS, boxRows } from "./box-columns.js";
import { statTable } from "./stat-table.js";
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

/** The last play in its parts: { words: "TD pass, 29 yds", who: "BLUE", ppa: "+3.4 PPA", when: "Q1 2:08" }, any of the last
 *  three null when unknown; null without a play. The score line drops `ppa` and `when` first, then `who`. */
export function lastPlayParts(play, { abbr } = {}) {
  if (!play || typeof play !== "object") return null;
  const yards = scrimmage(play) && isNum(play.yardsGained) ? `${fmtSigned(play.yardsGained, 0)} yds` : null;
  const named = typeof abbr === "function" ? abbr(play.offense) : typeof play.offense === "string" ? play.offense : null;
  const who = typeof named === "string" && named ? named : null;
  return {
    words: [playWords(play), yards].filter(Boolean).join(", "),
    who,
    ppa: isNum(play.ppa) ? `${fmtSigned(play.ppa, 1)} PPA` : null,
    when: isNum(play.period) ? `${period(play.period)} ${fmtClock(play.clock)}` : null,
  };
}

/** "TD pass, 29 yds, BLUE · +3.4 PPA · Q1 2:08": the play's words, its yards on a real down, who had the ball, its value and when. */
export function lastPlayWords(play, { abbr } = {}) {
  const parts = lastPlayParts(play, { abbr });
  if (!parts) return null;
  return [[parts.words, parts.who].filter(Boolean).join(", "), parts.ppa, parts.when].filter(Boolean).join(" · ");
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

/** The score line's right side: the percentage, then the last play. Nothing when neither is known. Each part the line may
 *  drop on a narrow screen is its own span (the kickoff number, the play's team, PPA and clock; CSS decides by width). */
export function stripExtras({ wp = {}, lastPlay = null, usAbbr = DASH } = {}) {
  const pct = isNum(wp.pct) ? wp.pct : isNum(wp.kickoff) ? wp.kickoff : null;
  const wpNode = pct === null ? null : el(
    "span",
    { class: "strip__wp", "aria-label": `Win probability: ${fmtPct(pct)} ${text(usAbbr)}` },
    el("b", { class: "strip__wp-pct", dataset: { k: "strip:wp" } }, fmtPct(pct)),
    el("span", { class: "strip__wp-who" }, `${text(usAbbr)} to win`),
    isNum(wp.pct) && isNum(wp.kickoff) && fmtPct(wp.kickoff) !== fmtPct(wp.pct) ? el("small", { class: "strip__wp-kick" }, `${fmtPct(wp.kickoff)} at kickoff`) : isNum(wp.pct) ? null : el("small", { class: "strip__wp-kick" }, "at kickoff"),
  );
  const parts = typeof lastPlay === "string" ? (lastPlay ? { words: lastPlay } : null) : lastPlay && typeof lastPlay === "object" && lastPlay.words ? lastPlay : null;
  const lastNode = parts
    ? el(
        "span",
        { class: "strip__last" },
        el("b", { class: "strip__last-label" }, "Last play"),
        el(
          "span",
          { class: "strip__last-words", dataset: { k: "strip:last" } },
          text(parts.words),
          parts.who ? el("span", { class: "strip__last-who" }, `, ${text(parts.who)}`) : null,
          parts.ppa ? el("span", { class: "strip__last-ppa" }, ` · ${text(parts.ppa)}`) : null,
          parts.when ? el("span", { class: "strip__last-when" }, ` · ${text(parts.when)}`) : null,
        ),
      )
    : null;
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

/** Score by quarter, then the drive lines, then `extra` (the trivia standings, owner 2026-10-22) at the cell's foot. `us` and
 *  `them` are { name, abbr }. */
export function scoreCell({ s = {}, us = {}, them = {}, usHome = true, extra = null } = {}) {
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
    extra,
  );
}

// The short box (owner 2026-10-22): the leaders by yards, QBR left out (it reads "–" during a game; the Box score panel keeps it)
export const SHORT_BOX = [["passing", 1], ["rushing", 2], ["receiving", 3]];

const yardsOf = (row) => (isNum(row.YDS) ? row.YDS : typeof row.YDS === "string" && Number.isFinite(Number(row.YDS)) ? Number(row.YDS) : -Infinity);

/** One team's short box: one table per category with lines, the team's abbreviation at the head of the first. Rows are in
 *  yards order and never re-sort, the heads never stick (the In Game bug of 2026-10-22: a stuck head covered the passer). */
export function shortBox(categories, { team = {}, side = "us", onTap } = {}) {
  const cats = obj(categories);
  const tables = SHORT_BOX.filter(([name]) => records(cats[name]).length).map(([name, keep]) => {
    const rows = boxRows(cats[name]).sort((a, b) => yardsOf(b) - yardsOf(a)).slice(0, keep);
    return statTable({ columns: BOX_COLUMNS[name].filter((c) => c.key !== "QBR"), rows, compact: true, sizes: true, sortable: false, onRowTap: typeof onTap === "function" ? onTap : undefined });
  });
  if (!tables.length) return el("p", { class: "note stage-box__empty" }, `${text(team.abbr)}: player lines appear after the first pass or run.`);
  const firstHead = tables[0].querySelector("thead th");
  if (firstHead) firstHead.prepend(el("b", { class: `stage-box__abbr stage-box__abbr--${side}`, title: text(team.name) }, text(team.abbr)));
  return el("div", { class: "stage-box__tables" }, tables);
}

/** Both teams' short box scores side by side (owner 2026-10-20: "right and left, not up and down"), the team's color down
 *  each half's edge. `usCats` and `themCats` are the live state's playerStats for each team. */
export function stageBox({ us = {}, them = {}, usCats, themCats, onTap } = {}) {
  const half = (side, team, cats) => el("div", { class: `stage-box__half stage-box__half--${side}` }, shortBox(cats, { team, side, onTap: onTap ? (row) => onTap(row, side) : undefined }));
  return el("div", { class: "stage-box" }, half("us", us, usCats), half("them", them, themCats));
}

/** The shot chart's end zone (owner 2026-10-22: the chart follows the offense on the field): whose offense, in its color, and
 *  how many passes and runs are charted. */
export function offenseHead({ abbr, side = "us", counts = "" } = {}) {
  return el(
    "div",
    { class: `shot-endzone shot-endzone--${side === "them" ? "them" : "us"}` },
    el("b", { class: "shot-endzone__team" }, `${text(abbr)} offense`),
    counts ? el("span", { class: "shot-endzone__counts" }, counts) : null,
  );
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
