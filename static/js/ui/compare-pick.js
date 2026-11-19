// Compare two players: the second player (batch 3, owner 2026-11-16, a viewer's ask of 2026-10-31 "Compare players side by side
// please"; his picks: from the player card, two players). The card's Compare opens this sheet: a search of every player the
// app knows (our roster, the opponents', every FBS roster it has read), and "Search all of FBS" for CFBD's own player search.
// A pick opens #compare=<first>,<second>, the two side by side (views/compare.js).
//
//   openComparePick({ first, replace })   first: { playerId, name, team } the card's player; replace: "a" or "b" to change
//                                         one side of a comparison already open (the other side stays)
//   compareHref(a, b)                     the comparison's address from two { playerId, team }

import { el, isNum, text } from "./dom.js";
import { openSheet } from "./remote.js";
import { fetchJson } from "../views/common.js";

const WAIT_MS = 200;
const str = (value) => (typeof value === "string" ? value.trim() : "");

export function compareHref(a, b) {
  const id = (p) => str(String(p?.playerId ?? ""));
  if (!/^\d{1,12}$/.test(id(a)) || !/^\d{1,12}$/.test(id(b))) return null;
  const q = [str(a.team) ? `ta=${encodeURIComponent(str(a.team))}` : null, str(b.team) ? `tb=${encodeURIComponent(str(b.team))}` : null].filter(Boolean).join("&");
  return `#compare=${id(a)},${id(b)}${q ? `?${q}` : ""}`;
}

async function findPlayers(q, wide) {
  const envelope = await fetchJson(`/api/search?q=${encodeURIComponent(q)}${wide ? "&wide=1" : ""}`);
  const data = envelope?.data && typeof envelope.data === "object" ? envelope.data : {};
  const players = Array.isArray(data.players) ? data.players.filter((p) => p && typeof p === "object" && /^\d{1,12}$/.test(String(p.playerId ?? ""))) : [];
  return { players, note: str(data.wideNote) || null };
}

export function openComparePick({ first, other = null, replace = null } = {}) {
  const keep = replace === "a" ? other : first; // the side that stays
  if (!keep || !/^\d{1,12}$/.test(String(keep.playerId ?? ""))) return null;
  let handle = null;
  const results = el("div", { class: "compare-pick__results", "aria-live": "polite" });
  const input = el("input", { type: "search", class: "compare-pick__input", placeholder: "Search a player by name", "aria-label": "Search a player by name", autocomplete: "off", enterkeyhint: "search" });
  let asked = 0;
  let timer = null;

  function go(player) {
    const second = { playerId: String(player.playerId), team: str(player.team) || null };
    const href = replace === "a" ? compareHref(second, keep) : compareHref(keep, second);
    handle?.close?.("route");
    if (href) window.location.hash = href.slice(1);
  }

  function row(p) {
    const facts = [p.position, p.team].map(str).filter(Boolean).join(" · ");
    return el(
      "button",
      { type: "button", class: "compare-pick__row", onclick: () => go(p) },
      el("b", {}, `${isNum(p.number) ? `#${p.number} ` : ""}${text(p.name)}`),
      facts ? el("small", {}, facts) : null,
    );
  }

  async function search(wide = false) {
    const q = input.value.trim();
    if (q.length < 2) {
      results.replaceChildren();
      return;
    }
    const mine = ++asked;
    results.replaceChildren(el("p", { class: "note" }, wide ? "Asking CFBD for every FBS player by that name…" : "Searching…"));
    try {
      const { players, note } = await findPlayers(q, wide);
      if (mine !== asked) return;
      const others = players.filter((p) => String(p.playerId) !== String(keep.playerId));
      results.replaceChildren(
        ...(others.length ? others.slice(0, 15).map(row) : [el("p", { class: "note" }, `No player by "${q}" in the rosters the app has read.`)]),
        wide ? (note ? el("p", { class: "note" }, note) : null) : el("button", { type: "button", class: "btn btn--quiet compare-pick__wide", onclick: () => search(true) }, "Search all of FBS"),
      );
    } catch (error) {
      if (mine !== asked) return;
      results.replaceChildren(el("p", { class: "note note--error" }, `The search did not answer (${text(error?.message) || "error"}).`));
    }
  }

  input.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(() => search(false), WAIT_MS);
  });

  const body = el(
    "div",
    { class: "compare-pick" },
    el("p", { class: "note" }, `Compare ${text(keep.name || "this player")} with any player: same position or not, either team.`),
    input,
    results,
  );
  handle = openSheet({ title: replace ? "Change the player" : `Compare ${text(keep.name || "")}`.trim(), body, className: "compare-pick-sheet" });
  setTimeout(() => {
    try {
      if (!(globalThis.matchMedia && globalThis.matchMedia("(pointer: coarse)").matches)) input.focus();
    } catch {
      // no matchMedia
    }
  }, 50);
  return handle;
}
