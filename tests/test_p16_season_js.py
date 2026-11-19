"""Phase 16, stream SEASON: Season, the team pages and Ratings in the fake browser (tests/fakedom.py).

Every national number is linked (tables wave 3: the value and each rank in columns of their own, the chip opening the
national list, the conference list with scope=conference, last season's list with year=), a row without a metric keeps a
plain chip, the Season page's tables size themselves (the polls' own order a badge, a plain number at small; the FPI
schedule strengths' rank as their value at small), Gators schedule rows open the archive or the program while other teams' rows promise no tap, the poll
choice and a table's sort survive a refresh with new data, Ratings scrolls its own boxes (never
scrollIntoView) and marks the next opponent, and damaged payloads never print undefined, null or NaN."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from tests.fakedom import needs_node, run_scenario

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "static" / "css" / "components.css").read_text(encoding="utf-8")
PAGE_CHECK = (ROOT / "tools" / "page_check.py").read_text(encoding="utf-8")


# --- payloads shaped like the server's (values from the recorded 2026 fixtures, trimmed) ----------------------


def team_block(school: str, abbr: str, **extra: Any) -> dict[str, Any]:
    return {"school": school, "abbreviation": abbr, "conference": "SEC", "color": "#0021a5", "logo": f"/media/logo/{abbr}", "logoDark": f"/media/logo/{abbr}?v=dark", **extra}


def profile_rows() -> list[dict[str, Any]]:
    return [
        {"side": "offense", "label": "Points per game", "key": "ppg", "metric": "profile:ppg", "value": 31.4, "format": "1f", "nationalRank": 12, "nationalOf": 136, "conferenceRank": 3, "conferenceOf": 16},
        {"side": "offense", "label": "Yards per game", "key": "ypg", "metric": "profile:ypg", "value": 412.0, "format": "0f", "nationalRank": 20, "nationalOf": 136, "conferenceRank": 5, "conferenceOf": 16},
        {"side": "defense", "label": "Points allowed per game", "key": "opp_ppg", "metric": "profile:opp_ppg", "value": 18.2, "format": "1f", "nationalRank": 30, "nationalOf": 136, "conferenceRank": 4, "conferenceOf": 16},
        {"side": "defense", "label": "Yards allowed per game", "key": "ypg_d", "value": 330.0, "format": "0f", "nationalRank": 41, "nationalOf": 136, "conferenceRank": None, "conferenceOf": 16},
    ]


def season_payload() -> dict[str, Any]:
    def game(gid: int, week: int, opp: str, abbr: str, *, done: bool, archived: bool, result: str | None = None, us: int | None = None, them: int | None = None, ap: int | None = None, sp: int | None = None, win: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "gameId": gid, "week": week, "postseason": None, "playoffRound": None, "date": f"2026-09-{week + 4:02d}T23:30:00.000Z", "startTimeTbd": False,
            "opponent": {**team_block(opp, abbr), "apRank": ap}, "homeAway": "away" if week == 3 else "home", "venue": "Florida Memorial Stadium",
            "completed": done, "result": result, "usPoints": us, "themPoints": them, "tv": "SEC Network", "archived": archived,
            "opponentSp": {"rank": sp, "rating": 10.0} if sp else None, "winPct": win,
        }

    return {
        "season": 2026,
        "team": team_block("Florida", "FLA"),
        "record": {"overall": {"wins": 2, "losses": 1, "ties": 0}, "conference": {"wins": 1, "losses": 0, "ties": 0}, "home": {"wins": 2, "losses": 0, "ties": 0}, "away": {"wins": 0, "losses": 1, "ties": 0}, "apRank": 18, "coachesRank": None, "spRank": 13, "spMetric": "rating:sp"},
        "schedule": [
            game(1001, 1, "Florida Atlantic", "FAU", done=True, archived=True, result="W", us=66, them=21, sp=106, win={"value": 0.991, "estimate": False, "source": "postgame"}),
            game(1002, 2, "Fresno State", "FRES", done=True, archived=False, result="L", us=17, them=20, ap=12, sp=30, win={"value": 0.47, "estimate": False, "source": "postgame"}),
            game(1003, 3, "Texas State", "MISS", done=False, archived=False, ap=8, sp=20, win={"value": 0.25, "estimate": True, "source": "pregame Elo"}),
        ],
        "nextGameId": 1003,
        "standings": [
            {"team": "Texas State", "conference": {"wins": 1, "losses": 0}, "overall": {"wins": 3, "losses": 0}, "apRank": 8, "isUs": False, "place": 1, "form": [{"result": "W", "points": 41, "opponentPoints": 38, "opponent": "Louisville", "homeAway": "home"}]},
            {"team": "Florida", "conference": {"wins": 1, "losses": 0}, "overall": {"wins": 2, "losses": 1}, "apRank": None, "isUs": True, "place": 2, "form": [{"result": "W", "points": 66, "opponentPoints": 21}, None, {"result": "L", "points": 17, "opponentPoints": 20, "opponent": "Fresno State", "homeAway": "away"}, {"result": "?"}]},
            {"team": "Fresno State", "conference": {"wins": 0, "losses": 1}, "overall": {"wins": 2, "losses": 1}, "apRank": 12, "isUs": False, "place": 3, "form": []},
        ],
        "polls": [
            {"poll": "AP", "metric": "poll:AP", "name": "AP Top 25", "week": 4, "usRank": 18, "pathWeeks": [{"week": 2}, {"week": 3}, {"week": 4}], "previousWeek": {"week": 3}, "ranks": [
                {"rank": 1, "school": "Texas", "conference": "SEC", "conferenceShort": "BB", "points": 1500, "isUs": False, "previousRank": 3, "change": 2, "movement": "+2", "apPath": [3, 3, 1]},
                {"rank": 8, "school": "Texas State", "conference": "SEC", "points": 1100, "isUs": False, "previousRank": 5, "change": -3, "movement": "-3", "apPath": [5, None, 8]},
                {"rank": 18, "school": "Florida", "conference": "SEC", "points": 400, "isUs": True, "previousRank": None, "change": None, "movement": "new", "apPath": [None, None, 18]},
            ]},
            {"poll": "Coaches", "metric": "poll:Coaches", "name": "Coaches Poll", "week": 4, "usRank": None, "ranks": [
                {"rank": 1, "school": "Texas", "conference": "SEC", "points": 1600, "isUs": False, "previousRank": 1, "change": 0, "movement": "0"},
            ]},
        ],
        "profile": {"games": 3, "rows": profile_rows()},
        "advanced": {"rows": [
            {"side": "offense", "label": "Success rate", "key": "offense_success_rate", "metric": "advanced:offense_success_rate", "group": "Overall", "value": 0.486, "format": "pct", "nationalRank": 41, "nationalOf": 138},
            {"side": "defense", "label": "Success rate allowed", "key": "defense_success_rate", "metric": "advanced:defense_success_rate", "group": "Overall", "value": 0.391, "format": "pct", "nationalRank": 22, "nationalOf": 138},
            {"side": "offense", "label": "Run rate", "key": "offense_run_rate", "metric": "advanced:offense_run_rate", "group": "Tempo", "value": 0.52, "format": "pct", "nationalRank": None, "nationalOf": 138},
        ]},
        "ratings": {
            "sp": {"rating": 19.4, "rank": 13, "of": 138, "metric": "rating:sp", "offense": {"rating": 33.4, "rank": 21, "of": 138, "metric": "rating:spOffense"}, "defense": {"rating": 14.5, "rank": 10, "of": 138, "metric": "rating:spDefense"}, "special": {"rating": 0.6, "rank": 50, "of": 138, "metric": "rating:spSpecial"}},
            "elo": {"rating": 1668, "rank": 34, "of": 138, "metric": "rating:elo"},
            "fpi": {"rating": 16.4, "rank": 16, "of": 138, "metric": "rating:fpi", "strengthOfScheduleRank": 61, "strengthOfScheduleOf": 138, "strengthOfScheduleMetric": "rating:fpiSos", "strengthOfRecordRank": 5, "strengthOfRecordOf": 138},
        },
        "trends": {"weeks": [1, 2, 3], "opponents": ["Florida Atlantic", "Fresno State", "Texas State"], "points": [66.0, None, None], "pointsAllowed": [21.0, 20.0, 3.0], "yardsPerPlay": [None, None, None], "turnoverMargin": [1, -1, 0], "thirdDown": [0.5, 0.4, 0.45]},
        "resume": {"expectedWins": 1.98, "gamesCounted": 3, "wins": 2, "losses": 1, "luck": 0.02, "sosPlayed": {"rating": 12.3, "rank": 41, "of": 138, "metric": "rating:sosPlayed"}, "remaining": {"games": [], "averageSp": 15.6, "rankAmongPlayed": 1, "of": 4}, "polls": [{"week": 3, "seasonType": "regular", "ap": 22, "coaches": None}, {"week": 4, "seasonType": "regular", "ap": 18, "coaches": 20}]},
        "lastSeason": {"year": 2025, "rows": [
            {"side": "offense", "label": "Points per game", "key": "ppg", "metric": "profile:ppg", "metricYear": 2025, "format": "1f", "now": {"value": 31.4, "rank": 12, "of": 136, "year": 2026}, "last": {"value": 24.0, "rank": 70, "of": 134, "year": 2025}, "better": True},
            {"side": "defense", "label": "Points allowed per game", "key": "opp_ppg", "format": "1f", "now": {"value": 18.2, "rank": 30, "of": 136}, "last": {"value": 25.0, "rank": 80, "of": 134}, "better": True},
        ]},
        "roadAhead": [{"gameId": 1003, "week": 3, "date": "2026-09-27T23:30:00.000Z", "site": "Home", "opponent": "Texas State", "record": "3-0", "apRank": 8, "sp": 15.2, "spRank": 20, "spOf": 138, "spMetric": "rating:sp", "lastThree": [{"result": "W", "score": "41-38", "opponent": "Louisville"}, {"result": "L", "score": "10-13"}]}],
        "playoff": {"week": 14, "metric": "poll:CFP", "usRank": None, "rankings": [{"rank": 1, "school": "Texas", "conference": "SEC", "isUs": False}], "rounds": [
            {"round": "First Round", "games": [{"gameId": 9001, "slot": "FR1", "completed": True, "winner": "Texas", "isUs": False, "bowl": "At DKR", "away": {"school": "Clemson", "seed": 9, "points": 10}, "home": {"school": "Texas", "seed": 8, "points": 20}}]},
        ]},
        "parts": {},
    }


def ratings_payload() -> dict[str, Any]:
    teams = ["Georgia", "Ohio State", "Texas", "Oregon", "Alabama", "Fresno State", "LSU", "Penn State", "USC", "Michigan", "Tennessee", "Texas State", "Florida", "Ole Miss"]
    rows = []
    for i, team in enumerate(teams, start=1):
        rows.append({
            "team": team, "conference": "SEC" if team in {"Georgia", "Texas", "Alabama", "Fresno State", "LSU", "Tennessee", "Texas State", "Florida", "Ole Miss"} else "Big Ten",
            "sp": {"rating": 30 - i, "rank": i}, "spOffense": {"rating": 40 - i, "rank": i}, "spDefense": {"rating": 10 + i, "rank": i}, "spSpecial": {"rating": 0.5, "rank": i},
            "elo": {"rating": 2000 - 10 * i, "rank": 15 - i}, "fpi": {"rating": 20 - i, "rank": i}, "talent": {"talent": 1000 - i, "rank": i, "of": 120},
            "core": {"value": 10 - i, "rank": i}, "coreOffense": {"value": 5, "rank": i}, "coreDefense": {"value": -2, "rank": i}, "srs": {"value": None, "rank": None},
            "adjEpa": {"value": None, "rank": None}, "adjEpaAllowed": {"value": None, "rank": None}, "sosPlayed": None,
        })
    return {
        "season": 2026, "team": "Florida", "conference": "SEC", "rows": rows, "us": rows[12], "conferences": [{"conference": "SEC", "rating": 15.6, "offense": 34.0, "defense": 18.7, "specialTeams": 0.26, "rank": 1}],
        "published": {"core": True, "srs": False, "adjusted": False},
        "counts": {"sp": 136, "spOffense": 136, "spDefense": 136, "spSpecial": 136, "sosPlayed": 4, "elo": 136, "fpi": 136, "talent": 120, "core": 130, "coreOffense": 130, "coreDefense": 130, "srs": 0, "adjEpa": 0, "adjEpaAllowed": 0},
        "metrics": {"sp": "rating:sp", "spOffense": "rating:spOffense", "spDefense": "rating:spDefense", "spSpecial": "rating:spSpecial", "sosPlayed": "rating:sosPlayed", "elo": "rating:elo", "fpi": "rating:fpi", "talent": "rating:talent", "core": "rating:core", "coreOffense": "rating:coreOffense", "coreDefense": "rating:coreDefense", "srs": "rating:srs", "adjEpa": "adjusted:epa", "adjEpaAllowed": "adjusted:epaAllowed"},
        "parts": {},
    }


def team_payload(school: str) -> dict[str, Any]:
    us = school == "Florida"
    return {
        "season": 2026,
        "team": team_block(school, "FLA" if us else "DT", record={"wins": 3, "losses": 0, "ties": 0}, conferenceRecord={"wins": 1, "losses": 0, "ties": 0}, apRank=None if us else 8, sp={"rating": 15.2, "rank": 13 if us else 20, "of": 138, "metric": "rating:sp"}, isUs=us,
                          form=[{"result": "W", "points": 41, "opponentPoints": 38, "opponent": "Georgia"}, {"result": "L", "points": 3, "opponentPoints": 7}]),
        "location": {"city": "Pleasant Corner" if us else "Willow Park", "state": "AL" if us else "VT"},
        "profile": {"rows": profile_rows()},
        "advanced": {"rows": []},
        "schedule": [
            {"gameId": 1001, "week": 1, "date": "2026-09-05T23:30:00.000Z", "opponent": team_block("Akron", "RHU"), "homeAway": "home", "completed": True, "result": "W", "usPoints": 66, "themPoints": 21, "archived": True},
            {"gameId": 1003, "week": 3, "date": "2026-09-27T23:30:00.000Z", "opponent": {**team_block("Fresno State", "FRES"), "apRank": 12}, "homeAway": "away", "completed": False, "archived": False},
        ],
        "roster": [{"playerId": 1, "number": 2, "name": "Mason Hamilton", "position": "QB", "classYear": "SO", "weight": 241}],
        # tables wave 3: the coaches, the play value and usage, and the standings the team page sizes
        "coaches": [
            {"name": "Pat Whistler", "hireDate": "2021-11-28T00:00:00.000Z", "wins": 6, "losses": 2, "ties": 0, "year": 2026, "srs": 12.4, "spOverall": 18.3},
            {"name": "Lee Clipboard", "hireDate": "2024-01-05", "wins": None, "losses": None, "ties": None, "year": 2026, "srs": None, "spOverall": None},
        ],
        # freeze wave F3: one Staff band; the resolver's names, the season load's date, CFBD's rows inside it
        "staff": {
            "headCoach": "Pat Whistler", "offensiveCoordinator": "Ora Chalk", "defensiveCoordinator": None,
            "sources": {"headCoach": "season", "offensiveCoordinator": "season"}, "source": "The season's coaches load", "savedAt": "2026-08-01",
            "full": [{"name": "Ora Chalk", "role": "Offensive coordinator"}, {"name": "Sam Whistle", "role": "Tight ends coach"}],
            "cfbd": [
                {"name": "Pat Whistler", "hireDate": "2021-11-28T00:00:00.000Z", "wins": 6, "losses": 2, "ties": 0, "year": 2026, "srs": 12.4, "spOverall": 18.3},
                {"name": "Lee Clipboard", "hireDate": "2024-01-05", "wins": None, "losses": None, "ties": None, "year": 2026, "srs": None, "spOverall": None},
            ],
        },
        "standings": None if us else {"conference": "Pac-12", "conferenceShort": "PA", "rows": [
            {"place": 1, "team": "Texas State", "abbreviation": "DT", "logo": "/media/logo/DT", "conference": {"wins": 2, "losses": 0}, "overall": {"wins": 3, "losses": 0}, "apRank": 8, "isUs": True, "form": [{"result": "W", "points": 41, "opponentPoints": 38}]},
            {"place": 2, "team": "Florida", "abbreviation": "FLA", "logo": "/media/logo/FLA", "conference": {"wins": 1, "losses": 1}, "overall": {"wins": 2, "losses": 1}, "apRank": None, "isUs": False, "form": []},
        ]},
        "series": None if us else {"team1": "Florida", "team2": "Texas State", "usWins": 13, "themWins": 13, "ties": 1, "streak": {"team": "Texas State", "games": 1}, "lastTen": [
            {"season": 2025, "homeTeam": "Texas State", "awayTeam": "Florida", "homeScore": 34, "awayScore": 24, "winner": "Texas State", "neutralSite": False},
            {"season": 2024, "homeTeam": "Florida", "awayTeam": "Texas State", "homeScore": 24, "awayScore": 17, "winner": "Florida", "neutralSite": False},
            {"season": 2020, "homeTeam": None, "awayTeam": "Florida", "homeScore": "x"},
        ]},
        "recruiting": {"talent": {"talent": 891.07, "rank": 10, "of": 138, "metric": "rating:talent"}, "blueChip": None, "returning": None},
        "playValue": {
            "players": [
                {"playerId": "pv1", "name": "Avery Runner", "position": "RB", "plays": 64, "all": 0.12, "pass": None, "rush": 0.12},
                {"playerId": "pv2", "name": "Quinn Thrower Jr.", "position": "QB", "plays": 210, "all": 0.31, "pass": 0.36, "rush": 0.05},
            ],
            "usage": [
                {"playerId": "pv1", "name": "Avery Runner", "position": "RB", "overall": 0.18, "pass": 0.02, "rush": 0.41},
                {"playerId": "pv2", "name": "Quinn Thrower Jr.", "position": "QB", "overall": 0.52, "pass": 0.88, "rush": 0.12},
            ],
        },
        "parts": {},
    }


def damaged(payload: Any) -> Any:
    """Every scalar and list in the payload swapped for junk, a level at a time (the server is untrusted)."""
    junk = [None, "x", -1, {}, [], True, 1e308, "NaN"]
    out = copy.deepcopy(payload)

    def walk(node: Any, depth: int) -> Any:
        if isinstance(node, dict):
            for i, key in enumerate(list(node)):
                if (i + depth) % 3 == 0:
                    node[key] = junk[(i + depth) % len(junk)]
                else:
                    node[key] = walk(node[key], depth + 1)
            return node
        if isinstance(node, list):
            return [None, *[walk(item, depth + 1) for item in node], "junk"]
        return node

    return walk(out, 0)


FIXTURE = {
    "season": season_payload(),
    "ratings": ratings_payload(),
    "ours": team_payload("Florida"),
    "opponent": team_payload("Texas State"),
    "damaged": {"season": damaged(season_payload()), "ratings": damaged(ratings_payload()), "team": damaged(team_payload("Texas State"))},
}


SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object Object\]/;
const text = (node) => (node ? node.textContent : "");
const clean = (label, node) => {
  const t = text(node);
  assert.ok(!RAW.test(t), `${label} printed ${JSON.stringify(t.match(/.{0,60}(undefined|null|NaN|Infinity|\[object Object\]).{0,60}/)?.[0])}`);
  return t;
};
const all = (root, sel) => root.querySelectorAll(sel);
const proto = Object.getPrototypeOf(document.body);
let intoView = 0;
proto.scrollIntoView = function () { intoView += 1; };

async function mountView(factory, url, data, opts = {}) {
  const { clearEnvelopeCache } = await import(moduleUrl("views/common.js"));
  clearEnvelopeCache();
  let current = clone(data);
  route(url, () => envelope(current));
  const main = document.createElement("main");
  document.body.append(main);
  const view = factory(opts);
  view.mount(main);
  await settle();
  return { main, view, set: (next) => { current = clone(next); } };
}

scenarios.seasonLinks = async () => {
  installWindow();
  const { createSeasonView } = await import(moduleUrl("views/season.js"));
  const { nationalHref, pollHref } = await import(moduleUrl("ui/national-link.js"));
  const { main, view } = await mountView(createSeasonView, "/api/season/overview", FIXTURE.season);
  const t = clean("season", main);
  assert.ok(!/could not be drawn/i.test(t), t.slice(0, 200));
  const link = (href) => [...all(main, "a.rank-chip--link")].filter((a) => a.getAttribute("href") === href);
  // national, conference and last-season chips each open their own list
  const nat = link(nationalHref("profile:ppg", { team: "Florida" }));
  assert.ok(nat.length >= 2, "the tile and the profile row link the national list");
  const cell = nat.find((a) => a.parentNode.localName === "td");
  assert.ok(cell, "a profile chip sits in a table cell");
  // tables wave 3 (rule 3): every data point in its own column, the value and then its FBS rank (from medium)
  const cells = [...cell.parentNode.parentNode.childNodes];
  const valueCell = cells[cells.indexOf(cell.parentNode) - 1];
  assert.ok(!valueCell.className.includes("txt"), "the value cell is numeric (right-aligned)");
  assert.equal(text(valueCell), "31.4", "the value alone in its cell");
  assert.equal(text(cell.parentNode), "#12", "the chip alone in the next");
  assert.ok(cell.parentNode.className.includes("st__min-medium"), "the FBS rank from medium");
  assert.ok(link(nationalHref("profile:ppg", { team: "Florida", scope: "conference" })).length === 1, "the SEC chip opens the conference list");
  assert.ok(link(nationalHref("profile:ppg", { team: "Florida", year: 2025 })).length === 1, "last season's chip carries the year");
  assert.ok(link(nationalHref("profile:ppg", { team: "Florida" })).some((a) => a.closest("#season-last")), "this season's chip in the last-season band has no year");
  assert.ok(link(nationalHref("advanced:offense_success_rate", { team: "Florida" })).length === 1);
  assert.ok(link(nationalHref("rating:spOffense", { team: "Florida" })).length === 1, "Ratings band rows link by metric");
  assert.ok(link(nationalHref("rating:sosPlayed", { team: "Florida" })).length === 1, "the résumé's schedule strength is a chip");
  assert.ok(link(nationalHref("rating:sp", { team: "Texas State" })).length === 1, "road-ahead SP+ links the opponent's row");
  // no metric: a plain chip (never a guessed link)
  const ypgd = [...all(main, "#season-profile .prof tr")].find((tr) => text(tr).startsWith("Yards allowed per game"));
  assert.ok(ypgd.querySelector("span.rank-chip") && !ypgd.querySelector("a.rank-chip--link"), "the row without a metric keeps a plain chip");
  assert.ok(![...all(main, ".tiles a.rank-chip--link")].some((a) => (a.getAttribute("aria-label") || "").startsWith("Yards allowed per game")), "nor is its tile");
  // a row with no rank shows a dash in that rank's own column (wave 3: no invisible placeholder beside the value)
  assert.equal(text(ypgd.querySelectorAll("td")[3]), "–", "no conference rank: a dash");
  assert.ok(ypgd.querySelectorAll("td")[3].className.includes("st__min-large"), "the conference rank at large");
  assert.equal(all(main, ".rank-chip--placeholder").length, 0);
  // poll ranks are poll badges linked to the poll
  assert.ok([...all(main, "a.poll-badge--link")].some((a) => a.getAttribute("href") === pollHref("AP", { team: "Fresno State" })));
  // ENH-19: the poll path is a chart; the ranks in its two rows of numbers still open their poll's list
  const pathLinks = [...all(main, "#season-resume a.pp__link")];
  assert.ok(pathLinks.length === 3 && pathLinks.every((a) => /^#national=poll/.test(a.getAttribute("href"))), "the poll path's ranks link to their poll");
  // tiles: 'of N' beside the chip
  assert.ok([...all(main, ".tile__of")].some((n) => text(n) === "of 136"));
  // trends (board 9): one column a game, the season average under each stat's name
  assert.ok(all(main, "#season-trends .tgrid__game").length >= 1, "the games head the columns");
  assert.ok([...all(main, ".tgrid__avgtext")].some((n) => text(n) === "avg 14.7"), [...all(main, ".tgrid__avgtext")].map(text).join("|"));
  // every row opens the game's program (the mock, owner 2026-10-20: the prior weeks' programs are reached here; a finished game's program leads to the Archive)
  const rows = [...all(main, "#season-schedule li.sched__game")];
  assert.equal(rows.length, 3);
  assert.ok(rows.every((li) => li.getAttribute("role") === "button" && text(li).includes("›")));
  assert.deepEqual(rows.map((li) => li.getAttribute("data-href")), ["#program=1001", "#program=1002", "#program=1003"]);
  rows[0].click();
  assert.equal(window.location.hash, "program=1001");
  rows[2].click();
  assert.equal(window.location.hash, "program=1003");
  // GX-08: the opponent's SP+ chip and the win chance, the estimate marked
  assert.ok(t.includes("Opp SP+") && text(rows[2]).includes("25%") && text(rows[2]).includes("est."));
  assert.ok(!text(rows[0]).includes("est."));
  // Phase 17 #33: a played game shows its result, never a win chance
  assert.ok(!text(rows[0]).includes("99%") && !rows[0].querySelector(".sched__ctx-win") && !rows[1].querySelector(".sched__ctx-win"));
  assert.ok(rows[0].querySelector(".sched__ctx-sp"));
  // G3-07: playoff sides with their seeds and the winner are team links
  const playoff = main.querySelector("#season-playoff");
  assert.ok([...all(playoff, "td button.team-link")].map((b) => b.dataset.team).includes("Clemson"));
  assert.ok(text(playoff).includes("(9)"));
  // road-ahead form (wave 3): the last three as the standings' squares, each square's title the score and the opponent
  const roadForm = main.querySelector("#season-road .form");
  assert.equal(roadForm.getAttribute("aria-label"), "Last 2: W L");
  assert.equal(roadForm.querySelector(".form__sq--w").getAttribute("title"), "Won 41-38 vs Louisville");
  assert.equal(roadForm.querySelector(".form__sq--l").getAttribute("title"), "Lost 10-13");
  // tables wave 3 (owner 2026-10-10): the Season page's own tables size themselves, every data point in its own column
  const marks = (ths) => ths.map((th) => (th.className.includes("st__min-large") ? "L" : th.className.includes("st__min-medium") ? "M" : ""));
  for (const id of ["season-standings", "season-ratings", "season-resume", "season-profile", "season-numbers", "season-road", "season-last", "season-playoff"]) { // the Season stop (Wave 4): Advanced is The numbers' first view
    assert.ok([...all(main, `#${id} .stat-table-wrap`)].every((wrap) => wrap.dataset.size), `${id}: every table sized`);
  }
  // the polls (wave 3, 2026-11-01: the Newspaper's band now, ui/polls-band.js, drawn here from the same answer): the poll's
  // own order (its badge, a plain number at small), the team, its conference's own column
  const { pollsBand } = await import(moduleUrl("ui/polls-band.js"));
  const pollsNode = pollsBand(clone(FIXTURE.season), { ui: { poll: null, sorts: {} } });
  main.append(pollsNode);
  const pollHeads = [...all(main, "#season-polls thead th")];
  assert.deepEqual(pollHeads.map((th) => th.dataset.term), ["AP rank", "Team", "Conference", "±", "AP path", "Points"], "no first-place votes in the payload: no column");
  assert.deepEqual(marks(pollHeads), ["", "", "M", "", "L", ""], "the conference from medium, the AP path at large");
  assert.equal(pollHeads[0].querySelector(".sz-t--short").textContent, "#");
  const top = main.querySelector("#season-polls tbody tr").querySelectorAll("td");
  assert.ok(top[0].querySelector(".sz-t--long .poll-badge") && top[0].querySelector(".sz-t--short").textContent === "1", "the badge at large and medium, the number at small");
  assert.equal(top[2].querySelector(".sz-t--long").textContent, "SEC");
  assert.equal(top[2].querySelector(".sz-t--mid").textContent, "BB", "the conference's short name at medium");
  assert.ok(top[1].querySelector(".sz-t--short button.team-link"), "the team stays a link at small");
  // the ratings: the value and its FBS rank apart; the FPI schedule strengths show their rank as the value at small
  const ratingRows = [...all(main, "#season-ratings tbody tr")];
  const sos = ratingRows.find((tr) => tr.querySelector("td").dataset.term === "Strength of schedule").querySelectorAll("td");
  assert.equal(sos[1].querySelector(".sz-t--long").textContent, "–");
  assert.equal(sos[1].querySelector(".sz-t--short").textContent, "#61");
  assert.ok(sos[2].className.includes("st__min-medium") && sos[2].querySelector("a.rank-chip--link"));
  const special = ratingRows.find((tr) => tr.querySelector("td").dataset.term === "SP+ special teams");
  assert.ok(special && special.className.includes("st__min-large"), "special teams at large only");
  assert.deepEqual([...all(main, "#season-ratings thead th")].map((th) => th.dataset.term), ["Rating", "Value", "FBS rank"]);
  // the standings sort, place first
  assert.ok(main.querySelector("#season-standings thead th button"), "teams sort");
  assert.equal(text(main.querySelector("#season-standings tbody tr td")), "1");
  // GX-06 movement and GX-17 form squares
  assert.equal(text(main.querySelector(".mv--up")), "+2");
  assert.equal(text(main.querySelector(".mv--down")), "−3");
  assert.equal(text(main.querySelector(".mv--new")), "new");
  const squares = main.querySelector("#season-standings tr.is-us .form");
  assert.equal(squares.getAttribute("aria-label"), "Last 2: W L", "nulls and unknown results are skipped");
  // the next opponent is marked and remembered for Ratings; the jump list is a page row
  assert.ok(main.querySelector("#season-standings tr.is-next"));
  assert.deepEqual(JSON.parse(localStorage.getItem("kickoff:next-opponent")), { school: "Texas State", gameId: 1003 });
  // Phase 17 #5: the sections are a chip row pinned above the page, one chip per band, never on a band head
  const chips = main.querySelector("nav.chips-row");
  assert.ok(chips && chips.nextSibling === main.querySelector(".page.season") && !main.querySelector(".band__head .chips-row"));
  assert.ok(chips.querySelectorAll(".chips-row__chip").map((c) => text(c)).includes("Schedule"));
  view.unmount();
};

scenarios.seasonStop = async () => {
  // the Season stop (the season as one line, Wave 4; the owner's board of 2026-10-30): The numbers box at the bottom with
  // Advanced on the switch, Our land from the map, the schedule rows' three stops following the line, and Last and Next on
  // the window leading to their stops
  installWindow();
  route("/api/numbers/Florida", () => envelope({ team: { games: 2, offense: { successRate: 0.49, ranks: { successRate: 10 } }, defense: {} }, rankOf: {} }));
  route("/api/imperialism/2026/team/Florida", () => envelope({
    season: 2026, now: { cells: 380, pct: 3.4, rank: 7, of: 110 },
    weeks: [{ phase: "regular", week: 0, label: "Start", partial: false, cells: 300, record: "0-0" }, { phase: "regular", week: 1, label: "Wk 1", partial: false, cells: 420, record: "1-0" }, { phase: "regular", week: 2, label: "Wk 2", partial: false, cells: 380, record: "1-1" }],
    events: [{ phase: "regular", week: 1, winner: "Florida", loser: "Florida Atlantic", cellsMoved: 120, rule: "win" }, { phase: "regular", week: 2, winner: "Fresno State", loser: "Florida", cellsMoved: 40, rule: "win" }],
  }));
  const { createSeasonView } = await import(moduleUrl("views/season.js"));
  const { main, view } = await mountView(createSeasonView, "/api/season/overview", FIXTURE.season);
  await settle();
  clean("the Season stop", main);
  const box = main.querySelector("#season-numbers");
  assert.ok(box, "The numbers box at the bottom");
  const seg = box.querySelector(".box__switch");
  assert.deepEqual(seg.querySelectorAll("button").map((b) => text(b)), ["Advanced"], "Advanced alone: the app's numbers left the box (his inventory, 2026-11-01)");
  assert.ok(text(box.querySelector(".box__view .d2-head")).startsWith("Advanced") && box.querySelectorAll("table").length === 1, "opens on Advanced, the one paired table");
  assert.ok(!main.querySelector("#season-advanced"), "Advanced is a view of the box, not a band");
  // Our land
  const land = main.querySelector("#season-land");
  assert.ok(land && text(land).includes("380") && text(land).includes("7th of the 110 schools holding land") && text(land).includes("Took from Florida Atlantic") && land.querySelector('a[href="#imperialism"]'), text(land));
  const lines = land.querySelectorAll(".land__line").map((l) => text(l));
  assert.ok(lines[0].startsWith("Wk 2") && lines[0].includes("-40") && lines[1].startsWith("Wk 1") && lines[1].includes("+120"), `latest first: ${lines.join(" | ")}`);
  // My Team's cover is our team alone since 2026-11-20: no Last or Next on it (the schedule's rows and the rail lead to the stops)
  assert.equal(main.querySelector('[data-k="pick:last"]'), null);
  assert.equal(main.querySelector('[data-k="pick:next"]'), null);
  // the schedule rows' three stops follow the line
  const { _setStops } = await import(moduleUrl("stops.js"));
  _setStops({ now: "2026-09-21T12:00-04:00", current: { kind: "season", href: "#season", label: "Season", detail: "the season right now" }, items: [
    { kind: "week", week: 2, gameId: 1002, opponent: "Fresno State", result: { usPoints: 17, themPoints: 20, won: false }, stops: { pre: { state: "saved", href: "#program=1002?tab=pre" }, game: { state: "done", href: "#archive=1002" }, post: { state: "live", href: "#postgame=1002" } } },
    { kind: "week", week: 3, gameId: 1003, opponent: "Texas State", result: null, stops: { pre: { state: "open", href: "#program=1003" }, game: { state: "to_come", href: null }, post: { state: "to_come", href: null } } },
  ] });
  const rows = main.querySelectorAll("#season-schedule .sched__game");
  const marksOf = (row) => row.querySelectorAll(".stops .rail__mark").map((m) => m.className);
  const r1002 = rows.find((r) => text(r).includes("Fresno State"));
  assert.deepEqual(marksOf(r1002), ["rail__mark rail__mark--square rail__mark--saved", "rail__mark rail__mark--circle rail__mark--done rail__mark--lost", "rail__mark rail__mark--square rail__mark--live"]);
  assert.deepEqual(r1002.querySelectorAll(".stops a").map((a) => a.getAttribute("href")), ["#program=1002?tab=pre", "#archive=1002", "#postgame=1002"]);
  const r1003 = rows.find((r) => text(r).includes("Texas State"));
  assert.equal(r1003.querySelectorAll(".stops a").length, 1, "only the open Pre-Game is a link ahead of the game");
  const r1001 = rows.find((r) => text(r).includes("Florida Atlantic"));
  assert.equal(r1001.querySelector(".stops").hidden, true, "a game the line does not have: no marks");
  clean("the Season stop after the line", main);
  view.unmount();
  main.remove();
};

scenarios.seasonState = async () => {
  installWindow();
  const { createSeasonView } = await import(moduleUrl("views/season.js"));
  const data = clone(FIXTURE.season);
  const { main, view, set } = await mountView(createSeasonView, "/api/season/overview", data);
  // the polls' switch (wave 3, 2026-11-01: the band is the Newspaper's; its choice lives in the ui it is given)
  const { pollsBand } = await import(moduleUrl("ui/polls-band.js"));
  const pollsUi = { poll: null, sorts: {} };
  const polls = pollsBand(data, { ui: pollsUi });
  main.append(polls);
  const pressed = () => [...all(main, "#season-polls .seg button")].filter((b) => b.getAttribute("aria-pressed") === "true").map((b) => b.dataset.poll);
  assert.deepEqual(pressed(), ["AP"]);
  main.querySelector('#season-polls button[data-poll="Coaches"]').click();
  assert.deepEqual(pressed(), ["Coaches"]);
  assert.equal(pollsUi.poll, "Coaches");
  assert.ok(text(main.querySelector("#season-polls")).includes("Coaches Poll, week 4"));
  polls.remove();
  const again = pollsBand(data, { ui: pollsUi });
  main.append(again);
  assert.deepEqual(pressed(), ["Coaches"], "drawn again with the same ui: the choice stays");
  again.remove();
  // new data: the page rebuilds and the changed value is marked
  data.profile.rows[0].value = 33.0;
  set(data);
  await advance(1000);
  await view.refresh();
  const changed = [...all(main, ".is-changed")];
  assert.ok(changed.some((n) => text(n) === "33.0"), "the new value is marked");
  view.unmount();
  const { pollFromArg } = await import(moduleUrl("views/season.js"));
  assert.equal(pollFromArg("polls:AP"), "AP");
  assert.equal(pollFromArg("polls:nope"), null);
  assert.equal(pollFromArg(null), null);
};

scenarios.ratings = async () => {
  installWindow();
  localStorage.setItem("kickoff:next-opponent", JSON.stringify({ school: "Fresno State", gameId: 1003 }));
  const { createRatingsView, ratingTarget } = await import(moduleUrl("views/ratings.js"));
  intoView = 0;
  const data = clone(FIXTURE.ratings);
  const { main, view, set } = await mountView(createRatingsView, "/api/ratings", data);
  clean("ratings", main);
  // no table scrolls inside the page (owner 2026-10-10): every team is on the page, each band folds
  // and each sizes itself (owner 2026-10-10, "size them now"): the team's abbreviation at small, the sub-ranks from medium or large
  for (const id of ["ratings-sp", "ratings-more", "ratings-side", "ratings-conferences"]) assert.ok(main.querySelector(`#${id} .stat-table-wrap`).dataset.size, id);
  assert.ok([...all(main, "#ratings-sp thead th")].filter((th) => th.className.includes("st__min-large")).length >= 4, "Special, SOS and their ranks only at large");
  assert.equal([...all(main, ".stat-table-wrap--box")].length, 0);
  assert.ok([...all(main, ".stat-table-wrap")].length >= 3);
  for (const id of ["ratings-sp", "ratings-more", "ratings-side"]) assert.ok(main.querySelector(`#${id}`).className.includes("band--foldable"), id);
  assert.equal(intoView, 0, "never scrollIntoView");
  const next = main.querySelector("#ratings-sp tr.is-next");
  assert.ok(next && text(next).includes("Fresno State") && text(next).includes("Next"));
  // each rank is out of its own rating's count (talent covers 120 teams, not 14)
  assert.ok([...all(main, "#ratings-side a.rank-chip--link")].some((a) => a.getAttribute("title") === "1 of 120"));
  assert.ok([...all(main, "#ratings-sp a.rank-chip--link")].some((a) => a.getAttribute("href") === "#national=rating%3AspOffense?team=Florida"));
  // the reader's sort survives a refresh with new data
  [...all(main, "#ratings-side th button")].find((b) => text(b) === "Elo").click();
  assert.equal(view.state.sorts["ratings-side"].key, "eloRating");
  data.rows[0].sp.rating = 31;
  set(data);
  await advance(1000);
  await view.refresh();
  const sorted = [...all(main, "#ratings-side th")].find((th) => th.getAttribute("aria-sort"));
  assert.equal(text(sorted), "Elo", "the Elo sort is still on after the rebuild");
  view.unmount();
  // #ratings=elo?team=Fresno State: the Elo table sorted by rank, Fresno State's row the focus, flashed
  const arrived = await mountView(createRatingsView, "/api/ratings", data, { arg: "elo", params: { team: "Fresno State" } });
  assert.deepEqual(arrived.view.state.sorts["ratings-side"], { key: "eloRank", dir: "ascending" });
  const focus = arrived.main.querySelector("#ratings-side tr.is-focus");
  assert.ok(focus && text(focus).includes("Fresno State"));
  assert.ok(focus.querySelector("td.flash"));
  await advance(10);
  assert.equal(intoView, 0);
  arrived.view.unmount();
  assert.deepEqual(ratingTarget("rating:talent"), { key: "talent", band: "ratings-side", column: "talentRank" });
  assert.deepEqual(ratingTarget("adjusted:epaAllowed"), { key: "adjEpaAllowed", band: "ratings-more", column: "adjAllowedRank" });
  assert.equal(ratingTarget("bogus"), null);
  assert.equal(ratingTarget(undefined), null);
};

scenarios.teamPage = async () => {
  // wave 3 of the one-column page (owner 2026-11-01): #team=<school> is My Team's page of that team, no tabs; the team page's
  // own bands (Talent and recruiting, Staff, Play value, School facts) load from /api/team into hosts at the bottom
  installWindow();
  await useTeam();
  route("/api/team/Florida", () => envelope(clone(FIXTURE.ours)));
  const { createSeasonView } = await import(moduleUrl("views/season.js"));
  const { main, view } = await mountView(createSeasonView, "/api/season/overview", clone(FIXTURE.season), { params: { team: "Florida", tab: "roster" } });
  await settle();
  clean("team", main);
  assert.ok(main.querySelector(".page.season"), "the one scroll");
  assert.equal(text(main.querySelector(".cover__name")), "Florida", "our own school asked for by name is the home team's page");
  assert.ok([...all(main, "a.rank-chip--link")].some((a) => a.getAttribute("href") === "#national=rating%3Atalent?team=Florida"), "Talent and recruiting from the team's own answer, at the bottom");
  const rows = [...all(main, "#season-schedule li.sched__game")].filter((li) => !li.className.includes("sched__game--bye"));
  assert.ok(rows.length >= 2 && rows.every((li) => li.getAttribute("role") === "button"), "Florida's own games open");
  const strip = main.querySelector("#season-schedule .ms");
  assert.ok(strip && strip.querySelector(".ms__bar"), "the margin strip over the games");
  for (const id of ["team-recruiting", "team-staff", "team-playvalue", "team-facts", "roster-table", "recruiting-class"]) assert.ok(main.querySelector(`#${id}`), `${id} on the page`);
  assert.equal(main.querySelector("button[data-tab]"), null, "no tabs");
  view.unmount();
};

scenarios.flyout = async () => {
  installWindow();
  await useTeam();
  const { openTeamFlyout } = await import(moduleUrl("views/team.js"));
  const { seriesRows } = await import(moduleUrl("ui/series.js"));
  route("/api/team/Texas%20State", () => envelope(clone(FIXTURE.opponent)));
  route("/api/injuries?team=Texas%20State", () => envelope({ team: { school: "Texas State" }, isUs: false, games: [{ gameId: 1002, week: 2, homeAway: "away", completed: true, opponent: { school: "Texas State" }, notes: true, reported: true, source: "Conference report", rows: [{ name: "Hurt Guy", position: "QB", status: "Out", note: "Shoulder" }], unassigned: [] }], counts: { games: 1, reports: 1 } }));
  openTeamFlyout("Texas State");
  await settle();
  const sheet = document.body.querySelector(".side-sheet") || document.body;
  const t = clean("flyout", sheet);
  // owner 2026-10-10: every team's sheet carries its injury report (our games against it), its roster (folded) and its recruiting
  const injuryBand = [...all(sheet, "section.band")].find((b) => text(b.querySelector(".band__head")).includes("Injury report"));
  assert.ok(injuryBand && text(injuryBand).includes("Hurt Guy") && text(injuryBand).includes("Week 2 at Texas State") && text(injuryBand).includes("1 out"), text(injuryBand));
  assert.equal(sheet.querySelector("#sheet-roster")?.getAttribute("data-collapsed"), "true", "the roster folded: a long list");
  assert.ok(sheet.querySelector("#sheet-recruiting"), "its talent and recruiting");
  assert.equal(sheet.querySelector("#team-roster"), null, "the sheet's own ids, never the team page's");
  const rows = [...all(sheet, "li.sched__game")].filter((li) => !li.className.includes("sched__game--bye"));
  assert.equal(rows.length, 2);
  // wave 3: the sheet's bands have ids of their own, so a team page under the sheet keeps its own
  for (const id of ["team-schedule", "team-standings", "team-history"]) assert.equal(sheet.querySelector(`#${id}`), null, id);
  assert.ok(sheet.querySelector("#sheet-standings") && sheet.querySelector("#sheet-history"), "the sheet's standings and series");
  // owner 2026-10-10: the schedule sits right under the four tiles, before the stat tables
  const sched = sheet.querySelector("#sheet-schedule");
  const kids = [...sched.parentNode.children];
  const at = kids.indexOf(sched);
  assert.ok(at > 0 && kids[at - 1].querySelector(".tiles"), "the tiles right above the schedule");
  assert.ok(text(kids[at + 1]).includes("Offense"), "the Offense table right below it");
  assert.ok(rows.every((li) => !li.hasAttribute("role") && !li.hasAttribute("tabindex")), "another team's schedule promises no tap");
  assert.equal(sched.querySelector("a.ms__slot")?.getAttribute("href"), "#program=1001?team=Texas%20State", "its margin strip's bars open its games from its side (ENH-19, FEAT-5)");
  assert.ok(!t.includes("›"));
  // the series from Florida's side: the opponent a link, Florida's score first in W/L color
  const history = [...all(sheet, "table")].find((tb) => text(tb).includes("Result"));
  assert.ok([...all(history, "td button.team-link")].some((b) => b.dataset.team === "Texas State"));
  assert.ok([...all(history, ".res--l")].some((n) => text(n) === "L 24-34"));
  assert.ok([...all(history, ".res--w")].some((n) => text(n) === "W 24-17"));
  assert.ok([...all(sheet, "a.poll-badge--link")].length >= 1, "the header's AP rank is a linked badge");
  assert.ok([...all(sheet, "a.team-head__link")].some((a) => a.getAttribute("href") === "#ratings=sp?team=Texas%20State"));
  // the series is the Pre-Game Program's table (ui/series.js): our score first in the result, the schools short at small
  assert.equal(history.querySelector("tbody td button.team-link .sz-t--short")?.textContent, "FLA", "ours from the identity at small");
  assert.deepEqual(seriesRows({ lastTen: [{ season: 2019, homeTeam: "A", awayTeam: "B" }] }, "Florida")[0], { season: "2019", away: "B", home: "A", awayAbbr: null, homeAbbr: null, score: "–", winner: null, winnerAbbr: null, won: null, result: null });
  assert.deepEqual(seriesRows(null, "Florida"), []);
  assert.equal(seriesRows({ lastTen: [{ homeTeam: "Florida", awayTeam: "X", homeScore: 7, awayScore: 7 }] }, "Florida")[0].result, "T 7-7");
};

scenarios.teamTables = async () => {
  // tables wave 3 (owner 2026-10-10): the team page's own tables size themselves, each data point in its own column
  installWindow();
  await useTeam();
  const players = [];
  route("/api/players/", (url) => { players.push(url); return envelope({ player: { playerId: "pv2", name: "Quinn Thrower Jr." }, parts: {} }); });
  const { coachRow, openTeamFlyout } = await import(moduleUrl("views/team.js"));
  const { createSeasonView } = await import(moduleUrl("views/season.js"));
  route("/api/team/Texas%20State", () => envelope(clone(FIXTURE.opponent)));
  const theirs = clone(FIXTURE.season);
  theirs.team = { ...theirs.team, school: "Texas State", conferenceShort: "SBC" }; // the overview answers the team asked for; its late bands follow its school
  const { main, view } = await mountView(createSeasonView, "/api/season/overview?team=Texas%20State", theirs, { params: { team: "Texas State" } });
  await advance(50); // the late bands' own answer (/api/team) lands after the page
  await settle();
  clean("team tables", main);
  const marks = (ths) => ths.map((th) => (th.className.includes("st__min-large") ? "L" : th.className.includes("st__min-medium") ? "M" : ""));
  const heads = (root) => [...all(root, "thead th")];
  const terms = (root) => heads(root).map((th) => th.dataset.term);
  const cells = (root, i) => [...all(root, "tbody tr")[i].querySelectorAll("td")];
  // Talent and recruiting: Measure | Value | FBS rank (medium), the chip in its own column and still the list's link
  const recruiting = main.querySelector("#team-recruiting");
  assert.deepEqual(terms(recruiting), ["Measure", "Value", "FBS rank"]);
  assert.deepEqual(marks(heads(recruiting)), ["", "", "M"]);
  const talent = cells(recruiting, 0);
  assert.equal(talent[0].querySelector(".sz-t--short").textContent, "Talent");
  assert.equal(text(talent[1]), "891", "the value alone");
  assert.equal(talent[2].querySelector("a.rank-chip--link").getAttribute("href"), "#national=rating%3Atalent?team=Texas%20State");
  // play value and usage: the player (the surname at small), his position from medium, sorted by the value
  const [ppa, usage] = all(main, "#team-playvalue .stat-table-wrap");
  assert.deepEqual(terms(ppa), ["Player", "Pos", "Plays", "PPA per play", "Pass", "Rush"]);
  assert.deepEqual(marks(heads(ppa)), ["", "M", "M", "", "", ""]);
  assert.deepEqual([heads(ppa)[3].querySelector(".sz-t--mid").textContent, heads(ppa)[3].querySelector(".sz-t--short").textContent], ["PPA/play", "PPA"]);
  assert.equal(heads(ppa)[3].getAttribute("aria-sort"), "descending", "the best play value first");
  assert.deepEqual([pnText(cells(ppa, 0)[0], "last"), pnText(cells(ppa, 0)[0], "initial"), text(cells(ppa, 0)[1])], ["Thrower", "Q. Thrower", "QB"], "item 6: the name steps down with the table");
  assert.equal(text(cells(ppa, 1)[4]), "–", "no pass value: a dash");
  assert.deepEqual(terms(usage), ["Player", "Pos", "Usage", "Pass", "Rush"]);
  assert.equal(heads(usage)[2].getAttribute("aria-sort"), "descending");
  assert.equal(pnText(cells(usage, 0)[0]), "Quinn Thrower Jr.");
  all(ppa, "tbody tr")[0].click();
  await settle();
  assert.equal(players.length, 1, "a row opens the player card");
  document.body.querySelector(".card-layer")?.remove();
  // Freeze wave F3 (one fact, one source): no Coaches table beside the Staff band; the one band names the head coach and the
  // coordinators as the resolver does, with CFBD's hire date and record on the head coach's line, the rest of the staff, and
  // any other coach CFBD lists on a line of his own
  assert.equal(main.querySelector("#team-coaches"), null, "the Coaches table went");
  const staff = main.querySelector("#team-staff");
  clean("staff", staff);
  const st = text(staff);
  assert.ok(st.includes("Head coach") && st.includes("Pat Whistler") && st.includes("hired") && st.includes("6-2 this season") && st.includes("SP+ 18.3") && st.includes("CFBD"), st.slice(0, 400));
  assert.ok(st.includes("Offensive coordinator") && st.includes("Ora Chalk") && st.includes("Sam Whistle, Tight ends coach"), "the coordinator once, the rest of the staff after");
  assert.ok(st.includes("Also listed by CFBD this season") && st.includes("Lee Clipboard"), "a second listed coach on his own line");
  assert.ok(text(staff.querySelector(".band__summary")).includes("the season's coaches load"), "the band says its source");
  assert.deepEqual(coachRow({ hireDate: "soon", wins: "6", ties: 1 }), { hireDate: "soon", wins: "6", ties: 1, hired: "–", hiredYear: null, hiredAt: null, recordText: "–", spOverall: null, srs: null });
  assert.equal(coachRow(null).hired, "–");
  view.unmount();
  // the standings and the series: the team's sheet keeps them (wave 3: the series left the team page for the Pre-Game Program)
  openTeamFlyout("Texas State");
  await settle();
  const sheet = document.body;
  const standings = sheet.querySelector("#sheet-standings");
  assert.deepEqual(terms(standings), ["#", "Team", "PA", "Overall", "AP rank", "Last 5"]);
  assert.deepEqual(marks(heads(standings)), ["", "", "", "", "M", "L"]);
  assert.ok(all(standings, "tbody tr")[0].className.includes("is-next") && all(standings, "tbody tr")[1].className.includes("is-us"));
  assert.equal(cells(standings, 0)[1].querySelector(".sz-t--short button.team-link").textContent, "DT");
  assert.equal(cells(standings, 0)[5].querySelector(".form").getAttribute("aria-label"), "Last 1: W");
  const series = sheet.querySelector("#sheet-history");
  assert.deepEqual(terms(series), ["Year", "Away", "Home", "Score", "Winner", "Result"]);
  assert.deepEqual(marks(heads(series)), ["", "", "", "M", "M", ""]);
  assert.ok(!heads(series).some((th) => th.querySelector("button")), "a series reads back from the last game: no sort");
  assert.equal(text(cells(series, 0)[0]), "2025");
  assert.deepEqual([cells(series, 0)[1].querySelector(".sz-t--short").textContent, cells(series, 0)[2].querySelector(".sz-t--short").textContent], ["FLA", "DT"]);
  assert.ok(text(series).includes("Florida's score first in the result."));
  document.body.querySelector(".sheet-layer")?.remove();
};

scenarios.damaged = async () => {
  installWindow();
  localStorage.setItem("kickoff:next-opponent", "not json");
  const { createSeasonView } = await import(moduleUrl("views/season.js"));
  const { createRatingsView } = await import(moduleUrl("views/ratings.js"));
  const { openTeamFlyout } = await import(moduleUrl("views/team.js"));
  route("/api/team/Texas%20State", () => envelope(clone(FIXTURE.damaged.team)));
  for (const [factory, url, data, opts] of [
    [createSeasonView, "/api/season/overview", FIXTURE.damaged.season, {}],
    [createSeasonView, "/api/season/overview", {}, {}],
    [createRatingsView, "/api/ratings", FIXTURE.damaged.ratings, { arg: "talent", params: { team: "Nobody" } }],
    [createRatingsView, "/api/ratings", { rows: "x", counts: [], metrics: 3 }, {}],
    [createSeasonView, "/api/season/overview?team=Texas%20State", FIXTURE.damaged.season, { params: { team: "Texas State" } }], // wave 3: a team's page is My Team's, its late bands from a damaged /api/team
    [createSeasonView, "/api/season/overview?team=Texas%20State", { team: null }, { params: { team: "Texas State" } }],
  ]) {
    const { main, view } = await mountView(factory, url, data, opts);
    await settle();
    const t = clean(url, main);
    assert.ok(!/could not be drawn/i.test(t), `${url} failed to draw: ${t.slice(0, 300)}`);
    view.unmount();
  }
  route("/api/team/Texas%20State", () => envelope(clone(FIXTURE.damaged.team)));
  openTeamFlyout("Texas State");
  await settle();
  clean("damaged flyout", document.body);
};

scenarios.graphics = async () => {
  const { formSquares, tiles } = await import(moduleUrl("ui/team-page.js"));
  const { trendRow, average } = await import(moduleUrl("ui/sparkline.js"));
  const { gameHref, recordLine, scheduleList } = await import(moduleUrl("ui/schedule.js"));
  // GX-17 form squares: newest right, nulls and unknown results skipped, five at most
  const five = formSquares([{ result: "L" }, { result: "W" }, null, { result: "W" }, "x", { result: "T" }, { result: "W" }, { result: "L" }]);
  assert.equal(five.getAttribute("aria-label"), "Last 5: W W T W L");
  assert.deepEqual([...all(five, ".form__sq")].map((n) => n.className), ["form__sq form__sq--w", "form__sq form__sq--w", "form__sq form__sq--t", "form__sq form__sq--w", "form__sq form__sq--l"]);
  for (const bad of [null, undefined, [], "WWL", [{ result: "?" }], {}]) assert.equal(formSquares(bad), null);
  // trend rows: last and average, never a raw NaN
  assert.equal(average([1, null, 3, "x"]), 2);
  assert.equal(average([]), null);
  for (const values of [[], [null], [1], [1, 2], "x", null, [NaN, Infinity]]) clean(`trend ${JSON.stringify(values)}`, trendRow({ label: "Points", values }));
  // tiles and the record box with junk
  clean("tiles", tiles([{ label: null, value: "x", rank: "3", of: {} }, null, { label: "Yards", value: 3, rank: 2, of: 136, href: "#national=profile%3Aypg" }]));
  clean("record", recordLine({ overall: null, apRank: "x", spRank: NaN }));
  clean("record", recordLine());
  clean("schedule", scheduleList({ games: [null, { gameId: "x", opponent: "Fresno State", completed: true, result: 3, winPct: { value: 2 }, opponentSp: { rank: "x" } }, {}], onSelect: () => {}, context: true }));
  assert.equal(gameHref({ gameId: 5, completed: true, archived: true }), "#program=5", "a played game opens its program (the mock, 2026-10-20); the program leads to the Archive");
  assert.equal(gameHref({ gameId: 5, completed: false, archived: true }), "#program=5");
  assert.equal(gameHref({ gameId: "x" }), null);
  assert.equal(gameHref(null), null);
};
"""

NAMES = ["seasonLinks", "seasonStop", "seasonState", "ratings", "teamPage", "flyout", "teamTables", "damaged", "graphics"]


@pytest.fixture(scope="module")
def fixture_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("season") / "fixture.json"
    path.write_text(json.dumps(FIXTURE), encoding="utf-8")
    return path


@needs_node
@pytest.mark.parametrize("scenario", NAMES)
def test_season_team_and_ratings_in_a_fake_browser(tmp_path: Path, fixture_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario, str(fixture_path))


def test_the_damaged_payloads_really_are_damaged() -> None:
    bad = FIXTURE["damaged"]["season"]
    assert bad != season_payload()
    flat = json.dumps(bad)
    assert '"junk"' in flat and "null" in flat and "1e+308" in flat


def test_page_check_covers_the_season_routes() -> None:
    group = PAGE_CHECK.split('"SEASON": [', 1)[1].split("]", 1)[0]
    for route in ("season", "season=polls:Coaches", "team={US}", "team={OPP}", "ratings", "ratings=sp"):
        assert f'"{route}"' in group, route


def test_season_css_sits_under_its_anchor() -> None:
    block = CSS.split("/* === SEASON: Season, Team page, Ratings === */", 1)[1].split("/* === PROGRAM:", 1)[0]
    for selector in (".sched__game--tap", ".sched__ctx", ".trend__avg", ".mv--up", ".tight .stat-table", ".ratings .stat-table tbody tr.is-us td"):
        assert selector in block, selector
    assert "@container (min-width: 561px)" in CSS, "the tiles size to their column"
    assert not any(":hover" in line and "@media (hover: hover)" not in line for line in block.splitlines()), "hover only where a mouse hovers"
