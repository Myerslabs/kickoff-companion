// Wikipedia links on the big team headers (Phase 17 #4, owner 2026-10-07: the logo opens the team's football page,
// the team name the school's page, the stadium the stadium's page; big headers only, tables keep the app's team
// page, and a "Team page" chip keeps the way there). Each link is drawn at once as a Wikipedia search, which always
// works; fillWiki(root) then asks /api/wiki once for every team and venue in root and points each link at its page.
//
//   wikiLink(kind, { team, venue, person }, ...children)  -> <a class="wiki-link">  kind: "football" | "school" | "stadium" | "coach"
//   teamPageChip(school)                           -> the app's own team page, as a chip
//   fillWiki(root)                                 -> Promise; links without an answer keep their search
//   searchUrl(words)

import { el, text } from "./dom.js";
import { fetchJson } from "../views/common.js";

const answers = new Map(); // "team|venue" query -> Promise of the answer, one request per page load each

export function searchUrl(words) {
  const q = new URLSearchParams({ search: String(words || ""), title: "Special:Search", go: "Go" });
  return `https://en.wikipedia.org/w/index.php?${q.toString()}`;
}

function fallback(kind, team, venue, person) {
  if (kind === "stadium") return searchUrl(venue);
  if (kind === "coach") return searchUrl(`${person} football coach`);
  return searchUrl(kind === "football" ? `${team} football` : `${team} university`);
}

const SAYS = { football: "football page", school: "school page", stadium: "stadium page", coach: "page" };

export function wikiLink(kind, { team, venue, person } = {}, ...children) {
  const school = typeof team === "string" && team.trim() ? team.trim() : null;
  const place = typeof venue === "string" && venue.trim() ? venue.trim() : null;
  const who = typeof person === "string" && person.trim() ? person.trim() : null;
  if ((kind === "stadium" && !place) || (kind === "coach" && !who) || (kind !== "stadium" && kind !== "coach" && !school)) return el("span", {}, ...children);
  const what = kind === "stadium" ? place : kind === "coach" ? who : school;
  return el(
    "a",
    {
      class: `wiki-link wiki-link--${kind}`,
      href: fallback(kind, school, place, who),
      target: "_blank",
      rel: "noopener",
      title: `Wikipedia: ${what}, ${SAYS[kind] || "page"}`,
      "aria-label": `${text(what)}: open the ${SAYS[kind] || "page"} on Wikipedia`,
      dataset: { wiki: kind, team: school || "", venue: place || "", person: who || "" },
    },
    ...children,
  );
}

export function teamPageChip(school) {
  const name = typeof school === "string" && school.trim() ? school.trim() : null;
  if (!name) return null;
  return el("a", { class: "cover-chip cover-chip--link team-page-chip", href: `#team=${encodeURIComponent(name)}`, "aria-label": `${name}: open the team page` }, "Team page");
}

export function fillWiki(root) {
  if (!root || typeof root.querySelectorAll !== "function") return Promise.resolve();
  const links = [...root.querySelectorAll("a.wiki-link")];
  if (!links.length) return Promise.resolve();
  const teams = [...new Set(links.filter((a) => a.dataset?.wiki !== "coach").map((a) => a.dataset?.team).filter(Boolean))].slice(0, 4);
  const coaches = [...new Set(links.filter((a) => a.dataset?.wiki === "coach" && a.dataset?.person).map((a) => `${a.dataset.person}|${a.dataset.team || ""}`))].slice(0, 12);
  const venue = links.map((a) => a.dataset?.venue).find(Boolean) || "";
  const params = new URLSearchParams();
  for (const t of teams) params.append("team", t);
  if (venue) params.set("venue", venue);
  for (const c of coaches) params.append("coach", c);
  const key = params.toString();
  if (!answers.has(key)) {
    answers.set(key, fetchJson(`/api/wiki?${key}`).then((envelope) => (envelope?.data && typeof envelope.data === "object" ? envelope.data : {})).catch((error) => {
      answers.delete(key); // the next draw tries again; the searches stand meanwhile
      console.warn("Wikipedia links did not load; the links stay as searches.", error?.message || error);
      return {};
    }));
  }
  return answers.get(key).then((data) => {
    const good = (url) => typeof url === "string" && url.startsWith("https://en.wikipedia.org/");
    for (const a of links) {
      const kind = a.dataset?.wiki;
      const url = kind === "stadium" ? data.venues?.[a.dataset?.venue]?.stadium : kind === "coach" ? data.coaches?.[`${a.dataset?.person}|${a.dataset?.team || ""}`]?.page : data.teams?.[a.dataset?.team]?.[kind];
      if (good(url)) a.setAttribute("href", url);
    }
  });
}
