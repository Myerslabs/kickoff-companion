"""The schedule margin strip (ENH-19, chart 3; the owner's board of 2026-10-30, "Build it as drawn"): a bar a game in the
Season page's Schedule band, our margin in the opponent's color, the games to come as dashed ticks, each slot opening its
game."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fakedom import needs_node, run_scenario

ROOT = Path(__file__).resolve().parents[1]

SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object \w+\]/;
const text = (node) => (node ? node.textContent : "");

const GAMES = [
  { gameId: 1, week: 1, homeAway: "home", result: "W", usPoints: 66, themPoints: 21, opponent: { school: "Florida Atlantic", abbreviation: "FAU", color: "#003366", altColor: "#cc0000" } },
  { gameId: 2, week: 2, homeAway: "home", result: "W", usPoints: 52, themPoints: 3, opponent: { school: "Campbell" } },
  { gameId: 3, week: 3, homeAway: "away", result: "W", usPoints: 44, themPoints: 39, opponent: { school: "Auburn", abbreviation: "AUB", color: "#0c2340" } },
  { gameId: 5, week: 5, homeAway: "away", result: "L", usPoints: 17, themPoints: 45, opponent: { school: "Missouri", abbreviation: "MIZ", color: "#f1b82d" } },
  { gameId: 7, week: 7, homeAway: "away", result: "W", usPoints: 27, themPoints: 24, opponent: { school: "Texas", abbreviation: "TEX", color: "#bf5700", altColor: "#ffffff" } },
  { gameId: 9, week: 9, homeAway: "neutral", result: null, usPoints: null, themPoints: null, date: "2026-10-31T19:30:00Z", opponent: { school: "Georgia", abbreviation: "UGA" } },
  { gameId: 10, week: 10, homeAway: "home", result: null, opponent: { school: "Oklahoma", abbreviation: "OU" } },
  { gameId: 20, week: 16, postseason: "Gator Bowl", homeAway: "neutral", result: "W", usPoints: 30, themPoints: 30, opponent: { school: "Iowa", abbreviation: "IOWA" } },
];

scenarios.strip = async () => {
  installWindow();
  const ms = await import(moduleUrl("ui/margin-strip.js"));
  assert.equal(ms.marginOf(GAMES[0]), 45);
  assert.equal(ms.marginOf(GAMES[3]), -28);
  assert.equal(ms.marginOf(GAMES[5]), null, "a game to come has no margin");
  assert.equal(ms.marginOf({ result: "W", usPoints: "x", themPoints: 3 }), null);
  assert.equal(ms.marginOf(null), null);
  const slots = ms.slotsOf(GAMES);
  assert.deepEqual(slots.map((s) => (s.bye ? `bye${s.week}` : s.post ? "post" : s.week)), [1, 2, 3, "bye4", 5, "bye6", 7, "bye8", 9, 10, "post"], "a bye for each regular week with no game, the postseason after");
  assert.deepEqual(ms.slotsOf([null, "x", { week: "y" }]), []);
  const padded = ms.slotsOf([{ gameId: 1, week: 3 }], { from: 1, to: 5 });
  assert.deepEqual(padded.map((s) => (s.bye ? `bye${s.week}` : s.week)), ["bye1", "bye2", 3, "bye4", "bye5"], "two strips line up over the same weeks");
  // each bar in the opponent's own color, ours allowed (every bar is an opponent), lightened to read on the panel
  assert.equal(ms.barColor({ color: "#bf5700" }), "#bf5700", "Texas's burnt orange is allowed here");
  assert.equal(ms.barColor({ color: "#f1b82d" }), "#f1b82d");
  assert.notEqual(ms.barColor({ color: "#003366" }), "#003366", "a navy too dark for the panel is lightened");
  assert.equal(ms.barColor({ school: "Campbell" }), "#9AA1AE", "no color on file: the fog");
  const svg = ms.marginChart({ games: GAMES, nextGameId: 9, width: 480 });
  assert.equal(svg.getAttribute("viewBox"), "0 0 480 210");
  const bars = svg.querySelectorAll(".ms__bar");
  assert.equal(bars.length, 6, "one bar a game played (the tie too)");
  assert.equal(Number(bars[3].getAttribute("y")), 104, "a loss hangs below the line");
  assert.ok(Number(bars[0].getAttribute("y")) < 104, "a win stands above it");
  assert.ok(bars[5].className.includes("ms__bar--tie") || (bars[5].getAttribute("class") || "").includes("ms__bar--tie"), "a tie is a sliver in the fog");
  assert.deepEqual(svg.querySelectorAll(".ms__margin").map((t) => t.textContent), ["+45", "+49", "+5", "−28", "+3", "T"]);
  assert.equal(svg.querySelectorAll(".ms__tick").length, 2, "the games to come: dashed ticks");
  assert.equal(svg.querySelectorAll(".ms__tick--next").length, 1, "the next one marked");
  assert.ok(text(svg.querySelector(".ms__day")).length >= 2, "with its day");
  const links = svg.querySelectorAll("a.ms__slot");
  assert.equal(links.length, 8, "every game opens its program; a bye opens nothing");
  assert.equal(links[0].getAttribute("href"), "#program=1");
  assert.ok(links[3].getAttribute("aria-label").includes("lost by 28, 17-45"), links[3].getAttribute("aria-label"));
  assert.ok(text(svg).includes("@MIZ") && text(svg).includes("bye") && text(svg).includes("Post"));
  assert.ok(!text(svg).includes("@UGA"), "a neutral site is not away");
  const other = ms.marginChart({ games: GAMES, team: "Texas", width: 480 });
  assert.equal(other.querySelector("a.ms__slot").getAttribute("href"), "#program=1?team=Texas", "another team's strip opens its games from its side");
  const narrow = ms.marginChart({ games: [...GAMES, ...GAMES.map((g) => ({ ...g, gameId: g.gameId + 100, week: (g.week || 0) + 20, postseason: null }))], width: 300 });
  assert.ok(!text(narrow).includes("@MIZ"), "no room: the opponents go, the weeks stay");
  assert.ok(!RAW.test(text(svg)) && !RAW.test(text(narrow)));
  // the block
  const block = ms.marginStrip({ games: GAMES, nextGameId: 9 });
  assert.ok(text(block).includes("Margin by week") && block.querySelector(".ms__chart svg"));
  assert.equal(ms.marginStrip({ games: [] }), null, "no games: no strip");
  assert.equal(ms.marginStrip({ games: "junk" }), null);
  const broken = ms.marginStrip({ games: [{ week: 1, result: "W", usPoints: null, themPoints: 3, opponent: null }, { week: 2, opponent: "x" }] });
  assert.ok(broken && !RAW.test(text(broken)), text(broken));
};
"""


scenarios_program = r"""
scenarios.program = async () => {
  installWindow();
  const { marginBand, PROGRAM_BANDS } = await import(moduleUrl("views/program.js"));
  const data = { game: { gameId: 9 }, us: { school: "Florida", abbreviation: "FLA" }, them: { school: "Georgia", abbreviation: "UGA" }, margins: { us: GAMES, them: [{ gameId: 30, week: 1, homeAway: "home", result: "W", usPoints: 63, themPoints: 3, opponent: { school: "Tennessee State", abbreviation: "TNST" } }, { gameId: 9, week: 9, homeAway: "neutral", result: null, opponent: { school: "Florida", abbreviation: "FLA", color: "#0021a5" } }] } };
  const b = marginBand(data);
  assert.equal(b.getAttribute("id"), "program-margins");
  assert.equal(text(b.querySelector(".band__summary")), "FLA 5-1 · UGA 1-0", "both records from the games' results");
  const heads = b.querySelectorAll(".ms__head h4").map((h) => h.textContent);
  assert.deepEqual(heads, ["Florida", "Georgia"], "a strip a team, headed by its school");
  assert.equal(b.querySelectorAll(".ms__note").length, 1, "the line under them once");
  const theirs = b.querySelectorAll(".ms")[1].querySelector("a.ms__slot");
  assert.equal(theirs.getAttribute("href"), "#program=30?team=Georgia", "their games open from their side");
  assert.equal(b.querySelectorAll(".ms__tick--next").length, 2, "this week's game marked in both");
  const weekRows = b.querySelectorAll(".ms").map((strip) => strip.querySelectorAll(".ms__axis").filter((t) => /^\d+$/.test(t.textContent)).map((t) => t.textContent).join(","));
  assert.equal(weekRows[0], weekRows[1], "both strips over the same weeks");
  assert.ok(!RAW.test(text(b)));
  assert.equal(marginBand({ us: {}, them: {} }), null, "an old lock with none: no band");
  const empty = marginBand({ us: { school: "Florida" }, them: {}, margins: { us: [], them: [] } });
  assert.ok(text(empty).includes("Neither team has played a game yet"));
  assert.ok(typeof PROGRAM_BANDS.week === "function" && PROGRAM_BANDS.weekPpa === undefined, "Margin by week's flyout from the menu (wave 3, 2026-11-01: Play value by game is the Ratings page's)");
};
"""


def test_the_program_carries_both_teams_margins(client, fake_cfbd):
    """ENH-19 chart 3 on the Pre-Game Program (owner 2026-10-30: "Add to program"): both teams' games, scores once final."""
    from tests.test_enh11_strengths import route_program

    route_program(fake_cfbd)
    data = client.get("/api/program/next").json()["data"]
    m = data["margins"]
    assert m["us"] and all({"gameId", "week", "homeAway", "result", "usPoints", "themPoints", "opponent"} <= set(row) for row in m["us"])
    assert all((row["result"] is None) == (row["usPoints"] is None) for row in m["us"]), "scores only once final"
    assert isinstance(m["them"], list)


def test_margin_rows_skip_damage_and_repeats():
    from app.cfbd.models import Game
    from app.services.depth2 import margin_rows

    g = lambda gid, week, home, away, hp, ap, done=True: Game.model_validate({"id": gid, "week": week, "homeTeam": home, "awayTeam": away, "homePoints": hp, "awayPoints": ap, "completed": done})  # noqa: E731
    games = [g(1, 1, "Georgia", "Tennessee State", 63, 3), g(1, 1, "Georgia", "Tennessee State", 63, 3), g(2, 2, "Alabama", "Georgia", 17, 20), g(3, 3, "Georgia", "Auburn", None, 9), "junk", None]
    rows = margin_rows(games, "Georgia", {"Alabama": {"abbreviation": "ALA", "color": "#9e1b32"}})
    assert [r["gameId"] for r in rows] == [1, 2, 3], "one row a game"
    assert rows[1] == {**rows[1], "homeAway": "away", "result": "W", "usPoints": 20, "themPoints": 17}
    assert rows[1]["opponent"] == {"school": "Alabama", "abbreviation": "ALA", "color": "#9e1b32", "altColor": None}
    assert rows[2]["result"] is None and rows[2]["usPoints"] is None, "a missing score is no final"
    assert margin_rows(games, None, {}) == []


@needs_node
@pytest.mark.parametrize("scenario", ["strip", "program"])
def test_the_margin_strip_in_a_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS + scenarios_program, scenario)


def test_the_schedule_band_carries_the_strip() -> None:
    season = (ROOT / "static" / "js" / "views" / "season.js").read_text(encoding="utf-8")
    assert 'recordLine({ ...record, team }), marginStrip({ games, nextGameId: data.nextGameId ?? null, team: picked ? team : null }), scheduleList({' in season, "between the record and the games, as drawn"
