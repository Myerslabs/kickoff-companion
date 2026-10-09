// Editorial content written outside the app (a scheduled Claude task drops a notes file
// per game) and the availability table for the injury report. Both always show who wrote
// it, when, and from which sources, and both have an honest "not written yet" state.

import { el, fmtDateTime, text } from "./dom.js";
import { statTable } from "./stat-table.js";

/**
 * editorial({ byline: {author, writtenAt}, sources: [{label, url}], sections: [{heading, paragraphs}] })
 */
/** Only the object rows of a list (a hand-written notes file can hold anything). */
function list(value) {
  return Array.isArray(value) ? value.filter((row) => row && typeof row === "object" && !Array.isArray(row)) : [];
}

export function editorial({ byline = {}, sources = [], sections = [] } = {}) {
  return el(
    "div",
    { class: "editorial" },
    el(
      "div",
      { class: "editorial__byline" },
      el("span", {}, `Written by ${text(byline?.author)}`),
      el("span", {}, byline?.writtenAt ? fmtDateTime(byline.writtenAt) : "–"),
    ),
    list(sections).map((section) =>
      el(
        "div",
        {},
        typeof section.heading === "string" && section.heading.trim() ? el("h3", {}, section.heading.trim()) : null,
        (Array.isArray(section.paragraphs) ? section.paragraphs : []).filter((para) => typeof para === "string" && para.trim()).map((para) => el("p", {}, para)),
      ),
    ),
    list(sources).length
      ? el(
          "ul",
          { class: "editorial__sources" },
          list(sources).map((source) => el("li", {}, typeof source.url === "string" && /^https?:\/\//.test(source.url) ? el("a", { href: source.url, target: "_blank", rel: "noopener" }, text(source.label)) : text(source.label))),
        )
      : null,
  );
}

export function editorialSkeleton() {
  return el("div", { class: "editorial" }, el("div", { class: "skel" }), el("div", { class: "skel skel--block" }), el("div", { class: "skel skel--block" }));
}

const STATUS_CLASS = { out: "out", doubtful: "doubtful", questionable: "questionable", probable: "probable", available: "available" };

/**
 * availabilityTable({ rows: [{name, position, status, note}], source, updatedAt })
 * status: out | doubtful | questionable | probable | available
 */
export function availabilityTable({ rows = [], source, updatedAt }) {
  const table = statTable({
    compact: true,
    columns: [
      { key: "name", label: "Player", kind: "text", sub: "position" },
      { key: "statusText", label: "Status", kind: "text", sortable: false },
      { key: "note", label: "Note", kind: "text", sortable: false },
    ],
    rows: rows.map((row) => ({ ...row, statusText: typeof row.status === "string" && row.status.trim() ? row.status.trim() : "Not reported" })), // Phase 17: a row with no status is kept
  });
  for (const cell of table.querySelectorAll("tbody tr")) {
    const statusCell = cell.children[1];
    const row = rows[[...cell.parentNode.children].indexOf(cell)];
    const cls = STATUS_CLASS[String(row?.status || "").toLowerCase()];
    if (statusCell && cls) statusCell.classList.add("avail", `avail--${cls}`);
  }
  return el(
    "div",
    {},
    table,
    source || updatedAt
      ? el("p", { class: "note" }, [source ? `Source: ${text(source)}.` : null, updatedAt ? ` Updated ${fmtDateTime(updatedAt)}.` : null].filter(Boolean).join(""))
      : null,
  );
}
