// The play-by-play log (L5): newest first, filter by team and by key plays, badges per play.
// Phase 17 #21: a play with a flag carries a button per foul after its text (ui/penalty-panel.js).
// Phase 16 wave 3 (L-09): a result column (signed yards and a success mark), scoring plays tinted, a header row
// for each drive, and the filter buttons stay in view while the list scrolls.

import { el, fmtClock, fmtSigned, isNum, period, replaceWith, situationText, text } from "./dom.js";
import { keyPlayBadges } from "./pills.js";
import { penaltyFlags } from "./penalty-panel.js";

const FILTERS = [
  { id: "all", label: "All" },
  { id: "us", label: "usAbbr" },
  { id: "them", label: "themAbbr" },
  { id: "key", label: "Key plays" },
];

/** A scrimmage play (a real down): the ones whose yards and success mean something. */
const scrimmage = (play) => isNum(play.down) && play.down > 0;

/** The result column: signed yards on a scrimmage play, and a dot for a successful one (hollow when it fell short). */
function result(play) {
  const yards = scrimmage(play) && isNum(play.yardsGained) ? play.yardsGained : null;
  const judged = typeof play.success === "boolean";
  if (yards === null && !judged) return el("span", { class: "play__res" });
  return el(
    "span",
    { class: "play__res" },
    yards === null ? null : el("span", { class: `play__yds${yards > 0 ? " play__yds--gain" : yards < 0 ? " play__yds--loss" : ""}` }, fmtSigned(yards, 0)),
    judged ? el("span", { class: `play__ok${play.success ? " play__ok--yes" : ""}`, title: play.success ? "Successful play" : "Not a successful play" }, el("span", { class: "sr-only" }, play.success ? "successful" : "not successful")) : null,
  );
}

function playRow({ play, us, them, isNew = false }) {
  const isUs = play.offense === us.name;
  const offense = isUs ? us : them;
  const defense = isUs ? them : us;
  return el(
    "li",
    { class: `play play--${isUs ? "us" : "them"}${play.scoring === true ? " play--score" : ""}${isNew ? " slide-in" : ""}`, dataset: { play: play.id } },
    el("span", { class: "play__clock" }, `${period(play.period)} ${fmtClock(play.clock)}`),
    el(
      "span",
      { class: "play__sit" },
      `${text(offense.abbr)} · ${situationText({ down: isNum(play.down) && play.down > 0 ? play.down : null, distance: play.distance, yardsToGoal: play.yardsToGoal, offenseAbbr: offense.abbr, defenseAbbr: defense.abbr })}`, // kickoffs and no-play penalties carry down 0: no "0th & 0"
      keyPlayBadges(play.flags),
    ),
    el("span", { class: "play__text" }, text(play.text), isNum(play.ppa) ? el("span", { class: "play__ppa", title: "Predicted points added" }, fmtSigned(play.ppa, 2)) : null, penaltyFlags(play)),
    result(play),
  );
}

/** The drive a play belongs to, as a key (the id when CFBD sent one, else the number); null when neither came. */
const driveKey = (play) => (play.driveId !== null && play.driveId !== undefined && play.driveId !== "" ? `id:${play.driveId}` : isNum(play.driveNumber) ? `n:${play.driveNumber}` : null);

/** The header row over one drive's plays (newest first): who had it, how many plays, the net yards, and points. */
function driveHeader(group, { us, them }) {
  const first = group[group.length - 1];
  const snaps = group.filter(scrimmage);
  // the drive is the offense's that ran its downs: a kickoff at its start is the other team's snap
  const owner = (snaps.length ? snaps[snaps.length - 1] : group[0]).offense;
  const isUs = owner === us.name;
  const side = isUs ? us : them;
  const yards = snaps.reduce((sum, p) => sum + (isNum(p.yardsGained) ? p.yardsGained : 0), 0);
  const scored = group.some((p) => p.scoring === true && p.offense === owner);
  const parts = [`${snaps.length} ${snaps.length === 1 ? "play" : "plays"}`, `${fmtSigned(yards, 0)} yds`];
  if (scored) parts.push("Points");
  return el(
    "li",
    { class: `play-drive play-drive--${isUs ? "us" : "them"}` },
    el("span", { class: "play-drive__team" }, isNum(first.driveNumber) ? `${text(side.abbr)} drive ${first.driveNumber}` : `${text(side.abbr)} drive`),
    el("span", { class: "play-drive__sum" }, parts.join(" · ")),
  );
}

/**
 * playLog({ plays, us: {name, abbr}, them: {name, abbr}, filter, onFilter(id), maxHeight, limit, freshIds })
 * Returns the element; element.setFilter(id), element.getFilter(), and element.addPlay(play) to
 * prepend one. `filter` is the starting filter and `onFilter` hears the reader's changes, so a
 * view that rebuilds the log keeps the filter. `freshIds` (a Set) names the plays that slide in.
 */
export function playLog({ plays = [], us, them, filter = "all", onFilter, maxHeight, limit = 200, freshIds = null }) {
  const fresh = freshIds instanceof Set ? new Set(freshIds) : new Set(); // Phase 16 wave 3: plays new since the last draw slide in
  let current = FILTERS.some((f) => f.id === filter) ? filter : "all";
  plays = Array.isArray(plays) ? plays.filter((play) => play && typeof play === "object") : []; // a malformed record is skipped, not drawn
  const list = el("ul", { class: "plays", "aria-live": "polite" });
  if (maxHeight) list.style.setProperty("--plays-max", typeof maxHeight === "number" ? `${maxHeight}px` : maxHeight);

  const matches = (play) => {
    if (current === "us") return play.offense === us.name;
    if (current === "them") return play.offense === them.name;
    if (current === "key") return Array.isArray(play.flags) && play.flags.length > 0;
    return true;
  };

  /** The rows: drive headers between drives, except under Key plays, where the plays stand alone. */
  function rows(shown) {
    if (current === "key") return shown.map((play) => playRow({ play, us, them, isNew: fresh.has(play.id) }));
    const out = [];
    let group = [];
    let key = null;
    const flush = () => {
      if (!group.length) return;
      if (key !== null) out.push(driveHeader(group, { us, them }));
      for (const play of group) out.push(playRow({ play, us, them, isNew: fresh.has(play.id) }));
      group = [];
    };
    for (const play of shown) {
      const next = driveKey(play);
      if (group.length && next !== key) flush();
      key = next;
      group.push(play);
    }
    flush();
    return out;
  }

  function render() {
    const shown = plays.filter(matches).slice(0, limit);
    replaceWith(list, shown.length === 0 ? el("li", { class: "note" }, plays.length === 0 ? "Plays appear after kickoff." : "No plays match this filter.") : null, rows(shown));
  }

  const seg = el(
    "div",
    { class: "seg", role: "group", "aria-label": "Filter plays" },
    FILTERS.map((f) =>
      el(
        "button",
        {
          type: "button",
          "aria-pressed": f.id === current ? "true" : "false",
          onclick: () => {
            current = f.id;
            fresh.clear(); // a filter change redraws the list; nothing slides
            for (const button of seg.querySelectorAll("button")) button.setAttribute("aria-pressed", button.dataset.filter === current ? "true" : "false");
            render();
            if (typeof onFilter === "function") onFilter(current);
          },
          dataset: { filter: f.id },
        },
        f.label === "usAbbr" ? text(us.abbr) : f.label === "themAbbr" ? text(them.abbr) : f.label,
      ),
    ),
  );

  render();
  const root = el("div", { class: "play-log" }, el("div", { class: "play-tools" }, seg), list);
  root.addPlay = (play) => {
    if (!play || typeof play !== "object") return;
    plays.unshift(play);
    fresh.clear();
    fresh.add(play.id);
    if (matches(play)) render();
  };
  root.setFilter = (id) => {
    current = FILTERS.some((f) => f.id === id) ? id : "all";
    fresh.clear();
    for (const button of seg.querySelectorAll("button")) button.setAttribute("aria-pressed", button.dataset.filter === current ? "true" : "false");
    render();
  };
  root.getFilter = () => current;
  return root;
}

export function playLogSkeleton(rows = 6) {
  return el("div", {}, Array.from({ length: rows }, () => el("div", { class: "skel skel--row" })));
}
