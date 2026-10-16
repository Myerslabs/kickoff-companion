// Notes by copy and paste (public release Phase 6). On the Game program's notes band:
//   Copy the prompt the server writes for this game and paste it into any AI chat that can search the web; paste
//   the chat's answer back and save. Phase 17 #12 (owner-approved mockup): one line of explanation, the prompt and
//   the notes file's path each with a copy button, a shorter box, and ONE Save that checks as it saves: a clean
//   answer saves and the page reloads; an answer with problems saves and lists them; an unreadable one is not saved.
// The server reads the answer leniently (code fences and chatter are fine, a bad row is skipped) and saves
// data/notes/<game_id>.json; the page then reloads with the notes. Nothing here calls an AI.
//
// Copying works over plain HTTP too: the Clipboard API needs a secure page, so the fallback selects the
// prompt in a text box and copies with execCommand, and the box stays open for a manual copy if both fail.
//
//   notesPaste({ gameId, onSaved, location })  the element. onSaved() runs after a save (default: reload the page).
//   notesPathButton(gameId, location, fetchPath)  the file's location with its Copy (the Load data page uses it too)

import { el, isNum, obj, text } from "./dom.js";
import { promptPaste } from "./prompt-paste.js";

async function send(path, options = {}) {
  const response = await fetch(path, { cache: "no-store", headers: { "Content-Type": "application/json", Accept: "application/json" }, ...options });
  let body = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  if (!response.ok) {
    const detail = Array.isArray(body?.detail) ? body.detail[0]?.msg : null; // FastAPI's own 422 for a bad body
    throw new Error(text(body?.errors?.[0]?.message || detail || `The server answered ${response.status}`));
  }
  return obj(body?.data);
}

/** Copy text: the Clipboard API where the page allows it, else a selected text box. Resolves true when copied. */
export async function copyText(value, box) {
  try {
    if (globalThis.navigator?.clipboard && globalThis.isSecureContext !== false) {
      await navigator.clipboard.writeText(value);
      return true;
    }
  } catch {
    // fall through to the text box
  }
  if (!box) return false;
  box.value = value;
  box.hidden = false;
  try {
    box.focus();
    box.select();
    box.setSelectionRange?.(0, value.length);
    return document.execCommand?.("copy") === true;
  } catch {
    return false;
  }
}

/**
 * The notes file's location with its Copy (Phase 17 #12; 2026-10-16, owner: "make sure the written notes work too, so you
 * can copy the location where you want to add the notes"): on the Pre-Game Program and on the Load data page's notes card.
 * `location` is { file, fileExists, example } from the server; without it the location comes with the prompt. The copy
 * works over plain HTTP too (a selected box and execCommand); when the file is not there yet, the example to start from.
 */
export function notesPathButton(gameId, location = null, fetchPath = null) {
  const id = isNum(gameId) ? gameId : Number.parseInt(String(gameId ?? ""), 10);
  if (!Number.isFinite(id) || id <= 0) return null;
  const loc = location && typeof location === "object" ? location : {};
  const known = typeof loc.file === "string" && loc.file ? loc.file : null;
  const example = typeof loc.example === "string" && loc.example ? loc.example : null;
  const box = el("input", { class: "notes-paste__copybox", type: "text", readonly: "", hidden: true, spellcheck: "false", "aria-label": "The location to copy" }); // one line: it never scrolls up and down
  const said = el("span", { class: "note", role: "status" }, "");
  const copy = async (value, done) => {
    box.hidden = true;
    const ok = await copyText(value, box);
    said.textContent = ok ? done : "Copy it from the box: it is selected.";
    if (ok) box.hidden = true;
  };
  const button = el("button", { class: "notes-paste__path", type: "button", title: "Copy where this game's notes file lives" }, el("code", {}, `data/notes/${id}.json`), el("span", { class: "notes-paste__copy" }, "Copy"));
  button.addEventListener("click", async () => {
    let path = known;
    if (!path && typeof fetchPath === "function") {
      try {
        path = await fetchPath();
      } catch {
        path = null; // the short path still copies
      }
    }
    const where = path || `data/notes/${id}.json`;
    const missing = loc.fileExists === false;
    await copy(where, missing ? "Copied. There is no file there yet: start from a copy of the example, saved under that name." : "Copied the notes file's location. Open it in any text editor on the server computer.");
  });
  const exampleButton = loc.fileExists === false && example
    ? el("button", { class: "btn btn--quiet", type: "button", onclick: () => copy(example, "Copied the example's location. Copy that file, rename it to the game's name above, and fill it in.") }, "Copy the example's location")
    : null;
  return el("span", { class: "notes-paste__where" }, button, exampleButton, said, box);
}

export function notesPaste({ gameId, onSaved, location = null } = {}) {
  const id = isNum(gameId) ? gameId : Number.parseInt(String(gameId ?? ""), 10);
  const host = el("div", { class: "notes-paste" });
  if (!Number.isFinite(id) || id <= 0) return host;
  let fullPath = null; // the notes file's real location, from the server with the prompt
  const fetchPrompt = async () => {
    const data = await send(`/api/notes/prompt?gameId=${id}`);
    if (typeof data.path === "string" && data.path) fullPath = data.path;
    return data;
  };
  // Phase 19: the prompt is copied, never shown; the answer is pasted and saved in one tap. The page reloads with the notes.
  const where = notesPathButton(id, location, async () => {
    await fetchPrompt();
    return fullPath;
  });
  host.append(
    el("p", { class: "notes-paste__lead" }, "Ask any AI chat that can search the web for this game's notes: copy the prompt, then copy the chat's answer and paste it here. Saving replaces this game's notes."),
    promptPaste({
      label: "the notes",
      getPrompt: async () => (await fetchPrompt()).prompt,
      saveAnswer: (value) => send("/api/notes/save", { method: "POST", body: JSON.stringify({ gameId: id, text: value }) }),
      onSaved: (warnings) => {
        const done = () => (typeof onSaved === "function" ? onSaved() : window.location.reload());
        if (!warnings.length) done();
        else host.append(el("button", { class: "btn", type: "button", onclick: done }, "Show the notes")); // saved with problems: read them first
      },
      extra: [where],
    }),
  );
  return host;
}
