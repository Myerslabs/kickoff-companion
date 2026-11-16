// The Newspaper (FEAT-14 wave 3, the owner's boards of 2026-10-27: the paper
// the reader). One long scroll of every week, on a six-column grid:
//   the masthead (this week's name, the date, the week, how many stories so far) and the week chips (a jump to any week);
//   the front page: the lead in four columns (its photo, the cutline, its text in two legs cut to the rail's foot) beside
//     the rail (Inside today, By the numbers, the week's quote); three stories of two columns, photo first, head first,
//     photo first, so no two headlines sit side by side; the game of the week across the page;
//   page 2: its own lead beside eight briefs, then three more stories; page 3 and on: the rest by subject;
//   the Top 25 at the back, Claude's stories and picks at the foot; then the earlier weeks folded, one row each, a tap
//     opening that week's paper in place.
// The server lays the pages out (app/services/paper_layout.py, Claude in wave 4); the page draws them. No empty space (his
// mark): a story's text runs to the foot of its row and fades into "The whole story"; a headline-only story takes an Also
// brief. Nothing repeats the tabs or the menu (his mark: no skybox, press box or links to In Game and the program). A
// copied story opens the reader (#story=<id>); a headline-only story opens its publisher's site.
//
//   mastheadName(season, week, who)   this week's paper's name
//   agateName(school)                  a school's name for a line of agate
//   gameOfWeek(matchups, ours)         the game drawn large: the best pair of ranked teams, else the first other game
//   createNewspaperView({ onStatus, edition })   edition: "week-6" opens that week folded open under this week's paper

import { ours, usName, usSchool } from "../identity.js";
import { paragraphs, sourcesLine, writingBand } from "../ui/writing-band.js"; // FEAT-11: what Claude Code wrote
import { el, fmtDate, fmtTime, isNum, obj, records, teamLink, teamLogo, text, recordText as sharedRecord } from "../ui/dom.js";
import { band, note, subhead } from "../ui/states.js";
import { getPrefs } from "../prefs.js";
import { icon } from "../ui/icons.js";
import { errorPanel, fetchJson, poller } from "./common.js";
import { pastYear } from "../ui/past.js"; // rollover R3: a past season's paper, as kept
import { pollsBand } from "../ui/polls-band.js"; // wave 3 of the one-column page (2026-11-01): the polls left My Team for the paper

const EDITION = /^(?:week-\d{1,2}|postseason)(?:-sunday)?$/; // Wave 6 (2026-11-15): a game's Sunday paper is "<week>-sunday"
const STORY = /^[0-9a-f]{16}$/;
let linkSeason = null; // rollover R3: while a past season's paper draws, its stories open that season's copies
const NBSP = " ";

// --- the masthead -------------------------------------------------------------------------------------------------

// The masthead's names: the team's mascot or school in a newspaper's name, one per week of the season.
const MASTHEADS = ["The {m} Gazette", "The {m} Herald", "The {s} Courier", "The {m} Chronicle", "The {s} Sentinel", "The {m} Tribune", "The Saturday {m}", "The {m} Bugle", "The {s} Ledger", "The {m} Dispatch"];

function seedOf(value) {
  const s = String(value ?? "");
  let h = 2166136261;
  for (let i = 0; i < s.length; i += 1) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619) >>> 0;
  }
  return h || 1;
}

/** This week's paper's name, steady all week (Phase 17 #26: "randomize a little bit, depending on the week"). */
export function mastheadName(season, week, who = ours()) {
  const id = who && typeof who === "object" ? who : {};
  const word = (v) => (typeof v === "string" && v.trim() ? v.trim() : null);
  const school = word(id.school) || word(id.name) || "Kickoff";
  const mascot = word(id.mascot) || school;
  const pick = MASTHEADS[seedOf(`${isNum(season) ? season : ""}:${isNum(week) ? week : "x"}`) % MASTHEADS.length];
  return pick.replace("{m}", mascot).replace("{s}", school);
}

const orn = () => el("span", { class: "np-orn", "aria-hidden": "true" }, "✦");

function masthead(data, edition, count, by) {
  const week = isNum(edition.week) ? edition.week : null;
  const season = isNum(edition.season) ? edition.season : data.season;
  const date = data.today || new Date().toISOString();
  const stories = isNum(count) ? `${count} ${count === 1 ? "story" : "stories"} so far` : null;
  return el(
    "header",
    { class: "np-mast" },
    el("h1", { class: "np-mast__name" }, mastheadName(season, week)),
    el("p", { class: "np-mast__line" }, fmtDate(date, "long"), orn(), text(edition.label || "This week"), stories ? [orn(), stories] : null, by === "Claude Code" ? [orn(), "laid out by Claude Code"] : null),
  );
}

// --- one story ------------------------------------------------------------------------------------------------------

const httpUrl = (u) => (typeof u === "string" && /^https?:\/\//i.test(u) ? u : null);

/** Where a story goes: the reader for a copied story, else its publisher's page (never a script or a bad address). */
function storyHref(s) {
  if (s && s.copied === true && STORY.test(String(s.id || ""))) return linkSeason ? `#story=${s.id}?season=${linkSeason}` : `#story=${s.id}`;
  return httpUrl(s && s.url);
}

function linkTo(s, child) {
  const href = storyHref(s);
  if (!href) return child;
  return href.startsWith("#") ? el("a", { href, onclick: rememberSpot }, child) : el("a", { href, target: "_blank", rel: "noopener" }, child);
}

/** Before the reader opens, the paper keeps its place, so the reader's way back returns to the same spot. */
function rememberSpot() {
  try {
    sessionStorage.setItem("np.from", JSON.stringify({ y: typeof window !== "undefined" ? window.scrollY : 0, at: Date.now() }));
  } catch {
    // storage refused: the reader's way back still opens the paper, at its top
  }
}

const dateWords = (iso) => (iso ? fmtDate(iso, "short") : null);
const hostOf = (s) => {
  try {
    return new URL(String(s.url)).hostname.replace(/^www\./, "");
  } catch {
    return null;
  }
};

/** The line under a story: its source and date, and the way to the whole story (or to its site, for a headline). */
function sourceLine(s) {
  const facts = [text(s.source || "News"), dateWords(s.publishedAt)].filter(Boolean).join(" · ");
  const href = storyHref(s);
  const go = !href ? null : s.copied ? el("a", { class: "np-go", href, onclick: rememberSpot }, "The whole story ›") : el("a", { class: "np-go", href, target: "_blank", rel: "noopener" }, `Read it at ${text(s.source || hostOf(s) || "the site")} ›`);
  return el("p", { class: "np-src" }, el("span", {}, facts), go ? el("span", { "aria-hidden": "true" }, "·") : null, go);
}

function picture(p, cls) {
  const pic = obj(p);
  if (typeof pic.src !== "string" || !(pic.src.startsWith("/") || httpUrl(pic.src))) return null;
  const words = typeof pic.cutline === "string" && pic.cutline ? pic.cutline : null;
  const credit = typeof pic.credit === "string" && pic.credit ? (pic.kind === "drawn" ? pic.credit : `Photo: ${pic.credit}`) : null; // a drawing says whose it is
  const img = el("img", { src: pic.src, alt: words || "", loading: "lazy", decoding: "async" });
  const box = el("div", { class: `np-pic ${cls}${pic.kind === "headshot" ? " np-pic--headshot" : ""}${pic.kind === "drawn" ? " np-pic--drawn" : ""}` }, img);
  img.addEventListener("error", () => box.remove()); // a photo that will not load leaves no grey box behind
  const cut = words || credit ? el("p", { class: "np-cut" }, [words, credit].filter(Boolean).join(" ")) : null;
  return [box, cut];
}

/** A story's opening, cut to the space its row leaves (the fade says there is more); one column or two. */
function cutText(opening, legs) {
  const paras = (Array.isArray(opening) ? opening : []).filter((p) => typeof p === "string" && p.trim()).map((p) => el("p", {}, p)); // strings: records() keeps objects only
  if (!paras.length) return null;
  if (legs) return el("div", { class: "np-legbox" }, el("div", { class: "np-legs np-text" }, paras), el("div", { class: "np-fade np-fade--leg2", "aria-hidden": "true" }));
  return el("div", { class: "np-textbox" }, el("div", { class: "np-text" }, paras), el("div", { class: "np-fade", "aria-hidden": "true" }));
}

function briefItem(s) {
  const facts = [text(s.source || "News"), dateWords(s.publishedAt)].filter(Boolean).join(" · ");
  const href = storyHref(s);
  const kids = [el("span", { class: "np-brief__head" }, text(s.title)), el("span", { class: "np-src" }, facts, s.copied ? null : el("span", { class: "np-only", title: "Only the headline is on this server" }, "Headline only"))];
  if (!href) return el("div", { class: "np-brief" }, kids);
  return href.startsWith("#") ? el("a", { class: "np-brief", href, onclick: rememberSpot, id: `np-s-${s.id}` }, kids) : el("a", { class: "np-brief", href, target: "_blank", rel: "noopener", id: `np-s-${s.id}` }, kids);
}

function alsoItem(s) {
  const href = storyHref(s);
  const kids = [el("span", { class: "np-label" }, "Also"), el("span", { class: "np-brief__head" }, text(s.title)), el("span", { class: "np-src" }, [text(s.source || "News"), dateWords(s.publishedAt), s.copied ? null : "Headline only"].filter(Boolean).join(" · "))];
  if (!href) return el("div", { class: "np-also" }, kids);
  return href.startsWith("#") ? el("a", { class: "np-also", href, onclick: rememberSpot }, kids) : el("a", { class: "np-also", href, target: "_blank", rel: "noopener" }, kids);
}

/** One story of two columns: photo first or head first; its text cut to the row; an Also brief under a headline. */
function storyCell(cell, i) {
  const c = obj(cell);
  const s = obj(c.story);
  if (!s.title) return null;
  const pic = picture(c.picture, "np-pic--story");
  const head = el("h3", { class: "np-head np-head--story" }, linkTo(s, text(s.title)));
  const kicker = el("span", { class: "np-kicker" }, text(s.kicker || "The week"));
  const body = s.copied ? cutText(s.opening, false) : el("span", { class: "np-only" }, "Headline only");
  const parts = c.first === "photo" && pic ? [pic, kicker, head] : [kicker, head, pic];
  return el("article", { class: `np-story np-span2${i ? " np-rule-v" : ""}`, id: `np-s-${s.id}` }, parts, body, sourceLine(s), c.also ? alsoItem(c.also) : null);
}

function storyRow(cells) {
  const list = records(cells).map(storyCell).filter(Boolean);
  return list.length ? el("section", { class: "np-row" }, list) : null;
}

/** A page's lead: kicker, headline, byline, the photo and its cutline, the text in two legs, the way to the whole story. */
function leadStory(lead, pic, { kicker, banner, deck, final, page = 1, briefs = [] } = {}) {
  const s = obj(lead);
  const head = el("h2", { class: `np-head ${page === 1 ? "np-head--lead" : "np-head--page"}${final ? " paper-head--final" : ""}` }, linkTo(s, text(banner || s.title)));
  const byline = deck || [s.author ? `By ${text(s.author)}` : null, text(s.source || null), s.publishedAt ? fmtDate(s.publishedAt, "long") : null].filter((v) => v && v !== "–").join(" · ");
  const text2 = s.copied ? cutText(s.opening, true) : briefs.length ? el("div", { class: "np-legbox" }, el("div", { class: "np-legs" }, briefs.map(briefItem)), el("div", { class: "np-fade np-fade--leg2", "aria-hidden": "true" })) : null;
  return el(
    "article",
    { class: "np-lead np-span4", id: `np-s-${s.id}` },
    el("span", { class: `np-kicker${final ? " paper-kicker--final" : ""}` }, text(kicker || s.kicker || "The week")),
    head,
    byline ? el("p", { class: `np-byline${final ? " paper-head--final" : ""}` }, byline) : null,
    picture(pic, "np-pic--lead"),
    text2,
    banner && banner !== s.title && s.title ? el("p", { class: "np-byline" }, "From ", linkTo(s, text(s.title))) : null,
    sourceLine(s),
  );
}

// --- the rail ---------------------------------------------------------------------------------------------------------

/** A key stat's value in its format: whole numbers, one decimal, or a whole-number rate (Design rules, 2026-10-21). */
function statValue(value, format) {
  if (!isNum(value)) return "–";
  if (format === "pct") return `${Math.round(value * 100)}%`;
  if (format === "1f") return value.toFixed(1);
  return String(Math.round(value));
}

/** "By the numbers": our game's key stats after the final, the two teams' records before it, else the week's count. */
function numbersBox({ recap, ourGame, data, chosen }) {
  let rows = [];
  const picked = records(chosen).filter((n) => typeof n.big === "string" && typeof n.words === "string");
  if (picked.length && !recap) {
    rows = picked.slice(0, 4); // FEAT-14 wave 4: the numbers Claude took from the week's stories
  } else if (recap) {
    rows = records(recap.keyStats).filter((s) => typeof s.label === "string").slice(0, 3).map((s) => ({ big: statValue(s.us, s.format), words: `${s.label.toLowerCase()} for us; ${statValue(s.them, s.format)} for ${text(recap.opponent)}` }));
  } else if (ourGame) {
    const away = obj(ourGame.away);
    const home = obj(ourGame.home);
    rows = [
      sharedRecord(obj(away.record)) ? { big: sharedRecord(obj(away.record)), words: `${text(away.school)}'s record${isNum(away.rank) ? `, No. ${away.rank}` : ""}` } : null,
      sharedRecord(obj(home.record)) ? { big: sharedRecord(obj(home.record)), words: `${text(home.school)}'s record${isNum(home.rank) ? `, No. ${home.rank}` : ""}` } : null,
    ].filter(Boolean);
  } else {
    const c = obj(obj(data.rankedWeek).counts);
    rows = [isNum(c.final) ? { big: String(c.final), words: "ranked games final" } : null, isNum(c.live) ? { big: String(c.live), words: "ranked games live" } : null, isNum(c.pre) ? { big: String(c.pre), words: "ranked games to come" } : null].filter(Boolean);
  }
  if (!rows.length) return null;
  return el("aside", { class: `np-box${recap ? " score-words" : ""}`, "aria-label": "By the numbers" }, el("div", { class: "np-standing" }, "By the numbers"), rows.map((r) => el("div", { class: "np-num" }, el("b", {}, r.big), el("span", {}, r.words))));
}

function insideBox(items, lastPage) {
  const list = records(items);
  if (!list.length) return null;
  return el(
    "nav",
    { "aria-label": "Inside today" },
    el("div", { class: "np-standing" }, "Inside today"),
    list.map((i) =>
      el(
        "button",
        { type: "button", class: "np-inside", style: { width: "100%", textAlign: "left", background: "none", border: "0", borderBottom: "1px solid var(--rule)", font: "inherit", cursor: "pointer" }, onclick: () => jump(i.id ? `np-s-${i.id}` : i.anchor || `np-page-${i.page}`) },
        el("span", { class: "np-label" }, `Page ${i.page}`),
        el("span", { class: "np-inside__words" }, text(i.words)),
      ),
    ),
  );
}

function jump(id) {
  const target = typeof document !== "undefined" && typeof document.getElementById === "function" ? document.getElementById(id) : null;
  if (target && typeof target.scrollIntoView === "function") target.scrollIntoView({ behavior: "smooth", block: "start" });
}

function quoteBox(q) {
  const quote = obj(q);
  if (typeof quote.text !== "string" || !quote.text) return null;
  return el("figure", { class: "np-box np-box--quiet", style: { margin: "0" } }, el("span", { class: "np-label" }, "Said this week"), el("blockquote", { class: "np-quote" }, `“${quote.text}”`), el("figcaption", { class: "np-src" }, text(quote.who || null), quote.publishedAt ? ` · ${fmtDate(quote.publishedAt, "short")}` : ""));
}

// --- the game of the week and the agate ---------------------------------------------------------------------------------

const rankedName = (t) => (isNum(t.rank) ? `No.${NBSP}${t.rank} ${text(t.school)}` : text(t.school));

/** The game of the week: the matchups come in AP poll order (No. 1 against an unranked team first), so the game drawn
 * large is the best pair of ranked teams (the lowest sum of ranks, then the better rank), else the first other game. */
export function gameOfWeek(matchups, ourGame = null) {
  const others = records(matchups).filter((g) => g !== ourGame && g.isUs !== true);
  const rank = (g, side) => (isNum(obj(g[side]).rank) ? obj(g[side]).rank : null);
  const pairs = others.filter((g) => rank(g, "home") !== null && rank(g, "away") !== null);
  if (!pairs.length) return others[0] || null;
  const key = (g) => [rank(g, "home") + rank(g, "away"), Math.min(rank(g, "home"), rank(g, "away"))];
  return pairs.reduce((best, g) => {
    const [a, b] = key(g);
    const [c, d] = key(best);
    return a < c || (a === c && b < d) ? g : best;
  });
}

function gameStatus(g) {
  return ["pre", "live", "final", "unplayed"].includes(g.status) ? g.status : "pre";
}

function gameModule(g) {
  if (!g) return null;
  const away = obj(g.away);
  const home = obj(g.home);
  const status = gameStatus(g);
  const line = obj(g.headline);
  const tag = typeof g.bowl === "string" && g.bowl ? g.bowl : g.conferenceGame === true ? text(g.conference || "Conference game") : "Non-conference";
  const side = (t, isHome) =>
    el(
      "div",
      { class: `np-game__side np-span2${isHome ? " np-game__side--home" : ""}` },
      isHome ? null : teamLogo(t, { size: 72, lazy: false, className: "np-logo" }),
      el("span", { style: { display: "grid", gap: "2px" } }, el("span", { class: "np-src" }, [isNum(t.rank) ? `AP ${t.rank}` : null, sharedRecord(obj(t.record))].filter(Boolean).join(" · ") || "Unranked"), el("span", { class: "np-game__name" }, t.school ? teamLink(t.school, text(t.school)) : "–")),
      isHome ? teamLogo(t, { size: 72, lazy: false, className: "np-logo" }) : null,
    );
  let middle;
  if (status === "final" && isNum(away.points) && isNum(home.points)) {
    const [w, l] = away.points >= home.points ? [away, home] : [home, away];
    middle = [el("span", { class: "np-head np-head--story paper-head--final" }, text(line.text) !== "–" ? text(line.text) : `${text(w.school)} ${w.points}, ${text(l.school)} ${l.points}`), el("span", { class: "np-src score-words" }, `Final: ${text(w.school)} ${w.points}, ${text(l.school)} ${l.points}`)];
  } else if (status === "live") {
    middle = [el("span", { class: "np-head np-head--story score-words" }, `${text(away.school)} ${isNum(away.points) ? away.points : "–"}, ${text(home.school)} ${isNum(home.points) ? home.points : "–"}`), el("span", { class: "np-src" }, isNum(g.period) ? (g.period <= 4 ? `Quarter ${g.period}${g.clock ? `, ${text(g.clock)} left` : ""}` : "Overtime") : "Under way")];
  } else {
    middle = [el("span", { class: "np-head np-head--story" }, typeof line.text === "string" && line.text ? line.text : `${rankedName(away)} ${g.neutralSite ? "vs." : "at"} ${rankedName(home)}`), el("span", { class: "np-src" }, [fmtDate(g.kickoff, "medium"), g.startTimeTbd === true ? "time TBD" : fmtTime(g.kickoff), text(g.venue || null)].filter((v) => v && v !== "–").join(" · "))];
  }
  return el("section", { class: "np-row np-game", "aria-label": "Game of the week" }, side(away, false), el("div", { class: "np-game__mid np-span2" }, el("span", { class: "np-kicker" }, `Game of the week · ${tag}`), middle), side(home, true));
}

// a school's name short enough for a line of agate the way a newspaper shortens it; never cut with "…"
const SHORTER = [[/\bState\b/g, "St."], [/\bMountain\b/g, "Mtn."], [/\bJunction\b/g, "Jct."], [/\bCentral\b/g, "Cen."], [/\bUniversity\b/g, "U."], [/\bInternational\b/g, "Intl."], [/\bNorthern\b/g, "N."], [/\bSouthern\b/g, "S."], [/\bEastern\b/g, "E."], [/\bWestern\b/g, "W."]];

/** "Appalachian State" -> "Appalachian St." in a line of agate (a name of thirteen letters or fewer stays whole). */
export function agateName(school) {
  const name = text(school);
  if (name.length <= 13) return name;
  return SHORTER.reduce((s, [from, to]) => s.replace(from, to), name);
}

function agateLine(g) {
  const away = obj(g.away);
  const home = obj(g.home);
  const name = (t) => `${isNum(t.rank) ? `${t.rank} ` : ""}${agateName(t.school)}`;
  const status = gameStatus(g);
  let words;
  let state;
  if (status === "final" && isNum(away.points) && isNum(home.points)) {
    const [w, l] = away.points >= home.points ? [away, home] : [home, away];
    words = `${name(w)}, ${name(l)}`;
    state = el("span", { class: "score-words" }, `${w.points}-${l.points}`);
  } else if (status === "live") {
    words = `${name(away)} at ${name(home)}`;
    state = el("span", { class: "score-words" }, `${isNum(away.points) ? away.points : "–"}-${isNum(home.points) ? home.points : "–"} live`);
  } else if (status === "unplayed") {
    words = `${name(away)} at ${name(home)}`;
    state = "Not played";
  } else {
    words = `${name(away)} ${g.neutralSite ? "vs" : "at"} ${name(home)}`;
    state = g.startTimeTbd === true ? "TBD" : fmtTime(g.kickoff).replace(/\s[A-Z]{2,4}$/, "");
  }
  return el("div", { class: `np-agate${g.isUs === true ? " is-us" : ""}` }, el("span", {}, words), el("span", { class: "np-agate__state" }, state));
}


// --- the pages ----------------------------------------------------------------------------------------------------------

function folio(page, name, paperLine, anchor) {
  return el("header", { class: "np-folio", id: anchor || null }, el("span", { style: { display: "flex", alignItems: "baseline", gap: "12px" } }, el("span", { class: "np-folio__page" }, page), el("span", { class: "np-folio__name" }, name)), el("span", { class: "np-folio__paper" }, paperLine));
}

function morePage(page, paperLine) {
  const columns = (Array.isArray(page.columns) ? page.columns : []).filter(Array.isArray).slice(0, 3); // arrays: records() keeps objects only
  return [
    folio(`Page ${page.page}`, text(page.name || "The rest of the week"), paperLine, `np-page-${page.page}`),
    el(
      "section",
      { class: "np-row" },
      columns.map((col, i) => el("div", { class: `np-column np-span2${i ? " np-rule-v" : ""}` }, records(col).map((item) => (typeof item.section === "string" ? el("div", { class: "np-standing" }, item.section) : item.title ? briefItem(item) : null)))),
    ),
  ];
}

/** The recap of our game when it belongs to this edition (this week's paper, our game final), else null. */
function recapFor(data, edition, ourGame) {
  const r = obj(data.recap);
  if (!edition.current || !isNum(r.gameId)) return null;
  const game = ourGame ? ourGame.gameId : edition.gameId;
  return isNum(game) && game === r.gameId && r.final && typeof r.final === "object" ? r : null;
}

/** One week's paper: the front page, page 2, page 3 and on, the Top 25 at the back (and, this week, Claude's line). */
function weekPages(data, edition, { kept = false, polls = null } = {}) {
  const lay = obj(edition.layout);
  const front = obj(lay.front);
  const matchups = records(edition.matchups).filter((g) => g.home && typeof g.home === "object" && g.away && typeof g.away === "object");
  const ourGame = matchups.find((g) => g.isUs === true) || null;
  const recap = kept ? null : recapFor(data, edition, ourGame);
  const status = ourGame ? gameStatus(ourGame) : null;
  const paperLine = `${mastheadName(isNum(edition.season) ? edition.season : data.season, isNum(edition.week) ? edition.week : null)} · ${kept ? text(edition.label) : fmtDate(data.today || new Date().toISOString(), "long")}`;
  const out = [];
  if (status === "live" && ourGame && !kept) {
    // our game under way: its score under the masthead, the way the paper's front carries a late score (no link: In Game is a tab)
    const a = obj(ourGame.away);
    const h = obj(ourGame.home);
    out.push(el("p", { class: "np-live score-words", role: "status" }, el("span", { class: "np-kicker" }, "Our game · Live"), el("b", {}, `${text(a.school)} ${isNum(a.points) ? a.points : "–"}, ${text(h.school)} ${isNum(h.points) ? h.points : "–"}`), el("span", { class: "np-src" }, isNum(ourGame.period) ? (ourGame.period <= 4 ? `Quarter ${ourGame.period}${ourGame.clock ? `, ${text(ourGame.clock)} left` : ""}` : "Overtime") : "Under way")));
  }
  const final = Boolean(recap) || (kept && status === "final");
  const finalWords = final && ourGame && typeof obj(ourGame.headline).text === "string" ? obj(ourGame.headline).text : null;
  const pog = recap ? obj(recap.playerOfGame) : null;
  const deck = recap ? [pog && pog.name && pog.isUs !== false ? `${text(pog.name)} is the player of the game` : null, sharedRecord(obj(recap.record)) ? `${usSchool()} moves to ${sharedRecord(obj(recap.record))}` : null].filter(Boolean).join(", and ") || null : null;
  if (front.lead) {
    out.push(
      el(
        "section",
        { class: "np-row", id: "np-page-1" },
        leadStory(front.lead, front.picture, { kicker: final ? "Game week · Final" : null, banner: finalWords, deck, final, briefs: records(front.leadBriefs) }),
        // Wave 6 (owner 2026-11-15, "Article replaces the box"): with the paper's own article on page 2 (By the numbers) the
        // rail keeps Inside today and the quote
        el("aside", { class: "np-rail np-span2 np-rule-v" }, insideBox(front.inside, null), obj(obj(lay.page2).lead).app === true ? null : numbersBox({ recap, ourGame, data, chosen: front.numbers }), quoteBox(front.quote)),
      ),
    );
  } else {
    // Wave 6 (owner 2026-11-15): the Sunday paper holds only the game's stories, so its empty words say so
    const sunday = typeof edition?.key === "string" && edition.key.endsWith("-sunday");
    const waiting = edition && edition.offseason
      ? "No stories about the team that week. The paper turns over on Monday morning with the week's stories."
      : sunday
        ? "No stories about the game yet. They show here as the feeds publish them, until the new week's paper on Monday morning."
        : "No stories from the team's feeds yet this week. They show here as the feeds publish.";
    out.push(note(kept ? (sunday ? "No stories about the game were kept." : "No stories were kept for this week.") : waiting, { kind: "empty" }));
  }
  out.push(storyRow(front.row));
  out.push(gameModule(gameOfWeek(matchups, ourGame)));
  const p2 = obj(lay.page2);
  if (p2.lead) {
    out.push(folio("Page 2", ours().school ? `More ${usName()}` : "More stories", paperLine, "np-page-2")); // the mascot ("More Gators"), the school without one
    out.push(el("section", { class: "np-row" }, leadStory(p2.lead, p2.picture, { page: 2 }), el("aside", { class: "np-rail np-span2 np-rule-v" }, el("div", {}, el("div", { class: "np-standing" }, "Briefs"), records(p2.briefs).map(briefItem)))));
    out.push(storyRow(p2.row));
  }
  for (const page of records(lay.more)) out.push(...morePage(page, paperLine));
  // the Top 25's Saturday (the agate) left the paper for the Top 25 page (wave 3, owner 2026-11-01, his inventory)
  if (!kept && polls) out.push(polls);
  if (!kept && !edition.offseason) out.push(storiesBand(edition, matchups)); // rollover R3: the off-season paper has no week's games to pick
  return out.filter(Boolean);
}

/** The Polls band at the back of this week's paper (wave 3 of the one-column page, owner 2026-11-01: the polls left My Team
 *  for the Newspaper, the sheets and the magazine): the season overview's polls, loaded on their own; the reader's poll and
 *  each table's order live in memory.polls across the minute's redraws (?poll=Coaches opens on that poll). */
function pollsHost(memory) {
  const host = el("section", { class: "np-polls" }, band({ id: "np-polls", title: "Polls", collapsible: false, state: { status: "loading" } }));
  fetchJson("/api/season/overview")
    .then((envelope) => host.replaceChildren(pollsBand(obj(envelope?.data), { ui: memory.polls, id: "np-polls" })))
    .catch((error) => host.replaceChildren(band({ id: "np-polls", title: "Polls", collapsible: false, state: { status: "error", message: `${text(error?.message || error)}. The paper tries again with the next refresh.` } })));
  return host;
}


/** FEAT-11: the week's stories and the Picks of the week, each pick by its game, written by Claude Code on Thursday. */
function storiesBand(edition, matchups) {
  const key = typeof edition?.key === "string" ? edition.key : null;
  if (!key) return null;
  const byId = new Map(matchups.map((g) => [String(g.gameId), g]));
  const gameName = (pick) => {
    const g = byId.get(String(pick.gameId));
    return g ? `${text(obj(g.away).school)} at ${text(obj(g.home).school)}` : null;
  };
  return writingBand({
    id: "paper-stories",
    title: "The week's stories and picks",
    kind: "paper",
    key,
    when: "Claude Code writes the week's stories and the Picks of the week on Thursday.",
    draw: (w) => el(
      "div",
      { class: "paper-stories" },
      records(w.stories).filter((s) => typeof s.headline === "string").map((s) => el("article", { class: "paper-story" }, el("h3", { class: "writing__head" }, s.headline), typeof s.dek === "string" ? el("p", { class: "paper-story__dek" }, s.dek) : null, ...paragraphs(s.paragraphs))),
      records(w.picks).length
        ? el("div", { class: "paper-picks" }, subhead("Picks of the week"), el("ul", { class: "writing__list" }, records(w.picks).filter((pick) => typeof pick.pick === "string").map((pick) => el("li", {}, el("b", {}, pick.pick), gameName(pick) ? ` (${gameName(pick)})` : "", typeof pick.reason === "string" ? `: ${pick.reason}` : ""))))
        : null,
      sourcesLine(w.sources),
    ),
  });
}

// --- the earlier weeks, folded ------------------------------------------------------------------------------------------

function foldRow(row, delay, memory) {
  const r = obj(row);
  const when = [r.weekOf ? `The week of ${fmtDate(r.weekOf, "long").replace(/^\w+, /, "")}` : null, r.bye ? "Bye week" : r.opponent ? `${r.homeAway === "away" ? "at " : ""}${text(r.opponent)}` : null].filter(Boolean).join(" · ");
  const holder = el("div", { class: "np-week", id: `np-weekbody-${r.key}`, hidden: true });
  const button = el(
    "button",
    { type: "button", class: "np-fold", id: `np-week-${r.key}`, "aria-expanded": "false", "aria-controls": `np-weekbody-${r.key}` },
    el("span", { class: "np-fold__week" }, text(r.label)),
    el("span", { style: { display: "grid", gap: "2px", minWidth: "0" } }, el("span", { class: "np-fold__when" }, when || "–"), el("span", { class: `np-fold__lead${r.final ? " paper-head--final" : ""}` }, text(r.lead || r.label))),
    el("span", { class: "np-src np-fold__rec", "aria-label": "Record after the week" }, text(r.record || null)),
    el("span", { class: "np-fold__open", "aria-hidden": "true" }, icon("chevron-down")),
  );
  let loaded = false;
  const draw = (data) => {
    const edition = data.edition && typeof data.edition === "object" ? data.edition : null;
    holder.replaceChildren(...(edition ? weekPages(data, edition, { kept: true }) : [note(`No paper was kept for ${text(r.label)}.`, { kind: "empty" })]));
    loaded = true;
    memory.refit?.();
  };
  async function load() {
    if (memory.papers.has(r.key)) return draw(memory.papers.get(r.key)); // a kept week never changes: drawn again from memory
    holder.replaceChildren(el("div", { class: "skel", style: { height: "160px" } }));
    try {
      const body = await fetchJson(`/api/newspaper?delay=${delay}&edition=${encodeURIComponent(r.key)}`);
      const data = obj(body.data);
      memory.papers.set(r.key, data);
      draw(data);
    } catch (error) {
      holder.replaceChildren(note(`${text(r.label)} could not be read: ${text(error?.message || "no answer")}.`, { kind: "error" }), el("button", { type: "button", class: "btn", onclick: load }, "Try again"));
    }
  }
  function toggle(force) {
    const open = typeof force === "boolean" ? force : button.getAttribute("aria-expanded") !== "true";
    button.setAttribute("aria-expanded", open ? "true" : "false");
    holder.hidden = !open;
    if (open) memory.refit?.();
    if (open) memory.open.add(r.key);
    else memory.open.delete(r.key);
    if (open && !loaded) load();
  }
  button.addEventListener("click", () => toggle());
  if (memory.open.has(r.key)) toggle(true);
  return { node: [button, holder], open: () => toggle(true), button };
}

function earlierWeeks(rows, delay, memory) {
  const list = records(rows).filter((r) => typeof r.key === "string" && EDITION.test(r.key));
  if (!list.length) return { node: null, rows: [] };
  const made = list.map((r) => ({ key: r.key, week: r.week, label: r.label, ...foldRow(r, delay, memory) }));
  return { node: el("section", { class: "np-folds", "aria-label": "Earlier weeks" }, el("div", { class: "np-standing" }, "Earlier weeks"), made.map((m) => m.node)), rows: made };
}

function weekChips(edition, made) {
  if (!made.length) return null;
  const chip = (label, current, onclick) => el("button", { type: "button", class: "np-chip", "aria-current": current ? "true" : null, onclick }, label);
  return el(
    "nav",
    { class: "np-weeks", "aria-label": "Weeks of the paper" },
    el("span", { class: "np-label" }, "Weeks"),
    chip(text(edition.label || "This week"), true, () => jump("np-top")),
    // Wave 6: a Sunday paper's chip says so ("8 Sun"), beside its week's "8"
    made.map((m) => chip(isNum(m.week) ? `${m.week}${typeof m.key === "string" && m.key.endsWith("-sunday") ? " Sun" : ""}` : text(m.label), false, () => {
      m.open();
      if (typeof m.button.scrollIntoView === "function") m.button.scrollIntoView({ behavior: "smooth", block: "start" });
    })),
  );
}

// --- the page -----------------------------------------------------------------------------------------------------------

function feedTrouble(feeds) {
  const entries = feeds && typeof feeds === "object" ? Object.values(feeds).filter((f) => f && typeof f === "object") : [];
  if (entries.length && entries.every((f) => f.status === "error")) return note(`Every feed failed: ${text(entries[0].error)}. The app keeps retrying.`, { kind: "error" });
  const stale = entries.find((f) => f.status === "stale");
  return stale ? note(`${text(stale.name)}: ${text(stale.error)}. The stories shown are from before.`, { kind: "empty" }) : null;
}

/** The edition to draw: the server's, or (an answer without one) this week's headlines with no matchups and no layout. */
function editionOf(data) {
  if (data.edition && typeof data.edition === "object") return data.edition;
  const week = records(data.weeks)[0] || {};
  return { key: null, current: true, label: isNum(week.week) ? `Week ${week.week}` : "This week", week: week.week, season: data.season, headlines: records(week.headlines), matchups: [], layout: null };
}

function plainLayout(headlines) {
  // an older server (no layout): the headlines as page 3's briefs, so the paper still reads
  const rows = records(headlines).filter((h) => typeof h.title === "string" && h.title.trim()).map((h) => ({ ...h, id: h.id || "", copied: false }));
  return rows.length ? { front: {}, more: [{ page: 1, name: "This week's headlines", columns: [rows.filter((_, i) => i % 3 === 0), rows.filter((_, i) => i % 3 === 1), rows.filter((_, i) => i % 3 === 2)] }], count: rows.length } : { front: {}, more: [], count: 0 };
}

/** Rollover R3: a past season's paper, as kept (frozen at the switch): its week chips, its pages, nothing live. */
function pastChips(data, current) {
  const listed = records(data.editions);
  if (!listed.length) return null;
  const go = (key) => () => {
    window.location.hash = `newspaper=${encodeURIComponent(key)}?season=${data.past}`;
  };
  return el(
    "nav",
    { class: "np-weeks", "aria-label": "Weeks of the paper" },
    el("span", { class: "np-label" }, `${data.past}`),
    listed.map((e) => el("button", { type: "button", class: "np-chip", "aria-current": e.key === current ? "true" : null, onclick: go(e.key) }, isNum(e.week) ? `${e.week}${typeof e.key === "string" && e.key.endsWith("-sunday") ? " Sun" : ""}` : text(e.label))),
  );
}

function renderPast(data, container) {
  const edition = data.edition && typeof data.edition === "object" ? data.edition : null;
  if (edition && !edition.layout) edition.layout = plainLayout(edition.headlines);
  const page = el(
    "div",
    { class: "page page--wide np", id: "np-top" },
    edition ? masthead(data, edition, isNum(obj(edition.layout).count) ? edition.layout.count : null, obj(edition.layout).by) : null,
    pastChips(data, edition ? edition.key : null),
    el("p", { class: "note past-note" }, `The ${data.past} paper, as kept when the app moved on. `, el("a", { href: `#review=${data.past}` }, `The ${data.past} season in review`), " · ", el("a", { href: "#newspaper" }, "Today's paper")),
    ...(edition ? weekPages(data, edition, { kept: true }) : [note("No paper was kept for that week. The chips above list the weeks that were.", { kind: "empty" })]),
  );
  container.replaceChildren(page);
  restoreSpot();
  return page;
}

/** Rollover R3 (owner 2026-11-15, "weekly it should update with the most relevant stories"): what the off-season paper is,
 *  when it turns over, and last season's papers once the app has moved on. */
function offseasonLine(data, edition) {
  const next = obj(edition.offseason).next;
  const when = typeof next === "string" && isNum(Date.parse(next)) ? fmtDate(next) : "Monday";
  const past = isNum(data.pastPapers) ? data.pastPapers : null;
  return el("p", { class: "note past-note" }, `The off-season paper: the week's stories about the team, chosen once a week. The next one comes ${when} morning.`, past ? el("span", {}, " ", el("a", { href: `#newspaper?season=${past}` }, `The ${past} papers`), ".") : null);
}

function render(envelope, container, asked, delay, memory) {
  const data = obj(envelope?.data);
  linkSeason = isNum(data.past) ? data.past : null;
  if (linkSeason) return renderPast(data, container);
  const edition = editionOf(data);
  if (!edition.layout) edition.layout = plainLayout(edition.headlines);
  const count = isNum(obj(edition.layout).count) ? edition.layout.count : null;
  const first = !memory.drawn;
  if (first && asked) memory.open.add(asked); // #newspaper=week-6 opens that week under this week's paper
  memory.drawn = true;
  const folded = earlierWeeks(data.folded, delay, memory);
  const page = el(
    "div",
    { class: "page page--wide np", id: "np-top" },
    masthead(data, edition, count, obj(edition.layout).by),
    weekChips(edition, folded.rows),
    feedTrouble(data.feeds),
    typeof data.editionError === "string" ? note(data.editionError, { kind: "empty" }) : null,
    edition.offseason ? offseasonLine(data, edition) : null,
    weekPages(data, edition, { polls: pollsHost(memory) }),
    folded.node,
  );
  container.replaceChildren(page);
  if (first && asked) {
    const row = folded.rows.find((r) => r.key === asked);
    if (row && typeof row.button.scrollIntoView === "function") setTimeout(() => row.button.scrollIntoView({ block: "start" }), 0);
  }
  restoreSpot();
  return page;
}

/** Back from the reader: the paper opens where it was (once, within half an hour). */
function restoreSpot() {
  let spot = null;
  try {
    spot = JSON.parse(sessionStorage.getItem("np.back") || "null");
    sessionStorage.removeItem("np.back");
  } catch {
    spot = null;
  }
  if (spot && isNum(spot.y) && isNum(spot.at) && Date.now() - spot.at < 30 * 60 * 1000 && typeof window !== "undefined" && typeof window.scrollTo === "function") {
    setTimeout(() => window.scrollTo(0, spot.y), 0);
  }
}

// --- fitting the page ---------------------------------------------------------------------------------------------------

/** No hole beside a lead (his mark): where the rail ends well above the lead (a week with few stories, a kept week with no
 *  numbers), the lead takes the page's width and the rail's boxes go under it. Measured after each draw and on resize;
 *  a phone stacks everything anyway. */
export function fitRows(root) {
  if (!root || typeof root.querySelectorAll !== "function" || !root.isConnected || !(root.clientWidth >= 700)) return 0;
  let widened = 0;
  for (const row of root.querySelectorAll(".np-row")) {
    const lead = row.querySelector(":scope > .np-lead");
    const rail = row.querySelector(":scope > .np-rail");
    if (!lead || !rail) continue;
    row.classList.remove("np-row--wide");
    const kids = [...rail.children].filter((k) => k.getBoundingClientRect().height > 0);
    const railBottom = kids.length ? Math.max(...kids.map((k) => k.getBoundingClientRect().bottom)) : rail.getBoundingClientRect().top;
    const legs = lead.querySelector(".np-legbox");
    const atMinimum = !legs || legs.getBoundingClientRect().height <= 100; // the lead's text already cut to its least
    if (atMinimum && lead.getBoundingClientRect().bottom - railBottom > 48) {
      row.classList.add("np-row--wide");
      widened += 1;
    }
  }
  return widened;
}

// --- the view -----------------------------------------------------------------------------------------------------------

export function createNewspaperView({ onStatus, edition = null, params = null } = {}) {
  const asked = typeof edition === "string" && EDITION.test(edition) ? edition : null;
  const delay = Number.isFinite(Number(getPrefs().delaySeconds)) ? Number(getPrefs().delaySeconds) : 30;
  const past = pastYear(params?.season); // rollover R3: #newspaper=week-8?season=2026, that season's paper as kept
  const url = past ? `/api/seasons/${past}/paper${asked ? `?edition=${encodeURIComponent(asked)}` : ""}` : `/api/newspaper?delay=${delay}`;
  const memory = { open: new Set(), papers: new Map(), drawn: false, polls: { poll: typeof params?.poll === "string" && params.poll ? params.poll : null, sorts: {} } }; // the open weeks and the polls' choice survive the minute's refresh
  let page = null;
  let frame = null;
  let timer = null;
  const refit = () => {
    if (frame !== null || typeof requestAnimationFrame !== "function") return;
    frame = requestAnimationFrame(() => {
      frame = null;
      try {
        fitRows(page);
      } catch (error) {
        console.error("The newspaper could not be fitted to the screen; it keeps its plain layout.", error);
      }
    });
  };
  memory.refit = refit;
  const onResize = () => {
    clearTimeout(timer);
    timer = setTimeout(refit, 150);
  };
  const win = typeof window !== "undefined" && typeof window.addEventListener === "function" ? window : null;
  const inner = poller({
    url,
    onStatus,
    render: (envelope, container) => {
      page = render(envelope, container, asked, delay, memory);
      refit();
    },
    renderError: (message, container, retry) => container.replaceChildren(errorPanel(past ? `The ${past} paper` : "Newspaper", message, retry)),
    loadingDetail: "This week's paper",
    renderLoading: () =>
      el(
        "div",
        { class: "page page--wide np" },
        el("header", { class: "np-mast" }, el("div", { class: "skel", style: { width: "min(420px, 70%)", height: "40px" } })),
        el("div", { class: "np-row" }, el("div", { class: "np-span4 skel", style: { height: "420px" } }), el("div", { class: "np-span2 skel", style: { height: "420px" } })),
      ),
  });
  return {
    mount(target) {
      inner.mount(target);
      win?.addEventListener("resize", onResize);
    },
    refresh: () => inner.refresh(),
    unmount() {
      win?.removeEventListener("resize", onResize);
      clearTimeout(timer);
      if (frame !== null && typeof cancelAnimationFrame === "function") cancelAnimationFrame(frame);
      frame = null;
      page = null;
      inner.unmount();
    },
    get last() {
      return inner.last;
    },
  };
}

export { isNum };
