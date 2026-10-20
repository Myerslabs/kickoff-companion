// The Newspaper (N1 to N4), redone to the owner's whiteboard (queue items 10 to 12, mock approved 2026-10-13).
//
// The page is a front page that fills the screen "like a newspaper", in boxes of two across:
//   the masthead: this week's name (steady within a week, made from the team's own names), the date and the edition,
//     and the ‹ › arrows to the other weeks' editions (the weekly keepsake, kept on the server for the season);
//   row 1: our lead story beside a pixel stadium | the week's top-ranked game, a pixel helmet for each team facing the
//     other's, the game's facts between them;
//   row 2: the player feature (the headline naming one of our players, his headshot in pixels) | the coach's story
//     (the made-up pixel coach); headlines only (owner), each a link out;
//   then "the paper continues in the same format" (owner): rows of two mixing the week's other headlines and the other
//     AP-ranked games, "the higher the ranked game, the higher the article", the matchup switching sides.
// A matchup carries a funny headline before kickoff and after the final only ("Funny headline only for the pregame and
// postgame articles"); while a game is on it shows the score, the quarter and the clock, our game following the
// spoiler delay. A matchup opens its box score (ours opens In Game); a story opens its source. A finished top game shows
// its score by quarter. The scores table, the slate and the earlier-weeks bands left the paper: every ranked game's
// score is on the Top 25 page.
//
// Every row's boxes are one height and the headlines take the largest size that fits (ui/paper-fit.js); the pictures
// are drawn on a grid shaped like their box (ui/pixel-art.js fillPicture). On a phone the boxes stack in the same order.
// The page refreshes every minute (live matchups); an earlier edition is read once from its file.
//
//   mastheadName(season, week, who)   this week's paper's name
//   pickStories(headlines, us)         { lead, player, coach, rest }: the week's stories for the boxes
//   paperRows(stories, matchups)       the rows after the first two: [["M" | "A", item], ...] pairs
//   createNewspaperView({ onStatus, edition })   edition: "week-6" or "postseason" opens an earlier edition

import { ours, usSchool } from "../identity.js";
import { el, fmtDate, fmtTime, isNum, obj, records, teamLink, text, recordText as sharedRecord } from "../ui/dom.js";
import { crewText } from "../ui/game-staff.js";
import { openMatchupSheet } from "../ui/matchup-sheet.js";
import { ageOf } from "../ui/news.js";
import { fitNames, fitRows, loosenNames } from "../ui/paper-fit.js";
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

/** The rows after the first two: two boxes a row, a matchup and a story switching sides, then whatever is left. */
export function paperRows(stories, matchups) {
  const as = [...records(stories)];
  const ms = [...records(matchups)];
  const pattern = ["MA", "AM", "MM"];
  const rows = [];
  for (let i = 0; as.length || ms.length; i += 1) {
    let p = pattern[i % pattern.length];
    if (!as.length) p = "MM";
    if (!ms.length) p = "AA";
    const pair = [];
    for (const k of p) {
      if (k === "M" && ms.length) pair.push(["M", ms.shift()]);
      else if (k === "A" && as.length) pair.push(["A", as.shift()]);
      else if (ms.length) pair.push(["M", ms.shift()]);
      else if (as.length) pair.push(["A", as.shift()]);
    }
    rows.push(pair);
  }
  return rows;
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

function leadBox(item, names) {
  const stadium = fillPicture("stadium", { seed: seedOf(text(item?.title || "stadium")) }, "A pixel stadium under the lights");
  if (!item) {
    return el("article", { class: "paper-box paper-lead paper-lead--empty" }, el("div", { class: "paper-words" }, el("p", { class: "paper-kicker" }, "This week"), el("p", { class: "paper-empty" }, "No stories from the team's feeds yet this week. They show here as the feeds publish.")), cell(stadium, "paper-pic--stadium"), margin());
  }
  return el("article", { class: "paper-box paper-lead" }, words(item, KICKERS[item.topic] || "This week", "paper-head--lead", names), cell(stadium, "paper-pic--stadium"), margin());
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
  const [top, ...others] = matchups;
  const rowA = el("div", { class: `paper-row paper-row--a${top ? "" : " paper-row--one"}` }, leadBox(story.lead, names), top ? matchBox(top, "big", names) : null);
  const rest = [...story.rest];
  const rowBBoxes = [story.player ? playerBox(story.player, names) : rest.length ? articleBox(rest.shift(), "left", names) : null, story.coach ? coachBox(story.coach, names) : rest.length ? articleBox(rest.shift(), "left", names) : null].filter(Boolean);
  const rowB = rowBBoxes.length ? el("div", { class: `paper-row paper-row--b${rowBBoxes.length === 1 ? " paper-row--one" : ""}` }, ...rowBBoxes) : null;
  const rows = paperRows(rest, others).map((pair) =>
    el(
      "div",
      { class: `paper-row paper-row--rest${pair.length === 1 ? " paper-row--one" : ""}` },
      pair.map(([kind, item], i) => (kind === "M" ? matchBox(item, "half", names) : articleBox(item, i ? "right" : "left", names))),
    ),
  );
  const earlier = edition.current
    ? null
    : note(`${text(edition.label)} edition, as the paper printed it${edition.rebuilt ? ": its headlines (the paper kept its matchups from the week this feature arrived)" : ""}.`, { kind: "empty" });
  const page = el(
    "div",
    { class: "page page--wide paper-page paper" },
    masthead(data, edition, editions),
    edition.current ? feedTrouble(data.feeds) : null,
    earlier,
    edition.current ? null : el("p", { class: "paper-back" }, el("a", { class: "btn btn--quiet", href: "#newspaper" }, "This week's paper")),
    rowA,
    rowB,
    ...rows,
  );
  container.replaceChildren(page);
  return page;
}

// --- fitting the page ---------------------------------------------------------------------------------------------------

const clamp = (lo, v, hi) => Math.max(lo, Math.min(hi, v));
const FLOOR = 15; // no fitted text under this (the 13 px rule, with room): a size taken from a small lead never goes lower

function setFit(root, selector, cap, min) {
  for (const n of root.querySelectorAll(selector)) {
    n.dataset.cap = String(cap);
    n.dataset.min = String(min);
  }
}

const boxesOf = (row) => [...row.children].filter((n) => n.classList?.contains("paper-box"));

/** Fit every row to one height and its type to its boxes; on a phone the CSS sizes stand. */
export function layoutPaper(root) {
  if (!root || !root.isConnected || !(root.clientWidth > 0)) return null;
  const width = root.clientWidth;
  const phone = width < 700;
  root.classList.toggle("paper--phone", phone);
  for (const n of root.querySelectorAll("[data-fit]")) n.style.fontSize = "";
  for (const b of root.querySelectorAll(".paper-box")) b.style.height = "";
  fitNames(root);
  if (phone) {
    loosenNames(root);
    refitPictures(root);
    return { phone: true };
  }
  const rowA = root.querySelector(".paper-row--a");
  const leadTarget = clamp(26, width * 0.021, 44);
  root.style.setProperty("--paper-top", `${Math.round(leadTarget)}px`); // no score numeral bigger than the lead's headline
  setFit(root, ".paper-head--lead", leadTarget * 1.3, leadTarget * 0.8);
  setFit(root, ".paper-match--big .paper-mid", Math.max(17, Math.min(leadTarget - 4, clamp(20, width * 0.018, 36))), 17);
  const lead = rowA?.querySelector(".paper-lead:not(.paper-lead--empty)");
  const boxesA = rowA ? boxesOf(rowA) : [];
  fitRows(rowA ? [{ row: rowA, boxes: boxesA, primary: lead ? boxesA.indexOf(lead) : null, target: leadTarget, minHeight: width * 0.22 }] : []); // a short lead never squeezes the top game
  const leadFont = parseFloat(lead?.querySelector(".paper-head--lead")?.style.fontSize || "") || leadTarget;
  root.style.setProperty("--paper-top", `${Math.floor(leadFont)}px`);
  const featCap = Math.max(FLOOR + 2, Math.min(leadFont - 4, clamp(22, width * 0.022, 42)));
  setFit(root, ".paper-head--feat", featCap, Math.max(FLOOR + 1, featCap * 0.6));
  const artCap = Math.max(FLOOR + 2, Math.min(leadFont - 6, clamp(18, width * 0.018, 30)));
  setFit(root, ".paper-row--b .paper-head--art", featCap, Math.max(FLOOR + 1, featCap * 0.6));
  setFit(root, ".paper-row--rest .paper-head--art", artCap, Math.max(FLOOR, artCap * 0.62));
  setFit(root, ".paper-match--half .paper-mid", Math.max(FLOOR + 1, Math.min(leadFont - 8, clamp(17, width * 0.0135, 26))), FLOOR);
  const later = [...root.querySelectorAll(".paper-row--b, .paper-row--rest")].map((row) => ({ row, boxes: boxesOf(row), minHeight: width * (row.classList.contains("paper-row--b") ? 0.13 : 0.12) }));
  const heights = fitRows(later);
  refitPictures(root);
  return { width, leadTarget, leadFont, featCap, artCap, heights };
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
