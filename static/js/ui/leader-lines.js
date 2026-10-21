// Leaders side by side, each pair on the pole (the Pre-Game Program from the mock, owner 2026-10-20: "For this type of table,
// can you pull it to the middle of the screen? For matchups, we want to put them on opposite sides of the pole", "Stats |
// Left Photo | Middle | Right Photo | Stats", "Narrow them"). One row of the band per category: our leader's numbers at the
// left hand with his FBS and conference rank chips outside them, his face and name, the pole in the middle (the category over
// the stat names, one a line), their leader's face and name, and his numbers at the right hand with the chips outside; the
// whole row sits in the middle of the band. The numbers come from /api/program/<id>/leaders (app/services/leader_lines.py)
// once it answers (it can take a moment the first time a week's conference games are read); until then each row shows the
// program's own leader line, the category's key number. The line over conference games is the last row of a pair.
// Phase 17 #17 (owner 2026-10-07: "show overall stats, to include secondary stats, but also conference stats") still holds:
// every stat the service lists, its two ranks, and the conference-game line.
//
//   leaderPairs(categories, { usAbbr, themAbbr, usTeam, themTeam, usConfGames, themConfGames, onTap })  -> <div class="lpairs">
//       category: { id, label, category, stat, format, us: player, them: player, more }
//         player  { name, playerId, number, position, headshotUrl, value }: the program's leaders payload side
//         more    the detailed category from /api/program/<id>/leaders ({ category, us: { detail, conferenceGames }, them }), or null
//       onTap(player, "us" | "them") opens the card (a face with no player id is not a button).
//   leaderPair(category, opts)       one row
//   confGamesText(category, stats)   "410 yds, 31/45, 3 TD, 1 int" from season-style totals, or null
//   confGamesShort(category, stats)  "410 yds", the line's lead number alone, or null

import { DASH, el, fmtStat, isNum, obj, personName, playerFace, settleNames, text, watchNames } from "./dom.js";
import { leaderLine, statLine } from "./leaders.js";
import { nationalHref } from "./national-link.js";
import { statFormat, statLabel } from "./stat-labels.js";
import { rankChip } from "./stat-table.js";

function statsOf(side) {
  return (Array.isArray(obj(obj(side).detail).stats) ? obj(side).detail.stats : []).filter((s) => s && typeof s === "object" && typeof s.stat === "string");
}

/** "410 yds, 31/45, 3 TD, 1 int": the conference-game totals in the leader card's own words. */
export function confGamesText(category, stats) {
  const s = obj(stats);
  if (!Object.values(s).some(isNum)) return null;
  const box = { ...s };
  if (category === "passing" && isNum(s.COMPLETIONS) && isNum(s.ATT)) box["C/ATT"] = `${s.COMPLETIONS}/${s.ATT}`;
  const line = leaderLine(category, box);
  return [line.hero, line.rest].filter((part) => typeof part === "string" && part.trim() && !/^(–|-)?\s*(yds|tkl)?$/.test(part.trim())).join(", ") || null;
}

/** "410 yds": the conference-game line's lead number alone, so a phone's row keeps its width (tables wave 2). */
export function confGamesShort(category, stats) {
  const s = obj(stats);
  if (!Object.values(s).some(isNum)) return null;
  const hero = leaderLine(category, { ...s }).hero;
  return typeof hero === "string" && hero.trim() && !/^(–|-)?\s*(yds|tkl)?$/.test(hero.trim()) ? hero.trim() : null;
}

/** One side of a stat row: the value, the FBS rank (linked to the stat's national list) and the conference rank. */
function side(entry, team) {
  if (!entry) return { value: null };
  const nat = obj(entry.national);
  const conf = obj(entry.conference);
  const metric = typeof entry.metric === "string" && entry.metric ? entry.metric : null;
  return {
    value: isNum(entry.value) ? entry.value : null,
    rank: isNum(nat.rank) ? nat.rank : null,
    of: nat.of,
    href: metric ? nationalHref(metric, { team }) : null,
    conf: isNum(conf.rank) ? { rank: conf.rank, of: conf.of, conference: conf.conference, href: metric ? nationalHref(metric, { team, scope: "conference" }) : null } : null,
  };
}

function idOf(player) {
  const id = obj(player).playerId;
  return id === undefined || id === null ? "" : String(id).trim();
}

/** A leader's face and name, a button to his card when the chart knows who he is; the empty side says so at the same size. */
function who(player, which, abbr, onTap) {
  const p = obj(player);
  const name = typeof p.name === "string" && p.name.trim() ? p.name.trim() : null;
  if (!name) return el("div", { class: `lpair__who lpair__who--${which} lpair__who--empty` }, el("span", { class: "lpair__name" }, `No ${text(abbr)} line yet`));
  const meta = [text(abbr), typeof p.position === "string" && p.position.trim() && p.position !== DASH ? p.position.trim() : null].filter(Boolean).join(" ");
  const inner = [playerFace(p, { them: which === "them", abbr, size: 56 }), el("span", { class: "lpair__name" }, personName(name, { fit: true })), el("small", { class: "lpair__meta" }, meta || DASH)];
  if (idOf(p) && typeof onTap === "function") return el("button", { class: `lpair__who lpair__who--${which}`, type: "button", "aria-label": `${name}: open the player card`, onclick: () => onTap(p, which) }, inner);
  return el("div", { class: `lpair__who lpair__who--${which}` }, inner);
}

/** A stat row's cell: the value against the pole, the chips outside it (ours at the left hand, theirs at the right). */
function cell(s, which, row, rowIndex, { team, label }) {
  const value = typeof s.text === "string" ? s.text : isNum(s.value) ? fmtStat(s.value, row.format) : null;
  const chips = [];
  if (isNum(s.rank)) chips.push(rankChip(s.rank, s.of, { href: s.href, label: `${label}, FBS` }));
  if (s.conf) chips.push(el("span", { class: "lpair__conf" }, el("span", { class: "lpair__conf-word" }, "Conf"), rankChip(s.conf.rank, s.conf.of, { href: s.conf.href, label: `${label}, ${text(s.conf.conference)}` })));
  const short = typeof s.textShort === "string" && s.textShort ? s.textShort : null; // a phone: the conference line's lead number alone
  const val = el("b", { class: `lpair__val${row.leads === which ? " lead" : row.leads && row.leads !== "even" ? " trail" : ""}` }, el("span", { class: "lpair__long" }, value === null ? DASH : value), short ? el("span", { class: "lpair__short", "aria-hidden": "true" }, short) : null);
  return el("div", { class: `lpair__cell lpair__${which}${row.rowClass ? ` ${row.rowClass}` : ""}`, style: { gridRow: String(rowIndex + 2) }, dataset: { team: text(team) } }, which === "us" ? [el("span", { class: "lpair__chips" }, chips), val] : [val, el("span", { class: "lpair__chips" }, chips)]);
}

/** Which side has the better number (every leader stat is higher-is-better but a passer's interceptions); null when not both. */
function leads(row, category) {
  const u = row.us.value;
  const t = row.them.value;
  if (!isNum(u) || !isNum(t)) return null;
  if (u === t) return "even";
  const lowerBetter = category === "passing" && row.stat === "INT";
  return (u > t) !== lowerBetter ? "us" : "them";
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
  const rows = order.map((stat) => ({ stat, label: statLabel(stat, category), format: statFormat(stat, category), us: side(u[stat], usTeam), them: side(t[stat], themTeam) }));
  if (!rows.length) {
    // the program's own line: the category's key number on both sides, until the whole lines arrive
    const hero = (p) => (p && typeof p === "object" && isNum(p.value) ? statLine(p.value, c.format, c.stat) : null);
    const stat = typeof c.stat === "string" ? c.stat : "";
    rows.push({ stat, label: statLabel(stat, category), format: c.format, us: { value: isNum(obj(c.us).value) ? c.us.value : null, text: hero(c.us) }, them: { value: isNum(obj(c.them).value) ? c.them.value : null, text: hero(c.them) } });
  }
  for (const row of rows) row.leads = leads(row, category);
  const usConf = confGamesText(category, obj(obj(more.us).conferenceGames).stats);
  const themConf = confGamesText(category, obj(obj(more.them).conferenceGames).stats);
  const games = (n) => (isNum(n) && n > 0 ? `${n} game${n === 1 ? "" : "s"}` : "");
  const same = usConfGames === themConfGames;
  if (usConf || themConf) {
    rows.push({
      stat: "conf",
      label: "Conference games",
      sub: same ? games(usConfGames) : "",
      rowClass: "lpair__cell--conf",
      us: { text: usConf ? `${usConf}${!same && games(usConfGames) ? ` (${games(usConfGames)})` : ""}` : null, textShort: usConf ? confGamesShort(category, obj(obj(more.us).conferenceGames).stats) : null },
      them: { text: themConf ? `${themConf}${!same && games(themConfGames) ? ` (${games(themConfGames)})` : ""}` : null, textShort: themConf ? confGamesShort(category, obj(obj(more.them).conferenceGames).stats) : null },
    });
  }
  const label = text(c.label);
  return el(
    "div",
    { class: "lpair", role: "group", "aria-label": label, style: { "--lpair-rows": String(rows.length + 1) } },
    who(c.us, "us", usAbbr, onTap),
    el("div", { class: "lpair__title" }, label),
    who(c.them, "them", themAbbr, onTap),
    rows.flatMap((row, i) => [
      cell(row.us, "us", row, i, { team: usTeam, label }),
      el("div", { class: "lpair__label", style: { gridRow: String(i + 2) } }, row.label, row.sub ? el("small", {}, row.sub) : null),
      cell(row.them, "them", row, i, { team: themTeam, label }),
    ]),
  );
}

export function leaderPairs(categories, opts = {}) {
  const list = (Array.isArray(categories) ? categories : []).filter((cat) => cat && typeof cat === "object");
  const host = el("div", { class: "lpairs" }, list.map((cat) => leaderPair(cat, opts)));
  for (const which of ["us", "them"]) settleNames(host.querySelectorAll(`.lpair__who--${which} .lpair__name .pn`));
  return watchNames(host);
}
