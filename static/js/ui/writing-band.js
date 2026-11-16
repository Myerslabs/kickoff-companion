// What Claude Code wrote (P4): one band that loads its piece (/api/writing/<kind>/<key>), draws it when it is there, and
// otherwise says when the schedule writes it, with Write it now where Claude Code is on the server. The run takes a few
// minutes; the band asks every few seconds while it goes and draws the piece once it is saved.
//
//   writingBand({ id, title, kind, key, when, draw, lead, summary, season })   season: a past season's piece, read only (R2);
//                         draw(written) returns the body; `when` says when the
//                         schedule writes it; lead() what shows above it either way (Getting there's stadium and map link,
//                         ENH-15); summary(written) the head's line once written; a record `shipped` with the app says so
//   bullets(list), paragraphs(list), sourcesLine(list)  the pieces' common parts

import { fetchJson } from "../views/common.js";
import { el, text } from "./dom.js";
import { prose } from "./prose.js";
import { band, note } from "./states.js";
import { getClaudeCode } from "./claude-get.js";

const POLL_MS = 5000;
const POLL_FOR_MS = 25 * 60 * 1000;

export function bullets(list) {
  const rows = (Array.isArray(list) ? list : []).filter((line) => typeof line === "string" && line.trim());
  return rows.length ? el("ul", { class: "writing__list" }, rows.map((line) => el("li", {}, line))) : null;
}

/** The piece's paragraphs, not a wall of text (owner 2026-11-07): split, listed and led by ui/prose.js; `names` and `onName`
 *  make the players the program knows a tap to the card. */
export function paragraphs(list, { names = null, onName = null, lead = true } = {}) {
  const rows = (Array.isArray(list) ? list : []).filter((p) => typeof p === "string" && p.trim());
  return rows.length ? prose(rows, { names, onName, lead }) : [];
}

export function sourcesLine(list) {
  const rows = (Array.isArray(list) ? list : []).filter((s) => s && typeof s === "object" && typeof s.label === "string" && s.label);
  if (!rows.length) return null;
  return el("p", { class: "note writing__sources" }, "Sources: ", rows.flatMap((s, i) => [i ? ", " : "", typeof s.url === "string" && /^https:\/\//.test(s.url) ? el("a", { href: s.url, target: "_blank", rel: "noopener" }, s.label) : s.label]));
}

function byline(written) {
  const when = typeof written?.writtenAt === "string" ? new Date(written.writtenAt) : null;
  if (written?.shipped === true) {
    const checked = when && !Number.isNaN(when.getTime()) ? when.toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" }) : null;
    return el("p", { class: "note writing__by" }, `Researched for the app${checked ? ` on ${checked}` : ""}; Claude Code on the server replaces it with its own.`);
  }
  const day = when && !Number.isNaN(when.getTime()) ? when.toLocaleString([], { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : null;
  return el("p", { class: "note writing__by" }, `Written by Claude Code on the server${day ? `, ${day}` : ""}.`);
}

function leadOf(lead) {
  if (typeof lead !== "function") return null;
  try {
    return lead();
  } catch (error) {
    console.error("A writing band's lead could not be drawn; the piece stays.", error);
    return null;
  }
}

export function writingBand({ id, title, kind, key, when = "", draw, lead = null, summary = null, season = null }) {
  const host = el("div", { class: "writing-host" }, band({ id, title, collapsible: true, foldable: true, state: { status: "loading" }, skeleton: () => el("div", { class: "skel skel--block" }) }));
  if (!kind || key === null || key === undefined || key === "") return null;
  const base = `/api/writing/${encodeURIComponent(kind)}/${encodeURIComponent(String(key))}`;
  const past = Number.isInteger(season) ? season : null; // rollover R2: that season's piece, nothing to write now
  const url = past ? `${base}?season=${past}` : base;
  let stopAt = 0;

  async function load() {
    let data = null;
    try {
      data = (await fetchJson(url))?.data || null;
    } catch (error) {
      host.replaceChildren(band({ id, title, collapsible: true, foldable: true, state: { status: "error", message: `${text(error?.message || "no answer")}.` } }));
      return;
    }
    const written = data?.written && typeof data.written === "object" ? data.written : null;
    if (written) {
      const said = typeof summary === "function" ? summary(written) : written.shipped === true ? "researched for the app" : "by Claude Code";
      host.replaceChildren(band({ id, title, collapsible: true, foldable: true, summary: said, state: { status: "ready" }, body: () => el("div", { class: "writing" }, leadOf(lead), draw(written), byline(written)) }));
      return;
    }
    const said = el("span", { class: "note", role: "status" }, data?.running ? "Writing now; it takes a few minutes." : "");
    if (past) {
      host.replaceChildren(band({ id, title, collapsible: true, foldable: true, summary: "not written", state: { status: "ready" }, body: () => el("div", { class: "writing writing--empty" }, leadOf(lead), note(`Not written for this game in ${past}.`)) }));
      return;
    }
    const go = data?.commandFound === true && !data?.running ? el("button", { class: "btn", type: "button", onclick: async () => {
      go.disabled = true;
      said.textContent = "Starting…";
      try {
        const response = await fetch(`${base}/run`, { method: "POST", cache: "no-store", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ confirm: true }) });
        const body = await response.json().catch(() => null);
        if (!response.ok) throw new Error(body?.errors?.[0]?.message || `The server answered ${response.status}`);
        said.textContent = "Writing now; it takes a few minutes.";
        stopAt = Date.now() + POLL_FOR_MS;
        setTimeout(again, POLL_MS);
      } catch (error) {
        said.textContent = `Not started: ${text(error?.message)}.`;
        go.disabled = false;
      }
    } }, "Write it now") : null;
    host.replaceChildren(band({ id, title, collapsible: true, foldable: true, summary: "not written yet", state: { status: "ready" }, body: () => el("div", { class: "writing writing--empty" }, leadOf(lead), note(when || "Not written yet."), go || said.textContent ? el("p", {}, go, " ", said) : null, data && data.commandFound === false ? getClaudeCode({ compact: true }) : null) }));
    if (data?.running && !stopAt) {
      stopAt = Date.now() + POLL_FOR_MS;
      setTimeout(again, POLL_MS);
    }
  }

  function again() {
    if (!host.isConnected && host.parentNode === null) return; // the page moved on
    if (Date.now() > stopAt) return;
    load().then(() => {
      if (host.querySelector(".writing")) return;
      setTimeout(again, POLL_MS);
    });
  }

  load();
  return host;
}
