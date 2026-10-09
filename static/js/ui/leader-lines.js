// The whole line under each pair of leaders on the Game program (Phase 17 #17, owner 2026-10-07: "show overall
// stats, to include secondary stats, but also conference stats"). One two-team table per category (ui/two-team.js,
// final pass): a row per stat with each side's value, its rank chip among FBS players and a second chip tagged
// "Conf" among the conference's players, both opening the Leaders board's national list, the tug bar between the
// two; then a row with the same leader's line over conference games only. From /api/program/<id>/leaders
// (app/services/leader_lines.py).
//
//   leaderLines(cat, { usAbbr, themAbbr, usTeam, themTeam, usConfGames, themConfGames })  -> <div class="lines"> or null
//   confGamesText(category, stats)   "410 yds, 31/45, 3 TD, 1 int" from season-style totals, or null

import { el, isNum, obj, text } from "./dom.js";
import { leaderLine } from "./leaders.js";
import { nationalHref } from "./national-link.js";
import { statFormat, statLabel } from "./stat-labels.js";
import { twoTeamTable } from "./two-team.js";

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

/** One side of a row: the value, the FBS chip (linked to the stat's national list) and the conference chip. */
function side(entry, team) {
  if (!entry) return { value: null };
  const nat = obj(entry.national);
  const conf = obj(entry.conference);
  const metric = typeof entry.metric === "string" && entry.metric ? entry.metric : null;
  return {
    value: isNum(entry.value) ? entry.value : null,
    rank: isNum(nat.rank) ? nat.rank : null,
    of: nat.of,
    metric,
    conf: isNum(conf.rank) ? { rank: conf.rank, of: conf.of, conference: conf.conference, href: metric ? nationalHref(metric, { team, scope: "conference" }) : null } : null,
  };
}

export function leaderLines(cat, { usAbbr = "", themAbbr = "", usTeam, themTeam, usConfGames, themConfGames } = {}) {
  const c = obj(cat);
  const category = typeof c.category === "string" ? c.category : "";
  const us = statsOf(c.us);
  const them = statsOf(c.them);
  if (!us.length && !them.length) return null;
  const order = [...new Set([...us, ...them].map((s) => s.stat))];
  const byStat = (list) => Object.fromEntries(list.map((s) => [s.stat, s]));
  const u = byStat(us);
  const t = byStat(them);
  const usConf = confGamesText(category, obj(obj(c.us).conferenceGames).stats);
  const themConf = confGamesText(category, obj(obj(c.them).conferenceGames).stats);
  const games = (n) => (isNum(n) && n > 0 ? `${n} game${n === 1 ? "" : "s"}` : "");
  const same = usConfGames === themConfGames;
  const rows = order.map((stat) => ({ label: statLabel(stat, category), format: statFormat(stat, category), us: side(u[stat], usTeam), them: side(t[stat], themTeam) }));
  if (usConf || themConf) {
    rows.push({
      label: "Conference games",
      sub: same ? games(usConfGames) : "",
      rowClass: "lines__conf",
      us: { text: usConf ? `${usConf}${!same && games(usConfGames) ? ` (${games(usConfGames)})` : ""}` : null },
      them: { text: themConf ? `${themConf}${!same && games(themConfGames) ? ` (${games(themConfGames)})` : ""}` : null },
    });
  }
  return el("div", { class: "lines" }, twoTeamTable({ rows, usAbbr, themAbbr, usTeam, themTeam, tug: true, labelHead: "Season", caption: `${text(c.label)}: each leader's whole line` }));
}
