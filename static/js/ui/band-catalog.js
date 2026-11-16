// Every band of every data page, by page (owner 2026-10-28: "I want to make sure that each band has its own flyout, and page
// as well as grouped together somewhere"; "each bands should live on a page where it is together with other like stats, and
// also its own page for detailed viewing"; reached "Only from the menu", where "Page opens its list"). The page stays where
// the bands sit together; the menu's row of a page opens its list, the whole page first, then each band, which opens wide
// by itself (views/panels.js), with Own page in the flyout's head: the band alone, across the whole page, at
// #band=<page>:<band> (views/band.js). The lists are in each page's own order.
// ENH-46 (owner 2026-11-10: "I dont think we need a menu item for things on that page"): the menu lists pages only. This
// catalog still names every band, and is now what opens one by itself: the button in a band's head on its page
// (ui/band-open.js reads catalogOf and bandsOf), Search (allBands), the flyout's Own page and the band's own page.
//
// A band is { id, label, hint } with, as needed:
//   key      the Pre-Game Program's own flyout builder (PROGRAM_BANDS in views/program.js), for the tables it already had
//   select   a selector for a band whose id carries a game or a team (the first match); `id` is then the catalog's own name
//   route    the page's address for this band when it is not the page's own ("stats=passing" for the players' list)
//   params   that address's query ({ view: "teams" }, { tab: "history" })
//   panel    In Game: the panel of views/live.js it is
//
//   BAND_PAGES                  { <page>: { label, hint, route, bands } }, route a hash without "#" (or a function of the identity)
//   bandsOf(page)               the page's bands ([] for none)
//   findBand(page, id)          one band, or null
//   pageRoute(page, band)       the address of the page the band is drawn from, query included ("stats=passing?view=teams")
//   bandHref(page, id)          "#band=<page's route>:<id>" (with the page's query): the band's own page
//   parseBandArg(arg)           "stats=passing:stats-teams" -> { route: "stats=passing", page: "stats", id: "stats-teams" }, or null
//   catalogOf(route)            the catalog page of an address on screen ("team=Georgia" -> "season"), or null
//   allBands()                  every band of every page as an entry Search can open: [{ page, entry, where }]
//   pageList(page, { hint })    a page's list, the whole page then each band: the menu's until ENH-46, now the list the
//                               flyout's previous and next walk when Search opens a band (views/search.js)

import { confLabel, usSchool } from "../identity.js";

const value = (v) => (typeof v === "function" ? v() : v);

const PROGRAM = [
  { id: "program-notes", key: "notes", label: "Program notes", hint: "the week's notes, with your own lines first" },
  { id: "program-headlines", key: "headlines", label: "Headlines", hint: "the week's news about us" },
  // the season as one line, Wave 2 (the owner's board of 2026-10-30): the like bands in their boxes; a box's other views are
  // their own rows, flyouts and pages (`select` finds the box on the page, `params` opens it on that view)
  { id: "program-matchup", key: "matchup", label: "The matchup", hint: "Strengths and weaknesses, then every unit against the unit it faces" },
  { id: "program-matchup-last", key: "matchupLast", select: "#program-matchup", params: { view: "last" }, label: "The matchup · Last season", hint: "both teams' last season, the offense beside the defense" },
  { id: "program-week", key: "week", label: "Margin by week", hint: "both teams' margins, game by game" }, // wave 3 (2026-11-01): the poll path is My Team's, Play value by game the Ratings page's
  { id: "program-visitors", key: "visitors", label: "Recruits on hand", hint: "the recruits visiting this week" },
  { id: "program-availability", key: "availability", label: "Availability report", hint: "who is out, doubtful or questionable" },
  { id: "program-leaders", key: "leaders", label: "Leaders side by side", hint: "both teams' leaders, category by category" },
  { id: "program-talent", key: "talent", label: "Talent", hint: "both rosters by position group, returning production, the cost and the classes" },
  { id: "program-lineups", key: "lineups", label: "Lineups", hint: "both lineups on the field, each man a tap to his card" }, // the picture alone since 2026-11-01
  { id: "program-tendencies", key: "tendencies", label: "Tendencies", hint: "the shot chart and the calls by down and distance" },
  { id: "program-schools", key: "schools", label: "The two schools and the series", hint: "the schools side by side, every meeting, the common opponents" },
  { id: "program-trip", key: "trip", label: "Getting there", hint: "the way to the stadium, parking, tailgating and the gates, printable" }, // ENH-15 (2026-10-30)
  { id: "program-scout", label: "Scouting report", hint: "Claude's report on the opponent" },
  // wave 3 of the one-column page (owner 2026-11-01, his inventory): the Pre-Game's arrivals, at the bottom until he reorders them
  { id: "program-resume", key: "resume", label: "Résumé", hint: "our expected wins, the schedule's strength, the poll path" },
  { id: "roster-stars", key: "stars", label: "Recruiting stars on the roster", hint: "the roster by recruiting stars" },
  { id: "roster-impact", key: "impact", label: "Impact players", hint: "who makes the plays" },
  { id: "team-staff", key: "staff", label: "Staff", hint: "the head coach, the coordinators, the staff" },
  // the Post-Game stop (the season as one line, Wave 3, the owner's board of 2026-10-30), in its order
  { id: "program-recap", label: "What decided it", hint: "Claude's account of the game, the morning after" },
  { id: "program-box", key: "box", label: "Box score", hint: "the score by quarter, both teams' stats and every player" },
  { id: "program-box-advanced", key: "boxAdvanced", select: "#program-box", params: { view: "advanced" }, label: "Box score · Advanced", hint: "PPA, success rate and havoc by quarter, the players' value" },
  { id: "program-results", key: "results", label: "Expectations and results", hint: "the program at kickoff held against the result" },
  { id: "program-blame", key: "blame", label: "Circle of Blame", hint: "the blame for this game, from Claude's Sunday report" },
  { id: "program-news", key: "news", label: "The game in the news", hint: "articles about the game after the final" },
  // wave 3 (owner 2026-11-01, his inventory): the Post-Game's arrivals, as the numbers stand with the game counted, at the bottom
  { id: "archive-stats", key: "stats", label: "Team stats", hint: "the game's team stats, from its archive" },
  { id: "archive-drives", key: "drives", label: "Drives", hint: "every drive of the game and how it ended" },
  { id: "archive-plays", key: "plays", label: "Play by play", hint: "the game's plays" },
  { id: "archive-ppa", key: "ppaGame", label: "Play value", hint: "the game's points added per play, team and player" },
  { id: "program-weather", key: "weather", label: "Weather", hint: "at the game site" },
  { id: "program-road", key: "road", label: "Road ahead", hint: "the games left" },
  { id: "program-print", label: "Print", hint: "the program on paper or as a PDF" }, // the last band (owner 2026-11-07)
  { id: "program-lessons", key: "lessons", label: "What Claude learned", hint: "the lessons of the weekly reviews" },
  { id: "blame-wheel", label: "The wheel", hint: "Claude's weekly blame by share, the verdict" },
  { id: "blame-case", label: "The case", hint: "the selected slice's case and evidence" },
  { id: "blame-moved", label: "What moved", hint: "since last week, and what the pack lacked" },
  { id: "blame-season", label: "The season (blame)", hint: "each week's top slice and its shares" },
];

// In Game's panels in its own order (views/live.js remoteItems), then the two of its stage that have no panel
const LIVE = [
  { id: "box", panel: "box", label: "Box score", hint: "both teams, every player" },
  { id: "drives", panel: "drives", label: "Drives", hint: "every drive and how it ended" },
  { id: "splits", panel: "splits", label: "Splits", hint: "quarter by quarter" },
  { id: "plays", panel: "plays", label: "Plays", hint: "the play by play" },
  { id: "situation", panel: "situation", label: "Situation", hint: "third downs, red zone, win probability" },
  { id: "edges", panel: "edges", label: "Edges", hint: "season ranks against each other" },
  { id: "weather", panel: "weather", label: "Weather", hint: "at the game site" },
  { id: "scores", panel: "scores", label: "Scores", hint: "around the country" },
  { id: "radio", panel: "radio", label: "Radio", hint: "the station, opened wide" }, // wave 3 (2026-11-01): the radio is In Game's; Visitors, Injuries, Lineups and Play value left for the program
  { id: "score", panel: "score", label: "Score by quarter", hint: "the line score, with the trivia's standings" },
  { id: "chart", panel: "chart", label: "Shot chart", hint: "passes by zone and runs by lane, the offense on the field" },
];

const STATS = (category, noun) => [
  { id: "stats-players", route: `stats=${category}`, label: "Every qualified player", hint: `every ${noun} at or over the minimum` },
  { id: "stats-teams", route: `stats=${category}`, params: { view: "teams" }, label: "Every team's offense", hint: "its own numbers, every FBS team" },
  { id: "stats-allowed", route: `stats=${category}`, params: { view: "teams" }, label: "Every team's defense", hint: "what it allowed, every FBS team" },
];

export const BAND_PAGES = {
  season: {
    label: "My Team", // the Season page until 2026-11-01 (owner: "my team and season are the same in my eyes"); the address stays #season
    hint: "the season: schedule, standings, polls, the numbers",
    route: "season",
    bands: [
      // the playoff band shows only while the team is in the AP Top 25, first on the page from week 8 (the owner's test of
      // 2026-10-28: "The college football playoff is not listed?")
      { id: "season-playoff", label: "College Football Playoff", hint: "the bracket as it stands, while the team is ranked" },
      { id: "season-schedule", label: "Schedule", hint: "every game, its result or its line" },
      { id: "season-standings", label: () => `${confLabel() || "Conference"} standings`, hint: "the conference table, with the race" },
      { id: "season-ratings", label: "Ratings", hint: "SP+, FPI, Elo and the rest, with their ranks" },
      { id: "season-resume", label: "Résumé", hint: "the wins and losses that count" },
      { id: "season-profile", label: "Stat profile", hint: "each stat with its national rank" },
      { id: "season-trends", label: "Trends, week by week", hint: "points and yards game by game" },
      { id: "season-road", label: "Road ahead", hint: "the games left" },
      { id: "season-last", label: "This season and last", hint: "the two seasons side by side" },
      // the Season stop (the season as one line, Wave 4, the owner's board of 2026-10-30): The numbers box and its views, Our land
      { id: "season-numbers", label: "The numbers", hint: "advanced measures" },
      { id: "season-advanced", select: "#season-numbers", params: { view: "advanced" }, label: "The numbers · Advanced", hint: "PPA, success rate and explosiveness, national ranks" },
      { id: "season-land", label: "Our land", hint: "the team's land on the Imperialism Map, taken and lost" },
      // wave 3 of the one-column page (owner 2026-11-01, his inventory picks): the team page's, the roster's, the recruiting's
      // and the Circle of Blame's bands on My Team, in the inventory's order, at the bottom until he reorders them
      { id: "season-injuries", label: "Availability report", hint: "who is out, doubtful or questionable, from the game notes" },
      { id: "team-recruiting", label: "Talent and recruiting", hint: "the roster's talent, the blue-chip ratio and returning production" },
      { id: "season-tendencies", label: "Tendencies", hint: "both offenses' calls by down and distance, the shot chart" },
      { id: "season-trip", label: "Getting there", hint: "the way to the next game's stadium, parking and the gates" },
      { id: "season-race", label: "What we need", hint: "the conference race and whom to pull for" },
      { id: "roster-breakdown", label: "Roster breakdown", hint: "the roster by class and position" },
      { id: "roster-costs", label: "Roster costs (rumored)", hint: "the rumored budget by position" },
      { id: "roster-table", label: "Roster", hint: "every player" },
      { id: "roster-stars", label: "Recruiting stars on the roster", hint: "the roster by recruiting stars" },
      { id: "roster-impact", label: "Impact players", hint: "who makes the plays" },
      { id: "recruiting-class", label: "The class", hint: "this year's signees and their ranks" },
      { id: "recruiting-where", label: "Where they're from", hint: "the class by state" },
      { id: "team-staff", label: "Staff", hint: "the head coach, the coordinators, the staff" },
      { id: "team-playvalue", label: "Play value and usage", hint: "who gets the ball and what it is worth" },
      { id: "team-facts", label: "School facts", hint: "the school, the stadium, the titles" },
      { id: "season-stars", label: "Players to know", hint: "the preseason's players to know, with this season's numbers" },
      { id: "blame-wheel", label: "Circle of Blame", hint: "Claude's weekly blame by share, the verdict" },
      { id: "season-lineup", label: "Lineup", hint: "our defense over our offense on the field, each man a tap to his card" }, // the lineup picture (owner 2026-11-01), at the bottom until he places it
      { id: "blame-case", label: "The case", hint: "the selected slice's case and evidence" },
      { id: "blame-moved", label: "What moved", hint: "since last week, and what the pack lacked" },
      { id: "blame-season", label: "The season (blame)", hint: "each week's top slice and its shares" },
    ],
  },
  roster: {
    label: "Roster",
    hint: "the breakdown, the costs, every player, the stars, impact players",
    route: "roster",
    bands: [
      { id: "roster-breakdown", label: "Roster breakdown", hint: "the roster by class and position" },
      { id: "roster-costs", label: "Roster costs (rumored)", hint: "the rumored budget by position" },
      { id: "roster-table", label: "Roster", hint: "every player" },
      { id: "roster-stars", label: "Recruiting stars on the roster", hint: "the roster by recruiting stars" },
      { id: "roster-impact", label: "Impact players", hint: "who makes the plays" },
    ],
  },
  recruiting: {
    label: "Recruiting",
    hint: "the class, where they're from, visitors",
    route: "recruiting",
    bands: [
      { id: "recruiting-class", label: "The class", hint: "this year's signees and their ranks" },
      { id: "recruiting-where", label: "Where they're from", hint: "the class by state" },
      { id: "recruiting-visitors", label: "Visitors", hint: "the recruits on hand this week" },
    ],
  },
  preseason: {
    label: "Preseason Magazine",
    hint: "offseason, outlook, staffs",
    route: "preseason",
    bands: [
      { id: "preseason-loads", label: "Season loads", hint: "what Claude loaded for the season" },
      { id: "preseason-home", select: 'section.band[id^="preseason-"]:not(#preseason-loads):not(#preseason-headlines):not(#preseason-trip):not(#preseason-polls):not(#preseason-ratings):not(#preseason-lineup)', label: () => usSchool(), hint: "the offseason, the outlook, the staff" },
      // wave 3 (owner 2026-11-01, his inventory): the magazine's arrivals, at the bottom until he reorders them
      { id: "preseason-headlines", label: "Headlines", hint: "the news about us, from the feeds" },
      { id: "team-recruiting", label: "Talent and recruiting", hint: "the roster's talent, the blue-chip ratio and returning production" },
      { id: "preseason-trip", label: "Getting there", hint: "the way to the next game's stadium" },
      { id: "preseason-polls", label: "Polls", hint: "the AP and Coaches polls, week by week" },
      { id: "preseason-ratings", label: "Ratings", hint: "our SP+, Elo and FPI with their ranks" },
      { id: "roster-breakdown", label: "Roster breakdown", hint: "the roster by class and position" },
      { id: "roster-costs", label: "Roster costs (rumored)", hint: "the rumored budget by position" },
      { id: "roster-table", label: "Roster", hint: "every player" },
      { id: "roster-stars", label: "Recruiting stars on the roster", hint: "the roster by recruiting stars" },
      { id: "roster-impact", label: "Impact players", hint: "who makes the plays" },
      { id: "recruiting-class", label: "The class", hint: "this year's signees and their ranks" },
      { id: "recruiting-where", label: "Where they're from", hint: "the class by state" },
      { id: "team-staff", label: "Staff", hint: "the head coach, the coordinators, the staff" },
      { id: "team-facts", label: "School facts", hint: "the school, the stadium, the titles" },
      { id: "preseason-lineup", label: "Lineup", hint: "our defense over our offense on the field, from the next game's chart" }, // the lineup picture (owner 2026-11-01), at the bottom until he places it
    ],
  },
  archive: {
    label: "Archive",
    hint: "every game the app watched",
    route: "archive",
    bands: [
      { id: "archive-list", label: "Archived games", hint: "every game the app watched, newest first" },
      { heading: "The last game watched" },
      { id: "archive-stats", route: "archive=latest", label: "Team stats", hint: "both teams, side by side" },
      { id: "archive-wp", route: "archive=latest", label: "Win probability", hint: "the chart, play by play" },
      { id: "archive-advanced-box", route: "archive=latest", label: "Advanced box score", hint: "PPA, success rate and havoc" },
      { id: "archive-ppa", route: "archive=latest", label: "Play value", hint: "expected points by play type" },
      { id: "archive-drives", route: "archive=latest", label: "Drives", hint: "every drive and how it ended" },
      { id: "archive-plays", route: "archive=latest", label: "Play by play", hint: "every play" },
      { id: "archive-box", route: "archive=latest", label: "Box score", hint: "both teams, every player" },
      { id: "archive-notes", route: "archive=latest", label: "Program notes of the week", hint: "the notes as they stood" },
      { id: "archive-availability", route: "archive=latest", label: "Availability report", hint: "who was out" },
    ],
  },
  // the team page's entry went with wave 3 of the one-column page (2026-11-01): #team=<school> is My Team's page of that team
  program: { label: "Pre-Game Program", hint: "the whole program, as it reads on the page", route: "program", bands: PROGRAM },
  live: { label: "In Game", hint: "the whole screen", route: "live", bands: LIVE },
  newspaper: {
    label: "Newspaper",
    hint: "this week's paper, then the earlier weeks",
    route: "newspaper",
    bands: [
      { id: "np-page-1", label: "Front page", hint: "this week's lead stories" },
      { id: "np-page-2", label: "Page 2", hint: "more about us" },
      { id: "np-page-3", label: "Page 3", hint: "the rest of the week, by section" },
      { id: "np-polls", label: "Polls", hint: "the AP and Coaches polls, week by week" }, // wave 3 (2026-11-01): from My Team; the Top 25's Saturday left for the Top 25 page
      { id: "paper-stories", label: "The week's stories and picks", hint: "Claude's stories and picks" },
      { id: "np-weeks", select: ".np-weeks", label: "Earlier weeks", hint: "every week of the paper, folded" },
    ],
  },
  leaders: {
    label: "Leaders",
    hint: "every category on one page, the top ten",
    route: "leaders",
    bands: [
      { id: "leaders-passing-YDS", label: "Passing yards", hint: "the top ten" },
      { id: "leaders-rushing-YDS", label: "Rushing yards", hint: "the top ten" },
      { id: "leaders-receiving-YDS", label: "Receiving yards", hint: "the top ten" },
      { id: "leaders-defensive-TOT", label: "Tackles", hint: "the top ten" },
      { id: "leaders-defensive-SACKS", label: "Sacks", hint: "the top ten" },
      { id: "leaders-interceptions-INT", label: "Interceptions", hint: "the top ten" },
      { id: "leaders-kicking-FGM", label: "Field goals made", hint: "the top ten" },
      { id: "leaders-punting-YPP", label: "Punting average", hint: "the top ten" },
      { id: "leaders-ppa-all", label: "Play value, PPA per play", hint: "points added per play" },
      { id: "leaders-usage-overall", label: "Usage", hint: "the share of the team's plays" },
      { id: "leaders-wepa-passing", label: "Adjusted passing EPA", hint: "per play, opponent-adjusted" },
      { id: "leaders-wepa-rushing", label: "Adjusted rushing EPA", hint: "per play, opponent-adjusted" },
      { id: "leaders-paar-kicking", label: "Kicker points above replacement", hint: "points added above replacement" },
      { id: "leaders-grades", label: "Top graded", hint: "our own stat grades" },
    ],
  },
  "stats-passing": { label: "Passing", hint: "every qualified passer and every team", route: "stats=passing", bands: STATS("passing", "passer") },
  "stats-rushing": { label: "Rushing", hint: "every qualified rusher and every team", route: "stats=rushing", bands: STATS("rushing", "rusher") },
  "stats-receiving": { label: "Receiving", hint: "every qualified receiver and every team", route: "stats=receiving", bands: STATS("receiving", "receiver") },
  "stats-defense": { label: "Defense", hint: "every qualified defender and every team", route: "stats=defense", bands: STATS("defense", "defender") },
  // FEAT-17 (owner 2026-10-30, "Build as drawn"): the map, Most land, ours
  imperialism: {
    label: "Imperialism Map",
    hint: "FBS land by enrollment, carved by the season's results",
    route: "imperialism",
    bands: [
      { id: "imp-map", label: "The map", hint: "every school's land, week by week, with Play" },
      { id: "imp-land", label: "Most land", hint: "the fifteen biggest holders and their week" },
      { id: "imp-us", label: "Our land", hint: "our cells by week, what we took and lost, the next game's stakes" },
    ],
  },
  // FEAT-18's Circle of Blame page dissolved into My Team and the Post-Game (wave 3 of the one-column page, 2026-11-01)
  ratings: {
    label: "Advanced Team Ratings",
    hint: "SP+, Elo, FPI and talent for every team",
    route: "ratings",
    bands: [
      { id: "ratings-sp", label: "SP+", hint: "every FBS team by SP+" },
      { id: "ratings-more", label: "CORE, SRS and adjusted EPA", hint: "the other ratings" },
      { id: "ratings-conferences", label: "Conference SP+", hint: "each conference's average" },
      { id: "ratings-side", label: "Ratings side by side", hint: "every rating, team by team" },
      // wave 3 (owner 2026-11-01, his inventory): our own ratings, advanced measures and play value by game, at the bottom
      { id: "ratings-ours", label: "Our ratings", hint: "our SP+, Elo and FPI with their ranks" },
      { id: "ratings-advanced", label: "Advanced", hint: "our PPA, success rate and explosiveness, national ranks" },
      { id: "ratings-ppa", label: "Play value by game", hint: "our points added per play, game by game" },
    ],
  },
  // the conference page (owner 2026-11-02, the board "Build as drawn"):
  // any conference, ours first; the chips on the page lead to the others, the band's own page keeps the conference
  conference: {
    label: "Conferences",
    hint: "the SEC first, any conference: against the rest, standings, the week, the teams rated, leaders, its land",
    route: "conference",
    bands: [
      { id: "conf-against", label: "Against the rest", hint: "Conference SP+, or every conference's teams averaged" },
      { id: "conf-against-numbers", select: "#conf-against", params: { view: "numbers" }, label: "Against the rest · By the numbers", hint: "pass and rush yards, allowed, sacks, takeaways, each conference ranked" },
      { id: "conf-standings", label: "Standings", hint: "the race played out: where each team can still finish" },
      { id: "conf-week", label: "This week", hint: "every game with a team of the conference, the line, the pick, pull for" },
      { id: "conf-rated", label: "The teams, rated", hint: "SP+, Elo, FPI, talent and Talent Edge, with FBS ranks" },
      { id: "conf-leaders", label: "Leaders", hint: "the conference's top five passers, rushers, receivers and tacklers" },
      { id: "conf-land", label: "Its land", hint: "each school's land on the Imperialism Map, the week's change" },
    ],
  },
  // wave 3 (owner 2026-11-01, his inventory): the Top 25 page carries the picks and Watch it live
  top25: {
    label: "Top 25",
    hint: "every game of the week with a ranked team, the picks, Watch it live",
    route: "top25",
    bands: [
      { id: "top25-picks", label: "Picks of the week", hint: "every game picked by Claude, the line beside" },
    ],
  },
};

const isBand = (item) => item && typeof item === "object" && typeof item.id === "string";

export function bandsOf(page) {
  const bands = BAND_PAGES[page]?.bands;
  return Array.isArray(bands) ? bands.filter(isBand) : [];
}

export function findBand(page, id) {
  return bandsOf(page).find((b) => b.id === id) || null;
}

function query(params) {
  const pairs = Object.entries(params && typeof params === "object" ? params : {}).filter(([, v]) => typeof v === "string" && v);
  return pairs.length ? `?${pairs.map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`).join("&")}` : "";
}

export function pageRoute(page, band = null) {
  const route = band && typeof band.route === "string" ? band.route : value(BAND_PAGES[page]?.route) || page;
  return `${route}${query(band?.params)}`;
}

export function bandHref(page, id) {
  const band = findBand(page, id);
  const route = pageRoute(page, band);
  const at = route.indexOf("?");
  const [path, tail] = at >= 0 ? [route.slice(0, at), route.slice(at)] : [route, ""];
  return `#band=${path}:${id}${tail}`;
}

/** The band route's argument: the page's address, then ":" and the band (split at the last colon: a page's own argument
 *  may hold colons, "leaders=passing:YDS:national", a band's id never does). */
export function parseBandArg(arg) {
  if (typeof arg !== "string") return null;
  const at = arg.lastIndexOf(":");
  if (at <= 0 || at === arg.length - 1) return null;
  const route = arg.slice(0, at);
  const id = arg.slice(at + 1);
  if (!/^[A-Za-z][\w-]*$/.test(id)) return null;
  const eq = route.indexOf("=");
  const page = eq >= 0 ? route.slice(0, eq) : route;
  if (!/^[a-z0-9]+$/i.test(page)) return null;
  return { route, page, id };
}

// Addresses that draw another page's bands: a team's page is My Team's of that team and #blame is My Team's (wave 3 of the
// one-column page, 2026-11-01), the Post-Game stop draws the program's, #picks is the Top 25's
const SAME_BANDS = { team: "season", blame: "season", postgame: "program", picks: "top25" };

/** The catalog page a band route names: the stats lists are one page each by category. */
export function catalogPage(parsed) {
  if (!parsed) return null;
  if (parsed.page === "stats") {
    const category = String(parsed.route.split("=")[1] || "passing").split("?")[0];
    return BAND_PAGES[`stats-${category}`] ? `stats-${category}` : null;
  }
  const page = SAME_BANDS[parsed.page] || parsed.page;
  return Object.prototype.hasOwnProperty.call(BAND_PAGES, page) ? page : null; // never a name every object answers to
}

/** The catalog page of an address on screen ("#team=Georgia", "stats=passing?view=teams", "postgame=401"), or null. */
export function catalogOf(route) {
  const path = String(route ?? "").replace(/^#/, "").split("?")[0];
  if (!path) return null;
  const eq = path.indexOf("=");
  const page = eq >= 0 ? path.slice(0, eq) : path;
  if (!/^[a-z0-9]+$/i.test(page)) return null;
  return catalogPage({ page, route: path });
}

/** Every band of every page as an entry Search can open, with its page's name: the menu lists pages only (ENH-46). */
export function allBands() {
  const out = [];
  for (const [page, meta] of Object.entries(BAND_PAGES)) {
    for (const band of bandsOf(page)) out.push({ page, entry: bandEntry(page, band), where: String(value(meta.label) || "") });
  }
  return out;
}

/** The Own page of a menu entry that opens wide: its band's page, or null (the radio's station list has none). `route`
 *  overrides the page's address (the Pre-Game Program of the game on screen, "program=<id>"). */
export function ownHref(entry, { route = null } = {}) {
  const [source, a, b] = String(entry?.flyout || "").split(":");
  let page = null;
  let id = null;
  if (source === "program") {
    page = "program";
    id = bandsOf("program").find((band) => band.key === a)?.id || null;
  } else if (source === "band") {
    page = a;
    id = b;
  } else if (entry?.live) {
    page = "live";
    id = entry.live;
  }
  if (!page || !id) return null;
  if (!route) return bandHref(page, id);
  const [path, tail] = route.includes("?") ? [route.slice(0, route.indexOf("?")), route.slice(route.indexOf("?"))] : [route, ""];
  return `#band=${path}:${id}${tail}`;
}

/** The menu's entry of one band: the program's own builders where it has them, In Game's panels over In Game, the rest by
 *  themselves from their page (views/panels.js). */
export function bandEntry(page, band) {
  const base = { id: `${page}:${band.id}`, label: band.label, hint: band.hint };
  if (page === "program" && band.key) return { ...base, flyout: `program:${band.key}`, band: band.id };
  if (page === "live") return { ...base, live: band.panel || band.id };
  return { ...base, flyout: `band:${page}:${band.id}` };
}

/** A page's list in the menu: the whole page first, then its bands in its own order (headings kept). */
export function pageList(page, { hint = null, only = null } = {}) {
  const meta = BAND_PAGES[page];
  if (!meta) return [];
  const items = (Array.isArray(meta.bands) ? meta.bands : []).filter((b) => !only || !isBand(b) || only.includes(b.id));
  return [
    {
      id: `${page}:page`,
      label: "The whole page",
      searchLabel: meta.label,
      hint: hint || meta.hint,
      get page() {
        return value(meta.route); // read when the row is drawn: the team page's address waits for the identity
      },
    },
    ...items.map((b) => (isBand(b) ? bandEntry(page, b) : { heading: b.heading })),
  ];
}
