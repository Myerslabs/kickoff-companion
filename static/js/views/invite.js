// Invite friends (Phase 18.6, owner 2026-10-08). A full-screen QR code by IP number (a phone scans it; no name lookup
// to go wrong), the address to type, what a guest can and cannot do, and a guide for watching away from home.
//
//   createInviteView({ onStatus })   the page (#invite)
//   inviteBody({ big })              the QR, address and warnings as one node (the Live sheet's sheet and the board reuse it)

import { band, note } from "../ui/states.js";
import { el } from "../ui/dom.js";
import { copyText } from "../ui/notes-paste.js";
import { errorPanel, fetchJson, poller } from "./common.js";

function obj(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

export function warningsList(warnings) {
  const list = (Array.isArray(warnings) ? warnings : []).filter((w) => typeof w === "string" && w.trim());
  return list.length ? el("ul", { class: "invite__warnings" }, list.map((w) => el("li", { class: "note note-warn" }, w))) : null;
}

/** The QR and the address for the data the server gave (null address: no network, so say so). */
export function inviteBody(data, { big = false } = {}) {
  const d = obj(data);
  const url = typeof d.url === "string" && /^https?:\/\/[^\s"<>]+$/.test(d.url) ? d.url : null;
  const qr = url && typeof d.qrPath === "string" && d.qrPath.startsWith("/setup/qr.svg") ? el("img", { class: `invite__qr${big ? " invite__qr--big" : ""}`, src: d.qrPath, alt: `QR code for ${url}`, width: big ? 360 : 200, height: big ? 360 : 200 }) : null;
  const said = el("span", { class: "note", role: "status" }, "");
  return el(
    "div",
    { class: "invite" },
    qr || note("This computer has no network address to share right now.", { kind: "empty" }),
    url ? el("p", { class: "invite__url" }, url) : null,
    url ? el("button", { class: "btn", type: "button", onclick: async () => { said.textContent = (await copyText(url)) ? "Copied." : "Copy it from above."; } }, "Copy the address") : null,
    said,
    warningsList(d.warnings),
  );
}

function guideBand() {
  return band({
    id: "invite-away",
    title: "Watching away from home",
    collapsible: true,
    foldable: true,
    collapsed: true,
    summary: "a bar, a friend's house",
    state: { status: "ready" },
    body: () =>
      el(
        "div",
        { class: "invite__guide" },
        el("p", {}, el("b", {}, "At a friend's house. "), "Run the server on a laptop, connect it to their Wi-Fi, and have everyone scan the code. It works the same as at home."),
        el("p", {}, el("b", {}, "At a bar or on guest Wi-Fi. "), "Many venues keep devices apart (\"client isolation\"), so a phone cannot reach your laptop even on the same network. Two ways around it:"),
        el("ul", {}, el("li", {}, "Turn on your laptop's own hotspot (Windows: Settings > Network > Mobile hotspot) and have friends join that Wi-Fi. The code above then shows the hotspot's address."), el("li", {}, "Bring a small travel router: join the venue with it, and everyone joins the router. Its sign-in page can open the app for guests (see docs/07-FRIENDS-AND-THE-BIG-SCREEN.md).")),
        el("p", { class: "note" }, "The app needs the internet on the laptop (for the scores), but a friend's phone only needs to reach the laptop."),
      ),
  });
}

function guestBand(data) {
  const d = obj(data);
  return band({
    id: "invite-guests",
    title: "What guests can do",
    collapsible: true,
    foldable: true,
    summary: d.pinSet ? "view-only" : "no host PIN set",
    state: { status: "ready" },
    body: () =>
      el(
        "div",
        {},
        d.pinSet
          ? el("p", {}, "Guests see every page and the live game and change nothing. You change things from this computer, or from your own tablet after you sign in with your host PIN (the \"I'm the host\" link at the top).")
          : el("p", {}, "No host PIN is set, so every device that joins can change settings. Set a host PIN in Settings > Friends and the big screen to make guests view-only."),
        el("p", { class: "settings__actions" }, el("a", { class: "btn", href: "#settings" }, "Open Settings")),
      ),
  });
}

export function createInviteView({ onStatus } = {}) {
  return poller({
    url: "/api/invite",
    refreshMs: 60 * 1000,
    onStatus,
    render: (envelope, container) => {
      const data = obj(envelope?.data);
      container.replaceChildren(
        el(
          "div",
          { class: "page invite-page" },
          el("h1", { class: "page-title" }, "Invite friends"),
          el("p", { class: "lead" }, "Anyone on the same Wi-Fi scans this with their camera and watches along. Nothing to install."),
          inviteBody(data, { big: true }),
          guestBand(data),
          guideBand(),
        ),
      );
    },
    renderError: (message, container, retry) => container.replaceChildren(errorPanel("Invite friends", message, retry)),
    renderLoading: () => el("div", { class: "page" }, band({ title: "Invite friends", collapsible: false, state: { status: "loading" } })),
    loadingDetail: "The address friends use",
  });
}

export async function loadInvite() {
  const envelope = await fetchJson("/api/invite");
  return obj(envelope?.data);
}

