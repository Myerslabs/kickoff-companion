// Table sizes (owner 2026-10-10; the Game program's matchup band was the test bed, locked at three widths).
// Every table draws at one of three sizes by its OWN box, never the screen, so a side sheet and a narrow
// column follow the same steps as a phone:
//   large   as much information as there is: every column, whole heads and names, the hints
//   medium  a good amount that looks nice: the national rank only, the school, middle-length stat names
//   small   as small as it goes and still says it: the abbreviation, PPG, no chips, no hints
// Nothing wraps and nothing scrolls sideways: words shorten, then columns drop; a table that cannot fit even
// at small shows at small anyway, the minimal table, never a note ("I would rather always show the minimal table",
// 2026-10-10; applySize(wrap, "none") and sizeNote stay for a caller that wants the note on purpose).
// A thin line between every column, at every size.
//
//   SIZES                       ["large", "medium", "small"], widest first
//   labelForms(label)           { long, mid, short } for a stat name, a head or a group title (unknown: all three the label)
//   fitSize(wrap, table, apply) apply(size) each size widest first until the table fits its wrap; "none" when none does.
//                               null when there is no layout engine to measure with (the Node tests).
//   watchSize(wrap, measure)    re-measure on resize, on the fonts arriving, and (with ResizeObserver) when the wrap
//                               is unfolded or its column changes; measure is stored as wrap.measure for the shared hook.
//   sizeNote()                  the note that stands in for a dropped table.
//   DROPPED                     the data-size value of a dropped table.
//   personSteps(steps, flags)   a table of players' ladder (item 6): "<size>/<form>" steps, full names then "K. Crawford" then
//                               the surname, the reduced surname and the clip; flags (dom.js nameSteps) skip the name steps
//                               that change nothing.
//   splitStep(step)             { size, form } of a step ("small/last"); form null for a plain size.
//   applyNames(wrap, form)      the wrap's data-pn; the clip measures the widest cut at which the table fits.

import { el, isNum } from "./dom.js";

export const SIZES = ["large", "medium", "small"];
export const DROPPED = "none";

// long label -> [middle form, short form]. The middle form is one line in a 560 px table; the short form is a
// phone's word (12 characters at most). Under a Defense group the short forms repeat the offense's: the group
// head says "allowed" once for all of them.
const FORMS = {
  // the team profile (app/services/profiles.py PROFILE_ROWS)
  "Points per game": ["Points per game", "PPG"],
  "Yards per game": ["Yards per game", "YPG"],
  "Yards per play": ["Yards per play", "YPP"],
  "Pass yards per game": ["Pass yds per game", "Pass"],
  "Pass yards per attempt": ["Pass yds per att", "Y/A"],
  "Completion rate": ["Completion rate", "Comp %"],
  "Rush yards per game": ["Rush yds per game", "Rush"],
  "Rush yards per carry": ["Rush yds per carry", "Y/C"],
  "Third down": ["Third down", "3rd"],
  "Fourth down": ["Fourth down", "4th"],
  "First downs per game": ["First downs/game", "1st downs"],
  "Sacks allowed per game": ["Sacks allowed/game", "Sacked"],
  "Turnovers lost per game": ["Turnovers lost/game", "TO lost"],
  "Penalty yards per game": ["Penalty yds/game", "Pen yds"],
  "Points allowed per game": ["Pts allowed/game", "PPG"],
  "Yards allowed per game": ["Yds allowed/game", "YPG"],
  "Yards allowed per play": ["Yds allowed/play", "YPP"],
  "Pass yards allowed per game": ["Pass yds allowed", "Pass"],
  "Pass yards allowed per attempt": ["Pass yds allowed/att", "Y/A"],
  "Rush yards allowed per game": ["Rush yds allowed", "Rush"],
  "Rush yards allowed per carry": ["Rush yds allowed/carry", "Y/C"],
  "Third down allowed": ["3rd down allowed", "3rd"],
  "Sacks per game": ["Sacks per game", "Sacks"],
  "Tackles for loss per game": ["TFL per game", "TFL"],
  "Takeaways per game": ["Takeaways/game", "Takeaways"],
  "Turnover margin": ["Turnover margin", "TO margin"],
  // the advanced rows (ADVANCED_ROWS)
  "Success rate": ["Success rate", "Success"],
  Explosiveness: ["Explosiveness", "Explosive"],
  "PPA per play": ["PPA per play", "PPA"],
  "Success rate allowed": ["Success allowed", "Success"],
  "Explosiveness allowed": ["Explosive allowed", "Explosive"],
  "PPA allowed per play": ["PPA allowed/play", "PPA"],
  "Success on standard downs": ["Success, std downs", "Std downs"],
  "Success on passing downs": ["Success, pass downs", "Pass downs"],
  "PPA on passing downs": ["PPA, pass downs", "PPA pass dn"],
  "Success allowed, standard downs": ["Success alw, std downs", "Std downs"],
  "Success allowed, passing downs": ["Success alw, pass downs", "Pass downs"],
  "Run rate": ["Run rate", "Run %"],
  "PPA per rush": ["PPA per rush", "PPA rush"],
  "PPA per pass": ["PPA per pass", "PPA pass"],
  "PPA allowed per rush": ["PPA alw per rush", "PPA rush"],
  "PPA allowed per pass": ["PPA alw per pass", "PPA pass"],
  "Line yards per rush": ["Line yds per rush", "Line yds"],
  "Line yards allowed": ["Line yds allowed", "Line yds"],
  "Stuff rate": ["Stuff rate", "Stuff %"],
  "Stuff rate (defense)": ["Stuff rate (defense)", "Stuff %"],
  "Power success": ["Power success", "Power"],
  "Power success allowed": ["Power success alw", "Power"],
  "Second-level yards": ["2nd-level yds", "2nd level"],
  "Open-field yards": ["Open-field yds", "Open field"],
  "Havoc rate": ["Havoc rate", "Havoc"],
  "Havoc, front seven": ["Havoc, front seven", "Havoc F7"],
  "Havoc, secondary": ["Havoc, secondary", "Havoc DBs"],
  "Havoc allowed": ["Havoc allowed", "Havoc"],
  "Points per scoring chance": ["Pts per scoring chance", "Pts/chance"],
  "Points per scoring chance allowed": ["Pts/chance allowed", "Pts/chance"],
  "Average start, yards to goal": ["Avg start, yds to goal", "Avg start"],
  "Average start allowed, yards to goal": ["Avg start allowed", "Avg start"],
  // the program's PPA band
  "Offense, overall": ["Offense, overall", "Off all"],
  "Offense, passing": ["Offense, passing", "Off pass"],
  "Offense, rushing": ["Offense, rushing", "Off rush"],
  "Defense, overall": ["Defense, overall", "Def all"],
  "Defense, passing": ["Defense, passing", "Def pass"],
  "Defense, rushing": ["Defense, rushing", "Def rush"],
  // In Game's team play value (wave 2): a defense's rows say allowed (rule 6); the short forms as the by-game table's
  "Defense allowed, overall": ["Def allowed, overall", "Def all"],
  "Defense allowed, passing": ["Def allowed, passing", "Def pass"],
  "Defense allowed, rushing": ["Def allowed, rushing", "Def rush"],
  // the program's Talent and recruiting band
  "Talent composite": ["Talent composite", "Talent"],
  "Blue-chip ratio": ["Blue-chip ratio", "Blue chips"],
  "Blue-chip ratio, offense": ["Blue chips, offense", "BC off"],
  "Blue-chip ratio, defense": ["Blue chips, defense", "BC def"],
  "Average rating, offense": ["Avg rating, offense", "Rating off"],
  "Average rating, defense": ["Avg rating, defense", "Rating def"],
  "Roster cost (rumored)": ["Roster cost", "Cost"],
  "Returning production": ["Returning production", "Returning"],
  "Returning passing": ["Returning passing", "Ret pass"],
  "Returning receiving": ["Returning receiving", "Ret rec"],
  "Returning rushing": ["Returning rushing", "Ret rush"],
  // the leader lines
  "Conference games": ["Conference games", "Conf games"],
  // wave 2 (owner 2026-10-10): the Pre-Game Program's and In Game's other tables. Team stats (ui/team-stats.js
  // teamStatRows, the final box, the Situation panel); Points, Plays, Comp-Att, Carries, Red zone and the rest are short
  // enough as they are
  "20+ yard plays": ["20+ yd plays", "20+ plays"],
  "40+ yard plays": ["40+ yd plays", "40+ plays"],
  "Pass yards": ["Pass yards", "Pass yds"],
  "Rush yards": ["Rush yards", "Rush yds"],
  "Yards per attempt": ["Yds per att", "Y/A"],
  "Yards per carry": ["Yds per carry", "Y/C"],
  "Passing TDs": ["Passing TDs", "Pass TD"],
  "Rushing TDs": ["Rushing TDs", "Rush TD"],
  "First downs": ["First downs", "1st downs"],
  "Fumbles lost": ["Fumbles lost", "Fum lost"],
  "Interceptions thrown": ["Ints thrown", "Ints"], // it sits under Turnovers
  "Tackles for loss": ["Tackles for loss", "TFL"],
  "Time of possession": ["Time of possession", "Possession"],
  // the live feed's efficiency (FEED_ROWS), the drive summary, the splits and the live tendencies
  "Standard downs": ["Standard downs", "Std downs"],
  "Passing downs": ["Passing downs", "Pass downs"],
  "Scoring chances": ["Scoring chances", "Chances"],
  "Deserve to win": ["Deserve to win", "Deserve win"],
  "Finished drives": ["Finished drives", "Drives"],
  "Points on drives": ["Points on drives", "Points"],
  "Points per drive": ["Points per drive", "Pts/drive"],
  "Three-and-outs": ["Three-and-outs", "3-and-outs"],
  "PPA per play (no TD plays)": ["PPA/play, no TDs", "PPA"],
  // the situations, both lists (app/services/depth2.py SITUATIONS for the program's tendencies, app/live/analysis.py
  // SITUATIONS for In Game's): the same words on both pages
  "1st down": ["1st down", "1st"],
  "2nd and 1 to 3": ["2nd and 1-3", "2nd 1-3"],
  "2nd and 4 to 7": ["2nd and 4-7", "2nd 4-7"],
  "2nd and 8 or more": ["2nd and 8+", "2nd 8+"],
  "3rd and 1 to 3": ["3rd and 1-3", "3rd 1-3"],
  "3rd and 4 to 6": ["3rd and 4-6", "3rd 4-6"],
  "3rd and 7 or more": ["3rd and 7+", "3rd 7+"],
  "4th down": ["4th down", "4th"],
  "Red zone (20 and in)": ["Red zone", "Red zone"],
  "Inside the 10": ["Inside the 10", "Inside 10"],
  // the advanced box score's "Both teams" table
  "Havoc (defense)": ["Havoc (defense)", "Havoc"],
  // the opponent-adjusted matchup (app/services/depth2.py ADJUSTED_KEYS, wave 2: it held a phone 4 px past its box)
  "Adjusted EPA per play": ["Adj EPA per play", "Adj EPA"],
  "Adjusted EPA per pass": ["Adj EPA per pass", "Adj EPA pass"],
  "Adjusted EPA per rush": ["Adj EPA per rush", "Adj EPA rush"],
  "Adjusted success rate": ["Adj success rate", "Adj success"],
  "Adjusted EPA allowed per play": ["Adj EPA allowed/play", "Adj EPA alw"],
  "Adjusted success rate allowed": ["Adj success allowed", "Adj succ alw"],
  "Adjusted line yards per rush": ["Adj line yds per rush", "Adj line yds"],
  "Adjusted line yards allowed": ["Adj line yds allowed", "Adj line alw"],
  // group titles and label heads
  Offense: ["Offense", "Off"],
  Defense: ["Defense", "Def (allowed)"],
  "Per game": ["Per game", "Per game"],
  Advanced: ["Advanced", "Adv"],
  "This season": ["This season", "Season"],
  Statistic: ["Statistic", "Stat"],
  Opponent: ["Opponent", "Opp"], // Common opponents' label head (wave 2)
  "Adjusted for opponents": ["Adjusted for opponents", "Adjusted"],
  // wave 3 (owner 2026-10-10): every other page's tables, gathered in one place so each page only declares its columns.
  // The Season page's ratings (and the Ratings and national lists' names for them)
  "SP+ overall": ["SP+ overall", "SP+"],
  "SP+ offense": ["SP+ offense", "SP+ off"],
  "SP+ defense": ["SP+ defense", "SP+ def"],
  "SP+ special teams": ["SP+ special teams", "SP+ ST"],
  "Strength of schedule": ["Strength of sched", "SOS"],
  "Strength of record": ["Strength of record", "SOR"],
  "FPI strength of schedule": ["FPI strength of sched", "FPI SOS"],
  "FPI strength of record": ["FPI strength of record", "FPI SOR"],
  "Strength of schedule played (average SP+ of opponents)": ["Schedule played, SP+", "SOS played"],
  // the Résumé
  "Expected wins": ["Expected wins", "Exp wins"],
  "Wins above expected": ["Wins above expected", "Above exp"],
  "Opponents played, average SP+": ["Opp played, avg SP+", "SOS played"],
  "Opponents to come, average SP+": ["Opp to come, avg SP+", "SOS to come"],
  // the advanced table's pair names and its group titles (app/services/profiles.py ADVANCED_ROWS)
  "Success, standard downs": ["Success, std downs", "Std downs"],
  "Success, passing downs": ["Success, pass downs", "Pass downs"],
  "PPA, passing downs": ["PPA, pass downs", "PPA pass dn"],
  "Run and pass": ["Run and pass", "Run/pass"],
  "Line play": ["Line play", "Line"],
  "Finishing drives": ["Finishing drives", "Finishing"],
  "Field position": ["Field position", "Field pos"],
  // the team page's Talent and recruiting (and the returning lists)
  "Returning production (PPA)": ["Returning PPA", "Ret PPA"],
  "Returning usage": ["Returning usage", "Ret usage"],
  "Returning passing usage": ["Returning pass usage", "Ret pass use"],
  "Returning receiving usage": ["Returning rec usage", "Ret rec use"],
  "Returning rushing usage": ["Returning rush usage", "Ret rush use"],
  "Returning PPA, total": ["Returning PPA, total", "Ret PPA total"],
  // the player card's splits (Season by split, Usage)
  "All plays": ["All plays", "All"],
  "First down": ["First down", "1st"],
  "Second down": ["Second down", "2nd"],
  // the grade's parts (app/services/grades.py SPECS)
  "Touchdown rate": ["Touchdown rate", "TD %"],
  "Interception rate": ["Interception rate", "INT %"],
  "Play value per pass (PPA)": ["PPA per pass", "PPA pass"],
  "Opponent-adjusted passing value": ["Adj passing value", "Adj pass"],
  "Rushing yards a game": ["Rush yds a game", "Rush YPG"],
  "Rushing touchdowns a game": ["Rush TD a game", "Rush TD"],
  "Play value per rush (PPA)": ["PPA per rush", "PPA rush"],
  "Opponent-adjusted rushing value": ["Adj rushing value", "Adj rush"],
  "Receiving yards a game": ["Rec yds a game", "Rec YPG"],
  "Yards per catch": ["Yards per catch", "Y/R"],
  "Catches a game": ["Catches a game", "Rec/game"],
  "Receiving touchdowns a game": ["Rec TD a game", "Rec TD"],
  "Tackles for loss a game": ["TFL a game", "TFL"],
  "Sacks a game": ["Sacks a game", "Sacks"],
  "Quarterback hurries a game": ["QB hurries a game", "Hurries"],
  "Tackles a game": ["Tackles a game", "Tkl"],
  "Passes defended a game": ["Passes defended/game", "PD"],
  "Interceptions a game": ["INT a game", "INT"],
  "Field goal rate": ["Field goal rate", "FG %"],
  "Field goals a game": ["Field goals a game", "FG/game"],
  "Longest field goal": ["Longest field goal", "Long FG"],
  "Extra point rate": ["Extra point rate", "XP %"],
  "Points added above replacement": ["Pts above replacement", "PAAR"],
  "Yards per punt": ["Yards per punt", "Y/P"],
  "Punts inside the 20, per punt": ["Inside the 20/punt", "In 20 %"],
  "Touchbacks per punt": ["Touchbacks/punt", "TB %"],
  // the national lists' value heads (app/services/national.py: the boards and the adjusted boards)
  "Passing yards": ["Passing yards", "Pass yds"],
  "Rushing yards": ["Rushing yards", "Rush yds"],
  "Receiving yards": ["Receiving yards", "Rec yds"],
  "Field goals made": ["Field goals made", "FGM"],
  "Punting average": ["Punting average", "Punt avg"],
  "Play value, PPA per play": ["PPA per play", "PPA"],
  "Kicker points added above replacement": ["Kicker PAAR", "PAAR"],
  "Adjusted passing EPA per play": ["Adj passing EPA/play", "Adj pass EPA"],
  "Adjusted rushing EPA per play": ["Adj rushing EPA/play", "Adj rush EPA"],
  // the matchup sheet's third group (app/services/matchup.py SIDE_GROUPS)
  "Both sides": ["Both sides", "Both"],
  // the Season in review's facts
  "Best win over a ranked team": ["Best ranked win", "Ranked win"],
  "Against ranked teams": ["Against ranked", "vs ranked"],
  "Games decided by 8 or fewer": ["Decided by 8 or fewer", "Close games"],
  "Longest winning streak": ["Longest win streak", "Win streak"],
  "The season ended on": ["Ended on", "Ended"],
  "Current streak": ["Current streak", "Streak"],
};

/** The three forms of a label; a label the table has no forms for keeps its words at every size. */
export function labelForms(label) {
  const long = typeof label === "string" ? label.trim() : "";
  const forms = FORMS[long];
  if (!forms) return { long, mid: long, short: long };
  return { long, mid: forms[0], short: forms[1] };
}

/** Every label with forms (the tests check the server's row labels against it). */
export function knownLabels() {
  return Object.keys(FORMS);
}

/** A table at width 100% grows past its wrap only when its content must: its own width is the measure. (Not scrollWidth:
    a linked chip's invisible 44 px press area pokes a few pixels past the last cell and would count as an overflow.) */
function fits(wrap, table) {
  const wide = isNum(table.offsetWidth) && table.offsetWidth > 0 ? table.offsetWidth : table.scrollWidth;
  const room = wrap.clientWidth;
  return isNum(wide) && isNum(room) && wide <= room + 1;
}

/**
 * Try each step widest first and keep the first that fits the wrap; the last step (small) stays when even it does not
 * (owner 2026-10-10, after the "turn the device sideways" note on his phone: "I would rather always show the minimal table").
 * A kit with a step between two sizes (medium with the abbreviations) passes its own list.
 * null without a layout engine (nothing measured, nothing applied).
 */
export function fitSize(wrap, table, apply, steps = SIZES) {
  if (!wrap || !table || !isNum(wrap.clientWidth) || wrap.clientWidth <= 0) return null;
  let last = null;
  for (const size of steps) {
    apply(size);
    last = size;
    if (fits(wrap, table)) return size;
  }
  return last;
}

// Player names (item 6, owner 2026-10-11): a table with a player column steps down as ONE table, so a column never mixes
// "Keegan Crawford" with "K. Harrington": large with full names, large with "K. Crawford", medium and small with "K. Crawford", small
// with the surname, small with the reduced surname ("Brackwater-M."), and last the clip, the reduced form cut with an
// ellipsis at a measured width. A step is "<size>/<form>"; a name step that changes no name in the table is skipped.
const NAME_FLOOR = 48; // the narrowest a clipped name gets: a few letters and the ellipsis
const NAME_STEPS = ["full", "initial", "last", "reduced", "clip"];

/** The steps of a table with player names, from its sizes (a kit's own list: the two-team "medium:abbr") and the name
 *  steps that change anything (dom.js nameSteps: { any, initial, last, reduced }). */
export function personSteps(steps = SIZES, flags = {}) {
  const f = flags && typeof flags === "object" ? flags : {};
  const sizes = Array.isArray(steps) && steps.length ? steps : SIZES;
  const out = [`${sizes[0]}/full`];
  if (f.initial) out.push(`${sizes[0]}/initial`);
  for (const size of sizes.slice(1)) out.push(`${size}/initial`);
  const small = sizes[sizes.length - 1];
  if (f.last) out.push(`${small}/last`);
  if (f.reduced) out.push(`${small}/reduced`);
  if (f.any) out.push(`${small}/clip`);
  return out;
}

/** A step's two parts: "medium:abbr/initial" -> { size: "medium:abbr", form: "initial" }; no form for a plain size. */
export function splitStep(step) {
  const [size, form] = String(step || "large").split("/");
  return { size: size || "large", form: NAME_STEPS.includes(form) ? form : null };
}

/**
 * Show one name form across a wrap (data-pn; no form clears it). The clip measures: the widest cut (--pn-max, the names'
 * largest width) at which the table fits its wrap, found by halving between the narrowest a name gets and its widest (a
 * handful of layouts, and only for a table that reached the clip). When even the narrowest cut does not fit, it stays only
 * if it narrowed the table (a head wider than its names gains nothing from cutting them).
 */
export function applyNames(wrap, form) {
  if (!wrap || !wrap.dataset) return;
  const style = wrap.style && typeof wrap.style.removeProperty === "function" ? wrap.style : null;
  if (style) style.removeProperty("--pn-max");
  if (!form) {
    delete wrap.dataset.pn;
    return;
  }
  wrap.dataset.pn = form;
  const table = form === "clip" && typeof wrap.querySelector === "function" ? wrap.querySelector("table") : null;
  if (!table || !style || !isNum(wrap.clientWidth) || wrap.clientWidth <= 0) return; // nothing to measure with (the tests)
  const wide = () => (isNum(table.offsetWidth) && table.offsetWidth > 0 ? table.offsetWidth : table.scrollWidth);
  const fitsAt = (px) => {
    style.setProperty("--pn-max", `${px}px`);
    return wide() <= wrap.clientWidth + 1;
  };
  const uncut = wide();
  if (uncut <= wrap.clientWidth + 1) return;
  const widths = [...wrap.querySelectorAll(".pn")].map((n) => n.getBoundingClientRect().width).filter((w) => isNum(w) && w > 0);
  const widest = widths.length ? Math.ceil(Math.max(...widths)) : 0;
  if (widest <= NAME_FLOOR) return;
  if (!fitsAt(NAME_FLOOR)) {
    if (wide() >= uncut - 0.5) style.removeProperty("--pn-max");
    return;
  }
  let fit = NAME_FLOOR;
  let miss = widest;
  while (miss - fit > 1) {
    const mid = Math.floor((fit + miss) / 2);
    if (fitsAt(mid)) fit = mid;
    else miss = mid;
  }
  style.setProperty("--pn-max", `${fit}px`);
}

/** The note that stands in for a table too wide for its box even at small. */
export function sizeNote() {
  return el("p", { class: "note size-note" }, "This table needs a wider screen. Turn the device sideways to see it.");
}

const observed = typeof WeakSet === "function" ? new WeakSet() : null;
let fontsHooked = false;

/**
 * Keep a wrap measured: now (once it is on the page), on every window resize (the stat table's one shared
 * listener calls wrap.measure), when the fonts arrive, and when the wrap itself changes width (a band
 * unfolding, a column count changing) through a ResizeObserver where there is one.
 */
export function watchSize(wrap, measure) {
  const safe = () => {
    try {
      measure();
    } catch (error) {
      console.error("tables: could not measure a table.", error);
    }
  };
  wrap.measure = safe;
  if (!isNum(wrap.clientWidth) || typeof requestAnimationFrame !== "function") return; // no layout engine (tests)
  let tries = 0;
  const first = () => {
    if (wrap.isConnected && wrap.clientWidth > 0) safe();
    else if (tries++ < 10) requestAnimationFrame(first);
  };
  requestAnimationFrame(first);
  if (typeof ResizeObserver === "function" && observed && !observed.has(wrap)) {
    observed.add(wrap);
    let last = -1;
    const observer = new ResizeObserver(() => {
      const width = wrap.clientWidth;
      if (!isNum(width) || width === last) return; // the same width again (our own re-layout): nothing to redo
      last = width;
      safe();
    });
    observer.observe(wrap);
    wrap.sizeObserver = observer; // kept on the wrap: an observer nothing references can be collected before a table built
    // off the page (a folded band, the leader lines) is ever laid out, and the table would stay at large
  }
  if (!fontsHooked && typeof document !== "undefined" && document.fonts && document.fonts.ready && typeof document.fonts.ready.then === "function") {
    fontsHooked = true;
    const again = () => {
      for (const node of document.querySelectorAll(".stat-table-wrap")) if (typeof node.measure === "function") node.measure();
    };
    document.fonts.ready.then(again).catch(() => {});
    // 2026-10-11 (wave 3, the Season page): the fonts load as a page first uses each weight (font-display: swap), so a page
    // drawn after the first fonts arrived measured its tables in the stand-in font, wider than the real one, and kept a
    // smaller size until something else made it measure again. Every font that finishes loading measures every table again.
    if (typeof document.fonts.addEventListener === "function") document.fonts.addEventListener("loadingdone", again);
  }
}
