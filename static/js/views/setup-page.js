// The Setup page (owner 2026-10-10): one menu item for the things a reader opens now and then: the demo, the archive of
// games the app watched, the season in review and the radio. Since the layout pass (owner 2026-10-22) it is the Profile's
// Setup section (views/settings.js), and #setup opens the Profile there. First time setup (connecting a device) moved inside
// Settings. Nothing to fetch: four large links, each with a line saying what it opens.

import { el } from "../ui/dom.js";
import { band } from "../ui/states.js";

export const SETUP_LINKS = [
  { label: "Demo", href: "/demo", note: "The whole app against a made-up league, with a game under way. Your key and your team stay as they are." },
  { label: "Archive", href: "#archive", note: "Every game the app watched: the box score, the win probability and your notes." },
  { label: "Season in review", href: "#review", note: "The season so far told from the schedule: the record, the streaks, the best win." },
  { label: "Radio", href: "#radio", note: "The station that carries the game and the player at the bottom of every page." },
];

function linkCard({ label, href, note }) {
  return el("a", { class: "setup-link", href }, el("span", { class: "setup-link__label" }, label), el("span", { class: "setup-link__note" }, note));
}

/** The Setup links as a band: the Profile's Setup section (the layout pass, owner 2026-10-22: settings and setup in one). */
export function setupBand() {
  return band({
    id: "settings-setup",
    title: "Setup",
    collapsible: false,
    summary: "demo, archive, season in review, radio",
    state: { status: "ready" },
    body: () =>
      el(
        "div",
        { class: "setup-links" },
        SETUP_LINKS.map(linkCard),
        el("p", { class: "note" }, "Connecting a phone, a tablet or a TV is First time setup, above."),
        // freeze wave F5 (section 7 of the plan): the developer pages, reachable without typing them
        el("p", { class: "note setup-dev" }, "Developer: ", el("a", { href: "/debug/live" }, "replay a game"), " · ", el("a", { href: "/static/styleguide.html" }, "the design system"), "."),
      ),
  });
}

/** The old Setup page, kept for the styleguide and the tests: the band alone. #setup itself opens the Profile now. */
export function createSetupPageView({ onStatus } = {}) {
  return {
    mount(target) {
      target.replaceChildren(el("div", { class: "page setup-page" }, setupBand()));
      if (typeof onStatus === "function") onStatus({ kind: "quiet", label: "Setup" });
    },
    refresh() {},
    unmount() {},
  };
}
