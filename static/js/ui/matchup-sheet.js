// The matchup sheet (UX-12, Phase 16 NV): any two FBS teams side by side in a side sheet, from
// GET /api/matchup?away=&home= (the cached all-FBS answers only; no per-school calls). Each team's record,
// polls, SP+, talent and last five results, the live or final score when the two meet this week, then the
// two-team table: one row per stat, value and rank chip in one cell, a divider before the second team, the
// better number bright. Every chip links to its national list with that team's row marked.
//
// API (later streams wire it into Scores rows and Newspaper slate cards):
//   openMatchupSheet({ away, home }) -> the openSheet handle plus reload(), or null without two names.
//   matchupBody(envelope, { onRetry })  the sheet's content, for the tests and the styleguide.

import { ageSeconds, fetchJson } from "../views/common.js";
import { DASH, el, fmtDateTime, fmtStat, isNum, teamLink, teamLogo, text } from "./dom.js";
import { nationalHref, pollHref } from "./national-link.js";
import { openSheet } from "./remote.js";
import { band, stateBlock } from "./states.js";
import { pollBadge, rankChip, rankChipPlaceholder, statTableSkeleton } from "./stat-table.js";

const FETCH_MS = 20000;
const NAME_MAX = 60;

function obj(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

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
    el("span", { class: "mx-fact" }, el("small", {}, "SP+"), el("b", {}, fmtStat(sp.rating, "1f")), rankChip(sp.rank, of, { href: nationalHref("rating:sp", { team: school }), label: `${text(school)} SP+` }) || null),
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

function better(row, a, b) {
  if (!isNum(a) || !isNum(b) || a === b) return [null, null];
  const awayBetter = row.higherIsBetter === false ? a < b : a > b;
  return awayBetter ? ["lead", "trail"] : ["trail", "lead"];
}

function valueCell(row, side, team, extra) {
  const v = obj(row[side]);
  const href = nationalHref(row.metric, { team });
  const chip = rankChip(v.rank, row.of, { href, label: `${text(team)} ${text(row.label)}` });
  return el("td", { class: `num${extra ? ` ${extra}` : ""}` }, fmtStat(v.value, typeof row.format === "string" ? row.format : "2f"), chip || rankChipPlaceholder());
}

function statTable2(data) {
  const away = obj(data.away);
  const home = obj(data.home);
  const rows = (Array.isArray(data.rows) ? data.rows : []).filter((r) => r && typeof r === "object" && !Array.isArray(r));
  const groups = [];
  for (const row of rows) {
    const group = typeof row.group === "string" && row.group ? row.group : "Stats";
    if (!groups.length || groups[groups.length - 1][0] !== group) groups.push([group, []]);
    groups[groups.length - 1][1].push(row);
  }
  const aSchool = name(away.school);
  const hSchool = name(home.school);
  return el(
    "div",
    { class: "stat-table-wrap" },
    el(
      "table",
      { class: "stat-table stat-table--compact tt mx-table" },
      el("caption", { class: "sr-only" }, `${text(aSchool)} and ${text(hSchool)}, side by side`),
      el("thead", {}, el("tr", {}, el("th", { class: "txt", scope: "col" }, "Statistic"), el("th", { class: "us", scope: "col" }, text(away.abbreviation || aSchool)), el("th", { class: "them tt__them", scope: "col" }, text(home.abbreviation || hSchool)))),
      groups.map(([group, list]) =>
        el(
          "tbody",
          {},
          el("tr", { class: "is-parent mx-group" }, el("td", { class: "txt", colspan: "3" }, group)),
          list.map((row) => {
            const [a, h] = better(row, obj(row.away).value, obj(row.home).value);
            return el("tr", {}, el("td", { class: "txt" }, text(row.label)), valueCell(row, "away", aSchool, a), valueCell(row, "home", hSchool, ["tt__them", h].filter(Boolean).join(" ")));
          }),
        ),
      ),
    ),
  );
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
  const rows = Array.isArray(data.rows) ? data.rows : [];
  const meta = obj(obj(envelope).meta);
  return el(
    "div",
    { class: "mx" },
    el("div", { class: "mx-teams" }, teamBlock(away, data, "away"), el("span", { class: "mx-at", "aria-hidden": "true" }, data.game && obj(data.game).neutralSite === true ? "vs" : "at"), teamBlock(home, data, "home")),
    gameLine(data),
    band({
      bare: true,
      title: "Side by side",
      collapsible: false,
      state: meta.stale === true ? { status: "stale", ageSeconds: ageSeconds(meta.fetched_at), message: "CFBD is not answering; these are the last numbers the app has." } : { status: "ready" },
      body: () => (rows.length ? statTable2(data) : stateBlock({ lead: "No season stats for these teams yet.", detail: "They fill in once CFBD publishes this season's numbers." })),
    }),
    failed.length ? el("p", { class: "note" }, `Part of this sheet did not load (${failed.join("; ")}); the app asks again next time.`) : null,
  );
}

function loading() {
  return el("div", { class: "mx" }, el("div", { class: "skel skel--block", style: { height: "150px", margin: 0 } }), statTableSkeleton(10, 3));
}

/** Open two teams side by side in a side sheet over the current page. */
export function openMatchupSheet({ away, home } = {}) {
  const a = name(away);
  const h = name(home);
  if (!a || !h) return null;
  const handle = openSheet({ title: `${a} at ${h}`, body: loading(), className: "mx-sheet" });
  let seq = 0;
  async function load() {
    const mine = ++seq;
    const controller = typeof AbortController === "function" ? new AbortController() : null;
    const timer = setTimeout(() => controller?.abort(), FETCH_MS);
    try {
      const envelope = await fetchJson(`/api/matchup?away=${encodeURIComponent(a)}&home=${encodeURIComponent(h)}`, controller?.signal);
      if (mine !== seq) return;
      const data = obj(envelope.data);
      if (obj(data.game).neutralSite === true) handle.setTitle(`${a} vs ${h}`);
      handle.setBody(matchupBody(envelope, { onRetry: load }));
    } catch (error) {
      if (mine !== seq) return;
      const missing = error?.status === 404;
      handle.setBody(stateBlock({ kind: "error", lead: missing ? "There is no such matchup." : "Could not load this matchup.", detail: error?.name === "AbortError" ? "The server did not answer in 20 s." : `${text(error?.message || "The request failed")}.`, action: missing ? null : { label: "Try now", onClick: () => load() } }));
    } finally {
      clearTimeout(timer);
    }
  }
  load();
  return { ...handle, reload: load };
}

