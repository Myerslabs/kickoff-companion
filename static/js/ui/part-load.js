// One part of the game's notes, loaded on its own (post-freeze Wave 1, owner 2026-10-25: "Recruits on hand sends you to
// Program notes. Every empty or partly filled section gets its own Claude button saying what is missing; Copy and Paste
// leave once the data is there"). A band of the Pre-Game Program that has nothing (or half) of its part says what is
// missing and offers that part alone: Run with Claude Code where the server finds the command, else Copy the prompt and
// Paste the answer. The answer is merged into the notes already there (/api/notes/save and /api/notes/run with "parts"),
// never replacing them. A part that is published later in the game week (the injury report two days out, the depth charts
// from the Monday) says from when and offers nothing yet: the rule of 2026-10-23, Run, Copy and alerts only when the data
// can plausibly be had. A filled band draws none of this; a new answer is the Load data page's.
//
//   partLoad({ gameId, parts, lead, detail, due, done })  -> element
//       parts   the notes' part names ("visitors", "availability", "lineups", ...)
//       due     the program's notes.due entry for the first part, { due, from } (missing: due)
//       done    called after a saved paste (default: the page refreshes in place, "kickoff:retry")
//   commandFound()  -> Promise<boolean>, the server's answer once per page load

import { el, fmtDate, isNum, obj, text } from "./dom.js";
import { stateBlock } from "./states.js";
import { promptPaste } from "./prompt-paste.js";
import { dataRunActive, onRunProgress, watchRun } from "./run-bar.js";

let found = null; // one question per page load: is Claude Code on the server

export function commandFound() {
  if (!found) {
    found = fetch("/api/notes/run", { cache: "no-store", headers: { Accept: "application/json" } })
      .then((response) => (response.ok ? response.json() : null))
      .then((body) => body?.data?.commandFound === true)
      .catch(() => false);
  }
  return found;
}

/** Forget the answer (the tests, and a page that wants to ask again). */
export function forgetCommand() {
  found = null;
}

async function send(path, body) {
  const response = await fetch(path, { method: "POST", cache: "no-store", headers: { "Content-Type": "application/json", Accept: "application/json" }, body: JSON.stringify(body) });
  let json = null;
  try {
    json = await response.json();
  } catch {
    json = null;
  }
  if (!response.ok) throw new Error(text(json?.errors?.[0]?.message || `The server answered ${response.status}`));
  const data = obj(json?.data);
  const problem = Array.isArray(json?.errors) && json.errors[0]?.message;
  if (problem) throw new Error(text(problem));
  return data;
}

function refresh() {
  document.dispatchEvent(new CustomEvent("kickoff:retry")); // the page asks the server again, in place
}

export function partLoad({ gameId, parts, lead, detail, due, done } = {}) {
  const asked = (Array.isArray(parts) ? parts : []).filter((p) => typeof p === "string" && p);
  const id = isNum(gameId) ? gameId : Number.parseInt(String(gameId ?? ""), 10);
  const later = due && typeof due === "object" && due.due === false;
  if (later) {
    const when = typeof due.from === "string" && due.from ? fmtDate(due.from, "long") : null;
    return stateBlock({ lead, detail: `${text(detail)} ${when ? `It is published from ${when}; it can be loaded then.` : "It is published later in the game week."}`.trim() });
  }
  const block = stateBlock({ lead, detail });
  if (!Number.isFinite(id) || id <= 0 || !asked.length) return block;
  const query = `gameId=${id}&parts=${encodeURIComponent(asked.join(","))}`;
  const status = el("p", { class: "part-load__status", "aria-live": "polite" });
  const run = el("button", { class: "btn btn--primary", type: "button" }, "Run with Claude");
  const runSlot = el("span", { class: "part-load__run" }); // the button joins it only once the server says Claude Code is there
  let busy = dataRunActive();
  const draw = () => {
    run.disabled = busy;
    run.textContent = busy ? "Loading…" : "Run with Claude";
  };
  run.addEventListener("click", async () => {
    busy = true;
    draw();
    status.textContent = "";
    try {
      const data = await send("/api/notes/run", { gameId: id, parts: asked });
      busy = Boolean(data.running);
      status.textContent = busy ? "Claude Code is looking it up in the background. The page refreshes when it is in." : "";
      watchRun(); // the loading bar follows the run; the page refreshes once at its end
    } catch (error) {
      busy = false;
      status.textContent = `${text(error?.message || "The run did not start")}.`;
    }
    draw();
  });
  const stop = onRunProgress((progress) => {
    if (!run.isConnected && !block.isConnected) {
      stop();
      return;
    }
    busy = progress?.running === true;
    draw();
  });
  const paste = promptPaste({
    label: "this part",
    getPrompt: async () => {
      const response = await fetch(`/api/notes/prompt?${query}`, { cache: "no-store", headers: { Accept: "application/json" } });
      const body = await response.json().catch(() => null);
      if (!response.ok || typeof body?.data?.prompt !== "string") throw new Error(text(body?.errors?.[0]?.message || "The prompt could not be made"));
      return body.data.prompt;
    },
    saveAnswer: (value) => send("/api/notes/save", { gameId: id, text: value, parts: asked }),
    onSaved: () => (typeof done === "function" ? done() : refresh()),
    extra: [runSlot],
  });
  commandFound().then((yes) => {
    if (yes) runSlot.append(run);
    draw();
  });
  block.append(el("div", { class: "part-load" }, paste, status));
  return block;
}
