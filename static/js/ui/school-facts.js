// School history and facts (the Prompts phase, owner 2026-10-13: "they will live on the team page"). One band on the
// team page's History tab and on the team sheet: founded, the stadium, titles, Heismans, the bowl record, the rivalries
// with their trophies, the coach's record here, the mascot, the colors, the fight song, alumni in the NFL. A fact the
// answer did not have is a dash, never a blank; a team with nothing loaded says so and points at the Prompts page.
//
//   factsBand(facts, { id, school })   the band
//   factRows(facts)                    [{ label, value }] in the page's order (exported for the tests)

import { DASH, el, fmtDate, fmtNum, isNum, str, text } from "./dom.js";
import { band } from "./states.js";

function list(value) {
  return Array.isArray(value) ? value.filter((x) => x !== null && x !== undefined) : [];
}

function rivalry(r) {
  if (!r || typeof r !== "object" || !str(r.rival)) return null;
  const bits = [str(r.trophy) ? r.trophy.trim() : null, isNum(r.firstMeeting) ? `since ${r.firstMeeting}` : null, str(r.record) ? r.record.trim() : null].filter(Boolean);
  return `${r.rival.trim()}${bits.length ? ` (${bits.join(", ")})` : ""}`;
}

export function factRows(facts) {
  const f = facts && typeof facts === "object" ? facts : {};
  const stadium = [str(f.stadium) ? f.stadium.trim() : null, isNum(f.stadiumOpened) ? `opened ${f.stadiumOpened}` : null, isNum(f.capacity) ? `${fmtNum(f.capacity)} seats` : null].filter(Boolean);
  const titles = list(f.nationalTitles).filter(isNum);
  const heismans = list(f.heismans).filter((x) => str(x));
  const rivals = list(f.rivalries).map(rivalry).filter(Boolean);
  const alumni = list(f.nflAlumni).filter((x) => str(x));
  return [
    { label: "Founded", value: isNum(f.founded) ? String(f.founded) : DASH },
    { label: "Stadium", value: stadium.length ? stadium.join(", ") : DASH },
    { label: "In the conference since", value: isNum(f.conferenceSince) ? String(f.conferenceSince) : DASH },
    { label: "All-time record", value: str(f.allTimeRecord) ? f.allTimeRecord.trim() : DASH },
    { label: "National titles", value: titles.length ? `${titles.length}: ${titles.join(", ")}` : DASH },
    { label: "Conference titles", value: isNum(f.conferenceTitles) ? String(f.conferenceTitles) : DASH },
    { label: "Heisman winners", value: heismans.length ? heismans.join("; ") : DASH },
    { label: "Bowl record", value: str(f.bowlRecord) ? f.bowlRecord.trim() : DASH },
    { label: "Rivalries", value: rivals.length ? rivals.join("; ") : DASH },
    { label: "Head coach's record here", value: str(f.headCoachRecord) ? f.headCoachRecord.trim() : DASH },
    { label: "Mascot", value: str(f.mascotOrigin) ? f.mascotOrigin.trim() : DASH },
    { label: "Colors", value: str(f.colorsOrigin) ? f.colorsOrigin.trim() : DASH },
    { label: "Fight song", value: str(f.fightSong) ? f.fightSong.trim() : DASH },
    { label: "In the NFL now", value: alumni.length ? alumni.join(", ") : DASH },
  ];
}

export function factsBand(facts, { id = "team-facts", school } = {}) {
  const f = facts && typeof facts === "object" ? facts : null;
  const name = str(school) ? school.trim() : "this school";
  const sources = f ? list(f.sources).filter((s) => s && typeof s === "object" && str(s.url) && /^https?:\/\//.test(s.url)) : [];
  return band({
    id,
    title: "School history",
    collapsible: false,
    foldable: true,
    summary: f ? `loaded ${str(f.savedAt) ? fmtDate(f.savedAt, "short") : ""}`.trim() : "not loaded",
    state: f ? { status: "ready" } : { status: "empty", message: `${name}'s history and facts are not loaded yet. One prompt per conference loads them.`, action: { label: "Open the prompts", href: "#prompts" } },
    body: () =>
      el(
        "div",
        { class: "facts" },
        el(
          "table",
          { class: "stat-table facts__table", "aria-label": `${name}: history and facts` },
          el("tbody", {}, factRows(f).map((row) => el("tr", {}, el("th", { scope: "row", class: "txt" }, row.label), el("td", { class: "txt facts__value" }, text(row.value))))),
        ),
        sources.length ? el("p", { class: "note facts__sources" }, "Sources: ", ...sources.slice(0, 6).flatMap((s, i) => [i ? ", " : "", el("a", { href: s.url, target: "_blank", rel: "noopener" }, str(s.label) ? s.label.trim() : "page")])) : null,
      ),
  });
}
