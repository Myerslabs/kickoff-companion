"""Pick a game on In Game (owner 2026-11-02: "I want the in game to stay the same, I just want to be able to see it for any
team"): the ticker's mode on the query, the rows ordered and filtered, the side a game is followed from, the sheet's tap
sending the follow, a guest's read-only list, and the week-long window of ui/follow.js (tests/test_other_team_js.py)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.services.ticker import TickerService
from tests.conftest import FakeCfbd
from tests.fakedom import needs_node, run_scenario
from tests.test_national import route_all


def test_the_query_overrides_the_ticker_setting_for_one_answer():
    service = TickerService.__new__(TickerService)
    service.prefs = SimpleNamespace(prefs=SimpleNamespace(tickerMode="mine"))
    service.settings = SimpleNamespace(team="Florida")
    service.client = SimpleNamespace(capabilities=SimpleNamespace(tier_level=2))  # My teams needs a Tier 2 key (2.0)
    calls = []

    class Current:
        def __init__(self, *args):
            calls.append(args)

        def mine(self):
            return frozenset({"Florida"})

    import app.services.ticker as module

    saved = module.teamset.current
    module.teamset.current = lambda *args: Current(*args)
    try:
        assert service._mode([], "national")[:2] == ("national", "national")
        assert service._mode([], "mine")[:2] == ("mine", "mine")
        assert service._mode([], "junk")[:2] == ("mine", "mine"), "a mode that is neither falls back to the setting"
        assert service._mode([], None)[:2] == ("mine", "mine")
        service.client = SimpleNamespace(capabilities=SimpleNamespace(tier_level=0))
        assert service._mode([], "mine")[:2] == ("national", "mine"), "a free key's ticker shows every game and says why"
    finally:
        module.teamset.current = saved


def test_the_route_takes_the_mode(client: TestClient, fake_cfbd: FakeCfbd):
    route_all(fake_cfbd)
    national = client.get("/api/ticker?delay=0&mode=national")
    assert national.status_code == 200 and national.json()["data"]["mode"] == "national"
    assert client.get("/api/ticker?mode=" + "x" * 13).status_code == 422, "the query is bounded"


SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object Object\]/;
const text = (node) => (node ? node.textContent : "");

// useTeam() is the harness's: Florida as us

const SLATE = [
  { gameId: 3, status: "final", detail: "Final", kickoff: "2026-11-07T16:00:00Z", isUs: false, home: { school: "Toledo", abbreviation: "TOL", points: 31 }, away: { school: "Ohio", abbreviation: "OHIO", points: 20 } },
  { gameId: 2, status: "pre", detail: "Sat 7:30 PM", kickoff: "2026-11-08T00:30:00Z", isUs: false, home: { school: "Ole Miss", abbreviation: "MISS", rank: 12 }, away: { school: "Georgia", abbreviation: "UGA", rank: 2 } },
  { gameId: 1, status: "live", detail: "Q3 4:12", kickoff: "2026-11-07T20:30:00Z", isUs: false, home: { school: "LSU", abbreviation: "LSU", rank: 15, points: 14 }, away: { school: "Alabama", abbreviation: "ALA", rank: 9, points: 17 } },
  { gameId: 4, status: "pre", detail: "Sat 7:45 PM", kickoff: "2026-11-08T00:45:00Z", isUs: true, home: { school: "Florida", abbreviation: "FLA", rank: 25 }, away: { school: "Oklahoma", abbreviation: "OU" } },
  { gameId: 5, status: "pre", kickoff: null, home: { school: "Texas", abbreviation: "TEX" }, away: { school: null } },
  { gameId: "x", status: "pre", home: { school: "A" }, away: { school: "B" } },
  null, "junk", 7,
];

scenarios.rows = async () => {
  await useTeam();
  const { pickRows, sideOf, pickRow } = await import(moduleUrl("ui/pick-game.js"));
  const rows = pickRows(SLATE);
  assert.deepEqual(rows.map((r) => r.gameId), [4, 1, 2, "x", 3], "ours first, then live, then to come by kickoff (the unscheduled after), the finals last; a game with one side out");
  assert.ok(rows[0].isUs === true);
  assert.deepEqual(pickRows(SLATE, { query: "geo" }).map((r) => r.gameId), [2], "a search by the school's words");
  assert.deepEqual(pickRows(SLATE, { query: "ala" }).map((r) => r.gameId), [1], "or its abbreviation");
  assert.deepEqual(pickRows("junk"), []);
  assert.equal(sideOf(SLATE[3]), "Florida", "ours when we play");
  assert.equal(sideOf(SLATE[2]), "LSU", "else the home side");
  assert.equal(sideOf({}), null);
  const li = pickRow(SLATE[2], { onPick: () => {} });
  assert.ok(li.querySelector("button") && text(li).includes("Q3 4:12") && text(li).includes("#9 Alabama 17") && text(li).includes("#15 LSU 14"), text(li));
  assert.ok(!pickRow(SLATE[2], { guest: true }).querySelector("button"), "a guest's row is plain");
  assert.ok(!pickRow(SLATE[5], {}).querySelector("button"), "no id, no tap");
  assert.ok(!RAW.test(text(pickRow({}, {}))) && !RAW.test(text(pickRow(SLATE[4], {}))));
};

scenarios.sheet = async () => {
  installWindow();
  await useTeam();
  const { pickGameSheet } = await import(moduleUrl("ui/pick-game.js"));
  route("/api/ticker", () => envelope({ mode: "national", games: SLATE }));
  let sent = null;
  route("/api/live/follow", () => envelope({ followed: { gameId: 1, team: "LSU" } }));
  const plainFetch = globalThis.fetch; // the harness's fetch takes the url alone: the request's body is read here
  globalThis.fetch = async (url, init) => { if (String(url).startsWith("/api/live/follow")) sent = init; return plainFetch(url, init); };
  const handle = pickGameSheet({ guest: false });
  await settle();
  const layer = document.querySelector(".sheet-layer");
  assert.ok(layer && layer.getAttribute("aria-label") === "Pick a game");
  const list = layer.querySelector(".pick-game__list");
  assert.equal(list.querySelectorAll("li.pick-game__row").length, 5);
  assert.ok(list.querySelector("li.is-us"), "ours marked");
  const search = layer.querySelector(".pick-game__search");
  search.value = "lsu";
  search.dispatchEvent({ type: "input" }); // the fake DOM takes a plain event; the handler reads the box
  await settle();
  assert.equal(list.querySelectorAll("li.pick-game__row").length, 1);
  list.querySelector("button").click();
  await settle();
  assert.ok(sent && sent.method === "POST", "the follow sent");
  assert.deepEqual(JSON.parse(sent.body), { gameId: 1, team: "LSU" });
  assert.ok(text(layer).includes("Watching Alabama at LSU."), text(layer).slice(-200));
  assert.ok(!RAW.test(text(layer)));
  // a game the engine drops (over, or gone from the season): the words say so and the list stays open
  route("/api/live/follow", () => envelope({ followed: null }));
  search.value = "toledo";
  search.dispatchEvent({ type: "input" });
  await settle();
  list.querySelector("button").click();
  await settle();
  assert.ok(text(layer).includes("Ohio at Toledo is over or gone; In Game stays on our game."), text(layer).slice(-200));
  assert.ok(!list.querySelector("button").disabled, "the list is open again");
  globalThis.fetch = plainFetch;
  handle.close();
};

scenarios.guest = async () => {
  installWindow();
  await useTeam();
  const { pickGameSheet } = await import(moduleUrl("ui/pick-game.js"));
  route("/api/ticker", () => envelope({ mode: "national", games: SLATE }));
  const handle = pickGameSheet({ guest: true });
  await settle();
  const layer = document.querySelector(".sheet-layer");
  assert.equal(layer.querySelectorAll(".pick-game__list button").length, 0, "a guest reads the list");
  assert.ok(text(layer).includes("The host picks the game"));
  handle.close();
};

scenarios.failed = async () => {
  installWindow();
  await useTeam();
  const { pickGameSheet } = await import(moduleUrl("ui/pick-game.js"));
  route("/api/ticker", () => ({ status: 503, body: { errors: [{ message: "CFBD is down" }] } }));
  const handle = pickGameSheet({ guest: false });
  await settle();
  const layer = document.querySelector(".sheet-layer");
  assert.ok(text(layer).includes("did not load: CFBD is down") && layer.querySelector("button"), text(layer));
  handle.close();
};

scenarios.tools = async () => {
  const { stageTools } = await import(moduleUrl("ui/stage.js"));
  let picked = 0;
  const nodes = stageTools({ delayLabel: "Delay 30 s", onPick: () => { picked += 1; } });
  assert.deepEqual(nodes.map(text), ["Delay 30 s", "Pick a game", "Radio", "Notes", "Invite", "Big screen"]);
  nodes[1].click();
  assert.equal(picked, 1);
};
"""


@needs_node
@pytest.mark.parametrize("scenario", ["rows", "sheet", "guest", "failed", "tools"])
def test_pick_a_game_in_the_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)
