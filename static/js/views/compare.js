// Two players side by side (batch 3, owner 2026-11-16; a viewer's ask of 2026-10-31, "Compare players side by side please").
// His picks: started from the player card, two players; the page shows bio and recruiting and this season's stats (game
// by game was not picked). #compare=<first id>,<second id>?ta=<team>&tb=<team> (the teams let the server read
// a roster it has not loaded yet, as the card's own ?team= does). Each player is the card's own answer (/api/players/<id>),
// so nothing new is asked of CFBD beyond what opening the two cards would.
//
// The page: the two players' heads (face, number, name, position, team, class, the recruit's stars; Change on each side),
// then Bio and recruiting (a row per fact), This season (each category both have on the two-team kit, the tug-of-war bar
// leaning to the better, then a category only one has).

import { DASH, el, fmtNum, isNum, teamLink, teamLogo, text } from "../ui/dom.js";
import { face, fmtHeight, recruitText, starLine, transferFact } from "../ui/player-card.js";
import { categoryColumns, categoryTitle } from "../ui/stat-labels.js";
import { twoTeamTable } from "../ui/two-team.js";
import { band, note } from "../ui/states.js";
import { compareHref, openComparePick } from "../ui/compare-pick.js";
import { errorPanel, fetchPatient } from "./common.js";

const ID = /^\d{1,12}$/;
// fewer is better: interceptions thrown, fumbles, and a punter's touchbacks (the review, 2026-11-19)
const LOWER = (category, key) => {
  const cat = String(category).toLowerCase();
  return (/^INT$/i.test(key) && cat === "passing") || (/^TB$/i.test(key) && cat === "punting") || /^(FUM|FUMBLES|LOST)$/i.test(key);
};

const str = (value) => (typeof value === "string" ? value.trim() : "");
const obj = (value) => (value && typeof value === "object" && !Array.isArray(value) ? value : {});

/** "#compare=1,2" -> ["1", "2"], else null. */
export function compareIds(arg) {
  const ids = String(arg || "").split(",").map((s) => s.trim()).filter((s) => ID.test(s));
  return ids.length === 2 && ids[0] !== ids[1] ? ids : null;
}

function surname(p) {
  const last = str(p.lastName) || str(p.name).split(" ").slice(-1)[0];
  return last || "Player";
}

/** This season's lines by category for one player: Map(category -> stats), the newest year the two players share. */
function seasonLines(data, year) {
  const out = new Map();
  for (const s of Array.isArray(data.seasons) ? data.seasons : []) {
    if (!s || typeof s !== "object" || typeof s.category !== "string" || Number(s.year) !== year) continue;
    out.set(s.category, obj(s.stats));
  }
  return out;
}

function newestYear(...answers) {
  const years = answers.flatMap((d) => (Array.isArray(d.seasons) ? d.seasons : []).map((s) => Number(s?.year)).filter((y) => Number.isFinite(y)));
  return years.length ? Math.max(...years) : null;
}

function head(p, side, onChange) {
  const school = str(p.team);
  return el(
    "div",
    { class: `compare__who compare__who--${side}` },
    face(p, side === "b"),
    el(
      "div",
      { class: "compare__words" },
      el("div", { class: "compare__name" }, isNum(p.number) ? `#${p.number} ` : null, text(p.name)),
      el("div", { class: "compare__line" }, [str(p.position), str(p.classYear)].filter(Boolean).join(" · ") || DASH),
      // the review (owner 2026-11-19): the team's own logo, else its abbreviation tile; the player's answer carries both
      // (teamAbbr, logo, logoDark), so a missing logo no longer draws a lone dash
      school ? el("div", { class: "compare__team" }, teamLogo({ school, abbreviation: str(p.teamAbbr) || school.slice(0, 4).toUpperCase(), logo: p.logo, logoDark: p.logoDark }, { size: 20 }), teamLink(school, school)) : null,
      starLine(p),
      el("button", { type: "button", class: "btn btn--quiet compare__change", onclick: onChange }, "Change"),
    ),
  );
}

/** Why a side did not load, in words. */
function failText(error) {
  return error?.status === 404 ? "This player has no card: cards cover FBS players found on a roster the app has read." : text(error?.message || "The server did not answer");
}

/** A side whose answer failed (the review, 2026-11-19): its reason, Change and Try again; the other side still draws. */
function failedHead(side, error, onChange, onRetry) {
  return el(
    "div",
    { class: `compare__who compare__who--${side} compare__who--failed` },
    el(
      "div",
      { class: "compare__words" },
      el("div", { class: "compare__name" }, "Not loaded"),
      note(failText(error), { kind: "error" }),
      el(
        "div",
        { class: "compare__actions" },
        el("button", { type: "button", class: "btn btn--quiet compare__change", onclick: onChange }, "Change"),
        el("button", { type: "button", class: "btn btn--quiet compare__retry", onclick: onRetry }, "Try again"),
      ),
    ),
  );
}

/** Bio and recruiting: one row per fact, the two players in the two columns. */
function bioBand(a, b) {
  const recruit = (p) => {
    const words = recruitText(p.recruit, p.position);
    const stars = isNum(p.stars) && p.stars > 0 ? `${p.stars}-star` : null;
    const rank = isNum(p.recruitRank) ? `#${p.recruitRank} nationally` : null;
    return [stars, words, rank].filter(Boolean).join(", ") || DASH;
  };
  const rows = [
    ["Team", (p) => (str(p.team) ? teamLink(str(p.team), str(p.team)) : DASH)],
    ["Position", (p) => text(p.position)],
    ["Class", (p) => text(p.classYear)],
    ["Height", (p) => fmtHeight(p.heightText || p.height)],
    ["Weight", (p) => (isNum(p.weight) ? `${p.weight} lb` : DASH)],
    ["Hometown", (p) => text(p.hometown)],
    ["High school", (p) => text(p.highSchool)],
    ["Recruit", recruit],
    ["Transfer", (p) => transferFact(p.transfer) || DASH],
  ];
  const table = el(
    "table",
    { class: "compare-bio" },
    el("caption", { class: "sr-only" }, "Bio and recruiting"),
    el("thead", {}, el("tr", {}, el("th", { scope: "col" }, "Fact"), el("th", { scope: "col" }, text(a.name)), el("th", { scope: "col" }, text(b.name)))),
    el("tbody", {}, rows.map(([label, cell]) => el("tr", {}, el("th", { scope: "row" }, label), el("td", {}, cell(a)), el("td", {}, cell(b))))),
  );
  return band({ id: "compare-bio", title: "Bio and recruiting", collapsible: false, body: () => el("div", { class: "tight" }, table) });
}

/** One category both players have: the two-team kit, the bar leaning to the better line. */
function categoryTable(category, statsA, statsB, a, b) {
  const keys = [...new Set([...Object.keys(statsA), ...Object.keys(statsB)])];
  const rows = categoryColumns(category, keys).map((c) => ({
    label: c.label,
    labelMid: c.labelMid,
    labelShort: c.labelShort,
    format: c.format,
    higherIsBetter: !LOWER(category, c.key),
    key: c.key,
    us: { value: isNum(statsA[c.key]) ? statsA[c.key] : null },
    them: { value: isNum(statsB[c.key]) ? statsB[c.key] : null },
  }));
  return el(
    "div",
    { class: "compare__block" },
    el("h3", { class: "compare__cat" }, categoryTitle(category)),
    twoTeamTable({ rows, usAbbr: surname(a), themAbbr: surname(b), usName: text(a.name), themName: text(b.name), usTeam: str(a.team) || undefined, themTeam: str(b.team) || undefined, tug: true, centered: true, better: false, labelHead: "Stat", caption: `${categoryTitle(category)}: ${text(a.name)} and ${text(b.name)}` }),
  );
}

/** A category only one of the two has: his line alone, so nothing he did is hidden. */
function aloneTable(category, stats, p) {
  const columns = categoryColumns(category, Object.keys(stats));
  return el(
    "div",
    { class: "compare__block compare__block--alone" },
    el("h3", { class: "compare__cat" }, `${categoryTitle(category)}: ${text(p.name)} only`),
    el("dl", { class: "compare__alone" }, columns.map((c) => [el("dt", {}, c.label), el("dd", {}, isNum(stats[c.key]) ? fmtStat(stats[c.key], c.format) : DASH)])),
  );
}

function fmtStat(value, format) {
  if (!isNum(value)) return DASH;
  if (format === "pct") return `${(value * (value <= 1.5 ? 100 : 1)).toFixed(1)}%`;
  if (format === "1f") return value.toFixed(1);
  return fmtNum(value);
}

function statsBand(dataA, dataB, a, b, failed = [false, false]) {
  const year = newestYear(dataA, dataB);
  if (year === null) {
    const loaded = failed[0] ? (failed[1] ? null : b) : failed[1] ? a : null;
    const message = loaded ? `${text(loaded.name)} has no stat line yet.` : "Neither player has a stat line yet.";
    return band({ id: "compare-stats", title: "This season", collapsible: false, state: { status: "empty", message } });
  }
  const linesA = seasonLines(dataA, year);
  const linesB = seasonLines(dataB, year);
  // the review (2026-11-19): a player with no line in the newest year says so, instead of his side quietly missing
  const silent = [
    [linesA, a, failed[0]],
    [linesB, b, failed[1]],
  ]
    .filter(([lines, , gone]) => !gone && lines.size === 0)
    .map(([, p]) => `${text(p.name)}: no ${year} line.`);
  const shared = [...linesA.keys()].filter((c) => linesB.has(c));
  const onlyA = [...linesA.keys()].filter((c) => !linesB.has(c));
  const onlyB = [...linesB.keys()].filter((c) => !linesA.has(c));
  const blocks = [
    ...shared.map((c) => categoryTable(c, linesA.get(c), linesB.get(c), a, b)),
    ...onlyA.map((c) => aloneTable(c, linesA.get(c), a)),
    ...onlyB.map((c) => aloneTable(c, linesB.get(c), b)),
  ];
  return band({
    id: "compare-stats",
    title: `${year} season`,
    summary: shared.length ? `${shared.length} ${shared.length === 1 ? "category" : "categories"} side by side` : silent.length || failed.includes(true) ? "one player's line" : "no category in common",
    collapsible: false,
    body: () =>
      el(
        "div",
        { class: "compare__stats" },
        silent.length ? note(silent.join(" "), { kind: "empty" }) : null,
        shared.length || silent.length || failed.includes(true) ? null : note("These two have no stat category in common; each one's line is below.", { kind: "empty" }),
        blocks,
      ),
  });
}

export function createCompareView({ onStatus, arg, params } = {}) {
  const ids = compareIds(arg);
  const teams = [str(params?.ta) || null, str(params?.tb) || null];
  let container = null;
  let controller = null;

  function setStatus(status) {
    if (typeof onStatus === "function") onStatus(status);
  }

  async function load() {
    if (!container) return;
    if (!ids) {
      container.replaceChildren(el("div", { class: "page" }, errorPanel("Compare players", "The address names no two players. Open a player's card and tap Compare.")));
      setStatus({ kind: "quiet", label: "Nothing to compare" });
      return;
    }
    controller?.abort?.();
    controller = typeof AbortController === "function" ? new AbortController() : null;
    container.replaceChildren(el("div", { class: "page compare" }, band({ id: "compare-loading", title: "Compare players", collapsible: false, state: { status: "loading" } }), note("Each player's numbers come from his card; a team the app has not read yet can take a minute.", { kind: "empty" })));
    setStatus({ kind: "quiet", label: "Loading" });
    // the review (2026-11-19): each side on its own, so one failed player keeps the other on the page with a Change
    const url = (id, team) => `/api/players/${encodeURIComponent(id)}${team ? `?team=${encodeURIComponent(team)}` : ""}`;
    const one = (id, team) =>
      fetchPatient(url(id, team), { signal: controller?.signal }).then(
        (envelope) => ({ data: obj(envelope?.data), error: null }),
        (error) => ({ data: {}, error: error || new Error("The server did not answer") }),
      );
    const sides = await Promise.all([one(ids[0], teams[0]), one(ids[1], teams[1])]);
    if (!container || sides.some((s) => s.error?.name === "AbortError")) return;
    if (sides[0].error && sides[1].error) {
      const both = sides.every((s) => s.error?.status === 404);
      container.replaceChildren(el("div", { class: "page" }, errorPanel("Compare players", both ? "Neither player has a card: cards cover FBS players found on a roster the app has read." : failText(sides[0].error), () => load())));
      setStatus({ kind: "error", label: "Not loaded" });
      return;
    }
    try {
      draw(sides);
    } catch (error) {
      console.error("The comparison did not draw.", error);
      container.replaceChildren(el("div", { class: "page" }, errorPanel("Compare players", "The page could not draw these two players.", () => load())));
      setStatus({ kind: "error", label: "Not drawn" });
      return;
    }
    setStatus(sides.some((s) => s.error) ? { kind: "error", label: "One player not loaded" } : { kind: "ok", label: "Up to date" });
  }

  function draw(sides) {
    const failed = sides.map((s) => Boolean(s.error));
    const [dataA, dataB] = sides.map((s) => s.data);
    const [a, b] = sides.map((s) => (s.error ? { name: "Not loaded" } : obj(s.data.player)));
    // the review (2026-11-19): an answer with no team keeps the team the page arrived with, so Change and the swap still
    // tell the server where to look
    const teamOf = (p, i) => (failed[i] ? null : str(p.team)) || teams[i] || null;
    const who = (p, i) => ({ playerId: ids[i], name: failed[i] ? null : p.name, team: teamOf(p, i) });
    const change = (side) => () => openComparePick({ first: who(a, 0), other: who(b, 1), replace: side });
    const swap = compareHref({ playerId: ids[1], team: teamOf(b, 1) }, { playerId: ids[0], team: teamOf(a, 0) });
    const headOf = (p, i, side) => (failed[i] ? failedHead(side, sides[i].error, change(side), () => load()) : head(p, side, change(side)));
    const page = el(
      "div",
      { class: "page compare" },
      el(
        "header",
        { class: "compare__head flow-full" },
        headOf(a, 0, "a"),
        // the swap sits outside anything aria-hidden (the review, 2026-11-19), and stays on a phone (components.css)
        el("div", { class: "compare__vs" }, el("span", { class: "compare__vs-word", "aria-hidden": "true" }, "vs"), swap ? el("a", { class: "btn btn--quiet compare__swap", href: swap, title: "Swap sides", "aria-label": "Swap sides" }, "⇄") : null),
        headOf(b, 1, "b"),
      ),
      bioBand(a, b),
      statsBand(dataA, dataB, a, b, failed),
    );
    container.replaceChildren(page);
    try {
      document.dispatchEvent(new CustomEvent("kickoff:rendered"));
    } catch {
      // no document
    }
  }

  return {
    mount(target) {
      container = target;
      load();
    },
    refresh: () => load(),
    unmount() {
      controller?.abort?.();
      container = null;
    },
  };
}
