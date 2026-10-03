"""Phase 10a, the Saturday rehearsal without a Saturday. The real Tier 2 live document of the
finished last game of the demo team is cut into in-progress snapshots and served one per poll to the real engine
on a fake clock: the window opens, the feed goes from waiting to ok, fails and recovers, halftime
slows the poll, the two in-game win probability probes go out, the final closes the window and
writes the archive, and every raw answer lands in the recording with its manifest. Then the
failure paths, the long game past five hours, the close without a final, the live-view window,
the settle time handed to the client, the stream's ping, and the ticker's scoreboard recording."""

from __future__ import annotations

import asyncio
import copy
import json
import logging
import re
import sqlite3
from collections import Counter
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

import app.api.live as live_api
from app.cfbd.models import LiveGame, parse_one
from app.live.engine import WINDOW_AFTER, WINDOW_CAP, GameWindow, LiveEngine
from app.live.events import LiveEvent, events_from_live
from app.live.state import derive_state
from tests.conftest import FakeCfbd, fixture_payload
from tests.league_facts import last_game, live_counts, next_game_row, wp_points

LAST = last_game()  # our last game: the one replayed here
GAME = LAST["id"]
KICKOFF = datetime.fromisoformat(LAST["startDate"].replace("Z", "+00:00"))
HOME, AWAY, WEEK = LAST["homeTeam"], LAST["awayTeam"], LAST["week"]
FINAL_SCORE = (LAST["homePoints"], LAST["awayPoints"])
PLAY_COUNT, DRIVE_COUNT = live_counts()
NEXT = next_game_row()  # the game after it, which the engine turns to once this one is done
NEXT_GAME = NEXT["id"]
NEXT_KICKOFF = datetime.fromisoformat(NEXT["startDate"].replace("Z", "+00:00"))
FULL = fixture_payload("live_plays")
PLAYS = [play for drive in FULL["drives"] for play in drive["plays"]]
HALFTIME_CUT = 1 + max(i for i, play in enumerate(PLAYS) if play["period"] == 2)  # through the second quarter's "End Period" at 0:00
# Every eighth play plus halftime. The cuts avoid play 46, where CFBD's own play scores dip for one
# play (a false start on the extra point, 14 then 13 then 14); a real document's team points come
# from CFBD's team block, not from a play.
CUTS = sorted(set(range(8, len(PLAYS), 8)) | {HALFTIME_CUT})
IN_PROGRESS = ("in progress", "In Progress")  # CFBD's exact in-game string is unknown until Saturday
FAIL = ("http", 500)
FEED_KEYS = {"state", "lastSuccessAt", "lastNewEventAt", "consecutiveFailures", "lastError", "staleSeconds", "checkedAt"}
RECORD_NAME = re.compile(r"^(?P<kind>[a-z]+(?:-[a-z]+)?)-\d{8}T\d{9}Z(?:-\d+)?\.json$")


# --- the scripted upstream -------------------------------------------------------------------------------------


def line_scores(plays: list[dict[str, Any]], side: str, periods: int) -> list[int]:
    """Points per quarter up to the current one, from the play scores."""
    ends: dict[int, int] = {}
    for play in plays:
        if isinstance(play.get(side), int):
            ends[play["period"]] = play[side]
    out: list[int] = []
    before = 0
    for period in range(1, periods + 1):
        total = ends.get(period, before)
        out.append(total - before)
        before = total
    return out


def snapshot(count: int, status: str) -> dict[str, Any]:
    """The live document as it would have looked after `count` plays: drives and plays truncated,
    the drive in progress without a result, the status line from the last play."""
    doc = copy.deepcopy(FULL)
    drives: list[dict[str, Any]] = []
    taken: list[dict[str, Any]] = []
    for drive in doc["drives"]:
        if len(taken) >= count:
            break
        plays = drive["plays"][: count - len(taken)]
        if len(plays) < len(drive["plays"]):
            drive.update(plays=plays, playCount=len(plays), result=None, pointsGained=0, endPeriod=None, endClock=None, endYardsToGoal=plays[-1]["yardsToGoal"], duration=None, yards=sum(p.get("yardsGained") or 0 for p in plays))
        drives.append(drive)
        taken.extend(plays)
    last = taken[-1]
    doc.update(drives=drives, status=status, period=last["period"], clock=last["clock"], possession=last["team"], down=last["down"], distance=last["distance"], yardsToGoal=last["yardsToGoal"])
    for team in doc["teams"]:
        side = "homeScore" if team["homeAway"] == "home" else "awayScore"
        team["points"] = last[side]
        team["lineScores"] = line_scores(taken, side, last["period"])
    return doc


def game_snapshots() -> list[dict[str, Any]]:
    """About 25 in-progress snapshots, then the full document (status "Final")."""
    return [snapshot(n, "Halftime" if n == HALFTIME_CUT else IN_PROGRESS[i % 2]) for i, n in enumerate(CUTS)] + [FULL]


def respond(entry: Any) -> httpx.Response:
    if isinstance(entry, tuple) and entry[0] == "http":
        return httpx.Response(entry[1], json={"message": "scripted upstream failure"})
    if isinstance(entry, tuple) and entry[0] == "raw":
        return httpx.Response(200, content=json.dumps(entry[1]).encode(), headers={"content-type": "application/json"})
    return httpx.Response(200, json=entry)


def tier2_info() -> dict[str, Any]:
    info = fixture_payload("info")
    return {**info, "patronLevel": 2, "tierName": "Tier 2", "monthlyLimit": 30000, "remainingCalls": 29000, "features": {**info["features"], "livePlayByPlay": True}}


def upcoming_schedule() -> list[dict[str, Any]]:
    """The recorded schedule with our last game not played yet."""
    return [{**g, "completed": False, "homePoints": None, "awayPoints": None} if g.get("id") == GAME else g for g in fixture_payload("games_team")]


def route_game(fake: FakeCfbd, live_plays: Callable[[httpx.Request], httpx.Response], *, schedule: list[dict[str, Any]] | None = None) -> None:
    """Tier 2 /info, the schedule, the recorded week-3 box scores, and /metrics/wp empty then recorded."""
    fake.route("/info", json=tier2_info())
    rows = schedule if schedule is not None else upcoming_schedule()
    fake.route("/games", handler=lambda r: httpx.Response(200, json=rows))
    fake.fixture("/games/teams", "games_teams")
    fake.fixture("/games/players", "games_players")
    wp_calls = {"n": 0}

    def win_probability(request: httpx.Request) -> httpx.Response:
        wp_calls["n"] += 1
        return httpx.Response(200, json=[] if wp_calls["n"] == 1 else fixture_payload("metrics_wp"))

    fake.route("/metrics/wp", handler=win_probability)
    fake.route("/live/plays", handler=live_plays)


class Saturday:
    """The engine's own loop on a fake clock against a fake CFBD that serves one scripted answer
    per poll. Samples the feed health before each poll and at every sleep, and the released state
    at 0 and 45 seconds after every poll, walking the store the way the stream does."""

    def __init__(self, app, fake: FakeCfbd, script: list[Any] | Callable[[Saturday], Any], *, start: datetime = KICKOFF - timedelta(minutes=31), time_scale: float = 1.0, watch: bool = True, disconnect_at: datetime | None = None, max_sleeps: int = 3000) -> None:
        self.app = app
        self.engine: LiveEngine = app.state.live
        self.cfbd = app.state.cfbd
        self.fake = fake
        self.script = script
        self.clock = {"now": start}
        self.time_scale = time_scale
        self.disconnect_at = disconnect_at
        self.disconnected_at: datetime | None = None
        self.max_sleeps = max_sleeps
        self.sleeps: list[float] = []
        self.feed: list[dict[str, Any]] = []
        self.windows: list[dict[str, Any] | None] = []
        self.states: dict[int, list[dict[str, Any]]] = {0: [], 45: []}
        self.sent_seq: dict[int, list[int]] = {0: [0], 45: [0]}
        self.seq_problems: list[str] = []
        self.poll_log: list[tuple[int, datetime]] = []
        self._poll_seen = 0
        self._opened = False  # the game's window was open at some sleep
        self.queue = self.engine.subscribe() if watch else None
        self.cfbd._clock = lambda: self.clock["now"]
        self.cfbd._sleep = self._no_wait  # the client's own retry backoff: no real waiting in a test
        self.cfbd.capabilities.live_plays = True
        self.engine._sleep = self._sleep
        route_game(fake, self._live_plays)

    @property
    def now(self) -> datetime:
        return self.clock["now"]

    async def _no_wait(self, seconds: float) -> None:
        return None

    def entry(self, poll: int) -> Any:
        if callable(self.script):
            return self.script(self)
        return self.script[min(poll, len(self.script)) - 1]

    def _live_plays(self, request: httpx.Request) -> httpx.Response:
        poll = self.engine.stats.polls
        if poll != self._poll_seen:  # the first attempt of this poll; the client retries a 500 up to three times
            self._poll_seen = poll
            self.poll_log.append((poll, self.now))
            self.feed.append(self.engine.feed_health())
        return respond(self.entry(poll))

    def _sample(self) -> None:
        for delay, states in self.states.items():
            states.append(self.engine.state(delay, GAME))
            sent = self.sent_seq[delay][-1]
            released = self.engine.released_since(GAME, delay, sent)
            if any((e.seq or 0) <= sent for e in released):
                self.seq_problems.append(f"delay {delay}: a seq at or below {sent} was released again")
            if released:
                self.sent_seq[delay].append(max(e.seq or 0 for e in released))

    async def _sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.feed.append(self.engine.feed_health())
        self.windows.append(self.engine.status()["window"])
        if self.engine.mode == "live" and self.engine.current_game_id == GAME:
            self._opened = True
            self._sample()
        if self.finished or len(self.sleeps) > self.max_sleeps:
            raise asyncio.CancelledError
        self.clock["now"] += timedelta(seconds=seconds * self.time_scale)
        if self.disconnect_at is not None and self.queue is not None and self.now >= self.disconnect_at:
            self.engine.unsubscribe(self.queue)
            self.queue = None
            self.disconnected_at = self.now

    @property
    def finished(self) -> bool:
        """The game's window opened and has closed. A window with no play and no final no longer
        retires its game (Phase 11: a moved kickoff may open it again), so a closed window counts."""
        if self.engine.mode != "idle":
            return False
        window = self.engine.window
        return GAME in self.engine._done_games or (self._opened and (window is None or window.game_id != GAME))

    def run(self) -> Saturday:
        async def scenario() -> None:
            with pytest.raises(asyncio.CancelledError):
                await self.engine.run()

        asyncio.run(scenario())
        return self

    # --- what it left behind ---

    @property
    def data_dir(self) -> Path:
        return self.app.state.settings.data_dir

    def archive(self) -> dict[str, Any] | None:
        path = self.data_dir / "archive" / f"{GAME}.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None

    def recordings(self) -> list[tuple[Path, dict[str, Any]]]:
        folder = self.data_dir / "live" / str(GAME)
        return [(p, json.loads(p.read_text(encoding="utf-8"))) for p in sorted(folder.glob("*.json")) if p.name != "manifest.json"]

    def manifest(self) -> dict[str, Any]:
        return json.loads((self.data_dir / "live" / str(GAME) / "manifest.json").read_text(encoding="utf-8"))

    def polls_after(self, when: datetime) -> list[datetime]:
        return [t for _, t in self.poll_log if t > when]


def compress(values: list[Any]) -> list[Any]:
    out: list[Any] = []
    for value in values:
        if not out or out[-1] != value:
            out.append(value)
    return out


def is_subsequence(wanted: list[Any], seen: list[Any]) -> bool:
    it = iter(seen)
    return all(any(v == w for v in it) for w in wanted)


def contains_run(values: list[float], run: list[float]) -> bool:
    return any(values[i : i + len(run)] == run for i in range(len(values) - len(run) + 1))


def full_game_state() -> dict[str, Any]:
    game = parse_one(LiveGame, FULL, context="t")
    return derive_state(events_from_live(game, KICKOFF + timedelta(hours=4)), game_id=GAME, home=HOME, away=AWAY, mode="archive")


# --- the whole game --------------------------------------------------------------------------------------------


def test_a_scripted_game_runs_from_the_window_to_the_archive(app, fake_cfbd: FakeCfbd, caplog):
    caplog.set_level(logging.INFO, logger="kickoff.live")
    snaps = game_snapshots()
    assert 24 <= len(snaps) <= 28 and snaps[-1]["status"] == "Final"
    script = snaps[:4] + [FAIL] * 6 + snaps[4:]
    game = Saturday(app, fake_cfbd, script).run()
    engine = game.engine

    # the final closed the window; the next game is queued
    assert game.finished and (engine.window is None or engine.window.game_id != GAME)
    assert engine.stats.polls == len(script) and engine.stats.consecutive_failures == 0 and engine.stats.poll_failures == 6

    # released states: scores never go down, no play twice, the stream's seq only grows, the delay holds plays back
    for delay, states in game.states.items():
        scores = [(s["homeScore"], s["awayScore"]) for s in states if s["homeScore"] is not None and s["awayScore"] is not None]
        assert scores and all(b[0] >= a[0] and b[1] >= a[1] for a, b in zip(scores, scores[1:])), delay
        for state in states:
            ids = [p["id"] for p in state["plays"]]
            assert len(ids) == len(set(ids))
        seqs = [s["lastSeq"] for s in states]
        assert seqs == sorted(seqs)
        assert game.sent_seq[delay] == sorted(set(game.sent_seq[delay])) and len(game.sent_seq[delay]) > 5
    assert game.seq_problems == []
    assert game.states[0][-1]["counts"]["plays"] == CUTS[-1]  # the last sample is the last in-progress snapshot; the final closes without a sleep
    held_back = [(s0, s45) for s0, s45 in zip(game.states[0], game.states[45]) if s45["counts"]["plays"] < s0["counts"]["plays"]]
    assert len(held_back) > 10 and all(s45["pending"] for _, s45 in held_back)
    for s0, s45 in zip(game.states[0], game.states[45]):
        assert {p["id"] for p in s45["plays"]} <= {p["id"] for p in s0["plays"]}

    # the archive matches the full document
    saved = game.archive()
    expected = full_game_state()
    assert saved is not None and saved["partial"] is False and saved["partialReason"] is None and saved["season"] == 2026
    state = saved["state"]
    assert (state["homeScore"], state["awayScore"]) == (expected["homeScore"], expected["awayScore"]) == FINAL_SCORE
    assert state["status"] == "final" and state["counts"]["plays"] == expected["counts"]["plays"] == PLAY_COUNT and state["counts"]["drives"] == expected["counts"]["drives"] == DRIVE_COUNT
    assert saved["winProbability"] and len(saved["winProbability"]) == wp_points()

    # every answer recorded, named by kind, counted in the manifest with the raw status strings
    recordings = game.recordings()
    kinds = Counter(wrapper["kind"] for _, wrapper in recordings)
    for path, wrapper in recordings:
        match = RECORD_NAME.match(path.name)
        assert match and match["kind"] == wrapper["kind"] and set(wrapper) == {"receivedAt", "kind", "payload"}
    assert kinds["plays"] == len(snaps) and kinds["wp-probe"] == 2 and kinds["wp"] == 1 and kinds["box-teams"] == kinds["box-players"] >= 2
    assert "scoreboard" not in kinds  # the ticker did not run here
    manifest = game.manifest()
    assert manifest["counts"] == dict(kinds) and manifest["gameId"] == GAME and manifest["home"] == HOME and manifest["away"] == AWAY and manifest["week"] == WEEK
    assert manifest["kickoff"] == KICKOFF.isoformat() and manifest["pollSeconds"] == 12 and manifest["firstReceivedAt"] < manifest["lastReceivedAt"]
    assert [s["status"] for s in manifest["statuses"]] == ["in progress", "In Progress", "Halftime", "Final"]
    assert caplog.text.count("reports the status") == 4
    probes = [w for _, w in recordings if w["kind"] == "wp-probe"]
    assert probes[0]["payload"] == [] and len(probes[1]["payload"]) == wp_points()  # halftime got the empty answer, the fourth quarter the full one
    assert fake_cfbd.count("/metrics/wp") == 3

    # the feed: waiting, ok, stale while the fake fails, ok again
    states = compress([f["state"] for f in game.feed])
    assert is_subsequence(["waiting", "ok", "stale", "ok"], states), states
    assert all(set(f) == FEED_KEYS for f in game.feed)
    stale = [f for f in game.feed if f["state"] == "stale"]
    assert stale and all(isinstance(f["staleSeconds"], int) and f["staleSeconds"] > 45 for f in stale) and max(f["consecutiveFailures"] for f in stale) >= 5 and "500" in stale[-1]["lastError"]
    assert all(f["staleSeconds"] is None for f in game.feed if f["state"] != "stale")
    last_stale = max(i for i, f in enumerate(game.feed) if f["state"] == "stale")
    recovered = game.feed[last_stale + 1 :]
    assert recovered and all(f["lastError"] is None and f["consecutiveFailures"] == 0 for f in recovered), [f["state"] for f in recovered]  # a healthy feed shows no old error
    assert compress([f["state"] for f in recovered]) == ["ok", "idle"]  # ok until the final, idle once the window closed

    # the poll: 12 s, the backoff while it fails, 30 s at halftime
    assert contains_run(game.sleeps, [12, 24, 48, 60, 60, 60, 60, 12]), game.sleeps
    assert 30 in game.sleeps

    # the client's settle time came from the window (contract C4)
    assert game.cfbd.settle_until == KICKOFF + timedelta(hours=24)


# --- failure paths ---------------------------------------------------------------------------------------------


def test_three_500s_back_off_24_48_60_and_then_recover(app, fake_cfbd: FakeCfbd):
    snaps = game_snapshots()
    game = Saturday(app, fake_cfbd, snaps[:2] + [FAIL] * 3 + [snaps[2], snaps[-1]]).run()
    assert contains_run(game.sleeps, [12, 24, 48, 60, 12]), game.sleeps
    assert game.engine.stats.poll_failures == 3 and game.engine.stats.consecutive_failures == 0
    assert max(f["consecutiveFailures"] for f in game.feed) == 3
    assert fake_cfbd.count("/live/plays") == 2 + 3 * 2 + 2  # each failed poll is one try and one client retry (live calls make at most 2 attempts)
    saved = game.archive()
    assert saved and saved["partial"] is False and saved["state"]["counts"]["plays"] == PLAY_COUNT


def test_empty_and_null_answers_count_as_failures_and_the_loop_goes_on(app, fake_cfbd: FakeCfbd, caplog):
    snaps = game_snapshots()
    game = Saturday(app, fake_cfbd, snaps[:2] + [("raw", []), ("raw", {}), ("raw", None)] + [snaps[2], snaps[-1]]).run()
    engine = game.engine
    assert engine.stats.poll_failures == 3 and engine.stats.consecutive_failures == 0 and engine.stats.polls == 7
    assert max(f["consecutiveFailures"] for f in game.feed) == 3
    assert any("not a game document" in (f["lastError"] or "") for f in game.feed)
    assert 24 not in game.sleeps  # an answer that is not a game is not a reason to slow down
    assert caplog.text.count("Live poll unusable") == 3
    kinds = Counter(w["kind"] for _, w in game.recordings())
    assert kinds["plays"] == 7  # the junk answers are recorded too
    assert game.archive()["state"]["counts"]["plays"] == PLAY_COUNT


def test_a_box_score_500_does_not_stop_the_play_poll(app, fake_cfbd: FakeCfbd, caplog):
    snaps = game_snapshots()
    game = Saturday(app, fake_cfbd, snaps[:3] + [snaps[-1]])
    fake_cfbd.route("/games/teams", status=500, json={"message": "down"})
    game.run()
    assert game.finished and fake_cfbd.count("/live/plays") == 4 and fake_cfbd.count("/games/teams") >= 4
    kinds = Counter(w["kind"] for _, w in game.recordings())
    assert kinds["box-players"] >= 2 and "box-teams" not in kinds
    saved = game.archive()
    assert saved["state"]["counts"]["plays"] == PLAY_COUNT and saved["state"]["boxScore"] is None and saved["state"]["playerStats"]["Swampwater Tech"]
    assert "Box poll /games/teams failed" in caplog.text


def test_an_exception_inside_publish_is_logged_and_the_loop_goes_on(app, fake_cfbd: FakeCfbd, caplog):
    snaps = game_snapshots()
    game = Saturday(app, fake_cfbd, snaps[:4] + [snaps[-1]])
    store = game.engine.store
    original = store.append
    calls = {"n": 0}

    def flaky_append(events):
        calls["n"] += 1
        if calls["n"] == 3:
            raise sqlite3.OperationalError("database is locked")
        return original(events)

    store.append = flaky_append
    game.run()
    assert calls["n"] > 3 and "Could not store the live events" in caplog.text and "database is locked" in caplog.text
    assert game.finished and game.engine.stats.last_error.startswith("store:")
    saved = game.archive()
    assert saved["partial"] is False and saved["state"]["counts"]["plays"] == PLAY_COUNT and saved["state"]["counts"]["drives"] == DRIVE_COUNT


# --- the long game and the close without a final -------------------------------------------------------------------


MID_GAME = snapshot(100, "In Progress")


def test_the_window_stays_open_past_five_hours_and_closes_at_the_cap_with_a_partial_archive(app, fake_cfbd: FakeCfbd, caplog):
    game = Saturday(app, fake_cfbd, [MID_GAME], time_scale=60, disconnect_at=KICKOFF + timedelta(hours=8)).run()
    assert game.finished
    assert game.polls_after(KICKOFF + WINDOW_AFTER), "polling went on past kickoff plus five hours"
    assert any(w and w["gameId"] == GAME and w["extended"] and w["open"] for w in game.windows)
    assert caplog.text.count("is still in progress") == 1  # warned once, extended many times
    # nobody watching after eight hours: a check every half hour at most that ignores the client gate, then the look at the close
    after = game.polls_after(game.disconnected_at)
    checks, closing = after[:-1], after[-1]
    assert closing >= KICKOFF + WINDOW_CAP and 2 <= len(checks) <= 3 and all(t < KICKOFF + WINDOW_CAP for t in checks)
    assert all(b - a >= timedelta(minutes=30) for a, b in zip(checks, checks[1:])), checks
    saved = game.archive()
    assert saved["partial"] is True and "no final" in saved["partialReason"] and len(saved["partialReason"]) <= 160
    assert saved["state"]["status"] == "in_progress" and saved["winProbability"] is None and saved["season"] == 2026
    assert "closed without a final" in caplog.text


def test_a_final_posted_after_the_last_client_left_is_found_at_the_planned_close(app, fake_cfbd: FakeCfbd, caplog):
    caplog.set_level(logging.INFO, logger="kickoff.live")
    game = Saturday(app, fake_cfbd, lambda g: FULL if g.disconnected_at is not None else MID_GAME, time_scale=60, disconnect_at=KICKOFF + timedelta(hours=2))
    fake_cfbd.fixture("/metrics/wp", "metrics_wp")
    game.run()
    after = game.polls_after(game.disconnected_at)
    # still in progress when the last client left; the look past the planned close ignores the client gate and finds the final
    assert len(after) == 1 and KICKOFF + WINDOW_AFTER < after[0] < KICKOFF + WINDOW_AFTER + timedelta(minutes=30)
    assert "still in progress" not in caplog.text and "closed without a final" not in caplog.text
    saved = game.archive()
    assert saved["partial"] is False and saved["state"]["status"] == "final" and saved["state"]["counts"]["plays"] == PLAY_COUNT and len(saved["winProbability"]) == wp_points()
    assert datetime.fromisoformat(saved["savedAt"]) < KICKOFF + WINDOW_AFTER + timedelta(minutes=30)


def test_a_stretched_window_with_nobody_watching_checks_every_half_hour_until_the_final(app, fake_cfbd: FakeCfbd, caplog):
    final_from = KICKOFF + timedelta(hours=6, minutes=10)
    game = Saturday(app, fake_cfbd, lambda g: FULL if g.now >= final_from else MID_GAME, time_scale=60, disconnect_at=KICKOFF + timedelta(hours=2))
    fake_cfbd.fixture("/metrics/wp", "metrics_wp")
    game.run()
    after = game.polls_after(game.disconnected_at)
    assert 2 <= len(after) <= 4 and after[0] > KICKOFF + WINDOW_AFTER and after[-1] >= final_from and after[-2] < final_from
    assert all(b - a >= timedelta(minutes=30) for a, b in zip(after, after[1:])), after
    assert caplog.text.count("is still in progress") == 1
    saved = game.archive()
    assert saved["partial"] is False and saved["state"]["status"] == "final" and datetime.fromisoformat(saved["savedAt"]) < final_from + timedelta(minutes=30)


def called_off(status: str, *, plays: bool) -> dict[str, Any]:
    """A live document for a game that is not being played: the mid-game snapshot, or no drives at all."""
    if plays:
        return {**copy.deepcopy(MID_GAME), "status": status}
    doc = copy.deepcopy(FULL)
    doc.update(drives=[], status=status, period=None, clock=None, possession=None, down=None, distance=None, yardsToGoal=None)
    for team in doc["teams"]:
        team.update(points=None, lineScores=[])
    return doc


@pytest.mark.parametrize("status", ["Postponed", "In Progress"])
def test_a_feed_with_no_plays_never_stretches_the_window_or_writes_an_archive(app, fake_cfbd: FakeCfbd, caplog, status: str):
    caplog.set_level(logging.INFO, logger="kickoff.live")
    game = Saturday(app, fake_cfbd, [called_off(status, plays=False)], time_scale=60).run()
    assert game.finished and game.poll_log and not game.polls_after(KICKOFF + WINDOW_AFTER)  # no extension, no closing poll
    assert GAME not in game.engine._done_games  # no play and no final: a later real kickoff may open it again
    assert game.archive() is None and "no stored plays" in caplog.text and "still in progress" not in caplog.text
    assert not any(w and w["extended"] for w in game.windows)


@pytest.mark.parametrize("status", ["Postponed", "Canceled", "Cancelled", "Forfeit"])
def test_a_game_called_off_mid_game_closes_on_schedule_with_a_partial_archive(app, fake_cfbd: FakeCfbd, caplog, status: str):
    game = Saturday(app, fake_cfbd, [called_off(status, plays=True)], time_scale=60).run()
    assert game.finished and not any(w and w["extended"] for w in game.windows) and "still in progress" not in caplog.text
    assert len(game.polls_after(KICKOFF + WINDOW_AFTER)) == 1  # only the look at the close
    saved = game.archive()
    assert saved["partial"] is True and status in saved["partialReason"] and saved["state"]["counts"]["plays"] == 100


def test_a_closing_poll_never_replaces_the_complete_archive(app, fake_cfbd: FakeCfbd, caplog):
    caplog.set_level(logging.INFO, logger="kickoff.live")
    route_game(fake_cfbd, lambda r: respond(FAIL))
    engine: LiveEngine = app.state.live
    cfbd = app.state.cfbd
    now = KICKOFF + WINDOW_AFTER + timedelta(minutes=1)
    cfbd._clock = lambda: now

    async def no_wait(seconds: float) -> None:
        return None

    cfbd._sleep = no_wait
    cfbd.capabilities.live_plays = True
    window = GameWindow(GAME, HOME, AWAY, WEEK, KICKOFF, KICKOFF - timedelta(minutes=30), KICKOFF + WINDOW_AFTER)
    engine.window = window
    engine.store.append(events_from_live(parse_one(LiveGame, FULL, context="t"), KICKOFF + timedelta(hours=3)))
    engine.write_archive(window, [{"playId": "1", "homeWinProbability": 0.5}])
    path = app.state.settings.data_dir / "archive" / f"{GAME}.json"
    complete = path.read_text(encoding="utf-8")

    # a restart reopened the window of a game already final: the close makes no call and leaves the archive alone
    asyncio.run(engine._close_window(window))
    assert fake_cfbd.count("/live/plays") == 0 and path.read_text(encoding="utf-8") == complete and "already archived" in caplog.text

    # the stored status is not final, the closing poll fails, and the partial archive still does not replace the complete one
    engine.window = window
    engine.store.append([LiveEvent("status", "status", GAME, KICKOFF + timedelta(hours=4), {"status": "in_progress", "homeScore": 39, "awayScore": 44})])
    asyncio.run(engine._close_window(window))
    assert fake_cfbd.count("/live/plays") >= 1 and path.read_text(encoding="utf-8") == complete and "not written over it" in caplog.text
    saved = json.loads(complete)
    assert saved["partial"] is False and saved["winProbability"] == [{"playId": "1", "homeWinProbability": 0.5}]


def test_a_window_with_no_stored_events_closes_without_a_poll_or_an_archive(app, fake_cfbd: FakeCfbd, caplog):
    game = Saturday(app, fake_cfbd, [MID_GAME], time_scale=60, watch=False).run()
    assert game.finished and fake_cfbd.count("/live/plays") == 0 and game.archive() is None
    assert "no stored plays" in caplog.text and "still in progress" not in caplog.text
    assert not any(w and w["extended"] for w in game.windows)


def test_a_restart_during_a_long_game_finds_the_stretched_window(app, fake_cfbd: FakeCfbd):
    route_game(fake_cfbd, lambda r: respond(MID_GAME))
    engine: LiveEngine = app.state.live
    now = KICKOFF + timedelta(hours=6)
    app.state.cfbd._clock = lambda: now
    assert asyncio.run(engine.find_window()).game_id == NEXT_GAME  # nothing stored: the game's five hours are over
    engine.store.append([LiveEvent("status", "status", GAME, now - timedelta(minutes=1), {"status": "in_progress", "homeScore": 10, "awayScore": 7})])
    assert asyncio.run(engine.find_window()).game_id == NEXT_GAME  # a status without a single play (a postponed game's feed) is not a game on
    engine.store.append([LiveEvent("play:1", "play", GAME, now - timedelta(minutes=1), {"id": "1", "period": 3})])
    window = asyncio.run(engine.find_window())
    assert window.game_id == GAME and window.contains(now) and window.closes_at == now + timedelta(minutes=15)
    later = KICKOFF + WINDOW_CAP + timedelta(minutes=1)
    app.state.cfbd._clock = lambda: later
    assert asyncio.run(engine.find_window()).game_id == NEXT_GAME  # past the cap it never reopens


def test_a_window_that_opens_during_a_replay_stops_the_replay(app, fake_cfbd: FakeCfbd, caplog):
    game = Saturday(app, fake_cfbd, [FULL], start=KICKOFF - timedelta(minutes=20))
    engine = game.engine
    engine.window = GameWindow(GAME, HOME, AWAY, WEEK, KICKOFF, KICKOFF - timedelta(minutes=30), KICKOFF + WINDOW_AFTER)

    async def scenario() -> None:
        engine.mode = "replay"
        engine.replay.running = True
        engine._replay_task = asyncio.get_running_loop().create_task(asyncio.sleep(3600))
        with pytest.raises(asyncio.CancelledError):
            await engine.run()
        assert engine._replay_task.cancelled()

    asyncio.run(scenario())
    assert "opened during a replay" in caplog.text and engine.replay.running is False
    assert fake_cfbd.count("/live/plays") == 1 and game.archive()["state"]["status"] == "final"


# --- status: the live view, the feed, the settle time ------------------------------------------------------------


def test_status_gives_the_live_view_an_hour_before_kickoff_and_polling_at_thirty_minutes(app, fake_cfbd: FakeCfbd):
    route_game(fake_cfbd, lambda r: respond(MID_GAME))
    engine: LiveEngine = app.state.live
    cfbd = app.state.cfbd
    clock = {"now": KICKOFF}
    cfbd._clock = lambda: clock["now"]
    cfbd.capabilities.live_plays = True
    for minutes, live_view, is_open, feed in ((61, False, False, "idle"), (59, True, False, "idle"), (29, True, True, "waiting")):
        clock["now"] = KICKOFF - timedelta(minutes=minutes)
        engine.window = asyncio.run(engine.find_window())
        status = engine.status()
        window = status["window"]
        assert window["gameId"] == GAME and window["liveView"] is live_view and window["open"] is is_open, minutes
        assert window["liveViewAt"] == (KICKOFF - timedelta(hours=1)).isoformat() and window["opensAt"] == (KICKOFF - timedelta(minutes=30)).isoformat() and window["extended"] is False
        assert status["feed"]["state"] == feed and set(status["feed"]) == FEED_KEYS and status["feed"]["checkedAt"].endswith("Z")
    cfbd.capabilities.live_plays = False
    assert engine.status()["feed"]["state"] == "no_live_key"
    engine.mode = "replay"
    assert engine.status()["feed"]["state"] == "ok"
    engine.mode = "idle"
    clock["now"] = KICKOFF + WINDOW_AFTER + timedelta(minutes=1)
    engine.window = asyncio.run(engine.find_window())
    assert engine.status()["window"]["gameId"] == NEXT_GAME and engine.status()["window"]["liveView"] is False


def test_the_next_window_starts_waiting_not_stale_from_the_last_game(app, fake_cfbd: FakeCfbd):
    route_game(fake_cfbd, lambda r: respond(MID_GAME))
    engine: LiveEngine = app.state.live
    cfbd = app.state.cfbd
    clock = {"now": KICKOFF + timedelta(hours=3)}
    cfbd._clock = lambda: clock["now"]
    cfbd.capabilities.live_plays = True
    window = GameWindow(GAME, HOME, AWAY, WEEK, KICKOFF, KICKOFF - timedelta(minutes=30), KICKOFF + WINDOW_AFTER)
    engine.window = window
    engine._open_window(window)
    engine._poll_succeeded(clock["now"])
    engine._new_event_at = clock["now"]
    engine._poll_failed("CFBD answered 500")
    assert engine.feed_health()["lastError"] == "CFBD answered 500"
    asyncio.run(engine._close_window(window))

    # the server stayed up for a week; the loop opens the next window up to a schedule check after opens_at
    engine.window = GameWindow(NEXT_GAME, NEXT["homeTeam"], NEXT["awayTeam"], NEXT["week"], NEXT_KICKOFF, NEXT_KICKOFF - timedelta(minutes=30), NEXT_KICKOFF + WINDOW_AFTER)
    clock["now"] = NEXT_KICKOFF - timedelta(minutes=30) + timedelta(seconds=30)
    fresh = {"state": "waiting", "lastSuccessAt": None, "lastNewEventAt": None, "consecutiveFailures": 0, "lastError": None, "staleSeconds": None}
    assert {k: v for k, v in engine.feed_health().items() if k != "checkedAt"} == fresh
    # and an answer from before this window opened never counts, however it was left behind
    engine._success_at = engine._new_event_at = KICKOFF + timedelta(hours=3)
    assert {k: v for k, v in engine.feed_health().items() if k != "checkedAt"} == fresh


def test_the_loop_opens_the_window_and_polls_at_opens_at_not_a_minute_later(app, fake_cfbd: FakeCfbd):
    game = Saturday(app, fake_cfbd, [snapshot(8, "In Progress"), FULL], start=KICKOFF - timedelta(minutes=30, seconds=20)).run()
    assert game.sleeps[0] == 20 and game.poll_log[0][1] == KICKOFF - timedelta(minutes=30)
    assert game.feed[0]["state"] == "idle" and game.feed[1]["state"] == "waiting" and game.finished


def test_the_settle_time_comes_from_the_schedule_so_it_survives_a_restart(app, fake_cfbd: FakeCfbd):
    route_game(fake_cfbd, lambda r: respond(MID_GAME), schedule=fixture_payload("games_team"))  # the real schedule: our last game is final
    engine: LiveEngine = app.state.live
    cfbd = app.state.cfbd
    cfbd.settle_until = None
    cfbd._clock = lambda: KICKOFF + timedelta(days=1, hours=1)
    asyncio.run(engine.find_window())
    assert cfbd.settle_until is None  # more than a day after the last kickoff
    cfbd._clock = lambda: KICKOFF + timedelta(hours=3)
    window = asyncio.run(engine.find_window())
    assert cfbd.settle_until == KICKOFF + timedelta(hours=24) and window.game_id == NEXT_GAME


# --- the stream ---------------------------------------------------------------------------------------------------


def read_stream(client: TestClient, url: str) -> list[dict[str, Any]]:
    got: list[dict[str, Any]] = []
    with client.stream("GET", url) as response:
        assert response.headers["content-type"].startswith("text/event-stream")
        current: dict[str, Any] = {}
        for line in response.iter_lines():
            if line.startswith("event:"):
                current["event"] = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                current["data"] = json.loads(line.split(":", 1)[1])
            elif line.startswith(":"):
                current["comment"] = line
            elif line == "" and current:
                got.append(current)
                if current.get("event") == "bye":
                    break
                current = {}
    return got


def test_the_stream_says_hello_with_the_feed_and_pings_when_quiet(app, client: TestClient, fake_cfbd: FakeCfbd, monkeypatch):
    client.portal.call(app.state.live.stop_background)
    monkeypatch.setattr(live_api, "PING_SECONDS", 0.2)
    events = read_stream(client, "/api/live/stream?delay=0&ttl=1.2")
    assert events[0]["event"] == "hello" and set(events[0]["data"]["feed"]) == FEED_KEYS and events[0]["data"]["feed"]["state"] == "idle"
    pings = [e for e in events if e.get("event") == "ping"]
    assert len(pings) >= 2 and all(set(p["data"]) == {"feed", "serverTime"} and set(p["data"]["feed"]) == FEED_KEYS for p in pings)
    assert pings[0]["data"]["serverTime"] == pings[0]["data"]["feed"]["checkedAt"]
    assert not any("comment" in e for e in events)  # the old keepalive comment is gone
    assert events[-1]["event"] == "bye"


def test_state_frames_carry_the_feed_because_a_busy_stream_never_pings(app, client: TestClient, fake_cfbd: FakeCfbd):
    """During play a state frame goes out every poll, so the 15 s ping never fires; without the feed on each
    frame the Live sheet would keep saying Stale for up to a minute after CFBD answers again."""
    engine: LiveEngine = app.state.live
    client.portal.call(engine.stop_background)
    engine.current_game_id, engine.home, engine.away = GAME, HOME, AWAY
    play = LiveEvent("play:1", "play", GAME, engine._clock() - timedelta(seconds=5), {"id": "1", "period": 1, "clock": {"minutes": 14, "seconds": 55}, "offense": "Swampwater Tech", "defense": "Silver Dollar", "playType": "Rush", "yardsGained": 4})
    client.portal.call(engine.publish, [play])
    events = read_stream(client, "/api/live/stream?delay=0&ttl=0.5")
    states = [e for e in events if e.get("event") == "state"]
    assert states and all(set(s["data"]["feed"]) == FEED_KEYS for s in states)


def test_the_status_route_carries_the_feed_and_the_new_counters(client: TestClient, fake_cfbd: FakeCfbd):
    data = client.get("/api/live/status").json()["data"]
    assert set(data["feed"]) == FEED_KEYS and data["feed"]["state"] == "idle" and data["window"] is None  # no schedule routed: no window
    assert {"last_success_at", "last_new_event_at", "consecutive_failures", "last_error_at"} <= set(data["stats"])
    state = client.get("/api/live/state?delay=0").json()["data"]
    assert set(state["engine"]["feed"]) == FEED_KEYS


# --- the recorder and the box-score warning ------------------------------------------------------------------------


def test_the_recorder_never_raises_and_never_overwrites(app, tmp_path: Path, caplog):
    engine: LiveEngine = app.state.live
    now = KICKOFF + timedelta(hours=1)
    blocker = tmp_path / "blocker"
    blocker.write_text("a file where the folder should be", encoding="utf-8")
    engine.recorder.folder = blocker
    asyncio.run(engine._record_raw(GAME, now, "plays", {"id": GAME}))
    assert "Could not record the plays answer" in caplog.text
    engine.recorder.folder = tmp_path / "live"
    asyncio.run(engine._record_raw(GAME, now, "plays", {"id": GAME, "status": object()}))  # not JSON: logged, skipped
    assert caplog.text.count("Could not record the plays answer") == 2
    for status in ("in progress", "in progress", "Final"):
        asyncio.run(engine._record_raw(GAME, now, "plays", {"id": GAME, "status": status}))
    folder = tmp_path / "live" / str(GAME)
    names = sorted(p.name for p in folder.glob("plays-*.json"))
    assert len(names) == 3 and len(set(names)) == 3  # the same millisecond three times: suffixed, never overwritten
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["counts"] == {"plays": 3} and [s["status"] for s in manifest["statuses"]] == ["in progress", "Final"]
    assert not list(folder.glob("*.tmp"))
    # a restart keeps counting from the manifest on disk
    fresh = type(engine.recorder)(tmp_path / "live", 12)
    fresh.write(GAME, now + timedelta(seconds=1), "box-teams", [], {"gameId": GAME})
    assert json.loads((folder / "manifest.json").read_text(encoding="utf-8"))["counts"] == {"plays": 3, "box-teams": 1}


def test_the_box_poll_warns_once_while_the_game_is_missing(app, fake_cfbd: FakeCfbd, caplog):
    engine: LiveEngine = app.state.live
    window = GameWindow(GAME, HOME, AWAY, WEEK, KICKOFF, KICKOFF - timedelta(minutes=30), KICKOFF + WINDOW_AFTER)
    engine.window = window
    answer = {"teams": []}
    fake_cfbd.route("/games/teams", handler=lambda r: httpx.Response(200, json=answer["teams"]))
    fake_cfbd.fixture("/games/players", "games_players")

    async def polls(n: int) -> None:
        for _ in range(n):
            await engine.poll_box(window)

    asyncio.run(polls(3))
    assert caplog.text.count("does not include game") == 1
    answer["teams"] = fixture_payload("games_teams")
    asyncio.run(polls(1))
    assert "includes game 526000600 again" in caplog.text
    answer["teams"] = []
    asyncio.run(polls(2))
    assert caplog.text.count("does not include game") == 2
    kinds = Counter(json.loads(p.read_text(encoding="utf-8"))["kind"] for p in (app.state.settings.data_dir / "live" / str(GAME)).glob("box-*.json"))
    assert kinds == {"box-teams": 6, "box-players": 6}


# --- the ticker's scoreboard -------------------------------------------------------------------------------------


SCOREBOARD = [
    {"id": NEXT_GAME, "startDate": "2026-09-26T19:30:00.000Z", "status": "in_progress", "period": 2, "clock": "4:10", "homeTeam": {"id": 57, "name": "Swampwater Tech Mudpuppies", "conference": "Biscuit Belt", "points": 10}, "awayTeam": {"id": 145, "name": "Diner Tech Rebels", "conference": "Biscuit Belt", "points": 7}},
]


def test_the_ticker_records_fresh_scoreboards_only_inside_the_window(app, client: TestClient, fake_cfbd: FakeCfbd):
    client.portal.call(app.state.live.stop_background)

    def games(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("team"):
            return httpx.Response(200, json=fixture_payload("games_team"))
        return httpx.Response(200, json=fixture_payload("games_week"))

    fake_cfbd.route("/games", handler=games)
    fake_cfbd.fixture("/teams/fbs", "teams_fbs")
    fake_cfbd.fixture("/rankings", "rankings")
    fake_cfbd.route("/scoreboard", json=SCOREBOARD)
    engine: LiveEngine = app.state.live
    cfbd = app.state.cfbd
    cfbd.capabilities.scoreboard = True
    clock = {"now": NEXT_KICKOFF + timedelta(hours=1)}
    cfbd._clock = lambda: clock["now"]
    engine.window = GameWindow(NEXT_GAME, NEXT["homeTeam"], NEXT["awayTeam"], NEXT["week"], NEXT_KICKOFF, NEXT_KICKOFF - timedelta(minutes=30), NEXT_KICKOFF + WINDOW_AFTER)
    folder = app.state.settings.data_dir / "live" / str(NEXT_GAME)

    first = client.get("/api/ticker").json()["data"]
    files = sorted(folder.glob("scoreboard-*.json"))
    assert len(files) == 1 and json.loads(files[0].read_text(encoding="utf-8"))["payload"] == SCOREBOARD
    clock["now"] += timedelta(seconds=5)
    second = client.get("/api/ticker").json()["data"]
    assert fake_cfbd.count("/scoreboard") == 1 and len(list(folder.glob("scoreboard-*.json"))) == 1  # served from the cache: not recorded again
    assert [g["gameId"] for g in first["games"]] == [g["gameId"] for g in second["games"]] and first["games"] == second["games"]
    engine.window = None
    clock["now"] += timedelta(minutes=5)  # past the scoreboard lifetime even when a small budget stretches it
    client.get("/api/ticker")
    assert fake_cfbd.count("/scoreboard") == 2 and len(list(folder.glob("scoreboard-*.json"))) == 1  # fresh, but no window: not recorded
    assert json.loads((folder / "manifest.json").read_text(encoding="utf-8"))["counts"] == {"scoreboard": 1}
