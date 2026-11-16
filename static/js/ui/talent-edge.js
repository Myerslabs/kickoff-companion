// Talent Edge (FEAT-16, Feature Set v2 Phase A). The owner's board of 2026-10-30
// ("Keep FBS percentile", no other marks): at the bottom of the Pre-Game Program, both rosters judged by how every listed
// player was rated out of high school. Top to bottom: the caveat line (how many players carry a rating), the team totals
// beside a seven-spoke spider of each group's FBS percentile (100 is 1st of the teams with a rated player there), every
// group in a mirrored table (ours left, theirs right, each number pulled to the middle), then the six unit matchups as
// bars from the middle. Bold is the better value in that team's color; years since signing and transfers are never bold,
// since neither more nor fewer is better. The numbers come from the weekly job (app/jobs/talent_edge.py), read back into
// the program's answer as `talentEdge` (app/services/talent_edge.py program_block).
//
//   talentEdgeBand(data)      -> the band (#program-talent-edge), or null when the answer carries no block (an old lock)
//   talentEdgeSummary(row)    -> "#8 talent · 0.92 avg · 63% BCR" (the map's hover card, Phase B), or null
//   spiderPoints(values, r)   -> the polygon's points for seven percentiles (null counts as 0)

import { DASH, el, fmtNum, isNum, ordinal, text } from "./dom.js";
import { nationalHref } from "./national-link.js";
import { band, note } from "./states.js";
import { rankChip } from "./stat-table.js";

const SVG = "http://www.w3.org/2000/svg";
const AXES = [
  ["QB", "QB"],
  ["RB", "RB"],
  ["WR", "WR"],
  ["TE", "TE"],
  ["OL", "OL"],
  ["FRONT7", "Front 7"],
  ["SECONDARY", "Secondary"],
];
const ROWS = [
  ["QB", "QB"],
  ["RB", "RB"],
  ["WR", "WR"],
  ["TE", "TE"],
  ["OL", "OL"],
  ["FRONT7", "Front 7"],
  ["SECONDARY", "Secondary"],
  ["O", "Offense"],
  ["D", "Defense"],
  ["TOT", "Whole roster"],
];
const UNIT_WORDS = { WR: "receivers", OL: "line", RB: "backs", SECONDARY: "secondary", FRONT7: "front 7" };
const CX = 180;
const CY = 172;
const R = 118;

function svgEl(tag, attrs = {}, ...kids) {
  const node = document.createElementNS(SVG, tag);
  for (const [key, value] of Object.entries(attrs)) if (value !== null && value !== undefined) node.setAttribute(key, String(value));
  for (const kid of kids) if (kid !== null && kid !== undefined) node.append(typeof kid === "string" ? document.createTextNode(kid) : kid);
  return node;
}

const obj = (v) => (v && typeof v === "object" && !Array.isArray(v) ? v : {});
const group = (row, key) => obj(obj(obj(row).groups)[key]);

export function talentEdgeSummary(row) {
  const r = obj(row);
  const talent = obj(r.talent);
  const tot = group(r, "TOT");
  const parts = [];
  if (isNum(talent.rank)) parts.push(`#${talent.rank} talent`);
  if (isNum(tot.avgRating)) parts.push(`${tot.avgRating.toFixed(2)} avg`);
  if (isNum(tot.bcrPct)) parts.push(`${Math.round(tot.bcrPct)}% BCR`);
  return parts.length ? parts.join(" · ") : null;
}

function spot(i, radius) {
  const angle = -Math.PI / 2 + (i * 2 * Math.PI) / AXES.length;
  return [CX + radius * Math.cos(angle), CY + radius * Math.sin(angle)];
}

export function spiderPoints(values, radius = R) {
  return AXES.map((_, i) => {
    const v = Array.isArray(values) && isNum(values[i]) ? Math.max(0, Math.min(100, values[i])) : 0;
    return spot(i, (radius * v) / 100).map((n) => n.toFixed(1)).join(",");
  }).join(" ");
}

const rating = (v) => (isNum(v) ? v.toFixed(3) : DASH);
const stars = (v) => (isNum(v) ? v.toFixed(2) : DASH);
const years = (v) => (isNum(v) ? v.toFixed(1) : DASH);
const share = (v) => (isNum(v) ? `${Math.round(v)}%` : DASH);
const count = (v) => (isNum(v) ? String(v) : DASH);

/** Which side's value is bold: "us", "them" or null (a tie, a missing side, or a number neither way better). */
function better(a, b, round = (v) => v) {
  if (!isNum(a) || !isNum(b)) return null;
  const x = round(a);
  const y = round(b);
  return x > y ? "us" : y > x ? "them" : null;
}

function valueCell(words, side, bold, { tag = "span", cls = "" } = {}) {
  return el(tag, { class: `te__v te__v--${side}${bold === side ? " te__v--better" : ""}${cls ? ` ${cls}` : ""}` }, words);
}

function spider(us, them, usName, themName) {
  const valuesOf = (row) => AXES.map(([key]) => group(row, key).pct);
  const u = valuesOf(us);
  const t = them ? valuesOf(them) : null;
  const words = (row, name, values) => `${name}: ${AXES.map(([, label], i) => `${label} ${isNum(values[i]) ? values[i] : "no rating"}`).join(", ")}`;
  const svg = svgEl(
    "svg",
    { class: "te-spider", viewBox: "-10 0 380 330", role: "img", "aria-label": `Each group's FBS percentile by roster rating, 100 is 1st. ${words(us, usName, u)}.${t ? ` ${words(them, themName, t)}.` : ""}` },
    svgEl("polygon", { class: "te-spider__ground", points: spiderPoints([100, 100, 100, 100, 100, 100, 100]) }),
    ...[75, 50, 25].map((ring) => svgEl("polygon", { class: "te-spider__ring", points: spiderPoints(AXES.map(() => ring)) })),
    ...AXES.map((_, i) => {
      const [x, y] = spot(i, R);
      return svgEl("line", { class: "te-spider__spoke", x1: CX, y1: CY, x2: x.toFixed(1), y2: y.toFixed(1) });
    }),
    ...[25, 50, 75].map((ring) => svgEl("text", { class: "te-spider__tick", x: CX + 6, y: (CY - (R * ring) / 100 + 5).toFixed(1) }, String(ring))),
    t ? svgEl("polygon", { class: "te-spider__them", points: spiderPoints(t) }) : null,
    svgEl("polygon", { class: "te-spider__us", points: spiderPoints(u) }),
    ...AXES.flatMap(([, label], i) => {
      const [x, y] = spot(i, R + 20);
      const anchor = Math.abs(x - CX) < 5 ? "middle" : x > CX ? "start" : "end";
      const top = i === 0;
      const bottom = y > CY + R * 0.8;
      const nameY = top ? 20 : bottom ? y + 4 : y - 6;
      const nx = anchor === "start" ? x - 4 : anchor === "end" ? x + 4 : x;
      return [
        svgEl("text", { class: "te-spider__axis", x: nx.toFixed(1), y: nameY.toFixed(1), "text-anchor": anchor }, label),
        svgEl(
          "text",
          { class: "te-spider__nums", x: nx.toFixed(1), y: (nameY + 16).toFixed(1), "text-anchor": anchor },
          svgEl("tspan", { class: "te-spider__num--us" }, isNum(u[i]) ? String(u[i]) : DASH),
          t ? svgEl("tspan", { class: "te-spider__sep" }, " · ") : null,
          t ? svgEl("tspan", { class: "te-spider__num--them" }, isNum(t[i]) ? String(t[i]) : DASH) : null,
        ),
      ];
    }),
  );
  return el(
    "figure",
    { class: "te-spider-fig" },
    svg,
    el(
      "figcaption",
      { class: "te-spider__key" },
      el("span", { class: "te-key te-key--us" }, el("span", { class: "te-key__line", "aria-hidden": "true" }), usName),
      them ? el("span", { class: "te-key te-key--them" }, el("span", { class: "te-key__line", "aria-hidden": "true" }), themName) : null,
      el("span", {}, "FBS percentile by roster rating, 100 is 1st"),
    ),
  );
}

function totals(us, them, usName, themName) {
  const u = obj(us);
  const t = obj(them);
  const ut = group(u, "TOT");
  const tt = group(t, "TOT");
  const utal = obj(u.talent);
  const ttal = obj(t.talent);
  const chip = (rank, of, team, label, metric) => rankChip(rank, of, { href: metric ? nationalHref(metric, { team }) : null, label: `${team}, ${label}` });
  const rows = [
    { label: "Roster rating", sub: "average 247 composite", u: rating(ut.avgRating), t: rating(tt.avgRating), bold: better(ut.avgRating, tt.avgRating), uc: chip(ut.rank, ut.of, usName, "roster rating"), tc: them ? chip(tt.rank, tt.of, themName, "roster rating") : null },
    { label: "Average stars", sub: "of rated players", u: stars(ut.avgStars), t: stars(tt.avgStars), bold: better(ut.avgStars, tt.avgStars, (v) => Math.round(v * 100)) },
    { label: "Years since signing", sub: "from the recruit class", u: years(ut.avgYears), t: years(tt.avgYears), bold: null },
    { label: "Blue chips", sub: "of rated players", u: share(ut.bcrPct), t: share(tt.bcrPct), bold: better(ut.bcrPct, tt.bcrPct, Math.round) },
    { label: "Transfers", sub: "last three seasons", u: count(ut.transferCount), t: count(tt.transferCount), bold: null },
    { label: "247 team talent", sub: "the composite", u: isNum(utal.talent) ? fmtNum(utal.talent, 0) : DASH, t: isNum(ttal.talent) ? fmtNum(ttal.talent, 0) : DASH, bold: better(utal.talent, ttal.talent), uc: chip(utal.rank, utal.of, usName, "247 team talent", utal.metric), tc: them ? chip(ttal.rank, ttal.of, themName, "247 team talent", ttal.metric) : null },
  ];
  return el(
    "div",
    { class: "te-totals" },
    el("div", { class: "te-totals__row te-totals__head" }, el("span", { class: "te__team te__team--us" }, usName), el("span", { class: "te__mid" }, "Team totals"), el("span", { class: "te__team te__team--them" }, themName)),
    rows.map((r) =>
      el(
        "div",
        { class: "te-totals__row" },
        el("span", { class: "te-totals__end te-totals__end--us" }, r.uc || null, valueCell(r.u, "us", r.bold)),
        el("span", { class: "te__mid" }, el("span", {}, r.label), el("small", {}, r.sub)),
        el("span", { class: "te-totals__end te-totals__end--them" }, valueCell(r.t, "them", r.bold), r.tc || null),
      ),
    ),
  );
}

function groupsTable(us, them, usName, themName) {
  const u = obj(us);
  const t = obj(them);
  const ratedWords = (g) => (isNum(g.count) ? `${isNum(g.ratedCount) ? g.ratedCount : 0} of ${g.count}` : DASH);
  const th = (words, cls) => el("th", { scope: "col", class: cls }, words);
  return el(
    "div",
    { class: "te-groups-wrap" },
    el(
      "table",
      { class: "te-groups" },
      el("caption", { class: "sr-only" }, `Talent by position group, ${usName} and ${themName}`),
      el(
        "thead",
        {},
        el("tr", { class: "te-groups__teams" }, el("th", { scope: "colgroup", colspan: 4, class: "te__team te__team--us" }, usName), el("th", { class: "te__mid" }, "By group"), el("th", { scope: "colgroup", colspan: 4, class: "te__team te__team--them" }, themName)),
        el("tr", {}, th("Blue", "te-num--us"), th("Yrs", "te-num--us"), th("Stars", "te-num--us"), th("Rating", "te-num--us"), th("rated of listed", "te__mid"), th("Rating", "te-num--them"), th("Stars", "te-num--them"), th("Yrs", "te-num--them"), th("Blue", "te-num--them")),
      ),
      el(
        "tbody",
        {},
        ROWS.map(([key, label]) => {
          const a = group(u, key);
          const b = group(t, key);
          const r = better(a.avgRating, b.avgRating);
          const s = better(a.avgStars, b.avgStars, (v) => Math.round(v * 100));
          const c = better(a.bcrPct, b.bcrPct, Math.round);
          return el(
            "tr",
            { class: key === "O" ? "te-groups__rollup" : null, dataset: { group: key } },
            valueCell(share(a.bcrPct), "us", c, { tag: "td" }),
            valueCell(years(a.avgYears), "us", null, { tag: "td", cls: "te__v--quiet" }),
            valueCell(stars(a.avgStars), "us", s, { tag: "td" }),
            valueCell(rating(a.avgRating), "us", r, { tag: "td" }),
            el("th", { scope: "row", class: "te__mid" }, el("span", {}, label), el("small", {}, them ? `${ratedWords(a)} · ${ratedWords(b)}` : ratedWords(a))),
            valueCell(rating(b.avgRating), "them", r, { tag: "td" }),
            valueCell(stars(b.avgStars), "them", s, { tag: "td" }),
            valueCell(years(b.avgYears), "them", null, { tag: "td", cls: "te__v--quiet" }),
            valueCell(share(b.bcrPct), "them", c, { tag: "td" }),
          );
        }),
      ),
    ),
  );
}

function unitRow(m, us, them, usName, themName, ours) {
  const usKey = m.a_group;
  const themKey = m.b_group;
  const usWords = `${ours ? "Our" : text(us.abbreviation || usName)} ${UNIT_WORDS[usKey] || text(usKey).toLowerCase()}`;
  const themWords = `${ours ? "their" : text(them.abbreviation || themName)} ${UNIT_WORDS[themKey] || text(themKey).toLowerCase()}`;
  const end = (side, value, key, row, team) => {
    const g = group(row, key);
    return el("span", { class: `te-unit__end te-unit__end--${side}` }, side === "us" ? [rankChip(g.rank, g.of, { label: `${team}, ${key}` }), el("span", { class: "te__v" }, rating(value))] : [el("span", { class: "te__v" }, rating(value)), rankChip(g.rank, g.of, { label: `${team}, ${key}` })]);
  };
  const track = (side, pct, words) =>
    el(
      "span",
      { class: `te-unit__track te-unit__track--${side}`, role: "img", "aria-label": `${words}: ${isNum(pct) ? `percentile ${pct}` : "no rating"}` },
      isNum(pct) ? el("span", { class: "te-unit__bar", style: { width: `${Math.max(3, Math.min(100, pct))}%` } }) : null,
    );
  return el(
    "div",
    { class: "te-unit", dataset: { offense: text(m.offense) } },
    end("us", m.a_rating, usKey, us, usName),
    track("us", m.a_pct, `${usName} ${UNIT_WORDS[usKey] || usKey}`),
    el("span", { class: "te__mid" }, el("span", {}, usWords), el("small", {}, themWords)),
    track("them", m.b_pct, `${themName} ${UNIT_WORDS[themKey] || themKey}`),
    end("them", m.b_rating, themKey, them, themName),
  );
}

function units(block, us, them, usName, themName, ours) {
  const rows = (Array.isArray(block.cross) ? block.cross : []).filter((m) => m && typeof m === "object" && typeof m.a_group === "string" && typeof m.b_group === "string");
  if (!rows.length) return null;
  const withBall = (side) => rows.filter((m) => m.offense === side);
  return el(
    "div",
    { class: "te-units" },
    el("div", { class: "te__group-head" }, `When ${usName} has the ball`),
    withBall("a").map((m) => unitRow(m, us, them, usName, themName, ours)),
    el("div", { class: "te__group-head" }, `When ${themName} has the ball`),
    withBall("b").map((m) => unitRow(m, us, them, usName, themName, ours)),
  );
}

function caveat(block, us, them, usName, themName) {
  const rated = (row) => {
    const s = obj(obj(row).summary);
    return isNum(s.rated) && isNum(s.roster) ? `${s.rated} of ${s.roster}` : DASH;
  };
  const week = isNum(block.computedWeek) ? ` Worked out through week ${block.computedWeek}.` : "";
  const fail = obj(block.lastFailure);
  return [
    el(
      "p",
      { class: "te__caveat" },
      "Whole-roster talent index. Ratings available: ",
      el("b", { class: "te__team--us" }, `${usName} ${rated(us)}`),
      them ? [", ", el("b", { class: "te__team--them" }, `${themName} ${rated(them)}`)] : null,
      `. Blue chips are of rated players.${week}`,
    ),
    typeof fail.message === "string" && fail.message ? note(`The last weekly run, ${text(fail.at)}, failed: ${text(fail.message)} These are the numbers from the run before it.`, { kind: "error", lead: "Not updated" }) : null,
  ];
}

export function talentEdgeBand(data) {
  const block = data && typeof data.talentEdge === "object" && data.talentEdge ? data.talentEdge : null;
  if (!block) return null;
  const usName = text(data.us?.school || "");
  const themName = text(data.them?.school || "");
  const us = block.us && typeof block.us === "object" ? block.us : null;
  const them = block.them && typeof block.them === "object" ? block.them : null;
  const usAbbr = text(us?.abbreviation || data.us?.abbreviation || usName);
  const themAbbr = text(them?.abbreviation || data.them?.abbreviation || themName);
  const ours = data.ours !== false;
  const of = isNum(block.of) ? block.of : null;
  const rankOf = (row) => group(row, "TOT").rank;
  const summary = us ? [`${usAbbr} ${isNum(rankOf(us)) ? ordinal(rankOf(us)) : DASH}`, them ? `${themAbbr} ${isNum(rankOf(them)) ? ordinal(rankOf(them)) : DASH}` : null].filter(Boolean).join(" · ") : "";
  let state = { status: "ready" };
  if (block.available !== true) state = { status: block.failed === true ? "error" : "empty", message: text(block.message || "Talent Edge has not been worked out yet.") };
  else if (!us) state = { status: "empty", message: `${usName || "This team"} is not in this week's Talent Edge table.` };
  const missing = Array.isArray(block.missing) ? block.missing.filter((n) => typeof n === "string" && n && n !== usName) : [];
  const parts = talentEdgeParts(data);
  return band({
    id: "program-talent-edge",
    title: "Talent Edge",
    collapsible: true,
    foldable: true,
    summary: summary ? `Roster rating: ${summary}${of ? ` of ${of}` : ""}` : null,
    state,
    errorLead: "Talent Edge is unavailable.",
    body: parts.body,
  });
}

/** The band's parts for the Talent box (the season as one line, Wave 2): { summary, state, body() }; null with no table. */
export function talentEdgeParts(data) {
  const block = data && typeof data.talentEdge === "object" && data.talentEdge ? data.talentEdge : null;
  if (!block) return null;
  const usName = text(data.us?.school || "");
  const themName = text(data.them?.school || "");
  const us = block.us && typeof block.us === "object" ? block.us : null;
  const them = block.them && typeof block.them === "object" ? block.them : null;
  const usAbbr = text(us?.abbreviation || data.us?.abbreviation || usName);
  const themAbbr = text(them?.abbreviation || data.them?.abbreviation || themName);
  const ours = data.ours !== false;
  const of = isNum(block.of) ? block.of : null;
  const rankOf = (row) => group(row, "TOT").rank;
  const summary = us ? [`${usAbbr} ${isNum(rankOf(us)) ? ordinal(rankOf(us)) : DASH}`, them ? `${themAbbr} ${isNum(rankOf(them)) ? ordinal(rankOf(them)) : DASH}` : null].filter(Boolean).join(" · ") : "";
  let state = { status: "ready" };
  if (block.available !== true) state = { status: block.failed === true ? "error" : "empty", message: text(block.message || "Talent Edge has not been worked out yet.") };
  else if (!us) state = { status: "empty", message: `${usName || "This team"} is not in this week's Talent Edge table.` };
  const missing = Array.isArray(block.missing) ? block.missing.filter((n) => typeof n === "string" && n && n !== usName) : [];
  return {
    summary: summary ? `Roster rating: ${summary}${of ? ` of ${of}` : ""}` : "",
    state,
    body: () =>
      el(
        "div",
        { class: "te" },
        caveat(block, us, them, usName, themName),
        el("div", { class: "te__top" }, totals(us, them, usName, themName), spider(us, them, usName, themName)),
        groupsTable(us, them, usName, themName),
        them ? units(block, us, them, usName, themName, ours) : note(`${missing.join(", ") || themName || "The opponent"} is not an FBS team, so it has no Talent Edge numbers and the unit matchups need both sides.`),
        note("Rating is the average 247 composite of a group's rated players, out of high school: a transfer keeps his first rating, a player with no recruit record is rated from the transfer portal, and anyone found in neither is unrated. The spider and the bars show the group's percentile among the FBS teams with a rated player there (100 is 1st); the chips are its FBS rank. Years count from the recruiting class. Blue chips are four- and five-star players over the rated players. Transfers came in through the portal in the last three seasons. Kickers, punters, snappers and athletes count in the roster but in no group."),
      ),
  };
}
