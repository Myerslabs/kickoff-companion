// What Claude learned (FEAT-6, owner 2026-10-25: "I want claude cli to improve on itself every week"): the lessons of the weekly
// reviews, the additions to the notes instructions with their reasons (each undone with a tap, and back) and the weekly data
// check's last findings. Settings' Claude section draws it, and since wave 3 of the one-column page (owner 2026-11-01, his
// inventory: "I think I need to see this one") the Post-Game stop too.
//
//   learnedBand({ id })   the band, loading its own answers

import { el, fmtDate, text } from "./dom.js";
import { band, subhead } from "./states.js";
import { fetchJson } from "../views/common.js";

export function learnedBand({ id = "settings-learned" } = {}) {
  // FEAT-6 (owner 2026-10-25: "I want claude cli to improve on itself every week"): what the weekly review learned, the
  // additions it made to the notes instructions with their reasons (each one undone with a tap, and back), and the
  // weekly data check's last findings (ENH-29)
  const slot = el("div", {}, el("p", { class: "note" }, "Checking…"));
  async function draw() {
    let data = {};
    let check = null;
    try {
      data = (await fetchJson("/api/claude/lessons"))?.data || {};
      check = (await fetchJson("/api/writing/datacheck/latest"))?.data?.written || null;
    } catch (error) {
      slot.replaceChildren(el("p", { class: "note" }, `Could not read what Claude learned: ${text(error?.message || "no answer")}.`));
      return;
    }
    const lessons = (Array.isArray(data.lessons) ? data.lessons : []).filter((r) => r && typeof r.text === "string").slice(-12).reverse();
    const additions = (Array.isArray(data.additions) ? data.additions : []).filter((r) => r && typeof r.text === "string" && typeof r.id === "string").reverse();
    const said = el("p", { class: "note", role: "status" }, "");
    const flip = (row) => el("button", { class: "btn btn--quiet", type: "button", onclick: async (event) => {
      event.currentTarget.disabled = true;
      try {
        const response = await fetch(`/api/claude/additions/${encodeURIComponent(row.id)}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ active: row.active === false }) });
        if (!response.ok) throw new Error(`The server answered ${response.status}`);
        said.textContent = row.active === false ? "Brought back: the next notes run follows it again." : "Undone: the next notes run leaves it out.";
        draw();
      } catch (error) {
        said.textContent = `Not changed: ${text(error?.message)}.`;
      }
    } }, row.active === false ? "Bring it back" : "Undo");
    const findings = (Array.isArray(check?.findings) ? check.findings : []).filter((f) => f && typeof f.subject === "string");
    slot.replaceChildren(...[
      lessons.length
        ? el("div", {}, subhead("Lessons from the weekly reviews"), el("ul", { class: "writing__list" }, lessons.map((r) => el("li", {}, r.text, typeof r.at === "string" ? el("span", { class: "note" }, ` (${fmtDate(r.at, "short")})`) : null))))
        : el("p", { class: "note" }, "No lessons yet: the weekly review runs the morning after each of our games and compares the notes with the box score."),
      additions.length
        ? el("div", {}, subhead("Additions to the notes instructions"), el("ul", { class: "writing__list" }, additions.map((r) => el("li", { class: r.active === false ? "is-off" : null }, el("b", {}, r.active === false ? "Undone: " : ""), r.text, typeof r.reason === "string" && r.reason ? el("span", { class: "note" }, ` Why: ${r.reason}`) : null, " ", flip(r)))))
        : null,
      said,
      check
        ? el("div", {}, subhead("The weekly data check"), findings.length
          ? el("ul", { class: "writing__list" }, findings.map((f) => el("li", {}, el("b", {}, `${f.subject}: `), `the app says ${text(f.appSays)}, the web says ${text(f.webSays)}`, typeof f.source === "string" && /^https:\/\//.test(f.source) ? [" (", el("a", { href: f.source, target: "_blank", rel: "noopener" }, "source"), ")"] : null)))
          : el("p", { class: "note" }, `Nothing out of date in the last check (${fmtDate(check.writtenAt, "short")}).`))
        : null,
    ].filter(Boolean));
  }
  draw();
  return band({ id, title: "What Claude learned", collapsible: false, summary: "", state: { status: "ready" }, body: () => slot });
}
