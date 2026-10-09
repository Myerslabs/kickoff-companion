// Who is looking (Phase 18.6). After a host PIN is set, every device but the server computer and the host's own signed-in
// tablet is a guest: it sees everything and changes nothing (the server refuses the writes). This module asks who the
// device is, marks the page (body[data-role]), shows a quiet "View only" line with an "I'm the host" PIN prompt, and
// greets a new guest once.
//
//   startGuestMode()          fetch /api/host, mark the page, banner and welcome as needed
//   hostStatus()              the last answer: { pinSet, isHost, serverComputer } or null

import { el } from "./dom.js";
import { fetchJson } from "../views/common.js";
import { loadInvite } from "../views/invite.js";
import { openSheet } from "./remote.js";

const WELCOME_KEY = "kickoff.guest.welcome";
let last = null;

export function hostStatus() {
  return last;
}

function seen() {
  try {
    return window.localStorage.getItem(WELCOME_KEY) === "1";
  } catch {
    return false;
  }
}

function markSeen() {
  try {
    window.localStorage.setItem(WELCOME_KEY, "1");
  } catch {
    // blocked storage: the welcome shows again next visit, which is harmless
  }
}

async function post(url, body) {
  const response = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
  let envelope = null;
  try {
    envelope = await response.json();
  } catch {
    envelope = null;
  }
  if (!response.ok) throw new Error(envelope?.errors?.[0]?.message || `The server answered ${response.status}`);
  return envelope?.data && typeof envelope.data === "object" ? envelope.data : {};
}

export function openPinSheet(onDone) {
  const said = el("p", { class: "note", role: "status" }, "");
  const input = el("input", { class: "input", type: "password", inputmode: "numeric", autocomplete: "off", maxlength: "8", "aria-label": "Host PIN", placeholder: "Host PIN" });
  let handle = null;
  const go = el("button", {
    class: "btn btn--primary", type: "button",
    onclick: async () => {
      said.textContent = "Checking…";
      try {
        await post("/api/host/login", { pin: input.value });
        handle?.close?.();
        window.location.reload();
      } catch (error) {
        said.textContent = error?.message || "That did not work.";
      }
    },
  }, "Sign in as the host");
  handle = openSheet({ title: "Host PIN", body: () => el("div", {}, el("p", {}, "Enter the host PIN to change settings from this device."), input, el("p", { class: "settings__actions" }, go), said) });
  input.focus?.();
  if (typeof onDone === "function") onDone(handle);
  return handle;
}

async function welcomeGuest() {
  if (seen()) return;
  markSeen();
  let copyUrl = null;
  try {
    copyUrl = (await loadInvite()).copyUrl;
  } catch {
    copyUrl = null;
  }
  let handle = null;
  const close = el("button", { class: "btn btn--primary", type: "button", onclick: () => handle?.close?.() }, "Got it");
  handle = openSheet({
    title: "Welcome",
    body: () => el(
      "div",
      {},
      el("p", {}, "You are watching along on someone else's game-day screen. Look at anything: the live game, the plays, the box score, the season. Only the host can change settings."),
      el("p", {}, "Want your own? This app runs on one computer at home and shows your team and your teams. Each person has their own copy with their own teams."),
      typeof copyUrl === "string" && copyUrl.startsWith("https://") ? el("p", {}, el("a", { class: "btn", href: copyUrl, target: "_blank", rel: "noopener" }, "Get your own copy")) : el("p", { class: "note" }, "Ask the host how to get a copy."),
      el("p", { class: "settings__actions" }, close),
    ),
  });
}

export async function startGuestMode() {
  try {
    const envelope = await fetchJson("/api/host");
    last = envelope?.data && typeof envelope.data === "object" ? envelope.data : null;
  } catch {
    return null; // a courtesy: without the answer the page behaves as before
  }
  if (!last) return null;
  const guest = last.pinSet === true && last.isHost !== true;
  document.body.dataset.role = guest ? "guest" : "host";
  if (guest) {
    const bar = el("div", { class: "guest-bar", role: "note" }, el("span", {}, "View only. You can look at everything; the host changes settings."), el("button", { class: "btn btn--quiet", type: "button", onclick: () => openPinSheet() }, "I'm the host"));
    document.body.prepend(bar);
    setTimeout(() => welcomeGuest(), 2500);
  }
  return last;
}
