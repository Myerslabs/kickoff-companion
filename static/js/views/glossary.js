// The Glossary (owner request 2026-09-26): every stat and term the app shows, grouped the way the
// app uses them and searchable. The same entries answer a tap on a dotted-underlined label anywhere
// (static/js/ui/hints.js). "#glossary=<id>" opens the page at one entry.
// Phase 16 (G3-15, stream NV): the group bands fold (remembered on the device) with jump links to each
// group in the intro band's body, never its head; search matches are marked; an entry whose stat has a
// national list links to it ('National list ›', opened in a side sheet, no fetch until tapped).

import { GLOSSARY, GLOSSARY_GROUPS } from "../glossary-data.js";
import { el, text } from "../ui/dom.js";
import { listLink } from "../ui/national-sheet.js";
import { band, note, revealBand } from "../ui/states.js";
import { marked } from "./search.js";

const ENTRIES = Array.isArray(GLOSSARY) ? GLOSSARY.filter((e) => e && typeof e.id === "string" && typeof e.term === "string") : [];
const GROUPS = Array.isArray(GLOSSARY_GROUPS) ? GLOSSARY_GROUPS : [];

function haystack(entry) {
  return [entry.term, entry.text, entry.read, ...(Array.isArray(entry.aliases) ? entry.aliases : [])].map((s) => String(s ?? "").toLowerCase()).join(" \n ");
}

/** The band id of a glossary group. Exported for the tests. */
export function groupId(group) {
  return `gloss-group-${String(group).toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
}

function entryEl(entry, focused, query) {
  return el(
    "div",
    { class: `gloss__entry${focused ? " is-focus" : ""}`, id: `gloss-${entry.id}` },
    el("div", { class: "gloss__term" }, marked(entry.term, query), el("small", {}, entry.source === "App" ? "The app's own rule" : "From CFBD")),
    el(
      "div",
      { class: "gloss__body" },
      el("p", {}, marked(entry.text, query)),
      entry.read ? el("p", { class: "gloss__read" }, marked(entry.read, query)) : null,
      typeof entry.metric === "string" ? listLink(entry.metric, { label: entry.term }) : null,
    ),
  );
}

/** Unfold a band for a search or a jump without changing the fold the reader chose (not remembered). */
function openQuietly(section) {
  if (!section || (section.dataset?.collapsed ?? section.getAttribute?.("data-collapsed")) !== "true") return;
  section.setAttribute("data-collapsed", "false");
  if (section.dataset) section.dataset.collapsed = "false";
  const toggle = section.querySelector(".band__toggle");
  if (toggle) toggle.setAttribute("aria-expanded", "true");
}

export function createGlossaryView({ onStatus, focusId = null } = {}) {
  let container = null;
  let query = "";
  const setStatus = (kind, label) => {
    if (typeof onStatus === "function") onStatus({ kind, label });
  };

  function groups() {
    const q = query.toLowerCase();
    const matching = ENTRIES.filter((entry) => !q || haystack(entry).includes(q));
    const grouped = GROUPS.map((group) => [group, matching.filter((entry) => entry.group === group)]);
    const other = matching.filter((entry) => !GROUPS.includes(entry.group));
    if (other.length) grouped.push(["Other", other]);
    return { matching, grouped: grouped.filter(([, entries]) => entries.length) };
  }

  function listEl() {
    if (!ENTRIES.length) return band({ title: "Glossary", collapsible: false, state: { status: "empty", message: "The glossary is empty." } });
    const { matching, grouped } = groups();
    if (!matching.length) return note(`Nothing matches "${query}". Try a shorter word, like "rate" or "yards".`);
    const focusGroup = focusId ? ENTRIES.find((e) => e.id === focusId)?.group : null;
    return el(
      "div",
      { class: "gloss-groups" },
      grouped.map(([group, entries]) => {
        const section = band({
          id: groupId(group),
          title: group,
          collapsible: false,
          foldable: true,
          summary: `${entries.length} ${entries.length === 1 ? "term" : "terms"}`,
          state: { status: "ready" },
          body: () => el("div", { class: "gloss" }, entries.map((entry) => entryEl(entry, entry.id === focusId && !query, query))),
        });
        if (query || group === focusGroup) openQuietly(section); // a match or the asked-for entry is never folded away
        return section;
      }),
    );
  }

  function jumpLinks() {
    const present = new Set(ENTRIES.map((e) => e.group));
    const names = [...GROUPS.filter((g) => present.has(g)), ...(ENTRIES.some((e) => !GROUPS.includes(e.group)) ? ["Other"] : [])];
    return el(
      "nav",
      { class: "gloss__jump", "aria-label": "Glossary groups" },
      names.map((group) =>
        el("a", {
          class: "gloss__jump-link",
          href: `#${groupId(group)}`,
          onclick: (event) => {
            event.preventDefault(); // a band id is not a route: scroll there, never navigate
            const section = document.getElementById(groupId(group));
            if (section) revealBand(section);
          },
        }, text(group)),
      ),
    );
  }

  return {
    mount(target) {
      container = target;
      const host = el("div", {}, listEl());
      const search = el("input", {
        type: "search",
        class: "setting__text gloss__search",
        placeholder: "Search, e.g. success, EPA, havoc",
        "aria-label": "Search the glossary",
        oninput: (event) => {
          query = String(event.target.value || "").trim();
          host.replaceChildren(listEl());
        },
      });
      container.replaceChildren(
        el(
          "div",
          { class: "season", style: { gridTemplateColumns: "minmax(0, 1fr)" } },
          band({
            id: "glossary-search",
            title: "Glossary",
            collapsible: false,
            summary: `${ENTRIES.length} terms`,
            state: { status: "ready" },
            body: () => el("div", { class: "gloss__intro" }, search, el("p", { class: "note" }, "Tap any stat name with a dotted underline, anywhere in the app, for the same explanation. Settings has a switch to hide the underlines. A stat with a national list links to it: every FBS team's number, ranked."), jumpLinks()),
          }),
          host,
        ),
      );
      setStatus("quiet", `${ENTRIES.length} terms`);
      if (focusId) {
        const node = document.getElementById(`gloss-${focusId}`);
        if (node) requestAnimationFrame(() => node.scrollIntoView({ block: "center" }));
      }
    },
    refresh() {},
    unmount() {
      container = null;
    },
  };
}
