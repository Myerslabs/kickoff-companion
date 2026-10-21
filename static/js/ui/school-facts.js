// School history and facts (the Prompts phase, owner 2026-10-13: "they will live on the team page"). One band on the
// team page's History tab and on the team sheet: founded, the stadium, titles, Heismans, the bowl record, the rivalries
// with their trophies, the coach's record here, the mascot, the colors, the fight song, alumni in the NFL. A fact the
// answer did not have is a dash, never a blank; a team with nothing loaded says so and points at the Prompts page.
//
//   factsBand(facts, { id, school, outside })   the band; outside: the school is not one the loads cover (2026-10-16)
//   OUTSIDE   what a team the loads leave out says
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
  const stadium = [str(f.stadium) ? f.stadium.trim() : null, str(f.stadiumNickname) ? `"${f.stadiumNickname.trim()}"` : null, isNum(f.stadiumOpened) ? `opened ${f.stadiumOpened}` : null, isNum(f.capacity) ? `${fmtNum(f.capacity)} seats` : null].filter(Boolean); // the preloaded facts (2026-10-21): the nickname too
  const titleYears = list(f.conferenceTitleYears).filter(isNum);
  const retired = list(f.retiredNumbers).filter((x) => str(x));
  const traditions = list(f.traditions).filter((x) => str(x));
  const titles = list(f.nationalTitles).filter(isNum);
  const heismans = list(f.heismans).filter((x) => str(x));
  const rivals = list(f.rivalries).map(rivalry).filter(Boolean);
  const alumni = list(f.nflAlumni).filter((x) => str(x));
  // freeze wave F4: the dated events, which only the once-a-day note showed before; a year alone keeps its year
  const dayWithYear = (iso) => {
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
    if (!m) return iso; // a year alone stays a year
    const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3])); // a local day: no zone shift off the date written
    return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString([], { month: "long", day: "numeric", year: "numeric" });
  };
  const dates = list(f.dates).filter((d) => d && typeof d === "object" && str(d.date) && str(d.event)).map((d) => `${dayWithYear(d.date.trim())}: ${d.event.trim()}`);
  return [
    { label: "Founded", value: isNum(f.founded) ? String(f.founded) : DASH },
    { label: "Stadium", value: stadium.length ? stadium.join(", ") : DASH },
    { label: "In the conference since", value: isNum(f.conferenceSince) ? String(f.conferenceSince) : DASH },
    { label: "All-time record", value: str(f.allTimeRecord) ? f.allTimeRecord.trim() : DASH },
    { label: "National titles", value: titles.length ? `${titles.length}: ${titles.join(", ")}` : DASH },
    { label: "Conference titles", value: isNum(f.conferenceTitles) ? `${f.conferenceTitles}${titleYears.length ? `: ${titleYears.join(", ")}` : ""}` : titleYears.length ? `${titleYears.length}: ${titleYears.join(", ")}` : DASH },
    { label: "First season", value: isNum(f.firstSeason) ? String(f.firstSeason) : DASH },
    { label: "Heisman winners", value: heismans.length ? heismans.join("; ") : DASH },
    { label: "Bowl record", value: str(f.bowlRecord) ? f.bowlRecord.trim() : DASH },
    { label: "Rivalries", value: rivals.length ? rivals.join("; ") : DASH },
    { label: "Head coach's record here", value: str(f.headCoachRecord) ? f.headCoachRecord.trim() : DASH },
    { label: "Winningest coach", value: str(f.winningestCoach) ? f.winningestCoach.trim() : DASH },
    { label: "Longest win streak", value: str(f.longestWinStreak) ? f.longestWinStreak.trim() : DASH },
    { label: "Record crowd", value: str(f.recordCrowd) ? f.recordCrowd.trim() : DASH },
    { label: "Retired numbers", value: retired.length ? retired.join("; ") : DASH },
    { label: "Mascot", value: [str(f.mascotName) ? f.mascotName.trim() : null, str(f.mascotOrigin) ? f.mascotOrigin.trim() : null].filter(Boolean).join(": ") || DASH },
    { label: "Colors", value: str(f.colorsOrigin) ? f.colorsOrigin.trim() : DASH },
    { label: "Fight song", value: str(f.fightSong) ? f.fightSong.trim() : DASH },
    { label: "Traditions", value: traditions.length ? traditions.join("; ") : DASH },
    { label: "In the NFL now", value: alumni.length ? alumni.join(", ") : DASH },
    { label: "Dates", value: dates.length ? dates.join("; ") : DASH },
  ];
}

/** The season loads cover my teams only (owner 2026-10-16), so another team's empty band says so instead of leading to Load data. */
export const OUTSIDE = "Loaded for your primary and secondary teams and the next opponent only. To load it, add the school as a liked team in Settings.";

export function factsBand(facts, { id = "team-facts", school, outside = false } = {}) {
  const f = facts && typeof facts === "object" ? facts : null;
  const name = str(school) ? school.trim() : "this school";
  const sources = f ? list(f.sources).filter((s) => s && typeof s === "object" && str(s.url) && /^https?:\/\//.test(s.url)) : [];
  return band({
    id,
    title: "School history",
    collapsible: false,
    foldable: true,
    summary: f ? `loaded ${str(f.savedAt) ? fmtDate(f.savedAt, "short") : ""}`.trim() : "not loaded",
    state: f ? { status: "ready" } : outside ? { status: "empty", message: `${name}'s history is not loaded. ${OUTSIDE}`, action: { label: "Open Settings", href: "#settings" } } : { status: "empty", message: `${name}'s history and facts are not loaded yet. One prompt per conference loads them.`, action: { label: "Open Load data", href: "#prompts" } },
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
