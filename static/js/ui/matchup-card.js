// The matchup card (N2, P2): the opponent as the hero, then us and the opponent side by
// side in one compact table with a rank chip beside every number, scheme labels when the notes
// file has them, and the weather row at the foot. Thin on purpose (owner direction 2026-09-23).
// Phase 16 (stream PROGRAM): the table is the shared two-team table (ui/two-team.js): value and a linked
// chip in one cell, a divider before the opponent, Offense and Defense as group rows.

import { icon } from "./icons.js";
import { usLabel, usSchool } from "../identity.js";
import { el, fmtNum, isNum, teamLogo, text } from "./dom.js";
import { pollHref } from "./national-link.js";
import { pollBadge } from "./stat-table.js";
import { listLink, twoTeamTable } from "./two-team.js";
import { fillWiki, teamPageChip, wikiLink } from "./wiki-links.js";
import { kickWind } from "./wind.js";

function recordText(record) {
  if (!record || !isNum(record.wins) || !isNum(record.losses)) return null;
  return record.ties ? `${record.wins}-${record.losses}-${record.ties}` : `${record.wins}-${record.losses}`;
}

/**
 * matchupCard({ kicker, us: {abbreviation, school}, them: {school, abbreviation, logo, logoDark, apRank, record, conferenceRecord},
 *               teamTags: [{label, href, rank, of, name}], tags: [{label, kind, href}], schemes: {offense, defense, source},
 *               rows: [{ label, side, format, metric, higherIsBetter, us: {value, rank, of}, them: {value, rank, of} }], foot })
 * A row's metric makes both chips links to that stat's national list (ours highlighted on its chip,
 * the opponent's on its own). Phase 17 #11: teamTags describe the opponent (SP+) and sit on its record line;
 * tags describe the game (a conference game, a bowl) and sit under the hero, so a rating never reads as the game's.
 */
export function matchupCard({ kicker = "This week's opponent", us = {}, them = {}, teamTags = [], tags = [], schemes = null, rows = [], foot } = {}) {
  const rec = recordText(them.record);
  const confRec = recordText(them.conferenceRecord);
  const list = (Array.isArray(rows) ? rows : []).filter((row) => row && typeof row === "object");
  const chip = (tag) => (typeof tag.href === "string" && tag.href.startsWith("#") ? listLink(tag.href, tag.label, { rank: tag.rank, of: tag.of, name: tag.name, className: `tag tag--link${tag.kind ? ` tag--${tag.kind}` : ""}` }) : el("span", { class: `tag${tag.kind ? ` tag--${tag.kind}` : ""}` }, text(tag.label)));
  const valid = (value) => (Array.isArray(value) ? value : []).filter((tag) => tag && typeof tag === "object" && typeof tag.label === "string" && tag.label.trim());
  const teamChips = valid(teamTags).map(chip);
  const gameChips = valid(tags).map(chip);
  const groups = [["offense", "Offense", schemes?.offense], ["defense", "Defense", schemes?.defense]]
    .map(([side, title, scheme]) => ({ title, note: typeof scheme === "string" ? scheme : null, rows: list.filter((r) => r.side === side) }))
    .filter((g) => g.rows.length);
  const card = el(
    "article",
    { class: "mcard mcard--thin", id: "program-matchup", "aria-label": `Matchup: ${text(them.school)}` },
    el("div", { class: "mcard__kicker" }, kicker),
    el(
      "div",
      { class: "mcard__hero" },
      wikiLink("football", { team: them.school }, teamLogo(them, { size: 64, lazy: false, className: "mcard__logo" })), // Phase 17 #4
      el(
        "div",
        { class: "mcard__name" },
        isNum(them.apRank) ? pollBadge(them.apRank, "AP", { href: pollHref("AP", { team: them.school }), label: text(them.school) }) : null,
        isNum(them.apRank) ? " " : null,
        them.school ? wikiLink("school", { team: them.school }, text(them.school)) : text(null),
        rec ? el("span", { class: "mcard__rec" }, ` ${rec}`) : null,
        confRec || teamChips.length || them.school ? el("small", { class: "mcard__facts" }, confRec ? `${confRec} in conference` : null, teamChips, teamPageChip(them.school)) : null,
      ),
    ),
    gameChips.length ? el("div", { class: "mcard__tags", "aria-label": "This game" }, gameChips) : null,
    groups.length
      ? twoTeamTable({ groups, usAbbr: text(us.abbreviation || usLabel()), themAbbr: text(them.abbreviation), usTeam: us.school, themTeam: them.school, tug: true, labelHead: "This season", caption: `${text(us.school || usSchool())} and ${text(them.school)} this season`, className: "mcard__table" })
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
