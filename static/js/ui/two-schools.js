// The two schools (the Prompts phase, wave B, owner 2026-10-13: the facts "sprinkled throughout the app as a variable").
// On the Pre-Game Program, under the cover: each school's founding, all-time record, titles, Heismans and stadium side by
// side, and the trophy the two play for when the facts name one. Drawn only when at least one side has facts; the band
// is never an empty box.
//
//   twoSchoolsBand({ us, them, facts })   us/them: the program's team blocks; facts: { us, them } from /api/program
//   trophyLine(facts, us, them)           "The Rusty Skillet: BLUE leads 68-44-2, since 1915" or null (tests)

import { DASH, el, fmtNum, isNum, obj, str, text } from "./dom.js";
import { band } from "./states.js";

function count(list) {
  return Array.isArray(list) ? list.filter((x) => x !== null && x !== undefined && x !== "").length : 0;
}

function rows(f) {
  const x = obj(f);
  const stadium = [str(x.stadium) ? x.stadium.trim() : null, isNum(x.capacity) ? `${fmtNum(x.capacity)} seats` : null].filter(Boolean).join(", ");
  return {
    Founded: isNum(x.founded) ? String(x.founded) : DASH,
    "All-time record": str(x.allTimeRecord) ? x.allTimeRecord.trim() : DASH,
    "National titles": count(x.nationalTitles) ? `${count(x.nationalTitles)} (last ${Math.max(...x.nationalTitles.filter(isNum))})` : DASH,
    "Conference titles": isNum(x.conferenceTitles) ? String(x.conferenceTitles) : DASH,
    "Heisman winners": count(x.heismans) ? String(count(x.heismans)) : DASH,
    Stadium: stadium || DASH,
  };
}

export function trophyLine(facts, us, them) {
  const sides = [[obj(facts).us, us, them], [obj(facts).them, them, us]];
  for (const [f, owner, other] of sides) {
    const rivalries = Array.isArray(obj(f).rivalries) ? f.rivalries : [];
    const hit = rivalries.find((r) => r && typeof r === "object" && str(r.rival) && str(other?.school) && r.rival.trim().toLowerCase() === other.school.trim().toLowerCase());
    if (!hit) continue;
    const who = str(owner?.abbreviation) ? owner.abbreviation : str(owner?.school) ? owner.school : "They";
    const bits = [str(hit.record) ? `${who} ${hit.record.trim()}` : null, isNum(hit.firstMeeting) ? `since ${hit.firstMeeting}` : null].filter(Boolean);
    return `${str(hit.trophy) ? hit.trophy.trim() : "A rivalry"}${bits.length ? `: ${bits.join(", ")}` : ""}`;
  }
  return null;
}

export function twoSchoolsBand({ us, them, facts, id = "program-schools" } = {}) {
  const f = obj(facts);
  if (!f.us && !f.them) return null;
  const u = rows(f.us);
  const t = rows(f.them);
  const usName = str(us?.abbreviation) ? us.abbreviation : str(us?.school) ? us.school : "Us";
  const themName = str(them?.abbreviation) ? them.abbreviation : str(them?.school) ? them.school : "Them";
  const trophy = trophyLine(f, us, them);
  return band({
    id,
    title: "The two schools",
    collapsible: true,
    foldable: true,
    summary: trophy || "history and facts",
    state: { status: "ready" },
    body: () => el(
      "div",
      { class: "schools" },
      trophy ? el("p", { class: "schools__trophy" }, text(trophy)) : null,
      el(
        "table",
        { class: "stat-table schools__table", "aria-label": "The two schools' history" },
        el("thead", {}, el("tr", {}, el("th", { scope: "col", class: "txt" }, ""), el("th", { scope: "col" }, text(usName)), el("th", { scope: "col" }, text(themName)))),
        el("tbody", {}, Object.keys(u).map((label) => el("tr", {}, el("th", { scope: "row", class: "txt" }, label), el("td", { class: "txt" }, text(u[label])), el("td", { class: "txt" }, text(t[label]))))),
      ),
      !f.us || !f.them ? el("p", { class: "note" }, `${!f.us ? text(us?.school || "Our") : text(them?.school || "Their")} facts are not loaded yet. `, el("a", { href: "#prompts" }, "Open the prompts")) : null,
    ),
  });
}
