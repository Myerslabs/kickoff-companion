"""Public release Phase 6, Phase 17 #12, Phase 19, in the fake browser (tests/fakedom.py): the copy-and-paste notes control.
The prompt is copied and never shown (owner, 2026-10-08), the path button copies the notes file's real location, ONE
Paste button reads the clipboard and saves (no text field), a page that may not read the clipboard (plain HTTP) opens one
small box that saves the moment text is pasted into it, problems are listed after (never undefined, null or NaN), and a
refused save says why and lets the owner try again."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fakedom import STATIC_JS, needs_node, run_scenario

SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object Object\]/;
const text = (node) => (node ? node.textContent : "");
const clean = (label, node) => {
  const t = text(node);
  assert.ok(!RAW.test(t), `${label} printed ${JSON.stringify(t.slice(0, 400))}`);
  return t;
};
const flush = async () => { for (let i = 0; i < 6; i += 1) await new Promise((resolve) => setImmediate(resolve)); };

function scripted(answers) {
  const sent = [];
  globalThis.fetch = async (url, options = {}) => {
    sent.push({ url: String(url), method: options.method || "GET", body: options.body ? JSON.parse(options.body) : null });
    const key = Object.keys(answers).find((prefix) => String(url).startsWith(prefix));
    const answer = typeof answers[key] === "function" ? answers[key](options) : answers[key];
    if (!answer) return { ok: false, status: 404, json: async () => ({ errors: [{ message: "no route" }] }) };
    return { ok: answer.status < 300, status: answer.status, json: async () => answer.body };
  };
  return sent;
}

function clipboard(initial = "") {
  const clip = { text: initial, wrote: null, canRead: true, canWrite: true };
  Object.defineProperty(globalThis, "navigator", { configurable: true, value: { clipboard: {
    readText: async () => { if (!clip.canRead) throw new Error("denied"); return clip.text; },
    writeText: async (value) => { if (!clip.canWrite) throw new Error("denied"); clip.wrote = value; },
  } } });
  return clip;
}

const GOOD = {
  ok: true, error: null,
  warnings: ["The answer is for game 5, not this game (526001015). Saving puts it on this game."],
  summary: { gameId: 526001015, author: "Chat", sections: ["Coaching matchup"], availability: 2 },
};

const visibleBoxes = (host) => host.querySelectorAll("textarea").filter((b) => b.getAttribute("hidden") === null);

scenarios.flow = async () => {
  const { notesPaste } = await import(moduleUrl("ui/notes-paste.js"));
  let saved = 0;
  const sent = scripted({
    "/api/notes/prompt": { status: 200, body: { data: { prompt: "PROMPT FOR GAME 526001015 {shape}", gameId: 526001015, path: "C:/Kickoff/data/notes/526001015.json" } } },
    "/api/notes/save": (options) => {
      const body = JSON.parse(options.body).text;
      if (body.includes("refuse")) return { status: 422, body: { errors: [{ message: "No JSON object in the answer" }] } };
      return { status: 200, body: { data: { ...GOOD, warnings: body.includes("clean") ? [] : GOOD.warnings, saved: true } } };
    },
  });
  const clip = clipboard();
  const host = notesPaste({ gameId: 526001015, onSaved: () => { saved += 1; } });
  document.body.append(host);
  const [copy, paste, pathButton] = host.querySelectorAll("button");
  assert.equal(text(copy), "Copy the prompt");
  assert.equal(text(paste), "Paste the answer");
  assert.ok(text(pathButton).includes("data/notes/526001015.json"));
  assert.equal(visibleBoxes(host).length, 0, "no text field and no prompt on show");
  // copy: the prompt goes to the clipboard and is never shown
  copy.click();
  await flush();
  assert.equal(clip.wrote, "PROMPT FOR GAME 526001015 {shape}");
  assert.equal(visibleBoxes(host).length, 0);
  assert.ok(!text(host).includes("PROMPT FOR GAME"), "the prompt text is not on the page");
  assert.ok(clean("copied", host).includes("Copied."));
  assert.equal(sent[0].url, "/api/notes/prompt?gameId=526001015");
  // the path button copies the file's real location from the server
  pathButton.click();
  await flush();
  assert.ok(text(host).includes("Copied the notes file's location."));
  // an empty clipboard is answered here, without a save request
  const count = sent.length;
  paste.click();
  await flush();
  assert.ok(text(host).includes("There is nothing to paste yet"));
  assert.equal(sent.length, count);
  // one tap: the clipboard's answer is read and saved; problems are listed before the page reloads
  clip.text = "```json\n{\"sections\": []}\n```";
  paste.click();
  await flush();
  assert.deepEqual(sent[sent.length - 1].body, { gameId: 526001015, text: clip.text });
  const shown = clean("warned save", host);
  assert.ok(shown.includes("Saved, with 1 note.") && shown.includes("not this game"), shown.slice(-300));
  assert.equal(saved, 0, "the reader sees the problems first");
  host.querySelectorAll("button").find((b) => text(b) === "Show the notes").click();
  assert.equal(saved, 1);
  // a clean answer saves and hands over at once
  clip.text = "clean answer";
  paste.click();
  await flush();
  assert.equal(saved, 2);
  // a refused save explains itself and can be tried again
  clip.text = "refuse this";
  paste.click();
  await flush();
  assert.ok(text(host).includes("Not saved. No JSON object in the answer"), text(host).slice(-300));
  assert.equal(saved, 2);
  assert.equal(visibleBoxes(host).length, 0);
};

scenarios.nobrowserclipboard = async () => {
  const { notesPaste } = await import(moduleUrl("ui/notes-paste.js"));
  const sent = scripted({
    "/api/notes/prompt": { status: 200, body: { data: { prompt: "THE PROMPT", gameId: 526001015, path: "C:/x.json" } } },
    "/api/notes/save": { status: 200, body: { data: { ...GOOD, warnings: [], saved: true } } },
  });
  const clip = clipboard();
  clip.canRead = false;
  clip.canWrite = false;
  let saved = 0;
  const host = notesPaste({ gameId: 526001015, onSaved: () => { saved += 1; } });
  document.body.append(host);
  const [copy, paste] = host.querySelectorAll("button");
  // plain HTTP, nothing can be copied by script: only then does the prompt appear, selected, to copy by hand
  copy.click();
  await flush();
  const boxes = visibleBoxes(host);
  assert.equal(boxes.length, 1);
  assert.equal(boxes[0].value, "THE PROMPT");
  assert.ok(text(host).includes("The prompt is selected below: copy it by hand."));
  // paste cannot read the clipboard: ONE small box opens, and a paste into it saves with no further tap
  paste.click();
  await flush();
  const pasteBox = visibleBoxes(host).find((b) => b.getAttribute("readonly") === null);
  assert.ok(pasteBox && text(host).includes("Press and hold in the box"));
  const before = sent.filter((s) => s.method === "POST").length;
  pasteBox.dispatchEvent({ type: "paste", clipboardData: { getData: () => "the chat's whole answer" }, preventDefault() {} });
  await flush();
  assert.equal(sent.filter((s) => s.method === "POST").length, before + 1);
  assert.equal(saved, 1);
  assert.ok(clean("after", host).includes("Saved."));
};

scenarios.desktopkey = async () => {
  const { notesPaste } = await import(moduleUrl("ui/notes-paste.js"));
  const sent = scripted({
    "/api/notes/prompt": { status: 200, body: { data: { prompt: "P", gameId: 526001015, path: "C:/x.json" } } },
    "/api/notes/save": { status: 200, body: { data: { ...GOOD, warnings: [], saved: true } } },
  });
  const clip = clipboard();
  clip.canRead = false; // plain HTTP: the page may not read the clipboard
  globalThis.matchMedia = (query) => ({ matches: query === "(pointer: fine)" }); // a desktop with a mouse and a keyboard
  let saved = 0;
  const host = notesPaste({ gameId: 526001015, onSaved: () => { saved += 1; } });
  document.body.append(host);
  const [, paste] = host.querySelectorAll("button");
  paste.click();
  await flush();
  assert.equal(visibleBoxes(host).length, 0, "no text box on a desktop");
  assert.ok(text(host).includes("Press Ctrl+V now"));
  const before = sent.filter((s) => s.method === "POST").length;
  document.dispatchEvent({ type: "paste", clipboardData: { getData: () => "the chat's whole answer" }, preventDefault() {} });
  await flush();
  assert.equal(sent.filter((s) => s.method === "POST").length, before + 1, "the paste keystroke saved it");
  assert.equal(saved, 1);
  // a touch device (no fine pointer) still gets the one small box
  globalThis.matchMedia = () => ({ matches: false });
  const touch = notesPaste({ gameId: 526001015 });
  document.body.append(touch);
  touch.querySelectorAll("button")[1].click();
  await flush();
  assert.equal(visibleBoxes(touch).length, 1);
  delete globalThis.matchMedia;
};

scenarios.refused = async () => {
  const { notesPaste } = await import(moduleUrl("ui/notes-paste.js"));
  scripted({ "/api/notes/save": { status: 500, body: null } });
  const clip = clipboard("hello");
  const host = notesPaste({ gameId: "526001015" });
  document.body.append(host);
  host.querySelectorAll("button")[1].click();
  await flush();
  const t = clean("refused", host);
  assert.ok(t.includes("Not saved. The server answered 500."), t);
  assert.equal(clip.text, "hello");
  assert.equal(notesPaste({ gameId: null }).childNodes.length, 0, "no game: nothing to paste into");
};
"""

NAMES = ["flow", "nobrowserclipboard", "desktopkey", "refused"]


@needs_node
@pytest.mark.parametrize("scenario", NAMES)
def test_notes_paste_in_a_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)


def test_the_program_offers_paste_and_claude_code_only_where_found() -> None:
    program = (STATIC_JS / "views" / "program.js").read_text(encoding="utf-8")
    assert "notesPaste({ gameId: data.game?.gameId })" in program
    assert 'status?.commandFound !== true && !status?.running' in program  # the tool's button hides where the command is missing
