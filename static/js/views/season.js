// The Season view (S1 to S5, S10, and our team-page summary): fetches
// /api/season/overview and renders it with the design-system components. Every band has
// loading, empty, stale, and error states driven by the server's per-part status.
//
// Phase 16 (stream SEASON):
//   createSeasonView({ onStatus, arg, params })  arg "polls:<AP|Coaches|CFP>" opens on that poll and brings
//       the Polls band into view (the poll list's Full page link). Phase 17 #2: params.band "standings" brings the
//       standings into view (the cover's conference record chip).
//   It runs on the shared poller (views/common.js): a refresh with the same data rebuilds nothing, a rebuild
//   keeps the page's and every table's scroll, and the reader's poll choice lives in the view's ui state, so
//   it survives every refresh. Values that changed since the last draw are marked (.is-changed).
//   Every national number is linked: its chip opens that stat's national list (the conference chip the conference
//   list, last season's chip that season's list). Poll ranks are poll badges. Schedule rows open the game: its
//   archive when the app watched it, else its program.
// Tables wave 3 (owner 2026-10-10; docs/03-DESIGN.md, Table sizes): every table on the page sizes itself by its own box,
//   every data point in its own column (the value, then its FBS rank from medium, the conference's at large). The
//   standings, the polls, the road ahead and the committee rankings sort, each keeping the reader's order in the view's
//   ui.sorts across refreshes; a poll's own order is its badge at large and medium and a plain number at small.

import { confLabel, usSchool } from "../identity.js";
import { pollMs } from "../prefs.js";
import { DASH, el, flashChanges, fmtNum, fmtStat, isNum, records, remember, snapshotKeys, text } from "../ui/dom.js";
import { nationalHref, pollName } from "../ui/national-link.js";
import { openGame, recordLine, scheduleList, scheduleSkeleton } from "../ui/schedule.js";
import { rankPath, trendRow } from "../ui/sparkline.js";
import { band, note, sectionChips, subhead } from "../ui/states.js";
import { pollBadge, rankChip, statTable, statTableSkeleton } from "../ui/stat-table.js";
import { conferenceColumn, logoLink, profileTable, profileTiles, standingsTable, teamAbbrLink } from "../ui/team-page.js";
import { advancedPaired, resumeBlock } from "../ui/depth2.js";
import { playoffBlock, playoffSummary } from "../ui/playoff.js";
import { lastSeasonBlock, roadAheadBlock } from "../ui/offday.js";
import { errorPanel, partState, poller, recordText } from "./common.js";
import { flow } from "../ui/flow.js";

export const NEXT_OPPONENT_KEY = "kickoff:next-opponent"; // the Ratings page marks this team's row

/** "polls:Coaches" -> "Coaches"; anything else -> null. Exported for the tests. */
export function pollFromArg(arg) {
  if (typeof arg !== "string") return null;
  const m = /^polls:(.+)$/i.exec(arg.trim());
  return m ? pollName(m[1]) : null;
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
/** The season's week now: the next game's week, else one past the last game played; the postseason counts as late. Exported
    for the tests. */
export function seasonWeek(data) {
  const games = Array.isArray(data?.schedule) ? data.schedule.filter((g) => g && typeof g === "object") : [];
  const next = games.find((g) => String(g.gameId) === String(data?.nextGameId ?? ""));
  if (next && (next.postseason || next.playoffRound)) return 99;
  if (next && isNum(next.week)) return next.week;
  const played = games.filter((g) => g.completed);
  if (played.some((g) => g.postseason || g.playoffRound)) return 99;
  const weeks = played.map((g) => g.week).filter(isNum);
  return weeks.length ? Math.max(...weeks) + 1 : 0;
}

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
export function createSeasonView({ onStatus, arg, params } = {}) {
  const ui = { poll: pollFromArg(arg), revealed: false, flow: null, chips: null, sorts: {} }; // sorts: each sortable table's order, kept across refreshes
  const focusBand = ui.poll !== null ? "#season-polls" : params?.band === "standings" ? "#season-standings" : null;

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
      body: () => advancedPaired(rows, { team, conferenceLabel: confLabel() }),
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
      body: () => playoffBlock(p, team, { sorts: ui.sorts }),
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
      body: () => lastSeasonBlock(rows, last.year, data.season, { team, conferenceLabel: confLabel() }),
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
      body: () => roadAheadBlock(rows, { logos: new Map(records(data.schedule).map((g) => [g.opponent?.school, g.opponent])), sorts: ui.sorts }),
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
    return band({
      id: "season-standings",
      title: `${confLabel()} standings`,
      collapsible: false,
      foldable: true,
      summary: rows.length ? `${rows.length} teams` : "",
      state: partState(data.parts?.records, rows.length > 0),
      emptyText: "Standings appear after the first conference game.",
      body: () => el("div", { class: "tight" }, standingsTable(rows, { conference: confLabel(), rowClass: rowMark(next), caption: `${confLabel()} standings`, sort: ui.sorts.standings, onSort: (sort) => { ui.sorts.standings = sort; } })),
    });
  }

  /** The latest AP rank on a team's path (the AP path column sorts by it); null when it is unranked now. */
  function lastRank(path) {
    const list = Array.isArray(path) ? path : [];
    const last = list.length ? list[list.length - 1] : null;
    return isNum(last) ? last : null;
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

  /**
   * One poll, sized by its own box (wave 3): the poll's own order (its badge at large and medium, a plain number at small,
   * decision 2), the team (its abbreviation at small, still its link), its conference in a column of its own (its short
   * name at medium, gone at small, decision 1), the week's movement and the points; the AP path and the first-place votes
   * at large (measured 2026-10-11: a 1080p screen's one-column band, about 460 px, holds the rank, the team, the
   * conference, the movement and the points). The points and the votes show only for a poll that has them (the
   * committee's has neither). Teams sort, by the poll's order first.
   */
  function pollTable(poll, next) {
    const short = pollName(poll.poll) || text(poll.poll);
    const rows = records(poll.ranks).map((row) => ({ ...row, rank: isNum(row.rank) ? row.rank : null, apPathRank: lastRank(row.apPath) })); // a damaged rank sorts last
    const has = (key) => rows.some((row) => isNum(row[key]));
    const columns = [
      { key: "rank", label: `${short} rank`, labelMid: short, labelShort: "#", order: true, render: (row) => pollBadge(row.rank, short, { label: row.school, showPoll: false }) },
      { key: "school", label: "Team", kind: "text", render: (row) => logoLink(row.school, row), renderShort: (row) => teamAbbrLink(row.school, row.abbreviation) },
      conferenceColumn(),
      { key: "change", label: "±", render: movementCell },
      { key: "apPath", label: "AP path", size: "large", sortKey: "apPathRank", render: (row) => rankPath(row.apPath, { label: `${text(row.school)} AP` }) || el("span", { class: "nr" }, DASH) },
      has("points") ? { key: "points", label: "Points", labelMid: "Pts" } : null,
      has("firstPlaceVotes") ? { key: "firstPlaceVotes", label: "First-place votes", size: "large" } : null,
    ].filter(Boolean).map((column) => ({ ...column, tieKey: "school" }));
    const id = `poll:${text(poll.poll)}`;
    return statTable({
      compact: true,
      sizes: true,
      columns,
      rows,
      sort: ui.sorts[id] || { key: "rank", dir: "ascending" },
      onSort: (sort) => {
        ui.sorts[id] = sort; // the reader's order survives a refresh, one per poll
      },
      rowClass: rowMark(next),
      caption: text(poll.name),
    });
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
          ? el("div", { class: "tight" }, el("p", { class: "poll-caption" }, `${text(poll.name)}, week ${text(poll.week)}`), pollTable(poll, next))
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
      if (r.sp.special && typeof r.sp.special === "object") add("spSpecial", "SP+ special teams", r.sp.special, "1f", { of: r.sp.special.of ?? r.sp.of, large: true }); // at large only: as much as there is
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
    // wave 3 (rule 3): the rating and its FBS rank in columns of their own. The FPI strength of schedule and of record have a
    // rank and no rating: at small, where the rank column is gone, the rank is their value (owner 2026-10-10)
    const value = (row) => (isNum(row.value) ? el("span", { "data-k": `rating:${row.key}` }, fmtStat(row.value, row.format)) : el("span", { class: "nr" }, DASH));
    const columns = [
      { key: "label", label: "Rating", kind: "text" },
      { key: "value", label: "Value", render: value, renderShort: (row) => (isNum(row.value) || !isNum(row.rank) ? value(row) : `#${row.rank}`) },
      { key: "rank", label: "FBS rank", labelMid: "FBS", kind: "rank", of: "of", size: "medium", link: (row) => nationalHref(row.metric, { team }) },
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
          statTable({ compact: true, sizes: true, sortable: false, columns, rows, rowClass: (row) => (row.large ? "st__min-large" : null), caption: "Ratings" }),
          anyError && !allError ? note(`One rating source failed: ${text(anyError.error)}.`) : null,
        ),
    });
  }

  /** The Season bands that span two columns on a wide page (owner pick 2026-10-07: the big tables). */
  const SEASON_WIDE = ["season-profile", "season-advanced", "season-last"]; // final pass: "This season and last" was clipped in one column on the iPad

  function render(envelope, container) {
    const data = envelope?.data && typeof envelope.data === "object" ? envelope.data : {};
    const team = school(data.team?.school) || usSchool();
    const next = nextOpponent(data);
    if (next) remember(NEXT_OPPONENT_KEY, next);
    const before = snapshotKeys(container);
    // Phase 17 #7, #28: one flowing page instead of three fixed columns (whose short middle left holes): the
    // bands pack into 1 to 4 columns by width, the stat profile and the advanced tables span two
    // The owner's order (2026-10-10). The College Football Playoff band (only once the committee's first ranking is out)
    // sits last until week 8, then first.
    const playoff = data.playoff ? el("div", { class: "season__wide flow-full" }, playoffBand(data, team)) : null;
    const playoffFirst = seasonWeek(data) >= 8;
    const grid = el(
      "div",
      { class: "page season season--flow" },
      playoffFirst ? playoff : null,
      scheduleBand(data, team),
      standingsBand(data, next?.school),
      pollsBand(data, next?.school),
      ratingsBand(data, team),
      resumeBand(data, team),
      profileBand(data, team),
      trendsBand(data),
      advancedBand(data, team),
      el("div", { class: "season__wide flow-full" }, roadAheadBand(data)),
      lastSeasonBand(data, team),
      playoffFirst ? null : playoff,
    );
    if (ui.flow) ui.flow.stop();
    if (ui.chips) ui.chips.stop();
    ui.chips = sectionChips(grid); // Phase 17 #5: the pinned section chips, above the page
    ui.chips.refresh();
    container.replaceChildren(ui.chips, grid);
    ui.flow = flow(grid, { wide: SEASON_WIDE });
    flashChanges(before, container);
    if (focusBand && !ui.revealed) {
      ui.revealed = true;
      setTimeout(() => jumpToBand(container.querySelector(focusBand)), 0); // after the router's scroll to the top
    }
  }

  const view = poller({
    url: "/api/season/overview",
    refreshMs: pollMs(),
    onStatus,
    render,
    renderError: (message, container, retry) => container.replaceChildren(errorPanel("Season", message, retry)),
    renderLoading: loadingLayout,
    loadingDetail: "The schedule, polls, standings and ratings",
  });
  view.ui = ui; // the tests read the poll choice
  const unmount = view.unmount;
  view.unmount = (...args) => {
    ui.flow?.stop(); // the layout's observers go with the page
    ui.flow = null;
    ui.chips?.stop();
    ui.chips = null;
    return unmount.apply(view, args);
  };
  return view;
}

export { rankChip };
