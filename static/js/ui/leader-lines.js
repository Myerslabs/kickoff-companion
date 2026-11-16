// Leaders side by side (BUG-14, the owner's board of 2026-10-26: "Leaders
// side by side is unreadable", wanted "the same band type, pulled to the middle, not columns turned sideways"). Each category
// is drawn in the Tale of the tape's kit: the two leaders over it, pulled to the middle with the category between them, then
// one row a stat, Statistic | FBS rank | our value | Edge | their value | FBS rank, the bar leaning to the better number
// (fewer interceptions is better; ui/two-team.js tugShare, longer for a bigger gap), the better number bold; the line over
// conference games under the stats. No rank is a dash the chip's width, never a blank (the kit's rule, owner
// 2026-10-10). On a phone the rank columns go and the conference line keeps its lead number alone; from a band of
// 1300 px two categories sit side by side. The numbers come from /api/program/<id>/leaders
// (app/services/leader_lines.py) once it answers (it can take a moment the first time a week's conference games are
// read); until then each category shows the program's own leader line, the category's key number.
// Phase 17 #17 (owner 2026-10-07: "show overall stats, to include secondary stats, but also conference stats") still holds:
// every stat the service lists, its FBS rank, and the conference-game line.
//
//   leaderPairs(categories, { usAbbr, themAbbr, usTeam, themTeam, usConfGames, themConfGames, onTap })  -> <div class="lpairs">
//       category: { id, label, category, stat, format, us: player, them: player, more }
//         player  { name, playerId, number, position, headshotUrl, value }: the program's leaders payload side
//         more    the detailed category from /api/program/<id>/leaders ({ category, us: { detail, conferenceGames }, them }), or null
//       onTap(player, "us" | "them") opens the card (a leader with no player id is not a button).
//   leaderPair(category, opts)       one category
//   statWords(stat, category)        { long, short }: "Tackles for loss" and "TFL"
//   levelNames(root)                 each category's two names in the shorter form of the two (run after every fit)
//   confGamesText(category, stats)   "410 yds, 31/45, 3 TD, 1 int" from season-style totals, or null
//   confGamesShort(category, stats)  "410 yds", the line's lead number alone, or null

import { DASH, el, fmtStat, isNum, obj, personName, playerFace, settleNames, text, watchNames } from "./dom.js";
import { leaderLine, statLine } from "./leaders.js";
import { nationalHref } from "./national-link.js";
import { statFormat, statLabel } from "./stat-labels.js";
import { rankChip } from "./stat-table.js";
import { listLink, tugShare, twoTeamLeader } from "./two-team.js";

// the board's whole stat names, and the short ones a phone shows (CFBD's keys; anything else keeps its stat-labels word)
const WORDS = {
  YDS: ["Yards", "Yds"],
  TD: ["Touchdowns", "TD"],
  INT: ["Interceptions", "Int"],
  COMPLETIONS: ["Completions", "Cmp"],
  ATT: ["Attempts", "Att"],
  YPA: ["Yards a pass", "Y/A"],
  QBR: ["QBR", "QBR"],
  CAR: ["Carries", "Car"],
  YPC: ["Yards a carry", "Y/C"],
  LONG: ["Longest", "Long"],
  REC: ["Receptions", "Rec"],
  YPR: ["Yards a catch", "Y/R"],
  AVG: ["Average", "Avg"],
  TOT: ["Tackles", "Tkl"],
  SOLO: ["Solo", "Solo"],
  TFL: ["Tackles for loss", "TFL"],
  SACKS: ["Sacks", "Sacks"],
  "QB HUR": ["Hurries", "Hurries"],
  PD: ["Passes defended", "PD"],
  FGM: ["Field goals made", "FGM"],
  FGA: ["Field goal tries", "FGA"],
  XPM: ["Extra points made", "XPM"],
  XPA: ["Extra point tries", "XPA"],
  PTS: ["Points", "Pts"],
  NO: ["Punts", "No."],
  YPP: ["Yards a punt", "Avg"],
  "IN 20": ["Inside the 20", "In 20"],
  TB: ["Touchbacks", "TB"],
  FUM: ["Fumbles", "Fum"],
  LOST: ["Fumbles lost", "Lost"],
};

export function statWords(stat, category) {
  const key = typeof stat === "string" ? stat.trim().toUpperCase() : "";
  if (key === "PCT") return String(category || "").toLowerCase() === "kicking" ? { long: "Field goal %", short: "FG %" } : { long: "Completion %", short: "Comp %" };
  const words = WORDS[key];
  if (words) return { long: words[0], short: words[1] };
  const label = statLabel(stat, category);
  return { long: label, short: label };
}

function statsOf(side) {
  return (Array.isArray(obj(obj(side).detail).stats) ? obj(side).detail.stats : []).filter((s) => s && typeof s === "object" && typeof s.stat === "string");
}

/** "410 yds, 31/45, 3 TD, 1 int": the conference-game totals in the leader card's own words. */
export function confGamesText(category, stats) {
  const s = obj(stats);
  if (!Object.values(s).some(isNum)) return null;
  const box = { ...s };
  if (isNum(s.YDS)) box.YDS = fmtStat(s.YDS, "0f"); // "1,302 yds"
  if (category === "passing" && isNum(s.COMPLETIONS) && isNum(s.ATT)) box["C/ATT"] = `${s.COMPLETIONS}/${s.ATT}`;
  const line = leaderLine(category, box);
  return [line.hero, line.rest].filter((part) => typeof part === "string" && part.trim() && !/^(–|-)?\s*(yds|tkl)?$/.test(part.trim())).join(", ") || null;
}

/** "410 yds": the conference-game line's lead number alone, so a phone's row keeps its width (tables wave 2). */
export function confGamesShort(category, stats) {
  const s = obj(stats);
  if (!Object.values(s).some(isNum)) return null;
  const hero = leaderLine(category, isNum(s.YDS) ? { ...s, YDS: fmtStat(s.YDS, "0f") } : { ...s }).hero;
  return typeof hero === "string" && hero.trim() && !/^(–|-)?\s*(yds|tkl)?$/.test(hero.trim()) ? hero.trim() : null;
}

/** One side of a stat row: the value, its FBS rank and the rank's list. */
function side(entry, team) {
  if (!entry) return { value: null };
  const nat = obj(entry.national);
  const metric = typeof entry.metric === "string" && entry.metric ? entry.metric : null;
  return {
    value: isNum(entry.value) ? entry.value : null,
    rank: isNum(nat.rank) ? nat.rank : null,
    of: isNum(nat.of) ? nat.of : null,
    href: metric ? nationalHref(metric, { team }) : null,
  };
}

function idOf(player) {
  const id = obj(player).playerId;
  return id === undefined || id === null ? "" : String(id).trim();
}

/** A leader over the stats, pulled to the middle: the name and "FLA QB" beside the face, the face against the category. A
 *  button to the card when the chart knows who he is; the empty side says so at the same place. */
function who(player, which, abbr, onTap) {
  const p = obj(player);
  const name = typeof p.name === "string" && p.name.trim() ? p.name.trim() : null;
  if (!name) return el("div", { class: `lpair__who lpair__who--${which} lpair__who--empty` }, el("span", { class: "lpair__id" }, el("span", { class: "lpair__name" }, `No ${text(abbr)} line yet`)));
  const meta = [text(abbr), typeof p.position === "string" && p.position.trim() && p.position !== DASH ? p.position.trim() : null].filter(Boolean).join(" ");
  const id = el("span", { class: "lpair__id" }, el("span", { class: "lpair__name" }, personName(name, { fit: true })), el("small", { class: "lpair__meta" }, meta || DASH));
  const face = el("span", { class: "lpair__face" }, playerFace(p, { them: which === "them", abbr, size: 44 }));
  const inner = which === "us" ? [id, face] : [face, id];
  if (idOf(p) && typeof onTap === "function") return el("button", { class: `lpair__who lpair__who--${which}`, type: "button", "aria-label": `${name}: open the player card`, onclick: () => onTap(p, which) }, inner);
  return el("div", { class: `lpair__who lpair__who--${which}` }, inner);
}

/** "Passing" over "yards": the category's first word as its title, the rest under it. */
function title(label) {
  const words = text(label).trim().split(/\s+/);
  const lead = words.slice(1).join(" ");
  return el("div", { class: "lpair__title" }, el("b", {}, words[0] || DASH), lead ? el("small", {}, lead) : null);
}

/** A rank cell: the chip, else a dash the chip's width (no national list for the stat, or the list leaves the player off). */
function rankCell(s, which, label) {
  const chip = isNum(s.rank) ? rankChip(s.rank, s.of, { href: s.href, label: `${label}, FBS` }) : null;
  return el("span", { class: `lpair__rank lpair__rank--${which}` }, chip || el("span", { class: "lpair__norank", title: "No FBS rank" }, DASH));
}

function valueCell(s, which, row, label) {
  const shown = typeof s.text === "string" && s.text ? s.text : isNum(s.value) ? fmtStat(s.value, row.format) : DASH;
  const tone = row.lead === which ? " lead" : row.lead === "us" || row.lead === "them" ? " trail" : "";
  const body = shown !== DASH && s.href ? listLink(s.href, shown, { rank: s.rank, of: s.of, name: label, className: "lpair__val-link" }) : shown;
  return el("b", { class: `lpair__val lpair__val--${which}${tone}` }, body);
}

/** The Edge column: the kit's tug-of-war bar, leaning to the better number. */
function edgeCell(row, { usAbbr, themAbbr }) {
  const track = el("span", { class: "tug", role: "img" }, el("span", { class: "tug__mid" }));
  let says = row.lead === "even" ? "Even" : "No edge to show";
  if (row.lead === "us" || row.lead === "them") {
    track.append(el("span", { class: `tug__bar tug__bar--${row.lead}`, style: { width: `${Math.round(tugShare(row) * 50)}%` } }));
    says = `${row.lead === "us" ? text(usAbbr) : text(themAbbr)} has the edge`;
  }
  track.setAttribute("aria-label", says);
  track.setAttribute("title", says);
  return el("span", { class: "lpair__edge" }, track);
}

function words(forms) {
  return forms.long === forms.short ? el("span", { class: "lpair__words" }, forms.long) : el("span", { class: "lpair__words" }, el("span", { class: "lpair__long" }, forms.long), el("span", { class: "lpair__short", "aria-hidden": "true" }, forms.short));
}

function statRow(row, opts, label) {
  return el(
    "div",
    { class: "lpair__row lpair__stat" },
    el("span", { class: "lpair__label" }, words(row.words)),
    rankCell(row.us, "us", label),
    valueCell(row.us, "us", row, label),
    edgeCell(row, opts),
    valueCell(row.them, "them", row, label),
    rankCell(row.them, "them", label),
  );
}

/** The line over conference games, each side under its own numbers ("In 3 games" when both played as many). */
function confRow(category, more, { usConfGames, themConfGames }) {
  const lines = { us: obj(obj(more.us).conferenceGames).stats, them: obj(obj(more.them).conferenceGames).stats };
  const long = { us: confGamesText(category, lines.us), them: confGamesText(category, lines.them) };
  if (!long.us && !long.them) return null;
  const games = (n) => (isNum(n) && n > 0 ? `${n} game${n === 1 ? "" : "s"}` : "");
  const same = usConfGames === themConfGames && games(usConfGames);
  const line = (which, n) => {
    if (!long[which]) return el("span", { class: `lpair__line lpair__line--${which}` }, DASH);
    const full = `${long[which]}${!same && games(n) ? ` (${games(n)})` : ""}`;
    const short = confGamesShort(category, lines[which]);
    return el("span", { class: `lpair__line lpair__line--${which}` }, short && short !== full ? [el("span", { class: "lpair__long" }, full), el("span", { class: "lpair__short", "aria-hidden": "true" }, short)] : full);
  };
  return el(
    "div",
    { class: "lpair__row lpair__confrow" },
    el("span", { class: "lpair__label" }, same ? `In ${same}` : "Conference games"),
    line("us", usConfGames),
    el("span", { class: "lpair__confword" }, "conference"),
    line("them", themConfGames),
  );
}

export function leaderPair(cat, { usAbbr = "", themAbbr = "", usTeam, themTeam, usConfGames, themConfGames, onTap } = {}) {
  const c = obj(cat);
  const more = obj(c.more);
  const category = typeof more.category === "string" && more.category ? more.category : typeof c.category === "string" ? c.category : "";
  const us = statsOf(more.us);
  const them = statsOf(more.them);
  const order = [...new Set([...us, ...them].map((s) => s.stat))];
  const byStat = (list) => Object.fromEntries(list.map((s) => [s.stat, s]));
  const u = byStat(us);
  const t = byStat(them);
  const lowerBetter = (stat) => category === "passing" && stat === "INT"; // every leader stat is higher-is-better but a passer's interceptions
  const rows = order.map((stat) => ({ stat, words: statWords(stat, category), format: statFormat(stat, category), higherIsBetter: !lowerBetter(stat), us: side(u[stat], usTeam), them: side(t[stat], themTeam) }));
  if (!rows.length) {
    // the program's own line: the category's key number on both sides, until the whole lines arrive
    const hero = (p) => (p && typeof p === "object" && isNum(p.value) ? statLine(p.value, c.format, c.stat) : null);
    const stat = typeof c.stat === "string" ? c.stat : "";
    rows.push({ stat, words: statWords(stat, category), format: c.format, higherIsBetter: !lowerBetter(stat), us: { value: isNum(obj(c.us).value) ? c.us.value : null, text: hero(c.us) }, them: { value: isNum(obj(c.them).value) ? c.them.value : null, text: hero(c.them) } });
  }
  for (const row of rows) row.lead = twoTeamLeader(row);
  const label = text(c.label);
  const ab = { us: text(usAbbr), them: text(themAbbr) };
  return el(
    "section",
    { class: "lpair", role: "group", "aria-label": label },
    el("div", { class: "lpair__row lpair__heads" }, who(c.us, "us", ab.us, onTap), title(label), who(c.them, "them", ab.them, onTap)),
    el(
      "div",
      { class: "lpair__row lpair__cols" },
      el("span", { class: "lpair__label" }, "Statistic"),
      el("span", { class: "lpair__rank lpair__rank--us" }, "FBS rank"),
      el("span", { class: "lpair__val lpair__val--us" }, ab.us),
      el("span", { class: "lpair__edge" }, "Edge"),
      el("span", { class: "lpair__val lpair__val--them" }, ab.them),
      el("span", { class: "lpair__rank lpair__rank--them" }, "FBS rank"),
    ),
    rows.map((row) => statRow(row, { usAbbr: ab.us, themAbbr: ab.them }, label)),
    confRow(category, more, { usConfGames, themConfGames }),
  );
}

const FORMS = ["full", "initial", "last", "reduced", "number"]; // ui/dom.js NAME_FORMS, longest first

/** The two leaders of a category in one form: the shorter of the two the fit chose ("K. Crawford" beside "C. Phillips", as
 *  the board had them), since their side has less room than ours (the stat names sit at our hand). */
export function levelNames(root) {
  if (!root || typeof root.querySelectorAll !== "function") return;
  for (const pair of root.querySelectorAll(".lpair")) {
    const names = [...pair.querySelectorAll(".lpair__who .pn[data-fit]")];
    const step = Math.max(0, ...names.map((pn) => FORMS.indexOf(pn.dataset.pn || "full")));
    if (step > 0) for (const pn of names) pn.dataset.pn = FORMS[step];
  }
}

export function leaderPairs(categories, opts = {}) {
  const list = (Array.isArray(categories) ? categories : []).filter((cat) => cat && typeof cat === "object");
  const host = el("div", { class: "lpairs" }, list.map((cat) => leaderPair(cat, opts)));
  for (const which of ["us", "them"]) settleNames(host.querySelectorAll(`.lpair__who--${which} .lpair__name .pn`));
  return watchNames(host, { after: levelNames });
}
