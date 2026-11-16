"""FEAT-2, Picks of the week (owner 2026-10-25: under National, named with the paper's weekly name, Power and Group of 5, four
timeslots once game and broadcast information exists; 2026-10-30: "Claude picks", the line beside): the windows, the
groups, the pick marked once final, the record, the paper's picks until Claude's, the run's packet and slot, the page."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.cfbd.models import BettingGame, Game, GameMedia
from app.services.claude_schedule import week_slots
from app.services.picks import is_power, packet_games, pick_right, picks_week, slot_of
from app.services.writing import WritingStore, build_prompt, read
from tests.fakedom import needs_node, run_scenario

ET = ZoneInfo("America/New_York")


def test_the_windows_and_the_groups():
    at = lambda h, m=0: datetime(2026, 10, 31, h, m, tzinfo=ET)  # noqa: E731
    assert [slot_of(at(12)), slot_of(at(13, 59)), slot_of(at(15, 30)), slot_of(at(19, 30)), slot_of(at(22))] == ["early", "early", "afternoon", "prime", "late"]
    assert slot_of(None) is None
    assert is_power("SEC", "Big Sky") and is_power(None, "FBS Independents") and is_power("Pac-12", "Mountain West")
    assert not is_power("Mid-American", "Sun Belt"), "the rest are the Group of 5"
    assert is_power(None, None, "Florida", "Campbell", {"Florida": "SEC"}), "a blank conference read from CFBD's team list"


def test_a_pick_right_or_wrong_once_final():
    row = {"final": True, "home": {"school": "Georgia", "points": 24}, "away": {"school": "Florida", "points": 27}}
    assert pick_right("Florida", row) is True and pick_right("Georgia", row) is False
    assert pick_right("Florida", {**row, "final": False}) is None, "not before the final"
    assert pick_right("Texas", row) is None, "a pick of neither school counts nothing"
    assert pick_right("Florida", {**row, "home": {"school": "Georgia", "points": 27}}) is None, "a tie"
    assert pick_right(None, row) is None


def _state(tmp_path: Path, games: list[dict], lines: list[dict] | None = None, media: list[dict] | None = None):
    part = lambda records, ok=True: SimpleNamespace(records=records, ok=ok)  # noqa: E731
    teams = {"Florida": {"abbreviation": "FLA", "conference": "SEC", "color": "#0021a5"}, "Georgia": {"abbreviation": "UGA", "conference": "SEC", "color": "#ba0c2f"},
             "Toledo": {"abbreviation": "TOL", "conference": "Mid-American"}, "Ohio": {"abbreviation": "OHIO", "conference": "Mid-American"}}
    fetched = {
        "weekGames": part([Game.model_validate(g) for g in games]),
        "weekLines": part([BettingGame.model_validate(b) for b in lines or []]),
        "weekMedia": part([GameMedia.model_validate(m) for m in media or []]),
    }

    async def f(name, endpoint, params, model, kind):
        assert params["week"] == 10
        return fetched[name]

    async def slot():
        return (10, "regular"), {"teams": part([]), "rankings": part([])}

    program = SimpleNamespace(_f=f, _teams=lambda p: teams, _abbreviations=lambda t: {k: v["abbreviation"] for k, v in t.items()})
    settings = SimpleNamespace(season=2026, data_dir=tmp_path, team="Florida", tzinfo=ET)
    return SimpleNamespace(program=program, rankedweek=SimpleNamespace(_slot=slot), settings=settings)


GAMES = [
    {"id": 1, "week": 10, "startDate": "2026-10-31T19:30:00.000Z", "homeTeam": "Georgia", "awayTeam": "Florida", "homeConference": "SEC", "awayConference": "SEC", "neutralSite": True, "completed": True, "homePoints": 24, "awayPoints": 27},
    {"id": 2, "week": 10, "startDate": "2026-11-01T00:00:00.000Z", "homeTeam": "Toledo", "awayTeam": "Ohio", "homeConference": "Mid-American", "awayConference": "Mid-American"},
    {"id": 3, "week": 10, "startDate": "2026-10-31T16:00:00.000Z", "startTimeTBD": True, "homeTeam": "Florida", "awayTeam": "Campbell", "homeConference": "SEC", "awayConference": "CAA"},
    {"id": 4, "week": 10, "startDate": "2026-10-31T16:00:00.000Z", "homeTeam": "Montana", "awayTeam": "Idaho"},  # no FBS team: left out
]


def test_the_week_in_its_windows_with_the_picks(tmp_path: Path):
    state = _state(tmp_path, GAMES, lines=[{"id": 1, "homeTeam": "Georgia", "awayTeam": "Florida", "lines": [{"provider": "Book", "spread": -7.5, "formattedSpread": "Georgia -7.5"}]}], media=[{"id": 1, "mediaType": "tv", "outlet": "ABC"}])
    store = WritingStore(tmp_path, 2026)
    store.save("paper", "week-10", {"picks": [{"gameId": 1, "pick": "Georgia", "reason": "Home field."}]})
    got = asyncio.run(picks_week(state))
    assert got["key"] == "week-10" and got["label"] == "Week 10"
    assert [s["id"] for s in got["slots"]] == ["afternoon", "prime"], "3:30 PM and 8 PM Eastern"
    assert got["counts"] == {"power": 2, "g5": 1}, "the FCS-only game left out"
    first = got["slots"][0]["games"][0]
    assert first["power"] is True and first["tv"] == "ABC" and first["line"]["formatted"] == "Georgia -7.5" and first["isUs"] is True
    assert got["picksBy"] == "paper" and first["pick"] == "Georgia" and first["right"] is False, "the paper's picks until Claude's"
    assert got["record"]["power"] == {"right": 0, "wrong": 1}
    assert [g["gameId"] for g in got["unscheduled"]] == [3], "a time to be set waits outside the windows"
    store.save("picks", "week-10", {"picks": [{"gameId": 1, "pick": "Florida", "reason": "The defense."}, {"gameId": 2, "pick": "Toledo"}, {"gameId": "x", "pick": "Ohio"}]})
    got = asyncio.run(picks_week(state))
    assert got["picksBy"] == "claude" and got["record"]["power"] == {"right": 1, "wrong": 0}
    assert got["slots"][1]["games"][0]["pick"] == "Toledo" and got["slots"][1]["games"][0]["power"] is False
    packet = packet_games(got)
    assert [g["gameId"] for g in packet] == [2, 3], "the run sees the games still to play"
    assert packet[0]["home"] == "Toledo" and "line" in packet[0]


def test_no_games_says_so(tmp_path: Path):
    got = asyncio.run(picks_week(_state(tmp_path, [])))
    assert got["slots"] == [] and got["ready"] is False and "No games" in got["note"]


def test_the_picks_answer_prompt_and_slot():
    answer, _warnings, error = read("picks", '{"picks": [{"gameId": 1, "pick": "Florida", "reason": "Defense."}, {"gameId": "x"}]}')
    assert error is None and answer["picks"] == [{"gameId": 1, "pick": "Florida", "reason": "Defense."}]
    prompt = build_prompt("picks", "Florida", {"games": [{"gameId": 1}]})
    assert "Pick the winner of every game" in prompt and "no betting odds or moneylines" in prompt
    kickoff = datetime(2026, 10, 31, 19, 30, tzinfo=timezone.utc)
    slots = {s.key: s for s in week_slots(401, kickoff, ET, 10)}
    assert "picks:week-10" in slots and slots["picks:week-10"].writing_key == "week-10" and slots["picks:week-10"].at.astimezone(ET).hour == 14
    assert slots["picks:week-10"].at > slots["paper:week-10"].at, "after the paper"


def test_the_picks_route(app, client: TestClient, monkeypatch: pytest.MonkeyPatch):
    import app.api.picks as routes

    async def fake(state):
        return {"week": 10, "key": "week-10", "slots": [], "writtenAt": None}

    monkeypatch.setattr(routes, "picks_week", fake)
    data = client.get("/api/picks").json()["data"]
    assert data["key"] == "week-10" and data["running"] is False and "commandFound" in data

    async def broken(state):
        raise RuntimeError("boom")

    monkeypatch.setattr(routes, "picks_week", broken)
    assert client.get("/api/picks").status_code == 502


SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object \w+\]/;
const text = (node) => (node ? node.textContent : "");

const WEEK = {
  season: 2026, week: 10, key: "week-10", label: "Week 10", ready: true, picksBy: "claude", writtenAt: "2026-10-29T18:14:00Z", running: false, commandFound: true,
  counts: { power: 2, g5: 1 }, record: { power: { right: 1, wrong: 0 }, g5: { right: 0, wrong: 0 } },
  slots: [
    { id: "afternoon", name: "Afternoon", hours: "2 to 6 PM", games: [
      { gameId: 1, kickoff: "2026-10-31T19:30:00Z", tv: "ABC", power: true, neutralSite: true, isUs: true, final: true, home: { school: "Georgia", abbreviation: "UGA", rank: 3, points: 24 }, away: { school: "Florida", abbreviation: "FLA", rank: 17, points: 27 }, line: { short: "UGA -7.5" }, pick: "Florida", reason: "The defense travels.", right: true },
      { gameId: 5, kickoff: "2026-10-31T20:00:00Z", tv: null, power: true, final: false, home: { school: "Texas" }, away: { school: "Campbell", fbs: false }, line: null, pick: null, reason: null, right: null },
    ] },
    { id: "prime", name: "Prime time", hours: "6 to 9 PM", games: [
      { gameId: 2, kickoff: "2026-11-01T00:00:00Z", tv: "ESPNU", power: false, final: false, home: { school: "Toledo", abbreviation: "TOL" }, away: { school: "Ohio", abbreviation: "OHIO" }, line: { formatted: "Toledo -3" }, pick: "Toledo", reason: "At home.", right: null },
    ] },
  ],
  unscheduled: [],
};

scenarios.page = async () => {
  installWindow();
  await useTeam();
  const { createPicksView, gameRow } = await import(moduleUrl("views/picks.js"));
  const { clearEnvelopeCache } = await import(moduleUrl("views/common.js"));
  clearEnvelopeCache();
  let current = JSON.parse(JSON.stringify(WEEK));
  route("/api/picks", () => envelope(current));
  const main = document.createElement("main");
  document.body.append(main);
  const view = createPicksView({});
  view.mount(main);
  await settle();
  const t = text(main);
  assert.ok(/Picks of the week/.test(main.querySelector(".picks-head__title").textContent), "named with the paper's weekly name");
  assert.ok(t.includes("Record this week: Power 1-0"), t.slice(0, 400));
  assert.ok(t.includes("Picked by Claude Code"), "who picked");
  assert.ok(main.querySelector("#picks-afternoon") && !main.querySelector("#picks-prime"), "Power first: the Group of 5 game waits for its switch");
  assert.equal(main.querySelectorAll("#picks-afternoon li.picks__row").length, 2);
  const ours = main.querySelector("li.picks__row.is-us");
  assert.ok(ours && text(ours).includes("FLA") && text(ours).includes("Right") && text(ours).includes("UGA -7.5") && text(ours).includes(" vs "), text(ours));
  assert.ok(text(main).includes("No pick yet") && text(main).includes("TV to be set") && text(main).includes("None yet"));
  assert.equal(main.querySelector("#picks-run"), null, "Claude has picked: no run band");
  const g5 = main.querySelectorAll(".picks__scope button").find((b) => text(b).startsWith("Group of 5"));
  g5.click();
  await settle();
  assert.ok(main.querySelector("#picks-prime") && !main.querySelector("#picks-afternoon"), "the Group of 5 games alone");
  assert.ok(text(main).includes("Toledo -3"));
  assert.ok(!RAW.test(text(main)), text(main));
  view.unmount();
  // before Claude's run: the paper's picks, and the host's Pick every game now
  current = { ...JSON.parse(JSON.stringify(WEEK)), picksBy: "paper" };
  clearEnvelopeCache();
  const again = document.createElement("main");
  document.body.append(again);
  const v2 = createPicksView({});
  v2.mount(again);
  await settle();
  const run = again.querySelector("#picks-run");
  assert.ok(run && run.querySelectorAll("button").some((b) => text(b) === "Pick every game now"), text(run));
  assert.ok(text(again).includes("The paper's picks"));
  v2.unmount();
  const row = gameRow({});
  assert.ok(!RAW.test(text(row)), text(row));
};
"""


@needs_node
def test_the_picks_page_in_a_fake_browser(tmp_path: Path) -> None:
    run_scenario(tmp_path, SCENARIOS, "page")
