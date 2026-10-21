"""Freeze wave F7 (2026-10-20), the performance wave: the cache keeps what it read decoded until it changes, a part is parsed
once per key, a game's events live in memory with one built state per delay, answers leave compressed but the event stream,
the page's files are named under the build's folder and kept, data requests wait for the startup checks while health does
not, an edition and a season file are decoded once per change, the LAN address is kept a minute, the leader lines and the
profiles are built once per list."""

from __future__ import annotations

import asyncio
import json
import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

import app.cache as cache_module
from app import netinfo
from app.build import build_id
from app.cache import Cache, DataKind
from app.cfbd.client import Fetched
from app.cfbd.models import PlayerStat
from app.db import Database
from app.live.events import LiveEvent
from app.live.store import EventStore
from app.main import STARTUP_INLINE_SECONDS, Compression
from app.services.editions import Editions
from app.services.national_extra import PageRanks
from app.services.parts import PartFetcher
from app.services.players import LINES_MEMO_LIMIT, lines_from
from app.services.profiles import profiles_for
from app.services.season_notes import SeasonNotes

ROOT = Path(__file__).resolve().parents[1]
MONDAY = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)


# --- the cache in memory -----------------------------------------------------------------------------------------------------


def test_the_cache_keeps_what_it_read_decoded_until_it_changes(tmp_path: Path, monkeypatch):
    db = Database(tmp_path / "cache.db")
    cache = Cache(db)
    cache.put("k", "/x", {"a": "1"}, {"n": 1}, fetched_at=MONDAY, ttl=timedelta(hours=1))
    first = cache.get("k")
    assert first is not None and cache.get("k") is first, "the second read is the first's object, not another decode"
    assert cache.memory_stats()["entries"] == 1 and cache.memory_stats()["bytes"] == first.size_bytes
    cache.put("k", "/x", {"a": "1"}, {"n": 2}, fetched_at=MONDAY, ttl=timedelta(hours=1))
    assert cache.get("k").payload == {"n": 2}, "a put replaces what memory held"
    cache.delete("k")
    assert cache.get("k") is None and cache.memory_stats() == {"entries": 0, "bytes": 0}
    cache.put("k2", "/y", None, [1, 2, 3], fetched_at=MONDAY, ttl=timedelta(hours=1))
    assert cache.get("k2") is not None and cache.clear() == 1 and cache.get("k2") is None and cache.memory_stats()["entries"] == 0
    # a second Cache over the same file starts cold and reads the row
    cache.put("k3", "/z", None, {"z": 1}, fetched_at=MONDAY, ttl=timedelta(hours=1))
    cold = Cache(db)
    assert cold.get("k3").payload == {"z": 1} and cold.memory_stats()["entries"] == 1
    # the budget: beyond it the least recently used leave memory, never the file
    monkeypatch.setattr(cache_module, "MEMORY_BUDGET", 1)
    cache.put("k4", "/w", None, {"w": 1}, fetched_at=MONDAY, ttl=timedelta(hours=1))
    assert cache.memory_stats()["entries"] == 0 and cache.get("k4").payload == {"w": 1}
    db.close()


# --- a part parsed once per key -------------------------------------------------------------------------------------------


class StubClient:
    def __init__(self) -> None:
        self.at = MONDAY
        self.calls = 0

    async def get(self, endpoint: str, params: dict, kind: DataKind | None = None, max_age: timedelta | None = None) -> Fetched:
        self.calls += 1
        rows = [{"playerId": str(i), "player": f"P{i}", "team": "A", "category": "passing", "statType": "YDS", "stat": i} for i in range(3)]
        return Fetched(endpoint, {k: str(v) for k, v in params.items()}, rows, self.at, "cache", False, 0.0)


def test_a_part_is_parsed_once_per_key_until_its_payload_is_refetched():
    stub = StubClient()
    fetcher = PartFetcher(stub)  # type: ignore[arg-type]
    fetch = lambda **params: asyncio.run(fetcher.fetch("p", "/stats/player/season", params, PlayerStat, DataKind.SEASON_STATS))  # noqa: E731
    first = fetch(year=2026)
    again = fetch(year=2026)
    assert first.ok and again.records is first.records, "the same key, the same fetch time: the records already parsed"
    assert len(fetcher._memo) == 1
    stub.at = MONDAY + timedelta(hours=1)
    fresh = fetch(year=2026)
    assert fresh.records is not first.records and fresh.records == first.records and len(fetcher._memo) == 1, "a refetched payload is parsed again, in the same slot"
    fetcher.MEMO_LIMIT = 2
    fetch(year=2025)
    fetch(year=2024)
    assert [key[1] for key in fetcher._memo] == [(("year", "2025"),), (("year", "2024"),)], "the least recently used leaves at the limit"
    fetch(year=2025)
    fetch(year=2023)
    assert [key[1] for key in fetcher._memo] == [(("year", "2025"),), (("year", "2023"),)], "a hit moves to the back"


# --- the live store in memory, one built state per delay -----------------------------------------------------------------


def test_a_games_events_live_in_memory_and_a_cold_reader_sees_the_same(tmp_path: Path):
    db = Database(tmp_path / "live.db")
    store = EventStore(db)
    t0 = datetime(2026, 9, 26, 20, 0, tzinfo=timezone.utc)
    store.append([LiveEvent("play:1", "play", 7, t0, {"id": "1", "text": "Run for 3"})])
    store.append([LiveEvent("status", "status", 7, t0 + timedelta(seconds=30), {"status": "in_progress", "period": 1})])
    store.append([LiveEvent("play:2", "play", 7, t0 + timedelta(seconds=60), {"id": "2", "text": "Pass"})])
    store.append([LiveEvent("status", "status", 7, t0 + timedelta(seconds=90), {"status": "in_progress", "period": 2})])
    assert store.count(7) == 4 and store.count_kind(7, "play") == 2 and store.count_kind(7, "status") == 2 and store.latest_seq(7) == 4
    assert store.latest(7, "status") == {"status": "in_progress", "period": 2}, "the newest, whatever the delay"
    assert store.latest(7, "nothing") is None and store.latest(8, "status") is None
    assert [e.id for e in store.released(7, t0 + timedelta(seconds=30))] == ["play:1", "status"]
    assert [e.seq for e in store.released(7, t0 + timedelta(seconds=90), after_seq=2)] == [3, 4]
    assert [e.seq for e in store.released(7, t0 + timedelta(seconds=90), limit=2)] == [1, 2]
    assert store.pending_after(7, t0 + timedelta(seconds=30), 2) and not store.pending_after(7, t0 + timedelta(seconds=90), 4)
    cold = EventStore(db)  # another reader over the same log reads it once and agrees
    assert [e.seq for e in cold.released(7, t0 + timedelta(hours=1))] == [1, 2, 3, 4] and cold.latest(7, "status") == store.latest(7, "status")
    assert cold.count_kind(7, "play") == 2 and cold.latest_seq(7) == 4 and cold.games() == [7]
    assert store.clear(7) == 4 and store.count(7) == 0 and store.latest_seq(7) == 0 and store.released(7, t0 + timedelta(hours=1)) == []
    db.close()


def test_the_engine_builds_one_state_per_delay_and_each_caller_gets_its_own(app, client: TestClient):
    engine = app.state.live
    gid = 424242
    key = engine.store_key(gid)
    t0 = datetime.now(timezone.utc) - timedelta(minutes=10)
    engine.store.append([LiveEvent("play:1", "play", key, t0, {"id": "1", "text": "Run for 3"})])
    first = engine.state(0.0, game_id=gid)
    again = engine.state(0.0, game_id=gid)
    assert first is not again and first["lastSeq"] == again["lastSeq"] == 1 and first["plays"] is again["plays"], "one fold, two top levels"
    assert "pending" in first and len(engine._state_memo) == 1
    engine.store.append([LiveEvent("play:2", "play", key, t0 + timedelta(seconds=30), {"id": "2", "text": "Pass"})])
    third = engine.state(0.0, game_id=gid)
    assert third["lastSeq"] == 2 and len(third["plays"]) == 2 and len(engine._state_memo) == 2, "a new event, a new build"
    held = engine.state(3600.0, game_id=gid)
    assert held["lastSeq"] == 0 and held["pending"] is True and held["delaySeconds"] == 3600.0 and len(engine._state_memo) == 3, "a long delay sees nothing yet, and says so"
    first["plays"] = None  # a caller's own top level is its own to change
    assert engine.state(0.0, game_id=gid)["plays"] is third["plays"]


# --- compressed answers, never the stream; the page's files under the build's folder --------------------------------------


def test_answers_leave_compressed_but_the_event_stream(client: TestClient):
    async def big(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"text/plain")]})
        await send({"type": "http.response.body", "body": b"x" * 5000})

    raw = TestClient(Compression(big, minimum_size=1500))
    packed = raw.get("/api/season/overview", headers={"Accept-Encoding": "gzip"})
    assert packed.headers.get("content-encoding") == "gzip" and packed.content == b"x" * 5000
    stream = raw.get("/api/live/stream?delay=45", headers={"Accept-Encoding": "gzip"})
    assert "content-encoding" not in stream.headers and stream.content == b"x" * 5000, "the stream's chunks leave as they are written"
    small = TestClient(Compression(big, minimum_size=6000)).get("/api/x", headers={"Accept-Encoding": "gzip"})
    assert "content-encoding" not in small.headers
    health = client.get("/api/health", headers={"Accept-Encoding": "gzip"})
    assert health.status_code == 200 and health.headers.get("content-encoding") == "gzip" and health.json()["data"]["status"]


def test_the_page_names_its_files_under_the_builds_folder_which_is_kept_a_year(client: TestClient):
    bid = build_id()
    page = client.get("/")
    assert page.status_code == 200 and f'src="/static/v/{bid}/js/app.js"' in page.text and f'href="/static/v/{bid}/css/' in page.text
    assert page.headers["cache-control"] == "no-cache", "the page itself is never kept"
    versioned = client.get(f"/static/v/{bid}/js/app.js")
    assert versioned.status_code == 200 and versioned.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert versioned.content == (ROOT / "static" / "js" / "app.js").read_bytes(), "the file itself, from static/"
    assert client.get(f"/static/v/{bid}/css/tokens.css").status_code == 200
    plain = client.get("/static/js/app.js")
    assert plain.status_code == 200 and plain.headers["cache-control"] == "no-cache", "the plain path still answers, for the tools and old pages"
    assert client.get("/static/v/not-a-build/js/app.js").status_code == 404 and client.get(f"/static/v/{bid}/js/nothing.js").status_code == 404
    assert client.get(f"/static/v/{bid}/../../.env").status_code in (404, 400)


# --- the start: data requests wait for the checks; health does not ---------------------------------------------------------


def test_data_requests_wait_for_the_startup_checks_and_health_does_not(app, client: TestClient):
    flags: list[str] = []

    def make():
        event = asyncio.Event()

        async def checks() -> None:
            await event.wait()
            flags.append("done")

        return event, asyncio.get_running_loop().create_task(checks())

    event, task = client.portal.call(make)
    app.state.startup_checks = task
    assert client.get("/api/health").status_code == 200 and flags == [], "health answers while the checks run (the boot screen polls it)"
    assert client.get("/").status_code == 200 and client.get(f"/static/v/{build_id()}/js/app.js").status_code == 200 and flags == [], "the page and its files too"
    result: dict[str, int] = {}
    worker = threading.Thread(target=lambda: result.setdefault("status", client.get("/api/identity").status_code))
    worker.start()
    worker.join(0.4)
    assert worker.is_alive() and flags == [], "a data request waits"
    client.portal.call(event.set)
    worker.join(15)
    assert not worker.is_alive() and result["status"] == 200 and flags == ["done"]
    assert STARTUP_INLINE_SECONDS == 1.5
    main_src = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    assert "WARM_DELAY_SECONDS = 2 " in main_src, "the warm-up comes 2 s after the start (the tests hold it off)"


# --- files decoded once per change; the LAN address kept a minute ---------------------------------------------------------


def _touch_later(path: Path) -> None:
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 10_000_000))


def test_an_edition_is_decoded_once_per_change_and_a_repeated_save_reads_nothing(tmp_path: Path):
    store = Editions(tmp_path, 2026)
    edition = {"key": "week-4", "week": 4, "matchups": [{"gameId": 5, "status": "final", "headline": {"text": "A beats B"}}], "frozen": False}
    saved = store.save(edition)
    loaded = store.load("week-4")
    assert loaded is store.load("week-4") and loaded["matchups"][0]["gameId"] == 5, "the same file, the same decode"
    assert store.save(dict(edition)) is saved, "the same edition again: nothing read back, nothing written"
    path = tmp_path / "season" / "2026" / "paper" / "week-4.json"
    by_hand = {**loaded, "matchups": [{"gameId": 6, "status": "final"}]}
    path.write_text(json.dumps(by_hand), encoding="utf-8")
    _touch_later(path)
    assert store.load("week-4")["matchups"][0]["gameId"] == 6, "a changed file is read again"
    assert store.save({**edition, "matchups": [{"gameId": 7}]})["matchups"][0]["gameId"] == 7
    path.unlink()
    assert store.load("week-4") is None


def test_a_season_file_is_decoded_once_per_change(tmp_path: Path):
    notes = SeasonNotes(tmp_path, 2026)
    assert notes.coaches() == {"teams": {}, "batches": {}}
    notes.coaches_path.parent.mkdir(parents=True, exist_ok=True)
    notes.coaches_path.write_text(json.dumps({"teams": {"A": {"school": "A", "headCoach": "One"}}}), encoding="utf-8")
    first = notes._read(notes.coaches_path)
    assert first is notes._read(notes.coaches_path) and notes.coaches()["teams"]["A"]["headCoach"] == "One"
    notes.coaches_path.write_text(json.dumps({"teams": {"A": {"school": "A", "headCoach": "Two"}}}), encoding="utf-8")
    _touch_later(notes.coaches_path)
    assert notes.coaches()["teams"]["A"]["headCoach"] == "Two"
    notes.coaches_path.write_text("{broken", encoding="utf-8")
    _touch_later(notes.coaches_path)
    assert notes.coaches() == {"teams": {}, "batches": {}}, "a damaged file is empty, not the last good decode"
    notes.coaches_path.unlink()
    assert notes.coaches() == {"teams": {}, "batches": {}}


def test_the_lan_address_is_kept_a_minute(monkeypatch):
    calls: list[int] = []
    monkeypatch.setattr(netinfo, "_lan_ip", lambda: calls.append(1) or "10.0.0.5")
    monkeypatch.setattr(netinfo, "_LAN", None)
    assert netinfo.lan_ip() == "10.0.0.5" and netinfo.lan_ip() == "10.0.0.5" and calls == [1]
    monkeypatch.setattr(netinfo, "LAN_IP_SECONDS", 0.0)
    assert netinfo.lan_ip() == "10.0.0.5" and calls == [1, 1]


# --- the leader lines, the profiles and the rank tables, built once per list -------------------------------------------------


def _rows(n: int, team: str = "A") -> list[PlayerStat]:
    return [PlayerStat(playerId=str(i), player=f"P{i}", position="QB", team=team if i % 2 else "B", category="passing", statType="YDS", stat=i) for i in range(n)]


def test_the_leader_lines_are_built_once_per_list():
    big = _rows(250)
    lines = lines_from(big)
    assert lines_from(big) is lines and len(lines) == 250 and lines[("3", "passing")].team == "A"
    assert lines_from(list(big)) is not lines, "another list, even an equal one, is its own"
    small = _rows(5)
    assert lines_from(small) is not lines_from(small), "a short list is not worth keeping"
    for i in range(LINES_MEMO_LIMIT + 2):
        lines_from(_rows(200 + i))
    from app.services import players

    assert len(players._LINES_MEMO) <= LINES_MEMO_LIMIT


def test_the_profiles_are_built_once_per_set_of_lists():
    stats: list = []
    league: list = []
    team: list = []
    built = profiles_for(stats, league, team, "Biscuit Belt", "A")
    assert profiles_for(stats, league, team, "Biscuit Belt", "A") is built
    assert profiles_for(stats, league, team, "Biscuit Belt", "B") is not built, "another team, another set of edges"
    assert profiles_for([], league, team, "Biscuit Belt", "A") is not built, "another list is another build"


def test_the_national_rank_tables_are_built_once_per_fetch(app, client: TestClient, fake_cfbd):
    from tests.test_national_extra import route_national

    route_national(fake_cfbd)
    PageRanks._memo.clear()
    assert client.get("/api/roster").status_code == 200
    keys = list(PageRanks._memo)
    assert len(keys) == 1
    assert client.get("/api/roster").status_code == 200 and list(PageRanks._memo) == keys, "the same parts, the same tables"
    assert client.get("/api/team/Swampwater%20Tech").status_code == 200
    after_team = list(PageRanks._memo)
    assert keys[0] in after_team and len(after_team) <= 2, "the team page ranks over its own parts (the returning production too): one more set at most"
    assert client.get("/api/team/Swampwater%20Tech").status_code == 200 and list(PageRanks._memo) == after_team
