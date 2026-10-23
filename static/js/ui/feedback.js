// Feedback with the logs (owner 2026-10-23: "The logs should come with the feedback. I want to be able to see what was
// done when feedback was submitted."). Send feedback in the menu, for every device, guests too: a bug, an enhancement or
// a feature, the words, a name; with it go this tablet's last fifteen minutes (ui/trail.js) and, on the server, its log
// of the same time and the status snapshot (app/services/feedback.py), saved on the computer that runs the app. Then, like
// a crash reporter (owner 2026-10-23: "It seems to email it to the developers, and can attach logs if necessary... simple
// is fine"), Email it to the developer opens the sender's own mail app with the report filled in (home addresses and
// computer names taken out), Copy the report covers a device with no mail app, and the full report downloads to attach.
// Nothing goes through a service. The host's Profile, Feedback lists every report saved here.
//
//   openFeedback({ kind, text })    the Send feedback sheet, optionally filled in (an error panel's Send a report)
//   mailtoHref(mail)                the mail link of a report's { to, subject, body } (exported for the tests)
//   feedbackBand()                  the host's list in Profile, Feedback: each report, its trail, its log, Download, GitHub
//   logsLine()                      Download the logs and Copy the last 200 lines (About and help)
//   payload(form, steps, device)    the report as sent (exported for the tests)

import { getPrefs } from "../prefs.js";
import { DASH, el, fmtDateTime, text } from "./dom.js";
import { copyText } from "./notes-paste.js";
import { openSheet } from "./remote.js";
import { band, note } from "./states.js";
import { trailSteps } from "./trail.js";

export const KINDS = [
  { id: "bug", label: "Bug", ask: "What happened, and what did you expect?" },
  { id: "enhancement", label: "Enhancement", ask: "What would make it better?" },
  { id: "feature", label: "Feature", ask: "What would you like it to do?" },
];
const NAME_KEY = "feedback.name";

function savedName() {
  try {
    return localStorage.getItem(NAME_KEY) || localStorage.getItem("trivia.name") || "";
  } catch {
    return "";
  }
}

function rememberName(name) {
  try {
    if (name) localStorage.setItem(NAME_KEY, name);
  } catch {
    // no storage: asked again next time
  }
}

function device() {
  const p = getPrefs() || {};
  const w = typeof window !== "undefined" ? window : {};
  return {
    width: Number.isFinite(w.innerWidth) ? w.innerWidth : null,
    height: Number.isFinite(w.innerHeight) ? w.innerHeight : null,
    pixelRatio: Number.isFinite(w.devicePixelRatio) ? w.devicePixelRatio : null,
    browser: typeof navigator !== "undefined" ? String(navigator.userAgent || "").slice(0, 300) : null,
    role: typeof document !== "undefined" ? document.body?.dataset?.role || "host" : null,
    delaySeconds: Number.isFinite(Number(p.delaySeconds)) ? Number(p.delaySeconds) : null,
    theme: typeof p.theme === "string" ? p.theme : null,
  };
}

/** The report as sent: the kind, the words, the name, the page, the device, the trail. */
export function payload({ kind, text: words, name }, steps = trailSteps(), info = device()) {
  return {
    kind: KINDS.some((k) => k.id === kind) ? kind : "bug",
    text: String(words || "").trim().slice(0, 4000),
    name: String(name || "").trim().slice(0, 40),
    route: typeof window !== "undefined" && window.location && typeof window.location.hash === "string" ? (window.location.hash || "#").slice(0, 200) : "",
    device: Object.fromEntries(Object.entries(info || {}).filter(([, v]) => v !== null && v !== undefined)),
    trail: Array.isArray(steps) ? steps.slice(-300) : [],
  };
}

async function postJson(url, body) {
  const response = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const answer = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = answer?.errors?.[0]?.message;
    const error = new Error(typeof message === "string" && message ? message : response.status === 429 ? "Too many reports in a few minutes. Wait a little and send it again." : `The server answered ${response.status}.`);
    error.status = response.status;
    throw error;
  }
  return answer?.data;
}

const EMAIL = /^[^\s@<>"]+@[^\s@<>"]+\.[a-z]{2,}$/i;

/** mailto:<to>?subject=...&body=... for a report's mail; null without a plain address. */
export function mailtoHref(mail) {
  const to = typeof mail?.to === "string" ? mail.to.trim() : "";
  if (!EMAIL.test(to)) return null;
  const subject = encodeURIComponent(String(mail?.subject || "Kickoff Companion feedback"));
  const body = encodeURIComponent(String(mail?.body || ""));
  return `mailto:${to}?subject=${subject}&body=${body}`;
}

/** Email it, Copy the report, and the full report to attach: the developer's way in, after Send and in the host's list. */
function mailBlock(mail, { id = null, canDownload = false } = {}) {
  const href = mailtoHref(mail);
  if (!href) return null;
  const to = mail.to.trim();
  const said = el("span", { class: "note", role: "status" }, "");
  const box = el("textarea", { class: "input logs__box", readonly: true, rows: "8", hidden: true, "aria-label": "The report to copy" });
  const full = typeof mail.full === "string" && mail.full ? mail.full : String(mail.body || "");
  const copy = el("button", { type: "button", class: "btn btn--quiet", onclick: async () => {
    const copied = await copyText(`To: ${to}\nSubject: ${mail.subject || ""}\n\n${full}`, box);
    if (!copied) {
      box.value = `To: ${to}\nSubject: ${mail.subject || ""}\n\n${full}`;
      box.hidden = false;
    }
    said.textContent = copied ? " Copied: paste it into any email." : " Select the report below and copy it.";
  } }, "Copy the report");
  const zip = canDownload && id ? el("a", { class: "btn btn--quiet", href: `/api/feedback/${encodeURIComponent(id)}/zip`, download: `feedback-${id}.zip` }, "Download the full report") : null;
  return el(
    "div",
    { class: "feedback-mail" },
    el("p", { class: "feedback-report__tools" }, el("a", { class: "btn btn--primary", href, target: "_blank", rel: "noopener" }, "Email it to the developer"), copy, zip, said),
    el("p", { class: "note" }, `Your mail app opens addressed to ${to} with the report filled in: what you wrote, the last steps on this device and the log's errors, with home addresses and computer names taken out. Attach the full report if you're asked for it. No mail app? Copy the report and send it from any email.`),
    box,
  );
}

export function openFeedback({ kind: startKind = "bug", text: startText = "" } = {}) {
  let kind = KINDS.some((k) => k.id === startKind) ? startKind : "bug";
  const ask = el("label", { class: "feedback-form__ask", for: "feedback-text" }, (KINDS.find((k) => k.id === kind) || KINDS[0]).ask);
  const words = el("textarea", { id: "feedback-text", class: "input feedback-form__text", rows: "6", maxlength: "4000", "aria-describedby": "feedback-with" });
  if (typeof startText === "string" && startText) words.value = startText.slice(0, 4000);
  const name = el("input", { type: "text", class: "input feedback-form__name", maxlength: "40", value: savedName(), autocomplete: "off", "aria-label": "Your name (optional)", placeholder: "Your name (optional)" });
  const said = el("p", { class: "feedback-form__said", role: "status", "aria-live": "polite" });
  const buttons = KINDS.map((k) =>
    el(
      "button",
      {
        type: "button",
        "aria-pressed": k.id === kind ? "true" : "false",
        onclick: () => {
          kind = k.id;
          buttons.forEach((b, i) => b.setAttribute("aria-pressed", KINDS[i].id === kind ? "true" : "false"));
          ask.textContent = k.ask;
        },
      },
      k.label,
    ),
  );
  const send = el("button", { type: "submit", class: "btn btn--primary" }, "Send");
  const form = el(
    "form",
    { class: "feedback-form", novalidate: true },
    el("div", { class: "seg feedback-form__kinds", role: "group", "aria-label": "What kind" }, buttons),
    ask,
    words,
    name,
    el("p", { class: "note", id: "feedback-with" }, "With it go this device's last 15 minutes (the pages opened, what was tapped, any errors) and the app's log from the same time. It's saved on the computer running the app; next you can email it to the developer."),
    el("div", { class: "feedback-form__foot" }, send, said),
  );
  const done = (report) =>
    el(
      "div",
      { class: "feedback-done" },
      el("p", { class: "feedback-done__lead" }, "Thanks: it's saved."),
      el("p", { class: "note" }, `Saved as ${text(report?.id)} with this device's last 15 minutes and the app's log.`),
      mailBlock(report?.mail, { id: report?.id, canDownload: report?.canDownload === true }),
      el("button", { type: "button", class: "btn", onclick: () => handle.setBody(form) }, "Send another"),
    );
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const body = payload({ kind, text: words.value, name: name.value });
    if (!body.text) {
      said.textContent = "Write a line or two about it first.";
      words.focus?.();
      return;
    }
    send.disabled = true;
    said.textContent = "Sending…";
    try {
      const report = await postJson("/api/feedback", body);
      rememberName(body.name);
      words.value = "";
      said.textContent = "";
      handle.setBody(done(report));
    } catch (error) {
      said.textContent = `Not sent: ${text(error?.message || error)}`;
    } finally {
      send.disabled = false;
    }
  });
  const handle = openSheet({ title: "Send feedback", className: "feedback-sheet", body: form });
  return handle;
}

// --- the host's side ----------------------------------------------------------------------------------------------------

const KIND_WORD = Object.fromEntries(KINDS.map((k) => [k.id, k.label]));

function clock(iso) {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? DASH : d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit", second: "2-digit" });
}

function kindChip(kind) {
  return el("span", { class: `feedback-kind feedback-kind--${KIND_WORD[kind] ? kind : "bug"}` }, KIND_WORD[kind] || "Bug");
}

function who(report) {
  const name = typeof report?.name === "string" && report.name ? report.name : null;
  return [name, report?.from === "guest" ? "a guest" : report?.from === "host" ? "the host" : null].filter(Boolean).join(", ") || DASH;
}

function trailTable(steps) {
  const rows = (Array.isArray(steps) ? steps : []).filter((s) => s && typeof s === "object");
  if (!rows.length) return note("No steps came with it.");
  return el(
    "table",
    { class: "feedback-trail" },
    el("thead", {}, el("tr", {}, el("th", { scope: "col" }, "Time"), el("th", { scope: "col" }, "What"), el("th", { scope: "col" }, "Page"))),
    el(
      "tbody",
      {},
      rows.map((s) => el("tr", { class: `feedback-trail__${["page", "tap", "sheet", "error"].includes(s.kind) ? s.kind : "note"}` }, el("td", {}, clock(s.at)), el("td", {}, `${s.kind === "tap" ? "Tapped" : s.kind === "page" ? "Opened" : s.kind === "sheet" ? "Sheet" : s.kind === "error" ? "Error" : "Note"}: ${text(s.what)}`), el("td", {}, text(s.route)))),
    ),
  );
}

function reportView(report, back) {
  const id = typeof report?.id === "string" ? report.id : "";
  const screen = report?.device && Number.isFinite(report.device.width) ? `${report.device.width}×${report.device.height}` : DASH;
  return el(
    "div",
    { class: "feedback-report" },
    el("button", { type: "button", class: "btn btn--quiet", onclick: back }, "‹ All feedback"),
    el("div", { class: "feedback-report__head" }, kindChip(report?.kind), el("b", {}, fmtDateTime(report?.submittedAt)), el("span", {}, who(report))),
    el("p", { class: "feedback-report__text" }, text(report?.text)),
    el("p", { class: "note" }, `Page ${text(report?.route)} · screen ${screen} · ${text(report?.trailSteps)} steps`),
    id ? el("p", { class: "feedback-report__tools" }, el("a", { class: "btn", href: `/api/feedback/${encodeURIComponent(id)}/zip`, download: `feedback-${id}.zip` }, "Download the report")) : null,
    mailBlock(report?.mail),
    el("h3", { class: "feedback-report__h" }, "What the tablet did"),
    trailTable(report?.trail),
    el("details", { class: "feedback-report__log" }, el("summary", {}, "The server's log from the same 15 minutes"), el("pre", {}, text(report?.serverLog) || "Nothing was logged in that time.")),
  );
}

/** The host's list (Profile, Feedback). A guest is told where reports go instead. */
export function feedbackBand() {
  const host = typeof document === "undefined" || document.body?.dataset?.role !== "guest";
  const slot = el("div", { class: "feedback-list" }, note("Loading the reports…", { kind: "loading" }));
  const showList = async () => {
    try {
      const response = await fetch("/api/feedback");
      const answer = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(answer?.errors?.[0]?.message || `The server answered ${response.status}.`);
      const reports = (Array.isArray(answer?.data?.reports) ? answer.data.reports : []).filter((r) => r && typeof r.id === "string");
      slot.replaceChildren(
        logsLine(),
        reports.length
          ? el("ul", { class: "feedback-list__rows" }, reports.map((r) => el("li", {}, el("button", { type: "button", class: "feedback-row", onclick: () => open(r.id) }, kindChip(r.kind), el("span", { class: "feedback-row__words" }, el("b", {}, text(r.first) || "(no words)"), el("small", {}, `${fmtDateTime(r.submittedAt)} · ${who(r)} · ${text(r.route)}`))))))
          : note("No feedback yet. Anyone can send it from the menu: Send feedback."),
        answer?.data?.skipped ? note(`${answer.data.skipped} report folder(s) could not be read.`, { kind: "error" }) : null,
      );
    } catch (error) {
      slot.replaceChildren(note(`The reports could not be read: ${text(error?.message || error)}`, { kind: "error" }));
    }
  };
  const open = async (id) => {
    slot.replaceChildren(note("Opening the report…", { kind: "loading" }));
    try {
      const response = await fetch(`/api/feedback/${encodeURIComponent(id)}`);
      const answer = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(answer?.errors?.[0]?.message || `The server answered ${response.status}.`);
      slot.replaceChildren(reportView(answer.data, showList));
    } catch (error) {
      slot.replaceChildren(note(`The report could not be opened: ${text(error?.message || error)}`, { kind: "error" }), el("button", { type: "button", class: "btn", onclick: showList }, "‹ All feedback"));
    }
  };
  if (host) showList();
  else slot.replaceChildren(note("Reports go to the host's computer, with what this tablet did. Send one from the menu: Send feedback."));
  return band({ id: "settings-feedback", title: "Feedback", collapsible: false, state: { status: "ready" }, body: () => slot });
}

/** Download the logs, and Copy the last 200 lines (the host's About and help, the Feedback list). */
export function logsLine() {
  const said = el("span", { class: "note", role: "status" }, "");
  const box = el("textarea", { class: "input logs__box", readonly: true, rows: "6", hidden: true, "aria-label": "The log's last 200 lines" });
  const copy = el("button", { type: "button", class: "btn btn--quiet", onclick: async (event) => {
    const button = event.currentTarget;
    button.disabled = true;
    said.textContent = " Reading the log…";
    try {
      const response = await fetch("/api/logs/tail?lines=200");
      const answer = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(answer?.errors?.[0]?.message || `The server answered ${response.status}.`);
      const lines = typeof answer?.data?.text === "string" ? answer.data.text : "";
      const copied = await copyText(lines, box);
      if (!copied) {
        box.value = lines;
        box.hidden = false;
      }
      said.textContent = copied ? " Copied the last 200 lines." : " Select the lines below and copy them.";
    } catch (error) {
      said.textContent = ` ${text(error?.message || error)}`;
    } finally {
      button.disabled = false;
    }
  } }, "Copy the last 200 lines");
  return el("div", { class: "logs-line" }, el("p", {}, el("strong", {}, "The logs: "), el("a", { class: "btn", href: "/api/logs/download", download: "kickoff-logs.zip" }, "Download the logs"), " ", copy, said), el("p", { class: "note" }, "The download has every log file and the status page's facts; the CFBD key is never in them."), box);
}
