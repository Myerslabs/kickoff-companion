// Your own notes during a game (Phase 19). Each note is stamped with the quarter, clock and score when the page knows them,
// with a small Remove on each. Freeze wave F5 (owner 2026-10-20: "if you write your own note then it should just go into the
// program note, like note from Pat"): every line reads "Note from <your name>", the name from Settings ("the host" until
// set). Since 2026-11-14 (owner: "move this add a note to the bottom of the band", "Claude's always on top, then oldest
// first"): the panel goes under Claude's notes on the Pre-Game Program's Program notes and In Game's Notes sheet, your notes
// oldest first so a new one lands at the bottom, then the line box and the Add button last; no line while there are none.
//
//   gameNotesPanel({ gameId, getContext, name })   getContext() -> { period, clock, score } or null; returns the element
//   noteAuthor(name)                               the name the lines carry: the one given, else Settings', else "the host"
//   periodWord(period) -> "Q2" | "OT" ...    exported for the tests

import { el, isNum, str, text } from "./dom.js";
import { note } from "./states.js";
import { fetchJson } from "../views/common.js";
import { getPrefs } from "../prefs.js";

export function noteAuthor(name) {
  if (str(name)) return name.trim();
  let saved = null;
  try {
    saved = getPrefs()?.hostName;
  } catch {
    saved = null;
  }
  return str(saved) ? saved.trim() : "the host";
}

export function periodWord(period) {
  if (!isNum(period) || period < 1) return "";
  return period <= 4 ? `Q${period}` : period === 5 ? "OT" : `${period - 4}OT`;
}

async function send(url, options = {}) {
  const response = await fetch(url, { cache: "no-store", headers: { "Content-Type": "application/json" }, ...options });
  let envelope = null;
  try {
    envelope = await response.json();
  } catch {
    envelope = null;
  }
  if (!response.ok) throw new Error(envelope?.errors?.[0]?.message || `The server answered ${response.status}`);
  return envelope?.data && typeof envelope.data === "object" ? envelope.data : {};
}

function stamp(n) {
  const bits = [periodWord(n.period), typeof n.clock === "string" ? n.clock : "", typeof n.score === "string" ? n.score : ""].filter(Boolean);
  if (bits.length) return bits.join(" · ");
  const when = typeof n.at === "string" ? new Date(n.at) : null;
  return when && !Number.isNaN(when.getTime()) ? when.toLocaleString([], { weekday: "short", hour: "numeric", minute: "2-digit" }) : "";
}

export function gameNotesPanel({ gameId, getContext, name } = {}) {
  const id = isNum(gameId) ? gameId : Number.parseInt(String(gameId ?? ""), 10);
  const host = el("div", { class: "gamenotes" });
  if (!Number.isFinite(id) || id <= 0) return host;
  const who = noteAuthor(name);
  const input = el("textarea", { class: "input gamenotes__input", rows: "2", maxlength: "1000", placeholder: `A note from ${who}: a play, a call, who to watch`, "aria-label": "Your note" });
  const said = el("p", { class: "note", role: "status" }, "");
  const list = el("ul", { class: "gamenotes__list" });

  function draw(notes) {
    const rows = (Array.isArray(notes) ? notes : []).filter((n) => n && typeof n === "object" && typeof n.text === "string"); // the order written: a new note at the bottom
    list.replaceChildren(...rows.map((n) => el("li", { class: "gamenotes__item" }, el("b", { class: "gamenotes__from" }, `Note from ${who}`), stamp(n) ? el("span", { class: "gamenotes__stamp" }, stamp(n)) : null, el("span", { class: "gamenotes__text" }, n.text), el("button", { class: "btn btn--quiet", type: "button", "aria-label": "Remove this note", onclick: () => remove(n.id) }, "Remove"))));
    list.hidden = !rows.length;
  }

  async function load() {
    try {
      draw((await fetchJson(`/api/gamenotes/${id}`)).data?.notes);
    } catch (error) {
      said.textContent = `Your notes did not load: ${error?.message || "no answer"}.`;
    }
  }

  async function remove(noteId) {
    try {
      draw((await send(`/api/gamenotes/${id}/${encodeURIComponent(noteId)}`, { method: "DELETE" })).notes);
      said.textContent = "";
    } catch (error) {
      said.textContent = `Not removed: ${error?.message || "the request failed"}.`;
    }
  }

  const add = el("button", {
    class: "btn btn--primary", type: "button",
    onclick: async () => {
      const value = input.value.trim();
      if (!value) {
        said.textContent = "Write something first.";
        return;
      }
      let context = null;
      try {
        context = typeof getContext === "function" ? getContext() : null;
      } catch {
        context = null;
      }
      add.disabled = true;
      try {
        const body = { text: value, ...(context && typeof context === "object" ? { period: isNum(context.period) ? context.period : null, clock: typeof context.clock === "string" ? context.clock : null, score: typeof context.score === "string" ? context.score : null } : {}) };
        draw((await send(`/api/gamenotes/${id}`, { method: "POST", body: JSON.stringify(body) })).notes);
        input.value = "";
        said.textContent = "Saved.";
      } catch (error) {
        said.replaceChildren(note(`${error?.message || "The note was not saved"}.`, { kind: "error", lead: "Not saved." }));
      }
      add.disabled = false;
    },
  }, "Add the note");

  list.hidden = true; // until the notes come: no empty line (owner 2026-11-14)
  host.append(list, input, el("p", { class: "settings__actions" }, add), said);
  load();
  return host;
}
