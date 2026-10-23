// The Newspaper (N1 to N4): our local sports section (Design rules, 2026-10-21), laid out as a newspaper's front page since
// the layout pass (owner 2026-10-22, board 5: https://claude.ai/artifact/Vv827cCpVUGkdDWuN4QeAV; "the problem is that the
// articles become completely uniform down the page"; the whiteboard of 2026-10-13 had boxes of two across):
//   the masthead: this week's name (steady within a week, made from the team's own names), the date and the edition,
//     and the ‹ › ears to the other weeks' editions (the weekly keepsake, kept on the server for the season);
//   the skybox: refers to inside (the next game, the Top 25's count, the trivia's leader or the season's record);
//   the lead, one dominant story: our game with a banner headline across the page, the deck (the player of the game and
//     the record after the final, the kickoff before it), the pixel stadium, and the press box beside it (the turning
//     point, the key numbers in words, what is next; or the two teams and the line), the ways into the box and the program;
//   then modules of different widths and depths: the game of the week (the best pair of ranked teams, else the
//     top-ranked other game, its helmets facing and its score by quarter) across two columns beside "By the numbers"; the player feature (or the player of the game),
//     the coach's story, and the rail's scoreboard: every ranked game of the week in one line of agate, ours marked, the
//     full cards on the Top 25 page (his 1: ours first, the Top 25 compact), in AP poll order as there (2026-10-22);
//   the other headlines as briefs at the foot.
// A matchup carries a funny headline before kickoff and after the final only ("Funny headline only for the pregame and
// postgame articles"); while a game is on it shows the score, the quarter and the clock, our game following the spoiler
// delay. A matchup opens its box score (ours opens In Game); a story opens its source. Names are never cut (his 2):
// headlines wrap and balance, the agate shortens a long school the way a newspaper does ("Dust Devil St.").
// The pictures are drawn on a grid shaped like their box (ui/pixel-art.js fillPicture). On a phone the modules stack in
// the same order. The page refreshes every minute (live matchups); an earlier edition is read once from its file.
//
//   mastheadName(season, week, who)   this week's paper's name
//   pickStories(headlines, us)         { lead, player, coach, rest }: the week's stories for the modules
//   agateName(school)                  a school's name for a line of agate
//   gameOfWeek(matchups, ours)         the game drawn large: the best pair of ranked teams, else the first other game
//   layoutPaper(root)                  names on one line under the helmets, pictures redrawn to their boxes
//   createNewspaperView({ onStatus, edition })   edition: "week-6" or "postseason" opens an earlier edition

import { ours, usSchool } from "../identity.js";
import { el, fmtDate, fmtTime, isNum, obj, records, teamLink, text, recordText as sharedRecord } from "../ui/dom.js";
import { crewText } from "../ui/game-staff.js";
import { openMatchupSheet } from "../ui/matchup-sheet.js";
import { ageOf } from "../ui/news.js";
import { fitNames, loosenNames } from "../ui/paper-fit.js";
import { lastTriviaData, triviaRunning } from "../ui/trivia.js";
import { fillPicture, pixelBanner, pixelPicture, refitPictures, seedOf } from "../ui/pixel-art.js";
import { band, note } from "../ui/states.js";
import { quarterLine } from "../ui/team-stats.js";
import { getPrefs, pollMs } from "../prefs.js";
import { errorPanel, poller } from "./common.js";

const REFRESH_MS = 60 * 1000; // this week's paper: live matchups
const EDITION = /^(?:week-\d{1,2}|postseason)$/;
const NBSP = " ";

// --- the masthead -------------------------------------------------------------------------------------------------

// The masthead's names: the team's mascot or school in a newspaper's name, one per week of the season.
const MASTHEADS = ["The {m} Gazette", "The {m} Herald", "The {s} Courier", "The {m} Chronicle", "The {s} Sentinel", "The {m} Tribune", "The Saturday {m}", "The {m} Bugle", "The {s} Ledger", "The {m} Dispatch"];

/** This week's paper's name, steady all week (Phase 17 #26: "randomize a little bit, depending on the week"). */
export function mastheadName(season, week, who = ours()) {
  const id = who && typeof who === "object" ? who : {};
  const word = (v) => (typeof v === "string" && v.trim() ? v.trim() : null);
  const school = word(id.school) || word(id.name) || "Kickoff";
  const mascot = word(id.mascot) || school;
  const pick = MASTHEADS[seedOf(`${isNum(season) ? season : ""}:${isNum(week) ? week : "x"}`) % MASTHEADS.length];
  return pick.replace("{m}", mascot).replace("{s}", school);
}

function editionHref(key, current) {
  return current ? "#newspaper" : `#newspaper=${encodeURIComponent(key)}`;
}

function navLink(which, entry) {
  const arrow = el("span", { class: "paper-mast__arrow", "aria-hidden": "true" }, which === "prev" ? "‹" : "›");
  if (!entry) return el("span", { class: `paper-mast__nav paper-mast__nav--${which} is-off`, "aria-hidden": "true" }, which === "prev" ? arrow : null, which === "next" ? arrow : null);
  const where = entry.opponent ? `${entry.homeAway === "away" ? "at" : "vs"} ${text(entry.opponent)}` : entry.current ? "this week" : "";
  const words = el("span", { class: "paper-mast__navtext" }, el("b", {}, `${text(entry.label)} edition`), where ? el("small", {}, where) : null);
  return el(
    "a",
    { class: `paper-mast__nav paper-mast__nav--${which}`, href: editionHref(entry.key, entry.current), "aria-label": `${which === "prev" ? "Earlier" : "Later"} edition: ${text(entry.label)}${where ? `, ${where}` : ""}` },
    which === "prev" ? [arrow, words] : [words, arrow],
  );
}

function masthead(data, edition, editions) {
  const at = editions.findIndex((e) => e.key === edition.key);
  const prev = at > 0 ? editions[at - 1] : null;
  const next = at >= 0 && at < editions.length - 1 ? editions[at + 1] : null;
  const week = isNum(edition.week) ? edition.week : null;
  const season = isNum(edition.season) ? edition.season : data.season;
  const date = edition.current ? data.today || new Date().toISOString() : edition.date;
  const where = edition.opponent ? `${edition.homeAway === "away" ? "at" : "vs"} ${text(edition.opponent)}` : null;
  const orn = () => el("span", { class: "paper-mast__orn", "aria-hidden": "true" }, "✦");
  return el(
    "header",
    { class: "paper-mast" },
    navLink("prev", prev),
    el(
      "div",
      { class: "paper-mast__center" },
      pixelBanner({ seed: seedOf(`${isNum(season) ? season : ""}:${isNum(week) ? week : "x"}:banner`) }),
      el("h1", { class: "paper-mast__name" }, mastheadName(season, week)),
      el("p", { class: "paper-mast__line" }, el("span", {}, fmtDate(date, "long")), orn(), el("span", {}, `${text(edition.label || "This week")} edition`), where ? [orn(), el("span", {}, where)] : null),
    ),
    navLink("next", next),
  );
}

// --- the stories ------------------------------------------------------------------------------------------------------

const KICKERS = { game: "Game week", injury: "Injury report", recruiting: "Recruiting", coach: "From the coach", weather: "Forecast", nfl: "In the NFL", "other-sport": "Around campus", practice: "Practice", trophy: "Rivalries and titles", rankings: "Rankings", stadium: "Game day", scoreboard: "Results" };

const headlineOk = (h) => typeof h.title === "string" && h.title.trim();

/**
 * The week's stories for the boxes: the player feature is the newest headline naming one of our players, the coach's
 * story the newest about the coach, the lead the newest of the rest (owner: headlines only, never a write-up).
 */
export function pickStories(headlines, us = usSchool()) {
  const items = records(headlines).filter(headlineOk);
  const names = (h) => records(h.players).filter((p) => typeof p.playerId === "string" && p.playerId && (!p.team || p.team === us));
  const player = items.find((h) => names(h).length) || null;
  const coach = items.find((h) => h !== player && h.topic === "coach") || null;
  const lead = items.find((h) => h !== player && h !== coach) || null;
  const rest = items.filter((h) => h !== player && h !== coach && h !== lead);
  return { lead, player, coach, rest };
}

// a score or a record ("52-16") and a team's or a player's name never split across two lines
function richText(title, names) {
  const value = text(title);
  const list = [...new Set(names.filter((n) => typeof n === "string" && /\s/.test(n)))].sort((a, b) => b.length - a.length);
  const esc = (x) => x.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const keep = new RegExp(`(${[...list.map(esc), "\\d+-\\d+"].join("|")})`);
  return value.split(keep).map((part, i) => (i % 2 ? el("span", { class: "paper-nw" }, part) : part));
}

function storyHref(item) {
  return typeof item.url === "string" && /^https?:\/\//i.test(item.url) ? item.url : null;
}

function words(item, kicker, cls, names) {
  const href = storyHref(item);
  const title = richText(item.title, names);
  return el(
    "div",
    { class: "paper-words" },
    el("p", { class: "paper-kicker" }, kicker),
    el("h3", { class: `paper-head ${cls}`, dataset: { fit: "1" } }, href ? el("a", { href, target: "_blank", rel: "noopener" }, title) : title),
    el("p", { class: "paper-source" }, [item.source, ageOf(item.publishedAt)].filter(Boolean).map(text).join(" · ") || "Headline"),
  );
}

const cell = (canvas, cls = "") => el("div", { class: `paper-pic ${cls}` }, canvas);
const margin = () => el("div", { class: "paper-m", "aria-hidden": "true" });

function storyPicture(item) {
  const face = records(item.players).find((p) => typeof p.playerId === "string" && p.playerId);
  const pic = pixelPicture({ topic: item.topic, seed: seedOf(item.title), playerId: face ? face.playerId : null, label: face ? `${text(face.name)}, in pixels` : `A pixel picture: ${text(item.topic || "the game")}` });
  pic.classList.add("paper-topic");
  return pic;
}

function articleBox(item, side, names) {
  const box = el("article", { class: `paper-box paper-art paper-art--${side}` });
  const kids = [margin(), cell(storyPicture(item)), words(item, KICKERS[item.topic] || "This week", "paper-head--art", names)];
  box.append(...(side === "left" ? kids : kids.reverse()));
  return box;
}

function playerBox(item, names) {
  const face = records(item.players).find((p) => typeof p.playerId === "string" && p.playerId);
  const pic = fillPicture("player", { playerId: face ? face.playerId : null, seed: 3 }, face ? `${text(face.name)}, in pixels` : "Our player, in pixels");
  return el("article", { class: "paper-box paper-feat paper-feat--player" }, margin(), cell(pic, "paper-pic--player"), words(item, "Player feature", "paper-head--feat", names));
}

function coachBox(item, names) {
  return el("article", { class: "paper-box paper-feat paper-feat--coach" }, margin(), cell(fillPicture("coach", { seed: 5 }, "Our coach, in pixels"), "paper-pic--coach"), words(item, "From the coach", "paper-head--feat", names));
}

// --- a ranked game ----------------------------------------------------------------------------------------------------

const abbr = (t) => text(t.abbreviation || (typeof t.school === "string" ? t.school.slice(0, 4).toUpperCase() : null));
const rankedName = (t) => (isNum(t.rank) ? `No.${NBSP}${t.rank} ${text(t.school)}` : text(t.school));
const QUARTERS = ["1st quarter", "2nd quarter", "3rd quarter", "4th quarter"];

function quarterWords(g) {
  if (isNum(g.period)) return g.period <= 4 ? QUARTERS[g.period - 1] : g.period === 5 ? "Overtime" : `${g.period - 4} overtimes`;
  return /half/i.test(text(g.detail)) ? "Halftime" : "Under way";
}

function recordText(t) {
  const r = obj(t.record);
  const c = obj(t.conferenceRecord);
  const main = sharedRecord(r); // freeze wave F3: the one formatter (ui/dom.js), so a tie shows here as everywhere
  const conf = sharedRecord(c);
  return main ? (conf ? `${main} (${conf} conf)` : main) : "No record yet";
}

function who(t, isUs) {
  return el(
    "div",
    { class: `paper-who${isUs ? " is-us" : ""}` },
    el("div", { class: "paper-who__line" }, isNum(t.rank) ? el("span", { class: "paper-rank" }, el("span", { class: "paper-rank__ap" }, "AP"), ` ${t.rank}`) : el("span", { class: "paper-rank paper-rank--nr" }, "NR")),
    el("div", { class: "paper-who__name", dataset: { oneline: "1", min: "14" } }, t.school ? teamLink(t.school, text(t.school)) : text(null)),
    el("div", { class: "paper-who__rec" }, recordText(t)),
  );
}

function helmet(t, flip, isUs) {
  const pic = fillPicture("helmet", { color: t.color, alt: t.altColor, flip, seed: seedOf(text(t.school)) }, `A pixel helmet in ${text(t.school)}'s colors`);
  return el("div", { class: `paper-helm paper-helm--${flip ? "home" : "away"}` }, el("div", { class: "paper-pic paper-pic--helm" }, pic), who(t, isUs));
}

// a line of facts breaks only between its facts, never inside a stadium's or a network's name
/** The network, or our game's announcers from the notes (freeze wave F4), for a game box's facts line. */
function crewOrTv(g) {
  const crew = g && g.broadcast ? crewText({ broadcast: g.broadcast }, g) : null;
  return crew || (g && g.tv ? text(g.tv) : null);
}

function facts(list) {
  return list.filter((f) => typeof f === "string" && f && f !== "–").flatMap((f, i) => [i ? `${NBSP}· ` : null, el("span", { class: "paper-nw" }, f)]).filter(Boolean);
}

function wpBar(g) {
  if (!isNum(g.homeWinProbability) || g.homeWinProbability < 0 || g.homeWinProbability > 1) return null;
  const away = obj(g.away);
  const home = obj(g.home);
  const a = Math.round((1 - g.homeWinProbability) * 100);
  const h = 100 - a;
  return el(
    "div",
    { class: "paper-wp", role: "img", "aria-label": `Pregame win probability: ${abbr(away)} ${a}%, ${abbr(home)} ${h}%` },
    el("span", { class: "paper-wp__cap" }, "Pregame win probability"),
    el("span", { class: "paper-wp__lab" }, `${abbr(away)} ${a}%`),
    el("span", { class: "paper-wp__bar" }, el("i", { style: { width: `${a}%`, background: away.color || "var(--fog)" } }), el("i", { style: { width: `${h}%`, background: home.color || "var(--mist)" } })),
    el("span", { class: "paper-wp__lab" }, `${h}% ${abbr(home)}`),
  );
}

function finalScore(g) {
  const away = obj(g.away);
  const home = obj(g.home);
  const a = away.points;
  const h = home.points;
  const periods = Math.max(Array.isArray(home.lineScores) ? home.lineScores.length : 0, Array.isArray(away.lineScores) ? away.lineScores.length : 0);
  const ot = periods > 4 ? (periods === 5 ? ", overtime" : `, ${periods - 4} overtimes`) : "";
  if (!isNum(a) || !isNum(h)) return el("div", { class: "paper-score" }, el("span", { class: "paper-score__state" }, "Final"));
  const side = (t, p, first, won) => el("span", { class: won ? "is-winner" : "is-loser" }, first ? `${abbr(t)} ${p}` : `${p} ${abbr(t)}`);
  return el("div", { class: "paper-score" }, el("span", { class: "paper-score__num" }, side(away, a, true, a >= h), el("span", { class: "paper-score__dot" }, " · "), side(home, h, false, h >= a)), el("span", { class: "paper-score__state" }, `Final${ot}`));
}

function statusLine(g) {
  const away = obj(g.away);
  const home = obj(g.home);
  const a = isNum(away.points) ? away.points : "–";
  const h = isNum(home.points) ? home.points : "–";
  const q = quarterWords(g);
  return el(
    "a",
    { class: "paper-status", href: gameHref(g) || "#top25" },
    el("span", { class: "paper-status__score" }, `${abbr(away)} ${a}`, el("span", { class: "paper-score__dot" }, " · "), `${h} ${abbr(home)}`),
    el("span", { class: "paper-status__clock" }, el("i", { class: "paper-live-dot", "aria-hidden": "true" }), typeof g.clock === "string" && g.clock ? `${q}, ${g.clock} left` : q),
  );
}

function gameHref(g) {
  if (g.isUs === true) return "#live";
  return isNum(g.gameId) ? `#box=${g.gameId}` : null;
}

function tagOf(g) {
  if (typeof g.bowl === "string" && g.bowl) return g.bowl;
  return g.conferenceGame === true ? text(g.conference || "Conference game") : "Non-conference";
}

function matchBox(g, size, names) {
  const away = obj(g.away);
  const home = obj(g.home);
  const us = usSchool();
  const line = obj(g.headline);
  const status = ["pre", "live", "final", "unplayed"].includes(g.status) ? g.status : "pre";
  const word = g.isUs === true ? "Our game" : status === "live" ? "Live" : status === "unplayed" ? "Not played" : line.kicker || "Top 25";
  const kicker = el("p", { class: `paper-kicker paper-kicker--${status}` }, [word, tagOf(g)].join(" · "));
  const mid = el("div", { class: "paper-mid", dataset: { fit: "1" } }, kicker);
  const href = gameHref(g);
  if (status === "unplayed") {
    // a kept edition's game the season never finished (postponed or cancelled): no score, no headline
    mid.append(el("p", { class: "paper-status__clock paper-unplayed" }, `${rankedName(away)} ${g.neutralSite ? "vs." : "at"} ${rankedName(home)} was not played`), el("p", { class: "paper-facts" }, facts([fmtDate(g.kickoff, "medium"), text(g.venue)])));
  } else if (status === "live") {
    mid.append(statusLine(g), el("p", { class: "paper-facts" }, facts([`kicked off ${fmtTime(g.kickoff)}`, text(g.venue), crewOrTv(g)])));
  } else {
    const headText = typeof line.text === "string" && line.text ? line.text : `${rankedName(away)} ${g.neutralSite ? "vs." : "at"} ${rankedName(home)}`;
    mid.append(el("h3", { class: `paper-head paper-head--match${status === "final" ? " paper-head--final" : ""}` }, href ? el("a", { href }, richText(headText, names)) : richText(headText, names)));
    if (status === "final") {
      mid.append(finalScore(g));
      if (size === "big" && Array.isArray(home.lineScores) && Array.isArray(away.lineScores) && home.lineScores.length && away.lineScores.length) {
        const q = quarterLine({ us: { abbr: abbr(away), scores: away.lineScores, total: away.points }, them: { abbr: abbr(home), scores: home.lineScores, total: home.points } });
        q.classList.add("paper-qline");
        mid.append(q);
      }
      mid.append(el("p", { class: "paper-facts" }, facts([fmtDate(g.kickoff, "medium"), text(g.venue), crewOrTv(g)])));
    } else {
      const l = obj(g.line);
      const spread = typeof l.short === "string" && l.short ? l.short : typeof l.formatted === "string" && l.formatted ? l.formatted : null;
      mid.append(
        el("p", { class: "paper-facts paper-facts--when" }, facts([fmtDate(g.kickoff, "medium"), g.startTimeTbd === true ? "time TBD" : fmtTime(g.kickoff), text(g.venue), crewOrTv(g)])),
        spread || isNum(l.overUnder) ? el("p", { class: "paper-facts paper-facts--line" }, "Line ", el("b", {}, text(spread)), " · Over/under ", el("b", {}, isNum(l.overUnder) ? String(l.overUnder) : "–")) : null,
        wpBar(g),
      );
    }
  }
  const box = el(
    "article",
    { class: `paper-box paper-match paper-match--${size} paper-match--${status}${g.isUs === true ? " paper-match--us" : ""}`, "aria-label": `${text(away.school)} ${g.neutralSite ? "versus" : "at"} ${text(home.school)}` },
    margin(),
    helmet(away, false, away.school === us),
    mid,
    helmet(home, true, home.school === us),
    margin(),
  );
  box.style.setProperty("--c-away", typeof away.color === "string" && away.color ? away.color : "var(--rule-strong)");
  box.style.setProperty("--c-home", typeof home.color === "string" && home.color ? home.color : "var(--rule-strong)");
  // freeze wave F5 (owner 2026-10-20): a tap on Matchup opens the two teams side by side (ui/matchup-sheet.js, Phase 16)
  if (status !== "unplayed" && typeof away.school === "string" && away.school && typeof home.school === "string" && home.school) {
    mid.append(el("p", { class: "paper-tools" }, el("button", { class: "btn btn--quiet paper-matchup", type: "button", "aria-haspopup": "dialog", onclick: () => openMatchupSheet({ away: away.school, home: home.school }) }, "Matchup")));
  }
  return box;
}

// --- the front page (the layout pass, owner 2026-10-22, board 5: https://claude.ai/artifact/Vv827cCpVUGkdDWuN4QeAV) ---------
// "The problem is that the articles become completely uniform down the page": a newspaper's front instead. One dominant
// story (our game) with a banner headline across the page, a deck, the big picture and a column beside it; then modules of
// different widths and depths (the game of the week across two columns, the player, the coach); a rail at the right with
// "By the numbers" and every ranked game in one line of agate; the other headlines as briefs at the foot. Our team first,
// the Top 25 compact (his 1); names never cut (his 2).

const pct = (v) => `${Math.round(v * 100)}%`;

/** A key stat's value in its format: whole numbers, one decimal, or a whole-number rate (Design rules, 2026-10-21). */
function statValue(value, format) {
  if (!isNum(value)) return "–";
  if (format === "pct") return pct(value);
  if (format === "1f") return value.toFixed(1);
  return String(Math.round(value));
}

/** The recap of our game when it belongs to this edition (this week's paper, our game final), else null. */
function recapFor(data, edition, ours) {
  const r = obj(data.recap);
  if (!edition.current || !isNum(r.gameId)) return null;
  const game = ours ? ours.gameId : edition.gameId;
  return isNum(game) && game === r.gameId && r.final && typeof r.final === "object" ? r : null;
}

// a school's name short enough for a line of agate the way a newspaper shortens it; never cut with "…" (his 2)
const SHORTER = [[/\bState\b/g, "St."], [/\bMountain\b/g, "Mtn."], [/\bJunction\b/g, "Jct."], [/\bCentral\b/g, "Cen."], [/\bUniversity\b/g, "U."], [/\bInternational\b/g, "Intl."], [/\bNorthern\b/g, "N."], [/\bSouthern\b/g, "S."], [/\bEastern\b/g, "E."], [/\bWestern\b/g, "W."]];

/** "Dust Devil State" -> "Dust Devil St." in a line of agate (a name of thirteen letters or fewer stays whole). */
/** The game of the week: the matchups come in AP poll order (No. 1 against an unranked team first), so the game drawn
 * large is the best pair of ranked teams (the lowest sum of ranks, then the better rank), else the first other game. */
export function gameOfWeek(matchups, ours = null) {
  const others = records(matchups).filter((g) => g !== ours && g.isUs !== true);
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

export function agateName(school) {
  const name = text(school);
  if (name.length <= 13) return name;
  return SHORTER.reduce((s, [from, to]) => s.replace(from, to), name);
}

/** The skybox under the flag: three refers to inside (the next game, the Top 25, the season or the trivia). */
function skybox(data, edition, recap) {
  const counts = obj(obj(data.rankedWeek).counts);
  const next = recap ? obj(recap.next) : obj(data.nextGame);
  const nextWhen = next.date ? `${fmtDate(next.date, "medium")}${next.startTimeTbd ? "" : `, ${fmtTime(next.date)}`}` : null;
  const nextWho = next.opponent ? `${next.homeAway === "away" ? "at" : next.homeAway === "home" ? "vs" : ""} ${text(next.opponent)}`.trim() : null;
  const top = [isNum(counts.final) && counts.final ? `${counts.final} final` : null, isNum(counts.live) && counts.live ? `${counts.live} live` : null, isNum(counts.pre) && counts.pre ? `${counts.pre} to come` : null].filter(Boolean).join(", ");
  const trivia = lastTriviaData();
  const leader = triviaRunning(trivia) ? records(trivia.standings)[0] : null;
  const rec = recap ? obj(recap.record) : null;
  const items = [
    nextWho ? { kicker: recap ? "Next up" : "This week", words: [nextWho, nextWhen].filter(Boolean).join(", "), href: "#program" } : null,
    top ? { kicker: "Top 25", words: top, href: "#top25" } : null,
    leader && leader.name ? { kicker: "Trivia", words: `${text(leader.name)} lead${Array.isArray(leader.today) ? `, ${leader.today[0]} of ${leader.today[1]}` : ""}`, href: "#trivia" } : rec && isNum(rec.wins) ? { kicker: "The season", words: `${text(ours().name || usSchool())} ${sharedRecord(rec) || ""}`.trim(), href: "#season" } : null,
  ].filter(Boolean);
  if (!items.length) return null;
  return el("nav", { class: "front-sky", "aria-label": "Inside" }, items.map((i) => el("a", { class: "front-sky__item", href: i.href }, el("span", { class: "paper-kicker" }, i.kicker), el("span", { class: "front-sky__words" }, i.words, el("span", { class: "front-sky__go", "aria-hidden": "true" }, " ›")))));
}

/** The lead: the kicker, the banner headline across the page, the deck, the big picture with a column of text beside it. */
function leadPackage({ story, ours, recap, edition, names }) {
  const status = ours ? (["pre", "live", "final", "unplayed"].includes(ours.status) ? ours.status : "pre") : recap ? "final" : null;
  const us = text(ours ? (obj(ours.away).school === usSchool() ? obj(ours.away).abbreviation : obj(ours.home).abbreviation) : null);
  const them = ours ? (obj(ours.away).school === usSchool() ? obj(ours.home) : obj(ours.away)) : {};
  const final = status === "final";
  const kicker = el("p", { class: `paper-kicker${final ? " paper-kicker--final" : ""}` }, ours || recap ? `Game week · ${final ? "Final" : status === "live" ? "Live" : "Preview"}` : KICKERS[story.lead?.topic] || "This week");
  const headWords = ours && obj(ours.headline).text ? obj(ours.headline).text : story.lead ? story.lead.title : null;
  const href = ours ? gameHref(ours) : story.lead ? storyHref(story.lead) : null;
  let banner;
  if (status === "live" && ours) banner = el("div", { class: "front-banner front-banner--live" }, statusLine(ours));
  else if (headWords) banner = el("h2", { class: `front-banner${final ? " paper-head--final" : ""}` }, href ? el("a", href.startsWith("http") ? { href, target: "_blank", rel: "noopener" } : { href }, richText(headWords, names)) : richText(headWords, names));
  else banner = el("p", { class: "paper-empty" }, "No stories from the team's feeds yet this week. They show here as the feeds publish.");
  const pog = recap ? obj(recap.playerOfGame) : null;
  const rec = recap ? sharedRecord(obj(recap.record)) : null;
  const deckWords = recap
    ? [pog && pog.name && pog.isUs !== false ? `${text(pog.name)} is the player of the game` : null, rec ? `${usSchool()} moves to ${rec}` : null].filter(Boolean).join(", and ")
    : ours
      ? [fmtDate(ours.kickoff, "long"), ours.startTimeTbd === true ? "time TBD" : fmtTime(ours.kickoff), ours.venue ? text(ours.venue) : null, crewOrTv(ours)].filter((f) => typeof f === "string" && f && f !== "–").join(" · ")
      : null;
  const deck = deckWords ? el("p", { class: `front-deck${final ? " paper-head--final" : ""}` }, deckWords) : null;
  const stadium = fillPicture("stadium", { seed: seedOf(text(headWords || "stadium")) }, "A pixel stadium under the lights");
  const art = el("figure", { class: "front-art" }, el("div", { class: "paper-pic paper-pic--stadium" }, stadium), ours && ours.venue ? el("figcaption", { class: "front-cutline" }, `${text(ours.venue)}${final ? ", after the final whistle" : status === "live" ? ", the game under way" : ", waiting for kickoff"}.`) : null);
  return el(
    "section",
    { class: "front-lead", "aria-label": "Our game" },
    kicker,
    banner,
    deck,
    el("div", { class: "front-leadrow" }, art, pressBox({ ours, recap, story, them, us, status })),
  );
}

/** The column beside the lead's picture: the turning point, the key numbers in words, what is next; or before the game,
 *  the two teams and the line; always the way into the box score and the program. */
function pressBox({ ours, recap, story, them, us, status }) {
  const paras = [];
  if (recap) {
    const tp = obj(recap.turningPoint);
    const q = isNum(tp.period) ? (tp.period <= 4 ? QUARTERS[tp.period - 1] : "overtime") : null;
    const clock = tp.clock && isNum(tp.clock.minutes) ? `${tp.clock.minutes}:${String(isNum(tp.clock.seconds) ? tp.clock.seconds : 0).padStart(2, "0")}` : null;
    if (q && isNum(tp.usScore) && isNum(tp.themScore)) paras.push(`The turning point came ${clock ? `with ${clock} left in the ` : "in the "}${q}: the play that made it ${tp.usScore}-${tp.themScore}${isNum(tp.usWpBefore) && isNum(tp.usWpAfter) ? `, our chances from ${pct(tp.usWpBefore)} to ${pct(tp.usWpAfter)}` : ""}.`);
    const stats = records(recap.keyStats).filter((s) => typeof s.label === "string").slice(0, 3);
    if (stats.length) paras.push(stats.map((s) => `${s.label}: ${text(us || "us")} ${statValue(s.us, s.format)}, ${text(them.abbreviation || recap.opponent)} ${statValue(s.them, s.format)}`).join(". ") + ".");
    const next = obj(recap.next);
    if (next.opponent) paras.push(`Next: ${text(next.opponent)}${next.homeAway === "home" ? " at home" : next.homeAway === "away" ? " on the road" : ""}${next.date ? `, ${fmtDate(next.date, "long")}` : ""}.`);
  } else if (ours) {
    const l = obj(ours.line);
    const spread = typeof l.short === "string" && l.short ? l.short : typeof l.formatted === "string" && l.formatted ? l.formatted : null;
    const away = obj(ours.away);
    const home = obj(ours.home);
    paras.push(`${rankedName(away)} (${recordText(away)}) ${ours.neutralSite ? "meets" : "visits"} ${rankedName(home)} (${recordText(home)}).`);
    if (spread || isNum(l.overUnder)) paras.push(`The line: ${text(spread)}${isNum(l.overUnder) ? `, over/under ${l.overUnder}` : ""}.`);
  } else if (story.lead) {
    paras.push([story.lead.source, ageOf(story.lead.publishedAt)].filter(Boolean).map(text).join(" · "));
  }
  const gid = ours ? ours.gameId : recap ? recap.gameId : null;
  return el(
    "div",
    { class: `front-col${status === "final" ? " paper-head--final" : ""}` },
    el("p", { class: "front-byline" }, recap || ours ? "From the press box" : "The lead story"),
    paras.map((p) => el("p", {}, p)),
    ours || recap ? el("a", { class: "front-refer", href: ours ? gameHref(ours) || "#live" : `#box=${gid}` }, status === "pre" ? "In Game at kickoff ›" : "The box score ›") : null,
    isNum(gid) ? el("a", { class: "front-refer", href: `#program=${gid}` }, status === "final" ? "The Post-Game Program ›" : "The Pre-Game Program ›") : null,
  );
}

/** The rail's "By the numbers": our game's key stats after the final, the two teams before it, else the week's count. */
function numbersBox({ recap, ours, data }) {
  let rows = [];
  if (recap) {
    rows = records(recap.keyStats).filter((s) => typeof s.label === "string").slice(0, 3).map((s) => ({ big: statValue(s.us, s.format), words: `${s.label.toLowerCase()} for us; ${statValue(s.them, s.format)} for ${text(recap.opponent)}` }));
  } else if (ours) {
    const away = obj(ours.away);
    const home = obj(ours.home);
    const l = obj(ours.line);
    rows = [
      sharedRecord(obj(away.record)) ? { big: sharedRecord(obj(away.record)), words: `${text(away.school)}'s record` } : null,
      sharedRecord(obj(home.record)) ? { big: sharedRecord(obj(home.record)), words: `${text(home.school)}'s record` } : null,
      isNum(l.overUnder) ? { big: String(l.overUnder), words: "points, the over/under" } : null,
    ].filter(Boolean);
  } else {
    const c = obj(obj(data.rankedWeek).counts);
    rows = [isNum(c.final) ? { big: String(c.final), words: "ranked games final" } : null, isNum(c.live) ? { big: String(c.live), words: "ranked games live" } : null, isNum(c.pre) ? { big: String(c.pre), words: "ranked games to come" } : null].filter(Boolean);
  }
  if (!rows.length) return null;
  return el("aside", { class: `front-numbers${recap ? " score-words" : ""}`, "aria-label": "By the numbers" }, el("p", { class: "front-railhead" }, "By the numbers"), rows.map((r) => el("p", { class: "front-num" }, el("b", {}, r.big), el("span", {}, r.words))));
}

/** One ranked game as a line of agate: the winner first after a final, the score and the quarter while live. */
function agateLine(g) {
  const away = obj(g.away);
  const home = obj(g.home);
  const name = (t) => `${isNum(t.rank) ? `${t.rank} ` : ""}${agateName(t.school)}`;
  const status = ["pre", "live", "final", "unplayed"].includes(g.status) ? g.status : "pre";
  let words;
  let state;
  if (status === "final" && isNum(away.points) && isNum(home.points)) {
    const [w, l] = away.points >= home.points ? [away, home] : [home, away];
    const periods = Math.max(Array.isArray(home.lineScores) ? home.lineScores.length : 0, Array.isArray(away.lineScores) ? away.lineScores.length : 0);
    words = [el("b", {}, `${name(w)} ${w.points}`), ", ", el("span", { class: "front-agate__l" }, `${name(l)} ${l.points}`)];
    state = periods > 5 ? `${periods - 4}OT` : periods === 5 ? "OT" : "F";
  } else if (status === "live") {
    words = `${name(away)} ${isNum(away.points) ? away.points : "–"}, ${name(home)} ${isNum(home.points) ? home.points : "–"}`;
    state = el("span", { class: "front-agate__live" }, isNum(g.period) ? (g.period <= 4 ? `Q${g.period}` : "OT") : "Live");
  } else if (status === "unplayed") {
    words = `${name(away)} at ${name(home)}`;
    state = "Not played";
  } else {
    words = `${name(away)} ${g.neutralSite ? "vs." : "at"} ${name(home)}`;
    state = g.startTimeTbd === true ? "TBD" : fmtTime(g.kickoff);
  }
  // plain lines, as a newspaper's agate (a 44 px press target a line would stretch the rail): the cards are on the Top 25 page
  return el("div", { class: `front-agate__row${g.isUs === true ? " is-us" : ""}${status === "final" || status === "live" ? " score-words" : ""}` }, el("span", { class: "front-agate__game" }, words), el("span", { class: "front-agate__state" }, state));
}

/** The rail's scoreboard: every ranked game of the week in one line, ours marked, the teams off this week, the way to the cards. */
function scoreboard(matchups, edition) {
  if (!matchups.length) return null;
  const off = records(edition.offThisWeek).filter((t) => typeof t.school === "string");
  return el(
    "section",
    { class: "front-scores", "aria-label": "Around the Top 25" },
    el("p", { class: "front-railhead" }, "Around the Top 25"),
    el("div", { class: "front-agate" }, matchups.map(agateLine)),
    off.length ? el("p", { class: "front-off" }, el("b", {}, "Off this week: "), off.map((t) => `${isNum(t.rank) ? `${t.rank} ` : ""}${agateName(t.school)}`).join(", ")) : null,
    el("a", { class: "front-refer", href: "#top25" }, "Every game's card on the Top 25 page ›"),
  );
}

/** The player of the game from the recap, when no headline this week names one of ours. */
function pogBox(recap) {
  const p = obj(recap.playerOfGame);
  const pic = fillPicture("player", { seed: seedOf(text(p.name)) }, `${text(p.name)}, in pixels`);
  return el(
    "article",
    { class: "paper-box paper-feat paper-feat--player" },
    margin(),
    cell(pic, "paper-pic--player"),
    el("div", { class: "paper-words" }, el("p", { class: "paper-kicker" }, "Player of the game"), el("h3", { class: "paper-head paper-head--feat" }, `${text(p.name)}${p.position ? `, ${text(p.position)}` : ""}`), el("p", { class: "paper-source" }, isNum(p.value) ? `${p.value.toFixed(1)} points of play value` : "From the play by play")),
  );
}

/** The other headlines as briefs: two columns at the foot, or one column in a tier when no coach's story fills it. */
function briefs(items, { column = false } = {}) {
  const list = records(items).filter(headlineOk).slice(0, 8);
  if (!list.length) return null;
  return el(
    "section",
    { class: `front-briefs${column ? " front-briefs--column" : ""}`, "aria-label": "More headlines" },
    el("p", { class: "front-railhead" }, "More headlines"),
    el(
      "div",
      { class: "front-briefs__list" },
      list.map((item) => {
        const href = storyHref(item);
        return el("p", { class: "front-brief" }, el("b", {}, href ? el("a", { href, target: "_blank", rel: "noopener" }, text(item.title)) : text(item.title)), el("small", {}, [item.source, ageOf(item.publishedAt)].filter(Boolean).map(text).join(" · ") || "Headline"));
      }),
    ),
  );
}

// --- the page ---------------------------------------------------------------------------------------------------------

/** The edition to draw: the server's, or (a server from before items 10-12) this week's headlines with no matchups. */
function editionOf(data) {
  if (data.edition && typeof data.edition === "object") return data.edition;
  if (data.edition === null) return null;
  // no edition at all: a server from before items 10-12, or one that could not read the ranked games (editionError)
  const week = records(data.weeks)[0] || {};
  return { key: "this-week", current: true, label: isNum(week.week) ? `Week ${week.week}` : "This week", week: week.week, season: data.season, opponent: week.opponent, homeAway: week.homeAway, headlines: records(week.headlines), matchups: [] };
}

function feedTrouble(feeds) {
  const entries = feeds && typeof feeds === "object" ? Object.values(feeds).filter((f) => f && typeof f === "object") : [];
  if (entries.length && entries.every((f) => f.status === "error")) return note(`Every feed failed: ${text(entries[0].error)}. The app keeps retrying.`, { kind: "error" });
  const stale = entries.find((f) => f.status === "stale");
  return stale ? note(`${text(stale.name)}: ${text(stale.error)}. The stories shown are from before.`, { kind: "empty" }) : null;
}

function render(envelope, container, asked) {
  const data = obj(envelope?.data);
  const editions = records(data.editions);
  const edition = editionOf(data);
  if (!edition) {
    container.replaceChildren(
      el(
        "div",
        { class: "page page--wide paper-page" },
        band({
          id: "paper-missing",
          title: "Newspaper",
          collapsible: false,
          state: { status: "ready" },
          body: () =>
            el(
              "div",
              {},
              note(`No paper was kept for ${asked ? text(asked).replace("week-", "week ") : "that week"}. The paper keeps every week's edition from the week it started saving them, and an earlier week's headlines when the feeds had any for it. The arrows by the paper's name page through the weeks it has.`, { kind: "empty" }),
              el("p", {}, el("a", { class: "btn", href: "#newspaper" }, "This week's paper")),
            ),
        }),
      ),
    );
    return null;
  }
  const matchups = records(edition.matchups).filter((g) => g.home && typeof g.home === "object" && g.away && typeof g.away === "object");
  const story = pickStories(edition.headlines);
  const names = [
    ...matchups.flatMap((g) => [obj(g.away), obj(g.home)]).flatMap((t) => [isNum(t.rank) ? rankedName(t) : null, t.school]),
    ...records(edition.headlines).flatMap((h) => records(h.players).map((p) => p.name)),
  ];
  // the front page (board 5): our game leads; the best pair of ranked teams is the game of the week; every ranked game is
  // a line in the rail's scoreboard; the player and the coach (or the player of the game, or another story) between them
  const ours = matchups.find((g) => g.isUs === true) || null;
  const top = gameOfWeek(matchups, ours);
  const recap = recapFor(data, edition, ours);
  const rest = [...story.rest];
  const leadAside = (ours || recap) && story.lead ? story.lead : null; // the lead is our game's own; the feed's headline about it goes to the briefs
  const player = story.player ? playerBox(story.player, names) : recap && obj(recap.playerOfGame).name ? pogBox(recap) : rest.length ? articleBox(rest.shift(), "left", names) : null;
  const coach = story.coach ? coachBox(story.coach, names) : rest.length ? articleBox(rest.shift(), "right", names) : null;
  const numbers = numbersBox({ recap, ours, data });
  const tier2 = top || numbers ? el("div", { class: `front-tier front-tier--two${top ? "" : " front-tier--rail-only"}` }, top ? el("div", { class: "front-span2" }, matchBox(top, "big", names)) : null, numbers ? el("div", { class: "front-rail" }, numbers) : null) : null;
  const scores = scoreboard(matchups, edition);
  const more = leadAside ? [...rest, leadAside] : rest;
  // no coach's story this week: the other headlines take the coach's column instead of the foot, so no column stands empty
  const middle = coach ? el("div", { class: "front-mod front-mod--coach" }, coach) : more.some(headlineOk) ? el("div", { class: "front-mod front-mod--briefs" }, briefs(more, { column: true })) : null;
  const tier3 = player || middle || scores ? el("div", { class: "front-tier front-tier--three" }, player ? el("div", { class: "front-mod front-mod--player" }, player) : null, middle, scores ? el("div", { class: "front-rail" }, scores) : null) : null;
  const earlier = edition.current
    ? null
    : note(`${text(edition.label)} edition, as the paper printed it${edition.rebuilt ? ": its headlines (the paper kept its matchups from the week this feature arrived)" : ""}.`, { kind: "empty" });
  const page = el(
    "div",
    { class: "page page--wide paper-page paper front" },
    masthead(data, edition, editions),
    edition.current ? skybox(data, edition, recap) : null,
    edition.current ? feedTrouble(data.feeds) : null,
    earlier,
    edition.current ? null : el("p", { class: "paper-back" }, el("a", { class: "btn btn--quiet", href: "#newspaper" }, "This week's paper")),
    leadPackage({ story, ours, recap, edition, names }),
    tier2,
    tier3,
    coach ? briefs(more) : null,
  );
  container.replaceChildren(page);
  return page;
}

// --- fitting the page ---------------------------------------------------------------------------------------------------

/** Fit the front page to the screen: a team's name under its helmet on one line, the pictures drawn to their boxes. The
 *  modules keep their own heights (board 5: a newspaper's modules differ in depth); on a phone a long name may break. */
export function layoutPaper(root) {
  if (!root || !root.isConnected || !(root.clientWidth > 0)) return null;
  const width = root.clientWidth;
  const phone = width < 700;
  root.classList.toggle("paper--phone", phone);
  fitNames(root);
  if (phone) loosenNames(root);
  refitPictures(root);
  return { width, phone };
}

// --- the view -----------------------------------------------------------------------------------------------------------

export function createNewspaperView({ onStatus, edition = null } = {}) {
  const asked = typeof edition === "string" && EDITION.test(edition) ? edition : null;
  const delay = Number(getPrefs().delaySeconds);
  const url = `/api/newspaper?delay=${Number.isFinite(delay) ? delay : 30}${asked ? `&edition=${encodeURIComponent(asked)}` : ""}`;
  let page = null;
  let frame = null;
  let timer = null;
  const layout = () => {
    frame = null;
    try {
      layoutPaper(page);
    } catch (error) {
      console.error("The newspaper could not be fitted to the screen; it keeps its plain sizes.", error);
    }
  };
  const schedule = () => {
    if (frame === null && typeof requestAnimationFrame === "function") frame = requestAnimationFrame(layout);
  };
  const onResize = () => {
    clearTimeout(timer);
    timer = setTimeout(schedule, 150);
  };
  const inner = poller({
    url,
    refreshMs: asked ? pollMs() : REFRESH_MS,
    holdDuringRuns: Boolean(asked), // this week's paper carries live scores: never held for a data load, like the Top 25 (freeze wave F1, F5); a kept edition can wait
    onStatus,
    render: (envelope, container) => {
      page = render(envelope, container, asked);
      schedule();
      if (typeof document !== "undefined" && document.fonts?.ready) document.fonts.ready.then(schedule).catch(() => {});
    },
    renderError: (message, container, retry) => container.replaceChildren(errorPanel("Newspaper", message, retry)),
    loadingDetail: asked ? "That week's edition" : "This week's paper",
    renderLoading: () =>
      el(
        "div",
        { class: "page page--wide paper-page paper" },
        el("header", { class: "paper-mast" }, el("div", { class: "skel", style: { width: "min(420px, 70%)", height: "40px", margin: "4px auto", gridColumn: "1 / -1" } })),
        el("div", { class: "paper-row paper-row--a" }, el("div", { class: "paper-box paper-box--skel" }, el("div", { class: "skel" })), el("div", { class: "paper-box paper-box--skel" }, el("div", { class: "skel" }))),
        el("div", { class: "paper-row paper-row--b" }, el("div", { class: "paper-box paper-box--skel" }, el("div", { class: "skel" })), el("div", { class: "paper-box paper-box--skel" }, el("div", { class: "skel" }))),
      ),
  });
  const win = typeof window !== "undefined" && typeof window.addEventListener === "function" ? window : null;
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
