// Copy a prompt, paste the answer, done (Phase 19, owner 2026-10-08: "I don't want the prompt text to be visible", "I want
// the paste button to just paste and save and not open the text field"). Every prompt in the app works the same way:
//
//   [Copy the prompt]   the server writes the prompt, the button puts it on the clipboard; the text is never shown
//   [Paste the answer]  reads the clipboard, checks the answer and saves it in one tap
//
// Two browser limits are handled without the owner noticing unless they bite:
//   - Reading the clipboard needs a secure page (https or localhost). Where the button cannot read it, a desktop browser
//     is told to press Ctrl+V and the page saves what arrives, with no box. A tablet at the plain-HTTP home address
//     (no keyboard) shows ONE small box instead: press and hold, choose Paste, and it saves by itself.
//   - Writing the clipboard has the same limit; the fallback copies through a hidden box. Only if that also fails does
//     the prompt appear, selected, so it can still be copied by hand.
//
//   promptPaste({ label, getPrompt, saveAnswer, onSaved, extra }) -> element
//     getPrompt()        async, the prompt text
//     saveAnswer(text)   async, saves; resolves { warnings: [string] } or throws an Error whose message is shown
//     onSaved(warnings)  runs after a save (default: nothing)
//     extra              more nodes for the button row (the notes file's location chip, a Claude Code button)
//   copyHidden(value), readClipboard()   the two clipboard helpers (exported for the tests and other buttons)

import { el } from "./dom.js";
import { note } from "./states.js";

const MAX_CHARS = 400000;

/** Copy text without showing it. True when it worked. */
export async function copyHidden(value) {
  try {
    if (globalThis.navigator?.clipboard?.writeText && globalThis.isSecureContext !== false) {
      await navigator.clipboard.writeText(value);
      return true;
    }
  } catch {
    // fall through to the hidden box
  }
  try {
    const box = document.createElement("textarea");
    box.value = value;
    box.setAttribute("readonly", "");
    box.style.position = "fixed";
    box.style.opacity = "0";
    box.style.pointerEvents = "none";
    document.body.append(box);
    box.focus();
    box.select();
    box.setSelectionRange?.(0, value.length);
    const done = document.execCommand?.("copy") === true;
    box.remove();
    return done;
  } catch {
    return false;
  }
}

/** The clipboard's text, or null when this page may not read it (plain HTTP, or the browser said no). */
export async function readClipboard() {
  try {
    if (globalThis.navigator?.clipboard?.readText && globalThis.isSecureContext !== false) {
      const value = await navigator.clipboard.readText();
      return typeof value === "string" ? value : "";
    }
  } catch {
    // refused or unsupported: the paste box takes over
  }
  return null;
}

/** A desktop with a mouse and a keyboard (Ctrl+V works), as opposed to a tablet or phone. False where the browser cannot say. */
function hasKeyboard() {
  try {
    return globalThis.matchMedia?.("(pointer: fine)")?.matches === true;
  } catch {
    return false;
  }
}

const reveal = (node) => node.removeAttribute("hidden");
const hide = (node) => node.setAttribute("hidden", "");

export function promptPaste({ label = "the answer", getPrompt, saveAnswer, onSaved, extra = [] } = {}) {
  const status = el("p", { class: "note prompt-paste__status", role: "status" }, "");
  const result = el("div", { class: "prompt-paste__result", "aria-live": "polite" });
  const copyBox = el("textarea", { class: "input prompt-paste__fallback", readonly: true, rows: "5", hidden: true, "aria-label": "The prompt, to copy by hand" });
  const pasteBox = el("textarea", { class: "input prompt-paste__fallback", rows: "2", hidden: true, spellcheck: "false", placeholder: "Press and hold here, choose Paste", "aria-label": `Paste ${label} here` });
  let busy = false;

  const say = (message) => {
    status.textContent = message;
  };
  const show = (node) => result.replaceChildren(...(node ? [node] : []));

  async function submit(value) {
    if (busy) return;
    const answer = typeof value === "string" ? value : "";
    if (!answer.trim()) {
      show(note("There is nothing to paste yet. Copy the chat's whole answer first.", { kind: "error" }));
      return;
    }
    if (answer.length > MAX_CHARS) {
      show(note("That is far longer than an answer. Copy only the chat's answer.", { kind: "error" }));
      return;
    }
    busy = true;
    say("Checking and saving…");
    show(null);
    try {
      const data = await saveAnswer(answer);
      const warnings = (Array.isArray(data?.warnings) ? data.warnings : []).filter((w) => typeof w === "string" && w);
      hide(pasteBox);
      pasteBox.value = "";
      if (warnings.length) {
        say("");
        show(el("div", { class: "prompt-paste__warn", role: "status" }, el("p", {}, el("strong", {}, `Saved, with ${warnings.length} note${warnings.length === 1 ? "" : "s"}. `), "Anything the chat could not fill stays empty."), el("ul", {}, warnings.map((w) => el("li", {}, w)))));
      } else {
        say("Saved.");
      }
      if (typeof onSaved === "function") onSaved(warnings);
    } catch (error) {
      say("");
      show(note(`${error?.message || "The save failed"}.`, { kind: "error", lead: "Not saved." }));
    }
    busy = false;
  }

  const copy = el("button", { class: "btn btn--primary", type: "button" }, "Copy the prompt");
  copy.addEventListener("click", async () => {
    copy.disabled = true;
    say("Getting the prompt…");
    show(null);
    try {
      const prompt = await getPrompt();
      if (typeof prompt !== "string" || !prompt.trim()) throw new Error("The server sent an empty prompt");
      if (await copyHidden(prompt)) {
        hide(copyBox);
        say("Copied. Paste it into an AI chat that can search the web, then copy the chat's whole answer and tap Paste the answer.");
      } else {
        copyBox.value = prompt;
        reveal(copyBox);
        copyBox.focus?.();
        copyBox.select?.();
        say("This browser would not copy by itself. The prompt is selected below: copy it by hand.");
      }
    } catch (error) {
      say(`No prompt: ${error?.message || "the request failed"}.`);
    }
    copy.disabled = false;
  });

  const paste = el("button", { class: "btn", type: "button" }, "Paste the answer");
  paste.addEventListener("click", async () => {
    const value = await readClipboard();
    if (value === null) {
      if (hasKeyboard()) {
        // A desktop browser: no box at all. The page waits for the paste keystroke and saves what arrives.
        awaitPasteKey();
        say("Press Ctrl+V now (Cmd+V on a Mac). The answer saves by itself.");
        return;
      }
      reveal(pasteBox);
      pasteBox.focus?.();
      say("This browser will not let the app read the clipboard here. Press and hold in the box, choose Paste, and it saves by itself.");
      return;
    }
    await submit(value);
  });

  // Reading the clipboard needs a secure page, but a paste keystroke is always allowed: listen for one, once, for half a minute.
  let waiting = null;
  function awaitPasteKey() {
    if (waiting) waiting.stop();
    const onPaste = (event) => {
      const pasted = event.clipboardData?.getData?.("text");
      if (typeof pasted !== "string" || !pasted.trim()) return;
      event.preventDefault?.();
      stop();
      submit(pasted);
    };
    const timer = setTimeout(() => {
      stop();
      say("No paste arrived. Tap Paste the answer and try again.");
    }, 30000);
    function stop() {
      clearTimeout(timer);
      document.removeEventListener("paste", onPaste, true);
      waiting = null;
    }
    document.addEventListener("paste", onPaste, true);
    waiting = { stop };
  }

  // The fallback box saves the moment text lands in it (a paste event, or an input that brings a whole answer at once).
  pasteBox.addEventListener("paste", (event) => {
    const pasted = event.clipboardData?.getData?.("text");
    if (typeof pasted === "string" && pasted.trim()) {
      event.preventDefault?.();
      submit(pasted);
    }
  });
  let timer = null;
  pasteBox.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(() => {
      if (pasteBox.value.trim().length > 40) submit(pasteBox.value);
    }, 400);
  });

  return el("div", { class: "prompt-paste" }, el("div", { class: "prompt-paste__row" }, copy, paste, ...extra), status, copyBox, pasteBox, result);
}
