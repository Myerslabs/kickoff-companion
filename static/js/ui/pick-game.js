// Pick a game (owner 2026-11-02: "I want the in game to stay the same, I just want to be able to see it for any team"):
// the tool on In Game's row that opens a side sheet with the week's games, every FBS team, from the ticker's slate
// (/api/ticker?mode=national: the games with their live scores, no call of its own): ours first, the games on now, the ones
// to come by kickoff, the finals last; a search box finds a team. A tap follows that game on this same In Game screen
// (POST /api/live/follow, FEAT-1), from the home side, or from ours when we play in it; the Watching line and Back to our
// game stay as they are (ui/follow.js). The host picks for every screen; a guest reads the list.
//
//   pickGameSheet({ guest })              opens the sheet; returns openSheet's handle
//   pickRows(entries, { query, us })      the entries ordered and filtered (exported for the tests)
//   pickRow(entry, { onPick, guest })     one row (exported for the tests)

import { isUs, usSchool } from "../identity.js";
import { deviceGame, watchHere, watchRoom } from "../watching.js"; // batch 3: a game on this screen alone
import { DASH, el, isNum, records, text } from "./dom.js";
import { openSheet } from "./remote.js";
import { note } from "./states.js";

const ORDER = { live: 1, pre: 2, final: 3 };

function school(side) {
  return side && typeof side === "object" && typeof side.school === "string" && side.school.trim() ? side.school.trim() : null;
}

function order(entry) {
  const status = typeof entry.status === "string" ? entry.status : "pre";
  return [entry.isUs === true ? 0 : ORDER[status] || 2, status === "final" ? "" : String(entry.kickoff || "~"), school(entry.home) || ""];
}

/** Every entry with two named sides, ours first, then the games on now, the ones to come by kickoff, the finals last;
 *  `query` keeps the games with a side whose school or abbreviation starts with (or contains) the words. */
export function pickRows(entries, { query = "", us = usSchool() } = {}) {
  const q = typeof query === "string" ? query.trim().toLowerCase() : "";
  const match = (side) => {
    const s = side && typeof side === "object" ? side : {};
    return [s.school, s.abbreviation].some((v) => typeof v === "string" && v.toLowerCase().includes(q));
  };
  return records(entries)
    .filter((e) => school(e.home) && school(e.away))
    .map((e) => ({ ...e, isUs: e.isUs === true || [school(e.home), school(e.away)].includes(us) }))
    .filter((e) => !q || match(e.home) || match(e.away))
    .sort((a, b) => {
      const [ka, kb] = [order(a), order(b)];
      for (let i = 0; i < ka.length; i += 1) if (ka[i] !== kb[i]) return ka[i] < kb[i] ? -1 : 1;
      return 0;
    });
}

/** The side In Game follows the game from: ours when we play in it, else the home side. */
export function sideOf(entry) {
  const sides = [school(entry?.home), school(entry?.away)];
  return sides.find((s) => s && isUs(s)) || sides[0] || null;
}

async function follow(entry) {
  const id = entry?.gameId;
  const response = await fetch("/api/live/follow", { method: "POST", cache: "no-store", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ gameId: Number(id), team: sideOf(entry) }) });
  let envelope = null;
  try {
    envelope = await response.json();
  } catch {
    envelope = null;
  }
  if (!response.ok) throw new Error(envelope?.errors?.[0]?.message || `The server answered ${response.status}`);
  return envelope?.data || null;
}

function sideWords(side) {
  const s = side && typeof side === "object" ? side : {};
  const name = school(s) || DASH;
  return el("span", { class: "pick-game__side" }, isNum(s.rank) ? el("small", { class: "pick-game__rank" }, `#${s.rank} `) : null, name, isNum(s.points) ? el("b", { class: "pick-game__pts" }, ` ${s.points}`) : null);
}

/** One game's row: its status words, the away side at the home side with the scores, ours marked. A button for the host, a
 *  plain row for a guest. */
export function pickRow(entry, { onPick, onEveryone = null, guest = false } = {}) {
  const e = entry && typeof entry === "object" ? entry : {};
  const status = typeof e.status === "string" ? e.status : "pre";
  const words = typeof e.detail === "string" && e.detail.trim() ? e.detail.trim() : status === "final" ? "Final" : status === "live" ? "In progress" : "Time to be set";
  const inner = [
    el("span", { class: `pick-game__when pick-game__when--${status}` }, words),
    el("span", { class: "pick-game__game" }, sideWords(e.away), el("span", { class: "pick-game__at" }, " at "), sideWords(e.home)),
    e.isUs === true ? el("span", { class: "pick-game__us" }, usSchool() || "Ours") : null,
  ];
  const mine = deviceGame();
  const here = mine && isNum(e.gameId) && mine.gameId === e.gameId;
  if (!isNum(e.gameId)) return el("li", { class: `pick-game__row${e.isUs === true ? " is-us" : ""}` }, ...inner);
  // batch 3 (owner 2026-11-16): a tap watches the game on this screen, a guest's too; the host can still move every screen
  const everyone = !guest && typeof onEveryone === "function" ? el("button", { type: "button", class: "btn btn--quiet pick-game__all", title: "Every screen follows this game", onclick: () => onEveryone(e) }, "Every screen") : null;
  return el("li", { class: `pick-game__row${e.isUs === true ? " is-us" : ""}${here ? " is-here" : ""}` }, el("button", { type: "button", class: "pick-game__btn", "aria-current": here ? "true" : null, onclick: () => onPick?.(e) }, ...inner), everyone);
}

/** The sheet: the search box, the list, the words under it. */
export function pickGameSheet({ guest = document.body?.dataset?.role === "guest" } = {}) {
  let entries = null;
  let query = "";
  const said = el("p", { class: "note", role: "status" }, "");
  const list = el("ul", { class: "pick-game__list" });
  const search = el("input", { type: "search", class: "pick-game__search", placeholder: "Find a team", "aria-label": "Find a team", autocomplete: "off", oninput: () => { query = search.value; draw(); } });
  const body = el(
    "div",
    { class: "pick-game" },
    el("p", { class: "note" }, guest ? "A tap watches that game on this screen only; the other screens stay on the room's game." : "A tap watches that game on this screen only, from the home team's side (ours when we play); the other screens stay on the room's game. Every screen moves them all."),
    search,
    list,
    said,
  );
  const handle = openSheet({ title: "Pick a game", body });

  /** Batch 3: this screen alone, our game too (the review, 2026-11-19: once the host moved every screen elsewhere, our row
   *  is not the room's). When the game is the room's own, the server answers the room's state for it (app/api/live.py). */
  function pickHere(entry) {
    watchHere({ gameId: entry.gameId, home: school(entry.home), away: school(entry.away), team: sideOf(entry) });
    handle.close?.();
    if (typeof window !== "undefined" && window.location.hash !== "#live") window.location.hash = "live";
  }

  async function pick(entry) {
    said.textContent = "Switching In Game…";
    for (const b of list.querySelectorAll("button")) b.disabled = true;
    try {
      const data = await follow(entry);
      const kept = data && typeof data === "object" && data.followed && typeof data.followed === "object";
      if (entry.isUs === true || kept) watchRoom(); // every screen follows it, this one too, once the room has moved
      if (entry.isUs === true) said.textContent = "Back to our game.";
      else if (!kept) said.textContent = `${text(school(entry.away))} at ${text(school(entry.home))} is over or gone; In Game stays on our game.`; // the engine drops a finished game (ui/follow.js's window)
      else said.textContent = `Watching ${text(school(entry.away))} at ${text(school(entry.home))}.`;
      if (entry.isUs === true || kept) setTimeout(() => handle.close?.(), 600);
      else for (const b of list.querySelectorAll("button")) b.disabled = false;
    } catch (error) {
      said.textContent = `Not switched: ${text(error?.message)}.`;
      for (const b of list.querySelectorAll("button")) b.disabled = false;
    }
  }

  function draw() {
    if (!Array.isArray(entries)) return;
    const rows = pickRows(entries, { query });
    list.replaceChildren(...(rows.length ? rows.map((e) => pickRow(e, { onPick: pickHere, onEveryone: pick, guest })) : [el("li", { class: "pick-game__row pick-game__row--none" }, query ? `No game with "${query.trim()}" this week.` : "No games on the slate this week.")]));
  }

  (async () => {
    try {
      const response = await fetch("/api/ticker?delay=0&mode=national", { cache: "no-store", headers: { Accept: "application/json" } });
      const envelope = await response.json();
      if (!response.ok) throw new Error(envelope?.errors?.[0]?.message || `The server answered ${response.status}`);
      entries = records(envelope?.data?.games);
      draw();
    } catch (error) {
      body.replaceChildren(note(`The week's games did not load: ${text(error?.message || "no answer")}.`, { kind: "error" }), el("button", { type: "button", class: "btn", onclick: () => { handle.close?.(); pickGameSheet({ guest }); } }, "Try again"));
    }
  })();
  return handle;
}
