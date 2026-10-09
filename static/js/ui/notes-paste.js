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
//   notesPaste({ gameId, onSaved })  the element. onSaved() runs after a save (default: reload the page).

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

export function notesPaste({ gameId, onSaved } = {}) {
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
  const pathButton = el("button", { class: "notes-paste__path", type: "button", title: "Copy where this game's notes file lives" }, el("code", {}, `data/notes/${id}.json`), el("span", { class: "notes-paste__copy" }, "Copy"));
  const pathNote = el("span", { class: "note", role: "status" }, "");
  pathButton.addEventListener("click", async () => {
    try {
      if (!fullPath) await fetchPrompt();
    } catch {
      // the short path below still copies
    }
    const path = fullPath || `data/notes/${id}.json`;
    pathNote.textContent = (await copyText(path)) ? "Copied the notes file's location." : `The location is ${path}`;
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
      extra: [pathButton, pathNote],
    }),
  );
  return host;
}
