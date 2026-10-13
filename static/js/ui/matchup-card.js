// The matchup card (N2, P2; redrawn 2026-10-10 with the table sizes): the opponent as the hero, then us and the
// opponent side by side in the shared two-team table (ui/two-team.js), each team's scheme under its own columns,
// and the weather row at the foot. The hero is one name line and one line of chips at every size, nothing wrapped:
// the AP badge, the opponent's name (its team page, with the mascot at large) and both records "2-3 (0-3)", then
// its SP+ chip, at large its last five results (each that game's box score), and the game's tags (the conference's
// short name alone, a bowl's name). No Team page chip: the name is the way there. Thin on purpose (owner 2026-09-23).
// The card follows the table's size (data-size on the article), so the logo and the name shrink with it.

import { icon } from "./icons.js";
import { usLabel, usSchool } from "../identity.js";
import { el, fmtNum, isNum, teamLink, teamLogo, text } from "./dom.js";
import { pollHref } from "./national-link.js";
import { pollBadge } from "./stat-table.js";
import { listLink, twoTeamTable } from "./two-team.js";
import { fillWiki, wikiLink } from "./wiki-links.js";
import { kickWind } from "./wind.js";

function recordText(record) {
  if (!record || !isNum(record.wins) || !isNum(record.losses)) return null;
  return record.ties ? `${record.wins}-${record.losses}-${record.ties}` : `${record.wins}-${record.losses}`;
}

/** "2-3 (0-3)": the record with the conference record in brackets, as the team page header has it. */
export function recordLine(team) {
  const t = team && typeof team === "object" ? team : {};
  const rec = recordText(t.record);
  const conf = recordText(t.conferenceRecord);
  if (!rec) return null;
  return conf ? `${rec} (${conf})` : rec;
}

/** The school and its mascot for the large table head ("Swampwater Tech Mudcats"); the school alone without one. */
export function fullName(team) {
  const t = team && typeof team === "object" ? team : {};
  const school = typeof t.school === "string" ? t.school.trim() : "";
  const mascot = typeof t.mascot === "string" ? t.mascot.trim() : "";
  if (!school) return null;
  return mascot && !school.toLowerCase().includes(mascot.toLowerCase()) ? `${school} ${mascot}` : school;
}

/** The last five results as W and L squares, newest last, each the game's box score (Phase 17 #2); null with none. */
export function lastFive(form) {
  const games = (Array.isArray(form) ? form : []).filter((g) => g && typeof g === "object" && ["W", "L", "T"].includes(g.result)).slice(-5);
  if (!games.length) return null;
  return el(
    "span",
    { class: "mcard__last5" },
    el("small", {}, "Last 5"),
    el(
      "span",
      { class: "form-guide" },
      games.map((g) => {
        const said = `${g.result === "W" ? "Won" : g.result === "L" ? "Lost" : "Tied"} ${isNum(g.points) ? g.points : "–"}-${isNum(g.opponentPoints) ? g.opponentPoints : "–"} ${g.homeAway === "away" ? "at" : "vs"} ${text(g.opponent)}`;
        const cls = `form-guide__game form-guide__game--${g.result.toLowerCase()}`;
        return isNum(g.gameId)
          ? el("a", { class: `${cls} form-guide__game--link`, href: `#box=${g.gameId}`, title: `${said}. Open the box score`, "aria-label": `${said}. Open the box score` }, g.result)
          : el("span", { class: cls, title: said }, g.result);
      }),
    ),
  );
}

/**
 * matchupCard({ kicker, us: {abbreviation, school, mascot}, them: {school, mascot, abbreviation, logo, logoDark, apRank, record,
 *               conferenceRecord, form}, teamTags: [{label, href, rank, of, name}], tags: [{label, kind, href}],
 *               schemes: {offense, defense, opponent: {offense, defense}, source}, onNotes,
 *               rows: [{ label, side, format, metric, higherIsBetter, us: {value, rank, of, conf}, them: {...} }], foot })
 * A row's metric makes both chips links to that stat's national list (ours highlighted on its chip, the opponent's
 * on its own). teamTags describe the opponent (SP+); tags describe the game and sit after the team's chips, the
 * conference's short name alone for a conference game. schemes.offense/defense are ours and schemes.opponent theirs,
 * each under its own columns in the group row; where one is missing, onNotes (the way to the notes band) is offered.
 */
export function matchupCard({ kicker = "This week's opponent", us = {}, them = {}, teamTags = [], tags = [], schemes = null, onNotes, rows = [], foot } = {}) {
  const u = us && typeof us === "object" ? us : {};
  const t = them && typeof them === "object" ? them : {}; // junk never throws
  const list = (Array.isArray(rows) ? rows : []).filter((row) => row && typeof row === "object");
  const chip = (tag) => (typeof tag.href === "string" && tag.href.startsWith("#") ? listLink(tag.href, tag.label, { rank: tag.rank, of: tag.of, name: tag.name, className: `tag tag--link${tag.kind ? ` tag--${tag.kind}` : ""}` }) : el("span", { class: `tag${tag.kind ? ` tag--${tag.kind}` : ""}` }, text(tag.label)));
  const valid = (value) => (Array.isArray(value) ? value : []).filter((tag) => tag && typeof tag === "object" && typeof tag.label === "string" && tag.label.trim());
  const teamChips = valid(teamTags).map(chip);
  const gameChips = valid(tags).map(chip);
  const s = schemes && typeof schemes === "object" ? schemes : {};
  const theirs = s.opponent && typeof s.opponent === "object" ? s.opponent : {};
  const word = (value) => (typeof value === "string" && value.trim() ? value.trim() : null);
  const missing = typeof onNotes === "function" ? { label: "Get this week's notes", onClick: onNotes } : { label: "Get this week's notes", href: "#prompts" }; // never a dead end (the Prompts phase)
  const groups = [["offense", "Offense", s.offense, theirs.offense], ["defense", "Defense", s.defense, theirs.defense]]
    .map(([side, title, ours, others]) => ({ title, rows: list.filter((r) => r.side === side), us: word(ours), them: word(others), missing }))
    .filter((g) => g.rows.length);
  const school = typeof t.school === "string" && t.school.trim() ? t.school.trim() : null;
  const mascot = typeof t.mascot === "string" && t.mascot.trim() && school && !school.toLowerCase().includes(t.mascot.trim().toLowerCase()) ? t.mascot.trim() : null;
  const record = recordLine(t);
  const card = el(
    "article",
    { class: "mcard mcard--thin", id: "program-matchup", "aria-label": `Matchup: ${text(school)}`, dataset: { size: "large" } },
    el("div", { class: "mcard__kicker" }, kicker),
    el(
      "div",
      { class: "mcard__hero" },
      wikiLink("football", { team: school }, teamLogo(t, { size: 64, lazy: false, className: "mcard__logo" })), // Phase 17 #4
      el(
        "div",
        { class: "mcard__who" },
        el(
          "div",
          { class: "mcard__name" },
          isNum(t.apRank) ? pollBadge(t.apRank, "AP", { href: pollHref("AP", { team: school }), label: text(school) }) : null,
          school ? teamLink(school, text(school)) : text(null), // the name is the way to the team page (no chip)
          mascot ? el("span", { class: "mcard__mascot" }, mascot) : null,
          record ? el("span", { class: "mcard__rec" }, record) : null,
        ),
        teamChips.length || gameChips.length || t.form ? el("div", { class: "mcard__chips", "aria-label": "This team and this game" }, teamChips, lastFive(t.form), gameChips) : null,
      ),
    ),
    groups.length
      ? twoTeamTable({
          groups,
          usAbbr: text(u.abbreviation || usLabel()),
          themAbbr: text(t.abbreviation),
          usTeam: u.school,
          themTeam: school,
          usName: fullName(u),
          themName: fullName(t),
          tug: true,
          labelHead: "This season",
          caption: `${text(u.school || usSchool())} and ${text(school)} this season`,
          className: "mcard__table",
          onSize: (size) => {
            card.dataset.size = size;
          },
        })
      : el("p", { class: "note" }, "No season stats yet."),
    foot ? el("div", { class: "mcard__foot" }, foot) : null,
  );
  fillWiki(card);
  return card;
}

// Phase 16 wave 3 (owner pick 3B): the sprite's weather icons, drawn the same on every device (the emoji were not).
const SKY_GLYPHS = [
  [/thunder|storm/i, "storm"],
  [/rain|shower|drizzle/i, "rain"],
  [/snow|sleet|ice/i, "snow"],
  [/fog|haze|mist/i, "fog"],
  [/mostly cloudy|overcast/i, "cloud"],
  [/partly|cloud/i, "partly"],
  [/clear|sunny|fair/i, "sun"],
];

/** The sky's glyph, or null when the forecast names no sky we know (Phase 17: no placeholder circle). */
function skyGlyph(sky) {
  const s = String(sky || "");
  for (const [re, glyph] of SKY_GLYPHS) if (re.test(s)) return glyph;
  return null;
}

/** A radar link only to a real web page (UX-14): the payload's NWS link, never a script or a local path. */
function radarHref(url) {
  return typeof url === "string" && /^https:\/\/[^\s"'<>]+$/i.test(url.trim()) ? url.trim() : null;
}

function radarLink(url) {
  const href = radarHref(url);
  return href ? el("a", { class: "weather__radar btn btn--quiet", href, target: "_blank", rel: "noopener noreferrer", title: "The National Weather Service radar for the stadium" }, "Radar") : null;
}

/**
 * weatherRow({ kickoffText, tempF, windMph, windDir, sky, precipChance, indoors, source, note, label, radarUrl })
 * With no forecast (`note` set, or no temperature and no sky) it says so in one line. label names the row
 * ("Weather forecast" before the game, "Kickoff weather" after it); radarUrl adds a Radar link-out when it
 * is an https page (Phase 16, UX-14), hidden otherwise.
 */
export function weatherRow({ kickoffText, tempF, windMph, windDir, sky, precipChance, indoors = false, source, note, label = "Weather forecast", radarUrl } = {}) {
  const hasForecast = isNum(tempF) || (typeof sky === "string" && sky.trim());
  const title = typeof label === "string" && label.trim() ? label.trim() : "Weather forecast";
  const when = el("div", { class: "weather__when" }, title, kickoffText ? el("b", {}, text(kickoffText)) : null);
  if (!hasForecast) {
    return el("div", { class: "weather" }, when, el("div", { class: "weather__main" }, el("small", {}, typeof note === "string" && note.trim() ? note.trim() : "No forecast yet.")), radarLink(radarUrl));
  }
  const wind = isNum(windMph) ? `${Math.round(windMph)} mph wind${typeof windDir === "string" && windDir.trim() ? ` ${windDir.trim()}` : ""}` : null;
  const detail = indoors ? "Indoors, no effects" : [typeof sky === "string" && sky.trim() ? text(sky) : null, isNum(precipChance) ? `${Math.round(precipChance)}% rain` : null].filter(Boolean).join(", ");
  return el(
    "div",
    { class: "weather" },
    when,
    indoors || skyGlyph(sky) ? el("span", { class: "weather__glyph", "aria-hidden": "true" }, icon(indoors ? "stadium" : skyGlyph(sky))) : null,
    el("div", { class: "weather__main" }, el("span", { dataset: { k: "weather-main" } }, [isNum(tempF) ? `${Math.round(tempF)}° F` : null, wind].filter(Boolean).join(", ") || text(null)), detail ? el("small", {}, detail) : null, kickWind({ windMph, indoors })), // Phase 17 #6
    radarLink(radarUrl),
    source ? el("div", { class: "weather__source" }, `Source: ${text(source)}`) : null,
  );
}

function number(value) {
  return isNum(value) ? value : null;
}

/**
 * venueLine(venueDetail, { us }) -> <p class="venue-line"> or null (GX-19, restrained): the stadium's name,
 * capacity, grass or turf, elevation, year built, dome, and our record against this opponent at the venue,
 * as one text line. Each fact appears only when the payload has it; with none, there is no line.
 */
export function venueLine(detail, { us = usSchool() } = {}) {
  const d = detail && typeof detail === "object" && !Array.isArray(detail) ? detail : null;
  if (!d) return null;
  const facts = [];
  const name = typeof d.name === "string" && d.name.trim() ? d.name.trim() : null;
  const capacity = number(d.capacity);
  if (capacity !== null && capacity > 0) facts.push(`Capacity ${fmtNum(capacity, 0)}`);
  if (d.grass === true) facts.push("Grass");
  else if (d.grass === false) facts.push("Artificial turf");
  const feet = number(d.elevationFt);
  if (feet !== null) facts.push(`Elevation ${fmtNum(Math.round(feet), 0)} ft`);
  const built = number(d.yearBuilt);
  if (built !== null && built > 1800 && built < 2100) facts.push(`Built ${Math.round(built)}`);
  if (d.dome === true) facts.push("Dome");
  const rec = d.recordAtVenue && typeof d.recordAtVenue === "object" ? d.recordAtVenue : null;
  const wins = number(rec?.wins);
  const losses = number(rec?.losses);
  const ties = number(rec?.ties);
  // Phase 17 #3: the record is the series against this opponent at this stadium, so the line names the opponent
  const opponent = typeof rec?.opponent === "string" && rec.opponent.trim() ? rec.opponent.trim() : null;
  const unlisted = number(rec?.gamesWithoutVenue);
  let record = null;
  if (opponent && wins !== null && losses !== null && wins + losses + (ties || 0) > 0) {
    record = el(
      "span",
      { title: unlisted ? `Counts only the series games CFBD lists a stadium for; ${unlisted} older ${unlisted === 1 ? "game has" : "games have"} none.` : null },
      `${text(us)} ${wins}-${losses}${ties ? `-${ties}` : ""} vs ${opponent} here`,
    );
  }
  if (!name && !facts.length && !record) return null;
  const parts = [name ? el("b", { class: "venue-line__name" }, wikiLink("stadium", { venue: name }, name)) : null, ...facts, record].filter(Boolean); // Phase 17 #4
  const line = el("p", { class: "venue-line" }, parts.flatMap((part, i) => (i ? [" · ", part] : [part])));
  fillWiki(line);
  return line;
}
