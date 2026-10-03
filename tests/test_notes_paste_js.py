"""Public release Phase 6 in the fake browser (tests/fakedom.py): the copy-and-paste notes control. Copying
falls back to a text box when the page has no clipboard (plain HTTP), the check draws a preview with its
warnings and never prints undefined, null or NaN, Save waits for a passing check of the same text, and a
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

const GOOD = {
  ok: true, error: null,
  warnings: ["The answer is for game 5, not this game (526001015). Saving puts it on this game."],
  summary: { gameId: 526001015, author: "Chat", sections: ["Coaching matchup", null, "Key matchups"], availability: 2, availabilityRows: [{ name: "A Player", position: "WR", status: "Out" }, { name: "B Player", position: null, status: "Questionable" }, null, "junk"], visitors: { home: 1, away: NaN }, lineups: { us: 22, them: null }, schemes: { offense: "Spread", defense: null }, sources: 3 },
};

scenarios.flow = async () => {
  const { notesPaste } = await import(moduleUrl("ui/notes-paste.js"));
  let saved = 0;
  const sent = scripted({
    "/api/notes/prompt": { status: 200, body: { data: { prompt: "PROMPT FOR GAME 526001015 {shape}", gameId: 526001015 } } },
    "/api/notes/preview": { status: 200, body: { data: GOOD } },
    "/api/notes/save": (options) => (JSON.parse(options.body).text.includes("refuse") ? { status: 422, body: { errors: [{ message: "No JSON object in the answer" }] } } : { status: 200, body: { data: { ...GOOD, saved: true } } }),
  });
  const host = notesPaste({ gameId: 526001015, onSaved: () => { saved += 1; } });
  document.body.append(host);
  const buttons = host.querySelectorAll("button");
  const [copy, check, save] = buttons;
  assert.equal(text(copy), "Copy the prompt");
  copy.click();
  await flush();
  const box = host.querySelector("textarea.notes-paste__prompt");
  assert.equal(box.value, "PROMPT FOR GAME 526001015 {shape}", "no clipboard over plain HTTP: the prompt waits in a box to copy");
  assert.ok(clean("copy note", host).includes("Select the prompt below and copy it"));
  assert.equal(sent[0].url, "/api/notes/prompt?gameId=526001015");
  // an empty paste is answered here, without a request
  check.click();
  await flush();
  assert.ok(text(host).includes("Paste the chat's answer first."));
  assert.equal(sent.length, 1);
  const answer = host.querySelector("textarea.notes-paste__answer");
  answer.value = "```json\n{\"sections\": []}\n```";
  check.click();
  await flush();
  assert.deepEqual(sent[1].body, { gameId: 526001015, text: answer.value });
  const shown = clean("preview", host);
  assert.ok(shown.includes("2: Coaching matchup, Key matchups"), shown.slice(0, 300));
  assert.ok(shown.includes("1 home, 0 away") && shown.includes("22 slots for us, 0 for them") && shown.includes("Spread"));
  assert.ok(shown.includes("A Player WR · Out") && shown.includes("B Player · Questionable"));
  assert.ok(shown.includes("not this game"), "the game-number warning is shown");
  assert.equal(save.disabled, false, "a passing check enables Save");
  // editing the text after the check disables Save until it is checked again
  answer.value = answer.value + " ";
  answer.dispatchEvent(makeEvent("input", { bubbles: true }));
  assert.equal(save.disabled, true);
  check.click();
  await flush();
  save.click();
  await flush();
  assert.equal(saved, 1, "a save hands over to the page");
  assert.equal(sent[sent.length - 1].url, "/api/notes/save");
  // a refused save explains itself and can be tried again
  answer.value = "refuse this";
  answer.dispatchEvent(makeEvent("input", { bubbles: true }));
  check.click();
  await flush();
  save.click();
  await flush();
  assert.ok(text(host).includes("Not saved. No JSON object in the answer."), text(host).slice(-300));
  assert.equal(save.disabled, false);
  assert.equal(saved, 1);
};

scenarios.refused = async () => {
  const { notesPaste, previewBlock } = await import(moduleUrl("ui/notes-paste.js"));
  scripted({ "/api/notes/preview": { status: 200, body: { data: { ok: false, error: "No JSON object in the answer.", warnings: [null, 7], summary: null } } } });
  const host = notesPaste({ gameId: "526001015" });
  document.body.append(host);
  host.querySelector("textarea.notes-paste__answer").value = "hello";
  host.querySelectorAll("button")[1].click();
  await flush();
  const t = clean("refused", host);
  assert.ok(t.includes("Not saved. No JSON object in the answer."));
  assert.equal(host.querySelectorAll("button")[2].disabled, true, "Save stays off");
  assert.equal(notesPaste({ gameId: null }).childNodes.length, 0, "no game: nothing to paste into");
  clean("junk preview", previewBlock({ ok: true, summary: { sections: "x", visitors: null, lineups: 5, schemes: [], sources: "many", availabilityRows: {} }, warnings: "x" }));
  clean("empty preview", previewBlock(null));
};
"""

NAMES = ["flow", "refused"]


@needs_node
@pytest.mark.parametrize("scenario", NAMES)
def test_notes_paste_in_a_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)


def test_the_program_offers_paste_and_claude_code_only_where_found() -> None:
    program = (STATIC_JS / "views" / "program.js").read_text(encoding="utf-8")
    assert "notesPaste({ gameId: data.game?.gameId })" in program
    assert 'status?.commandFound !== true && !status?.running' in program  # the tool's button hides where the command is missing
