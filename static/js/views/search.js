// Search (Phase 15): any FBS team, any player of ours or the next opponent's as you type, and every
// player in CFBD on request. Opens from the Search button in the top bar or the "/" key.
// Typing only reads the app's own copies (no CFBD call); "Search every player" asks CFBD once per term.
// Phase 16 (G3-15): the old results dim while a search runs (aria-busy), the matched letters are marked,
// openable rows end in a chevron, 'Former' and 'Not FBS' are tags, and a favorite team carries a star.

import { usSchool } from "../identity.js";
import { DASH, el, frag, isNum, teamLogo, text } from "../ui/dom.js";
import { openSheet } from "../ui/remote.js";
import { fetchJson } from "./common.js";
import { openPlayer } from "./player.js";

const DEBOUNCE_MS = 200;

function section(title, items) {
  return el("section", { class: "search__group" }, el("h3", { class: "search__head" }, title), el("ul", { class: "search__list" }, items));
}

/** The words of a query worth marking: two letters or more, longest first so "ole miss" marks "ole" and "miss". */
function terms(query) {
  return [...new Set(String(query ?? "").toLowerCase().split(/\s+/).filter((w) => w.length >= 2))].sort((a, b) => b.length - a.length);
}

/** A name with every match of the query's words in <mark> (G3-15). Exported for the tests. */
export function marked(value, query) {
  const label = text(value);
  const words = terms(query);
  if (label === DASH || !words.length) return label;
  const lower = label.toLowerCase();
  const hits = [];
  for (const word of words) {
    for (let at = lower.indexOf(word); at >= 0; at = lower.indexOf(word, at + word.length)) {
      if (!hits.some(([s, e]) => at < e && at + word.length > s)) hits.push([at, at + word.length]);
    }
  }
  if (!hits.length) return label;
  hits.sort((a, b) => a[0] - b[0]);
  const parts = [];
  let pos = 0;
  for (const [start, end] of hits) {
    if (start > pos) parts.push(label.slice(pos, start));
    parts.push(el("mark", { class: "search__mark" }, label.slice(start, end)));
    pos = end;
  }
  if (pos < label.length) parts.push(label.slice(pos));
  return frag(parts);
}

const CHEVRON = () => el("span", { class: "search__go", "aria-hidden": "true" }, "›");

function teamItem(t, close, query) {
  return el(
    "li",
    {},
    el(
      "button",
      { class: `search__item${t.isFavorite === true ? " search__item--fav" : ""}`, type: "button", onclick: () => { close(); document.dispatchEvent(new CustomEvent("kickoff:team", { detail: t.school })); } },
      teamLogo(t, { size: 28, className: "search__logo" }),
      el("span", { class: "search__name" }, el("span", {}, marked(t.school, query), t.isFavorite === true ? el("span", { class: "search__star", title: "One of your teams", "aria-label": "One of your teams" }, " ★") : null), el("small", {}, [t.mascot, t.conference].filter(Boolean).join(" · ") || DASH)),
      el("span", { class: "search__meta" }, text(t.abbreviation)),
      CHEVRON(),
    ),
  );
}

function playerItem(p, close, query) {
  const sub = [p.position, p.team, p.current === false && isNum(p.toYear) ? `last played ${p.toYear}` : null].filter(Boolean).join(" · ");
  const tag = p.canOpen ? null : el("span", { class: "tag" }, p.current ? "Not FBS" : "Former"); // cards cover this season's FBS players
  const body = [
    el("span", { class: "search__num" }, isNum(p.number) ? `#${p.number}` : DASH),
    el("span", { class: "search__name" }, el("span", {}, marked(p.name, query)), el("small", {}, sub || DASH)),
    el("span", { class: "search__meta" }, tag),
  ];
  if (!p.canOpen) return el("li", {}, el("div", { class: "search__item search__item--quiet" }, body, el("span", { class: "search__go" })));
  return el(
    "li",
    {},
    el("button", { class: `search__item${p.isUs ? " search__item--us" : ""}`, type: "button", onclick: () => { close(); openPlayer(p.playerId, { name: p.name, number: p.number, position: p.position, isUs: p.isUs, team: p.team }); } }, body, CHEVRON()),
  );
}

/** Opens the search sheet. Returns its close function. */
export function openSearch() {
  const input = el("input", { class: "search__input", type: "search", placeholder: "Team or player", "aria-label": "Search teams and players", autocomplete: "off", spellcheck: "false", enterkeyhint: "search" });
  const results = el("div", { class: "search__results", "aria-live": "polite" });
  const wideButton = el("button", { class: "btn", type: "button" }, "Search every player");
  let timer = null;
  let seq = 0;
  let handle = null;
  const close = () => handle && handle.close ? handle.close() : null;

  function pending(on) {
    if (on) {
      results.setAttribute("aria-busy", "true");
      results.classList.add("is-pending");
    } else {
      results.removeAttribute("aria-busy");
      results.classList.remove("is-pending");
    }
  }

  function render(data, wide, query) {
    const teams = Array.isArray(data.teams) ? data.teams.filter((t) => t && typeof t === "object") : [];
    const players = Array.isArray(data.players) ? data.players.filter((p) => p && typeof p === "object") : [];
    const all = Array.isArray(data.wide) ? data.wide.filter((p) => p && typeof p === "object") : null;
    const blocks = [];
    if (teams.length) blocks.push(section("Teams", teams.map((t) => teamItem(t, close, query))));
    if (players.length) blocks.push(section(`Players: ${usSchool()}${data.opponent ? ` and ${text(data.opponent)}` : ""}`, players.map((p) => playerItem(p, close, query))));
    if (wide && all) blocks.push(all.length ? section("Every player (CFBD)", all.map((p) => playerItem(p, close, query))) : el("p", { class: "note" }, "CFBD has no player by that name."));
    if (data.wideNote) blocks.push(el("p", { class: "note" }, text(data.wideNote)));
    if (!blocks.length) blocks.push(el("p", { class: "note" }, `No team, ${usSchool()} player or next-opponent player by that name. Search every player to ask CFBD.`));
    results.replaceChildren(...blocks);
  }

  async function run(wide = false) {
    const q = input.value.trim();
    const mine = ++seq;
    if (q.length < 2 && !wide) {
      pending(false);
      results.replaceChildren(el("p", { class: "note" }, "Type two letters or more: a school, a mascot, a player, or a jersey number."));
      return;
    }
    pending(true); // the old results dim until the new ones arrive
    if (wide) results.prepend(el("p", { class: "note" }, "Asking CFBD…"));
    try {
      const envelope = await fetchJson(`/api/search?q=${encodeURIComponent(q)}${wide ? "&wide=1" : ""}`);
      if (mine !== seq) return; // a newer search has started
      pending(false);
      render(envelope?.data || {}, wide, q);
    } catch (error) {
      if (mine !== seq) return;
      pending(false);
      results.replaceChildren(el("p", { class: "note note--error" }, `Search failed: ${text(error?.message)}. Try again.`));
    }
  }

  input.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(() => run(false), DEBOUNCE_MS);
  });
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      clearTimeout(timer);
      run(input.value.trim().length >= 3);
    }
  });
  wideButton.addEventListener("click", () => run(true));

  const body = el("div", { class: "search" }, el("div", { class: "search__bar" }, input, wideButton), el("p", { class: "search__hint" }, "Teams and players as you type. Enter or the button searches every player in CFBD (one call per name)."), results);
  handle = openSheet({ title: "Search", body });
  input.focus(); // the sheet focuses its close button; the reader came here to type
  run(false);
  return close;
}
