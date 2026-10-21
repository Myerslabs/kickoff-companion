// The team page (T1, T2): a header with tabs, the four stat tiles, the recruiting star strip,
// and the impact-player cards. Works for us and for any opponent; sim-only fields from the
// reference screenshots (prestige, archetypes, overall grades) are left out on purpose.
//
// Phase 16 (stream SEASON):
//   teamHeader({ team, season, location, facts, tabs, current, onTab, form })
//       the logo is teamLogo (self-hosted, the dark variant on navy); a fact may carry `href` (a dotted link,
//       design rule 19 for SP+) or `node` (a poll badge); `form` is the last five results as W/L squares.
//   tiles([{ label, value, format, rank, of, href, key }])
//       sized by their column (a container query: 2 x 2 below 560 px of column, 4 across above), sentence-case
//       one-line labels, a 40px value, and under it the rank chip (a link with href) followed by "of N".
//   profileTiles(rows, { team })            the four tiles from profile rows (points and yards, for and against).
//   profileTable(rows, side, { team, conferenceLabel })   one side of the stat profile, sized by its own box (tables
//       wave 3, rule 3: every data point in its own column): Statistic | Value | FBS rank (from medium) | the
//       conference's rank (large). The defense's small head says "Def (allowed)" once for its rows. Season and the
//       team pages share it, so a chip means the same thing everywhere.
//   standingsTable(rows, { conference, rowClass, caption, sort, onSort })   a conference's standings, sized (wave 3):
//       # | Team (logo and school; its abbreviation, still a link, at small) | the conference record under the
//       conference's short name | Overall | AP rank (from medium) | Last 5 (large). Teams sort, by place to start.
//   teamAbbrLink(school, abbreviation)  a team's link that reads its abbreviation: a sized team cell's small form.
//   conferenceColumn()  a team's conference as its own column (decision 1): its whole name at large, its short name
//       (the row's conferenceShort) at medium, gone at small. The polls and the committee's rankings share it.
//   formSquares(form, { limit = 5 })  GX-17: the last results as small squares, a letter on a tinted fill,
//       newest on the right; null when there is no finished game.

import { icon } from "./icons.js";
import { raceBadge } from "./race.js";
import { DASH, el, fmtNum, fmtStat, isNum, personName, teamLink, teamLogo, text, recordText as sharedRecord } from "./dom.js";
import { metricLink, nationalHref, pollHref } from "./national-link.js";
import { pollBadge, rankChip, sizedText, statTable } from "./stat-table.js";
import { fillWiki, wikiLink } from "./wiki-links.js";

function recordText(record) {
  return sharedRecord(record); // freeze wave F3: the one formatter (ui/dom.js)
}

const RESULT_WORD = { W: "Won", L: "Lost", T: "Tied" };

/** GX-17: the last `limit` results, newest on the right, each a letter on a tinted square. */
export function formSquares(form, { limit = 5 } = {}) {
  const games = (Array.isArray(form) ? form : []).filter((g) => g && typeof g === "object" && ["W", "L", "T"].includes(g.result)).slice(-Math.max(1, limit));
  if (!games.length) return null;
  const letters = games.map((g) => g.result);
  return el(
    "span",
    { class: "form", role: "img", "aria-label": `Last ${games.length}: ${letters.join(" ")}` },
    games.map((g) => {
      const score = isNum(g.points) && isNum(g.opponentPoints) ? ` ${g.points}-${g.opponentPoints}` : "";
      const where = g.homeAway === "away" ? "at" : "vs";
      const opponent = typeof g.opponent === "string" && g.opponent.trim() ? ` ${where} ${g.opponent.trim()}` : "";
      return el("span", { class: `form__sq form__sq--${g.result.toLowerCase()}`, title: `${RESULT_WORD[g.result]}${score}${opponent}`, "aria-hidden": "true" }, g.result);
    }),
  );
}

/**
 * teamHeader({ team: {school, abbreviation, logo, logoDark, conference, apRank, record, conferenceRecord, form},
 *              season, location, facts: [{label, value, href, node}], tabs: [{id, label}], current, onTab, form })
 * returns { root, setTab }
 */
export function teamHeader({ team = {}, season, location, facts = [], tabs = [], current, onTab, form, extra } = {}) {
  const t = team && typeof team === "object" ? team : {};
  let active = current || tabs[0]?.id || null;
  const tabButtons = tabs.map((tab) =>
    el(
      "button",
      {
        class: "team-tab",
        type: "button",
        role: "tab",
        "aria-selected": tab.id === active ? "true" : "false",
        dataset: { tab: tab.id },
        onclick: () => {
          setTab(tab.id);
          if (typeof onTab === "function") onTab(tab.id);
        },
      },
      text(tab.label),
    ),
  );
  function setTab(id) {
    active = id;
    for (const button of tabButtons) button.setAttribute("aria-selected", button.dataset.tab === id ? "true" : "false");
  }
  const rec = recordText(t.record);
  const confRec = recordText(t.conferenceRecord);
  const squares = formSquares(form === undefined ? t.form : form);
  const factValue = (fact) => {
    if (fact?.node && typeof Node !== "undefined" && fact.node instanceof Node) return fact.node;
    if (typeof fact?.href === "string" && fact.href.startsWith("#")) return el("a", { class: "team-head__link", href: fact.href, "aria-label": `${text(fact.label)} ${text(fact.value)}. ${text(fact.hint || "Open the ratings")}` }, el("b", {}, text(fact.value)));
    return el("b", {}, text(fact?.value));
  };
  const root = el(
    "header",
    { class: "team-head" },
    el(
      "div",
      { class: "team-head__top" },
      wikiLink("football", { team: t.school }, teamLogo(t, { size: 72, lazy: false, className: "team-head__logo" })), // Phase 17 #4
      el(
        "div",
        {},
        el("div", { class: "team-head__conf" }, [season, t.conference].filter(Boolean).map(text).join(" ")),
        el("div", { class: "team-head__name" }, isNum(t.apRank) ? `#${t.apRank} ` : null, t.school ? wikiLink("school", { team: t.school }, text(t.school)) : text(null)),
        el("div", { class: "team-head__rec" }, rec ? `${rec}${confRec ? ` (${confRec})` : ""}` : "–", squares ? el("span", { class: "team-head__form" }, el("span", { class: "team-head__form-label" }, "Last 5"), squares) : null),
      ),
      facts.length ? el("dl", { class: "team-head__facts" }, facts.filter((f) => f && typeof f === "object").map((fact) => [el("dt", {}, text(fact.label)), el("dd", {}, factValue(fact))])) : null,
      extra || null,
    ),
    el(
      "div",
      { class: "team-head__bottom" },
      location ? el("div", { class: "team-head__loc" }, "Location: ", el("b", {}, text(location))) : null,
      tabs.length ? el("div", { class: "team-head__tabs", role: "tablist" }, tabButtons) : null,
    ),
  );
  fillWiki(root);
  return { root, setTab };
}

/** tiles([{ label, value, format, rank, of, href, key }]): the four big numbers, a linked rank chip and "of N" under each. */
export function tiles(items = []) {
  const list = (Array.isArray(items) ? items : []).filter((item) => item && typeof item === "object");
  return el(
    "div",
    { class: "tiles-box" },
    el(
      "div",
      { class: "tiles" },
      list.map((item) => {
        const chip = rankChip(item.rank, item.of, { href: item.href, label: item.label });
        return el(
          "div",
          { class: "tile" },
          el("div", { class: "tile__label", title: text(item.label) }, text(item.label)),
          el("div", { class: "tile__val", "data-k": item.key ? `tile:${item.key}` : null }, fmtStat(item.value, item.format || "0f")),
          el("div", { class: "tile__rank" }, chip || el("span", { class: "rank-chip" }, "–"), chip && isNum(item.of) ? el("span", { class: "tile__of" }, `of ${item.of}`) : null),
        );
      }),
    ),
  );
}

const TILE_KEYS = [["ppg", "Points per game"], ["ypg", "Yards per game"], ["opp_ppg", "Points allowed per game"], ["ypg_d", "Yards allowed per game"]];

function rowsOf(rows) {
  return (Array.isArray(rows) ? rows : []).filter((row) => row && typeof row === "object");
}

/** The four tiles from a team's profile rows, each chip linked to its national list. */
export function profileTiles(rows, { team } = {}) {
  const byKey = new Map(rowsOf(rows).map((row) => [row.key, row]));
  return tiles(TILE_KEYS.map(([key, label]) => {
    const row = byKey.get(key) || {};
    return { key, label, value: row.value, format: row.format, rank: row.nationalRank, of: row.nationalOf, href: nationalHref(row.metric, { team }) };
  }));
}

/** A conference's name for a rank head ("BB rank"), or "Conf" when there is none. */
function confWord(label) {
  return typeof label === "string" && label.trim() ? label.trim() : "Conf";
}

/**
 * One side of the stat profile ("offense" takes the rows for both sides too), sized by its own box (tables wave 3):
 * Statistic | Value | FBS rank (from medium) | the conference's rank (large), each its own column (rule 3). The value
 * keeps its flash key (v:<key>); a row with no rank shows a dash in that column.
 */
export function profileTable(rows, side, { team, conferenceLabel = "Conf" } = {}) {
  const list = rowsOf(rows).filter((row) => row.side === side || (side === "offense" && row.side === "both"));
  return el(
    "div",
    { class: "prof" },
    statTable({
      compact: true,
      sizes: true,
      columns: [
        { key: "label", label: "Statistic", labelShort: side === "defense" ? "Def (allowed)" : "Stat", kind: "text" }, // rule 5: the defense's head says allowed once
        { key: "value", label: "Value", render: (row) => el("span", { "data-k": typeof row?.key === "string" && row.key ? `v:${row.key}` : null }, isNum(row?.value) ? fmtStat(row.value, row.format || "2f") : DASH) },
        { key: "nationalRank", label: "FBS rank", labelMid: "FBS", kind: "rank", of: "nationalOf", size: "medium", link: metricLink({ team }) },
        { key: "conferenceRank", label: `${confWord(conferenceLabel)} rank`, kind: "rank", of: "conferenceOf", size: "large", link: metricLink({ team, scope: "conference" }) }, // Phase 17 #27: a rank, and says so
      ],
      rows: list,
      caption: `${side} profile`,
    }),
  );
}

/** A team's link that reads its abbreviation (the school when it has none): a sized team cell's small form, so the tap
 *  survives at small (wave 3). A dash with no school. */
export function teamAbbrLink(school, abbreviation) {
  const name = typeof school === "string" && school.trim() ? school.trim() : null;
  if (!name) return DASH;
  const short = typeof abbreviation === "string" && abbreviation.trim() ? abbreviation.trim() : name;
  return teamLink(name, short);
}

/** A team's conference in a column of its own (owner 2026-10-10, decision 1: the second fact under a name has its own
 *  column at large and medium and is gone at small): the whole name at large, the short name the server sends
 *  (conferenceShort: "BB") at medium, where a ranked list's band has no room for a long conference name. */
export function conferenceColumn() {
  const words = (value) => (typeof value === "string" && value.trim() ? value.trim() : null);
  return {
    key: "conference",
    label: "Conference",
    labelMid: "Conf",
    kind: "text",
    size: "medium",
    render: (row) => {
      const name = words(row.conference);
      if (!name) return DASH;
      const short = words(row.conferenceShort) || name;
      return el("span", {}, sizedText(name, short, short));
    },
  };
}

/** How many games of a form list were won (the Last 5 column's sort). */
export function formWins(form) {
  return (Array.isArray(form) ? form : []).filter((g) => g && typeof g === "object" && g.result === "W").length;
}

/**
 * A conference's standings, sized by its own box (tables wave 3; the Season page and every team page share it):
 * # | Team | the conference record (headed by the conference's short name) | Overall | AP rank (from medium) | Last 5
 * (large). At small the team is its abbreviation (still its link). Teams sort; place first.
 * rows: the server's standings rows ({ place, team, abbreviation, logo, conference: record, overall: record, apRank, form }).
 */
/** The team's standing in the race beside its name (F8 feature 1): Clinched, Out or Tiebreaker; nothing while alive. */
function badged(node, row) {
  const badge = raceBadge(row.raceStatus);
  return badge ? el("span", { class: "st__team-badged" }, node, badge) : node;
}

export function standingsTable(rows, { conference = "Conf", rowClass, caption, sort, onSort } = {}) {
  const list = rowsOf(rows).map((row) => ({ ...row, place: isNum(row.place) ? row.place : null, confText: recordText(row.conference) || DASH, overallText: recordText(row.overall) || DASH, formWins: formWins(row.form) }));
  const school = (row) => (typeof row.team === "string" && row.team.trim() ? row.team.trim() : null);
  const columns = [
    { key: "place", label: "#", dim: true },
    { key: "team", label: "Team", kind: "text", render: (row) => badged(logoLink(row.team, row), row), renderShort: (row) => badged(teamAbbrLink(row.team, row.abbreviation), row) },
    { key: "confText", label: confWord(conference) },
    { key: "overallText", label: "Overall", labelShort: "Ovr" },
    { key: "apRank", label: "AP rank", labelMid: "AP", size: "medium", render: (row) => (isNum(row.apRank) ? pollBadge(row.apRank, "AP", { href: pollHref("AP", { team: school(row) }), label: school(row), showPoll: false }) : el("span", { class: "nr" }, "NR")) },
    // measured 2026-10-11: a 1080p screen's one-column band (about 460 px) holds the AP rank at medium but not the squares too
    { key: "form", label: "Last 5", size: "large", sortKey: "formWins", render: (row) => formSquares(row.form) || DASH },
  ].map((column) => ({ ...column, tieKey: "team" })); // a tie in any column falls back to the school's name
  return statTable({
    compact: true,
    sizes: true,
    columns,
    rows: list,
    sort: sort && typeof sort.key === "string" ? sort : { key: "place", dir: "ascending" },
    onSort,
    rowClass,
    caption: typeof caption === "string" && caption ? caption : `${confWord(conference)} standings`,
  });
}

/**
 * starStrip({ counts: {"5": n, "4": n, ...}, average, note })
 * Count by star level, then the average. Missing levels show zero, a missing average a dash.
 */
export function starStrip({ counts = {}, average, note } = {}) {
  const levels = ["5", "4", "3", "2", "1"];
  return el(
    "div",
    { class: "starstrip", role: "group", "aria-label": "Recruiting stars" },
    levels.map((level) => el("div", { class: "starstrip__cell" }, el("span", { class: `starstrip__n${level === "5" || level === "4" ? " starstrip__n--hot" : ""}` }, isNum(counts[level]) ? counts[level] : 0), el("span", { class: "starstrip__label" }, `${level}-star`))),
    el("div", { class: "starstrip__cell" }, el("span", { class: "starstrip__label" }, "Avg"), el("span", { class: "starstrip__n" }, isNum(average) ? fmtNum(average, 2) : "–"), el("span", { class: "stars", "aria-hidden": "true" }, icon("star"))),
    note ? el("div", { class: "starstrip__note" }, note) : null,
  );
}

function badge(number, them) {
  return el("div", { class: `number-badge${them ? " number-badge--them" : ""}`, "aria-hidden": "true" }, text(number));
}

function face(player, them) {
  if (!player?.headshotUrl) return badge(player?.number, them);
  const img = el("img", { class: "headshot", src: player.headshotUrl, alt: "", width: "64", height: "64", loading: "lazy" });
  img.addEventListener("error", () => img.replaceWith(badge(player.number, them)));
  return img;
}

/**
 * impactCard({ player: {name, number, position, classYear, headshotUrl}, chips: [string], tag, them, onTap })
 */
export function impactCard({ player = {}, chips = [], tag, them = false, onTap } = {}) {
  return el(
    "button",
    { class: "impact", type: "button", onclick: () => onTap && onTap(player) },
    face(player, them),
    el(
      "div",
      {},
      // item 6: one line, the name fitted (full, "K. Crawford", the surname, the reduced surname, then the ellipsis)
      el("div", { class: "impact__name" }, player.position ? `${text(player.position)} ` : null, personName(player.name, { fit: true }), tag ? el("span", { class: "tag" }, text(tag)) : null),
      el("div", { class: "impact__chips" }, chips.length ? chips.map((chip) => el("span", { class: "chip" }, text(chip))) : el("span", { class: "chip" }, "No stats yet")),
    ),
    el("div", { class: "impact__class" }, text(player.classYear)),
  );
}

export function impactSkeleton(count = 4) {
  return el("div", { class: "impact-grid" }, Array.from({ length: count }, () => el("div", { class: "skel skel--block", style: { margin: 0 } })));
}

// --- G3-10 part B (owner look): logos in the team columns --------------------------------------------

function isUrl(value) {
  return typeof value === "string" && (value.startsWith("/") || /^https?:\/\//.test(value));
}

/**
 * logoLink(school, team, { size = 20 }): the team's self-hosted logo (the dark variant on navy) before its linked
 * name, 16px under 700px. A team without a logo URL gets the name alone: no tile, so a dense table stays calm.
 */
export function logoLink(school, team, { size = 20 } = {}) {
  const name = typeof school === "string" && school.trim() ? school.trim() : null;
  if (!name) return el("span", {}, "–");
  const t = team && typeof team === "object" ? team : {};
  const logo = isUrl(t.logo) || isUrl(t.logoDark) ? teamLogo({ ...t, school: name }, { size, className: "tl__logo" }) : null;
  return el("span", { class: logo ? "tl" : "tl tl--bare" }, logo, teamLink(name, name));
}
