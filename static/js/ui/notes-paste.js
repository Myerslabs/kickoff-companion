// Notes by copy and paste (public release Phase 6). Two steps on the Game program's notes band:
//   1. Copy the prompt the server writes for this game, and paste it into any AI chat that can search the web.
//   2. Paste the chat's answer back, check it (a preview of what is in it, with warnings), then save it.
// The server reads the answer leniently (code fences and chatter are fine, a bad row is skipped) and saves
// data/notes/<game_id>.json; the page then reloads with the notes. Nothing here calls an AI.
//
// Copying works over plain HTTP too: the Clipboard API needs a secure page, so the fallback selects the
// prompt in a text box and copies with execCommand, and the box stays open for a manual copy if both fail.
//
//   notesPaste({ gameId, onSaved })  the element. onSaved() runs after a save (default: reload the page).

import { el, isNum, replaceWith, text } from "./dom.js";
import { note } from "./states.js";

const MAX_CHARS = 400000;

function obj(value) {
  return value && typeof value === "object" ? value : {};
}

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

/** What a checked answer holds, in plain words, with its warnings. */
export function previewBlock(reading) {
  const r = obj(reading);
  const s = obj(r.summary);
  const sections = Array.isArray(s.sections) ? s.sections.filter((h) => typeof h === "string" && h.trim()) : [];
  const visitors = obj(s.visitors);
  const lineups = obj(s.lineups);
  const schemes = obj(s.schemes);
  const broadcast = obj(s.broadcast);
  const crew = [broadcast.playByPlay, broadcast.analyst, ...(Array.isArray(broadcast.sideline) ? broadcast.sideline : [])].filter((v) => typeof v === "string" && v.trim());
  const count = (value) => (isNum(value) ? value : 0);
  const items = [
    ["Program notes", sections.length ? `${sections.length}: ${sections.join(", ")}` : "none"],
    ["Availability", count(s.availability) ? `${count(s.availability)} player${count(s.availability) === 1 ? "" : "s"}` : "none"],
    ["Visitors", count(visitors.home) + count(visitors.away) ? `${count(visitors.home)} home, ${count(visitors.away)} away` : "none"],
    ["Depth charts", count(lineups.us) + count(lineups.them) ? `${count(lineups.us)} slot${count(lineups.us) === 1 ? "" : "s"} for us, ${count(lineups.them)} for them` : "none"],
    ["Schemes", [schemes.offense, schemes.defense].filter((v) => typeof v === "string" && v.trim()).join(" / ") || "none"],
    ["TV crew", crew.length ? `${typeof broadcast.network === "string" && broadcast.network.trim() ? `${broadcast.network.trim()}: ` : ""}${crew.join(", ")}` : "none"],
    ["Coaches", count(s.coaches) ? `${count(s.coaches)} named` : "none"],
    ["Sources", count(s.sources) ? String(count(s.sources)) : "none"],
    ["Written by", text(s.author)],
  ];
  const rows = (Array.isArray(s.availabilityRows) ? s.availabilityRows : []).filter((row) => row && typeof row === "object" && typeof row.name === "string");
  const warnings = (Array.isArray(r.warnings) ? r.warnings : []).filter((w) => typeof w === "string" && w);
  return el(
    "div",
    { class: "notes-preview" },
    typeof r.error === "string" && r.error ? note(r.error, { kind: "error", lead: "Not saved." }) : null,
    r.ok === true
      ? el("dl", { class: "facts notes-preview__facts" }, items.flatMap(([label, value]) => [el("dt", {}, label), el("dd", {}, value)]))
      : null,
    r.ok === true && rows.length
      ? el("ul", { class: "notes-preview__rows" }, rows.map((row) => el("li", {}, el("strong", {}, row.name), typeof row.position === "string" && row.position ? ` ${row.position}` : "", ` · ${text(row.status)}`)))
      : null,
    warnings.length ? el("ul", { class: "notes-preview__warnings" }, warnings.map((w) => el("li", {}, w))) : null,
  );
}

export function notesPaste({ gameId, onSaved } = {}) {
  const id = isNum(gameId) ? gameId : Number.parseInt(String(gameId ?? ""), 10);
  const host = el("div", { class: "notes-paste" });
  if (!Number.isFinite(id) || id <= 0) return host;
  const promptBox = el("textarea", { class: "input notes-paste__prompt", readonly: true, rows: "6", hidden: true, "aria-label": "The prompt for this game" });
  const copyNote = el("p", { class: "note", role: "status" }, "");
  const answer = el("textarea", { class: "input notes-paste__answer", rows: "8", spellcheck: "false", placeholder: "Paste the chat's whole answer here", "aria-label": "The AI chat's answer" });
  const preview = el("div", { "aria-live": "polite" });
  const check = el("button", { class: "btn", type: "button" }, "Check it");
  const save = el("button", { class: "btn btn--primary", type: "button", disabled: true }, "Save the notes");
  let checked = null; // the text that passed the last check

  const copy = async (button) => {
    button.disabled = true;
    copyNote.textContent = "Getting the prompt…";
    try {
      const data = await send(`/api/notes/prompt?gameId=${id}`);
      const prompt = typeof data.prompt === "string" ? data.prompt : "";
      if (!prompt) throw new Error("The server sent an empty prompt");
      const done = await copyText(prompt, promptBox);
      if (!done) {
        promptBox.value = prompt;
        promptBox.hidden = false;
      }
      copyNote.textContent = done ? "Copied. Paste it into an AI chat that can search the web, wait for the answer, then copy the whole answer." : "Select the prompt below and copy it, then paste it into an AI chat that can search the web.";
    } catch (error) {
      copyNote.textContent = `No prompt: ${error?.message || "the request failed"}.`;
    }
    button.disabled = false;
  };

  const run = async (path) => {
    const value = answer.value;
    if (!value.trim()) {
      replaceWith(preview, note("Paste the chat's answer first.", { kind: "error" }));
      return null;
    }
    if (value.length > MAX_CHARS) {
      replaceWith(preview, note("That is far longer than a notes answer. Paste only the chat's answer.", { kind: "error" }));
      return null;
    }
    return send(path, { method: "POST", body: JSON.stringify({ gameId: id, text: value }) });
  };

  check.addEventListener("click", async () => {
    check.disabled = true;
    save.disabled = true;
    try {
      const reading = await run("/api/notes/preview");
      if (reading) {
        replaceWith(preview, previewBlock(reading));
        checked = reading.ok === true ? answer.value : null;
        save.disabled = reading.ok !== true;
      }
    } catch (error) {
      replaceWith(preview, note(`${error?.message || "The check failed"}.`, { kind: "error" }));
    }
    check.disabled = false;
  });

  save.addEventListener("click", async () => {
    if (checked !== answer.value) {
      save.disabled = true;
      replaceWith(preview, note("The answer changed since the check. Check it again.", { kind: "error" }));
      return;
    }
    save.disabled = true;
    check.disabled = true;
    try {
      await run("/api/notes/save");
      replaceWith(preview, note("Saved. Loading the notes…"));
      if (typeof onSaved === "function") onSaved();
      else window.location.reload();
    } catch (error) {
      replaceWith(preview, note(`${error?.message || "The save failed"}.`, { kind: "error", lead: "Not saved." }));
      save.disabled = false;
      check.disabled = false;
    }
  });

  answer.addEventListener("input", () => {
    save.disabled = true;
    checked = null;
  });

  const copyButton = el("button", { class: "btn btn--primary", type: "button" }, "Copy the prompt");
  copyButton.addEventListener("click", () => copy(copyButton));
  host.append(
    el("div", { class: "notes-paste__step" },
      el("h4", {}, "1. Ask an AI chat"),
      el("p", { class: "note" }, "The prompt names this game and your team and asks for the notes as one block of JSON. Use any chat that can search the web."),
      el("p", {}, copyButton),
      copyNote,
      promptBox,
    ),
    el("div", { class: "notes-paste__step" },
      el("h4", {}, "2. Paste the answer"),
      answer,
      el("p", { class: "notes-paste__actions" }, check, " ", save),
      preview,
      el("p", { class: "note" }, "Saving replaces this game's notes. Anything the chat could not fill stays empty; a row it got wrong is left out."),
    ),
  );
  return host;
}
