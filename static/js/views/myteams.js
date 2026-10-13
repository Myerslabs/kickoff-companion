// My teams (public release Phase 5b): one list of the home team, the other primary teams and the secondary
// teams, each with its record, its national ranks (AP, SP+, Elo, FPI) and its last and next game. Every
// team name opens its team page; every SP+, Elo and FPI rank opens its national list in the My teams view.
// The list reads answers other pages already cache, so it costs no call of its own once they have loaded.
// With a free key only the home team shows, with a note on what a Tier 2 key adds.
//
// Tables wave 3 (owner 2026-10-10): sized by its own box, every data point in its own column. Large (a 1080p screen):
// Team | Role | Why | Record | Conf record | AP rank | SP+ rank | Elo rank | FPI rank | Last game ("W 31-14") | Last opponent
// ("at Silver Dollar") | Next game ("vs Diner Tech") | Kickoff ("Oct 10"). Medium (the iPad held sideways): the shorter heads,
// without Why, Elo and FPI. Small: Team (its abbreviation, still its link) | Record | Last | Opp ("at SD") | Next ("vs DT").
// The AP rank is the poll's badge (a poll rank, never the quartile chip). The teams sort; the server's order (role, AP
// rank, school) to start.

import { DASH, el, fmtDate, isNum, obj, str } from "../ui/dom.js";
import { nationalHref, pollHref } from "../ui/national-link.js";
import { band, note } from "../ui/states.js";
import { logoLink, teamAbbrLink } from "../ui/team-page.js";
import { pollBadge, statTable, statTableSkeleton } from "../ui/stat-table.js";
import { pollMs } from "../prefs.js";
import { stateName } from "../us-states.js";
import { combinedState, errorPanel, poller, recordText } from "./common.js";

const ROLE_LABEL = { home: "Home team", primary: "Primary", secondary: "Secondary" };
const ROLE_WEIGHT = { home: 3, primary: 2, secondary: 1 }; // the first tap on Role (high to low) puts the home team first
const PLANS_URL = "https://collegefootballdata.com/api-tiers";

/** "W 31-14", "L 10-17", or the result alone when the score is missing; a dash when there is no finished game. */
export function resultText(game) {
  const g = obj(game);
  if (!str(g.opponent)) return DASH;
  const score = isNum(g.usPoints) && isNum(g.themPoints) ? `${g.usPoints}-${g.themPoints}` : "";
  const result = str(g.result) || "";
  return [result, score].filter(Boolean).join(" ") || DASH;
}

/** "at Silver Dollar" or "vs Diner Tech" (a neutral site reads vs); { short: true } for the abbreviation ("at SD"), the
 *  school when the opponent has none. A dash when there is no game. */
export function opponentText(game, { short = false } = {}) {
  const g = obj(game);
  const opponent = str(g.opponent);
  if (!opponent) return DASH;
  const where = g.homeAway === "away" ? "at" : "vs";
  return `${where} ${short ? str(g.opponentAbbr) || opponent : opponent}`;
}

/** The kickoff's day ("Oct 10"); a dash when unknown. */
export function kickoffText(game) {
  const g = obj(game);
  return str(g.opponent) && str(g.date) ? fmtDate(g.date, "short") : DASH;
}

export function shapeRows(rows) {
  return (Array.isArray(rows) ? rows : [])
    .filter((r) => r && typeof r === "object" && str(r.school))
    .map((r) => {
      const last = obj(r.last);
      const next = obj(r.next);
      return {
        ...r,
        team: r.school,
        abbreviation: str(r.abbreviation),
        apRank: isNum(r.apRank) ? r.apRank : null,
        roleText: ROLE_LABEL[r.role] || DASH,
        roleWeight: ROLE_WEIGHT[r.role] || null,
        whyText: r.role === "secondary" ? (Array.isArray(r.why) ? r.why.filter((w) => str(w)).map(stateName) : []).join(", ") || null : null, // the role column says the rest
        recordShown: recordText(r.record),
        confShown: recordText(r.conferenceRecord),
        spRank: isNum(obj(r.sp).rank) ? r.sp.rank : null,
        eloRank: isNum(obj(r.elo).rank) ? r.elo.rank : null,
        fpiRank: isNum(obj(r.fpi).rank) ? r.fpi.rank : null,
        lastResult: resultText(last),
        lastMargin: str(last.opponent) && isNum(last.usPoints) && isNum(last.themPoints) ? last.usPoints - last.themPoints : null,
        lastOpp: opponentText(last),
        lastOppShort: opponentText(last, { short: true }),
        lastOppName: str(last.opponent),
        nextOpp: opponentText(next),
        nextOppShort: opponentText(next, { short: true }),
        nextOppName: str(next.opponent),
        nextDate: kickoffText(next),
        nextAt: str(next.opponent) ? str(next.date) : null,
        isUs: r.role === "home",
      };
    });
}

function render(envelope, container, state) {
  const data = obj(envelope?.data);
  const rows = shapeRows(data.rows);
  const set = obj(data.teamSet);
  const of = (key) => {
    const first = rows.find((r) => isNum(obj(r[key]).of));
    return first ? first[key].of : undefined;
  };
  const rankLink = (metric) => (row) => nationalHref(metric, { team: row.team, scope: set.allowed === true ? "mine" : "national" });
  const polled = isNum(data.pollWeek); // with the poll loaded an unranked team reads NR; without it, a dash
  const apBadge = (row) => (isNum(row.apRank) ? pollBadge(row.apRank, "AP", { href: pollHref("AP", { team: row.team }), label: row.team, showPoll: false }) : polled ? el("span", { class: "nr" }, "NR") : DASH);
  const columns = [
    { key: "team", label: "Team", kind: "text", render: (row) => logoLink(row.team, row), renderShort: (row) => teamAbbrLink(row.team, row.abbreviation) },
    { key: "roleText", label: "Role", kind: "text", size: "medium", sortKey: "roleWeight" },
    { key: "whyText", label: "Why", kind: "text", size: "large" },
    { key: "recordShown", label: "Record", kind: "text" },
    { key: "confShown", label: "Conf record", labelMid: "Conf", kind: "text", size: "medium" },
    { key: "apRank", label: "AP rank", labelMid: "AP", size: "medium", render: apBadge },
    { key: "spRank", label: "SP+ rank", labelMid: "SP+", kind: "rank", of: of("sp"), size: "medium", link: rankLink("rating:sp") },
    { key: "eloRank", label: "Elo rank", labelMid: "Elo", kind: "rank", of: of("elo"), size: "large", link: rankLink("rating:elo") },
    { key: "fpiRank", label: "FPI rank", labelMid: "FPI", kind: "rank", of: of("fpi"), size: "large", link: rankLink("rating:fpi") },
    { key: "lastResult", label: "Last game", labelMid: "Last", kind: "text", sortKey: "lastMargin" },
    { key: "lastOpp", label: "Last opponent", labelMid: "Opponent", labelShort: "Opp", kind: "text", shortKey: "lastOppShort", sortKey: "lastOppName" },
    { key: "nextOpp", label: "Next game", labelMid: "Next", kind: "text", shortKey: "nextOppShort", sortKey: "nextOppName" },
    { key: "nextDate", label: "Kickoff", labelMid: "Date", kind: "text", size: "medium", sortKey: "nextAt" },
  ].map((column) => ({ ...column, tieKey: "team" })); // a tie in any column falls back to the school's name
  const plansUrl = str(data.plansUrl) && data.plansUrl.startsWith("https://") ? data.plansUrl : PLANS_URL;
  const lockedNote = str(data.note)
    ? el("p", { class: "note plan-note" }, `${data.note} `, set.allowed === true ? el("a", { href: "/welcome" }, "Open the setup page") : el("a", { href: plansUrl, target: "_blank", rel: "noopener" }, "See CFBD's plans"))
    : null;
  const primaries = rows.filter((r) => r.role === "home" || r.role === "primary").length;
  const secondary = rows.filter((r) => r.role === "secondary").length;
  container.replaceChildren(
    el(
      "div",
      { class: "page myteams-page" }, // up to 1,600 px wide (components.css): the table's large needs about 1,420 px, so a 1080p screen shows it
      band({
        id: "myteams",
        title: "My teams",
        collapsible: false,
        summary: rows.length ? `${primaries} primary, ${secondary} secondary${isNum(data.pollWeek) ? ` · AP week ${data.pollWeek}` : ""}` : "",
        state: combinedState([data.parts?.teams, data.parts?.records, data.parts?.rankings], rows.length > 0),
        emptyText: "No teams yet. Pick your teams on the setup page.",
        body: () =>
          el(
            "div",
            {},
            statTable({ compact: true, sizes: true, columns, rows, sort: state.sort, onSort: (sort) => { state.sort = sort; }, rowClass: (r) => (r.isUs ? "is-us" : null), caption: "My teams" }),
            lockedNote,
            note("Every rank is national. Tap a team for its page, an SP+, Elo or FPI rank for the full list, or an AP rank for the poll. Your home team's colors theme the app; the Season, Pre-Game Program and In Game pages follow it."),
            el("p", { class: "settings__actions" }, el("a", { class: "btn", href: "/welcome" }, "Change my teams")),
          ),
      }),
    ),
  );
}

export function createMyTeamsView({ onStatus } = {}) {
  const state = { sort: null };
  return poller({
    url: "/api/myteams",
    refreshMs: pollMs(),
    onStatus,
    render: (envelope, container) => render(envelope, container, state),
    renderError: (message, container, retry) => container.replaceChildren(errorPanel("My teams", message, retry)),
    renderLoading: () => el("div", { class: "page" }, band({ title: "My teams", collapsible: false, state: { status: "loading" }, skeleton: () => statTableSkeleton(6, 10) })),
  });
}
