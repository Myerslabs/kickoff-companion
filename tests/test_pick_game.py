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


def test_the_ticker_is_every_game_whatever_is_asked():
    """Batch 3 (owner 2026-11-19), one team: the My teams ticker is gone; an old setting or query gets every game."""
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
        for asked in ("national", "mine", "junk", None):
            assert service._mode([], asked)[:2] == ("national", "national"), asked
        assert service._mode([], None)[3] == frozenset({"Florida"}), "our games are still marked"
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
  // batch 3 (owner 2026-11-16: "Stays on host's game, each client can view another game"): a row's tap watches the game on
  // this screen alone, a guest's too; the host's Every screen moves the room
  const guestRow = pickRow(SLATE[2], { guest: true, onPick: () => {}, onEveryone: () => {} });
  assert.ok(guestRow.querySelector("button.pick-game__btn") && !guestRow.querySelector(".pick-game__all"), "a guest watches here, never moves every screen");
  assert.ok(pickRow(SLATE[2], { onPick: () => {}, onEveryone: () => {} }).querySelector("button.pick-game__all"), "the host's Every screen");
  assert.ok(!pickRow(SLATE[2], { onPick: () => {} }).querySelector(".pick-game__all"), "no Every screen without its handler");
  assert.ok(!pickRow(SLATE[5], {}).querySelector("button"), "no id, no tap");
  assert.ok(!RAW.test(text(pickRow({}, {}))) && !RAW.test(text(pickRow(SLATE[4], {}))));
};

scenarios.sheet = async () => {
  installWindow();
  await useTeam();
  const { pickGameSheet } = await import(moduleUrl("ui/pick-game.js"));
  const { deviceGame, _resetDeviceGame } = await import(moduleUrl("watching.js"));
  _resetDeviceGame();
  route("/api/ticker", () => envelope({ mode: "national", games: SLATE }));
  let sent = null;
  route("/api/live/follow", () => envelope({ followed: { gameId: 1, team: "LSU" } }));
  const plainFetch = globalThis.fetch; // the harness's fetch takes the url alone: the request's body is read here
  globalThis.fetch = async (url, init) => { if (String(url).startsWith("/api/live/follow")) sent = init; return plainFetch(url, init); };
  const open = async () => {
    const handle = pickGameSheet({ guest: false });
    await settle();
    const layer = document.querySelector(".sheet-layer");
    return { handle, layer, list: layer.querySelector(".pick-game__list"), search: layer.querySelector(".pick-game__search") };
  };
  const find = async (box, words) => {
    box.value = words;
    box.dispatchEvent({ type: "input" }); // the fake DOM takes a plain event; the handler reads the box
    await settle();
  };
  let { handle, layer, list, search } = await open();
  assert.ok(layer && layer.getAttribute("aria-label") === "Pick a game");
  assert.equal(list.querySelectorAll("li.pick-game__row").length, 5);
  assert.ok(list.querySelector("li.is-us"), "ours marked");
  assert.ok(text(layer).includes("this screen only"), "the words say a tap is this screen's");
  // the host's Every screen: the room follows it (the engine's follow), this screen with it
  await find(search, "lsu");
  assert.equal(list.querySelectorAll("li.pick-game__row").length, 1);
  list.querySelector("button.pick-game__all").click();
  await settle();
  assert.ok(sent && sent.method === "POST", "the follow sent");
  assert.deepEqual(JSON.parse(sent.body), { gameId: 1, team: "LSU" });
  assert.ok(text(layer).includes("Watching Alabama at LSU."), text(layer).slice(-200));
  assert.ok(!RAW.test(text(layer)));
  assert.equal(deviceGame(), null, "every screen: this one follows the room");
  // a game the engine drops (over, or gone from the season): the words say so and the list stays open
  route("/api/live/follow", () => envelope({ followed: null }));
  await find(search, "toledo");
  list.querySelector("button.pick-game__all").click();
  await settle();
  assert.ok(text(layer).includes("Ohio at Toledo is over or gone; In Game stays on our game."), text(layer).slice(-200));
  assert.ok(!list.querySelector("button").disabled, "the list is open again");
  handle.close();
  // a row's own tap: this screen alone, nothing sent to the engine, In Game opened on it
  sent = null;
  ({ handle, layer, list, search } = await open());
  await find(search, "lsu");
  list.querySelector("button.pick-game__btn").click();
  await settle();
  assert.equal(sent, null, "the room stays on its game");
  assert.equal(deviceGame()?.gameId, 1, "this screen watches it");
  assert.equal(window.location.hash, "live");
  // our own game's row watches it here too (the review, 2026-11-19: after the host moved every screen elsewhere, our game
  // is not the room's; when it is, the server answers the room's state for it)
  ({ handle, layer, list, search } = await open());
  assert.ok(list.querySelector("li.is-here"), "the game this screen watches, marked");
  list.querySelector("li.is-us button.pick-game__btn").click();
  await settle();
  assert.equal(sent, null, "nothing sent to the engine");
  assert.equal(deviceGame()?.gameId, 4, "our game, watched here");
  assert.equal(deviceGame()?.team, "Florida", "from our side");
  // Every screen moves this one only once the room has moved: a failed follow leaves this screen's game as it was
  ({ handle, layer, list, search } = await open());
  route("/api/live/follow", () => ({ status: 503, body: { errors: [{ message: "busy" }] } }));
  await find(search, "lsu");
  list.querySelector("button.pick-game__all").click();
  await settle();
  assert.ok(text(layer).includes("Not switched: busy."), text(layer).slice(-200));
  assert.equal(deviceGame()?.gameId, 4, "the follow failed: this screen keeps its game");
  route("/api/live/follow", () => envelope({ followed: { gameId: 1, team: "LSU" } }));
  list.querySelector("button.pick-game__all").click();
  await settle();
  assert.equal(deviceGame(), null, "the room moved: this screen follows it");
  globalThis.fetch = plainFetch;
  handle.close?.();
};

scenarios.aging = async () => {
  // the review (2026-11-19): a game picked more than a day ago (or with no time) is dropped on load
  const kept = new Map();
  globalThis.sessionStorage = { getItem: (k) => (kept.has(k) ? kept.get(k) : null), setItem: (k, v) => kept.set(k, String(v)), removeItem: (k) => kept.delete(k) };
  const { deviceGame, watchHere, _resetDeviceGame } = await import(moduleUrl("watching.js"));
  _resetDeviceGame();
  watchHere({ gameId: 7, home: "LSU", away: "Alabama" });
  const saved = JSON.parse(kept.get("kickoff:watch"));
  assert.ok(Number.isFinite(saved.at) && Math.abs(saved.at - Date.now()) < 5000, "the time it was picked is kept");
  _resetDeviceGame({ reload: true });
  assert.equal(deviceGame()?.gameId, 7, "picked just now: still this screen's");
  kept.set("kickoff:watch", JSON.stringify({ ...saved, at: Date.now() - 25 * 3600 * 1000 }));
  _resetDeviceGame({ reload: true });
  assert.equal(deviceGame(), null, "a day old: the room's game again");
  assert.ok(!kept.has("kickoff:watch"), "and forgotten");
  kept.set("kickoff:watch", JSON.stringify({ gameId: 7, home: "LSU" }));
  _resetDeviceGame({ reload: true });
  assert.equal(deviceGame(), null, "no time: dropped");
  _resetDeviceGame();
  delete globalThis.sessionStorage;
};

scenarios.guest = async () => {
  installWindow();
  await useTeam();
  const { pickGameSheet } = await import(moduleUrl("ui/pick-game.js"));
  route("/api/ticker", () => envelope({ mode: "national", games: SLATE }));
  const handle = pickGameSheet({ guest: true });
  await settle();
  const layer = document.querySelector(".sheet-layer");
  assert.ok(layer.querySelectorAll(".pick-game__list button.pick-game__btn").length > 0, "a guest picks a game for this screen too");
  assert.equal(layer.querySelectorAll(".pick-game__all").length, 0, "never Every screen");
  assert.ok(text(layer).includes("A tap watches that game on this screen only"), text(layer));
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
@pytest.mark.parametrize("scenario", ["rows", "sheet", "guest", "failed", "tools", "aging"])
def test_pick_a_game_in_the_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)
