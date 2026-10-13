// The Recruiting page (R1 to R3): the current and next class with a switch, the star strip,
// the commits table, and the visitors list for this week's game from the notes file.
//
// Phase 16 (stream PEOPLE):
//   LRP-05  the national class rank is the class band's headline, a chip that opens the national class list
//           (class:<year>); the band summary carries the same chip. #recruiting=<focus> opens a class year
//           ("2027", not remembered) and scrolls to a part: "national" (the class rank), "where", "visitors".
//           The Visitors summary shows the kickoff date, never the game id.
//   LRP-13  ratings on the 0-100 scale in their tier color, stars as 4-star; each commit's national rank is a chip
//           that opens the recruit list once the row carries its list key (metric, from stream NV).
//   GX-20   (restrained) 'Where they're from': State | Commits | Avg rating | 5/4/3 stars per class, with the
//           in-state share, from the class's byState and inState.
//   DS-14   the visitors' sub-headings name their team as a link; DS-06 the .page container.
//
// Tables wave 3 (owner 2026-10-10): every table sizes itself by its own box, each data point in its own column.
//   The class: its national rank is the class's own order (decision 2: the chip at large and medium, a plain number at
//     small) | Recruit (stepping down with the table, item 6) | Pos (decision 1: its own column, gone at small) | Stars | Rating | High
//     school (large) | Hometown, Ht, Wt (from medium). The recruits sort; the reader's order survives a refresh.
//   Where they're from: State (its name, the code at small) | Commits | Avg rating | 5-star | 4-star | 3-star, one count
//     per column (the old "1 / 0 / 0" cell held three), nothing dropped.
//   Visitors: Recruit (the notes' words, shortened only when they read cleanly) | Pos (gone at small) | Class | Stars | High school (large) | Hometown
//     (from medium) | Status. A table of players, so it sorts.

import { usSchool } from "../identity.js";
import { el, fmtDate, fmtPct, isNum, recall, remember, str, text } from "../ui/dom.js";
import { nationalHref } from "../ui/national-link.js";
import { band, note, revealBand, subhead } from "../ui/states.js";
import { mountFlow, stopFlow } from "../ui/flow.js";
import { visitorRows } from "../ui/in-game-tables.js";
import { rankChip, statTable, statTableSkeleton } from "../ui/stat-table.js";
import { starStrip } from "../ui/team-page.js";
import { stateName } from "../us-states.js";
import { errorPanel, partState, poller } from "./common.js";

/** " Class rank #17 of 221 (250.98 points, 247Sports)." or nothing (Phase 13). Exported for the tests. */
export function classRankText(rank) {
  if (!rank || typeof rank !== "object" || typeof rank.rank !== "number" || !Number.isFinite(rank.rank)) return "";
  const of = typeof rank.of === "number" && rank.of > 0 ? ` of ${rank.of}` : "";
  const points = typeof rank.points === "number" && Number.isFinite(rank.points) ? ` (${rank.points.toFixed(2)} points` : "";
  return ` Class rank #${rank.rank}${of} nationally${points ? `${points}, 247Sports composite)` : ""}.`;
}

const CLASS_KEY = "recruiting:class";

/** A commit's national-rank chip link: the row's list key once stream NV sends it (recruit:<year>). */
function recruitLink(row) {
  const key = [row?.metric, row?.recruitMetric].find((m) => typeof m === "string" && m);
  return key ? nationalHref(key) : null;
}

const COMMIT_COLUMNS = [
  { key: "nationalRank", label: "National rank", labelMid: "Nat", labelShort: "Nat", kind: "rank", order: true, link: recruitLink }, // "Nat" from medium: the iPad's two-wide band keeps the hometown
  { key: "name", label: "Recruit", kind: "text", person: true, sub: "position", subLabel: "Pos" },
  { key: "stars", label: "Stars", format: "stars" },
  { key: "rating", label: "Rating", format: "rating100" },
  { key: "highSchool", label: "High school", kind: "text", size: "large" },
  { key: "hometown", label: "Hometown", kind: "text", size: "medium" },
  { key: "heightText", label: "Ht", size: "medium", sortKey: "height" }, // a number column: it sorts by inches, tallest first
  { key: "weight", label: "Wt", size: "medium" },
].map((column) => ({ ...column, tieKey: "name" }));

const VISITOR_COLUMNS = [
  { key: "name", label: "Recruit", kind: "text", person: { notes: true }, sub: "position", subLabel: "Pos" }, // the notes' words (item 6)
  { key: "classYear", label: "Class", kind: "text" },
  { key: "stars", label: "Stars", format: "stars" },
  { key: "highSchool", label: "High school", kind: "text", size: "large" },
  { key: "hometown", label: "Hometown", kind: "text", size: "medium" },
  { key: "status", label: "Status", kind: "text" },
];

function rows(list) {
  return (Array.isArray(list) ? list : []).filter((r) => r && typeof r === "object");
}

/** A class's commits as the table's rows: guarded fields. Exported for the tests. */
export function commitRows(list) {
  return rows(list).map((c) => {
    const name = str(c.name);
    return {
      ...c,
      name,
      position: str(c.position),
      nationalRank: isNum(c.nationalRank) ? c.nationalRank : null,
      stars: isNum(c.stars) ? c.stars : null,
      rating: isNum(c.rating) ? c.rating : null,
      highSchool: str(c.highSchool),
      hometown: str(c.hometown),
      heightText: str(c.heightText),
      height: isNum(c.height) ? c.height : null,
      weight: isNum(c.weight) ? c.weight : null,
    };
  });
}

/** The class's commits, sized (wave 3), in national-rank order to start. `sorts` keeps the reader's order. Exported for the
 *  design system, which draws the page's own table. */
export function commitsTable(commits, { sorts } = {}) {
  const kept = sorts && typeof sorts === "object" ? sorts : {};
  return statTable({
    columns: COMMIT_COLUMNS,
    rows: commitRows(commits),
    sort: kept.commits || { key: "nationalRank", dir: "ascending" },
    onSort: (sort) => {
      kept.commits = sort;
    },
    compact: true,
    sizes: true,
    caption: "Commits",
  });
}

function visitorsBlock(visitors, team) {
  const side = (title, school, kind, list) => {
    const shaped = visitorRows(list); // the notes' visitors, guarded as In Game guards them (ui/in-game-tables.js)
    return el("div", {}, subhead(title, { team: school, side: kind }), shaped.length ? statTable({ compact: true, sizes: true, columns: VISITOR_COLUMNS, rows: shaped, caption: title }) : note("No visitors listed."));
  };
  const opponent = typeof visitors.opponent === "string" && visitors.opponent.trim() ? visitors.opponent.trim() : null;
  const source = visitors.source
    ? el("p", { class: "note" }, "Source: ", typeof visitors.sourceUrl === "string" && /^https?:\/\//.test(visitors.sourceUrl) ? el("a", { href: visitors.sourceUrl, target: "_blank", rel: "noopener" }, text(visitors.source)) : text(visitors.source), visitors.updatedAt ? ` · updated ${text(visitors.updatedAt)}` : "")
    : null;
  return el(
    "div",
    {},
    visitors.error ? note(`${text(visitors.error)}. Fix the notes file and reload.`, { kind: "error", lead: "Notes file problem." }) : null,
    visitors.note && !visitors.error ? note(text(visitors.note)) : null,
    el("div", { class: "twocol" }, side(`Visiting ${text(team)}`, team, "us", visitors.home), side(`Visiting ${text(opponent)}`, opponent, "them", visitors.away)),
    source,
  );
}

/** The class rank as a linked chip, or null. */
function classChip(cls, team) {
  const rank = cls?.classRank && typeof cls.classRank === "object" ? cls.classRank : null;
  if (!rank) return null;
  return rankChip(rank.rank, isNum(rank.of) ? rank.of : null, { href: nationalHref(rank.metric, { team }), label: `${text(cls.year)} recruiting class` });
}

/** The band's headline (LRP-05): "Class rank #17 of 221 nationally, 250.98 points (247Sports composite)". */
function classHeadline(cls, team) {
  const chip = classChip(cls, team);
  const rank = cls.classRank || {};
  if (!chip) return el("div", { class: "class-head class-head--none" }, el("span", { class: "class-head__label" }, "Class rank"), el("span", { class: "class-head__of" }, "not ranked yet"));
  return el(
    "div",
    { class: "class-head", id: "recruiting-rank" },
    el("span", { class: "class-head__label" }, "Class rank"),
    chip,
    el("span", { class: "class-head__of" }, isNum(rank.of) && rank.of > 0 ? `of ${rank.of} nationally` : "nationally"),
    isNum(rank.points) ? el("span", { class: "class-head__pts" }, `${rank.points.toFixed(2)} points, 247Sports composite`) : null,
  );
}

function classSummary(cls, team) {
  if (!cls) return "";
  const counts = [isNum(cls.count) ? `${cls.count} commits` : null, isNum(cls.average) ? `${cls.average.toFixed(2)} stars average` : null].filter(Boolean).join(", ");
  const chip = classChip(cls, team);
  if (!chip) return counts;
  return el("span", { class: "class-sum" }, chip, " nationally", counts ? ` · ${counts}` : "");
}

/** The by-state rows of a class, guarded: a missing state reads "Unknown", counts must be numbers. Each star count has its
 *  own field (s5, s4, s3: one column each, wave 3; the old "1 / 0 / 0" cell held three) and stateName is the state's name
 *  for large and medium (the code at small). Exported for the tests. */
export function whereRows(cls) {
  return rows(cls?.byState).map((r) => {
    const stars = r.stars && typeof r.stars === "object" ? r.stars : {};
    const n = (k) => (isNum(stars[k]) ? stars[k] : 0);
    const state = typeof r.state === "string" && r.state.trim() ? r.state.trim().slice(0, 24) : "Unknown";
    return { state, stateName: stateName(state), commits: isNum(r.commits) ? r.commits : null, averageRating: isNum(r.averageRating) ? r.averageRating : null, s5: n("5"), s4: n("4"), s3: n("3") };
  });
}

/** "In-state (FL): 11 of 19 commits, 58%." plus the commits with no state on record; "" when unknown. Exported for the tests. */
export function inStateLine(cls) {
  const inState = cls?.inState && typeof cls.inState === "object" ? cls.inState : null;
  const parts = [];
  if (inState && isNum(inState.commits) && isNum(inState.of) && inState.of > 0) {
    const share = isNum(inState.share) ? inState.share : inState.commits / inState.of;
    parts.push(`In-state${typeof inState.state === "string" && inState.state ? ` (${inState.state})` : ""}: ${inState.commits} of ${inState.of} commits, ${fmtPct(share)}.`);
  }
  if (isNum(cls?.unknownState) && cls.unknownState > 0) parts.push(`${cls.unknownState} commit${cls.unknownState === 1 ? "" : "s"} with no home state on record.`);
  return parts.join(" ");
}

const WHERE_COLUMNS = [
  { key: "stateName", label: "State", kind: "text", shortKey: "state" },
  { key: "commits", label: "Commits", labelShort: "#" }, // a phone: "#" keeps the six columns in its band
  { key: "averageRating", label: "Avg rating", labelShort: "Avg", format: "rating100" },
  { key: "s5", label: "5-star" },
  { key: "s4", label: "4-star" },
  { key: "s3", label: "3-star" },
].map((column) => ({ ...column, tieKey: "stateName" }));

/** Where a class is from, sized (wave 3), the most commits first, with the in-state line under it. `sorts` keeps the
 *  reader's order. Exported for the design system, which draws the page's own table. */
export function whereBlock(cls, { sorts } = {}) {
  const list = whereRows(cls);
  const line = inStateLine(cls);
  if (!list.length) return note(line || "No home states on record for this class yet.");
  const kept = sorts && typeof sorts === "object" ? sorts : {};
  return el(
    "div",
    {},
    statTable({
      compact: true,
      sizes: true,
      columns: WHERE_COLUMNS,
      rows: list,
      sort: kept.where || { key: "commits", dir: "descending" },
      onSort: (sort) => {
        kept.where = sort;
      },
      caption: `Where the ${text(cls?.year)} class is from`,
    }),
    line ? el("p", { class: "note" }, line) : null,
  );
}

/** "national", "2027", "where", "visitors" or "2027:where": { year, part }. Exported for the tests. */
export function parseRecruitingArg(arg) {
  const out = { year: null, part: null };
  if (typeof arg !== "string") return out;
  for (const piece of arg.split(":")) {
    const v = piece.trim().toLowerCase();
    if (/^\d{4}$/.test(v)) out.year = Number(v);
    else if (["national", "class", "rank"].includes(v)) out.part = "national";
    else if (["where", "states", "from"].includes(v)) out.part = "where";
    else if (["visitors", "visits"].includes(v)) out.part = "visitors";
  }
  return out;
}

function reveal(container, state) {
  if (!state.part || state.revealed) return;
  const target = state.part === "national" ? container.querySelector("#recruiting-class") : state.part === "where" ? container.querySelector("#recruiting-where") : container.querySelector("#recruiting-visitors");
  if (!target) return;
  state.revealed = true;
  revealBand(target);
  const flash = state.part === "national" ? container.querySelector("#recruiting-rank") || target : target;
  flash.classList.add("flash");
}

function render(envelope, container, state) {
  const data = envelope.data || {};
  const classes = rows(data.classes);
  const parts = data.parts || {};
  const team = typeof data.team === "string" ? data.team : typeof data.team?.school === "string" ? data.team.school : usSchool();
  const current = classes.find((c) => String(c.year) === String(state.year)) || classes[0] || null;
  const buttons = classes.map((cls) => el("button", { type: "button", "aria-pressed": current && cls.year === current.year ? "true" : "false", onclick: () => { state.year = cls.year; remember(CLASS_KEY, cls.year); render(envelope, container, state); } }, `${text(cls.year)} (${text(cls.count)})`));
  const visitors = data.visitors && typeof data.visitors === "object" ? data.visitors : {};
  const part = current ? parts[current.partName] : null;
  const kickoff = typeof visitors.date === "string" && visitors.date ? fmtDate(visitors.date) : null;
  const commits = current ? rows(current.commits) : [];
  const page = el(
      "div",
      { class: "page recruiting" },
      band({
        id: "recruiting-class",
        title: current ? `${text(current.year)} class` : "Recruiting class",
        collapsible: false,
        tools: classes.length > 1 ? el("div", { class: "seg", role: "group", "aria-label": "Class" }, buttons) : null,
        summary: classSummary(current, team),
        state: partState(part, Boolean(current && current.count)),
        emptyText: current ? `No commits recorded for ${text(current.year)} yet.` : "No classes yet.",
        body: () =>
          el(
            "div",
            {},
            classHeadline(current, team),
            starStrip({ counts: current.starCounts && typeof current.starCounts === "object" ? current.starCounts : {}, average: current.average, note: `${text(current.count)} commits in the ${text(current.year)} class.` }),
            commitsTable(commits, { sorts: state.sorts }),
          ),
      }),
      current
        ? band({
            id: "recruiting-where",
            title: `Where they're from, ${text(current.year)} class`,
            collapsible: false,
            summary: current.inState && isNum(current.inState.share) ? `${fmtPct(current.inState.share)} in-state` : "",
            state: partState(part, whereRows(current).length > 0 || Boolean(inStateLine(current))),
            emptyText: "No home states on record for this class yet.",
            body: () => whereBlock(current, { sorts: state.sorts }),
          })
        : null,
      band({
        id: "recruiting-visitors",
        title: visitors.opponent ? `Visitors, ${text(visitors.opponent)} week` : "Visitors this week",
        collapsible: false,
        summary: kickoff && kickoff !== "–" ? `kickoff ${kickoff}` : "",
        state: partState(parts.schedule, true),
        body: () => visitorsBlock(visitors, team),
      }),
  );
  state.ui ??= {};
  mountFlow(state.ui, container, page, { wide: ["recruiting-class"] }); // final pass: the flowing page with its section chips
  reveal(container, state);
}

/** The view. `arg` is the route's focus ("national", "2027", "where", "visitors"). */
export function createRecruitingView({ onStatus, arg } = {}) {
  const asked = parseRecruitingArg(arg);
  const state = { year: asked.year ?? recall(CLASS_KEY, null), part: asked.part, revealed: false, sorts: {} }; // sorts: the reader's order, kept across refreshes
  const view = poller({
    url: "/api/recruiting",
    refreshMs: 60 * 60 * 1000,
    onStatus,
    render: (envelope, container) => render(envelope, container, state),
    renderError: (message, container, retry) => container.replaceChildren(errorPanel("Recruiting", message, retry)),
    renderLoading: () =>
      el(
        "div",
        { class: "page recruiting" },
        band({ title: "Recruiting class", collapsible: false, state: { status: "loading" }, skeleton: () => statTableSkeleton(8, 8) }),
        band({ title: "Where they're from", collapsible: false, state: { status: "loading" }, skeleton: () => statTableSkeleton(4, 4) }),
        band({ title: "Visitors this week", collapsible: false, state: { status: "loading" }, skeleton: () => statTableSkeleton(3, 6) }),
      ),
  });
  return { ...view, unmount() { stopFlow(state.ui); view.unmount(); } };
}
