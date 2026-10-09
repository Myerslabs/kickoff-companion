// My teams (public release Phase 5b): one list of the home team, the other primary teams and the secondary
// teams, each with its record, its national ranks (AP, SP+, Elo, FPI) and its last and next game. Every
// team name opens its team page; every SP+, Elo and FPI rank opens its national list in the My teams view.
// The list reads answers other pages already cache, so it costs no call of its own once they have loaded.
// With a free key only the home team shows, with a note on what a Tier 2 key adds.

import { DASH, el, fmtDate, isNum, obj, str } from "../ui/dom.js";
import { nationalHref } from "../ui/national-link.js";
import { band, note } from "../ui/states.js";
import { logoLink } from "../ui/team-page.js";
import { statTable, statTableSkeleton } from "../ui/stat-table.js";
import { pollMs } from "../prefs.js";
import { stateName } from "../us-states.js";
import { combinedState, errorPanel, poller, recordText } from "./common.js";

const ROLE_LABEL = { home: "Home team", primary: "Primary", secondary: "Secondary" };
const PLANS_URL = "https://collegefootballdata.com/api-tiers";

/** "W 31-14 vs Opponent" or "L 10-17 at Opponent"; a dash when there is no finished game. */
export function lastText(game) {
  const g = obj(game);
  const opponent = str(g.opponent);
  if (!opponent) return DASH;
  const where = g.homeAway === "away" ? "at" : "vs";
  const score = isNum(g.usPoints) && isNum(g.themPoints) ? `${g.usPoints}-${g.themPoints} ` : "";
  return `${str(g.result) ? `${g.result} ` : ""}${score}${where} ${opponent}`;
}

/** "vs Opponent, Oct 11"; a dash when the season is over for the team. */
export function nextText(game) {
  const g = obj(game);
  const opponent = str(g.opponent);
  if (!opponent) return DASH;
  const where = g.homeAway === "away" ? "at" : "vs";
  const when = str(g.date) ? fmtDate(g.date, "short") : "";
  return `${where} ${opponent}${when && when !== DASH ? `, ${when}` : ""}`;
}

export function shapeRows(rows) {
  return (Array.isArray(rows) ? rows : [])
    .filter((r) => r && typeof r === "object" && str(r.school))
    .map((r) => ({
      ...r,
      team: r.school,
      roleText: ROLE_LABEL[r.role] || DASH,
      whyText: r.role === "secondary" ? (Array.isArray(r.why) ? r.why.filter((w) => str(w)).map(stateName) : []).join(", ") || null : null, // the role column says the rest
      recordShown: recordText(r.record),
      confShown: recordText(r.conferenceRecord),
      spRank: isNum(obj(r.sp).rank) ? r.sp.rank : null,
      eloRank: isNum(obj(r.elo).rank) ? r.elo.rank : null,
      fpiRank: isNum(obj(r.fpi).rank) ? r.fpi.rank : null,
      lastShown: lastText(r.last),
      nextShown: nextText(r.next),
      isUs: r.role === "home",
    }));
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
  const columns = [
    { key: "team", label: "Team", kind: "text", sub: "whyText", stick: true, render: (row) => logoLink(row.team, row) },
    { key: "roleText", label: "", kind: "text" },
    { key: "recordShown", label: "Record", kind: "text" },
    { key: "confShown", label: "Conf", kind: "text" },
    { key: "apRank", label: "AP", kind: "rank", sortable: true },
    { key: "spRank", label: "SP+", kind: "rank", of: of("sp"), sortable: true, link: rankLink("rating:sp") },
    { key: "eloRank", label: "Elo", kind: "rank", of: of("elo"), sortable: true, link: rankLink("rating:elo") },
    { key: "fpiRank", label: "FPI", kind: "rank", of: of("fpi"), sortable: true, link: rankLink("rating:fpi") },
    { key: "lastShown", label: "Last game", kind: "text" },
    { key: "nextShown", label: "Next", kind: "text" },
  ];
  const plansUrl = str(data.plansUrl) && data.plansUrl.startsWith("https://") ? data.plansUrl : PLANS_URL;
  const lockedNote = str(data.note)
    ? el("p", { class: "note plan-note" }, `${data.note} `, set.allowed === true ? el("a", { href: "/welcome" }, "Open the setup page") : el("a", { href: plansUrl, target: "_blank", rel: "noopener" }, "See CFBD's plans"))
    : null;
  const primaries = rows.filter((r) => r.role === "home" || r.role === "primary").length;
  const secondary = rows.filter((r) => r.role === "secondary").length;
  container.replaceChildren(
    el(
      "div",
      { class: "page" },
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
            statTable({ compact: true, columns, rows, sort: state.sort, onSort: (sort) => { state.sort = sort; }, rowClass: (r) => (r.isUs ? "is-us" : null), caption: "My teams" }),
            lockedNote,
            note("Every rank is national. Tap a team for its page, or an SP+, Elo or FPI rank for the full list. Your home team's colors theme the app; the Season, Game program and Live pages follow it."),
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
