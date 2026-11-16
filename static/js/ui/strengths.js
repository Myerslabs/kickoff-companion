// Strengths and weaknesses (ENH-11, with chart 1 of ENH-19). The owner's list of 2026-10-23 (Offense run and pass, Defense
// run and pass, Special teams, Coaching career and at the school, Talent, Cost) and his board of 2026-10-28
// ("Build it"). His mark on the first drawing, one shared track: "they
// seem to indicate right is good, and left is bad, but that also seems to indicate they are all georgia leans". So each
// category sits in the middle and each team's bar grows from it toward that team's side, ours left and theirs right as in
// every two-team table: the longer, the stronger (1st fills it), in the rank's tone (the top quarter of FBS a strength,
// the bottom quarter a weakness), the rank chip and the number at the outer end. Cost is a line of words while few
// schools are loaded, with the way to load the rest (the roster-cost prompt on the Load data page).
//
//   strengthsBand(data)  -> the band (#program-strengths), or null when the program carries no strengths (an old lock)
//   barShare(rank, of)   -> 0 to 100: how much of its half a rank fills (1st all of it, the last a sliver)
//   costWords(cost, us, them) -> the cost row's words

import { DASH, el, fmtStat, fmtUsd, isNum, ordinal, text } from "./dom.js";
import { nationalHref } from "./national-link.js";
import { band, note } from "./states.js";
import { rankChip, rankTone } from "./stat-table.js";

const LOADED_ENOUGH = 120; // below this many schools loaded, the cost row offers to load the rest

export function barShare(rank, of) {
  if (!isNum(rank) || !isNum(of) || of < 1 || rank < 1) return 0;
  return Math.max(3, Math.min(100, ((of + 1 - rank) / of) * 100));
}

function sideOf(row, side) {
  const s = row && typeof row[side] === "object" && row[side] ? row[side] : {};
  return { value: s.value, rank: isNum(s.rank) ? s.rank : null, of: isNum(s.of) ? s.of : null, metric: typeof s.metric === "string" ? s.metric : null, wins: s.wins, losses: s.losses, tie: s.tie === true };
}

/** The number under a chip: "+0.16 a run", "-0.04 allowed", ".774 · 48-14", "891". */
function valueWords(row, s) {
  if (row.format === "pct3") {
    if (!isNum(s.value)) return DASH;
    const pct = s.value.toFixed(3).replace(/^0/, "");
    return isNum(s.wins) && isNum(s.losses) ? `${pct} · ${s.wins}-${s.losses}` : pct;
  }
  const number = fmtStat(s.value, typeof row.format === "string" ? row.format : "0f");
  if (number === DASH) return DASH;
  return typeof row.words === "string" && row.words ? `${number} ${row.words}` : number;
}

function end(row, side, team, label) {
  const s = sideOf(row, side);
  const href = s.metric ? nationalHref(s.metric, { team }) : null;
  const chip = rankChip(s.rank, s.of, { href, label: `${text(team)}, ${label}`, tie: s.tie });
  return el("span", { class: `strengths__end strengths__end--${side}` }, chip || el("span", { class: "strengths__dash" }, DASH), el("small", {}, valueWords(row, s)));
}

function track(row, side, team, label) {
  const s = sideOf(row, side);
  const tone = rankTone(s.rank, s.of);
  const share = barShare(s.rank, s.of);
  const words = isNum(s.rank) ? `${text(team)}, ${label}: ${ordinal(s.rank)}${isNum(s.of) ? ` of ${s.of}` : ""}` : `${text(team)}, ${label}: no rank yet`;
  return el(
    "span",
    { class: `strengths__track strengths__track--${side}`, role: "img", "aria-label": words },
    el("span", { class: "strengths__half", "aria-hidden": "true" }),
    share > 0 ? el("span", { class: `strengths__bar${tone ? ` strengths__bar--${tone}` : ""}`, style: { width: `${share.toFixed(1)}%` } }) : null,
  );
}

function rowView(group, row, us, them) {
  const label = text(row.label);
  const named = group.key === "offense" || group.key === "defense" ? `${label.toLowerCase()} ${group.key}` : label;
  return el(
    "div",
    { class: "strengths__row", dataset: { key: text(row.key) } },
    end(row, "us", us, named),
    track(row, "us", us, named),
    el("span", { class: "strengths__label" }, label),
    track(row, "them", them, named),
    end(row, "them", them, named),
  );
}

function lastName(full) {
  const words = typeof full === "string" ? full.trim().split(/\s+/) : [];
  return words.length ? words[words.length - 1] : null;
}

function groupHead(group) {
  const coaches = group.coaches && typeof group.coaches === "object" ? [lastName(group.coaches.us), lastName(group.coaches.them)].filter(Boolean) : [];
  const words = group.key === "coaching" && coaches.length ? `${text(group.label)} · ${coaches.join(" and ")}` : text(group.label);
  return el("div", { class: "strengths__group" }, words);
}

function costSide(c) {
  return c && typeof c === "object" && isNum(c.totalUsd) ? c : null;
}

/** The cost row's words, which say what the bars would: who spends more, among how many schools loaded. */
export function costWords(cost, usAbbr, themAbbr) {
  const c = cost && typeof cost === "object" ? cost : {};
  const u = costSide(c.us);
  const t = costSide(c.them);
  const of = isNum(c.of) ? c.of : null;
  const among = of ? ` of the ${of} school${of === 1 ? "" : "s"} loaded` : "";
  const place = (s) => (isNum(s.rank) ? `${s.tie ? "tied " : ""}${ordinal(s.rank)}` : "unranked");
  if (u && t) {
    if (u.totalUsd === t.totalUsd) return `Roster budget: both rumored at ${fmtUsd(u.totalUsd)}, ${place(u)}${among}`;
    return `Roster budget, rumored: ${usAbbr} ${place(u)}, ${themAbbr} ${place(t)}${among}`;
  }
  if (u || t) {
    const [have, haveAbbr, missingAbbr] = u ? [u, usAbbr, themAbbr] : [t, themAbbr, usAbbr];
    return `Roster budget: ${haveAbbr} rumored at ${fmtUsd(have.totalUsd)} (${place(have)}${among}); ${missingAbbr} not loaded`;
  }
  return "No roster budget loaded for either team";
}

function costRow(cost, usAbbr, themAbbr) {
  const c = cost && typeof cost === "object" ? cost : {};
  const u = costSide(c.us);
  const t = costSide(c.them);
  const of = isNum(c.of) ? c.of : 0;
  const link = !u || !t ? "Load roster costs" : of < LOADED_ENOUGH ? "Load the rest" : null;
  return el(
    "div",
    { class: "strengths__row strengths__row--cost", dataset: { key: "cost" } },
    el("span", { class: "strengths__end strengths__end--us" }, el("b", { class: "strengths__money" }, u ? fmtUsd(u.totalUsd) : DASH)),
    el("span", { class: "strengths__words" }, costWords(c, usAbbr, themAbbr), link ? [" · ", el("a", { href: "#prompts" }, link)] : null),
    el("span", { class: "strengths__end strengths__end--them" }, el("b", { class: "strengths__money" }, t ? fmtUsd(t.totalUsd) : DASH)),
  );
}

/** "FLA best: special teams 1st · UGA best: talent 1st". */
function summaryOf(groups, usAbbr, themAbbr) {
  const best = (side) => {
    let top = null;
    for (const group of groups) {
      for (const row of Array.isArray(group.rows) ? group.rows : []) {
        const s = sideOf(row, side);
        if (!isNum(s.rank)) continue;
        const name = group.key === "offense" || group.key === "defense" ? `${text(row.label).toLowerCase()} ${group.key}` : group.key === "coaching" ? "coaching" : text(group.label).toLowerCase();
        if (!top || s.rank < top.rank) top = { rank: s.rank, name };
      }
    }
    return top;
  };
  const parts = [[usAbbr, best("us")], [themAbbr, best("them")]].filter(([, b]) => b).map(([abbr, b]) => `${abbr} best: ${b.name} ${ordinal(b.rank)}`);
  return parts.join(" · ");
}

/** The band's parts for The matchup box (the season as one line, Wave 2, 2026-10-30): { summary, ranked, body() }, or null
 *  for a program with no strengths (an old lock). */
export function strengthsParts(data) {
  const s = data && typeof data.strengths === "object" && data.strengths ? data.strengths : null;
  if (!s) return null;
  const groups = (Array.isArray(s.groups) ? s.groups : []).filter((g) => g && typeof g === "object" && Array.isArray(g.rows));
  const us = text(data.us?.school || "");
  const them = text(data.them?.school || "");
  const usAbbr = text(data.us?.abbreviation || us);
  const themAbbr = text(data.them?.abbreviation || them);
  const ranked = groups.some((g) => g.rows.some((row) => isNum(sideOf(row, "us").rank) || isNum(sideOf(row, "them").rank)));
  const of = groups.flatMap((g) => g.rows).map((row) => sideOf(row, "us").of || sideOf(row, "them").of).find(isNum);
  return {
    summary: summaryOf(groups, usAbbr, themAbbr),
    ranked,
    body: () =>
      el(
        "div",
        { class: "strengths" },
        el(
          "div",
          { class: "strengths__head" },
          el("span", { class: "strengths__end strengths__end--us strengths__team" }, us || usAbbr),
          el("span", { class: "strengths__dir strengths__dir--us" }, "stronger ←"),
          el("span", { class: "strengths__label" }, `FBS rank${isNum(of) ? ` of ${of}` : ""}`),
          el("span", { class: "strengths__dir strengths__dir--them" }, "→ stronger"),
          el("span", { class: "strengths__end strengths__end--them strengths__team" }, them || themAbbr),
        ),
        groups.map((group) => [groupHead(group), group.rows.map((row) => rowView(group, row, us, them))]),
        el("div", { class: "strengths__group" }, "Cost"),
        costRow(s.cost, usAbbr, themAbbr),
        note("Each bar grows from the middle toward its team's side: the longer, the stronger (1st fills it). Green is a strength, the top quarter of FBS; red a weakness, the bottom quarter. Run and pass: CFBD's points added per play (allowed, on defense). Special teams: SP+. Coaching: win percentage among the season's FBS head coaches, this season's games counted. Talent: the 247 composite. Cost: the rumored roster budget, among the schools loaded."),
      ),
  };
}

export function strengthsBand(data) {
  const parts = strengthsParts(data);
  if (!parts) return null;
  return band({
    id: "program-strengths",
    title: "Strengths and weaknesses",
    collapsible: true,
    foldable: true,
    summary: parts.summary,
    state: { status: parts.ranked ? "ready" : "empty" },
    emptyText: "The ranks appear once CFBD publishes the season's numbers.",
    body: parts.body,
  });
}
