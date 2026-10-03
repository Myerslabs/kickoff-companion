// The Season view (S1 to S5, S10, and our team-page summary): fetches
// /api/season/overview and renders it with the design-system components. Every band has
// loading, empty, stale, and error states driven by the server's per-part status.
//
// Phase 16 (stream SEASON):
//   createSeasonView({ onStatus, arg, params })  arg "polls:<AP|Coaches|CFP>" opens on that poll and brings
//       the Polls band into view (the poll list's Full page link).
//   It runs on the shared poller (views/common.js): a refresh with the same data rebuilds nothing, a rebuild
//   keeps the page's and every table's scroll, and the reader's poll choice lives in the view's ui state, so
//   it survives every refresh. Values that changed since the last draw are marked (.is-changed).
//   Every national number is a linked unit: the value and its chip in one cell, the chip opening that
//   stat's national list (the conference chip the conference list, last season's chip that season's list). Poll
//   ranks are poll badges. Schedule rows open the game: its archive when the app watched it, else its program.

import { confLabel, usSchool } from "../identity.js";
import { pollMs } from "../prefs.js";
import { el, flashChanges, fmtNum, fmtStat, isNum, remember, snapshotKeys, text } from "../ui/dom.js";
import { nationalHref, pollHref, pollName } from "../ui/national-link.js";
import { openGame, recordLine, scheduleList, scheduleSkeleton } from "../ui/schedule.js";
import { rankPath, trendRow } from "../ui/sparkline.js";
import { band, jumpList, note, subhead } from "../ui/states.js";
import { pollBadge, rankChip, statTable, statTableSkeleton } from "../ui/stat-table.js";
import { formSquares, logoLink, profileTable, profileTiles } from "../ui/team-page.js";
import { advancedPaired, resumeBlock } from "../ui/depth2.js";
import { playoffBlock, playoffSummary } from "../ui/playoff.js";
import { lastSeasonBlock, roadAheadBlock } from "../ui/offday.js";
import { errorPanel, partState, poller, recordText } from "./common.js";

export const NEXT_OPPONENT_KEY = "kickoff:next-opponent"; // the Ratings page marks this team's row

/** "polls:Coaches" -> "Coaches"; anything else -> null. Exported for the tests. */
export function pollFromArg(arg) {
  if (typeof arg !== "string") return null;
  const m = /^polls:(.+)$/i.exec(arg.trim());
  return m ? pollName(m[1]) : null;
}

function records(value) {
  return Array.isArray(value) ? value.filter((row) => row && typeof row === "object") : [];
}

function school(value) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

/** The next opponent from the schedule, or null. */
export function nextOpponent(data) {
  const games = records(data?.schedule);
  const game = games.find((g) => g.gameId === data?.nextGameId && data?.nextGameId !== null && data?.nextGameId !== undefined) || null;
  const name = school(game?.opponent?.school);
  return name ? { school: name, gameId: game.gameId } : null;
}

/** Bring a band to the top of the page at once (unfolding it first), for a link that names it. An instant jump,
 *  not a smooth one: the poller's next draw keeps the page where it is, so a scroll still under way would stop. */
export function jumpToBand(section) {
  if (!section) return false;
  if ((section.dataset?.collapsed ?? section.getAttribute?.("data-collapsed")) === "true" && typeof section.setCollapsed === "function") section.setCollapsed(false);
  if (typeof window === "undefined" || typeof window.scrollTo !== "function" || typeof section.getBoundingClientRect !== "function") return false;
  const top = section.getBoundingClientRect().top + (isNum(window.scrollY) ? window.scrollY : 0) - 68; // under the top bar
  window.scrollTo(0, Math.max(0, Math.round(top)));
  return true;
}

function column(...children) {
  return el("div", { class: "season__col" }, children);
}

/** The middle column (app.css stacks its two-up spreads at 1100-1599 px). */
function guide(...children) {
  return el("div", { class: "season__guide" }, children);
}

/**
 * createSeasonView({ onStatus, arg }) -> { mount(container), refresh(), unmount() }
 * onStatus receives { kind, label } for the top-bar pill.
 */
export function createSeasonView({ onStatus, arg } = {}) {
  const ui = { poll: pollFromArg(arg), revealed: false };
  const focusPolls = ui.poll !== null;

  function loadingLayout() {
    const loading = (id, title, skeleton) => band({ id, title, collapsible: false, state: { status: "loading" }, skeleton });
    return el(
      "div",
      { class: "season" },
      column(loading("season-schedule", "Schedule", scheduleSkeleton), loading("season-polls", "Polls", () => statTableSkeleton(8, 3)), loading("season-trends", "Trends, week by week", () => statTableSkeleton(5, 3))),
      guide(loading("season-profile", "Stat profile", () => el("div", {}, el("div", { class: "skel-tiles" }, Array.from({ length: 4 }, () => el("div", { class: "skel skel--block" }))), statTableSkeleton(14, 3), statTableSkeleton(12, 3))), loading("season-last", "This season and last", () => statTableSkeleton(6, 4))),
      column(loading("season-standings", `${confLabel()} standings`, () => statTableSkeleton(8, 5)), loading("season-ratings", "Ratings", () => statTableSkeleton(5, 2)), loading("season-resume", "Résumé", () => statTableSkeleton(5, 2)), loading("season-advanced", "Advanced", () => statTableSkeleton(12, 3))),
      el("div", { class: "season__wide" }, loading("season-road", "Road ahead", () => statTableSkeleton(5, 8))),
    );
  }

  function scheduleBand(data, team) {
    const games = records(data.schedule);
    const record = data.record && typeof data.record === "object" ? data.record : {};
    return band({
      id: "season-schedule",
      title: "Schedule",
      collapsible: false,
      summary: `${recordText(record.overall)} · ${recordText(record.conference)} ${confLabel()}`,
      state: partState(data.parts?.schedule, games.length > 0),
      emptyText: "No games on the schedule yet.",
      body: () => el("div", {}, recordLine({ ...record, team }), scheduleList({ games, nextGameId: data.nextGameId ?? null, onSelect: openGame, context: true, spOf: data.ratings?.sp?.of })),
    });
  }

  function profileBand(data, team) {
    const profile = data.profile && typeof data.profile === "object" ? data.profile : { rows: [] };
    const rows = records(profile.rows);
    const has = rows.some((row) => isNum(row.value));
    const state = partState(data.parts?.stats, has);
    const ypg = rows.find((row) => row.key === "ypg") || {};
    return band({
      id: "season-profile",
      title: "Stat profile",
      collapsible: false,
      foldable: true,
      summary: isNum(profile.games) ? `${profile.games} game${profile.games === 1 ? "" : "s"}, rank of ${text(ypg.nationalOf)} FBS teams` : "",
      state,
      emptyText: "Season stats appear after the first game.",
      body: () =>
        el(
          "div",
          { class: "season__profile" },
          profileTiles(rows, { team }),
          el("div", { class: "spread spread--2" }, el("div", {}, subhead("Offense"), profileTable(rows, "offense", { team, conferenceLabel: confLabel() })), el("div", {}, subhead("Defense"), profileTable(rows, "defense", { team, conferenceLabel: confLabel() }))),
        ),
    });
  }

  /** G3-03: every advanced measure as one paired table (Offense | Defense), its own band in the right column. */
  function advancedBand(data, team) {
    const rows = records(data.advanced?.rows);
    const has = rows.some((row) => isNum(row.value));
    return band({
      id: "season-advanced",
      title: "Advanced",
      collapsible: false,
      foldable: true,
      summary: has ? "Offense and defense, national ranks" : "",
      state: partState(data.parts?.advanced, has),
      emptyText: "Advanced stats appear after the first game.",
      body: () => advancedPaired(rows, { team }),
    });
  }

  /** G3-03: the trends, their own band under Polls in the left column (design rule 14 keeps polls under the schedule). */
  function trendsBand(data) {
    const trends = data.trends && typeof data.trends === "object" ? data.trends : {};
    const has = ["points", "pointsAllowed", "yardsPerPlay", "turnoverMargin", "thirdDown"].some((key) => Array.isArray(trends[key]) && trends[key].some(isNum));
    return band({
      id: "season-trends",
      title: "Trends, week by week",
      collapsible: false,
      foldable: true,
      state: partState(data.parts?.trends, has),
      emptyText: "Trends appear after the first game.",
      body: () => trendsBody(data),
    });
  }

  function trendsBody(data) {
    const trends = data.trends && typeof data.trends === "object" ? data.trends : {};
    const missing = Array.isArray(data.parts?.trends?.missingWeeks) ? data.parts.trends.missingWeeks : [];
    // G3-12: W or L for each finished game, in schedule order (the trend arrays' order); none when they disagree
    const finished = records(data.schedule).filter((g) => g.completed === true);
    const results = finished.length > 0 && finished.length === (Array.isArray(trends.weeks) ? trends.weeks.length : -1) ? finished.map((g) => (g.result === "W" || g.result === "L" ? g.result : null)) : null;
    return el(
      "div",
      {},
      trendRow({ label: "Points scored", values: trends.points, key: "points", results }),
      trendRow({ label: "Points allowed", values: trends.pointsAllowed, them: true, key: "pointsAllowed", results }),
      trendRow({ label: "Yards per play", values: trends.yardsPerPlay, format: "1f", key: "yardsPerPlay", results }),
      trendRow({ label: "Turnover margin", values: trends.turnoverMargin, format: "+0f", key: "turnoverMargin", results }),
      trendRow({ label: "Third down", values: trends.thirdDown, format: "pct", key: "thirdDown", results }),
      results ? el("p", { class: "note trend__key" }, "Filled dot a win, hollow a loss; the dashed line is the season average.") : null,
      missing.length ? note(`Box scores for week${missing.length > 1 ? "s" : ""} ${missing.map(text).join(", ")} could not be loaded. The app keeps retrying.`) : null,
    );
  }

  /** Phase 13: expected wins, strength of schedule, the rest of the schedule, the poll path. */
  function resumeBand(data, team) {
    const r = data.resume && typeof data.resume === "object" ? data.resume : null;
    return band({
      id: "season-resume",
      title: "Résumé",
      collapsible: false,
      foldable: true,
      summary: r && isNum(r.expectedWins) ? `${fmtNum(r.expectedWins, 1)} expected wins, ${text(r.wins)} actual` : "",
      state: r ? { status: "ready" } : { status: "empty" },
      emptyText: "The résumé appears after the first game.",
      body: () => resumeBlock(r, team),
    });
  }

  /** Phase 15: from the committee's first ranking in November through the title game. */
  function playoffBand(data, team) {
    const p = data.playoff && typeof data.playoff === "object" ? data.playoff : null;
    if (!p) return null;
    return band({
      id: "season-playoff",
      title: "College Football Playoff",
      collapsible: false,
      foldable: true,
      summary: playoffSummary(p, team),
      state: { status: "ready" },
      body: () => playoffBlock(p, team),
    });
  }

  /** Phase 15: this season's profile beside last season's. */
  function lastSeasonBand(data, team) {
    const last = data.lastSeason && typeof data.lastSeason === "object" ? data.lastSeason : { rows: [] };
    const rows = records(last.rows);
    const better = rows.filter((r) => r.better === true).length;
    const worse = rows.filter((r) => r.better === false).length;
    return band({
      id: "season-last",
      title: "This season and last",
      collapsible: false,
      foldable: true,
      summary: rows.length ? `${better} better, ${worse} worse than ${text(last.year)}` : "",
      state: partState(data.parts?.lastStats, rows.length > 0),
      emptyText: "Last season's numbers appear once CFBD answers.",
      body: () => lastSeasonBlock(rows, last.year, data.season, { team }),
    });
  }

  /** Phase 15: every remaining opponent with its record, rank, SP+ and form. */
  function roadAheadBand(data) {
    const rows = records(data.roadAhead);
    return band({
      id: "season-road",
      title: "Road ahead",
      collapsible: false,
      foldable: true,
      summary: rows.length ? `${rows.length} games left` : "",
      state: partState(data.parts?.games, rows.length > 0),
      emptyText: "No games left on the schedule.",
      body: () => roadAheadBlock(rows, { logos: new Map(records(data.schedule).map((g) => [g.opponent?.school, g.opponent])) }),
    });
  }

  function rowMark(next) {
    return (row) => {
      if (row.isUs) return "is-us";
      if (next && (row.team === next || row.school === next)) return "is-next";
      return row.isFavorite === true ? "is-fav" : null;
    };
  }

  function standingsBand(data, next) {
    const rows = records(data.standings);
    const columns = [
      { key: "place", label: "#", dim: true },
      { key: "team", label: "Team", kind: "text", render: (row) => logoLink(row.team, row) },
      { key: "confText", label: confLabel() },
      { key: "overallText", label: "Overall" },
      { key: "apRank", label: "AP", render: (row) => (isNum(row.apRank) ? pollBadge(row.apRank, "AP", { href: pollHref("AP", { team: row.team }), label: row.team, showPoll: false }) : el("span", { class: "nr" }, "NR")) },
      { key: "form", label: "Last 5", render: (row) => formSquares(row.form) || "–" },
    ];
    return band({
      id: "season-standings",
      title: `${confLabel()} standings`,
      collapsible: false,
      foldable: true,
      summary: rows.length ? `${rows.length} teams` : "",
      state: partState(data.parts?.records, rows.length > 0),
      emptyText: "Standings appear after the first conference game.",
      body: () => el("div", { class: "tight" }, statTable({ compact: true, sortable: false, columns, rows: rows.map((row) => ({ ...row, confText: recordText(row.conference), overallText: recordText(row.overall) })), rowClass: rowMark(next), caption: `${confLabel()} standings` })),
    });
  }

  /** GX-06: '+3' up, '-2' down, 'new' to the poll, '0' unchanged; a dash with no week before. */
  function movementCell(row) {
    const label = typeof row.movement === "string" ? row.movement : null;
    if (label === "new") return el("span", { class: "mv mv--new" }, "new");
    if (!isNum(row.change) || !label) return el("span", { class: "mv" }, "–");
    const cls = row.change > 0 ? "mv--up" : row.change < 0 ? "mv--down" : "";
    const shown = row.change > 0 ? `+${row.change}` : row.change < 0 ? `−${Math.abs(row.change)}` : "0";
    return el("span", { class: `mv ${cls}`.trim(), title: isNum(row.previousRank) ? `No. ${row.previousRank} the week before` : null }, shown);
  }

  function pollsBand(data, next) {
    const polls = records(data.polls);
    if (!polls.some((poll) => poll.poll === ui.poll)) ui.poll = polls[0]?.poll ?? null;
    const body = el("div", {});
    const buttons = polls.map((poll) => el("button", { type: "button", "aria-pressed": poll.poll === ui.poll ? "true" : "false", dataset: { poll: text(poll.poll) } }, `${text(poll.poll)}${isNum(poll.usRank) ? ` #${poll.usRank}` : ""}`));
    const draw = () => {
      const poll = polls.find((p) => p.poll === ui.poll);
      body.replaceChildren(
        poll
          ? el("div", { class: "tight" }, el("p", { class: "poll-caption" }, `${text(poll.name)}, week ${text(poll.week)}`), statTable({
              compact: true,
              sortable: false,
              columns: [
                { key: "rank", label: "#", dim: true },
                { key: "school", label: "Team", kind: "text", sub: "conference", render: (row) => logoLink(row.school, row) },
                { key: "change", label: "±", render: movementCell },
                { key: "apPath", label: "AP path", render: (row) => rankPath(row.apPath, { label: `${text(row.school)} AP` }) || el("span", { class: "nr" }, "–") },
                { key: "points", label: "Pts" },
              ],
              rows: records(poll.ranks),
              rowClass: rowMark(next),
              caption: text(poll.name),
            }))
          : note("No poll yet."),
      );
    };
    buttons.forEach((button, index) =>
      button.addEventListener("click", () => {
        ui.poll = polls[index]?.poll ?? null;
        buttons.forEach((b, i) => b.setAttribute("aria-pressed", i === index ? "true" : "false"));
        draw();
      }),
    );
    if (polls.length) draw();
    return band({
      id: "season-polls",
      title: "Polls",
      collapsible: false,
      foldable: true,
      tools: polls.length > 1 ? el("div", { class: "seg", role: "group", "aria-label": "Poll" }, buttons) : null,
      state: partState(data.parts?.rankings, polls.length > 0),
      emptyText: "Polls appear after the first poll of the season.",
      body: () => body,
    });
  }

  function ratingsBand(data, team) {
    const r = data.ratings && typeof data.ratings === "object" ? data.ratings : {};
    const rows = [];
    const add = (key, label, block, format, extra = {}) => rows.push({ key, label, value: block?.rating ?? null, format, rank: block?.rank, of: block?.of ?? r.sp?.of, metric: block?.metric, ...extra });
    if (r.sp) {
      add("sp", "SP+ overall", r.sp, "1f");
      add("spOffense", "SP+ offense", r.sp.offense, "1f", { of: r.sp.offense?.of ?? r.sp.of });
      add("spDefense", "SP+ defense", r.sp.defense, "1f", { of: r.sp.defense?.of ?? r.sp.of });
    }
    if (r.elo) add("elo", "Elo", r.elo, "0f");
    if (r.fpi) {
      add("fpi", "FPI", r.fpi, "1f");
      rows.push({ key: "fpiSos", label: "Strength of schedule", value: null, rank: r.fpi.strengthOfScheduleRank, of: r.fpi.strengthOfScheduleOf ?? r.fpi.of, metric: r.fpi.strengthOfScheduleMetric });
      rows.push({ key: "fpiSor", label: "Strength of record", value: null, rank: r.fpi.strengthOfRecordRank, of: r.fpi.strengthOfRecordOf ?? r.fpi.of, metric: r.fpi.strengthOfRecordMetric });
    }
    const parts = data.parts || {};
    const anyError = ["sp", "elo", "fpi"].map((k) => parts[k]).find((p) => p && p.status === "error");
    const allError = ["sp", "elo", "fpi"].every((k) => parts[k]?.status === "error");
    const state = allError ? partState(anyError, false) : rows.length ? partState(["sp", "elo", "fpi"].map((k) => parts[k]).find((p) => p?.status === "stale") || parts.sp, true) : { status: "empty" };
    const columns = [
      { key: "label", label: "Rating", kind: "text" },
      {
        key: "value",
        label: "Value",
        render: (row) => (isNum(row.value) ? el("span", { "data-k": `rating:${row.key}` }, fmtStat(row.value, row.format)) : el("span", { class: "nr" }, "")),
        rank: { key: "rank", of: "of", link: (row) => nationalHref(row.metric, { team }), placeholder: true },
      },
    ];
    return band({
      id: "season-ratings",
      title: "Ratings",
      collapsible: false,
      tools: el("a", { class: "btn btn--quiet", href: "#ratings" }, "Every team"),
      state,
      emptyText: "Ratings appear once SP+, Elo, or FPI publish for the season.",
      body: () =>
        el(
          "div",
          {},
          statTable({ compact: true, sortable: false, columns, rows, caption: "Ratings" }),
          anyError && !allError ? note(`One rating source failed: ${text(anyError.error)}.`) : null,
        ),
    });
  }

  function render(envelope, container) {
    const data = envelope?.data && typeof envelope.data === "object" ? envelope.data : {};
    const team = school(data.team?.school) || usSchool();
    const next = nextOpponent(data);
    if (next) remember(NEXT_OPPONENT_KEY, next);
    const before = snapshotKeys(container);
    const grid = el(
      "div",
      { class: "season" },
      el("div", { class: "season__top" }),
      column(scheduleBand(data, team), pollsBand(data, next?.school), trendsBand(data)),
      guide(profileBand(data, team), lastSeasonBand(data, team)),
      column(standingsBand(data, next?.school), ratingsBand(data, team), resumeBand(data, team), advancedBand(data, team)),
      el("div", { class: "season__wide" }, roadAheadBand(data)),
      data.playoff ? el("div", { class: "season__wide" }, playoffBand(data, team)) : null,
    );
    grid.querySelector(".season__top").append(jumpList(grid)); // UX-11: a page row, never on a band head
    container.replaceChildren(grid);
    flashChanges(before, container);
    if (focusPolls && !ui.revealed) {
      ui.revealed = true;
      setTimeout(() => jumpToBand(container.querySelector("#season-polls")), 0); // after the router's scroll to the top
    }
  }

  const view = poller({
    url: "/api/season/overview",
    refreshMs: pollMs(),
    onStatus,
    render,
    renderError: (message, container, retry) => container.replaceChildren(errorPanel("Season", message, retry)),
    renderLoading: loadingLayout,
  });
  view.ui = ui; // the tests read the poll choice
  return view;
}

export { rankChip };
