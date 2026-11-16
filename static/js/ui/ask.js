// Ask about this page (FEAT-12): a question about the page open goes to Claude Code on the server with the page's own
// text (what the reader sees, up to 30,000 characters), and the answer comes back here in plain words. One question at a
// time; the sheet asks every few seconds until the answer is in. The host's: a guest's sheet says so.
//
//   openAsk({ route })   the sheet
//   pageText(root)       the visible text of the page, for the question (exported for the tests)

import { el, text } from "./dom.js";
import { openSheet } from "./remote.js";

const POLL_MS = 3000;
const POLL_FOR_MS = 7 * 60 * 1000;
const MAX_PAGE = 30000;

export function pageText(root = typeof document !== "undefined" ? document.querySelector("main") : null) {
  const words = typeof root?.innerText === "string" ? root.innerText : typeof root?.textContent === "string" ? root.textContent : "";
  return words.replace(/[ \t]+\n/g, "\n").replace(/\n{3,}/g, "\n\n").trim().slice(0, MAX_PAGE);
}

function answerView(status) {
  const body = typeof status?.answer === "string" ? status.answer : "";
  return el("div", { class: "ask__answer writing" }, body.split(/\n{2,}/).filter((p) => p.trim()).map((p) => el("p", {}, p.trim())));
}

export function openAsk({ route = "" } = {}) {
  const words = el("textarea", { class: "input ask__text", rows: "3", maxlength: "500", "aria-label": "Your question", placeholder: "What does this page say about…?" });
  const said = el("p", { class: "note", role: "status", "aria-live": "polite" }, "");
  const out = el("div", { class: "ask__out" });
  const go = el("button", { type: "submit", class: "btn btn--primary" }, "Ask");
  const guest = typeof document !== "undefined" && document.body?.dataset?.role === "guest";
  let stopAt = 0;

  async function poll() {
    try {
      const response = await fetch("/api/ask", { cache: "no-store" });
      const status = (await response.json())?.data || {};
      if (status.running && Date.now() < stopAt) {
        setTimeout(poll, POLL_MS);
        return;
      }
      go.disabled = false;
      if (status.answer) {
        said.textContent = "Claude Code's answer:";
        out.replaceChildren(answerView(status));
      } else {
        said.textContent = status.error ? `No answer: ${text(status.error)}.` : "No answer came back.";
      }
    } catch (error) {
      go.disabled = false;
      said.textContent = `The server didn't answer (${text(error?.message)}).`;
    }
  }

  const form = el(
    "form",
    { class: "ask", novalidate: true, onsubmit: async (event) => {
      event.preventDefault();
      if (!words.value.trim()) {
        said.textContent = "Type a question first.";
        return;
      }
      go.disabled = true;
      out.replaceChildren();
      said.textContent = "Claude Code is reading the page…";
      try {
        const response = await fetch("/api/ask", { method: "POST", cache: "no-store", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question: words.value, route, text: pageText() }) });
        const body = await response.json().catch(() => null);
        if (!response.ok) throw new Error(body?.errors?.[0]?.message || `The server answered ${response.status}`);
        stopAt = Date.now() + POLL_FOR_MS;
        setTimeout(poll, POLL_MS);
      } catch (error) {
        go.disabled = false;
        said.textContent = `Not asked: ${text(error?.message)}.`;
      }
    } },
    el("label", { class: "ask__label" }, "A question about this page, answered by Claude Code on the server from what the page shows (and the web, when the page is not enough)."),
    words,
    el("p", {}, go),
    said,
    out,
  );
  if (guest) {
    go.disabled = true;
    said.textContent = "Only the host can ask; this device is view-only.";
  }
  return openSheet({ title: "Ask about this page", className: "ask-sheet", body: form });
}
