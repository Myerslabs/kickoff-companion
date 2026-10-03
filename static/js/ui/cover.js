// The program cover: the matchup as the hero, kickoff in local time, venue, TV, countdown,
// line and win probability. The one place motion is allowed on first reveal.
//
// Phase 16 (stream PROGRAM; audit P-03, P-10, L-11, G3-10, P-08, P-01; GX-07 face-off). Frozen API (the Live sheet and the
// Archive call it too; every new prop is optional, so their old calls draw what they drew):
//   cover({ us, them, homeIsUs, date, startTimeTbd, venue, neutralSite, tv, line, pregame, reveal, now, state,
//           usPoints, themPoints, kicker, liveHref, archiveHref, prev, next, extra })  -> <section class="cover">
//       state "final" draws the final score ("SWT 31 · 24 GBS", winner chalk, loser fog, W or L); otherwise the
//       cover works the state out from the clock: a countdown, "Kickoff in 38 min" inside the hour, and
//       "Under way" once kickoff has passed (never for a TBD kickoff, whose time is a placeholder).
//       liveHref: "Open the Live sheet" under way (primary) and inside the hour (secondary). archiveHref: "Full
//       game in the Archive" on a final (pass it only when the archive holds the game). prev / next:
//       { href, label } arrows in the kicker row. extra: a node for the cover's foot (the page's jump list).
//       The returned section has tick(now = the clock): it redraws the countdown and the buttons in place
//       (the cover itself is not rebuilt) and returns the state it now shows.
//   coverState({ state, date, startTimeTbd, now })   "final" | "live" | "soon" | "pre" | "tbd" | "unknown".
//   coverSkeleton()                                  the loading cover in the cover's real shape.
//   countdownParts(kickoffIso, now), openingLine(spreadOpen, spread, homeName, awayName)   as before.

import { usLabel } from "../identity.js";
import { el, fmtDate, fmtNum, fmtTime, isNum, teamLink, teamLogo, text } from "./dom.js";
import { nationalHref, pollHref } from "./national-link.js";
import { pollBadge } from "./stat-table.js";
import { listLink } from "./two-team.js";

const SOON_MS = 60 * 60 * 1000;

function record(rec) {
  if (!rec || !isNum(rec.wins) || !isNum(rec.losses)) return "–";
  return rec.ties ? `${rec.wins}-${rec.losses}-${rec.ties}` : `${rec.wins}-${rec.losses}`;
}

function obj(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function isHash(href) {
  return typeof href === "string" && href.startsWith("#") && href.length > 1;
}

export function countdownParts(kickoffIso, now = new Date(Date.now())) {
  const kickoff = new Date(kickoffIso);
  if (Number.isNaN(kickoff.getTime())) return null;
  const diff = Math.floor((kickoff.getTime() - now.getTime()) / 1000);
  if (diff <= 0) return { passed: true, days: 0, hours: 0, minutes: 0 };
  return { passed: false, days: Math.floor(diff / 86400), hours: Math.floor((diff % 86400) / 3600), minutes: Math.floor((diff % 3600) / 60) };
}

/**
 * "Swampwater Tech -1.5" for an opening spread that differs from the current one, else null. CFBD's spread
 * is from the home side: negative, the home team is favored. Exported for the tests (Phase 13).
 */
export function openingLine(spreadOpen, spread, homeName, awayName) {
  if (!isNum(spreadOpen) || (isNum(spread) && spreadOpen === spread)) return null;
  if (spreadOpen === 0) return "a pick'em";
  const favored = spreadOpen < 0 ? homeName : awayName;
  return `${text(favored)} -${fmtNum(Math.abs(spreadOpen), 1).replace(/\.0$/, "")}`;
}

/** What the cover shows: "final", "live" (kickoff passed), "soon" (within the hour), "pre", "tbd" or "unknown". */
export function coverState({ state, date, startTimeTbd, now = new Date(Date.now()) } = {}) {
  if (state === "final") return "final";
  const kickoff = new Date(date);
  if (!date || Number.isNaN(kickoff.getTime())) return "unknown";
  if (startTimeTbd) return "tbd"; // the time is a placeholder: never "Under way" or a minute countdown from it
  const at = now instanceof Date && !Number.isNaN(now.getTime()) ? now : new Date(Date.now());
  const left = kickoff.getTime() - at.getTime();
  if (left <= 0) return "live";
  return left <= SOON_MS ? "soon" : "pre";
}

function daysUntil(date, now) {
  const kickoff = new Date(date);
  const a = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const b = new Date(kickoff.getFullYear(), kickoff.getMonth(), kickoff.getDate()).getTime();
  return Math.round((b - a) / 86400000);
}

/** The final score, ours first: "SWT 31 · 24 GBS", winner in chalk, loser in fog (L-11: the archive's hero too). */
function finalScore(props, usAbbr, themAbbr) {
  const us = props.usPoints;
  const them = props.themPoints;
  if (!isNum(us) || !isNum(them)) return el("div", { class: "cover__countdown cover__state cover__state--final" }, el("span", { class: "num" }, "Final"));
  const result = us > them ? "W" : us < them ? "L" : "T";
  const side = (won, abbr, points, first) => el("span", { class: `cover__score-side ${won ? "is-winner" : "is-loser"}` }, first ? `${abbr} ${points}` : `${points} ${abbr}`);
  return el(
    "div",
    { class: `cover__countdown cover__state cover__state--final cover__state--${result === "W" ? "won" : result === "L" ? "lost" : "tied"}` },
    el("span", { class: "num cover__score", "aria-label": `Final: ${usAbbr} ${us}, ${themAbbr} ${them}` }, side(us >= them, usAbbr, us, true), el("span", { class: "cover__score-dot" }, " · "), side(them >= us, themAbbr, them, false)),
    el("small", {}, el("b", { class: `cover__result${result === "W" ? " res--w" : result === "L" ? " res--l" : ""}` }, result === "W" ? "Won" : result === "L" ? "Lost" : "Tied"), " · Final"),
  );
}

/** The middle block for a state: countdown, "Kickoff in 38 min", "Under way", a TBD date, or the final. */
function stateBlock(kind, props, now, usAbbr, themAbbr) {
  if (kind === "final") return finalScore(props, usAbbr, themAbbr);
  const box = (cls, main, sub) => el("div", { class: `cover__countdown cover__state cover__state--${cls}` }, main, sub ? el("small", {}, sub) : null);
  if (kind === "unknown") return box("unknown", el("span", { class: "num" }, "–"), "kickoff not set");
  if (kind === "tbd") {
    const days = daysUntil(props.date, now);
    if (days > 1) return box("tbd", el("span", { class: "num" }, `${days} days`), "to game day, kickoff time TBD");
    return box("tbd", el("span", { class: "num" }, days === 1 ? "Tomorrow" : days === 0 ? "Game day" : "Time TBD"), "kickoff time TBD");
  }
  if (kind === "live") return box("live", el("span", { class: "num" }, "Under way"), `kicked off ${fmtTime(props.date)}`);
  const parts = countdownParts(props.date, now);
  if (!parts) return box("unknown", el("span", { class: "num" }, "–"), "kickoff not set");
  if (kind === "soon") return box("soon", el("span", { class: "num" }, "Kickoff in ", el("b", { class: "cover__soon" }, `${Math.max(1, parts.minutes)} min`)), null);
  const txt = parts.days > 0 ? `${parts.days}d ${parts.hours}h ${parts.minutes}m` : parts.hours > 0 ? `${parts.hours}h ${parts.minutes}m` : `${parts.minutes} min`;
  return box("pre", el("span", { class: "num" }, txt), "to kickoff");
}

/** The buttons under the hero: the Live sheet while it matters, the Archive after a final it holds. */
function actions(kind, props) {
  const out = [];
  if (isHash(props.liveHref) && (kind === "live" || kind === "soon")) out.push(el("a", { class: `btn${kind === "live" ? " btn--primary" : ""} cover__action`, href: props.liveHref }, "Open the Live sheet"));
  if (kind === "final" && isHash(props.archiveHref)) out.push(el("a", { class: "btn cover__action", href: props.archiveHref }, "Full game in the Archive"));
  return out;
}

function navArrow(which, target) {
  const t = obj(target);
  if (!isHash(t.href)) return el("span", { class: `cover__nav cover__nav--${which} cover__nav--off`, "aria-hidden": "true" });
  const word = which === "prev" ? "Previous" : "Next";
  const label = typeof t.label === "string" && t.label.trim() ? t.label.trim() : null;
  return el("a", { class: `cover__nav cover__nav--${which}`, href: t.href, "aria-label": `${word} program${label ? `: ${label}` : ""}`, title: label ? `${word}: ${label}` : `${word} program` }, which === "prev" ? "‹" : "›");
}

/** P-15 item 2 (owner look): the pregame win probability as the newspaper's thin bar, ours from the left. */
function winBar(usWp, usAbbr, themAbbr) {
  if (!isNum(usWp) || usWp < 0 || usWp > 1) return null;
  const us = Math.round(usWp * 100);
  const them = 100 - us;
  return el(
    "div",
    { class: "cover__wp" },
    el("span", { class: "cover__wp-caption" }, "Pregame win probability"),
    el("span", { class: "cover__wp-label cover__wp-label--us" }, `${usAbbr} ${us}%`),
    el("div", { class: "wpbar cover__wpbar", role: "img", "aria-label": `Pregame win probability: ${usAbbr} ${us}%, ${themAbbr} ${them}%` }, el("div", { class: "wpbar__home wpbar__home--us", style: { width: `${us}%` } }), el("div", { class: "wpbar__away", style: { width: `${them}%` } })),
    el("span", { class: "cover__wp-label" }, `${them}% ${themAbbr}`),
  );
}

/** GX-17 (owner look): the last five results as W/L squares, newest on the right; each says its score. Exported for the tests. */
export function formGuide(form) {
  const games = (Array.isArray(form) ? form : []).filter((g) => g && typeof g === "object" && ["W", "L", "T"].includes(g.result)).slice(-5);
  if (!games.length) return null;
  const says = (g) => {
    const score = isNum(g.points) && isNum(g.opponentPoints) ? ` ${g.points}-${g.opponentPoints}` : "";
    const vs = typeof g.opponent === "string" && g.opponent ? ` ${g.homeAway === "away" ? "at" : "vs"} ${g.opponent}` : "";
    return `${g.result}${score}${vs}`;
  };
  return el(
    "div",
    { class: "form-guide", role: "img", "aria-label": `Last ${games.length}: ${games.map(says).join("; ")}` },
    games.map((g) => el("span", { class: `form-guide__game form-guide__game--${g.result.toLowerCase()}`, title: says(g) }, g.result)),
  );
}

/** Record, conference record, AP poll badge and the SP+ link for one team (each rank opens its list). */
function recordParts(team) {
  const t = obj(team);
  const parts = [];
  if (isNum(t.record?.wins)) parts.push(record(t.record));
  if (isNum(t.conferenceRecord?.wins)) parts.push(`${record(t.conferenceRecord)} conf`);
  if (isNum(t.apRank)) parts.push(pollBadge(t.apRank, "AP", { href: pollHref("AP", { team: t.school }), label: text(t.school) }));
  const sp = obj(t.sp);
  if (isNum(sp.rank)) parts.push(listLink(nationalHref(typeof sp.metric === "string" ? sp.metric : "rating:sp", { team: t.school }), `SP+ #${sp.rank}`, { rank: sp.rank, of: sp.of, name: "SP+", className: "cover__link" }));
  return parts;
}

/**
 * cover({ us, them, homeIsUs, date, startTimeTbd, venue, neutralSite, tv, line, pregame, reveal, now, state, usPoints, themPoints, kicker, liveHref, archiveHref, prev, next, extra })
 */
export function cover(props) {
  const p = obj(props);
  const { homeIsUs = true, date, startTimeTbd, venue, neutralSite, tv, reveal = false } = p;
  const now = p.now instanceof Date ? p.now : new Date(Date.now());
  const us = obj(p.us);
  const them = obj(p.them);
  const line = obj(p.line);
  const pregame = obj(p.pregame);
  const away = homeIsUs ? them : us;
  const home = homeIsUs ? us : them;
  const usAbbr = text(us.abbreviation || usLabel());
  const themAbbr = text(them.abbreviation || (typeof them.school === "string" ? them.school.slice(0, 3).toUpperCase() : null));
  const usWp = isNum(pregame.homeWinProbability) ? (homeIsUs ? pregame.homeWinProbability : 1 - pregame.homeWinProbability) : null;
  let kind = coverState({ state: p.state, date, startTimeTbd, now });

  const when = [fmtDate(date, "long"), startTimeTbd ? "time TBD" : fmtTime(date), text(venue) + (neutralSite ? " (neutral site)" : ""), tv ? `on ${text(tv)}` : null].filter(Boolean).join(" · ");

  // GX-07 (owner pick 2026-09-28): a face-off. Our 112px dark-variant logo on the left, as in every
  // two-team table, the opponent's facing it on the right, each name and record under its logo.
  const teamBlock = (team, side) => {
    const parts = recordParts(team);
    return el(
      "div",
      { class: `cover__side cover__side--${side}` },
      teamLogo(team, { size: 112, lazy: false, className: "cover__logo cover__logo--hero" }),
      el("div", { class: "cover__name" }, team.school ? teamLink(team.school, text(team.school)) : text(null)),
      el("div", { class: "cover__rec" }, parts.length ? parts.flatMap((part, index) => [index ? " · " : null, part]) : "No record yet"),
      formGuide(team.form),
    );
  };

  const lineParts = [];
  const homeName = homeIsUs ? us.school : them.school;
  const awayName = homeIsUs ? them.school : us.school;
  const opened = openingLine(line.spreadOpen, line.spread, homeName, awayName);
  if (line.formatted) lineParts.push(el("span", {}, "Line ", el("b", { dataset: { k: "cover-line" } }, text(line.formatted)), opened ? el("small", { class: "cover__opened" }, ` (opened ${opened})`) : null));
  const totalMoved = isNum(line.overUnderOpen) && isNum(line.overUnder) && line.overUnderOpen !== line.overUnder;
  if (isNum(line.overUnder)) lineParts.push(el("span", {}, "Over/under ", el("b", { dataset: { k: "cover-total" } }, fmtNum(line.overUnder, 1)), totalMoved ? el("small", { class: "cover__opened" }, ` (opened ${fmtNum(line.overUnderOpen, 1)})`) : null));
  const noLine = kind === "final" ? "No line was recorded." : "No betting line yet.";

  const middle = el("div", { class: "cover__middle" }, stateBlock(kind, p, now, usAbbr, themAbbr));
  const actionRow = el("div", { class: "cover__actions" }, actions(kind, p));
  const extra = typeof Node !== "undefined" && p.extra instanceof Node ? p.extra : null;

  const section = el(
    "section",
    { class: `cover${reveal ? " cover--reveal" : ""}`, "aria-label": "Game program cover", dataset: { state: kind } },
    el("div", { class: "cover__kicker-row" }, navArrow("prev", p.prev), el("div", { class: "cover__kicker" }, text(p.kicker || "Game program")), navArrow("next", p.next)),
    el("h1", { class: "cover__matchup sr-only" }, `${text(away.school)} ${neutralSite ? "vs" : "at"} ${text(home.school)}`),
    el(
      "div",
      { class: "cover__faceoff" },
      teamBlock(us, "us"),
      el("div", { class: "cover__center" }, el("span", { class: "cover__vs" }, neutralSite || homeIsUs ? "vs" : "at"), middle),
      teamBlock(them, "them"),
    ),
    el("div", { class: "cover__when" }, when),
    lineParts.length ? el("div", { class: "cover__line" }, lineParts) : el("div", { class: "cover__line" }, el("span", {}, noLine)),
    kind !== "final" ? winBar(usWp, usAbbr, themAbbr) : null,
    el("div", { class: "cover__foot" }, actionRow, extra),
  );

  /** Redraw the countdown and the buttons in place (P-10): no rebuild, no replayed reveal. */
  section.tick = (at = new Date(Date.now())) => {
    const when2 = at instanceof Date && !Number.isNaN(at.getTime()) ? at : new Date(Date.now());
    const next = coverState({ state: p.state, date, startTimeTbd, now: when2 });
    middle.replaceChildren(stateBlock(next, p, when2, usAbbr, themAbbr));
    if (next !== kind) actionRow.replaceChildren(...actions(next, p));
    kind = next;
    section.dataset.state = next;
    return next;
  };
  return section;
}

/** The loading cover in the real cover's shape: kicker, two logos facing each other, the countdown, the when line (P-04 item 5). */
export function coverSkeleton() {
  const bar = (width, height) => el("div", { class: "skel", style: { width, height, margin: "0" } });
  const side = (which) => el("div", { class: `cover__side cover__side--${which}` }, el("div", { class: "skel skel--logo" }), bar("120px", "18px"), bar("90px", "12px"));
  return el(
    "section",
    { class: "cover cover--skeleton", "aria-hidden": "true" },
    bar("180px", "12px"),
    el("div", { class: "cover__faceoff" }, side("us"), el("div", { class: "cover__center" }, bar("24px", "14px"), bar("200px", "44px")), side("them")),
    el("div", { class: "cover__when" }, bar("60%", "16px")),
  );
}
