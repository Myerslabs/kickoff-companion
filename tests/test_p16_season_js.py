"""Phase 16, stream SEASON: Season, the team pages and Ratings in the fake browser (tests/fakedom.py).

Every national number is a linked unit (value and chip in one cell, the chip opening the national list, the
conference list with scope=conference, last season's list with year=), a row without a metric keeps a plain
chip, Mudpuppies schedule rows open the archive or the program while other teams' rows promise no tap, the poll
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
    return {"school": school, "abbreviation": abbr, "conference": "Biscuit Belt", "color": "#0021a5", "logo": f"/media/logo/{abbr}", "logoDark": f"/media/logo/{abbr}?v=dark", **extra}


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
            "opponent": {**team_block(opp, abbr), "apRank": ap}, "homeAway": "away" if week == 3 else "home", "venue": "Swampwater Tech Memorial Stadium",
            "completed": done, "result": result, "usPoints": us, "themPoints": them, "tv": "Biscuit Belt Network", "archived": archived,
            "opponentSp": {"rank": sp, "rating": 10.0} if sp else None, "winPct": win,
        }

    return {
        "season": 2026,
        "team": team_block("Swampwater Tech", "SWT"),
        "record": {"overall": {"wins": 2, "losses": 1, "ties": 0}, "conference": {"wins": 1, "losses": 0, "ties": 0}, "home": {"wins": 2, "losses": 0, "ties": 0}, "away": {"wins": 0, "losses": 1, "ties": 0}, "apRank": 18, "coachesRank": None, "spRank": 13, "spMetric": "rating:sp"},
        "schedule": [
            game(1001, 1, "Swampwater Tech Atlantic", "FAU", done=True, archived=True, result="W", us=66, them=21, sp=106, win={"value": 0.991, "estimate": False, "source": "postgame"}),
            game(1002, 2, "Silver Dollar", "GRID", done=True, archived=False, result="L", us=17, them=20, ap=12, sp=30, win={"value": 0.47, "estimate": False, "source": "postgame"}),
            game(1003, 3, "Diner Tech", "MISS", done=False, archived=False, ap=8, sp=20, win={"value": 0.25, "estimate": True, "source": "pregame Elo"}),
        ],
        "nextGameId": 1003,
        "standings": [
            {"team": "Diner Tech", "conference": {"wins": 1, "losses": 0}, "overall": {"wins": 3, "losses": 0}, "apRank": 8, "isUs": False, "place": 1, "form": [{"result": "W", "points": 41, "opponentPoints": 38, "opponent": "Louisville", "homeAway": "home"}]},
            {"team": "Swampwater Tech", "conference": {"wins": 1, "losses": 0}, "overall": {"wins": 2, "losses": 1}, "apRank": None, "isUs": True, "place": 2, "form": [{"result": "W", "points": 66, "opponentPoints": 21}, None, {"result": "L", "points": 17, "opponentPoints": 20, "opponent": "Silver Dollar", "homeAway": "away"}, {"result": "?"}]},
            {"team": "Silver Dollar", "conference": {"wins": 0, "losses": 1}, "overall": {"wins": 2, "losses": 1}, "apRank": 12, "isUs": False, "place": 3, "form": []},
        ],
        "polls": [
            {"poll": "AP", "metric": "poll:AP", "name": "AP Top 25", "week": 4, "usRank": 18, "pathWeeks": [{"week": 2}, {"week": 3}, {"week": 4}], "previousWeek": {"week": 3}, "ranks": [
                {"rank": 1, "school": "Texas", "conference": "Biscuit Belt", "points": 1500, "isUs": False, "previousRank": 3, "change": 2, "movement": "+2", "apPath": [3, 3, 1]},
                {"rank": 8, "school": "Diner Tech", "conference": "Biscuit Belt", "points": 1100, "isUs": False, "previousRank": 5, "change": -3, "movement": "-3", "apPath": [5, None, 8]},
                {"rank": 18, "school": "Swampwater Tech", "conference": "Biscuit Belt", "points": 400, "isUs": True, "previousRank": None, "change": None, "movement": "new", "apPath": [None, None, 18]},
            ]},
            {"poll": "Coaches", "metric": "poll:Coaches", "name": "Coaches Poll", "week": 4, "usRank": None, "ranks": [
                {"rank": 1, "school": "Texas", "conference": "Biscuit Belt", "points": 1600, "isUs": False, "previousRank": 1, "change": 0, "movement": "0"},
            ]},
        ],
        "profile": {"games": 3, "rows": profile_rows()},
        "advanced": {"rows": [
            {"side": "offense", "label": "Success rate", "key": "offense_success_rate", "metric": "advanced:offense_success_rate", "group": "Overall", "value": 0.486, "format": "pct", "nationalRank": 41, "nationalOf": 138},
            {"side": "defense", "label": "Success rate allowed", "key": "defense_success_rate", "metric": "advanced:defense_success_rate", "group": "Overall", "value": 0.391, "format": "pct", "nationalRank": 22, "nationalOf": 138},
            {"side": "offense", "label": "Run rate", "key": "offense_run_rate", "metric": "advanced:offense_run_rate", "group": "Tempo", "value": 0.52, "format": "pct", "nationalRank": None, "nationalOf": 138},
        ]},
        "ratings": {
            "sp": {"rating": 19.4, "rank": 13, "of": 138, "metric": "rating:sp", "offense": {"rating": 33.4, "rank": 21, "of": 138, "metric": "rating:spOffense"}, "defense": {"rating": 14.5, "rank": 10, "of": 138, "metric": "rating:spDefense"}},
            "elo": {"rating": 1668, "rank": 34, "of": 138, "metric": "rating:elo"},
            "fpi": {"rating": 16.4, "rank": 16, "of": 138, "metric": "rating:fpi", "strengthOfScheduleRank": 61, "strengthOfScheduleOf": 138, "strengthOfScheduleMetric": "rating:fpiSos", "strengthOfRecordRank": 5, "strengthOfRecordOf": 138},
        },
        "trends": {"weeks": [1, 2, 3], "opponents": ["Swampwater Tech Atlantic", "Silver Dollar", "Diner Tech"], "points": [66.0, None, None], "pointsAllowed": [21.0, 20.0, 3.0], "yardsPerPlay": [None, None, None], "turnoverMargin": [1, -1, 0], "thirdDown": [0.5, 0.4, 0.45]},
        "resume": {"expectedWins": 1.98, "gamesCounted": 3, "wins": 2, "losses": 1, "luck": 0.02, "sosPlayed": {"rating": 12.3, "rank": 41, "of": 138, "metric": "rating:sosPlayed"}, "remaining": {"games": [], "averageSp": 15.6, "rankAmongPlayed": 1, "of": 4}, "polls": [{"week": 3, "seasonType": "regular", "ap": 22, "coaches": None}, {"week": 4, "seasonType": "regular", "ap": 18, "coaches": 20}]},
        "lastSeason": {"year": 2025, "rows": [
            {"side": "offense", "label": "Points per game", "key": "ppg", "metric": "profile:ppg", "metricYear": 2025, "format": "1f", "now": {"value": 31.4, "rank": 12, "of": 136, "year": 2026}, "last": {"value": 24.0, "rank": 70, "of": 134, "year": 2025}, "better": True},
            {"side": "defense", "label": "Points allowed per game", "key": "opp_ppg", "format": "1f", "now": {"value": 18.2, "rank": 30, "of": 136}, "last": {"value": 25.0, "rank": 80, "of": 134}, "better": True},
        ]},
        "roadAhead": [{"gameId": 1003, "week": 3, "date": "2026-09-27T23:30:00.000Z", "site": "Home", "opponent": "Diner Tech", "record": "3-0", "apRank": 8, "sp": 15.2, "spRank": 20, "spOf": 138, "spMetric": "rating:sp", "lastThree": [{"result": "W", "score": "41-38", "opponent": "Louisville"}, {"result": "L", "score": "10-13"}]}],
        "playoff": {"week": 14, "metric": "poll:CFP", "usRank": None, "rankings": [{"rank": 1, "school": "Texas", "conference": "Biscuit Belt", "isUs": False}], "rounds": [
            {"round": "First Round", "games": [{"gameId": 9001, "slot": "FR1", "completed": True, "winner": "Texas", "isUs": False, "bowl": "At DKR", "away": {"school": "Clemson", "seed": 9, "points": 10}, "home": {"school": "Texas", "seed": 8, "points": 20}}]},
        ]},
        "parts": {},
    }


def ratings_payload() -> dict[str, Any]:
    teams = ["Georgia", "Ohio State", "Texas", "Oregon", "Alabama", "Silver Dollar", "LSU", "Penn State", "USC", "Michigan", "Tennessee", "Diner Tech", "Swampwater Tech", "Sweet Tea State"]
    rows = []
    for i, team in enumerate(teams, start=1):
        rows.append({
            "team": team, "conference": "Biscuit Belt" if team in {"Georgia", "Texas", "Alabama", "Silver Dollar", "LSU", "Tennessee", "Diner Tech", "Swampwater Tech", "Sweet Tea State"} else "Big Ten",
            "sp": {"rating": 30 - i, "rank": i}, "spOffense": {"rating": 40 - i, "rank": i}, "spDefense": {"rating": 10 + i, "rank": i}, "spSpecial": {"rating": 0.5, "rank": i},
            "elo": {"rating": 2000 - 10 * i, "rank": 15 - i}, "fpi": {"rating": 20 - i, "rank": i}, "talent": {"talent": 1000 - i, "rank": i, "of": 120},
            "core": {"value": 10 - i, "rank": i}, "coreOffense": {"value": 5, "rank": i}, "coreDefense": {"value": -2, "rank": i}, "srs": {"value": None, "rank": None},
            "adjEpa": {"value": None, "rank": None}, "adjEpaAllowed": {"value": None, "rank": None}, "sosPlayed": None,
        })
    return {
        "season": 2026, "team": "Swampwater Tech", "conference": "Biscuit Belt", "rows": rows, "us": rows[12], "conferences": [{"conference": "Biscuit Belt", "rating": 15.6, "offense": 34.0, "defense": 18.7, "specialTeams": 0.26, "rank": 1}],
        "published": {"core": True, "srs": False, "adjusted": False},
        "counts": {"sp": 136, "spOffense": 136, "spDefense": 136, "spSpecial": 136, "sosPlayed": 4, "elo": 136, "fpi": 136, "talent": 120, "core": 130, "coreOffense": 130, "coreDefense": 130, "srs": 0, "adjEpa": 0, "adjEpaAllowed": 0},
        "metrics": {"sp": "rating:sp", "spOffense": "rating:spOffense", "spDefense": "rating:spDefense", "spSpecial": "rating:spSpecial", "sosPlayed": "rating:sosPlayed", "elo": "rating:elo", "fpi": "rating:fpi", "talent": "rating:talent", "core": "rating:core", "coreOffense": "rating:coreOffense", "coreDefense": "rating:coreDefense", "srs": "rating:srs", "adjEpa": "adjusted:epa", "adjEpaAllowed": "adjusted:epaAllowed"},
        "parts": {},
    }


def team_payload(school: str) -> dict[str, Any]:
    us = school == "Swampwater Tech"
    return {
        "season": 2026,
        "team": team_block(school, "SWT" if us else "DT", record={"wins": 3, "losses": 0, "ties": 0}, conferenceRecord={"wins": 1, "losses": 0, "ties": 0}, apRank=None if us else 8, sp={"rating": 15.2, "rank": 13 if us else 20, "of": 138, "metric": "rating:sp"}, isUs=us,
                          form=[{"result": "W", "points": 41, "opponentPoints": 38, "opponent": "Okra Valley"}, {"result": "L", "points": 3, "opponentPoints": 7}]),
        "location": {"city": "Pleasant Corner" if us else "Willow Park", "state": "AL" if us else "VT"},
        "profile": {"rows": profile_rows()},
        "advanced": {"rows": []},
        "schedule": [
            {"gameId": 1001, "week": 1, "date": "2026-09-05T23:30:00.000Z", "opponent": team_block("Rhubarb State", "RHU"), "homeAway": "home", "completed": True, "result": "W", "usPoints": 66, "themPoints": 21, "archived": True},
            {"gameId": 1003, "week": 3, "date": "2026-09-27T23:30:00.000Z", "opponent": {**team_block("Silver Dollar", "GRID"), "apRank": 12}, "homeAway": "away", "completed": False, "archived": False},
        ],
        "roster": [{"playerId": 1, "number": 2, "name": "Mason Hamilton", "position": "QB", "classYear": "SO", "weight": 241}],
        "coaches": [],
        "series": None if us else {"team1": "Swampwater Tech", "team2": "Diner Tech", "usWins": 13, "themWins": 13, "ties": 1, "streak": {"team": "Diner Tech", "games": 1}, "lastTen": [
            {"season": 2025, "homeTeam": "Diner Tech", "awayTeam": "Swampwater Tech", "homeScore": 34, "awayScore": 24, "winner": "Diner Tech", "neutralSite": False},
            {"season": 2024, "homeTeam": "Swampwater Tech", "awayTeam": "Diner Tech", "homeScore": 24, "awayScore": 17, "winner": "Swampwater Tech", "neutralSite": False},
            {"season": 2020, "homeTeam": None, "awayTeam": "Swampwater Tech", "homeScore": "x"},
        ]},
        "recruiting": {"talent": {"talent": 891.07, "rank": 10, "of": 138, "metric": "rating:talent"}, "blueChip": None, "returning": None},
        "playValue": {"players": [], "usage": []},
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
    "ours": team_payload("Swampwater Tech"),
    "opponent": team_payload("Diner Tech"),
    "damaged": {"season": damaged(season_payload()), "ratings": damaged(ratings_payload()), "team": damaged(team_payload("Diner Tech"))},
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
  const nat = link(nationalHref("profile:ppg", { team: "Swampwater Tech" }));
  assert.ok(nat.length >= 2, "the tile and the profile row link the national list");
  const cell = nat.find((a) => a.parentNode.localName === "td");
  assert.ok(cell, "a profile chip sits in a table cell");
  assert.ok(!cell.parentNode.className.includes("txt"), "the value cell is numeric (right-aligned)");
  assert.ok(text(cell.parentNode).startsWith("31.4"), `value and chip in one cell: ${text(cell.parentNode)}`);
  assert.ok(link(nationalHref("profile:ppg", { team: "Swampwater Tech", scope: "conference" })).length === 1, "the Biscuit Belt chip opens the conference list");
  assert.ok(link(nationalHref("profile:ppg", { team: "Swampwater Tech", year: 2025 })).length === 1, "last season's chip carries the year");
  assert.ok(link(nationalHref("profile:ppg", { team: "Swampwater Tech" })).some((a) => a.closest("#season-last")), "this season's chip in the last-season band has no year");
  assert.ok(link(nationalHref("advanced:offense_success_rate", { team: "Swampwater Tech" })).length === 1);
  assert.ok(link(nationalHref("rating:spOffense", { team: "Swampwater Tech" })).length === 1, "Ratings band rows link by metric");
  assert.ok(link(nationalHref("rating:sosPlayed", { team: "Swampwater Tech" })).length === 1, "the résumé's schedule strength is a chip");
  assert.ok(link(nationalHref("rating:sp", { team: "Diner Tech" })).length === 1, "road-ahead SP+ links the opponent's row");
  // no metric: a plain chip (never a guessed link)
  const ypgd = [...all(main, "#season-profile .prof tr")].find((tr) => text(tr).startsWith("Yards allowed per game"));
  assert.ok(ypgd.querySelector("span.rank-chip") && !ypgd.querySelector("a.rank-chip--link"), "the row without a metric keeps a plain chip");
  assert.ok(![...all(main, ".tiles a.rank-chip--link")].some((a) => (a.getAttribute("aria-label") || "").startsWith("Yards allowed per game")), "nor is its tile");
  // a row with no rank keeps an invisible chip so its value lines up
  assert.ok(all(main, ".prof .rank-chip--placeholder").length >= 1);
  // poll ranks are poll badges linked to the poll
  assert.ok([...all(main, "a.poll-badge--link")].some((a) => a.getAttribute("href") === pollHref("AP", { team: "Silver Dollar" })));
  assert.ok([...all(main, "#season-resume a.poll-badge--link")].length === 3, "the poll path's ranks are badges");
  // tiles: 'of N' beside the chip
  assert.ok([...all(main, ".tile__of")].some((n) => text(n) === "of 136"));
  // trends: the last value captioned, the average beside it, and the wait text under two games
  assert.ok(t.includes("Trend after game 2"));
  assert.ok([...all(main, ".trend__avg")].some((n) => text(n) === "avg 14.7"), [...all(main, ".trend__avg")].map(text).join("|"));
  // schedule rows open the game: the archive when the app watched it, else the program
  const rows = [...all(main, "#season-schedule li.sched__game")];
  assert.equal(rows.length, 3);
  assert.ok(rows.every((li) => li.getAttribute("role") === "button" && text(li).includes("›")));
  assert.deepEqual(rows.map((li) => li.getAttribute("data-href")), ["#archive=1001", "#program=1002", "#program=1003"]);
  rows[0].click();
  assert.equal(window.location.hash, "archive=1001");
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
  // road-ahead form: linked results
  assert.ok([...all(main, "#season-road .form-result button.team-link")].some((b) => b.dataset.team === "Louisville"));
  // GX-06 movement and GX-17 form squares
  assert.equal(text(main.querySelector(".mv--up")), "+2");
  assert.equal(text(main.querySelector(".mv--down")), "−3");
  assert.equal(text(main.querySelector(".mv--new")), "new");
  const squares = main.querySelector("#season-standings tr.is-us .form");
  assert.equal(squares.getAttribute("aria-label"), "Last 2: W L", "nulls and unknown results are skipped");
  // the next opponent is marked and remembered for Ratings; the jump list is a page row
  assert.ok(main.querySelector("#season-standings tr.is-next"));
  assert.deepEqual(JSON.parse(localStorage.getItem("kickoff:next-opponent")), { school: "Diner Tech", gameId: 1003 });
  // Phase 17 #5: the sections are a chip row pinned above the page, one chip per band, never on a band head
  const chips = main.querySelector("nav.chips-row");
  assert.ok(chips && chips.nextSibling === main.querySelector(".page.season") && !main.querySelector(".band__head .chips-row"));
  assert.ok(chips.querySelectorAll(".chips-row__chip").map((c) => text(c)).includes("Schedule"));
  view.unmount();
};

scenarios.seasonState = async () => {
  installWindow();
  const { createSeasonView } = await import(moduleUrl("views/season.js"));
  const data = clone(FIXTURE.season);
  const { main, view, set } = await mountView(createSeasonView, "/api/season/overview", data);
  const pressed = () => [...all(main, "#season-polls .seg button")].filter((b) => b.getAttribute("aria-pressed") === "true").map((b) => b.dataset.poll);
  assert.deepEqual(pressed(), ["AP"]);
  main.querySelector('#season-polls button[data-poll="Coaches"]').click();
  assert.deepEqual(pressed(), ["Coaches"]);
  // new data: the page rebuilds, the choice stays, and the changed value is marked
  data.profile.rows[0].value = 33.0;
  set(data);
  await advance(1000);
  await view.refresh();
  assert.deepEqual(pressed(), ["Coaches"], "the poll choice survives a refresh");
  assert.equal(view.ui.poll, "Coaches");
  assert.ok(text(main.querySelector("#season-polls")).includes("Coaches Poll, week 4"));
  const changed = [...all(main, ".is-changed")];
  assert.ok(changed.some((n) => text(n) === "33.0"), "the new value is marked");
  view.unmount();
  // #season=polls:Coaches opens on that poll
  const second = await mountView(createSeasonView, "/api/season/overview", data, { arg: "polls:Coaches" });
  assert.equal(second.view.ui.poll, "Coaches");
  await advance(10);
  second.view.unmount();
  const { pollFromArg } = await import(moduleUrl("views/season.js"));
  assert.equal(pollFromArg("polls:AP"), "AP");
  assert.equal(pollFromArg("polls:nope"), null);
  assert.equal(pollFromArg(null), null);
};

scenarios.ratings = async () => {
  installWindow();
  localStorage.setItem("kickoff:next-opponent", JSON.stringify({ school: "Silver Dollar", gameId: 1003 }));
  const { createRatingsView, ratingTarget } = await import(moduleUrl("views/ratings.js"));
  intoView = 0;
  const data = clone(FIXTURE.ratings);
  const { main, view, set } = await mountView(createRatingsView, "/api/ratings", data);
  clean("ratings", main);
  const boxes = [...all(main, ".stat-table-wrap--box")];
  assert.ok(boxes.length >= 3);
  assert.ok(boxes.every((w) => w.scrollTop > 0), `every box opens on Swampwater Tech: ${boxes.map((w) => w.scrollTop)}`);
  assert.equal(intoView, 0, "never scrollIntoView: the page itself must not move");
  const next = main.querySelector("#ratings-sp tr.is-next");
  assert.ok(next && text(next).includes("Silver Dollar") && text(next).includes("Next"));
  // each rank is out of its own rating's count (talent covers 120 teams, not 14)
  assert.ok([...all(main, "#ratings-side a.rank-chip--link")].some((a) => a.getAttribute("title") === "1 of 120"));
  assert.ok([...all(main, "#ratings-sp a.rank-chip--link")].some((a) => a.getAttribute("href") === "#national=rating%3AspOffense?team=Swampwater%20Tech"));
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
  // #ratings=elo?team=Silver Dollar: the Elo table sorted by rank, Silver Dollar's row the focus, flashed
  const arrived = await mountView(createRatingsView, "/api/ratings", data, { arg: "elo", params: { team: "Silver Dollar" } });
  assert.deepEqual(arrived.view.state.sorts["ratings-side"], { key: "eloRank", dir: "ascending" });
  const focus = arrived.main.querySelector("#ratings-side tr.is-focus");
  assert.ok(focus && text(focus).includes("Silver Dollar"));
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
  installWindow();
  await useTeam();
  const { createTeamView } = await import(moduleUrl("views/team.js"));
  const { main, view } = await mountView(createTeamView, "/api/team/Swampwater%20Tech", FIXTURE.ours, { school: "Swampwater Tech" });
  clean("team", main);
  assert.ok(main.querySelector(".back-row a.back-row__link"), "a Back row on the team route");
  assert.ok(main.querySelector(".page"), "the single-column page container");
  const sp = [...all(main, ".team-head__facts a.team-head__link")];
  assert.equal(sp[0]?.getAttribute("href"), "#ratings=sp?team=Swampwater%20Tech", "SP+ is a dotted link to Ratings");
  assert.ok(main.querySelector(".team-head .form"), "the last five in the header");
  assert.ok([...all(main, "a.rank-chip--link")].some((a) => a.getAttribute("href") === "#national=profile%3Appg?team=Swampwater%20Tech&scope=conference"));
  assert.ok([...all(main, "a.rank-chip--link")].some((a) => a.getAttribute("href") === "#national=rating%3Atalent?team=Swampwater%20Tech"));
  main.querySelector('button[data-tab="schedule"]').click();
  const rows = [...all(main, "li.sched__game")].filter((li) => !li.className.includes("sched__game--bye")); // Phase 17 #37: a bye row sits in the gap
  assert.equal(rows.length, 2);
  assert.ok(rows.every((li) => li.getAttribute("role") === "button"), "Swampwater Tech's own games open");
  assert.equal(rows[0].getAttribute("data-href"), "#archive=1001");
  view.unmount();
};

scenarios.flyout = async () => {
  installWindow();
  await useTeam();
  const { openTeamFlyout, seriesRow } = await import(moduleUrl("views/team.js"));
  route("/api/team/Diner%20Tech", () => envelope(clone(FIXTURE.opponent)));
  openTeamFlyout("Diner Tech");
  await settle();
  const sheet = document.body.querySelector(".side-sheet") || document.body;
  const t = clean("flyout", sheet);
  const rows = [...all(sheet, "li.sched__game")].filter((li) => !li.className.includes("sched__game--bye"));
  assert.equal(rows.length, 2);
  assert.ok(rows.every((li) => !li.hasAttribute("role") && !li.hasAttribute("tabindex")), "another team's schedule promises no tap");
  assert.ok(!t.includes("›"));
  // the series from Swampwater Tech's side: the opponent a link, Swampwater Tech's score first in W/L color
  const history = [...all(sheet, "table")].find((tb) => text(tb).includes("Result"));
  assert.ok([...all(history, "td button.team-link")].some((b) => b.dataset.team === "Diner Tech"));
  assert.ok([...all(history, ".res--l")].some((n) => text(n) === "L 24-34"));
  assert.ok([...all(history, ".res--w")].some((n) => text(n) === "W 24-17"));
  assert.ok([...all(sheet, "a.poll-badge--link")].length >= 1, "the header's AP rank is a linked badge");
  assert.ok([...all(sheet, "a.team-head__link")].some((a) => a.getAttribute("href") === "#ratings=sp?team=Diner%20Tech"));
  assert.deepEqual(seriesRow({ season: 2019, homeTeam: "A", awayTeam: "B" }), { season: 2019, site: "–", opponent: null, result: null, score: null, margin: null });
  assert.equal(seriesRow(null).result, null);
  assert.equal(seriesRow({ homeTeam: "Swampwater Tech", awayTeam: "X", homeScore: 7, awayScore: 7, neutralSite: true }).site, "Neutral");
};

scenarios.damaged = async () => {
  installWindow();
  localStorage.setItem("kickoff:next-opponent", "not json");
  const { createSeasonView } = await import(moduleUrl("views/season.js"));
  const { createRatingsView } = await import(moduleUrl("views/ratings.js"));
  const { createTeamView, openTeamFlyout } = await import(moduleUrl("views/team.js"));
  for (const [factory, url, data, opts] of [
    [createSeasonView, "/api/season/overview", FIXTURE.damaged.season, {}],
    [createSeasonView, "/api/season/overview", {}, {}],
    [createRatingsView, "/api/ratings", FIXTURE.damaged.ratings, { arg: "talent", params: { team: "Nobody" } }],
    [createRatingsView, "/api/ratings", { rows: "x", counts: [], metrics: 3 }, {}],
    [createTeamView, "/api/team/Diner%20Tech", FIXTURE.damaged.team, { school: "Diner Tech" }],
    [createTeamView, "/api/team/Diner%20Tech", { team: null }, { school: "Diner Tech" }],
  ]) {
    const { main, view } = await mountView(factory, url, data, opts);
    const t = clean(url, main);
    assert.ok(!/could not be drawn/i.test(t), `${url} failed to draw: ${t.slice(0, 300)}`);
    for (const tab of [...all(main, "button[data-tab]")]) {
      tab.click();
      clean(`${url} tab ${tab.dataset.tab}`, main);
    }
    view.unmount();
  }
  route("/api/team/Diner%20Tech", () => envelope(clone(FIXTURE.damaged.team)));
  openTeamFlyout("Diner Tech");
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
  clean("schedule", scheduleList({ games: [null, { gameId: "x", opponent: "Silver Dollar", completed: true, result: 3, winPct: { value: 2 }, opponentSp: { rank: "x" } }, {}], onSelect: () => {}, context: true }));
  assert.equal(gameHref({ gameId: 5, completed: true, archived: true }), "#archive=5");
  assert.equal(gameHref({ gameId: 5, completed: false, archived: true }), "#program=5", "an unplayed game has no archive");
  assert.equal(gameHref({ gameId: "x" }), null);
  assert.equal(gameHref(null), null);
};
"""

NAMES = ["seasonLinks", "seasonState", "ratings", "teamPage", "flyout", "damaged", "graphics"]


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
    for selector in (".sched__game--tap", ".sched__ctx", ".trend__avg", ".mv--up", ".tight .stat-table", ".ratings .stat-table-wrap--box tbody tr.is-us td"):
        assert selector in block, selector
    assert "@container (min-width: 561px)" in CSS, "the tiles size to their column"
    assert not any(":hover" in line and "@media (hover: hover)" not in line for line in block.splitlines()), "hover only where a mouse hovers"
