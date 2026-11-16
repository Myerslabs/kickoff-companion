// The menu's tree (the layout pass, owner 2026-10-22, boards 2 to 4).
// One level at a time:
// the opening level has Search, the six game-day tiles and the groups; a group slides its list in. He curates what is in it;
// anything new waits in New (beta) until he places it, and New hides while it is empty; since 2026-10-28 a screen he placed
// stays in New too while he tests it (TESTING). Only entries that open something are listed: no dead ends.
//
// The menu lists pages, never the bands on them (ENH-46, owner 2026-11-10: "I want anything that is just a menu item to it's
// page to be removed. Anything thats on the page still needs it whole page, and a way to look at it directly if the user
// wants, however I dont think we need a menu item for things on that page"; the board).
// A page's row opens the page: the lists of bands that 2026-10-28 put under
// each page ("Page opens its list") are gone, and with them the rows that opened one band of a page (National's polls, SP+,
// Elo, Usage, PPA) and the Profile's sections, which the Profile page has as tiles. A band is opened by itself from its own
// head on its page (ui/band-open.js) and from Search (ui/band-catalog.js allBands); its flyout's head still has Own page.
// New is the one list that keeps a row for a band: it is his testing list, and a new band on a long page is easy to miss.
//
// An entry is one of:
//   { id, label, hint, page }                  a page of the app ("season", or "leaders=passing:YDS:national")
//   { id, label, hint, href, external }        a page of the server's own (the status page), in a new tab
//   { id, label, hint, flyout }                a table opened wide by itself ("program:tape"; views/panels.js): New's rows, the Radio tile
//   { id, label, hint, live }                  one of In Game's panels, opened wide over In Game ("box")
//   { id, label, hint, items }                 a list one level down, with its count
//   { heading }                                a small heading inside a list (never a tap)
//
//   MENU                 { tiles, groups }: the opening level
//   entriesOf(items)     the entries of a list, headings and levels left out (the flyout's previous and next)
//   findPath(menu, test) the ids from the opening level down to the first entry `test` accepts, or null
//   levelAt(menu, path)  the list a path names ({ id, label, sub, items }), the opening level for []
//   allEntries(menu)     every entry at any depth with the labels of the levels above it (Search finds them)

import { usName } from "../identity.js";
import { bandEntry, BAND_PAGES, findBand } from "./band-catalog.js";

const value = (v) => (typeof v === "function" ? v() : v);

/** A page's row: a tap opens the page. The page's name and hint are the catalog's unless the row says its own. */
function pageRow(page, { id = page, label = null, hint = null } = {}) {
  const meta = BAND_PAGES[page];
  return {
    id,
    label: label || meta.label,
    hint: hint || meta.hint,
    get page() {
      return value(meta.route); // read when the row is drawn: an address that waits for the identity
    },
  };
}

const TILES = [
  { id: "newspaper", label: "Newspaper", icon: "newspaper", page: "newspaper" },
  { id: "program", label: "Program", icon: "program", page: "program" },
  { id: "live", label: "In Game", icon: "live", page: "live" },
  { id: "board", label: "Big screen", icon: "tv", page: "board" },
  { id: "trivia", label: "Trivia", icon: "trivia", page: "trivia" },
  { id: "radio", label: "Radio", icon: "radio", flyout: "radio" },
];

const GROUPS = [
  {
    id: "teams",
    label: "My Teams",
    icon: "shield",
    hint: () => `${usName()}, the season, your other teams`,
    items: [
      { heading: () => usName() },
      pageRow("newspaper", { id: "newspaper-bands", hint: "this week's pages, the Top 25, the earlier weeks" }), // owner 2026-10-28: "My Teams, first row"
      // My Team (owner 2026-11-01: "my team and season are the same in my eyes. We should rename season to my team and combine
      // menu's"): the Season page, with the team page's bands on it (wave 3 of the one-column page)
      pageRow("season", { hint: "the season, the roster, recruiting, the staff, the school, the Circle of Blame" }),
      pageRow("roster", { hint: "depth chart, impact players, position groups" }),
      pageRow("recruiting"),
      { id: "injuries", label: "Injury Report", hint: "who is out, season-long", page: "injuries" },
      { id: "review", label: "Season in review", hint: "the season told from the schedule", page: "review" },
      { id: "seasons", label: "Seasons", hint: "this season and the ones before, as kept", page: "seasons" }, // rollover R2 (owner 2026-11-15)
      pageRow("preseason"),
      pageRow("archive", { hint: "every game the app watched, the last one's tables" }),
      { heading: "The app's data" },
      { id: "prompts", label: "Load data", hint: "copy, paste or run the prompts", page: "prompts" },
    ],
  },
  {
    id: "game",
    label: "This week's game",
    icon: "matchup",
    hint: "the program, In Game, the Post-Game",
    sub: "game", // the game it is about, from views/panels.js
    items: [
      pageRow("program", { id: "program:page", hint: "the matchup, the week, the lineups, the notes" }),
      pageRow("live", { id: "live:page", hint: "the game on one screen: the score, the box, the drives, the plays" }),
      // the Post-Game stop (the season as one line, Wave 3, the owner's board of 2026-10-30)
      { id: "postgame", label: "Post-Game Program", hint: "the last game's stop: what decided it, the box, the blame", page: "postgame" },
    ],
  },
  {
    id: "national",
    label: "National",
    icon: "globe",
    hint: "Top 25, recruiting, the conferences, the Imperialism Map",
    items: [
      pageRow("top25", { hint: "every game of the week with a ranked team, the picks" }), // wave 3 (2026-11-01): the picks are its band
      { id: "recruiting-national", label: "National recruiting", hint: "this year's class, every school ranked", page: "national=class:current" },
      pageRow("conference", { hint: "the SEC first, any conference: standings, the week, the teams rated" }), // the conference page (owner 2026-11-02)
      pageRow("imperialism"), // FEAT-17, placed by the owner 2026-11-15: "the imperialism map can go under the national menu, as it's a national game"
    ],
  },
  {
    id: "stats",
    label: "Stats",
    icon: "bars",
    hint: "leaders and the full national lists",
    items: [
      pageRow("leaders"),
      // ENH-10 (owner 2026-10-23): each opens the whole list, every qualified player and every team (views/stats.js)
      { heading: "The full lists" },
      pageRow("stats-passing", { id: "lead-passing" }),
      pageRow("stats-rushing", { id: "lead-rushing" }),
      pageRow("stats-receiving", { id: "lead-receiving" }),
      pageRow("stats-defense", { id: "lead-defense" }),
    ],
  },
  {
    id: "advanced",
    label: "Advanced stats",
    icon: "trend",
    hint: "SP+, Elo, FPI and talent for every team",
    items: [pageRow("ratings")],
  },
  {
    id: "knowledge",
    label: "Knowledge",
    icon: "book",
    hint: "the glossary, the trivia",
    items: [
      { id: "glossary", label: "Glossary", hint: "every stat and term the app uses", page: "glossary" },
      { id: "trivia-page", label: "Trivia", hint: "today's questions, the leaderboard, how it plays", page: "trivia" },
    ],
  },
  {
    id: "profile",
    label: "Profile",
    icon: "person",
    hint: "settings, setup, friends, the server",
    items: [
      // the Profile page has a tile for every section (board 7, owner 2026-10-22); the menu's rows for them went with ENH-46
      { id: "profile", label: "Profile", hint: "your settings and setup in one place", page: "profile" },
      { heading: "Elsewhere" },
      { id: "invite", label: "Invite friends", hint: "a QR code for the Wi-Fi", page: "invite" },
      { id: "connect", label: "Connect a device", hint: "the first-time setup for a tablet", href: "/setup", external: true },
      { id: "status", label: "Server status", hint: "the server's own page, in a new tab", href: "/status", external: true },
    ],
  },
  { id: "new", label: "New", icon: "sparkle", beta: true, hint: "what you are testing, also in its place", items: [] }, // filled below from TESTING
];

// New is his testing list (owner 2026-10-28: "I still want things I am testing to be there"; "After each test, we can decide
// where they go. Then the new tests end up in new."): a screen that already has its place stays in New as well until his test;
// then he decides where it goes and its id leaves this list. New hides only when nothing is left. A band under test is named
// "<page>:<band>" from the catalog: since ENH-46 New's row is the only row a band has.
const TESTING = [
  // the season as one line, Wave 2 (2026-10-30): the boxes, for his test
  "program:program-matchup",
  "program:program-matchup-last",
  "program:program-week",
  "program:program-talent",
  "program:program-schools",
  "program:program-trip",
  "program:program-scout",
  "program:program-recap", // the Post-Game stop (Wave 3): what decided it, the Box score box, the Circle of Blame for the game
  "program:program-box",
  "program:program-blame",
  "newspaper-bands", // My Teams
  "season", // My Team (2026-11-01): the Season page renamed, the team page's bands on it
  "top25", // FEAT-2 (2026-10-30): Picks of the week, a band of the Top 25 since wave 3 (2026-11-01)
  "conference", // the conference page (2026-11-02): any conference, ours first, for his test
];

/** New's copy of a row placed elsewhere: its own id ("new:<id>"), the same place to open. The copy keeps the row's getters,
 *  so an address read from the identity is read when it is drawn. */
function testing(entry) {
  if (!entry || typeof entry !== "object" || "heading" in entry) return entry;
  const copy = Object.defineProperties({}, Object.getOwnPropertyDescriptors(entry));
  copy.id = `new:${entry.id}`;
  if (Array.isArray(entry.items)) copy.items = entry.items.map(testing);
  return copy;
}

/** A row anywhere in the groups (lists included), by its id. */
function placed(id) {
  const walk = (items) => {
    for (const item of Array.isArray(items) ? items : []) {
      if (!item || typeof item !== "object" || "heading" in item) continue;
      if (item.id === id) return item;
      const deeper = Array.isArray(item.items) ? walk(item.items) : null;
      if (deeper) return deeper;
    }
    return null;
  };
  return walk(GROUPS.filter((g) => g.id !== "new"));
}

/** What an id of TESTING names: a row with its place in the groups, else a band of the catalog ("<page>:<band>"). */
function underTest(id) {
  const row = placed(id);
  if (row) return row;
  const at = String(id).indexOf(":");
  const page = at > 0 ? id.slice(0, at) : null;
  const band = page && BAND_PAGES[page] ? findBand(page, id.slice(at + 1)) : null;
  return band ? bandEntry(page, band) : null;
}

// New screens not placed anywhere yet sit in New alone, after the copies of what he is testing. None now: the Imperialism Map,
// the last one, went under National (owner 2026-11-15) and left New, as a placed screen does after his test.
const UNPLACED = [];

GROUPS.find((g) => g.id === "new").items = [...TESTING.map(underTest).filter(Boolean).map(testing), ...UNPLACED];

export const MENU = { tiles: TILES, groups: GROUPS };

const isEntry = (item) => item && typeof item === "object" && !("heading" in item);

/** The entries of a list that open something by themselves (headings and lower levels left out). */
export function entriesOf(items) {
  return (Array.isArray(items) ? items : []).filter((item) => isEntry(item) && !Array.isArray(item.items));
}

/** The list a path names: the opening level for [], else the group or list at its end. */
export function levelAt(menu, path) {
  let level = { id: "", label: "Menu", items: null };
  let items = Array.isArray(menu?.groups) ? menu.groups : [];
  for (const id of Array.isArray(path) ? path : []) {
    const next = items.find((item) => isEntry(item) && item.id === id && Array.isArray(item.items));
    if (!next) break;
    level = next;
    items = next.items;
  }
  return level;
}

/** The ids from the opening level down to the first entry `test` accepts (the entry's own id last), or null. */
export function findPath(menu, test) {
  const walk = (items, trail) => {
    for (const item of Array.isArray(items) ? items : []) {
      if (!isEntry(item)) continue;
      if (Array.isArray(item.items)) {
        const found = walk(item.items, [...trail, item.id]);
        if (found) return found;
      } else if (test(item)) return [...trail, item.id];
    }
    return null;
  };
  for (const tile of Array.isArray(menu?.tiles) ? menu.tiles : []) if (test(tile)) return [tile.id];
  return walk(menu?.groups, []);
}

/** Every entry at any depth, with where it sits ("My Teams › Florida"), for Search. */
export function allEntries(menu) {
  const out = [];
  const walk = (items, trail, section) => {
    for (const item of Array.isArray(items) ? items : []) {
      if (!item || typeof item !== "object") continue;
      if ("heading" in item) {
        section = value(item.heading);
        continue;
      }
      if (Array.isArray(item.items)) walk(item.items, [...trail, value(item.label)], null);
      else out.push({ entry: item, where: [...trail, section].filter(Boolean).join(" › ") });
    }
  };
  for (const tile of Array.isArray(menu?.tiles) ? menu.tiles : []) out.push({ entry: tile, where: "Game day" });
  for (const group of Array.isArray(menu?.groups) ? menu.groups : []) walk(group.items, [value(group.label)], null);
  return out;
}

export { value as labelOf };
