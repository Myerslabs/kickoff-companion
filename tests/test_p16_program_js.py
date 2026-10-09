"""Phase 16, stream PROGRAM: the Game program, the shared two-team table, the edges table and the game
leaders grid in the fake browser (tests/fakedom.py). The two-team cell (value and chip together, lead and
trail, the divider, the placeholder chip, linked chips with the team), percentiles, edges keyed by unit,
the cover's game states and its in-place countdown, one fetch per picked game, leaders with units (bug 2),
the throw and run tables, the radar link, the venue line, and no undefined, null or NaN on a damaged page."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from tests.fakedom import needs_node, run_scenario

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"
CSS = (STATIC / "css" / "components.css").read_text(encoding="utf-8")


def team(school: str, abbr: str, *, logo: bool = True, **extra: object) -> dict:
    block = {"school": school, "abbreviation": abbr, "color": "#0021a5", "altColor": "#fa4616", "record": {"games": 3, "wins": 3, "losses": 0, "ties": 0}, "conferenceRecord": {"games": 1, "wins": 1, "losses": 0, "ties": 0}, "apRank": None, "sp": {"rating": 19.4, "rank": 13, "of": 138, "metric": "rating:sp"}}
    if logo:
        block.update(logo=f"/media/logo/{abbr}", logoDark=f"/media/logo/{abbr}?v=dark")
    block.update(extra)
    return block


def profile(value: float, rank: int | None, key: str, side: str, label: str, higher: bool = True, fmt: str = "1f") -> dict:
    return {"side": side, "label": label, "key": key, "metric": f"profile:{key}", "value": value, "format": fmt, "higherIsBetter": higher, "nationalRank": rank, "nationalOf": 138}


def payload(**game: object) -> dict:
    """A small /api/program answer in the real shape (checked against the simulator's on 2026-09-28)."""
    g = {"gameId": 526000600, "week": 3, "postseason": None, "playoffRound": None, "kickoff": "2026-09-26T19:30:00.000Z", "startTimeTbd": False, "completed": False, "homeIsUs": False, "neutralSite": False, "conferenceGame": True, "venue": "Silver Dollar Field", "venueDetail": {"name": "Silver Dollar Field", "city": "Silver Dollar", "state": "AL", "capacity": 87451, "grass": True, "dome": False, "elevationFt": 660, "elevationM": 201.2, "yearBuilt": 1939, "recordAtVenue": {"venue": "Silver Dollar Field", "opponent": "Silver Dollar", "gamesWithoutVenue": 2, "wins": 3, "losses": 5, "ties": 0, "games": 8}}, "tv": "ESPN", "usPoints": None, "themPoints": None, "usLineScores": None, "themLineScores": None, "archived": False}
    g.update(game)
    return {
        "season": 2026,
        "game": g,
        "us": team("Swampwater Tech", "SWT", form=[{"result": "W", "points": 66, "opponentPoints": 21, "opponent": "Swampwater Tech Atlantic", "week": 1}, {"result": "L", "points": 17, "opponentPoints": 20, "opponent": "Miami", "week": 2}]),
        "them": team("Silver Dollar", "GRID", apRank=22, form=[]),
        "line": {"spread": 2.5, "formatted": "Swampwater Tech -2.5", "spreadOpen": -1.5, "overUnder": 52.5, "overUnderOpen": 53.5},
        "pregame": {"homeWinProbability": 0.38, "usWinProbability": 0.62},
        "weather": {"available": True, "source": "National Weather Service", "tempF": 87.0, "windMph": 8.0, "windDir": "W", "sky": "Mostly Sunny", "precipChance": 6.0, "dome": False, "radarUrl": "https://forecast.weather.gov/MapClick.php?lat=32.6&lon=-85.49"},
        "profile": {
            "us": [profile(59.0, 1, "ppg", "offense", "Points per game"), profile(8.0, 5, "ypp", "offense", "Yards per play"), profile(12.0, 1, "opp_ppg", "defense", "Points allowed per game", False), profile(4.5, 30, "ypp_d", "defense", "Yards allowed per play", False)],
            "them": [profile(30.0, 40, "ppg", "offense", "Points per game"), profile(8.0, 5, "ypp", "offense", "Yards per play"), profile(20.0, None, "opp_ppg", "defense", "Points allowed per game", False), profile(4.9, 57, "ypp_d", "defense", "Yards allowed per play", False)],
        },
        "edges": [
            {"label": "Passing: Swampwater Tech offense vs Silver Dollar defense", "side": "offense", "usRank": 24, "themRank": 119, "of": 138, "themOf": 138, "edge": 95, "usValue": 298.333, "themValue": 252.0, "format": "0f", "usFormat": "0f", "themFormat": "0f", "usKey": "pass_ypg", "themKey": "pass_ypg_d", "usMetric": "profile:pass_ypg", "themMetric": "profile:pass_ypg_d"},
            {"label": "Rushing: Silver Dollar offense vs Swampwater Tech defense", "side": "defense", "usRank": 60, "themRank": 20, "of": 138, "themOf": 138, "edge": -40, "usValue": 150.0, "themValue": 210.5, "format": "0f", "usFormat": "0f", "themFormat": "0f", "usKey": "rush_ypg_d", "themKey": "rush_ypg"},
        ],
        "advanced": {"us": [{"side": "offense", "label": "Success rate", "key": "offense_success_rate", "metric": "advanced:offense_success_rate", "group": "Overall", "value": 0.486, "format": "pct", "higherIsBetter": True, "nationalRank": 41, "nationalOf": 138}], "them": [{"side": "offense", "label": "Success rate", "key": "offense_success_rate", "metric": "advanced:offense_success_rate", "group": "Overall", "value": 0.44, "format": "pct", "higherIsBetter": True, "nationalRank": 80, "nationalOf": 138}]},
        "adjusted": [],
        "tendencies": {"plays": 180, "games": 3, "runRate": 0.52, "bySituation": [], "runDirection": [], "passDepth": [], "passZones": [{"key": "deep_left", "depth": "deep", "direction": "left", "attempts": 4, "completions": 1, "completionPct": 0.25, "successRate": 0.25}, {"key": "short_middle", "depth": "short", "direction": "middle", "attempts": 0, "completions": 0, "completionPct": None, "successRate": None}], "runLanes": [{"key": "left", "carries": 12, "yardsPerCarry": 4.2, "successRate": 0.417}, {"key": "middle", "carries": 0, "yardsPerCarry": None, "successRate": None}], "unplacedPasses": 2, "unplacedRuns": 0},
        "advancedBox": None,
        "leaders": [
            {"label": "Passing yards", "stat": "YDS", "format": "0f", "us": {"playerId": "4536127", "player": "Mason Hamilton", "position": "QB", "value": 1204.0, "headshotUrl": "/media/headshot/4536127"}, "them": None},
            {"label": "Sacks", "stat": "SACKS", "format": "1f", "us": {"playerId": "1", "player": "Tyrese Sampson", "position": "DL", "value": 4.5, "headshotUrl": "/media/headshot/1"}, "them": {"playerId": "2", "player": "Kendric Faulkner", "position": "DL", "value": 1.0, "headshotUrl": None}},
        ],
        "series": {"team1": "Silver Dollar", "team2": "Swampwater Tech", "usWins": 38, "themWins": 43, "ties": 2, "streak": {"team": "Swampwater Tech", "games": 2}, "lastTen": [{"season": 2019, "homeTeam": "Swampwater Tech", "awayTeam": "Silver Dollar", "homeScore": 24, "awayScore": 13, "winner": "Swampwater Tech"}]},
        "notes": {"present": False},
        "final": None,
        "ppa": {"available": True, "season": {"us": {"offense": {"overall": 0.437, "passing": 0.68, "rushing": 0.337}, "defense": {"overall": -0.09, "passing": 0.023, "rushing": -0.04}}, "them": {"offense": {"overall": None}, "defense": {}}}, "games": {"us": [{"week": 1, "opponent": "Swampwater Tech Atlantic", "offense": {"overall": 0.61}, "defense": {"overall": -0.01}}, {"week": 2, "opponent": "Campbell", "offense": {"overall": 0.39}, "defense": {"overall": -0.43}}], "them": []}, "players": {"us": [], "them": []}, "seasonLeaders": {"us": [], "them": []}},
        "commonOpponents": [],
        "lastSeason": {"year": 2025, "rows": [{"side": "offense", "label": "Points per game", "key": "ppg", "metric": "profile:ppg", "metricYear": 2025, "format": "1f", "higherIsBetter": True, "us": {"value": 30.1, "rank": 30, "of": 136}, "them": {"value": 25.0, "rank": 70, "of": 136}}]},
        "recruiting": {"us": {"talent": {"talent": 891.07, "rank": 10, "of": 138, "metric": "rating:talent"}, "blueChip": {"ratio": 0.709}, "returning": {"percentPPA": 0.69}}, "them": {"talent": {"talent": 828.19, "rank": 18, "of": 138, "metric": "rating:talent"}, "blueChip": {"ratio": 0.4}, "returning": None}},
        "picker": [
            {"gameId": 526000153, "week": 2, "opponent": {"school": "Campbell"}, "completed": True, "result": "W", "usPoints": 52, "themPoints": 3, "archived": True},
            {"gameId": 526000600, "week": 3, "opponent": {"school": "Silver Dollar"}, "completed": False, "archived": False},
            {"gameId": 526001015, "week": 4, "opponent": {"school": "Diner Tech"}, "completed": False},
        ],
        "parts": {},
    }


def damaged(data: dict) -> dict:
    """The same answer with the kinds of damage a bad upstream day brings: nulls, wrong types, junk rows."""
    bad = copy.deepcopy(data)
    bad["us"]["record"] = None
    bad["us"]["sp"] = {"rank": "13", "metric": 7}
    bad["them"] = {"school": None, "abbreviation": None, "form": "x", "logo": 5}
    bad["line"] = {"formatted": None, "overUnder": "52"}
    bad["pregame"] = {"homeWinProbability": "high"}
    bad["weather"] = {"available": True, "tempF": None, "sky": None, "radarUrl": 12}
    bad["game"]["venueDetail"] = {"capacity": "big", "grass": "yes", "elevationFt": None, "recordAtVenue": {"wins": None}}
    bad["profile"] = {"us": [None, "junk", {"label": None, "value": "x"}], "them": "nope"}
    bad["edges"] = [None, {"label": 3, "usRank": "1"}, {"edge": None, "usRank": 4}]
    bad["advanced"] = {"us": [{"key": "a", "value": None, "group": None}], "them": None}
    bad["tendencies"] = {"plays": 10, "passZones": [None, {"depth": "deep", "direction": "left", "attempts": None}], "runLanes": "x"}
    bad["leaders"] = [None, {"label": None, "us": {"value": "many"}, "them": 3}]
    bad["series"] = {"lastTen": [None, {"season": None}]}
    bad["ppa"] = {"available": True, "season": None, "games": {"us": [None, {"week": None, "offense": None}]}}
    bad["lastSeason"] = {"year": None, "rows": [None, {"us": None}]}
    bad["recruiting"] = {"us": None, "them": "x"}
    bad["picker"] = [None, {"gameId": "abc"}, {"gameId": 526000600}]
    bad["notes"] = {"present": True, "sections": [None, {"heading": None, "paragraphs": [None]}], "availability": [None]}
    return bad


SCENARIOS = r"""
// Phase 17 #17: the leaders band asks /api/program/<id>/leaders on its own; these count the program itself.
const programCalls = (prefix) => calls.filter((u) => u.startsWith(prefix) && !u.includes("/leaders")).length;
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object Object\]/;
const text = (node) => (node ? node.textContent : "");
const clean = (label, node) => {
  const t = text(node);
  assert.ok(!RAW.test(t), `${label} printed ${JSON.stringify(t.slice(Math.max(0, t.search(RAW) - 80), t.search(RAW) + 80))}`);
  return t;
};
Object.getPrototypeOf(document.body).scrollIntoView = function () {};
const cls = (node) => (node ? node.className : "");

scenarios.twoTeam = async () => {
  const { twoTeamTable, twoTeamLeader } = await import(moduleUrl("ui/two-team.js"));
  const rows = [
    { label: "Yards per play", format: "1f", higherIsBetter: true, metric: "profile:ypp", us: { value: 8.04, rank: 5, of: 138 }, them: { value: 6.1, rank: 70, of: 138 } },
    { label: "Yards allowed per play", format: "1f", higherIsBetter: false, metric: "profile:ypp_d", us: { value: 4.5, rank: 30, of: 138 }, them: { value: 4.9, rank: 57, of: 138 } },
    { label: "Third down", format: "pct", higherIsBetter: true, us: { value: 0.46, rank: 50, of: 138 }, them: { value: 0.46, rank: 50, of: 138 } },
    { label: "Blue-chip ratio", format: "pct", higherIsBetter: true, us: { value: 0.7 }, them: { value: null } },
  ];
  const wrap = twoTeamTable({ rows, usAbbr: "SWT", themAbbr: "GRID", usTeam: "Swampwater Tech", themTeam: "Silver Dollar" });
  clean("two-team table", wrap);
  const body = wrap.querySelectorAll("tbody tr");
  assert.equal(body.length, 4);
  // value and chip in ONE cell, the opponent's cell carries the divider class
  const [label, us, them, better] = body[0].childNodes;
  assert.equal(text(label), "Yards per play");
  assert.ok(cls(us).includes("tt__cell") && us.querySelector(".tt__val") && us.querySelector(".rank-chip"), "value and chip share the cell");
  assert.equal(text(us.querySelector(".tt__val")), "8.0");
  assert.ok(cls(them).includes("tt__them"), "the divider class stands before the opponent");
  assert.ok(wrap.querySelector("th.tt__them"), "the opponent's header carries the divider too");
  // lead and trail; the Better column is symmetric
  assert.ok(cls(us).includes("lead") && cls(them).includes("trail"));
  assert.equal(text(better), "SWT");
  assert.ok(cls(better).includes("lead"));
  const [, usD, themD, betterD] = body[1].childNodes;
  assert.ok(cls(usD).includes("lead") && cls(themD).includes("trail"), "lower is better: 4.5 beats 4.9");
  // ties stay neutral
  const [, usT, themT, betterT] = body[2].childNodes;
  assert.ok(!cls(usT).includes("lead") && !cls(usT).includes("trail") && !cls(themT).includes("lead") && !cls(themT).includes("trail"));
  assert.equal(text(betterT), "Even");
  assert.ok(!cls(betterT).includes("lead"));
  // a row with no rank keeps an invisible chip so its value lines up; a missing value is a dash
  const [, usB, themB] = body[3].childNodes;
  assert.ok(usB.querySelector(".rank-chip--placeholder") && themB.querySelector(".rank-chip--placeholder"));
  assert.equal(text(themB.querySelector(".tt__val")), "–");
  // linked chips: each side's own team, the whole cell the target
  const usLink = us.querySelector("a.rank-chip--link");
  const themLink = them.querySelector("a.rank-chip--link");
  assert.equal(usLink.getAttribute("href"), "#national=profile%3Aypp?team=Swampwater%20Tech");
  assert.equal(themLink.getAttribute("href"), "#national=profile%3Aypp?team=Silver%20Dollar");
  assert.ok(cls(us).includes("tt__cell--link"));
  assert.ok(!body[2].childNodes[1].querySelector("a"), "no metric, no link: a plain chip");
  // a year opens that season's list
  const last = twoTeamTable({ rows: [{ ...rows[0], metricYear: 2025 }], usTeam: "Swampwater Tech" });
  assert.equal(last.querySelector("a.rank-chip--link").getAttribute("href"), "#national=profile%3Aypp?team=Swampwater%20Tech&year=2025");
  // groups draw group rows in one table
  const grouped = twoTeamTable({ groups: [{ title: "Offense", note: "Spread", rows: rows.slice(0, 1) }, { title: "Defense", rows: rows.slice(1, 2) }], usAbbr: "SWT", themAbbr: "GRID", better: false });
  assert.equal(grouped.querySelectorAll("table").length, 1);
  assert.equal(grouped.querySelectorAll("tr.tt__group").length, 2);
  assert.ok(text(grouped.querySelector("tr.tt__group")).includes("Spread"));
  assert.ok(!grouped.querySelector(".tt__better"));
  // leader rules: explicit leads win; no direction falls back to ranks; nothing comparable is null
  assert.equal(twoTeamLeader({ leads: "them", us: { value: 9 }, them: { value: 1 } }), "them");
  assert.equal(twoTeamLeader({ us: { value: 1, rank: 90 }, them: { value: 9, rank: 10 } }), "them");
  assert.equal(twoTeamLeader({ us: { value: 1 }, them: {} }), null);
  // junk never throws and never prints raw words
  for (const junk of [null, undefined, "x", 3, [null, "a", { us: "x", them: 5 }]]) clean("junk rows", twoTeamTable({ rows: junk, groups: junk === 3 ? [null, { rows: "x" }] : undefined }));
};

scenarios.percentile = async () => {
  const { percentile } = await import(moduleUrl("ui/two-team.js"));
  assert.equal(percentile(1, 138), 100);
  assert.equal(percentile(138, 138), 0);
  assert.equal(percentile(70, 139), 50);
  // ranks already run best-first: a lower-is-better stat's rank 1 (fewest points allowed) is the 100th
  // percentile, never reversed a second time by its low value
  assert.equal(percentile(1, 136), 100);
  assert.equal(percentile(30, 138), 79);
  for (const [rank, of] of [[null, 138], [5, null], [0, 138], [140, 138], [1, 1], ["5", 138], [NaN, 138], [5, Infinity]]) assert.equal(percentile(rank, of), null, `${rank} of ${of}`);
};

scenarios.ladderAndUnderline = async () => {
  const { twoTeamTable } = await import(moduleUrl("ui/two-team.js"));
  const rows = [
    { label: "Success rate", higherIsBetter: true, us: { value: 0.49, rank: 1, of: 101 }, them: { value: 0.4, rank: 101, of: 101 } },
    { label: "Havoc", higherIsBetter: true, us: { value: 0.2, rank: null }, them: { value: null } },
  ];
  const wrap = twoTeamTable({ rows, usAbbr: "SWT", themAbbr: "GRID", ladder: true, underline: true });
  clean("ladder", wrap);
  const marks = wrap.querySelectorAll("tbody tr")[0].querySelectorAll(".ladder__mark");
  assert.equal(marks.length, 2);
  assert.equal(wrap.querySelector(".ladder__mark--us").style.left, "100%");
  assert.equal(wrap.querySelector(".ladder__mark--them").style.left, "0%");
  assert.equal(text(wrap.querySelectorAll("tbody tr")[1].querySelector(".tt__ladder")), "–", "no ranks: a dash, no track");
  const bars = wrap.querySelectorAll(".tt__pct");
  assert.equal(bars.length, 2, "only ranked cells get an underline");
  assert.ok(cls(bars[0]).includes("tt__pct--us") && cls(bars[1]).includes("tt__pct--them"));
  assert.equal(bars[0].querySelector(".tt__pct-fill").style.width, "100%");
};

scenarios.edges = async () => {
  const { edgesTable, edgeRows, edgesSummary } = await import(moduleUrl("ui/edges.js"));
  const edges = FIXTURE.edges;
  const wrap = edgesTable(edges, { usAbbr: "SWT", themAbbr: "GRID", usTeam: "Swampwater Tech", themTeam: "Silver Dollar" });
  clean("edges", wrap);
  const rows = wrap.querySelectorAll("tbody tr");
  assert.equal(rows.length, 2);
  // offense row: Swampwater Tech's chip is its offense stat, the opponent's its defense stat
  // Phase 17 #14, #16: label | us | the tug bar | them; the cells bracket the bar
  const [offUs, offTug, offThem] = [rows[0].childNodes[1], rows[0].childNodes[2], rows[0].childNodes[3]];
  assert.equal(offUs.querySelector("a").getAttribute("href"), "#national=profile%3Apass_ypg?team=Swampwater%20Tech");
  assert.equal(offThem.querySelector("a").getAttribute("href"), "#national=profile%3Apass_ypg_d?team=Silver%20Dollar");
  // defense row: the reverse (and a row with keys but no metrics still links)
  assert.equal(rows[1].childNodes[1].querySelector("a").getAttribute("href"), "#national=profile%3Arush_ypg_d?team=Swampwater%20Tech");
  assert.equal(rows[1].childNodes[3].querySelector("a").getAttribute("href"), "#national=profile%3Arush_ypg?team=Silver%20Dollar");
  assert.equal(text(rows[0].childNodes[0]), "PassingSWT offense vs GRID defense");
  assert.equal(text(rows[1].childNodes[0]), "RushingGRID offense vs SWT defense");
  // the bar leans to the side with the edge, in its color, and says how far apart the ranks are
  assert.ok(offTug.querySelector(".tug__bar--us") && !offTug.querySelector(".tug__bar--them"));
  assert.ok(offTug.querySelector(".tug").getAttribute("title").includes("SWT has the edge, 95 national ranks apart"));
  assert.ok(rows[1].childNodes[2].querySelector(".tug__bar--them"));
  // our chip sits outside our value, the opponent's mirrored: the values meet the bar
  assert.ok(cls(offUs.childNodes[0]).includes("rank-chip") && cls(offThem.childNodes[offThem.childNodes.length - 1]).includes("rank-chip"));
  // no red-tinted rows, no Better or Edge to columns
  assert.ok(!cls(rows[0]).includes("is-us") && !text(wrap.querySelector("thead")).includes("Edge to") && !wrap.querySelector(".tt__better"));
  // values in each side's own format; the leader follows the edge, not the values (different stats)
  assert.equal(text(offUs.querySelector(".tt__val")), "298");
  assert.ok(cls(offUs).includes("lead") && cls(rows[1].childNodes[3]).includes("lead"));
  assert.equal(edgesSummary(edges, { usAbbr: "SWT", themAbbr: "GRID" }), "SWT better in 1 of 2 · Biggest: Passing, SWT offense vs GRID defense, SWT by 95 ranks");
  assert.equal(edgesSummary([], { usAbbr: "SWT" }), "");
  assert.equal(edgeRows([null, "x", { label: "Junk" }]).length, 0);
  clean("junk edges", edgesTable([null, { label: 5, usRank: 3 }, { edge: 4, side: "defense" }], {}));
};

scenarios.leaders = async () => {
  const { leadersGrid, statLine, boxLeader, leaderLine } = await import(moduleUrl("ui/leaders.js"));
  const { programLeader } = await import(moduleUrl("views/program.js"));
  assert.equal(statLine(4.5, "1f", "SACKS"), "4.5 sacks", "bug 2: a 1f board keeps its half sack");
  assert.equal(statLine(1, "1f", "SACKS"), "1.0 sack");
  assert.equal(statLine(1204, "0f", "YDS"), "1,204 yds");
  assert.equal(statLine(38, "0f", "TOT"), "38 tkl");
  assert.equal(statLine(null, "0f", "YDS"), "–");
  assert.equal(statLine(12, "0f", "WHAT"), "12");
  const cats = FIXTURE.leaders.map((cat) => ({ label: cat.label, us: programLeader(cat.us, cat), them: programLeader(cat.them, cat) }));
  const grid = leadersGrid({ categories: cats, usAbbr: "SWT", themAbbr: "GRID", className: "leaders--program" });
  const t = clean("leaders", grid);
  assert.ok(t.includes("4.5 sacks") && t.includes("1,204 yds") && t.includes("1.0 sack"));
  assert.equal(text(grid.querySelector(".leaders__head")), "SWTGRID", "the SWT | GRID head row");
  const empty = grid.querySelectorAll(".leader-cat")[0].querySelector(".leader--empty");
  assert.ok(empty && cls(empty).includes("leader--them") && text(empty) === "No GRID line yet");
  assert.ok(grid.querySelector(".leader__hero"), "the key number is its own bold element");
  // a box-score line puts the category's key stat first
  assert.deepEqual(leaderLine("passing", { YDS: 245, "C/ATT": "18/27", TD: 2, INT: 1 }), { hero: "245 yds", rest: "18/27, 2 TD, 1 int" });
  const top = boxLeader("rushing", [{ name: "A", stats: { YDS: 40, CAR: 9 } }, { name: "B", stats: { YDS: 120, CAR: 20, TD: 1 } }]);
  assert.equal(top.name, "B");
  assert.equal(top.lineText, "120 yds, 20 car, 1 TD");
  // a plain string line (the Live sheet's) still draws; junk never prints raw words
  clean("string line", leadersGrid({ categories: [{ label: "Passing", us: { name: "X", line: "12/20, 180 yds" }, them: { name: null, line: { hero: null, rest: 5 } } }, null, "x"] }));
  assert.equal(programLeader(null, {}), null);
};

scenarios.coverStates = async () => {
  const { cover, coverState } = await import(moduleUrl("ui/cover.js"));
  const base = { us: FIXTURE.us, them: FIXTURE.them, homeIsUs: false, date: "2026-09-26T19:30:00.000Z", venue: "Silver Dollar Field", tv: "ESPN", line: FIXTURE.line, pregame: { homeWinProbability: 0.38 }, liveHref: "#live" };
  const at = (iso) => new Date(iso);
  // upcoming: a countdown, no Live button yet
  const pre = cover({ ...base, now: at("2026-09-24T19:30:00.000Z") });
  assert.equal(pre.dataset.state, "pre");
  assert.ok(text(pre).includes("2d 0h 0m") && !text(pre).includes("Open the Live sheet"));
  // P-15: the pregame win probability as a bar, Swampwater Tech from the left (home 38% here, so Swampwater Tech 62%)
  const bar = pre.querySelector(".cover__wp");
  assert.ok(bar && text(bar).includes("SWT 62%") && text(bar).includes("38% GRID"));
  assert.equal(bar.querySelector(".wpbar__home--us").style.width, "62%");
  assert.ok(!cover({ ...base, pregame: { homeWinProbability: "high" } }).querySelector(".cover__wp"), "no number, no bar");
  // inside the hour: "Kickoff in 38 min" and a secondary Live button
  const soon = cover({ ...base, now: at("2026-09-26T18:52:00.000Z") });
  assert.equal(soon.dataset.state, "soon");
  assert.ok(text(soon).includes("Kickoff in 38 min"));
  const soonBtn = soon.querySelector("a.cover__action");
  assert.ok(soonBtn && !cls(soonBtn).includes("btn--primary"));
  // under way: the primary Live button, no score (the spoiler delay lives on the Live sheet)
  const live = cover({ ...base, now: at("2026-09-26T20:00:00.000Z") });
  assert.equal(live.dataset.state, "live");
  assert.ok(text(live).includes("Under way"));
  const liveBtn = live.querySelector("a.cover__action");
  assert.equal(liveBtn.getAttribute("href"), "#live");
  assert.ok(cls(liveBtn).includes("btn--primary"));
  // a TBD kickoff never says under way
  const tbd = cover({ ...base, startTimeTbd: true, now: at("2026-09-26T23:00:00.000Z") });
  assert.equal(tbd.dataset.state, "tbd");
  assert.ok(!text(tbd).includes("Under way") && !tbd.querySelector("a.cover__action"));
  assert.equal(coverState({ date: "2026-09-26T19:30:00.000Z", startTimeTbd: true, now: at("2026-09-27T00:00:00Z") }), "tbd");
  assert.equal(coverState({ date: "nope" }), "unknown");
  // final: the score, W or L, the Archive link only when the archive holds the game
  const final = cover({ ...base, state: "final", usPoints: 31, themPoints: 24, now: at("2026-09-27T12:00:00Z") });
  const ft = clean("final cover", final);
  assert.ok(ft.includes("SWT 31") && ft.includes("24 GRID") && ft.includes("Won"));
  assert.ok(final.querySelector(".cover__score .is-winner") && text(final.querySelector(".cover__score .is-loser")).includes("24"));
  assert.ok(!final.querySelector("a.cover__action"), "no archive file: no Archive link");
  const archived = cover({ ...base, state: "final", usPoints: 17, themPoints: 20, archiveHref: "#archive=526000600" });
  assert.equal(archived.querySelector("a.cover__action").getAttribute("href"), "#archive=526000600");
  assert.ok(text(archived).includes("Lost"));
  // a finished game with no line says it plainly
  assert.ok(text(cover({ ...base, state: "final", line: {}, pregame: {}, usPoints: 1, themPoints: 0 })).includes("No line was recorded."));
  // the old calls (Live sheet, Archive) still draw
  clean("old call", cover({ us: {}, them: {}, line: {}, pregame: {} }));
  clean("final without points", cover({ state: "final", us: { school: "Swampwater Tech" }, them: {} }));
};

scenarios.coverTick = async () => {
  const { cover } = await import(moduleUrl("ui/cover.js"));
  const node = cover({ us: FIXTURE.us, them: FIXTURE.them, homeIsUs: false, date: "2026-09-26T19:30:00.000Z", liveHref: "#live", now: new Date("2026-09-26T17:00:00Z") });
  document.body.append(node);
  const middle = node.querySelector(".cover__middle");
  const title = node.querySelector(".cover__matchup");
  assert.ok(text(middle).includes("2h 30m"));
  assert.equal(node.tick(new Date("2026-09-26T19:00:30Z")), "soon");
  assert.ok(text(middle).includes("Kickoff in 29 min"));
  assert.equal(node.querySelector(".cover__matchup"), title, "the cover is not rebuilt");
  assert.equal(node.querySelector(".cover__middle"), middle);
  assert.equal(node.tick(new Date("2026-09-26T19:31:00Z")), "live");
  assert.ok(text(middle).includes("Under way") && cls(node.querySelector("a.cover__action")).includes("btn--primary"));
  node.remove();
};

scenarios.faceOff = async () => {
  const { cover } = await import(moduleUrl("ui/cover.js"));
  const props = { us: FIXTURE.us, them: FIXTURE.them, homeIsUs: false, date: "2026-09-26T19:30:00.000Z", venue: "Silver Dollar Field", line: FIXTURE.line, now: new Date("2026-09-20T12:00:00Z") };
  const node = cover(props);
  const sides = node.querySelectorAll(".cover__side");
  assert.equal(sides.length, 2, "two team blocks face each other");
  assert.ok(text(sides[0]).includes("Swampwater Tech") && text(sides[1]).includes("Silver Dollar"), "Swampwater Tech on the left, as in every two-team table");
  assert.equal(text(node.querySelector(".cover__vs")), "at", "Swampwater Tech away: 'at'");
  const logos = node.querySelectorAll(".cover__side img.team-logo");
  assert.equal(logos.length, 2);
  assert.equal(logos[0].getAttribute("src"), "/media/logo/SWT?v=dark", "the dark variant on the navy cover");
  assert.equal(logos[0].getAttribute("width"), "112");
  assert.equal(logos[0].getAttribute("loading"), null, "the hero is never lazy");
  // a home game reads 'vs'; a neutral site too
  assert.equal(text(cover({ ...props, homeIsUs: true }).querySelector(".cover__vs")), "vs");
  assert.equal(text(cover({ ...props, neutralSite: true }).querySelector(".cover__vs")), "vs");
  // missing logos: the mono tile with the abbreviation, never a broken image
  const bare = cover({ ...props, us: { school: "Swampwater Tech", abbreviation: "SWT" }, them: { school: "Silver Dollar" } });
  const tiles = bare.querySelectorAll(".cover__side .team-logo--mono");
  assert.equal(tiles.length, 2);
  assert.equal(text(tiles[0]), "SWT");
  clean("no logos", bare);
  // final in the middle; under way in the middle
  const fin = cover({ ...props, state: "final", usPoints: 31, themPoints: 24 });
  assert.ok(text(fin.querySelector(".cover__middle")).includes("SWT 31"));
  const live = cover({ ...props, now: new Date("2026-09-26T20:00:00Z") });
  assert.ok(text(live.querySelector(".cover__middle")).includes("Under way"));
  // the SP+ link and the AP poll badge open their lists
  // Phase 17 #2: the record, the conference record and SP+ are chips like the AP badge
  const rec = node.querySelector(".cover__side--us .cover__rec");
  assert.ok(rec.querySelectorAll(".cover-chip").length >= 2, text(rec));
  assert.ok(!text(rec).includes(" · "), "chips, not a dotted line");
  const chipLinks = node.querySelectorAll(".cover__side--us a.cover-chip--link");
  const sp = chipLinks.find((a) => a.textContent.includes("SP+"));
  assert.equal(sp.getAttribute("href"), "#national=rating%3Asp?team=Swampwater%20Tech");
  // Phase 17 #2: our conference record opens the standings
  assert.ok(chipLinks.some((a) => a.getAttribute("href") === "#season?band=standings"));
  const ap = node.querySelector("a.poll-badge--link");
  assert.equal(ap.getAttribute("href"), "#national=poll%3AAP?team=Silver%20Dollar");
};

scenarios.formGuide = async () => {
  const { cover } = await import(moduleUrl("ui/cover.js"));
  const node = cover({ us: FIXTURE.us, them: FIXTURE.them, date: "2026-09-26T19:30:00.000Z" });
  const guide = node.querySelectorAll(".form-guide")[0];
  assert.ok(guide, "Swampwater Tech's last results");
  const games = guide.querySelectorAll(".form-guide__game");
  assert.equal(games.length, 2);
  assert.equal(text(games[1]), "L", "newest on the right");
  assert.ok(cls(games[0]).includes("form-guide__game--w") && cls(games[1]).includes("form-guide__game--l"));
  assert.ok(games[1].getAttribute("title").includes("17-20") && games[1].getAttribute("title").includes("Miami"));
  assert.equal(node.querySelectorAll(".form-guide").length, 1, "no games: no guide for the opponent");
  clean("junk form", cover({ us: { school: "Swampwater Tech", form: [null, { result: "X" }, { result: "W", points: "a" }] }, them: { form: "x" } }));
};

scenarios.weatherVenue = async () => {
  const { weatherRow, venueLine } = await import(moduleUrl("ui/matchup-card.js"));
  const w = weatherRow({ kickoffText: "3:30 PM", tempF: 87, windMph: 8, windDir: "W", sky: "Mostly Sunny", radarUrl: "https://forecast.weather.gov/MapClick.php?lat=1&lon=2" });
  const radar = w.querySelector("a.weather__radar");
  assert.ok(radar && radar.getAttribute("href").startsWith("https://forecast.weather.gov/") && radar.getAttribute("target") === "_blank");
  for (const bad of [null, undefined, "", "javascript:alert(1)", 12, "/local"]) assert.ok(!weatherRow({ tempF: 80, radarUrl: bad }).querySelector("a.weather__radar"), `no radar for ${bad}`);
  assert.ok(!weatherRow({ note: "No forecast yet.", radarUrl: null }).querySelector("a.weather__radar"));
  assert.ok(text(weatherRow({ tempF: 80, label: "Kickoff weather" })).includes("Kickoff weather"));
  const v = venueLine(FIXTURE.game.venueDetail, { us: "Swampwater Tech" });
  // Phase 17 #3: the stadium's name first, and the record names the opponent it is against
  assert.equal(text(v), "Silver Dollar Field · Capacity 87,451 · Grass · Elevation 660 ft · Built 1939 · Swampwater Tech 3-5 vs Silver Dollar here");
  assert.ok(v.querySelector(".venue-line__name") && v.querySelector("span[title]").getAttribute("title").includes("2 older games"));
  assert.equal(text(venueLine({ dome: true, grass: false })), "Artificial turf · Dome");
  assert.equal(text(venueLine({ name: "  Example Bowl " })), "Example Bowl");
  assert.equal(venueLine({}), null);
  assert.equal(venueLine(null), null);
  assert.equal(venueLine({ name: "", capacity: "big", grass: "yes", elevationFt: null, recordAtVenue: { wins: null } }), null);
  assert.equal(text(venueLine({ recordAtVenue: { opponent: "Diner Tech", wins: 1, losses: 0, ties: 1, games: 2 } }, { us: "Swampwater Tech" })), "Swampwater Tech 1-0-1 vs Diner Tech here");
  // a record that cannot say who it is against is left out rather than misread
  assert.equal(venueLine({ recordAtVenue: { wins: 8, losses: 2, ties: 0 } }, { us: "Swampwater Tech" }), null);
};

scenarios.zones = async () => {
  const { passZonesTable, runLanesTable, tendenciesBlock } = await import(moduleUrl("ui/depth2.js"));
  const zones = passZonesTable(FIXTURE.tendencies.passZones);
  const t = clean("zones", zones);
  const rows = zones.querySelectorAll("tbody tr");
  assert.equal(rows.length, 2);
  assert.equal(text(rows[0].childNodes[0]), "Deep", "the deep row sits over the short row");
  assert.equal(text(rows[1].childNodes[0]), "Short");
  assert.equal(text(zones.querySelector("thead")), "PassesLeftMiddleRight");
  assert.ok(text(rows[0].childNodes[1]).startsWith("4 att") && text(rows[0].childNodes[1]).includes("25.0% comp"));
  assert.ok(text(rows[1].childNodes[2]).startsWith("0 att"), "a zero is a zero");
  assert.ok(text(rows[0].childNodes[2]).startsWith("–"), "a zone missing from the payload is a dash");
  const lanes = runLanesTable(FIXTURE.tendencies.runLanes);
  clean("lanes", lanes);
  assert.ok(text(lanes).includes("12 car") && text(lanes).includes("4.2 yds") && text(lanes).includes("0 car"));
  const block = tendenciesBlock(FIXTURE.tendencies, "GRID");
  assert.ok(text(block).includes("2 passes had no charted zone"));
  clean("junk zones", passZonesTable([null, { depth: "deep", direction: "left", attempts: "x", completionPct: NaN }]));
  clean("junk lanes", runLanesTable("x"));
  assert.ok(t.length > 0);
};

async function mountProgram(data, hash = "") {
  const { clearEnvelopeCache } = await import(moduleUrl("views/common.js"));
  clearEnvelopeCache();
  route("/api/program", () => envelope(data));
  route("/api/notes/run", () => envelope({ running: false, commandFound: true }));
  route("/api/radio/sources", () => envelope({ sources: [{ id: "a", name: "WSTS", kind: "stream", url: "https://example.org/a" }] }));
  const { createProgramView } = await import(moduleUrl("views/program.js"));
  const root = document.createElement("div");
  document.body.append(root);
  const view = createProgramView({ onStatus: () => {}, gameId: hash || null });
  view.mount(root);
  await settle();
  return { root, view };
}

scenarios.programPage = async () => {
  const data = clone(FIXTURE);
  const { root, view } = await mountProgram(data);
  const t = clean("program", root);
  assert.ok(root.querySelector(".cover") && root.querySelector(".tt"));
  // the cover's arrows come from the picker's order
  assert.equal(root.querySelector("a.cover__nav--prev").getAttribute("href"), "#program=526000153");
  assert.equal(root.querySelector("a.cover__nav--next").getAttribute("href"), "#program=526001015");
  // the radar link and the venue facts under the weather row
  assert.ok(root.querySelector("a.weather__radar"));
  assert.ok(t.includes("Built 1939"));
  assert.ok(t.includes("4.5 sacks"));
  // the opponent's colors are switched on while the page is up, and reset when it goes
  assert.ok(document.documentElement.style["--opp"]);
  view.unmount();
  assert.ok(!document.documentElement.style["--opp"]);
  root.remove();
};

scenarios.pickerOneFetch = async () => {
  installWindow();
  const data = clone(FIXTURE);
  const { root, view } = await mountProgram(data);
  const before = programCalls("/api/program");
  assert.equal(before, 1);
  // choosing another game only changes the hash: the router builds the next view once (bug 13)
  const next = root.querySelector("a.cover__nav--next");
  assert.ok(next);
  view.open(526001015);
  await advance(1000);
  assert.equal(window.location.hash, "#program=526001015");
  assert.equal(programCalls("/api/program"), before, "the old view fetched nothing more");
  view.unmount();
  root.remove();
  const again = await mountProgram(data, "526001015");
  assert.equal(programCalls("/api/program/526001015"), 1, "the new view fetches once");
  again.view.unmount();
  again.root.remove();
};

scenarios.finalPage = async () => {
  const data = clone(FIXTURE);
  data.game.completed = true;
  data.game.usPoints = 31;
  data.game.themPoints = 24;
  data.game.archived = true;
  data.weather = { available: false, source: "National Weather Service", error: "Game day has passed; no forecast to show." };
  const { root, view } = await mountProgram(data);
  const t = clean("final program", root);
  assert.ok(t.includes("SWT 31") && t.includes("Full game in the Archive"));
  assert.equal(root.querySelector("a.cover__action").getAttribute("href"), "#archive=526000600");
  assert.ok(!t.includes("Under way"));
  view.unmount();
  root.remove();
};

scenarios.countdownTicks = async () => {
  const data = clone(FIXTURE);
  data.game.kickoff = new Date(Date.now() + 62 * 60 * 1000).toISOString();
  const { root, view } = await mountProgram(data);
  const coverNode = root.querySelector(".cover");
  assert.ok(text(coverNode.querySelector(".cover__middle")).includes("1h 2m"));
  await advance(29 * 1000);
  assert.ok(text(coverNode.querySelector(".cover__middle")).includes("1h 2m"), "no tick before 30 s");
  await advance(3 * 60 * 1000); // six ticks, well inside the 15-minute refresh
  assert.equal(root.querySelector(".cover"), coverNode, "ticking never rebuilds the cover");
  assert.equal(programCalls("/api/program"), 1, "and never fetches");
  assert.ok(text(coverNode.querySelector(".cover__middle")).includes("Kickoff in 59 min"), text(coverNode.querySelector(".cover__middle")));
  view.unmount();
  await advance(60 * 1000);
  assert.ok(text(coverNode.querySelector(".cover__middle")).includes("Kickoff in 59 min"), "an unmounted view stops ticking");
  root.remove();
};

scenarios.revealOnce = async () => {
  const data = clone(FIXTURE);
  data.game.kickoff = new Date(Date.now() + 5 * 86400 * 1000).toISOString();
  const { root, view } = await mountProgram(data);
  assert.ok(cls(root.querySelector(".cover")).includes("cover--reveal"), "the first draw reveals");
  data.line.formatted = "Swampwater Tech -3.5";
  await view.refresh();
  await settle();
  assert.ok(!cls(root.querySelector(".cover")).includes("cover--reveal"), "a refresh does not replay it");
  assert.ok(cls(root.querySelector('[data-k="cover-line"]')).includes("flash"), "the moved line flashes");
  view.unmount();
  root.remove();
};

scenarios.damagedPage = async () => {
  const { root, view } = await mountProgram(clone(FIXTURE_DAMAGED));
  clean("damaged program", root);
  assert.ok(root.querySelector(".cover"));
  view.unmount();
  root.remove();
  const bare = await mountProgram({ game: { gameId: 1 } });
  clean("bare program", bare.root);
  bare.view.unmount();
  bare.root.remove();
};
"""

NAMES = ["twoTeam", "percentile", "ladderAndUnderline", "edges", "leaders", "coverStates", "coverTick", "faceOff", "formGuide", "weatherVenue", "zones", "programPage", "pickerOneFetch", "finalPage", "countdownTicks", "revealOnce", "damagedPage"]


@pytest.fixture
def fixture_file(tmp_path: Path) -> Path:
    path = tmp_path / "program.json"
    data = payload()
    data["__damaged"] = damaged(payload())
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


@needs_node
@pytest.mark.parametrize("scenario", NAMES)
def test_program_in_a_fake_browser(tmp_path: Path, fixture_file: Path, scenario: str) -> None:
    script = SCENARIOS.replace("FIXTURE_DAMAGED", "FIXTURE.__damaged")
    run_scenario(tmp_path, script, scenario, str(fixture_file))


# --- static checks ------------------------------------------------------------------------------------------


def test_program_rules_sit_under_the_program_anchor() -> None:
    anchor = CSS.index("/* === PROGRAM:")
    people = CSS.index("/* === PEOPLE:")
    block = CSS[anchor:people]
    for selector in (".tt td.lead", ".tt td.trail", ".leaders__head", ".cover__nav", ".zones", ".weather__radar", ".venue-line", ".ladder", ".tt__pct", ".form-guide", ".cover__faceoff"):
        assert selector in block, selector


def test_page_check_has_the_program_routes() -> None:
    from tools.page_check import ROUTE_GROUPS

    routes = ROUTE_GROUPS["PROGRAM"]
    assert "program" in routes and "program={LIVE}" in routes  # the game under way in the simulator
    assert {"program={LAST}", "program={NEXT}"} <= set(routes)  # a finished game and an upcoming one


def test_the_damaged_payload_is_really_damaged() -> None:
    bad = damaged(payload())
    assert bad["them"]["school"] is None and bad["profile"]["them"] == "nope" and bad["picker"][0] is None
