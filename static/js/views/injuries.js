// The Injury Report (owner 2026-10-10): our team's injuries through the season, newest week first, from the availability
// reports the game notes already hold (/api/injuries, no CFBD call). One band per game: the next game first and open, then
// the games played, the older ones folded until opened (each band remembers its fold). A game with no report says so and
// leads to its program, where the notes that bring one are added (spec R2: missing data shows where to get it). The layout
// pass (owner 2026-10-22, "This is good" to the picks): no strip of week chips over the page, and the played games with no
// report fold into one line, each game in it a way to its program.
// injurySheetBand() is the same report for another team, in its side sheet: our games against it.

import { el, fmtDate, isNum, records, text } from "../ui/dom.js";
import { availabilityTable } from "../ui/editorial.js";
import { mountFlow, stopFlow } from "../ui/flow.js";
import { band, note } from "../ui/states.js";
import { statTableSkeleton } from "../ui/stat-table.js";
import { pollMs } from "../prefs.js";
import { errorPanel, fetchJson, partState, poller } from "./common.js";

const COUNTED = [["out", "out"], ["doubtful", "doubtful"], ["questionable", "questionable"], ["game-time decision", "game-time"], ["probable", "probable"]];

/** "Week 7 at Lake Effect", "Week 2 vs Diner Tech", "Vrbo Fiesta Bowl vs Diner Tech". Exported for the tests. */
export function gameTitle(game) {
  const g = game && typeof game === "object" ? game : {};
  const opponent = typeof g.opponent?.school === "string" && g.opponent.school.trim() ? g.opponent.school.trim() : "the opponent";
  const where = g.homeAway === "away" ? "at" : "vs";
  const lead = typeof g.label === "string" && g.label.trim() ? g.label.trim() : isNum(g.week) ? `Week ${g.week}` : "Game";
  return `${lead} ${where} ${opponent}`;
}

/** "2 out, 1 questionable" from a game's rows; "nobody listed" for a report with no one on it. Exported for the tests. */
export function countsLine(rows) {
  const list = records(rows);
  if (!list.length) return "nobody listed";
  const parts = COUNTED.map(([status, word]) => [list.filter((r) => String(r.status || "").toLowerCase() === status).length, word]).filter(([n]) => n > 0).map(([n, word]) => `${n} ${word}`);
  const other = list.length - COUNTED.reduce((sum, [status]) => sum + list.filter((r) => String(r.status || "").toLowerCase() === status).length, 0);
  if (other > 0) parts.push(`${other} other`);
  return parts.join(", ");
}

function missing(game) {
  const why = game.error ? `This game's notes could not be read (${text(game.error)}).` : game.notes ? "This game's notes hold no availability report." : "No notes for this game yet.";
  const id = game.gameId;
  const link = isNum(id) || /^\d+$/.test(String(id ?? "")) ? (game.completed ? el("a", { href: `#program=${encodeURIComponent(String(id))}` }, "Open this game's program") : el("a", { href: "#prompts" }, "Get this week's notes")) : null; // the Prompts phase: a missing report leads to the prompts
  return el("p", { class: "note" }, `${why} `, link);
}

function gameBody(game, { isUs }) {
  const rows = records(game.rows);
  const unplaced = isUs ? records(game.unassigned) : [];
  if (!game.reported) return missing(game);
  return el(
    "div",
    {},
    rows.length ? availabilityTable({ rows, source: game.source, updatedAt: game.updatedAt, showTeam: false }) : note(`Nobody from ${text(game.team) || "this team"} on the report.`),
    unplaced.length ? el("div", {}, el("h4", { class: "d2-head" }, "Team not named in the report"), availabilityTable({ rows: unplaced })) : null,
  );
}

function gameBand(game, index, { isUs, team }) {
  const rows = records(game.rows);
  const when = game.completed ? null : isNum(Date.parse(game.date)) ? `kickoff ${fmtDate(game.date)}` : null;
  return band({
    id: `injuries-${game.gameId}`,
    title: `${game.next ? "Next: " : ""}${gameTitle(game)}`,
    collapsible: false,
    foldable: true,
    collapsed: index >= 3, // the next game and the last two played open; the rest folded until opened
    summary: [game.reported ? countsLine(rows) : "no report", when].filter(Boolean).join(" · "),
    state: { status: "ready" },
    body: () => gameBody({ ...game, team }, { isUs }),
  });
}

/** No games: the schedule failed (CFBD down, the quota) reads as an error with its reason, never as an empty season. */
function emptyState(data) {
  const part = data.parts && typeof data.parts === "object" ? data.parts.schedule : null;
  return part && part.status === "error" ? partState(part, false) : { status: "empty", message: "No games on the schedule yet." };
}

/** The played games with no report, in one line (the layout pass, 2026-10-22): each a link to its program, where the notes
 *  that bring a report are added. Null when every played game has one. Exported for the tests. */
export function quietLine(games) {
  const list = records(games);
  if (!list.length) return null;
  const link = (game) => {
    const id = game.gameId;
    return isNum(id) || /^\d+$/.test(String(id ?? "")) ? el("a", { href: `#program=${encodeURIComponent(String(id))}` }, gameTitle(game)) : gameTitle(game);
  };
  return el(
    "p",
    { class: "note injuries-quiet flow-full" },
    el("b", {}, `No report for ${list.length === 1 ? "one played game" : `${list.length} played games`}: `),
    list.flatMap((game, i) => [i ? " · " : null, link(game)]).filter(Boolean),
  );
}

function render(envelope, container, state) {
  const data = envelope?.data && typeof envelope.data === "object" ? envelope.data : {};
  const games = records(data.games);
  const team = text(data.team?.school);
  const quiet = games.filter((game) => game.completed === true && !game.reported && !game.error); // played, no report: one line at the foot (a notes file that will not read keeps its band and says so)
  const shown = games.filter((game) => !quiet.includes(game));
  const page = el(
    "div",
    { class: "page injuries-page" },
    games.length
      ? shown.map((game, index) => gameBand(game, index, { isUs: data.isUs === true, team }))
      : band({ id: "injuries-none", title: "Injury Report", collapsible: false, state: emptyState(data), errorLead: "Could not load the schedule." }),
    quietLine(quiet),
    seasonLongBand(data), // freeze wave F3: the preseason load's season-long injuries, at the bottom
    el("p", { class: "note flow-full" }, "From the availability reports in each game's notes (the conference's report where it publishes one). Newest week first. Season-long injuries and suspensions from the preseason load are at the end."),
  );
  // each game's report spans two columns where there are two or more (wave 3): a table with a column of notes needs the room
  mountFlow(state.ui, container, page, { chips: false, wide: [...shown.map((game) => `injuries-${game.gameId}`), "injuries-season"] }); // no week chips over the page (2026-10-22)
}

/** The preseason load's "Injuries and suspensions" (freeze wave F3): the same table kit as a game's report, once, at the end. */
function seasonLongBand(data) {
  const rows = records(data.seasonLong);
  if (!rows.length) return null;
  return band({
    id: "injuries-season",
    title: "Season-long",
    collapsible: false,
    foldable: true,
    summary: `${rows.length} from the preseason load`,
    state: { status: "ready" },
    body: () => el("div", {}, availabilityTable({ rows, showTeam: false }), el("p", { class: "note" }, "From the preseason load's injuries and suspensions, as of the season's start; a week's report above says more when it names the player.")),
  });
}

export function createInjuriesView({ onStatus } = {}) {
  const state = { ui: {} };
  const view = poller({
    url: "/api/injuries",
    refreshMs: pollMs(),
    onStatus,
    render: (envelope, container) => render(envelope, container, state),
    renderError: (message, container, retry) => container.replaceChildren(errorPanel("Injury Report", message, retry)),
    renderLoading: () => el("div", { class: "page" }, band({ title: "Injury Report", collapsible: false, state: { status: "loading" }, skeleton: () => statTableSkeleton(6, 3) })),
    loadingDetail: "Each game's availability report",
  });
  return { ...view, unmount() { stopFlow(state.ui); view.unmount(); } };
}

/** Another team's report in its side sheet: our games against it, newest first. Loads on its own; never blocks the sheet. */
export function injurySheetBand(school) {
  const host = el("div", {}, note("Loading the availability reports…"));
  const section = band({ title: "Injury report", collapsible: false, foldable: true, summary: "from our game notes", state: { status: "ready" }, body: () => host });
  fetchJson(`/api/injuries?team=${encodeURIComponent(text(school))}`)
    .then((envelope) => {
      const data = envelope?.data && typeof envelope.data === "object" ? envelope.data : {};
      const games = records(data.games);
      if (!games.length) {
        const failed = data.parts?.schedule?.status === "error";
        host.replaceChildren(note(failed ? "Our schedule could not be loaded, so the reports cannot be matched to this team yet. The app keeps retrying." : `No report: ${text(school)} is not on our schedule this season, and the notes cover our games only.`));
        return;
      }
      host.replaceChildren(...games.map((game) => el("div", { class: "injury-game" }, el("h4", { class: "d2-head" }, `${gameTitle(game)}${game.reported ? ` · ${countsLine(game.rows)}` : ""}`), gameBody({ ...game, team: text(school) }, { isUs: false }))));
    })
    .catch((error) => host.replaceChildren(note(`The availability reports could not be loaded (${text(error?.message) || "no answer"}).`)));
  return section;
}
