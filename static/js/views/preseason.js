// The Preseason page (Phase 17 Part 3a, owner 2026-10-07: "One preseason prompt to load all the data, it will be a
// pretty deep look at the season and offseason"). A section per primary team: the outlook, offseason moves, injuries
// and suspensions, program facts and the staff, each with its sources. At the top, the loads: the preseason batch per
// primary team and the coaches batch per conference, with dates, a prompt to copy and a box to paste each answer, and
// "Run with Claude Code" where the command is found. From August, until this season's load is saved, it reminds.
//
//   createPreseasonView({ onStatus })  the shared poller view on /api/preseason (views/common.js)
//   loadsBand(status, run, onChange)   the loads band (exported for the tests)
//
// ENH-13 (the owner's board of 2026-10-30 "Build it as drawn"): each team's
// section opens with four parts in place of the Predictions, Storylines and Position battles lists: The picks and where it
// stands (the predicted record, the load's predictions, then the record so far with its pace, green ahead of the pick and red
// behind it), Players to know (a card a star: his face, the honor, why, this season's numbers; a tap opens his card),
// Projected starters on the field (Offense and Defense, the arrivals ringed in gold, a green dot on a man still starting on
// this week's chart) and the Storylines as cards (the load's storylines and position battles, then the draft, the arrivals
// and the new staff in a line each). The rest of the load follows in its columns.
//   picksPart(team), starsPart(team), startersPart(team), storiesPart(team)   exported for the tests

import { el, fmtDate, fmtUsd, isNum, obj, ordinal, playerNames, str, teamLogo, text } from "../ui/dom.js";
import { placeDefense, placeOffense } from "../ui/formation.js";
import { band, note, subhead } from "../ui/states.js";
import { mountFlow, stopFlow } from "../ui/flow.js";
import { fillWiki, wikiLink } from "../ui/wiki-links.js";
import { errorPanel, fetchJson, poller } from "./common.js";
// wave 3 of the one-column page (owner 2026-11-01, his inventory): the bands that joined the magazine, each loading its own answer
import { lateBands, ratingsBand } from "./season.js";
import { headlinesBand, lineupBand, tripBand } from "./program.js";
import { pollsBand } from "../ui/polls-band.js";
import { rosterBands } from "./roster.js";
import { recruitingBands } from "./recruiting.js";
import { teamExtraBands } from "./team.js";
import { usLabel, usSchool } from "../identity.js";
import { addSideChips, cover, ratingChip } from "../ui/cover.js"; // the cover on one team (owner 2026-11-07): the Magazine opens with our cover
import { nationalHref } from "../ui/national-link.js";
import { railHost } from "../ui/rail.js";
import { openPlayer } from "./player.js";

function list(value) {
  return (Array.isArray(value) ? value : []).filter((x) => x && typeof x === "object");
}

async function send(url, body) {
  const response = await fetch(url, { method: "POST", cache: "no-store", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  let envelope = null;
  try {
    envelope = await response.json();
  } catch {
    envelope = null;
  }
  if (!response.ok) throw new Error(envelope?.errors?.[0]?.message || `The server answered ${response.status}`);
  return envelope?.data && typeof envelope.data === "object" ? envelope.data : {};
}

/** One batch's row: what's saved, then Copy the prompt and Paste the answer (Phase 19: the prompt is never shown). */
export function loadsBand(status, run, onChange) {
  const s = obj(status);
  const pre = list(s.preseason);
  const coaches = list(s.coaches);
  const costs = list(s.costs);
  const savedTeams = pre.filter((t) => str(t.savedAt)).length;
  const allSavedAt = pre.length && savedTeams === pre.length && isNum(s.coachesSaved) && s.coachesSaved === s.coachesOf ? pre.map((t) => str(t.savedAt)).filter(Boolean).sort().pop() : null;
  const complete = savedTeams === pre.length && isNum(s.coachesSaved) && s.coachesSaved === s.coachesOf && costs.every((c) => str(c.savedAt)) && !s.remind;
  return band({
    id: "preseason-loads",
    title: "Season loads",
    collapsible: true,
    foldable: true,
    collapsed: complete, // everything loaded: folded out of the way of the teams (the reader's fold this visit still wins)
    summary: `preseason ${savedTeams} of ${pre.length} teams · coaches ${isNum(s.coachesSaved) ? s.coachesSaved : 0} of ${isNum(s.coachesOf) ? s.coachesOf : 0} · costs ${isNum(s.costsSaved) ? s.costsSaved : 0} of ${isNum(s.coachesOf) ? s.coachesOf : 0}`,
    state: { status: "ready" },
    // Freeze wave F3 (one fact, one source): the copy, paste and run of every batch live on the Load data page, where every
    // "not loaded yet" leads; this band says what is loaded and points there.
    body: () =>
      el(
        "div",
        { class: "season-load" },
        s.remind ? el("p", { class: "season-load__remind", role: "note" }, `The ${text(s.season)} preseason load isn't saved yet for every primary team. Run it once before the season starts.`) : null,
        el("p", { class: "note" }, `Preseason ${savedTeams} of ${pre.length} primary teams${allSavedAt ? ` (${fmtDate(allSavedAt, "short")})` : ""}, coaches ${isNum(s.coachesSaved) ? s.coachesSaved : 0} of ${isNum(s.coachesOf) ? s.coachesOf : 0} conferences, costs ${isNum(s.costsSaved) ? s.costsSaved : 0} of ${isNum(s.coachesOf) ? s.coachesOf : 0}.`),
        el("p", { class: "settings__actions" }, el("a", { class: "btn", href: "#prompts" }, "Open Load data"), " ", el("span", { class: "note" }, obj(run).commandFound === true ? "Copy, paste or run each load there." : "Copy and paste each load there (Claude Code is not installed on the server computer).")),
      ),
  });
}

function items(rows, { title = "title", detail = "detail" } = {}) {
  const good = list(rows).filter((r) => str(r[title]));
  if (!good.length) return null;
  return el("ul", { class: "preseason__items" }, good.map((r) => el("li", {}, el("b", {}, r[title]), str(r[detail]) ? ` ${r[detail]}` : null)));
}

function moves(rows) {
  const good = list(rows).filter((r) => str(r.name));
  if (!good.length) return null;
  return el("ul", { class: "preseason__items" }, good.map((r) => el("li", {}, el("b", { class: "pn" }, r.name), str(r.position) ? ` (${r.position})` : null, str(r.kind) ? `: ${r.kind}` : null, str(r.detail) ? `, ${r.detail}` : null))); // item 6: a name on one line
}

function injuries(rows) {
  const good = list(rows).filter((r) => str(r.name));
  if (!good.length) return null;
  return el("ul", { class: "preseason__items" }, good.map((r) => el("li", {}, el("b", { class: "pn" }, r.name), str(r.position) ? ` (${r.position})` : null, `: ${str(r.status) || "Status not reported"}`, str(r.detail) ? `, ${r.detail}` : null, str(r.expectedReturn) ? `. Back: ${r.expectedReturn}` : null)));
}

function block(title, node) {
  return node ? el("div", { class: "preseason__block" }, el("h4", { class: "preseason__h" }, title), node) : null;
}

// --- ENH-13: the four parts ---------------------------------------------------------------------------------------

function part(title, aside, body) {
  return body ? el("section", { class: "pre-part" }, el("div", { class: "pre-part__head" }, el("h4", { class: "preseason__h" }, title), aside ? el("span", { class: "pre-part__aside" }, aside) : null), body) : null;
}

function tile(label, value, sub, extra = null, cls = "") {
  const v = str(value);
  if (!v) return null;
  return el("div", { class: `pre-tile${cls ? ` ${cls}` : ""}` }, el("span", { class: "pre-tile__label" }, label), el("span", { class: v.length > 9 ? "pre-tile__value pre-tile__value--words" : "pre-tile__value" }, v), str(sub) ? el("span", { class: "pre-tile__sub" }, sub) : null, extra);
}

function recordText(line) {
  const r = obj(line);
  if (!isNum(r.wins) || !isNum(r.losses)) return null;
  return `${r.wins}-${r.losses}${isNum(r.ties) && r.ties > 0 ? `-${r.ties}` : ""}`;
}

/** The picks before the season beside the record so far. Exported for the tests. */
export function picksPart(team) {
  const t = obj(team);
  const outlook = obj(obj(t.preseason).outlook);
  const pick = obj(outlook.predictedRecord);
  const conf = str(t.conference) || "conference";
  const now = obj(t.now);
  const tiles = [];
  tiles.push(tile("Predicted", pick.overall, str(pick.conference) ? `${pick.conference} ${conf}` : null, str(pick.source) ? el("span", { class: "pre-tile__source" }, pick.source) : null));
  for (const item of list(outlook.predictions).filter((r) => str(r.title) && str(r.detail)).slice(0, 3)) tiles.push(tile(item.title, item.detail, null));
  const overall = recordText(now.overall);
  if (overall) {
    const conferenceWords = recordText(now.conference) ? `${recordText(now.conference)} ${conf}` : null;
    const ap = isNum(now.apRank) ? `No. ${now.apRank} AP` : null;
    const tone = now.versus === "ahead" ? "good" : now.versus === "behind" ? "bad" : null;
    const chip = str(now.pace) ? el("span", { class: `pre-chip${tone ? ` pre-chip--${tone}` : ""}` }, `on pace for ${now.pace}`) : null;
    tiles.push(tile("So far", overall, [conferenceWords, ap].filter(Boolean).join(" · "), chip, `pre-tile--now${tone ? ` pre-tile--${tone}` : ""}`));
  }
  const good = tiles.filter(Boolean);
  if (!good.length) return null;
  const aside = now.versus === "ahead" ? "ahead of the picks" : now.versus === "behind" ? "behind the picks" : now.versus === "on" ? "right on the picks" : null;
  return part("The picks and where it stands", aside, el("div", { class: "pre-tiles" }, good));
}

function initials(name) {
  return String(name || "").split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join("") || "?";
}

function face(star) {
  const box = el("span", { class: "pre-star__face", "aria-hidden": "true" }, initials(star.name));
  if (str(star.headshot) && /^\/media\/headshot\//.test(star.headshot)) {
    const img = el("img", { src: star.headshot, alt: "", loading: "lazy", width: "64", height: "64" });
    img.addEventListener("error", () => img.remove()); // no photo: the initials stay
    box.append(img);
  }
  return box;
}

/** The players to know, a card each. Exported for the tests. */
export function starsPart(team) {
  const t = obj(team);
  const stars = list(t.stars).filter((s) => str(s.name));
  if (!stars.length) return null;
  const card = (s) => {
    const names = playerNames(s.name);
    const inner = [
      el("span", { class: "pre-star__who" }, face(s), el("span", { class: "pre-star__id" }, el("span", { class: "pre-star__name" }, names.full), str(s.position) ? el("span", { class: "pre-star__pos" }, s.position) : null)),
      str(s.honor) ? el("span", { class: "pre-chip pre-chip--gold" }, s.honor) : null,
      str(s.why) ? el("span", { class: "pre-star__why" }, s.why) : null,
      list(s.numbers).length ? el("span", { class: "pre-star__numbers" }, list(s.numbers).filter((n) => str(n.value)).map((n) => el("span", {}, el("b", {}, n.value), el("small", {}, text(n.label))))) : null,
    ];
    const id = isNum(s.playerId) || /^\d+$/.test(String(s.playerId ?? "")) ? String(s.playerId) : null;
    return id
      ? el("button", { class: "pre-star", type: "button", "aria-label": `${names.full}${str(s.honor) ? `, ${s.honor}` : ""}: open the player card`, onclick: () => openPlayer(id, { name: names.full }) }, inner)
      : el("div", { class: "pre-star" }, inner);
  };
  return part("Players to know", stars.some((s) => s.playerId) ? "tap a card for the player" : null, el("div", { class: "pre-stars" }, stars.map(card)));
}

/** Map one side's spots from the program's two-sided field onto a field of its own. */
function oneSide(placed, side) {
  return placed.map((p) => ({ ...p, y: side === "offense" ? 14 + ((p.y - 56) / 34) * 76 : 8 + ((p.y - 9) / 33) * 76 }));
}

/** The front a projected defense lines up in, counted from its slots ("3-3" for three down linemen and three linebackers),
    so the linebackers spread across the field instead of crowding the middle. */
function frontOf(rows) {
  const k = (r) => String(r.slot || "").toUpperCase().replace(/[^A-Z0-9]/g, "");
  const line = rows.filter((r) => /^(DE|DT|NT|NG|DL|EDGE|RUSH|LDE|RDE|LDT|RDT|LE|RE|END|TACKLE)/.test(k(r))).length;
  const backers = rows.filter((r) => /^(LB|MLB|ILB|OLB|WLB|SLB|MIKE|WILL|SAM)\d?$/.test(k(r))).length;
  return line && backers ? { backs: null, tightEnds: null, underCenter: false, front: { line, linebackers: backers, backs: null } } : null;
}

function fieldOf(rows, side) {
  const slots = rows.map((r) => ({ slot: r.slot, players: [{ name: r.name, new: r.new === true, now: r.startingNow }] }));
  const placed = oneSide(side === "offense" ? placeOffense(slots, null) : placeDefense(slots, frontOf(rows)), side);
  return el(
    "div",
    { class: `formation__field pre-field pre-field--${side}` },
    el("div", { class: "pre-field__los", "aria-hidden": "true" }),
    placed.map((p) => {
      const pl = obj(p.player);
      const names = playerNames(pl.name, { notes: true });
      const words = `${text(p.slot)} ${names.full}${pl.new ? ", new this year" : ""}${pl.now === true ? ", still starting" : pl.now === false ? ", not starting now" : ""}`;
      return el(
        "div",
        { class: `formation__man formation__man--us pre-man${pl.new ? " pre-man--new" : ""}`, style: { "--fx": `${p.x}%`, "--fy": `${p.y}%` }, role: "img", "aria-label": words, title: words },
        el("span", { class: "formation__pos" }, text(p.slot).toUpperCase()),
        el("span", { class: "formation__num pre-man__dot" }, pl.now === true ? el("span", { class: "pre-man__now" }) : null),
        el("span", { class: "formation__name" }, names.last),
      );
    }),
  );
}

/** The projected starters on the field, Offense and Defense. Exported for the tests. */
export function startersPart(team) {
  const t = obj(team);
  const st = obj(t.starters);
  const rowsOf = (side) => list(st[side]).filter((r) => str(r.name) && str(r.slot));
  const sides = ["offense", "defense"].filter((side) => rowsOf(side).length);
  if (!sides.length) return null;
  let side = sides[0];
  const holder = el("div", { class: "pre-starters__field" });
  const show = () => holder.replaceChildren(fieldOf(rowsOf(side), side));
  const buttons = sides.map((s) => el("button", { type: "button", "aria-pressed": s === side ? "true" : "false", class: s === side ? "is-on" : null, onclick: () => {
    side = s;
    buttons.forEach((b, i) => {
      const on = sides[i] === side;
      b.setAttribute("aria-pressed", on ? "true" : "false");
      b.className = on ? "is-on" : "";
    });
    show();
  } }, s === "offense" ? "Offense" : "Defense"));
  const seg = el("div", { class: "seg", role: "group", "aria-label": "Which side" }, buttons);
  show();
  const anyNow = [...list(st.offense), ...list(st.defense)].some((r) => r.startingNow === true || r.startingNow === false);
  const legend = ["gold ring: new this year", anyNow ? "green dot: still starting on this week's chart" : null].filter(Boolean).join(" · ");
  return part("Projected starters", legend, el("div", { class: "pre-starters" }, el("div", { class: "pre-starters__bar" }, seg, el("span", { class: "pre-part__aside" }, "from the season load")), holder));
}

/** The storylines as cards: the load's own, its position battles, then the draft, the arrivals and the new staff. Exported for the tests. */
export function storiesPart(team) {
  const t = obj(team);
  const p = obj(t.preseason);
  const outlook = obj(p.outlook);
  const cards = [];
  for (const r of list(outlook.storylines).filter((x) => str(x.title))) cards.push([r.title, r.detail]);
  for (const r of list(outlook.positionBattles).filter((x) => str(x.title))) cards.push([`Position battle: ${r.title}`, r.detail]);
  const drafted = list(p.departures).filter((m) => str(m.name) && /draft/i.test(str(m.kind) || ""));
  if (drafted.length) {
    const first = drafted.find((m) => /round 1\b/i.test(str(m.detail) || "")) || drafted[0];
    cards.push(["Gone to the draft", `${drafted.length} ${drafted.length === 1 ? "pick" : "picks"}, ${first.name}${str(first.detail) ? ` (${first.detail})` : ""} first.`]);
  }
  const arrived = list(p.arrivals).filter((m) => str(m.name));
  if (arrived.length) {
    const transfers = arrived.filter((m) => /transfer/i.test(str(m.kind) || "")).length;
    const starters = [...list(obj(t.starters).offense), ...list(obj(t.starters).defense)];
    const newStarters = starters.filter((r) => r.new === true).length;
    const words = [transfers ? `${transfers} ${transfers === 1 ? "transfer" : "transfers"}` : null, arrived.length - transfers ? `${arrived.length - transfers} more` : null].filter(Boolean).join(" and ");
    cards.push([`${arrived.length} ${arrived.length === 1 ? "arrival" : "arrivals"}`, `${words}${starters.length ? `; ${newStarters} of the ${starters.length} projected starters are new` : ""}.`]);
  }
  const changes = list(p.coachingChanges).filter((c) => str(c.title));
  if (changes.length) cards.push(["A new staff", changes.slice(0, 3).map((c) => (str(c.detail) ? `${c.title}: ${c.detail}` : c.title)).join("; ")]);
  if (!cards.length) return null;
  return part("Storylines", "from the season load", el("div", { class: "pre-stories" }, cards.map(([title, detail]) => el("div", { class: "pre-story" }, el("b", {}, title), str(detail) ? el("p", {}, detail) : null))));
}

function teamBand(team) {
  const t = obj(team);
  const p = t.preseason ? obj(t.preseason) : null;
  const outlook = obj(p?.outlook);
  const c = obj(t.coaches);
  const staff = list(p?.staff).filter((m) => str(m.name));
  const sources = list(p?.sources).filter((s) => str(s.label) || str(s.url));
  const coachLine = [["HC", c.headCoach], ["OC", c.offensiveCoordinator], ["DC", c.defensiveCoordinator]].filter(([, v]) => str(v)).map(([k, v]) => `${k} ${v}`).join(" · ");
  return band({
    id: teamBandId(t),
    title: text(t.school),
    collapsible: true,
    foldable: true,
    summary: p ? `loaded ${fmtDate(t.savedAt, "short")}` : "not loaded",
    state: p ? { status: "ready" } : { status: "empty", message: "Not loaded yet. Copy the prompt in Season loads above, or run it with Claude Code.", action: { label: "Open Load data", href: "#prompts" } },
    body: () =>
      el(
        "div",
        { class: "preseason__team" },
        el("div", { class: "preseason__top" }, teamLogo(t, { size: 48 }), el("div", {}, el("div", { class: "preseason__conf" }, text(t.conference)), coachLine ? el("div", { class: "preseason__coaches" }, coachLine) : null)),
        str(outlook.summary) ? el("p", { class: "preseason__summary" }, outlook.summary) : null,
        // ENH-13: the four parts as drawn, in place of the Predictions, Storylines and Position battles lists
        el("div", { class: "pre-parts" }, picksPart(t), starsPart(t), startersPart(t), storiesPart(t)),
        // ENH-20 (P5): the sections flow in magazine columns across the band, not one long column beside an empty one
        el(
          "div",
          { class: "preseason__blocks" },
          block("Who left", moves(p?.departures)),
          block("Who arrived", moves(p?.arrivals)),
          block("Coaching changes", items(p?.coachingChanges)),
          block("Injuries and suspensions", injuries(p?.injuries)),
          block("Program facts", items(p?.programFacts)),
          block("Roster cost (rumored)", isNum(obj(t.costs).totalUsd) ? el("p", { class: "preseason__cost" }, el("b", {}, fmtUsd(t.costs.totalUsd)), str(t.costs.note) ? ` ${t.costs.note}` : null, el("small", {}, " See the team page for positions and players.")) : null),
          block("Staff", staff.length ? el("ul", { class: "preseason__items" }, staff.map((m) => el("li", {}, el("b", {}, wikiLink("coach", { person: m.name, team: str(t.school) }, m.name)), str(m.role) ? `, ${m.role}` : null))) : null),
        ),
        sources.length ? el("p", { class: "note" }, "Sources: ", sources.map((s, i) => [i ? ", " : null, str(s.url) && /^https?:\/\//.test(s.url) ? el("a", { href: s.url, target: "_blank", rel: "noopener" }, str(s.label) || s.url) : text(s.label)])) : null,
        str(t.author) ? el("p", { class: "note" }, `Written by ${t.author}.`) : null,
      ),
  });
}

/** The magazine's late bands (wave 3, 2026-11-01, his inventory, in its order): our headlines, Talent and recruiting,
 *  Getting there, the polls, our ratings, the roster's bands, the class and Where they're from, the staff and the school's
 *  facts, each loading its own answer; `ui` keeps the tables' orders across refreshes. */
function magazineLate(ui) {
  const team = usSchool();
  ui.polls ??= { poll: null, sorts: {} };
  ui.roster ??= { position: "", sort: null };
  ui.recruiting ??= { year: null, sorts: {} };
  ui.team ??= { sorts: {} };
  const extras = lateBands(`/api/team/${encodeURIComponent(team)}`, [["talent", "Talent and recruiting", "team-recruiting"], ["staff", "Staff", "team-staff"], ["facts", "School facts", "team-facts"]], (d) => teamExtraBands(d, ui.team));
  const roster = lateBands("/api/roster", [["breakdown", "Roster breakdown", "roster-breakdown"], ["costs", "Roster costs (rumored)", "roster-costs"], ["table", "Roster", "roster-table"], ["stars", "Recruiting stars on the roster", "roster-stars"], ["impact", "Impact players", "roster-impact"]], (d) => {
    const [breakdown, costs, table, stars, impact] = rosterBands(d, ui.roster);
    return { breakdown, costs, table, stars, impact };
  });
  const recruiting = lateBands("/api/recruiting", [["klass", "The class", "recruiting-class"], ["where", "Where they're from", "recruiting-where"]], (d) => {
    const draw = () => {
      const [klass, where] = recruitingBands(d, ui.recruiting, { visitors: false, redraw: draw });
      recruiting[0].replaceChildren(klass);
      if (where) recruiting[1].replaceChildren(where);
    };
    const [klass, where] = recruitingBands(d, ui.recruiting, { visitors: false, redraw: draw });
    return { klass, where };
  });
  const nextGame = lateBands("/api/program/next", [["trip", "Getting there", "preseason-trip"], ["lineup", "Lineup", "preseason-lineup"]], (d) => ({ trip: tripBand(d, { id: "preseason-trip" }), lineup: lineupBand(d, { id: "preseason-lineup" }) }));
  return [
    headlinesBand(undefined, { id: "preseason-headlines" }),
    extras[0],
    nextGame[0],
    ...lateBands("/api/season/overview", [["polls", "Polls", "preseason-polls"], ["ratings", "Ratings", "preseason-ratings"]], (d) => ({ polls: pollsBand(d, { ui: ui.polls, id: "preseason-polls" }), ratings: ratingsBand(d, team, { id: "preseason-ratings" }) })),
    ...roster,
    ...recruiting,
    extras[1],
    extras[2],
    nextGame[1], // the lineup picture (owner 2026-11-01: "I also want this on the ... preseason magazine"), at the bottom until he places it
  ].filter(Boolean);
}

/** A team band's id (the flow's wide list names it too). */
/** The Magazine's front (owner 2026-11-07: "the season and preseason magazine would just have the gators, but all of the
 *  other cover information should be there"): our cover, the picks and where it stands where the opponent stood, the
 *  coaches under our side, the load's date in the foot, the rail across the top. Exported for the tests. */
export function magazineCover(team, season) {
  const t = obj(team);
  const now = obj(t.now);
  const c = obj(t.coaches);
  const staffWords = [["HC", c.headCoach], ["OC", c.offensiveCoordinator], ["DC", c.defensiveCoordinator]].filter(([, v]) => str(v)).map(([k, v]) => `${k} ${v}`).join(" · ");
  const staff = staffWords ? el("div", { class: "cover__staff cover__staff--us" }, el("b", {}, text(str(t.abbreviation) || usLabel())), " ", staffWords) : null;
  const us = { school: t.school, mascot: t.mascot, abbreviation: t.abbreviation, conference: t.conference, logo: t.logo, logoDark: t.logoDark, color: t.color, altColor: t.altColor, record: now.overall, conferenceRecord: now.conference, apRank: now.apRank };
  const picks = picksPart(t);
  const loaded = t.preseason ? `${str(t.savedAt) ? `Loaded ${fmtDate(t.savedAt, "short")}` : "Preloaded with the app"}${str(t.author) ? ` · written by ${t.author}` : ""}` : "Not loaded yet: the Season loads band below has the prompt and the run.";
  const page = cover({
    one: true,
    us,
    kicker: [`${text(season)} Preseason Magazine`, str(t.conference)].filter(Boolean).join(" · "),
    label: `${text(season)} Preseason Magazine cover`,
    rail: railHost({ kind: "preseason" }),
    middle: picks ? el("div", { class: "cover__one-middle" }, picks) : el("div", { class: "cover__one-middle" }, note("The picks and the predicted record appear once the season load is in.")),
    staff: { us: staff },
    extra: el("span", { class: "note" }, loaded),
  });
  page.classList.add("preseason-cover", "flow-full");
  const cost = obj(t.costs);
  if (isNum(cost.totalUsd)) addSideChips(page, "us", [ratingChip("Roster cost", { value: fmtUsd(cost.totalUsd), title: str(cost.note) || "Rumored roster cost" })]);
  fillMagazineCover(page, t.school);
  return page;
}

/** The Magazine cover's second coat (the board as drawn, 2026-11-07): the all-time record, the national titles, the talent rank
 *  and the blue-chip share as chips, from the program's answer the page already has cached. */
async function fillMagazineCover(section, school) {
  if (!str(school) || school !== usSchool()) return;
  let program = null;
  try {
    program = (await fetchJson("/api/program/next"))?.data || null;
  } catch (error) {
    console.warn("The Magazine: the program behind the cover did not load; the cover keeps the load's own facts.", error?.message || error);
    return;
  }
  if (!program || typeof program !== "object" || !section.isConnected) return;
  const f = obj(obj(program.facts).us);
  const talent = obj(obj(obj(program.us).ratings).talent);
  const blue = obj(obj(obj(program.recruiting).us).blueChip);
  const chips = [
    str(f.allTimeRecord) ? ratingChip("All-time", { value: f.allTimeRecord }) : null,
    Array.isArray(f.nationalTitles) && f.nationalTitles.length ? ratingChip("National titles", { value: f.nationalTitles.length, title: f.nationalTitles.join(", ") }) : null,
    isNum(talent.rank) ? ratingChip("Talent", { rank: talent.rank, of: talent.of, href: nationalHref(str(talent.metric) || "rating:talent", { team: school }) }) : null,
    isNum(blue.ratio) ? ratingChip("Blue chips", { value: `${Math.round(blue.ratio * 100)}%`, title: "Blue-chip share of the signees" }) : null,
  ].filter(Boolean);
  addSideChips(section, "us", chips);
}

function teamBandId(t) {
  return `preseason-${String(t?.school || "team").toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
}

/** Rollover R3 (owner 2026-11-15: the Magazine "opens with 2026's last pages"): last season in brief, from its season in review
 *  as kept at the switch, and the way to the whole of it; nothing at all where no review was kept (before the first switch). */
function lastSeasonBrief(season) {
  const year = isNum(season) ? season - 1 : null;
  if (year === null) return null;
  const host = el("div", { class: "late late--brief" });
  fetchJson(`/api/seasons/${year}/book/overview`)
    .then((envelope) => {
      const d = obj(envelope?.data);
      const rec = obj(d.record);
      const overall = obj(rec.overall);
      const conf = obj(rec.conference);
      const games = (Array.isArray(d.schedule) ? d.schedule : []).filter((g) => g && typeof g === "object" && g.completed === true);
      const mine = (Array.isArray(d.standings) ? d.standings : []).find((r) => r && typeof r === "object" && r.isUs === true);
      const confName = text(obj(d.team).conferenceShort || obj(d.team).conference) || "conference";
      const record = isNum(overall.wins) ? `${overall.wins}–${isNum(overall.losses) ? overall.losses : 0}${overall.ties ? `–${overall.ties}` : ""}` : "–";
      const confLine = isNum(conf.wins) ? `${conf.wins}–${isNum(conf.losses) ? conf.losses : 0} ${confName}${mine && isNum(mine.place) ? `, ${ordinal(mine.place)}` : ""}` : null;
      const sp = obj(obj(d.ratings).sp);
      const ranks = [isNum(rec.apRank) ? `No. ${rec.apRank} AP` : null, isNum(rec.cfpRank) ? `No. ${rec.cfpRank} CFP` : null, isNum(sp.rank) ? `SP+ #${sp.rank}` : null].filter(Boolean);
      const chips = games.map((g) => {
        const result = text(g.result);
        const opp = obj(g.opponent);
        return el("span", { class: `brief__game${result ? ` brief__game--${result.toLowerCase()}` : ""}` }, `${result || "–"} ${isNum(g.usPoints) ? g.usPoints : "–"}-${isNum(g.themPoints) ? g.themPoints : "–"} ${text(opp.abbreviation || opp.school)}`);
      });
      host.replaceChildren(band({
        id: "preseason-last",
        title: `${year} in brief`,
        collapsible: false,
        foldable: true,
        summary: [record, ...ranks].join(" · "),
        state: { status: "ready" },
        body: () => el(
          "div",
          { class: "brief" },
          el("p", { class: "brief__record" }, el("b", {}, record), confLine ? el("span", {}, ` · ${confLine}`) : null, ranks.length ? el("span", { class: "dim" }, ` · ${ranks.join(" · ")}`) : null),
          chips.length ? el("div", { class: "brief__games" }, ...chips) : null,
          el("p", {}, el("a", { class: "btn btn--quiet", href: `#review=${year}` }, `The ${year} season in review`), " ", el("a", { class: "btn btn--quiet", href: `#newspaper?season=${year}` }, `The ${year} papers`)),
        ),
      }));
    })
    .catch(() => host.replaceChildren()); // no review kept for last season: no band
  return host;
}

export function createPreseasonView({ onStatus } = {}) {
  const ui = { run: null, timer: null, status: null, loads: null };
  let view = null;
  const refreshRun = async () => {
    try {
      const envelope = await fetchJson("/api/season-notes/run");
      ui.run = envelope?.data && typeof envelope.data === "object" ? envelope.data : null;
    } catch {
      ui.run = null;
    }
  };
  const again = async () => {
    await refreshRun();
    if (ui.loads && ui.loads.isConnected !== false) {
      const fresh = loadsBand(ui.status, ui.run, again); // the run's progress, without redrawing the teams
      ui.loads.replaceWith(fresh);
      ui.loads = fresh;
    }
    if (view) view.refresh(); // a saved batch changes the teams: the poller redraws when the data differ
    clearTimeout(ui.timer);
    if (ui.run?.running) ui.timer = setTimeout(again, 15000); // a run in progress: check every 15 s
  };
  view = poller({
    url: "/api/preseason",
    onStatus,
    render: (envelope, container) => {
      const data = obj(envelope?.data);
      const teams = list(data.teams);
      ui.status = data.status;
      ui.loads = loadsBand(data.status, ui.run, again);
      const mine = teams.find((t) => t && typeof t === "object" && t.school === usSchool()) || null; // the cover on one team (2026-11-07): the Magazine's front is our cover
      const page = el(
          "div",
          { class: "page preseason" },
          mine ? magazineCover(mine, data.season) : el("h1", { class: "page-title flow-full" }, `${text(data.season)} Preseason Magazine`),
          lastSeasonBrief(data.season), // rollover R3: the Magazine opens with last season's last pages
          ui.loads,
          teams.length ? teams.map(teamBand) : note("No team yet. Pick it on the setup page (Settings, Change team)."),
          ...magazineLate(ui),
      );
      mountFlow(ui, container, page, { wide: ["preseason-loads", ...teams.map(teamBandId)] }); // final pass: the flowing page with its section chips; ENH-20 (P5): every band across the page, so a short Season loads never sits beside a long team
      fillWiki(container); // Phase 19: the staff's names open their Wikipedia pages
    },
    renderError: (message, container, retry) => container.replaceChildren(errorPanel("Preseason Magazine", message, retry)),
    renderLoading: () => el("div", { class: "page" }, band({ title: "Preseason Magazine", collapsible: false, state: { status: "loading" } })),
    loadingDetail: "The season loads and each primary team's preseason notes",
  });
  const mount = view.mount;
  view.mount = (container) => {
    mount.call(view, container);
    again();
  };
  const unmount = view.unmount;
  view.unmount = (...args) => {
    clearTimeout(ui.timer);
    stopFlow(ui); // final pass: the layout's observers go with the page
    return unmount.apply(view, args);
  };
  return view;
}

