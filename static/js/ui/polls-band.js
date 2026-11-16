// The Polls band (wave 3 of the one-column page, owner 2026-11-01: the polls left My Team for the Newspaper, the side
// sheet, the Preseason Magazine and the season book; drawn here so any page draws the same band). Each poll on a switch,
// sized by its own box (tables wave 3): the poll's own order (its badge at large and medium, a plain number at small), the
// team (its abbreviation at small, still its link), its conference in a column of its own, the week's movement and the
// points; the AP path and the first-place votes at large. The points and the votes show only for a poll that has them
// (the committee's has neither). Teams sort, by the poll's order first, the reader's order kept in `ui.sorts`.
//
//   pollsBand(data, { ui, next, id, rowClass })   data: a season overview answer ({ polls, parts }); ui: { poll, sorts };
//       next: the next opponent's school (its row marked); rowClass: a row's class, else ours and the next opponent's

import { DASH, el, isNum, records, text } from "./dom.js";
import { pollName } from "./national-link.js";
import { rankPath } from "./sparkline.js";
import { band, note } from "./states.js";
import { pollBadge, statTable } from "./stat-table.js";
import { conferenceColumn, logoLink, teamAbbrLink } from "./team-page.js";
import { partState } from "../views/common.js";

/** The latest AP rank on a team's path (the AP path column sorts by it); null when it is unranked now. */
function lastRank(path) {
  const list = Array.isArray(path) ? path : [];
  const last = list.length ? list[list.length - 1] : null;
  return isNum(last) ? last : null;
}

/** GX-06: '+3' up, '-2' down, 'new' to the poll, '0' unchanged; a dash with no week before. */
export function movementCell(row) {
  const label = typeof row.movement === "string" ? row.movement : null;
  if (label === "new") return el("span", { class: "mv mv--new" }, "new");
  if (!isNum(row.change) || !label) return el("span", { class: "mv" }, "–");
  const cls = row.change > 0 ? "mv--up" : row.change < 0 ? "mv--down" : "";
  const shown = row.change > 0 ? `+${row.change}` : row.change < 0 ? `−${Math.abs(row.change)}` : "0";
  return el("span", { class: `mv ${cls}`.trim(), title: isNum(row.previousRank) ? `No. ${row.previousRank} the week before` : null }, shown);
}

function defaultRowClass(next) {
  return (row) => {
    if (row.isUs) return "is-us";
    if (next && (row.team === next || row.school === next)) return "is-next";
    return row.isFavorite === true ? "is-fav" : null;
  };
}

export function pollTable(poll, { ui, rowClass }) {
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
  const sorts = ui.sorts && typeof ui.sorts === "object" ? ui.sorts : (ui.sorts = {});
  return statTable({
    compact: true,
    sizes: true,
    columns,
    rows,
    sort: sorts[id] || { key: "rank", dir: "ascending" },
    onSort: (sort) => {
      sorts[id] = sort; // the reader's order survives a refresh, one per poll
    },
    rowClass,
    caption: text(poll.name),
  });
}

export function pollsBand(data, { ui, next = null, id = "season-polls", rowClass = null } = {}) {
  const state = ui && typeof ui === "object" ? ui : { poll: null, sorts: {} };
  const polls = records(data?.polls);
  if (!polls.some((poll) => poll.poll === state.poll)) state.poll = polls[0]?.poll ?? null;
  const mark = typeof rowClass === "function" ? rowClass : defaultRowClass(next);
  const body = el("div", {});
  const buttons = polls.map((poll) => el("button", { type: "button", "aria-pressed": poll.poll === state.poll ? "true" : "false", dataset: { poll: text(poll.poll) } }, `${text(poll.poll)}${isNum(poll.usRank) ? ` #${poll.usRank}` : ""}`));
  const draw = () => {
    const poll = polls.find((p) => p.poll === state.poll);
    body.replaceChildren(
      poll
        ? el("div", { class: "tight" }, el("p", { class: "poll-caption" }, `${text(poll.name)}, week ${text(poll.week)}`), pollTable(poll, { ui: state, rowClass: mark }))
        : note("No poll yet."),
    );
  };
  buttons.forEach((button, index) =>
    button.addEventListener("click", () => {
      state.poll = polls[index]?.poll ?? null;
      buttons.forEach((b, i) => b.setAttribute("aria-pressed", i === index ? "true" : "false"));
      draw();
    }),
  );
  if (polls.length) draw();
  return band({
    id,
    title: "Polls",
    collapsible: false,
    foldable: true,
    tools: polls.length > 1 ? el("div", { class: "seg", role: "group", "aria-label": "Poll" }, buttons) : null,
    state: partState(data?.parts?.rankings, polls.length > 0),
    emptyText: "Polls appear after the first poll of the season.",
    body: () => body,
  });
}
