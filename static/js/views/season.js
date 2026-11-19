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
// Tables wave 3 (owner 2026-10-10; the design rules, Table sizes): every table on the page sizes itself by its own box,
//   every data point in its own column (the value, then its FBS rank from medium, the conference's at large). The
//   standings, the polls, the road ahead and the committee rankings sort, each keeping the reader's order in the view's
//   ui.sorts across refreshes; a poll's own order is its badge at large and medium and a plain number at small.
// My Team (wave 3 of the one-column page, owner 2026-11-01: "my team and season are the same in my eyes"; his inventory picks
//   for the Season page and the team page were one list): one scroll, the window and the rail, the season's bands, then at
//   the bottom in the inventory's order the Availability report, Talent and recruiting, Tendencies, Getting there, What we
//   need, the roster's five bands, the class and Where they're from, Staff, Play value and usage, School facts, Players to
//   know and the Circle of Blame's four. The late bands load their own answers after the page is up (lateBands: one fetch a
//   source, a host a band, filled in place). #team=<school> is this page for any FBS team (the team page's tabs are gone):
//   its own-only bands (the rail, Tendencies, Getting there, Players to know, the blame) stay off, and Watch it live sits
//   under its window while its next game can be followed. The polls left for the Newspaper (ui/polls-band.js).
// Season with My Teams (the layout pass, board 9, owner 2026-10-22: "I want my teams, and season to combine. Have a selection
//   window at the top, start with the primary and allow to switch between teams similar to the pre-game-program weeks"):
//   params.team names the team picked (#season?team=Texas%20A%26M; none is the home team, every visit). Since batch 3 (owner
//   2026-11-19) the window on top shows one team with Change team (the switch on this device), no arrows or chips, and
//   carries what My Teams' table said: the record, AP, SP+, Elo, FPI, the last game and the next. The page under it is the
//   picked team's season in the same order, the bands side by side ending flush (Schedule | Standings 2:1, Polls | Ratings
//   over Résumé 1:2, the rest across the page); the College Football Playoff band only while the team is in the AP Top 25;
//   the trends one column a game, headed by the opponent in its colors.

import { confLabel as ourConfLabel, usSchool } from "../identity.js";
import { bookUrl, pastHref, pastMarks, pastNote } from "../ui/past.js"; // rollover R2: a past season read from what was kept
import { railHost, stopMarks } from "../ui/rail.js"; // the season as one line (owner 2026-10-30): the Season is the stop that leads Monday to Wednesday; Wave 4: each game's three stops on its row
import { landBand } from "../ui/land-band.js"; // the Season stop (Wave 4): our land on the Imperialism Map
import { rememberedView, rememberView, viewSwitch } from "../ui/box-switch.js"; // the Season stop (Wave 4): The numbers box
import { DASH, el, flashChanges, fmtNum, fmtStat, isNum, ordinal, records, remember, snapshotKeys, teamLogo, text } from "../ui/dom.js";
import { addSideChips, cover, ratingChip } from "../ui/cover.js"; // the cover on one team (owner 2026-11-07): My Team opens with our cover
import { teamStaff } from "../ui/game-staff.js";
import { teamChipColors } from "../ui/colors.js";
import { viewing } from "../viewing.js"; // batch 3: whether the team picked is the one this device is switched to
import { openTeamSwitch } from "../ui/team-switch.js"; // batch 3: My Team's Change team opens the same sheet as the top bar's
import { nationalHref, pollName } from "../ui/national-link.js";
import { openGame, recordLine, scheduleList, scheduleSkeleton } from "../ui/schedule.js";
import { marginStrip } from "../ui/margin-strip.js"; // ENH-19 chart 3: the season's shape between the record and the games
import { trendGrid } from "../ui/sparkline.js";
import { band, note, sectionChips, subhead } from "../ui/states.js";
import { rankChip, statTable, statTableSkeleton } from "../ui/stat-table.js";
import { profileTable, profileTiles, standingsTable } from "../ui/team-page.js";
import { raceRanges } from "../ui/race-ranges.js";
import { advancedPaired, resumeBlock } from "../ui/depth2.js";
import { playoffBlock, playoffSummary } from "../ui/playoff.js";
import { lastSeasonBlock, roadAheadBlock } from "../ui/offday.js";
import { errorPanel, fetchJson, partState, poller, recordText } from "./common.js";
import { flow } from "../ui/flow.js";
// wave 3 of the one-column page (2026-11-01): the bands that joined My Team from the other pages
import { raceBand } from "../ui/race.js";
import { followButton } from "../ui/follow.js";
import { injurySheetBand } from "./injuries.js";
import { rosterBands } from "./roster.js";
import { recruitingBands } from "./recruiting.js";
import { teamExtraBands } from "./team.js";
import { coverConditions, lineupBand, tendenciesBand, tripBand } from "./program.js";
import { starsPart } from "./preseason.js";
import { createBlameView } from "./blame.js";
import { pollsBand } from "../ui/polls-band.js"; // the season in review (Wave 7): the polls band any page draws
import { playerBands } from "../ui/season-players.js"; // the season in review (Wave 7): every starter, every player's stats
import { printButton } from "../ui/print.js"; // the season in review (Wave 7): the browser's own print
import { reviewBody } from "./review.js"; // the season in review (Wave 7): the season in a few lines
import { openPlayer } from "./player.js";

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

const FOCUS = { standings: "#season-standings", blame: "#blame-wheel" }; // ?band=
const TAB_FOCUS = { schedule: "#season-schedule", roster: "#roster-table", coaches: "#team-staff", history: "#team-facts" }; // the old team page's ?tab=

/**
 * Bands that load their own answer after the page is up (wave 3 of the one-column page): one fetch of `url`, one host a band,
 * each host a loading band with the band's own id and title until the answer is in (so the chips row and the menu's flyouts
 * know it from the start), then filled in place; build(data) gives { <key>: node | null }, a null host leaves. Exported for
 * the tests.
 */
export function lateBands(url, specs, build, { quiet = false } = {}) {
  const hosts = specs.map(([key, title, id]) => el("div", { class: "late", dataset: { late: key } }, band({ id, title, collapsible: false, foldable: true, state: { status: "loading" } }))); // foldable: every band on the program can be minimised
  fetchJson(url)
    .then((envelope) => {
      const built = build(envelope?.data && typeof envelope.data === "object" ? envelope.data : {}) || {};
      specs.forEach(([key], i) => {
        const node = built[key];
        if (node) {
          hosts[i].replaceChildren(node);
          // Wave 7 (2026-11-15): a late band's tables are built off the page; measured as they land, so a wide one steps
          // down (or scrolls at its floor) instead of waiting for a frame or a resize that may not come
          for (const wrap of hosts[i].querySelectorAll(".stat-table-wrap")) if (typeof wrap.measure === "function") wrap.measure();
        } else hosts[i].remove();
      });
    })
    .catch((error) => {
      if (quiet) {
        hosts.forEach((host) => host.remove()); // nothing to show (the game was never archived): no band at all
        return;
      }
      specs.forEach(([, title, id], i) => hosts[i].replaceChildren(band({ id, title, collapsible: false, foldable: true, state: { status: "error", message: `${text(error?.message || error)}. The band tries again with the next refresh.` } })));
    });
  return hosts;
}

/** Phase 13: expected wins, strength of schedule, the rest of the schedule, the poll path. */
export function resumeBand(data, team, { id = "season-resume" } = {}) {
  const r = data.resume && typeof data.resume === "object" ? data.resume : null;
  return band({
    id,
    title: "Résumé",
    collapsible: false,
    foldable: true,
    summary: r && isNum(r.expectedWins) ? `${fmtNum(r.expectedWins, 1)} expected wins, ${text(r.wins)} actual` : "",
    state: r ? { status: "ready" } : { status: "empty" },
    emptyText: "The résumé appears after the first game.",
    body: () => resumeBlock(r, team),
  });
}

/** Phase 15: every remaining opponent with its record, rank, SP+ and form. */
export function roadAheadBand(data, { id = "season-road", sorts = {} } = {}) {
  const rows = records(data.roadAhead);
  return band({
    id,
    title: "Road ahead",
    collapsible: false,
    foldable: true,
    summary: rows.length ? `${rows.length} games left` : "",
    state: partState(data.parts?.games, rows.length > 0),
    emptyText: "No games left on the schedule.",
    body: () => roadAheadBlock(rows, { logos: new Map(records(data.schedule).map((g) => [g.opponent?.school, g.opponent])), sorts }),
  });
}

export function ratingsBand(data, team, { id = "season-ratings" } = {}) {
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
    id,
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

export function jumpToBand(section) {
  if (!section) return false;
  if ((section.dataset?.collapsed ?? section.getAttribute?.("data-collapsed")) === "true" && typeof section.setCollapsed === "function") section.setCollapsed(false);
  if (typeof window === "undefined" || typeof window.scrollTo !== "function" || typeof section.getBoundingClientRect !== "function") return false;
  const top = section.getBoundingClientRect().top + (isNum(window.scrollY) ? window.scrollY : 0) - 68; // under the top bar
  window.scrollTo(0, Math.max(0, Math.round(top)));
  return true;
}

/** The address of a team's Season page: the home team's is plain #season (board 9). Exported for the tests. */
export function seasonHref(team, home = usSchool()) {
  const name = school(team);
  return !name || name === home ? "#season" : `#season?team=${encodeURIComponent(name)}`;
}

/** The followed teams in the window's order and where the picked one sits: { teams, at, prev, next }. Exported for the tests. */
export function pickOrder(picker, team) {
  const teams = records(picker?.teams).filter((t) => school(t.school));
  const at = teams.findIndex((t) => t.school === team);
  return { teams, at, prev: at > 0 ? teams[at - 1] : null, next: at >= 0 && at < teams.length - 1 ? teams[at + 1] : null };
}

/** Whether the team picked is in the AP Top 25 this week (the playoff band shows only then, owner 2026-10-22). Exported for the tests. */
export function inTopTwentyFive(data) {
  const rank = data?.record?.apRank;
  return isNum(rank) && rank >= 1 && rank <= 25;
}

/** The finished games in the trends' order, matched by game id (board 9): the schedule rows that head the columns. */
export function trendGames(data) {
  const trends = data?.trends && typeof data.trends === "object" ? data.trends : {};
  const finished = records(data?.schedule).filter((g) => g.completed === true);
  const ids = Array.isArray(trends.gameIds) ? trends.gameIds : null;
  if (ids) {
    const byId = new Map(finished.map((g) => [String(g.gameId), g]));
    return ids.map((id, i) => byId.get(String(id)) || { week: Array.isArray(trends.weeks) ? trends.weeks[i] : null, opponent: { school: Array.isArray(trends.opponents) ? trends.opponents[i] : null } });
  }
  const weeks = Array.isArray(trends.weeks) ? trends.weeks : [];
  if (finished.length === weeks.length) return finished;
  return weeks.map((week, i) => ({ week, opponent: { school: Array.isArray(trends.opponents) ? trends.opponents[i] : null } }));
}

/**
 * createSeasonView({ onStatus, arg }) -> { mount(container), refresh(), unmount() }
 * onStatus receives { kind, label } for the top-bar pill.
 */
export function createSeasonView({ onStatus, arg, params, review = false, past = null } = {}) {
  // rollover R2 (owner 2026-11-15, "The book and its games"): #review=2026 is that season's review read from what was kept when
  // the app moved on (/api/seasons/<year>/book/<part>), its schedule leading to each game's kept stops; never a CFBD call
  const pastSeason = review && Number.isInteger(past) ? past : null;
  const ui = { poll: pollFromArg(arg), revealed: false, flow: null, chips: null, sorts: {}, conf: null, roster: { position: "", sort: null }, recruiting: { year: null, sorts: {} }, team: { sorts: {} }, blame: null }; // sorts: each sortable table's order, kept across refreshes; roster, recruiting, team: the late bands' own
  const focusBand = FOCUS[params?.band] || TAB_FOCUS[params?.tab] || null; // ?band=standings (a cover's chip), ?band=blame (the old #blame), ?tab=roster (the old team page's tabs)
  const asked = school(params?.team);
  const picked = asked && asked !== usSchool() ? asked : null; // board 9: another followed team; none, or our own school (#team=<ours>), is the home team
  const boxView = typeof params?.view === "string" ? params.view : null; // the Season stop (Wave 4): ?view= opens The numbers on that view for one visit
  const confLabel = () => ui.conf || ourConfLabel(); // the team picked's conference, once its answer is here

  function loadingLayout() {
    const loading = (id, title, skeleton) => band({ id, title, collapsible: false, state: { status: "loading" }, skeleton });
    return el(
      "div",
      { class: "page season season--flow season--loading" },
      el("section", { class: "season-pick season-pick--loading", "aria-label": "Your team" }, el("div", { class: "skel skel--bar" }), el("div", { class: "skel skel--block" })),
      loading("season-schedule", "Schedule", scheduleSkeleton),
      loading("season-standings", `${picked ? "Conference" : confLabel()} standings`, () => statTableSkeleton(8, 5)),
      loading("season-ratings", "Ratings", () => statTableSkeleton(5, 2)),
      loading("season-resume", "Résumé", () => statTableSkeleton(5, 2)),
      loading("season-profile", "Stat profile", () => el("div", {}, el("div", { class: "skel-tiles" }, Array.from({ length: 4 }, () => el("div", { class: "skel skel--block" }))), statTableSkeleton(14, 3))),
      loading("season-trends", "Trends, week by week", () => statTableSkeleton(5, 3)),
    );
  }

  /** The selection window (board 9) as the cover on one team (owner 2026-11-07, "Lets try a my team cover"), one team
   *  since batch 3 with its Change team (ui/cover.js, one: true): the logo, the name, the record, AP, SP+, Elo, FPI and
   *  talent as chips, the last five, alone and centered since 2026-11-20 (the next game's card and the Last line went to the
   *  Pre-Game Program's side); the rail across the top on our own season. The school's facts, the staff, the line, the venue
   *  and the weather arrive from the program's answer a moment later (fillCover), the cover drawn at once from the season's. */
  function pickWindow(data, team) {
    const info = data.team && typeof data.team === "object" ? data.team : {};
    const record = data.record && typeof data.record === "object" ? data.record : {};
    const r = data.ratings && typeof data.ratings === "object" ? data.ratings : {};
    // batch 3 (owner 2026-11-19: "Let's just have one team listed, and a change team for the switch"): ours needs no word; the
    // team this device is switched to says so; another team opened by name (a flyout's Full page) is only not ours
    const roleWord = picked ? (viewing() === team ? "Changed on this device" : "Not your team") : null;
    const played = records(data.schedule).filter((g) => g.completed === true);
    const form = played.slice(-5).map((g) => ({ gameId: g.gameId, week: g.week, result: g.result, points: g.usPoints, opponentPoints: g.themPoints, opponent: school(g.opponent), homeAway: g.homeAway }));
    const us = { ...info, school: team, record: record.overall, conferenceRecord: record.conference, apRank: record.apRank, sp: r.sp, ratings: { elo: r.elo, fpi: r.fpi, talent: r.talent }, form };
    const { background } = teamChipColors(info);
    const kicker = [picked ? null : "My Team", typeof info.conference === "string" && info.conference ? info.conference : null, roleWord].filter(Boolean).join(" · ");
    const coverEl = cover({
      one: true,
      us,
      kicker,
      label: `${team}: the season right now`,
      rail: picked ? null : railHost({ kind: "season" }), // the rail on our own season (another team's page keeps its own window)
      // owner 2026-11-20 (of the next game's card and the Last line beside our cover: "remove the vanderbuilt part and just
      // show the gators logo at the top for my team"; his pick, Florida alone and centered): no middle, the Pre-Game Program
      // has the next game
      extra: el("div", { class: "season-pick__teams" }, el("button", { class: "btn btn--quiet season-pick__change", type: "button", onclick: () => openTeamSwitch() }, "Change team")), // the same sheet as the top bar's Change team
    });
    coverEl.classList.add("season-cover");
    fillCover(coverEl, data, team);
    return el(
      "section",
      { class: "season-pick flow-full", "aria-label": "Your team", style: { "--pick": background } },
      el("div", { class: "season-pick__row" }, coverEl),
    );
  }

  /** The cover's second coat, from the program's answer: the school's facts and scheme under our side, the staff, the
   *  weather in the foot (the next-game card it once filled left My Team on 2026-11-20). A program that does not load leaves the cover as the season drew it. */
  async function fillCover(coverEl, data, team) {
    const id = data.nextGameId;
    const url = !picked ? "/api/program/next" : isNum(id) || /^\d+$/.test(String(id ?? "")) ? `/api/program/${encodeURIComponent(String(id))}?team=${encodeURIComponent(team)}` : null;
    if (!url) return;
    let program = null;
    try {
      program = (await fetchJson(url))?.data || null;
    } catch (error) {
      console.warn("My Team: the program behind the cover did not load; the cover keeps what the season knows.", error?.message || error);
      return;
    }
    if (!program || typeof program !== "object" || !coverEl.isConnected) return;
    try {
      enrichCover(coverEl, program, team);
    } catch (error) {
      console.error("My Team: the cover's second coat could not be drawn.", error);
    }
  }

  function enrichCover(coverEl, program, team) {
    const side = coverEl.querySelector(".cover__side--us");
    const f = program.facts && typeof program.facts === "object" && program.facts.us && typeof program.facts.us === "object" ? program.facts.us : {};
    if (side && !side.querySelector(".cover__facts")) {
      const stadium = [typeof f.stadium === "string" && f.stadium.trim() ? f.stadium.trim() : null, isNum(f.stadiumOpened) ? `opened ${f.stadiumOpened}` : null].filter(Boolean).join(", ");
      const bits = [isNum(f.founded) ? `Founded ${f.founded}` : null, stadium || null].filter(Boolean);
      if (bits.length) side.append(el("div", { class: "cover__facts" }, bits.join(" · ")));
    }
    const schemes = program.notes && typeof program.notes === "object" && program.notes.schemes && typeof program.notes.schemes === "object" ? program.notes.schemes : null;
    if (side && schemes && !side.querySelector(".cover__scheme")) {
      const words = [typeof schemes.offense === "string" && schemes.offense.trim() ? `${schemes.offense.trim()} offense` : null, typeof schemes.defense === "string" && schemes.defense.trim() ? `${schemes.defense.trim()} defense` : null].filter(Boolean);
      if (words.length) side.append(el("div", { class: "cover__scheme" }, words.join(" · ")));
    }
    // the talent chip (his "Keep All", 2026-11-07): the season's answer ranks SP+, Elo and FPI, the program's the talent too
    const talent = program.us && typeof program.us === "object" && program.us.ratings && typeof program.us.ratings === "object" ? program.us.ratings.talent : null;
    if (talent && isNum(talent.rank) && !Array.from(coverEl.querySelectorAll(".cover__side--us .cover-chip")).some((c) => /^Talent #/.test(c.textContent))) addSideChips(coverEl, "us", [ratingChip("Talent", { rank: talent.rank, of: talent.of, href: nationalHref(typeof talent.metric === "string" ? talent.metric : "rating:talent", { team }) })]);
    const staff = teamStaff(program.notes, "us", { abbr: typeof program.us?.abbreviation === "string" ? program.us.abbreviation : null, school: team });
    const staffHost = coverEl.querySelector(".cover__staff--us");
    if (staff && staffHost) staffHost.replaceWith(staff);
    const conditions = coverConditions(program);
    const foot = coverEl.querySelector(".cover__foot");
    if (conditions && foot && !foot.querySelector(".cover__conditions")) foot.append(el("div", { class: "cover__conditions" }, conditions));
  }

  /** Rollover R2: a past season's schedule, its rows' marks from the line kept with the book and each leading to that game's
   *  kept stops (the Pre-Game as it stood at kickoff, the Archive game, the Post-Game as closed out); a row opens the Post-Game. */
  function pastScheduleBand(data, team) {
    const games = records(data.schedule);
    const record = data.record && typeof data.record === "object" ? data.record : {};
    const kept = { line: undefined };
    const marksHost = [];
    fetchJson(bookUrl(pastSeason, "stops"))
      .then((envelope) => {
        kept.line = envelope?.data && typeof envelope.data === "object" ? envelope.data : null;
      })
      .catch(() => {
        kept.line = null; // a book kept without its line: the rows still open each game's Post-Game
      })
      .then(() => marksHost.forEach(({ host, gameId }) => host.replaceChildren(...pastMarks(kept.line, gameId, pastSeason))));
    const marks = (game) => {
      const host = el("span", { class: "stops" });
      marksHost.push({ host, gameId: game.gameId });
      if (kept.line !== undefined) host.replaceChildren(...pastMarks(kept.line, game.gameId, pastSeason));
      return host;
    };
    return band({
      id: "season-schedule",
      title: "Schedule",
      collapsible: false,
      summary: `${recordText(record.overall)} · ${recordText(record.conference)} ${confLabel()}`,
      state: partState(data.parts?.schedule, games.length > 0),
      emptyText: "No games were kept for this season.",
      body: () => el("div", {}, recordLine({ ...record, team }), marginStrip({ games, nextGameId: null, team: null }), scheduleList({ marks, games, nextGameId: null, onSelect: (game) => { window.location.hash = pastHref("post", game.gameId, pastSeason).slice(1); }, context: true, spOf: data.ratings?.sp?.of, events: data.dates, team: null })),
    });
  }

  /** Rollover R3: a past season's papers, each week's as kept, at the bottom of its review (new at the bottom, his rule). */
  function pastPapersBand(season) {
    const shell = (state, extra = {}) => band({ id: "review-papers", title: "The papers", collapsible: false, foldable: true, state, ...extra });
    const host = el("div", { class: "late" }, shell({ status: "loading" }));
    fetchJson(`/api/seasons/${season}/paper`)
      .then((envelope) => {
        const list = records(envelope?.data?.editions);
        host.replaceChildren(shell(list.length ? { status: "ready" } : { status: "empty", message: `No paper was kept for ${season}.` }, {
          summary: `${list.length} kept`,
          body: () => el("ul", { class: "past-papers" }, ...list.map((e) => el("li", {}, el("a", { href: `#newspaper=${encodeURIComponent(text(e.key))}?season=${season}` }, text(e.label)), e.opponent ? el("span", { class: "dim" }, ` · ${e.homeAway === "away" ? "at" : "vs"} ${text(e.opponent)}`) : null))),
        }));
      })
      .catch((error) => host.replaceChildren(shell(isNum(error?.status) && error.status === 404 ? { status: "empty", message: `No paper was kept for ${season}.` } : { status: "error", message: `${text(error?.message || "no answer")}.` })));
    return host;
  }

  function keptWords() {
    const d = new Date(typeof ui.keptAt === "string" ? ui.keptAt : NaN);
    return Number.isNaN(d.getTime()) ? " · as kept when the app moved on" : ` · as kept ${d.toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" })}`;
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
      // freeze wave F4: the facts' dated events on their rows; FEAT-5: another team's rows open its games from its side
      body: () => el("div", {}, recordLine({ ...record, team }), marginStrip({ games, nextGameId: data.nextGameId ?? null, team: picked ? team : null }), scheduleList({ marks: picked ? null : (game) => stopMarks(game.gameId), games, nextGameId: data.nextGameId ?? null, onSelect: (game) => openGame(game, picked ? team : null), context: true, spOf: data.ratings?.sp?.of, events: data.dates, team: picked ? team : null })),
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

  const NUMBERS_VIEWS = [["advanced", "Advanced"]];

  /** The numbers (the Season stop, the season as one line Wave 4; the owner's board of 2026-10-30: "advanced lives in the
   *  bottom of the season tab"): one box with the season's advanced measures as the paired table (PPA, success rate,
   *  explosiveness, national ranks). The app's own count (FEAT-8) left the box with his inventory (2026-11-01: dropped). */
  function numbersBox(data, team) {
    const rows = records(data.advanced?.rows);
    const has = rows.some((row) => isNum(row.value));
    const part = data.parts?.advanced;
    const allowed = NUMBERS_VIEWS.map(([id]) => id);
    let current = allowed.includes(boxView) ? boxView : rememberedView("season.numbers", "advanced", allowed);
    const viewHost = el("div", { class: "box__view" });
    let seg = null;
    const show = (id) => {
      current = id;
      seg?.mark(id);
      draw();
    };
    const draw = () => {
      viewHost.replaceChildren(el("h4", { class: "d2-head" }, "Advanced: offense and defense, national ranks"), has ? advancedPaired(rows, { team, conferenceLabel: confLabel() }) : note(part && part.status === "error" ? `${text(part.error)}. The app keeps retrying.` : "Advanced stats appear after the first game.", { kind: part && part.status === "error" ? "error" : "empty" }));
    };
    seg = viewSwitch(NUMBERS_VIEWS, current, (id) => {
      rememberView("season.numbers", id);
      show(id);
    });
    draw();
    return band({
      id: "season-numbers",
      title: "The numbers",
      collapsible: false,
      foldable: true,
      summary: "advanced measures",
      tools: seg,
      state: { status: "ready" },
      body: () => el("div", { class: "box" }, viewHost),
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

  /** Board 9 ("can we identify each week by the team we played, maybe their team colors?"): one column a game. */
  function trendsBody(data) {
    const trends = data.trends && typeof data.trends === "object" ? data.trends : {};
    const missing = Array.isArray(data.parts?.trends?.missingWeeks) ? data.parts.trends.missingWeeks : [];
    const grid = trendGrid({
      games: trendGames(data),
      metrics: [
        { key: "points", label: "Points scored", values: trends.points },
        { key: "pointsAllowed", label: "Points allowed", values: trends.pointsAllowed },
        { key: "yardsPerPlay", label: "Yards per play", values: trends.yardsPerPlay, format: "1f" },
        { key: "turnoverMargin", label: "Turnover margin", values: trends.turnoverMargin, format: "+0f" },
        { key: "thirdDown", label: "Third down", values: trends.thirdDown, format: "pct" },
      ],
    });
    return el(
      "div",
      { class: "tgrid-wrap" },
      grid,
      grid ? el("p", { class: "note trend__key" }, "Each column is one game, headed by the opponent in its colors; a filled dot is a win, a hollow one a loss; the dashed line is the season average.") : null,
      missing.length ? note(`Box scores for week${missing.length > 1 ? "s" : ""} ${missing.map(text).join(", ")} could not be loaded. The app keeps retrying.`) : null,
    );
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
      tools: el("a", { class: "btn btn--quiet", href: typeof data.team?.conference === "string" && data.team.conference.trim() ? `#conference=${encodeURIComponent(data.team.conference.trim())}` : "#conference" }, "Conference page"), // the conference page (2026-11-02)
      state: partState(data.parts?.records, rows.length > 0),
      emptyText: "Standings appear after the first conference game.",
      // board 6 (ENH-31, owner 2026-10-25): each contender's range of finishes still possible under the table
      body: () => el("div", { class: "tight" }, standingsTable(rows, { conference: confLabel(), rowClass: rowMark(next), caption: `${confLabel()} standings`, sort: ui.sorts.standings, onSort: (sort) => { ui.sorts.standings = sort; } }), raceRanges(data.race, { abbreviations: Object.fromEntries(rows.filter((r) => typeof r.team === "string" && typeof r.abbreviation === "string").map((r) => [r.team, r.abbreviation])) })),
    });
  }

  // the Polls band moved to ui/polls-band.js (wave 3, 2026-11-01): the polls left My Team for the Newspaper and the sheets

  /** The bands that joined My Team (wave 3 of the one-column page), each loading its own answer: the Availability report,
   *  Talent and recruiting, Tendencies and Getting there (ours, from the next game's program), What we need (from this
   *  answer), the roster's five, the class and Where they're from, Staff, Play value and usage, School facts, Players to
   *  know (ours, from the magazine) and the Circle of Blame (ours, its own view in a host). In the inventory's order. */
  function lateBandsOf(data, team, ours) {
    const teamUrl = `/api/team/${encodeURIComponent(team)}`;
    const extras = lateBands(teamUrl, [["talent", "Talent and recruiting", "team-recruiting"], ["staff", "Staff", "team-staff"], ["playValue", "Play value and usage", "team-playvalue"], ["facts", "School facts", "team-facts"]], (d) => teamExtraBands(d, ui.team));
    // the lineup picture (owner 2026-11-01: "The lineup picture should go in the season\my team as well"): ours from the next game's chart
    const program = ours ? lateBands("/api/program/next", [["tendencies", "Tendencies", "season-tendencies"], ["trip", "Getting there", "season-trip"], ["lineup", "Lineup", "season-lineup"]], (d) => ({ tendencies: tendenciesBand(d, { id: "season-tendencies" }), trip: tripBand(d, { id: "season-trip" }), lineup: lineupBand(d, { id: "season-lineup" }) })) : [];
    const roster = lateBands(`/api/roster?team=${encodeURIComponent(team)}`, [["breakdown", "Roster breakdown", "roster-breakdown"], ["costs", "Roster costs (rumored)", "roster-costs"], ["table", "Roster", "roster-table"], ["stars", "Recruiting stars on the roster", "roster-stars"], ["impact", "Impact players", "roster-impact"]], (d) => {
      const [breakdown, costs, table, stars, impact] = rosterBands(d, ui.roster);
      return { breakdown, costs, table, stars, impact };
    });
    const recruiting = lateBands(`/api/recruiting?team=${encodeURIComponent(team)}`, [["klass", "The class", "recruiting-class"], ["where", "Where they're from", "recruiting-where"]], (d) => {
      const draw = () => {
        const [klass, where] = recruitingBands(d, ui.recruiting, { visitors: false, redraw: draw });
        recruiting[0].replaceChildren(klass);
        if (where) recruiting[1].replaceChildren(where);
      };
      const [klass, where] = recruitingBands(d, ui.recruiting, { visitors: false, redraw: draw });
      return { klass, where };
    });
    const stars = ours ? lateBands("/api/preseason", [["stars", "Players to know", "season-stars"]], (d) => {
      const mine = records(d.teams).find((t) => school(t.school) === team) || records(d.teams)[0] || null;
      const part = mine ? starsPart(mine) : null;
      return { stars: part ? band({ id: "season-stars", title: "Players to know", collapsible: false, foldable: true, summary: "from the preseason magazine", state: { status: "ready" }, body: () => part }) : null };
    }) : [];
    const blame = ours ? blameHost() : null;
    return [
      injurySheetBand(team, { id: "season-injuries", title: "Availability report" }),
      extras[0],
      program[0],
      program[1],
      raceBand(data.race, null, { id: "season-race" }),
      ...roster,
      ...recruiting,
      extras[1],
      extras[2],
      extras[3],
      ...stars,
      blame,
      program[2], // the lineup picture (owner 2026-11-01), at the bottom until he places it
    ].filter(Boolean);
  }

  /** The Circle of Blame's own view mounted in a host on the page (the wheel, the case, What moved, The season). */
  function blameHost(season = null) {
    ui.blame?.unmount();
    const host = el("div", { class: "late late--blame" });
    ui.blame = season ? createBlameView({ embedded: true, url: bookUrl(season, "blame"), kept: true }) : createBlameView({ embedded: true });
    ui.blame.mount(host);
    return host;
  }


  /** The season in review (the season line's Wave 7; owner 2026-11-15, Board 5
   *  "Build as drawn, but make sure there are more players stats, at least every starter"; "Season in review, book, and final
   *  or whatnot are the same thing ... Shown as a regular page in the browser"): My Team as it stands at the season's end, in the
   *  board's order, the bands that look ahead left out (the road ahead, getting there, the next lineup, the availability report,
   *  the next opponent's tendencies, the preseason's players to know), every starter and every player's stats added, and Print:
   *  the browser's own, letter pages in the light theme, as the Pre-Game Program prints. Before the end it is the season so far. */
  function reviewCover(data, team) {
    const rec = data.record && typeof data.record === "object" ? data.record : {};
    const overall = rec.overall && typeof rec.overall === "object" ? rec.overall : {};
    const conf = rec.conference && typeof rec.conference === "object" ? rec.conference : {};
    const games = records(data.schedule);
    const over = games.length > 0 && games.every((g) => g.completed === true);
    const played = games.filter((g) => g.completed === true);
    const lastWeek = played.length ? played[played.length - 1].week : null;
    const mine = records(data.standings).find((row) => row.isUs === true);
    const ratings = data.ratings && typeof data.ratings === "object" ? data.ratings : {};
    const rating = (label, block) => (block && typeof block === "object" && isNum(block.rank)
      ? el("span", { class: "review-cover__chip" }, el("span", { class: "dim" }, label), rankChip(block.rank, block.of, { href: nationalHref(typeof block.metric === "string" ? block.metric : "", { team }), label: `${team}, ${label}` }))
      : null);
    const poll = (label, rank) => (isNum(rank) ? el("span", { class: "review-cover__chip review-cover__poll" }, `${label} ${rank}`) : null);
    const resume = data.resume && typeof data.resume === "object" ? data.resume : {};
    const lines = [
      isNum(resume.expectedWins) ? `Expected wins ${fmtNum(resume.expectedWins, 1)} for the ${isNum(overall.wins) ? overall.wins : DASH} won.` : null,
      resume.sosPlayed && isNum(resume.sosPlayed.rank) ? `Schedule played: #${resume.sosPlayed.rank} of ${isNum(resume.sosPlayed.of) ? resume.sosPlayed.of : DASH} in strength.` : null,
    ].filter(Boolean);
    const record = isNum(overall.wins) ? `${overall.wins}–${isNum(overall.losses) ? overall.losses : 0}${overall.ties ? `–${overall.ties}` : ""}` : DASH;
    const confLine = isNum(conf.wins) ? `${conf.wins}–${isNum(conf.losses) ? conf.losses : 0} ${confLabel()}${mine && isNum(mine.place) ? ` · ${ordinal(mine.place)} in the ${confLabel()}` : ""}` : "";
    return band({
      id: "review-cover",
      title: `${team}${isNum(data.season) ? ` ${data.season}` : ""} · The season in review`,
      collapsible: false,
      summary: `${over ? "the season, final" : isNum(lastWeek) ? `the season so far, through Week ${lastWeek}` : "the season so far"}${pastSeason ? keptWords(data) : ""}`,
      state: partState(data.parts?.schedule, true),
      body: () => el(
        "div",
        { class: "review-cover" },
        el("div", { class: "review-cover__record" }, el("b", {}, record), confLine ? el("span", {}, confLine) : null),
        el(
          "div",
          { class: "review-cover__side" },
          el("div", { class: "review-cover__chips" }, poll("AP", rec.apRank), poll("Coaches", rec.coachesRank), poll("CFP", rec.cfpRank), rating("SP+", ratings.sp), rating("FPI", ratings.fpi), rating("Elo", ratings.elo)),
          lines.length ? el("p", { class: "note" }, lines.join(" ")) : null,
        ),
      ),
    });
  }

  function reviewGrid(data, team, playoff) {
    const players = lateBands(pastSeason ? bookUrl(pastSeason, "players") : "/api/season/players", [["starters", "The starters", "review-starters"], ["players", "Every player's stats", "review-players"]], (d) => playerBands(d, { onPlayer: pastSeason ? null : (row) => openPlayer(row.playerId, row) })); // a past season's player cards would be this season's: the names stay plain
    const print = band({
      id: "review-print",
      title: "Print the season",
      collapsible: false,
      state: { status: "ready" },
      body: () => el("div", { class: "review-print" }, el("p", { class: "note" }, "The browser's own print: letter pages in the light theme. Choose Save as PDF to keep it."), printButton()),
    });
    return el(
      "div",
      { class: "page season season--flow season--review" },
      pastSeason || picked ? null : el("div", { class: "review-rail" }, railHost({ kind: "book" })), // batch 4: the book is the rail's last stop, so it wears the rail too (our own season only, as the Season cover)
      reviewCover(data, team),
      pastSeason ? pastNote(pastSeason) : null,
      pastSeason ? pastScheduleBand(data, team) : scheduleBand(data, team),
      band({ id: "review-lines", title: "The season in a few lines", collapsible: false, foldable: true, state: partState(data.parts?.schedule, true), body: () => reviewBody(data, { games: false }) }),
      records(data.polls).length ? pollsBand(data, { ui, id: "review-polls" }) : null,
      profileBand(data, team),
      numbersBox(data, team),
      ...players,
      ratingsBand(data, team),
      resumeBand(data, team),
      standingsBand(data, null),
      playoff,
      raceBand(data.race, null, { id: "review-race" }),
      trendsBand(data),
      landBand(team, { season: data.season, id: "review-land" }),
      blameHost(pastSeason),
      pastSeason ? pastPapersBand(pastSeason) : null,
      print,
    );
  }

  function render(envelope, container) {
    const data = envelope?.data && typeof envelope.data === "object" ? envelope.data : {};
    if (pastSeason) ui.keptAt = envelope?.meta?.fetched_at; // when the book was kept, said on the cover
    const team = school(data.team?.school) || picked || usSchool();
    ui.conf = school(data.team?.conferenceShort) || school(data.team?.conference);
    const next = nextOpponent(data);
    const ours = !picked || picked === school(data.picker?.home);
    if (next && ours) remember(NEXT_OPPONENT_KEY, next); // the Ratings page marks our next opponent, not another team's
    const before = snapshotKeys(container);
    // The owner's order (2026-10-10), one column since 2026-11-01 ("every band just to be a single band"; board 9's flush rows,
    // Schedule | Standings and Polls | Ratings over Résumé, are stacked in the same order). The College Football Playoff band
    // shows only while the team picked is in the AP Top 25 ("Otherwise they are too far out of the playoff picture"): last
    // until week 8, then first.
    const playoff = data.playoff && inTopTwentyFive(data) ? playoffBand(data, team) : null;
    const playoffFirst = seasonWeek(data) >= 8;
    const coming = records(data.schedule).find((g) => String(g.gameId) === String(data.nextGameId ?? "")) || null;
    const watch = !ours && coming ? followButton(coming, team) : null; // FEAT-1 on a team's page (his inventory, 2026-11-01): Watch it live while its next game can be followed
    const grid = review ? reviewGrid(data, team, playoff) : el(
      "div",
      { class: "page season season--flow" },
      pickWindow(data, team), // the cover on one team (2026-11-07): the rail rides on it on our own season
      watch ? el("div", { class: "season__watch" }, watch) : null,
      playoffFirst ? playoff : null,
      scheduleBand(data, team),
      standingsBand(data, next?.school),
      ratingsBand(data, team),
      resumeBand(data, team),
      profileBand(data, team),
      trendsBand(data),
      roadAheadBand(data, { sorts: ui.sorts }),
      lastSeasonBand(data, team),
      playoffFirst ? null : playoff,
      numbersBox(data, team), // the Season stop (Wave 4): Advanced in its box
      landBand(team, { season: data.season, id: "season-land" }), // the Season stop (Wave 4): our land on the Imperialism Map (FEAT-17)
      ...lateBandsOf(data, team, ours), // wave 3 (2026-11-01): the team page's, the roster's, the recruiting's and the blame's bands
    );
    if (ui.flow) ui.flow.stop();
    if (ui.chips) ui.chips.stop();
    ui.chips = sectionChips(grid); // Phase 17 #5: the pinned section chips, above the page
    ui.chips.refresh();
    container.replaceChildren(ui.chips, grid);
    ui.flow = flow(grid);
    flashChanges(before, container);
    if (focusBand && !ui.revealed) {
      ui.revealed = true;
      setTimeout(() => jumpToBand(container.querySelector(focusBand)), 0); // after the router's scroll to the top
    }
  }

  const view = poller({
    url: pastSeason ? bookUrl(pastSeason, "overview") : picked ? `/api/season/overview?team=${encodeURIComponent(picked)}` : "/api/season/overview",
    onStatus,
    render,
    renderError: (message, container, retry) => container.replaceChildren(errorPanel(pastSeason ? `The ${pastSeason} season in review` : review ? "Season in review" : "My Team", message, retry)),
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
    ui.blame?.unmount(); // the Circle of Blame's own poller goes with the page (wave 3)
    ui.blame = null;
    return unmount.apply(view, args);
  };
  return view;
}

export { rankChip };
