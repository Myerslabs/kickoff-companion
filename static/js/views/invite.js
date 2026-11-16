// Invite friends (Phase 18.6, owner 2026-10-08). A full-screen QR code by IP number (a phone scans it; no name lookup
// to go wrong), the address to type, what a guest can and cannot do, and a guide for watching away from home.
//
//   createInviteView({ onStatus })   the page (#invite)
//   inviteBody({ big, pin })         the QR, address and warnings as one node (the Live sheet's sheet and the board reuse
//                                    it); pin false leaves out the host PIN warning (the Invite page says it in What guests can do)

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
export function inviteBody(data, { big = false, pin = true } = {}) {
  const d = obj(data);
  const url = typeof d.url === "string" && /^https?:\/\/[^\s"<>]+$/.test(d.url) ? d.url : null;
  const qr = url && typeof d.qrPath === "string" && d.qrPath.startsWith("/setup/qr.svg") ? el("img", { class: `invite__qr${big ? " invite__qr--big" : ""}`, src: d.qrPath, alt: `QR code for ${url}`, width: big ? 360 : 200, height: big ? 360 : 200 }) : null;
  const said = el("span", { class: "note", role: "status" }, "");
  const warnings = [...(Array.isArray(d.warnings) ? d.warnings : []), ...(pin && typeof d.pinWarning === "string" ? [d.pinWarning] : [])];
  return el(
    "div",
    { class: "invite" },
    qr || note("This computer has no network address to share right now.", { kind: "empty" }),
    el(
      "div",
      { class: "invite__text" },
      url ? el("p", { class: "invite__url" }, url) : null,
      url ? el("button", { class: "btn", type: "button", onclick: async () => { said.textContent = (await copyText(url)) ? "Copied." : "Copy it from above."; } }, "Copy the address") : null,
      said,
      warningsList(warnings),
    ),
  );
}

/** ENH-20 (P5): the code and the address in a band, the code beside the words on a tablet, like the page's other bands. */
function joinBand(data) {
  const d = obj(data);
  return band({
    id: "invite-join",
    title: "Scan to join",
    collapsible: false,
    summary: d.away === true ? "away from home" : "the same Wi-Fi",
    state: { status: "ready" },
    body: () => el(
      "div",
      { class: "invite-join" },
      el("p", { class: "invite-join__lead" }, d.away === true ? "Away from home is on: friends scan this code with their camera, or open this exact address. The plain address shows them a page saying the companion is away. Nothing to install." : "Anyone on the same Wi-Fi scans this with their camera and watches along. Nothing to install."),
      inviteBody(d, { big: true, pin: false }),
    ),
  });
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
        { class: "invite__guests" },
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
    onStatus,
    render: (envelope, container) => {
      const data = obj(envelope?.data);
      container.replaceChildren(
        el(
          "div",
          { class: "page invite-page" },
          el("h1", { class: "page-title" }, "Invite friends"),
          joinBand(data),
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

