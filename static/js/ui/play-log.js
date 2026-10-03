// The play-by-play log (L5): newest first, filter by team and by key plays, badges per play.

import { el, fmtClock, fmtSigned, isNum, period, replaceWith, situationText, text } from "./dom.js";
import { keyPlayBadges } from "./pills.js";

const FILTERS = [
  { id: "all", label: "All" },
  { id: "us", label: "usAbbr" },
  { id: "them", label: "themAbbr" },
  { id: "key", label: "Key plays" },
];

function playRow({ play, us, them, isNew = false }) {
  const isUs = play.offense === us.name;
  const offense = isUs ? us : them;
  const defense = isUs ? them : us;
  return el(
    "li",
    { class: `play play--${isUs ? "us" : "them"}${isNew ? " slide-in" : ""}`, dataset: { play: play.id } },
    el("span", { class: "play__clock" }, `${period(play.period)} ${fmtClock(play.clock)}`),
    el(
      "span",
      { class: "play__sit" },
      `${text(offense.abbr)} · ${situationText({ down: isNum(play.down) && play.down > 0 ? play.down : null, distance: play.distance, yardsToGoal: play.yardsToGoal, offenseAbbr: offense.abbr, defenseAbbr: defense.abbr })}`, // kickoffs and no-play penalties carry down 0: no "0th & 0"
      keyPlayBadges(play.flags),
    ),
    el("span", { class: "play__text" }, text(play.text), isNum(play.ppa) ? el("span", { class: "play__ppa", title: "Predicted points added" }, fmtSigned(play.ppa, 2)) : null),
  );
}

/**
 * playLog({ plays, us: {name, abbr}, them: {name, abbr}, filter, onFilter(id), maxHeight, limit })
 * Returns the element; element.setFilter(id), element.getFilter(), and element.addPlay(play) to
 * prepend one. `filter` is the starting filter and `onFilter` hears the reader's changes, so a
 * view that rebuilds the log keeps the filter.
 */
export function playLog({ plays = [], us, them, filter = "all", onFilter, maxHeight, limit = 200 }) {
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

  function render() {
    const shown = plays.filter(matches).slice(0, limit);
    replaceWith(
      list,
      shown.length === 0 ? el("li", { class: "note" }, plays.length === 0 ? "Plays appear after kickoff." : "No plays match this filter.") : null,
      shown.map((play) => playRow({ play, us, them })),
    );
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
  const root = el("div", {}, el("div", { class: "play-tools" }, seg), list);
  root.addPlay = (play) => {
    plays.unshift(play);
    if (matches(play)) list.prepend(playRow({ play, us, them, isNew: true }));
  };
  root.setFilter = (id) => {
    current = FILTERS.some((f) => f.id === id) ? id : "all";
    for (const button of seg.querySelectorAll("button")) button.setAttribute("aria-pressed", button.dataset.filter === current ? "true" : "false");
    render();
  };
  root.getFilter = () => current;
  return root;
}

export function playLogSkeleton(rows = 6) {
  return el("div", {}, Array.from({ length: rows }, () => el("div", { class: "skel skel--row" })));
}
