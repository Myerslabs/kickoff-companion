// The menu's tree (the layout pass, owner 2026-10-22, boards 2 to 4: https://claude.ai/artifact/NpbxneYraMKVB7diTvAvZh,
// https://claude.ai/artifact/4BBnTuogjVy6XPNoVc7WYP, https://claude.ai/artifact/4VVfYTQpLu1oyz8dz9xosZ). One level at a time:
// the opening level has Search, the six game-day tiles and the groups; a group slides its list in, and a list longer than
// about fourteen rows sends the rest one level down. He curates what is in it; anything new waits in New (beta) until he
// places it, and New hides while it is empty. Only entries that open something are listed: no dead ends.
//
// An entry is one of:
//   { id, label, hint, page }                  a page of the app ("season", or "leaders=passing:YDS:national")
//   { id, label, hint, href, external }        a page of the server's own (the status page), in a new tab
//   { id, label, hint, flyout }                a table opened wide by itself ("program:tape"; views/panels.js)
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

const TILES = [
  { id: "newspaper", label: "Newspaper", icon: "newspaper", page: "newspaper" },
  { id: "program", label: "Program", icon: "program", page: "program" },
  { id: "live", label: "In Game", icon: "live", page: "live" },
  { id: "board", label: "Big screen", icon: "tv", page: "board" },
  { id: "trivia", label: "Trivia", icon: "trivia", page: "trivia" },
  { id: "radio", label: "Radio", icon: "radio", flyout: "radio" },
];

// the matchup's tables in the Pre-Game Program's order (board 3: "the order is the Pre-Game Program's")
const MATCHUP = [
  { id: "tape", label: "Tale of the tape", hint: "each unit's national rank against the unit it faces", flyout: "program:tape" },
  { id: "leaders-pair", label: "Leaders side by side", hint: "both teams' leaders, category by category", flyout: "program:leaders" },
  { id: "lineups", label: "Lineups", hint: "the starters' experience, then the matchups", flyout: "program:lineups" },
  { id: "advanced-matchup", label: "Advanced matchup", hint: "PPA, success rate and explosiveness, side by side", flyout: "program:advanced" },
  { id: "tendencies", label: "Tendencies", hint: "the shot chart and the calls by down and distance", flyout: "program:tendencies" },
  { id: "talent", label: "Talent and recruiting", hint: "the two rosters' stars and talent", flyout: "program:recruiting" },
  { id: "play-value", label: "Play value", hint: "expected points by play type", flyout: "program:ppa" },
  { id: "availability", label: "Availability report", hint: "who is out, doubtful or questionable", flyout: "program:availability" },
  { id: "visitors", label: "Recruits on hand", hint: "the recruits visiting this week", flyout: "program:visitors" },
  { id: "common", label: "Common opponents", hint: "teams both of us have played", flyout: "program:common" },
  { id: "series", label: "Series", hint: "the all-time series, game by game", flyout: "program:series" },
  { id: "notes", label: "Program notes", hint: "the week's notes, with your own lines first", flyout: "program:notes" },
  { id: "headlines", label: "Headlines", hint: "the week's news about us", flyout: "program:headlines" },
  { id: "race", label: "What we need", hint: "the conference race and whom to pull for", flyout: "program:race" },
];

// In Game's panels in its own order (views/live.js remoteItems), each opened wide over In Game
const IN_GAME = [
  { id: "ig-box", label: "Box score", hint: "both teams, every player", live: "box" },
  { id: "ig-drives", label: "Drives", hint: "every drive and how it ended", live: "drives" },
  { id: "ig-splits", label: "Splits", hint: "quarter by quarter", live: "splits" },
  { id: "ig-plays", label: "Plays", hint: "the play by play", live: "plays" },
  { id: "ig-situation", label: "Situation", hint: "third downs, red zone, win probability", live: "situation" },
  { id: "ig-edges", label: "Edges", hint: "season ranks against each other", live: "edges" },
  { id: "ig-weather", label: "Weather", hint: "at the game site", live: "weather" },
  { id: "ig-visitors", label: "Visitors", hint: "the recruits on hand", live: "visitors" },
  { id: "ig-injuries", label: "Injuries", hint: "the availability report", live: "injuries" },
  { id: "ig-lineups", label: "Lineups", hint: "starters and depth", live: "lineups" },
  { id: "ig-scores", label: "Scores", hint: "around the country", live: "scores" },
  { id: "ig-value", label: "Play value", hint: "after the final", live: "value" },
];

const AFTER_FINAL = [
  { id: "final-box", label: "Final box", hint: "the box score once the game is over", flyout: "program:final" },
  { id: "advanced-box", label: "Advanced box score", hint: "PPA, success rate and havoc for the game", flyout: "program:advancedBox" },
  { id: "results", label: "Expectations and results", hint: "the program at kickoff held against the result", flyout: "program:results" },
  { id: "news", label: "The game in the news", hint: "articles about the game after the final", flyout: "program:news" },
];

const GROUPS = [
  {
    id: "teams",
    label: "My Teams",
    icon: "shield",
    hint: () => `${usName()}, the season, your other teams`,
    items: [
      { heading: () => usName() },
      { id: "season", label: "Season", hint: "every team you follow: schedule, standings, polls", page: "season" }, // board 9: My Teams and the Season are one page
      { id: "roster", label: "Roster", hint: "depth chart, impact players, position groups", page: "roster" },
      { id: "recruiting", label: "Recruiting", hint: "the class, where they're from, visitors", page: "recruiting" },
      { id: "injuries", label: "Injury Report", hint: "who is out, season-long", page: "injuries" },
      { id: "review", label: "Season in review", hint: "the season told from the schedule", page: "review" },
      { id: "preseason", label: "Preseason Magazine", hint: "offseason, outlook, staffs", page: "preseason" },
      { id: "archive", label: "Archive", hint: "every game the app watched", page: "archive" },
      { heading: "The app's data" },
      { id: "prompts", label: "Load data", hint: "copy, paste or run the prompts", page: "prompts" },
    ],
  },
  {
    id: "game",
    label: "This week's game",
    icon: "matchup",
    hint: "the matchup's tables and In Game's panels",
    sub: "game", // the game it is about, from views/panels.js
    items: [
      { heading: "The matchup" },
      ...MATCHUP,
      { heading: "More" },
      { id: "ingame", label: "In Game's panels", hint: "box score, drives, plays, situation and more", items: IN_GAME },
      { id: "afterfinal", label: "After the final", hint: "final box, advanced box, results, the news", items: AFTER_FINAL },
    ],
  },
  {
    id: "national",
    label: "National",
    icon: "globe",
    hint: "Top 25, the polls, recruiting",
    items: [
      { id: "top25", label: "Top 25", hint: "every game of the week with a ranked team", page: "top25" },
      { id: "poll-ap", label: "AP poll", hint: "this week's poll and its movement", page: "season=polls:AP" },
      { id: "poll-coaches", label: "Coaches poll", hint: "this week's poll and its movement", page: "season=polls:Coaches" },
      { id: "recruiting-national", label: "National recruiting", hint: "every class, ranked", page: "recruiting=national" },
    ],
  },
  {
    id: "stats",
    label: "Stats",
    icon: "bars",
    hint: "leaders by position",
    items: [
      { id: "leaders", label: "Leaders", hint: "every category on one page", page: "leaders" },
      { heading: "Players" },
      { id: "lead-passing", label: "Passing", hint: "passing yards, national", page: "leaders=passing:YDS:national" },
      { id: "lead-rushing", label: "Rushing", hint: "rushing yards, national", page: "leaders=rushing:YDS:national" },
      { id: "lead-receiving", label: "Receiving", hint: "receiving yards, national", page: "leaders=receiving:YDS:national" },
      { id: "lead-defense", label: "Defense", hint: "tackles, national", page: "leaders=defensive:TOT:national" },
    ],
  },
  {
    id: "advanced",
    label: "Advanced stats",
    icon: "trend",
    hint: "ratings, PPA, usage, our grades",
    items: [
      { heading: "Team ratings" },
      { id: "ratings", label: "Advanced Team Ratings", hint: "SP+, Elo, FPI and talent for every team", page: "ratings" },
      { id: "rating-sp", label: "SP+", hint: "sorted by SP+", page: "ratings=sp" },
      { id: "rating-elo", label: "Elo", hint: "sorted by Elo", page: "ratings=elo" },
      { heading: "Players" },
      { id: "lead-usage", label: "Usage", hint: "who gets the ball, national", page: "leaders=usage:overall:national" },
      { id: "lead-ppa", label: "PPA", hint: "points added per play, national", page: "leaders=ppa:all:national" },
    ],
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
      { id: "profile", label: "Profile", hint: "your settings and setup in one place", page: "profile" },
      // board 7, A (owner 2026-10-22, "Everything else is good"): every section of the Profile, each opening its flyout there
      { heading: "Settings" },
      { id: "profile-gameday", label: "Game day", hint: "the spoiler delay, the radio, the ticker", page: "profile=gameday" },
      { id: "profile-trivia", label: "Trivia", hint: "the popups, the leaderboard, the pace", page: "profile=trivia" },
      { id: "profile-display", label: "Display", hint: "the theme, the text size, the hints", page: "profile=display" },
      { id: "profile-teams", label: "Your teams", hint: "the home team, primary and secondary", page: "profile=teams" },
      { id: "profile-friends", label: "Friends and the big screen", hint: "the host PIN, the board on a monitor", page: "profile=friends" },
      { id: "profile-radio", label: "Radio stations", hint: "add your team's station", page: "profile=radio" },
      { id: "profile-claude", label: "Claude and loading data", hint: "Claude Code, the schedule, what is missing", page: "profile=claude" },
      { id: "profile-server", label: "Server Settings", hint: "start at login, backups, HTTPS, restart", page: "profile=server" },
      { id: "profile-about", label: "About and help", hint: "the CFBD key and plan, the version, the files", page: "profile=about" },
      { id: "profile-setup", label: "Setup", hint: "first time setup, the demo, the Archive", page: "profile=setup" },
      { id: "profile-feedback", label: "Feedback", hint: "the reports sent, with their logs", page: "profile=feedback" }, // owner 2026-10-23
      { heading: "Elsewhere" },
      { id: "invite", label: "Invite friends", hint: "a QR code for the Wi-Fi", page: "invite" },
      { id: "connect", label: "Connect a device", hint: "the first-time setup for a tablet", href: "/setup", external: true },
      { id: "status", label: "Server status", hint: "the server's own page, in a new tab", href: "/status", external: true },
    ],
  },
  { id: "new", label: "New", icon: "sparkle", beta: true, hint: "new screens waiting for a place", items: [] },
];

export const MENU = { tiles: TILES, groups: GROUPS };

const isEntry = (item) => item && typeof item === "object" && !("heading" in item);
const value = (v) => (typeof v === "function" ? v() : v);

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

/** Every entry at any depth, with where it sits ("This week's game › The matchup"), for Search. */
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
