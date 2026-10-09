// The matchup sheet (UX-12, Phase 16 NV): any two FBS teams side by side in a side sheet, from
// GET /api/matchup?away=&home= (the cached all-FBS answers only; no per-school calls). Each team's record,
// polls, SP+, talent and last five results, the live or final score when the two meet this week, then the
// shared two-team table (ui/two-team.js, final pass): one row per stat grouped by the side of the ball, the
// value and its rank chip in one cell, the tug-of-war bar between the teams. We sit first whenever we are in
// the game (every two-team table reads us, then them); between two other teams the away team is first, as the
// game is said, and the bars take those teams' own colors. Every chip links to its national list with that
// team's row marked.
//
// API (Scores rows and Newspaper slate cards open it):
//   openMatchupSheet({ away, home }) -> the openSheet handle plus reload(), or null without two names.
//   matchupBody(envelope, { onRetry })  the sheet's content, for the tests and the styleguide.
//   matchupOrder(data)                  { first, second, firstKey, secondKey, joiner, neutral }: who sits first.
//   sheetTitle(away, home, { homeIsUs, neutralSite })  "Us vs them", "us at them" or "away at home".

import { isUs } from "../identity.js";
import { ageSeconds, fetchPatient } from "../views/common.js";
import { rejectReason } from "./colors.js";
import { DASH, el, fmtDateTime, fmtStat, isNum, obj, records, teamLink, teamLogo, text } from "./dom.js";
import { nationalHref, pollHref } from "./national-link.js";
import { openSheet } from "./remote.js";
import { band, stateBlock } from "./states.js";
import { pollBadge, rankChip, statTableSkeleton } from "./stat-table.js";
import { twoTeamTable } from "./two-team.js";

const NAME_MAX = 60;

function name(value) {
  return typeof value === "string" && value.trim() && value.trim().length <= NAME_MAX ? value.trim() : null;
}

function recordText(record) {
  const r = obj(record);
  if (!isNum(r.wins) || !isNum(r.losses)) return null;
  return isNum(r.ties) && r.ties > 0 ? `${r.wins}-${r.losses}-${r.ties}` : `${r.wins}-${r.losses}`;
}

function fbsCount(data) {
  const row = (Array.isArray(data.rows) ? data.rows : []).find((r) => isNum(obj(r).of));
  return row ? row.of : null;
}

function formLine(form) {
  const games = (Array.isArray(form) ? form : []).filter((g) => g && typeof g === "object" && ["W", "L", "T"].includes(g.result));
  if (!games.length) return el("span", { class: "mx-form mx-form--none" }, "No games yet");
  return el(
    "span",
    { class: "mx-form", "aria-label": `Last ${games.length}: ${games.map((g) => `${g.result === "W" ? "won" : g.result === "L" ? "lost" : "tied"} ${isNum(g.points) ? g.points : DASH}-${isNum(g.opponentPoints) ? g.opponentPoints : DASH} ${g.homeAway === "away" ? "at" : "vs"} ${text(g.opponent)}`).join(", ")}` },
    games.map((g) => el("span", { class: `mx-form__game mx-form__game--${g.result.toLowerCase()}`, title: `${g.homeAway === "away" ? "at" : "vs"} ${text(g.opponent)}, ${isNum(g.points) ? g.points : DASH}-${isNum(g.opponentPoints) ? g.opponentPoints : DASH}` }, g.result)),
  );
}

function teamBlock(team, data, side) {
  const t = obj(team);
  const school = name(t.school);
  const overall = recordText(t.record);
  const conf = recordText(t.conferenceRecord);
  const sp = obj(t.sp);
  const talent = obj(t.talent);
  const of = fbsCount(data);
  const polls = [["AP", t.apRank], ["Coaches", t.coachesRank], ["CFP", t.cfpRank]].filter(([, rank]) => isNum(rank)).map(([poll, rank]) => pollBadge(rank, poll, { href: pollHref(poll, { team: school }), label: school }));
  const facts = [
    el("span", { class: "mx-fact" }, el("small", {}, "Record"), el("b", {}, overall || DASH), conf ? el("small", {}, ` (${conf} ${text(t.conference)})`) : null),
    el("span", { class: "mx-fact" }, el("small", {}, "SP+"), el("b", {}, fmtStat(sp.rating, "1f")), rankChip(sp.rank, isNum(sp.of) ? sp.of : of, { href: nationalHref("rating:sp", { team: school }), label: `${text(school)} SP+` }) || null),
    el("span", { class: "mx-fact" }, el("small", {}, "Talent"), el("b", {}, fmtStat(talent.talent, "0f")), rankChip(talent.rank, talent.of, { href: nationalHref("rating:talent", { team: school }), label: `${text(school)} talent` }) || null),
  ];
  return el(
    "div",
    { class: `mx-team mx-team--${side}${t.isUs === true ? " mx-team--us" : ""}` },
    el("div", { class: "mx-team__name" }, teamLogo(t, { size: 36 }), el("span", {}, school ? teamLink(school, school) : DASH, el("small", {}, [text(t.mascot), text(t.conference)].filter((s) => s !== DASH).join(" · ") || DASH))),
    polls.length ? el("div", { class: "mx-team__polls" }, polls) : null,
    el("div", { class: "mx-team__facts" }, facts),
    el("div", { class: "mx-team__form" }, el("small", {}, "Last five"), formLine(t.form)),
  );
}

function gameLine(data) {
  const g = obj(data.game);
  const away = obj(data.away);
  const home = obj(data.home);
  if (!Object.keys(g).length) return null;
  const aName = text(away.abbreviation || away.school);
  const hName = text(home.abbreviation || home.school);
  const scored = isNum(g.awayPoints) && isNum(g.homePoints);
  let line;
  if (g.status === "final" && scored) line = `Final: ${aName} ${g.awayPoints}, ${hName} ${g.homePoints}`;
  else if (g.status === "underway") line = scored ? `Under way: ${aName} ${g.awayPoints}, ${hName} ${g.homePoints}` : "Under way";
  else line = g.startTimeTbd === true ? `Kickoff time to be announced${g.kickoff ? `, ${fmtDateTime(g.kickoff).split(" ").slice(0, 3).join(" ")}` : ""}` : `Kickoff ${fmtDateTime(g.kickoff)}`;
  const where = [g.neutralSite === true ? "Neutral site" : null, typeof g.venue === "string" && g.venue ? g.venue : null].filter(Boolean).join(" · ");
  return el("p", { class: `mx-game mx-game--${text(g.status)}` }, el("b", {}, line), where ? el("small", {}, where) : null);
}

/** Who sits first: we do when we are in the game; between two other teams the away team, as the game is said. */
export function matchupOrder(data) {
  const d = obj(data);
  const away = obj(d.away);
  const home = obj(d.home);
  const neutralSite = obj(d.game).neutralSite === true;
  if (home.isUs === true) return { first: home, second: away, firstKey: "home", secondKey: "away", joiner: "vs", neutral: false };
  return { first: away, second: home, firstKey: "away", secondKey: "home", joiner: neutralSite ? "vs" : "at", neutral: away.isUs !== true };
}

function sideOf(value, of) {
  const s = obj(value);
  return { value: isNum(s.value) ? s.value : null, rank: s.rank, of: isNum(s.of) ? s.of : of };
}

function abbrOf(team) {
  return text(obj(team).abbreviation || name(obj(team).school));
}

/** The two-team table: the server's groups in order, each row's first team in our slot. */
function sideBySide(data, order) {
  const groups = [];
  for (const row of records(data.rows)) {
    const title = typeof row.group === "string" && row.group.trim() ? row.group.trim() : "This season";
    if (!groups.length || groups[groups.length - 1].title !== title) groups.push({ title, rows: [] });
    groups[groups.length - 1].rows.push({
      label: row.label,
      format: typeof row.format === "string" ? row.format : undefined,
      higherIsBetter: row.higherIsBetter,
      metric: row.metric,
      us: sideOf(row[order.firstKey], row.of),
      them: sideOf(row[order.secondKey], row.of),
    });
  }
  return twoTeamTable({
    groups,
    usAbbr: abbrOf(order.first),
    themAbbr: abbrOf(order.second),
    usTeam: name(order.first.school),
    themTeam: name(order.second.school),
    tug: true,
    labelHead: "This season",
    caption: `${text(name(order.first.school))} and ${text(name(order.second.school))}, side by side`,
    className: "mx-table",
  });
}

/** Between two other teams the bars wear those teams' colors (a readable one each), never ours and the week's opponent's. */
function neutralColors(order) {
  if (!order.neutral) return null;
  const usable = (team) => [obj(team).color, obj(team).altColor].find((c) => typeof c === "string" && !rejectReason(c, [])) || null;
  const first = usable(order.first);
  const second = usable(order.second);
  return { "--team-us": first || "var(--fog)", "--opp": second || "var(--fog)" };
}

function partErrors(data) {
  return Object.entries(obj(data.parts)).filter(([, p]) => obj(p).status === "error").map(([key, p]) => `${key}: ${text(obj(p).error)}`);
}

/** The sheet's content: both teams, the game when they meet this week, and the two-team table. */
export function matchupBody(envelope, { onRetry } = {}) {
  const data = obj(obj(envelope).data);
  const away = obj(data.away);
  const home = obj(data.home);
  const failed = partErrors(data);
  if (!name(away.school) || !name(home.school)) {
    return stateBlock({ kind: "error", lead: "This matchup could not be loaded.", detail: failed.length ? `${failed.join("; ")}.` : "The server sent no teams.", action: typeof onRetry === "function" ? { label: "Try now", onClick: onRetry } : null });
  }
  const rows = records(data.rows);
  const meta = obj(obj(envelope).meta);
  const order = matchupOrder(data);
  return el(
    "div",
    { class: `mx${order.neutral ? " mx--neutral" : ""}`, style: neutralColors(order) },
    el("div", { class: "mx-teams" }, teamBlock(order.first, data, "first"), el("span", { class: "mx-at", "aria-hidden": "true" }, order.joiner), teamBlock(order.second, data, "second")),
    gameLine(data),
    band({
      bare: true,
      title: "Side by side",
      collapsible: false,
      state: meta.stale === true ? { status: "stale", ageSeconds: ageSeconds(meta.fetched_at), message: "CFBD is not answering; these are the last numbers the app has." } : { status: "ready" },
      body: () => (rows.length ? sideBySide(data, order) : stateBlock({ lead: "No season stats for these teams yet.", detail: "They fill in once CFBD publishes this season's numbers." })),
    }),
    failed.length ? el("p", { class: "note" }, `Part of this sheet did not load (${failed.join("; ")}); the app asks again next time.`) : null,
  );
}

/** "Us vs them" when we are home or the site is neutral, "us at them" on the road, "away at home" between two other teams. */
export function sheetTitle(away, home, { homeIsUs = false, neutralSite = false } = {}) {
  if (homeIsUs) return `${home} vs ${away}`;
  return `${away} ${neutralSite ? "vs" : "at"} ${home}`;
}

function loading() {
  return el("div", { class: "mx" }, el("div", { class: "skel skel--block", style: { height: "150px", margin: 0 } }), statTableSkeleton(10, 4));
}

/** Open two teams side by side in a side sheet over the current page. */
export function openMatchupSheet({ away, home } = {}) {
  const a = name(away);
  const h = name(home);
  if (!a || !h) return null;
  const handle = openSheet({ title: sheetTitle(a, h, { homeIsUs: isUs(h) }), body: loading(), className: "mx-sheet" });
  let seq = 0;
  async function load() {
    const mine = ++seq;
    try {
      const envelope = await fetchPatient(`/api/matchup?away=${encodeURIComponent(a)}&home=${encodeURIComponent(h)}`, { current: () => mine === seq });
      if (mine !== seq) return;
      const data = obj(envelope.data);
      handle.setTitle(sheetTitle(a, h, { homeIsUs: obj(data.home).isUs === true, neutralSite: obj(data.game).neutralSite === true }));
      handle.setBody(matchupBody(envelope, { onRetry: load }));
    } catch (error) {
      if (mine !== seq) return;
      const missing = error?.status === 404;
      handle.setBody(stateBlock({ kind: "error", lead: missing ? "There is no such matchup." : "Could not load this matchup.", detail: error?.name === "AbortError" ? "The server did not answer in time." : `${text(error?.message || "The request failed")}.`, action: missing ? null : { label: "Try now", onClick: () => load() } }));
    }
  }
  load();
  return { ...handle, reload: load };
}

