"""The live engine: the poller inside a game window, the replay of a finished game on a
simulated clock, the raw recorder, the feed health, and the subscriber list the stream feeds from.

Rules from docs/02-ARCHITECTURE.md, "Live engine" and "Quota guard":
- Poll only inside the game window (30 minutes before kickoff until the final) and only while
  at least one client is connected. Halftime and long delays slow the poll to 30 seconds.
- Every raw upstream answer during a real game is written to data/live/<game_id>/ so that
  exact game can be replayed later, quirks included: the plays, both box-score answers, the win
  probability, the two in-game probes and the ticker's scoreboard, each file named by kind and
  time, with a manifest per game.
- A game still in progress when the window would close keeps it open, up to ten hours after
  kickoff, when it has stored plays and CFBD does not call it postponed, canceled or forfeited.
  With nobody watching, a stretched window still looks at the feed every half hour so a late
  final closes it. A window that closes without a final makes one last look at the feed and
  writes a partial archive, never an archive for a game with no stored plays, and never over
  the complete archive of a game already final.
- A kickoff CFBD still lists as TBD (its placeholder is local midnight) opens no window. Until
  the first play is stored, the open window re-reads the schedule every minute (a cached copy at
  most five minutes old), so a
  kickoff that moves or turns TBD moves the window with it. A window that closes without a play
  or a final does not retire its game: a later real kickoff opens a new window.
- Replay never calls the live endpoint; it reads the finished game's plays and drives (cached
  for good) and emits through the same store and stream, under its own key (the negated game
  id, Phase 12), so replaying a game the app recorded never touches that game's real event log.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.cache import DataKind
from app.cfbd.client import CfbdClient, CfbdError
from app.cfbd.models import Drive, FieldGoalEp, Game, GamePlayerStats, GameTeamStats, LiveGame, Play, PlayWinProbability, PredictedPoints, RosterPlayer, ScoreboardGame, parse_one, parse_records
from app.cfbd.quota import QuotaBlocked
from app.config import Settings
from app.db import Database
from app.live.analysis import ep_table, fg_table
from app.live.events import LiveEvent, box_events, clock_dict, events_from_finished, events_from_live, status_from_scores, wp_event
from app.live.state import derive_state
from app.live.store import EventStore
from app.services import gamekeys
from app.services.analytics import wp_series

log = logging.getLogger("kickoff.live")
snap_log = logging.getLogger("kickoff.live.snapshot")

WINDOW_BEFORE = timedelta(minutes=30)  # polling starts here
LIVE_VIEW_BEFORE = timedelta(minutes=60)  # the browser switches to the Live sheet here (contract C1)
WINDOW_AFTER = timedelta(hours=5)  # a safety net: the window also closes on the final
WINDOW_CAP = timedelta(hours=10)  # a game still in progress keeps the window open this long at most
WINDOW_EXTEND_STEP = timedelta(minutes=15)  # how far each extension pushes the close
CHECK_POLL_SPACING = timedelta(minutes=30)  # a stretched window with nobody watching looks at the feed this often
CALLED_OFF_WORDS = ("postpon", "cancel", "forfeit")  # a raw status with one of these never stretches the window
SETTLE_AFTER = timedelta(hours=24)  # finished-game answers cache an hour, not for good, until kickoff plus this (contract C4)
SCHEDULE_CHECK_SECONDS = 60
CLIENT_WAIT_SECONDS = 5
HALFTIME_POLL_SECONDS = 30
MAX_BACKOFF_SECONDS = 60
CLIENT_GRACE_SECONDS = 90  # a state poll counts as a connected client for this long
FEED_STALE_MIN_SECONDS = 45  # the feed is stale after max(this, three poll intervals) without a parsed answer
FEED_STALE_INTERVALS = 3
REPLAY_DEFAULT_GAP_SECONDS = 25.0  # when a play has no wall clock
REPLAY_MAX_GAP_SECONDS = 180.0  # a TV timeout is long enough; halftime is not a wait
SNAPSHOT_SECONDS = 60  # a one-line game snapshot in the log this often inside the window
STATE_RECORD_SECONDS = 300  # and the derived state (without the play and drive lists) on disk this often
BOX_POLL_SECONDS = 180  # the box score and player lines refresh every three minutes inside the window
SYNC_PLAY_SECONDS = 7.0  # "Sync to my TV": a play's length from snap to whistle, roughly
SYNC_LOOKBACK = timedelta(seconds=150)  # the snaps a tap can mean: up to this long before it
SYNC_LATENCY_PLAYS = 20  # the feed's delay is read off this many recent plays
SYNC_MAX_DELAY = 120
SCOREBOARD_SECONDS = 60  # the engine reads the scoreboard itself when the ticker has not for this long
KICKOFF_RECHECK_MAX_AGE = timedelta(minutes=5)  # the schedule re-read before the first play is at most this old
MANIFEST_NAME = "manifest.json"
CLOSE_REASON_MAX = 160


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _shape(payload: Any) -> str:
    """A payload described for a log line without printing it."""
    if isinstance(payload, list):
        return f"a list of {len(payload)}"
    if isinstance(payload, dict):
        return f"an object with {len(payload)} keys"
    return "null" if payload is None else type(payload).__name__


def _raw_status(payload: Any) -> str | None:
    """The /live/plays document's own status text, exactly as CFBD sent it."""
    if isinstance(payload, list):
        payload = payload[0] if payload else None
    if not isinstance(payload, dict) or "status" not in payload or payload["status"] is None:
        return None
    value = payload["status"]
    return value if isinstance(value, str) else json.dumps(value)


@dataclass
class GameWindow:
    game_id: int
    home: str | None
    away: str | None
    week: int | None
    kickoff: datetime
    opens_at: datetime
    closes_at: datetime
    season_type: str | None = None  # Phase 15: "postseason" for a bowl or playoff game (CFBD week 1)

    def contains(self, now: datetime) -> bool:
        return self.opens_at <= now <= self.closes_at

    @property
    def cap(self) -> datetime:
        return self.kickoff + WINDOW_CAP


@dataclass
class ReplayStatus:
    running: bool = False
    game_id: int | None = None
    speed: float = 1.0
    source: str = "finished"
    emitted: int = 0
    total: int = 0
    started_at: str | None = None
    error: str | None = None
    finished: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {"running": self.running, "gameId": self.game_id, "speed": self.speed, "source": self.source, "emitted": self.emitted, "total": self.total, "startedAt": self.started_at, "error": self.error, "finished": self.finished}


@dataclass
class EngineStats:
    polls: int = 0
    poll_failures: int = 0
    consecutive_failures: int = 0  # live polls that failed in a row; a parsed answer resets it
    events_stored: int = 0
    last_poll_at: str | None = None
    last_success_at: str | None = None  # the last parsed /live/plays answer in this window
    last_new_event_at: str | None = None  # the last time a new play or drive was stored
    last_error: str | None = None
    last_error_at: str | None = None
    recorded_files: int = 0
    stream_clients: int = 0
    extra: dict[str, Any] = field(default_factory=dict)


class Recorder:
    """Every raw answer of a real game on disk: data/live/<game_id>/<kind>-<UTC time>.json with a
    {receivedAt, kind, payload} wrapper, plus a manifest per game (the window, a count per kind,
    the first and last receipt, every distinct raw status string). Called from worker threads;
    never raises: a failed write is a warning in the log."""

    def __init__(self, folder: Path, poll_seconds: int) -> None:
        self.folder = folder
        self.poll_seconds = poll_seconds
        self.files = 0
        self._lock = threading.Lock()
        self._manifests: dict[int, dict[str, Any]] = {}

    def write(self, game_id: int, received_at: datetime, kind: str, payload: Any, meta: dict[str, Any]) -> Path | None:
        received = received_at.astimezone(timezone.utc)
        stamp = received.isoformat(timespec="milliseconds").replace("+00:00", "Z")
        try:
            body = json.dumps({"receivedAt": stamp, "kind": kind, "payload": payload}, separators=(",", ":"))
        except (TypeError, ValueError) as exc:
            log.warning("Could not record the %s answer for game %s: %s", kind, game_id, exc)
            return None
        folder = self.folder / str(game_id)
        try:
            folder.mkdir(parents=True, exist_ok=True)
            path = self._create(folder, f"{kind}-{received.strftime('%Y%m%dT%H%M%S%f')[:-3]}Z", body)
        except OSError as exc:
            log.warning("Could not record the %s answer for game %s: %s", kind, game_id, exc)
            return None
        with self._lock:
            self.files += 1
            self._update_manifest(game_id, folder, stamp, kind, payload, meta)
        return path

    @staticmethod
    def _create(folder: Path, base: str, body: str) -> Path:
        """A new file, never an overwrite: two answers in the same millisecond get a suffix."""
        for n in range(100):
            path = folder / (f"{base}-{n}.json" if n else f"{base}.json")
            try:
                with path.open("x", encoding="utf-8") as handle:
                    handle.write(body)
                return path
            except FileExistsError:
                continue
        raise OSError(f"no free file name for {base} in {folder}")

    def _load_manifest(self, folder: Path, game_id: int) -> dict[str, Any]:
        """The manifest on disk, so a restart mid-game keeps counting; a fresh one when it is missing or broken."""
        fresh: dict[str, Any] = {"gameId": game_id, "home": None, "away": None, "week": None, "kickoff": None, "pollSeconds": self.poll_seconds, "counts": {}, "firstReceivedAt": None, "lastReceivedAt": None, "statuses": []}
        path = folder / MANIFEST_NAME
        if not path.is_file():
            return fresh
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            log.warning("Recording manifest for game %s is unreadable (%s); starting a new one", game_id, exc)
            return fresh
        if not isinstance(raw, dict):
            log.warning("Recording manifest for game %s has the wrong shape; starting a new one", game_id)
            return fresh
        counts = raw.get("counts") if isinstance(raw.get("counts"), dict) else {}
        statuses = raw.get("statuses") if isinstance(raw.get("statuses"), list) else []
        fresh.update({k: raw.get(k) for k in ("home", "away", "week", "kickoff", "firstReceivedAt", "lastReceivedAt") if raw.get(k) is not None})
        fresh["counts"] = {str(k): v for k, v in counts.items() if isinstance(v, int) and not isinstance(v, bool)}
        fresh["statuses"] = [s for s in statuses if isinstance(s, dict) and isinstance(s.get("status"), str)]
        return fresh

    def _update_manifest(self, game_id: int, folder: Path, stamp: str, kind: str, payload: Any, meta: dict[str, Any]) -> None:
        manifest = self._manifests.get(game_id)
        if manifest is None:
            manifest = self._load_manifest(folder, game_id)
            self._manifests[game_id] = manifest
        for key, value in meta.items():
            if value is not None:
                manifest[key] = value
        manifest["pollSeconds"] = self.poll_seconds
        manifest["counts"][kind] = manifest["counts"].get(kind, 0) + 1
        if manifest["firstReceivedAt"] is None:
            manifest["firstReceivedAt"] = stamp
        manifest["lastReceivedAt"] = stamp
        if kind == "plays":
            raw = _raw_status(payload)
            if raw is not None and not any(s["status"] == raw for s in manifest["statuses"]):
                manifest["statuses"].append({"status": raw, "firstSeenAt": stamp})
                log.info("Live feed for game %s reports the status %r for the first time", game_id, raw)
        target = folder / MANIFEST_NAME
        temp = folder / (MANIFEST_NAME + ".tmp")
        try:
            temp.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
            os.replace(temp, target)
        except (OSError, TypeError, ValueError) as exc:
            log.warning("Could not write the recording manifest for game %s: %s", game_id, exc)


class LiveEngine:
    def __init__(self, client: CfbdClient, settings: Settings, db: Database, *, clock: Callable[[], datetime] | None = None, sleep: Callable[[float], Any] = asyncio.sleep) -> None:
        self.client = client
        self.settings = settings
        self.store = EventStore(db)
        self._clock = clock or (lambda: client._clock())  # resolved on every call so a swapped client clock is honoured
        self._sleep = sleep
        self._subscribers: set[asyncio.Queue] = set()
        self._last_state_poll: datetime | None = None
        self.window: GameWindow | None = None
        self.mode = "idle"  # idle, live, replay
        self.current_game_id: int | None = None
        self.home: str | None = None
        self.away: str | None = None
        self.replay = ReplayStatus()
        self._replay_task: asyncio.Task[Any] | None = None
        self._poll_task: asyncio.Task[Any] | None = None
        self.stats = EngineStats()
        self._backoff = 0
        self._halftime = False
        self._final_seen = False
        self._done_games: set[int] = set()  # finals seen this run: the cached schedule may still say not completed
        self._last_box_poll: datetime | None = None
        self._success_at: datetime | None = None  # the last parsed /live/plays answer in this window
        self._new_event_at: datetime | None = None
        self._feed_error: str | None = None  # the last live poll failure, for the feed health
        self._probes: set[str] = set()  # in-game win probability probes already made in this window
        self._box_missing_warned = False
        self._extension_warned = False
        self._last_raw_status: str | None = None  # the newest /live/plays status text in this window, as CFBD sent it
        self._check_poll_at: datetime | None = None  # the last look at the feed past the planned close with nobody watching
        self._kickoff_checked_at: datetime | None = None  # the last schedule re-read while waiting for the first play
        self._tbd_logged: set[int] = set()  # TBD kickoffs already named in the log
        self._scoreboard_at: datetime | None = None  # the last fresh scoreboard handed over in this window
        self._rosters: dict[str, dict[int, list[dict[str, str]]]] = {}  # both teams' rosters by jersey, for the play-by-play lines
        self._rosters_for: int | None = None  # the game those rosters were loaded for
        self._ep_tables: dict[str, dict[int, float]] = {}  # CFBD's 1st-and-10 expected points and field-goal make chances
        self._replay_key_for: int | None = None  # the game whose events live under the replay key (-game id)
        self._ep_tried_at: datetime | None = None  # the last attempt at the expected points tables
        self._snapshot_at: datetime | None = None
        self._state_recorded_at: datetime | None = None
        self.archive_dir = settings.data_dir / "archive"
        self.recorder = Recorder(settings.data_dir / "live", settings.live_poll_seconds)
        self.record_dir = self.recorder.folder

    # --- subscribers and gating ------------------------------------------------------------------

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._subscribers.add(queue)
        self.stats.stream_clients = len(self._subscribers)
        return queue

    def wake_streams(self) -> None:
        """Wake every open stream at once (the server is shutting down); each reads the flag and ends."""
        self._notify([])

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)
        self.stats.stream_clients = len(self._subscribers)

    def note_state_poll(self) -> None:
        self._last_state_poll = self._clock()

    def clients_connected(self) -> bool:
        if self._subscribers:
            return True
        return self._last_state_poll is not None and (self._clock() - self._last_state_poll).total_seconds() < CLIENT_GRACE_SECONDS

    def window_open(self, now: datetime | None = None) -> bool:
        """A real game's window is open now (never during a replay)."""
        window = self.window
        return self.mode != "replay" and window is not None and window.contains(now or self._clock())

    def _notify(self, stored: list[LiveEvent]) -> None:
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(len(stored))
            except asyncio.QueueFull:
                pass  # the reader is behind; it catches up from the store on its next tick

    async def publish(self, events: list[LiveEvent]) -> list[LiveEvent]:
        stored = await asyncio.to_thread(self.store.append, events)
        if stored:
            self.stats.events_stored += len(stored)
            if any(e.kind in ("play", "drive") for e in stored):
                self._new_event_at = self._clock()
                self.stats.last_new_event_at = _iso(self._new_event_at)
            self._notify(stored)
        return stored

    async def _publish_safely(self, events: list[LiveEvent], what: str) -> list[LiveEvent] | None:
        """Publish, or log why not and return None: one failed write must not stop the game, and
        the next poll carries the same plays again."""
        try:
            return await self.publish(events)
        except Exception as exc:  # noqa: BLE001 - logged with its traceback and shown on the status
            log.exception("Could not store the %s events for game %s; the next poll tries again", what, self.current_game_id)
            self._note_error(f"store: {exc.__class__.__name__}: {exc}")
            return None

    # --- reading -----------------------------------------------------------------------------------

    def cutoff(self, delay_seconds: float) -> datetime:
        return self._clock() - timedelta(seconds=max(0.0, delay_seconds))

    def store_key(self, game_id: int) -> int:
        """Where a game's events live in the store: a replayed game under its negated id."""
        return -game_id if game_id == self._replay_key_for else game_id

    def state(self, delay_seconds: float, game_id: int | None = None) -> dict[str, Any] | None:
        gid = game_id or self.current_game_id
        if gid is None:
            return None
        key = self.store_key(gid)
        events = self.store.released(key, self.cutoff(delay_seconds))
        state = derive_state(events, game_id=gid, home=self.home, away=self.away, mode=self.mode, rosters=self._rosters if self._rosters_for == gid else None, ep_tables=self._ep_tables)
        state["delaySeconds"] = delay_seconds
        state["team"] = self.settings.team  # the side the sheet follows (TEAM in .env), so it never assumes a team
        state["pending"] = self.store.pending_after(key, self.cutoff(delay_seconds), state["lastSeq"])
        return state

    def released_since(self, game_id: int, delay_seconds: float, after_seq: int) -> list[LiveEvent]:
        return self.store.released(self.store_key(game_id), self.cutoff(delay_seconds), after_seq)

    def pending(self, game_id: int, delay_seconds: float, after_seq: int) -> bool:
        return self.store.pending_after(self.store_key(game_id), self.cutoff(delay_seconds), after_seq)

    def sync(self, tap_at: datetime) -> dict[str, Any]:
        """"Sync to my TV" (Phase 12). The owner tapped at `tap_at` (server time) when he saw a snap
        on TV. Candidates are the real game's snaps from up to 150 s before the tap, newest first,
        with only what is known before the snap (no result, no play text). For each, the TV lag is
        the tap minus the snap's wall clock, and the suggested delay is that lag plus a play's
        length minus how late the feed runs, read off the fastest tenth of the recent plays (so
        most plays stay hidden until the TV has shown them), rounded up to 5 s, 0 to 120."""
        gid = self.current_game_id
        out: dict[str, Any] = {"tapAt": _iso(tap_at), "gameId": gid, "candidates": [], "feedLatency": None, "note": None}
        if self.mode != "live" or gid is None:
            out["note"] = "Sync works during a live game."
            return out
        firsts: dict[str, tuple[datetime, dict[str, Any]]] = {}
        for event in self.store.released(gid, self._clock()):
            if event.kind == "play" and isinstance(event.data, dict) and event.id not in firsts:
                firsts[event.id] = (event.received_at, event.data)
        timed: list[tuple[datetime, datetime, dict[str, Any]]] = []
        for received, data in firsts.values():
            wall = self._local(data.get("wallclock") if isinstance(data.get("wallclock"), str) else None)
            if wall is not None:
                timed.append((wall, received, data))
        timed.sort(key=lambda t: t[0])
        latencies = sorted((received - wall).total_seconds() for wall, received, _ in timed[-SYNC_LATENCY_PLAYS:])
        if not latencies:
            out["note"] = "No plays with a snap time yet. Try again after a few plays."
            return out
        fast = latencies[len(latencies) // 10]
        out["feedLatency"] = {"fastSeconds": round(fast, 1), "medianSeconds": round(latencies[len(latencies) // 2], 1), "plays": len(latencies)}
        for wall, _received, data in reversed(timed):
            if wall > tap_at + timedelta(seconds=3) or wall < tap_at - SYNC_LOOKBACK:
                continue
            lag = (tap_at - wall).total_seconds()
            raw = lag + SYNC_PLAY_SECONDS - fast
            suggested = max(0, min(SYNC_MAX_DELAY, int(-(-max(0.0, raw) // 5) * 5)))
            out["candidates"].append({
                "id": data.get("id"),
                "period": data.get("period"),
                "clock": data.get("clock"),
                "offense": data.get("offense"),
                "down": data.get("down"),
                "distance": data.get("distance"),
                "yardsToGoal": data.get("yardsToGoal"),
                "tvLagSeconds": round(lag, 1),
                "suggestedDelay": suggested,
            })
            if len(out["candidates"]) >= 3:
                break
        if not out["candidates"]:
            out["note"] = "Waiting for that snap to reach the feed (usually under a minute)."
        return out

    def poll_interval(self) -> int:
        """The wait before the next live poll: the backoff after a failure, 30 s at halftime, else the setting."""
        return self._backoff or (HALFTIME_POLL_SECONDS if self._halftime else self.settings.live_poll_seconds)

    def feed_health(self, now: datetime | None = None) -> dict[str, Any]:
        """Contract C1: whether the live feed is answering, for the status line on every device."""
        now = now or self._clock()
        window = self.window
        threshold = max(FEED_STALE_MIN_SECONDS, FEED_STALE_INTERVALS * self.poll_interval())
        success_at, new_event_at = self._success_at, self._new_event_at
        if self.mode != "replay" and window is not None:
            # Nothing from before this window opened counts: the loop opens the window up to a
            # schedule check after opens_at, and last week's answers must not read as a stale feed.
            success_at = success_at if success_at is not None and success_at >= window.opens_at else None
            new_event_at = new_event_at if new_event_at is not None and new_event_at >= window.opens_at else None
        stale_seconds: int | None = None
        if self.mode == "replay":
            state = "ok"
        elif window is None or not window.contains(now):
            state = "idle"
        elif not self.client.capabilities.live_plays:
            state = "no_live_key"
        elif success_at is None:
            state = "waiting"
        else:
            age = max(0.0, (now - success_at).total_seconds())
            state = "stale" if age > threshold else "ok"
            stale_seconds = int(age) if state == "stale" else None
        return {
            "state": state,
            "lastSuccessAt": _iso(success_at),
            "lastNewEventAt": _iso(new_event_at),
            "consecutiveFailures": self.stats.consecutive_failures,
            "lastError": self._feed_error,
            "staleSeconds": stale_seconds,
            "checkedAt": _iso(now),
        }

    def _window_status(self, window: GameWindow, now: datetime) -> dict[str, Any]:
        live_view_at = window.kickoff - LIVE_VIEW_BEFORE
        return {
            "gameId": window.game_id,
            "kickoff": window.kickoff.isoformat(),
            "opensAt": window.opens_at.isoformat(),
            "closesAt": window.closes_at.isoformat(),
            "open": window.contains(now),
            "liveView": live_view_at <= now <= window.closes_at,
            "liveViewAt": live_view_at.isoformat(),
            "extended": window.closes_at > window.kickoff + WINDOW_AFTER,
        }

    def status(self) -> dict[str, Any]:
        window = self.window
        now = self._clock()
        return {
            "mode": self.mode,
            "gameId": self.current_game_id,
            "home": self.home,
            "away": self.away,
            "window": self._window_status(window, now) if window else None,
            "feed": self.feed_health(now),
            "clientsConnected": self.clients_connected(),
            "livePlaysAvailable": bool(self.client.capabilities.live_plays),
            "pollSeconds": self.settings.live_poll_seconds,
            "projectedCallsPerGame": round(3.5 * 3600 / self.settings.live_poll_seconds),
            "replay": self.replay.as_dict(),
            "stats": {**self.stats.__dict__, "eventsStored": self.store.count(self.store_key(self.current_game_id)) if self.current_game_id else 0},
        }

    # --- bookkeeping -------------------------------------------------------------------------------

    def _note_error(self, message: str) -> None:
        self.stats.last_error = message
        self.stats.last_error_at = _iso(self._clock())

    def _poll_failed(self, message: str) -> None:
        self.stats.poll_failures += 1
        self.stats.consecutive_failures += 1
        self._feed_error = message
        self._note_error(message)

    def _poll_succeeded(self, now: datetime) -> None:
        """A parsed answer: the feed is healthy again, so its error goes (stats.last_error keeps it for the log view)."""
        self.stats.consecutive_failures = 0
        self._success_at = now
        self._feed_error = None
        self.stats.last_success_at = _iso(now)

    def _reset_feed(self) -> None:
        """The feed health starts from nothing in each window: no success, no new event, no error."""
        self._success_at = None
        self._new_event_at = None
        self._feed_error = None
        self.stats.last_success_at = None
        self.stats.last_new_event_at = None
        self.stats.consecutive_failures = 0

    def _set_settle_until(self, value: datetime) -> None:
        """Contract C4: until this time the client caches finished-game answers for an hour, not for good."""
        if getattr(self.client, "settle_until", None) != value:
            self.client.settle_until = value
            log.info("Finished-game answers are cached for an hour, not for good, until %s", _iso(value))

    def _last_status(self, game_id: int) -> str | None:
        data = self.store.latest(game_id, "status")
        value = data.get("status") if data else None
        return value if isinstance(value, str) else None

    def _in_progress_with_plays(self, game_id: int) -> bool:
        """The stored status says the game is on and at least one play is stored. A feed that never
        produced a play (a postponed game's document, say) is not a game in progress."""
        return self._last_status(game_id) == "in_progress" and self.store.count_kind(game_id, "play") > 0

    def _called_off(self) -> bool:
        """CFBD's own status text in this window says postponed, canceled or forfeited."""
        raw = (self._last_raw_status or "").lower()
        return any(word in raw for word in CALLED_OFF_WORDS)

    async def _still_on(self, game_id: int) -> bool:
        return not self._called_off() and await asyncio.to_thread(self._in_progress_with_plays, game_id)

    def _complete_archive(self, game_id: int) -> bool:
        """An archive written at the final is on disk (older files without the flag were all written there)."""
        path = self.archive_dir / f"{game_id}.json"
        if not path.is_file():
            return False
        try:
            body = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            log.warning("Archive for game %s is unreadable (%s); it may be replaced", game_id, exc)
            return False
        return isinstance(body, dict) and body.get("partial") is not True

    # --- recording ------------------------------------------------------------------------------------

    def _record_meta(self, game_id: int) -> dict[str, Any]:
        window = self.window
        if window is not None and window.game_id == game_id:
            return {"gameId": game_id, "home": window.home, "away": window.away, "week": window.week, "kickoff": window.kickoff.isoformat()}
        return {"gameId": game_id}

    async def _record_raw(self, game_id: int, now: datetime, kind: str, payload: Any) -> None:
        """Hand one raw answer to the recorder in a worker thread. Never raises into the caller."""
        try:
            await asyncio.to_thread(self.recorder.write, game_id, now, kind, payload, self._record_meta(game_id))
        except RuntimeError as exc:  # the worker pool is shutting down with the server
            log.warning("Could not record the %s answer for game %s: %s", kind, game_id, exc)
        self.stats.recorded_files = self.recorder.files

    async def record_scoreboard(self, payload: Any) -> None:
        """The ticker's fresh /scoreboard answer, kept with the recording while a window is open. Its
        entry for the game carries CFBD's in-game win probability (L8, Phase 11), stored as a
        wp event so the spoiler delay holds it back like a play."""
        window = self.window
        now = self._clock()
        if self.mode == "replay" or window is None or not window.contains(now):
            return
        await self._record_raw(window.game_id, now, "scoreboard", payload)
        self._scoreboard_at = now
        games = parse_records(ScoreboardGame, payload, context="live/scoreboard").records
        entry = next((g for g in games if g.id == window.game_id), None)
        event = wp_event(entry, now) if entry is not None else None
        if event is not None:
            await self._publish_safely([event], "win probability")

    # --- the game window -------------------------------------------------------------------------------

    def _local(self, iso: str | None) -> datetime | None:
        if not iso:
            return None
        try:
            return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(timezone.utc)
        except ValueError:
            return None

    async def find_window(self, max_age: timedelta | None = None) -> GameWindow | None:
        """Our next game whose window is open now or opens later, from the cached schedule
        (no older than `max_age` when given). Also sets the client's settle time from the most
        recent kickoff within the past day, so it survives a restart (contract C4)."""
        try:
            fetched = await self.client.get("/games", {"year": self.settings.season, "team": self.settings.team}, kind=DataKind.SCHEDULE, max_age=max_age)
        except (QuotaBlocked, CfbdError) as exc:
            log.warning("Live window check could not read the schedule: %s", exc)
            return self.window
        parsed = parse_records(Game, fetched.payload, context="live/schedule")
        now = self._clock()
        today = now.astimezone(self.settings.tzinfo).date()
        # Any day we play is game day for the cache (a Friday game, a bowl), not only Saturdays (Phase 12).
        self.client.game_day = any((k := self._local(g.start_date)) is not None and k.astimezone(self.settings.tzinfo).date() == today for g in parsed.records)
        candidates = []
        recent: datetime | None = None
        for game in parsed.records:
            kickoff = self._local(game.start_date)
            if kickoff is None:
                continue
            if now - SETTLE_AFTER <= kickoff <= now and (recent is None or kickoff > recent):
                recent = kickoff
            if game.completed or game.id in self._done_games:
                continue
            if game.start_time_tbd:
                if game.id not in self._tbd_logged and now <= kickoff + WINDOW_AFTER:
                    self._tbd_logged.add(game.id)
                    log.info("Game %s (%s at %s) has no kickoff time yet (TBD); no live window until CFBD sets one", game.id, game.away_team, game.home_team)
                continue
            window = GameWindow(game.id, game.home_team, game.away_team, game.week, kickoff, kickoff - WINDOW_BEFORE, kickoff + WINDOW_AFTER, game.season_type)
            if window.closes_at < now <= window.cap and await asyncio.to_thread(self._in_progress_with_plays, game.id):
                window.closes_at = min(window.cap, now + WINDOW_EXTEND_STEP)  # a restart during a long game: the stored status still says it is on
            if window.closes_at >= now:
                candidates.append(window)
        if recent is not None:
            self._set_settle_until(recent + SETTLE_AFTER)
        candidates.sort(key=lambda w: w.kickoff)
        return candidates[0] if candidates else None

    def _open_window(self, window: GameWindow) -> None:
        self._replay_key_for = None  # a real game: the store keys are the real ids again
        self.mode = "live"
        self.current_game_id, self.home, self.away = window.game_id, window.home, window.away
        self.client.live_window = True
        self._backoff = 0
        self._halftime = False
        self._final_seen = False
        self._last_box_poll = None
        self._reset_feed()
        self._probes = set()
        self._box_missing_warned = False
        self._extension_warned = False
        self._last_raw_status = None
        self._check_poll_at = None
        self._scoreboard_at = None
        self._set_settle_until(window.kickoff + SETTLE_AFTER)
        log.info("Live window open for game %s (%s at %s)", window.game_id, window.away, window.home)

    async def _extend_if_in_progress(self, window: GameWindow, now: datetime) -> None:
        """Past the planned close with the game still on: keep polling, up to the ten-hour cap. Only a
        game with stored plays whose status CFBD does not call postponed, canceled or forfeited
        stretches the window. With nobody watching, a look at the feed that ignores the client gate
        comes first (then one every half hour at most), so a final that CFBD posts after the last
        client left closes the window and writes the archive now, not at the cap."""
        if window.closes_at >= window.cap or not await self._still_on(window.game_id):
            return
        if not self.clients_connected() and self.client.capabilities.live_plays and (self._check_poll_at is None or now - self._check_poll_at >= CHECK_POLL_SPACING):
            self._check_poll_at = now
            try:
                await self.poll_once(window, closing=True)
            except (QuotaBlocked, CfbdError) as exc:  # poll_once counted and logged it; the stored status decides
                log.info("The check on game %s past the planned close failed (%s); the stored status stands", window.game_id, exc)
            if self._final_seen or not await self._still_on(window.game_id):
                return  # the final closes the window with its archive; anything else closes it now
        window.closes_at = min(window.cap, now + WINDOW_EXTEND_STEP)
        if not self._extension_warned:
            self._extension_warned = True
            log.warning("Game %s is still in progress %.1f hours after kickoff; the live window stays open (at most until %s)", window.game_id, (now - window.kickoff).total_seconds() / 3600, _iso(window.cap))

    async def _close_window(self, window: GameWindow) -> None:
        """The window is over. Without a final, one last look at the feed first; whatever happens
        there, the window closes."""
        try:
            if not self._final_seen:
                await self._finish_without_final(window)
        finally:
            log.info("Live window for game %s closed", window.game_id)
            if self._final_seen or self.store.count_kind(window.game_id, "play"):
                self._done_games.add(window.game_id)  # a window with no play and no final (a moved kickoff) may open again
            self.window = None
            self._final_seen = False
            self._halftime = False
            self._backoff = 0
            self._reset_feed()  # the next window's feed starts at waiting, never stale from this game
            self.mode = "idle"
            self.client.live_window = False

    def _final_already_archived(self, game_id: int) -> bool:
        return self._last_status(game_id) == "final" and self._complete_archive(game_id)

    async def _finish_without_final(self, window: GameWindow) -> None:
        """One /live/plays call that ignores the connected-client gate: a final writes the archive
        as usual, anything else writes it marked partial. A game with no stored plays is left alone,
        and so is one whose final was already archived (a restart reopened its window)."""
        game_id = window.game_id
        if not await asyncio.to_thread(self.store.count_kind, game_id, "play"):
            log.info("Live window for game %s closed with no stored plays (last status %r); no archive", game_id, self._last_raw_status)
            return
        if await asyncio.to_thread(self._final_already_archived, game_id):
            log.info("Live window for game %s closed; its final is already archived", game_id)
            return
        reason: str | None = None
        # A check that ran past the planned close in this same pass (nobody watching) was the last look; one call is enough.
        just_checked = self._check_poll_at is not None and self._check_poll_at > window.closes_at
        if not self.client.capabilities.live_plays:
            reason = "the key had no live plays when the window closed"
        elif not just_checked:
            try:
                await self.poll_once(window, closing=True)
            except (QuotaBlocked, CfbdError) as exc:
                reason = f"the closing poll failed: {exc}"
            except Exception as exc:  # noqa: BLE001 - logged with its traceback; the partial archive still goes out
                log.exception("The closing poll for game %s hit an unexpected error", window.game_id)
                reason = f"the closing poll failed: {exc.__class__.__name__}"
            if self._final_seen:
                return  # the archive was written at the final like any other game
        if reason is None:
            last = self._last_raw_status or await asyncio.to_thread(self._last_status, window.game_id)
            reason = f"no final from CFBD when the window closed at {_iso(window.closes_at)} (last status {last or 'unknown'})"
        reason = reason[:CLOSE_REASON_MAX]
        log.warning("Game %s closed without a final; writing a partial archive: %s", window.game_id, reason)
        await asyncio.to_thread(self.write_archive, window, None, partial=True, partial_reason=reason)

    # --- polling -------------------------------------------------------------------------------------

    async def poll_once(self, window: GameWindow, *, closing: bool = False) -> list[LiveEvent]:
        """One live call: record the raw answer, normalize, store; then the box score when it is due,
        the two in-game win probability probes, and the archive at the final. Raises QuotaBlocked or
        CfbdError when the call fails. `closing` is a look past the planned close that ignores the
        client gate (the check while nobody watches, or the last look at the close): nothing but the
        final's own calls follow it."""
        now = self._clock()
        self.stats.polls += 1
        self.stats.last_poll_at = now.isoformat(timespec="seconds")
        try:
            fetched = await self.client.get("/live/plays", {"gameId": window.game_id}, kind=DataKind.LIVE, live=True, use_cache=False)
        except (QuotaBlocked, CfbdError) as exc:
            self._poll_failed(str(exc))
            log.warning("Live poll failed (%d in a row): %s", self.stats.consecutive_failures, exc)
            raise
        await self._record_raw(window.game_id, now, "plays", fetched.payload)
        game = parse_one(LiveGame, fetched.payload, context="live/plays")
        if game is None or game.id != window.game_id:
            problem = f"live answer was not a game document ({_shape(fetched.payload)})" if game is None else f"live answer was for game {game.id}, not {window.game_id}"
            self._poll_failed(problem)
            log.warning("Live poll unusable (%d in a row): %s", self.stats.consecutive_failures, problem)
            return []
        self._poll_succeeded(now)
        self._last_raw_status = game.status if isinstance(game.status, str) else None
        events = events_from_live(game, now)
        stored = await self._publish_safely(events, "live")
        if stored is None:
            return []
        status = next((e.data for e in events if e.kind == "status"), {})
        final = status.get("status") == "final"
        raw_status = game.status if isinstance(game.status, str) else ""
        self._halftime = not final and ((status.get("period") == 2 and clock_dict(status.get("clock")) == {"minutes": 0, "seconds": 0}) or "half" in raw_status.lower())
        if not final and not closing:
            if self._halftime and "halftime" not in self._probes:
                await self._probe_win_probability(window, "halftime")
            period = status.get("period")
            if isinstance(period, int) and not isinstance(period, bool) and period >= 4 and "period4" not in self._probes:
                await self._probe_win_probability(window, "period4")
        if not closing:
            await self._load_rosters(window)
            await self._load_ep_tables()
            if not final:
                await self._poll_scoreboard(window, now)
        if final or (not closing and (self._last_box_poll is None or (now - self._last_box_poll).total_seconds() >= BOX_POLL_SECONDS)):
            stored += await self.poll_box(window, final=final)
        if final and not self._final_seen:
            self._final_seen = True
            win_probability = await self.fetch_win_probability(window.game_id)
            await asyncio.to_thread(self.write_archive, window, win_probability)
        return stored

    async def _poll_scoreboard(self, window: GameWindow, now: datetime) -> None:
        """The in-game win probability does not wait for the Live sheet's ticker: when no fresh
        scoreboard came in for a minute, the engine reads it (the same 15-second cache the ticker
        uses, so the two never bill twice for one answer). A failure is a warning; the play poll goes on."""
        if not self.client.capabilities.scoreboard:
            return
        if self._scoreboard_at is not None and (now - self._scoreboard_at).total_seconds() < SCOREBOARD_SECONDS:
            return
        try:
            fetched = await self.client.get("/scoreboard", {"classification": "fbs"}, kind=DataKind.SCOREBOARD, live=True)
        except (QuotaBlocked, CfbdError) as exc:
            log.warning("Scoreboard read for game %s failed: %s", window.game_id, exc)
            self._note_error(f"scoreboard: {exc}")
            self._scoreboard_at = now  # try again in a minute, not on every play poll
            return
        if fetched.source == "live":
            await self.record_scoreboard(fetched.payload)
        else:
            self._scoreboard_at = now  # the ticker's copy from under 15 s ago was already handed over

    async def _load_ep_tables(self) -> None:
        """CFBD's 1st-and-10 expected points and field-goal make chances for the fourth-down
        break-even, once per run (a week-long cache: about two calls a week). A failure leaves the
        fourth-down row out and is tried again on a later poll, at most every ten minutes."""
        if self._ep_tables.get("firstDown") and self._ep_tables.get("fieldGoal"):
            return
        now = self._clock()
        if self._ep_tried_at is not None and (now - self._ep_tried_at).total_seconds() < 600:
            return
        self._ep_tried_at = now
        try:
            first = await self.client.get("/ppa/predicted", {"down": "1", "distance": "10"}, kind=DataKind.REFERENCE)
            fg = await self.client.get("/metrics/fg/ep", {}, kind=DataKind.REFERENCE)
        except (QuotaBlocked, CfbdError) as exc:
            log.warning("Expected points tables unavailable (%s); the fourth-down row waits", exc)
            return
        self._ep_tables = {
            "firstDown": ep_table(parse_records(PredictedPoints, first.payload, context="live/ep").records),
            "fieldGoal": fg_table(parse_records(FieldGoalEp, fg.payload, context="live/fg").records),
        }

    async def _load_rosters(self, window: GameWindow) -> None:
        """Both teams' rosters by jersey, once per window, for naming the play-by-play lines. From
        the week-long roster cache (the Game program has usually read both already). A team whose
        roster fails keeps short names until the next window."""
        if self._rosters_for == window.game_id:
            return
        self._rosters_for = window.game_id
        self._rosters = {}
        for team in (window.home, window.away):
            if not team:
                continue
            try:
                fetched = await self.client.get("/roster", {"team": team, "year": self.settings.season}, kind=DataKind.ROSTER)
            except (QuotaBlocked, CfbdError) as exc:
                log.warning("Roster for %s unavailable (%s); its play-by-play lines keep short names", team, exc)
                continue
            by_jersey: dict[int, list[dict[str, str]]] = {}
            for player in parse_records(RosterPlayer, fetched.payload, context=f"live/roster {team}").records:
                if isinstance(player.jersey, int) and not isinstance(player.jersey, bool) and player.id:
                    by_jersey.setdefault(player.jersey, []).append({"id": str(player.id), "first": player.first_name or "", "last": player.last_name or ""})
            self._rosters[team] = by_jersey

    async def _snapshot(self, window: GameWindow) -> None:
        """For finding bugs after the game (added on the game night of 2026-09-26): once a minute a line with
        what the Live sheet shows at no delay (score, clock, down, the plays and drives stored, the
        feed's health, viewers, quota) goes to the log under kickoff.live.snapshot, and every five
        minutes the derived state itself, minus the play and drive lists, which the raw recordings
        already hold, is saved beside them as state-<time>.json. Never raises into the poll loop."""
        now = self._clock()
        if self._snapshot_at is not None and (now - self._snapshot_at).total_seconds() < SNAPSHOT_SECONDS:
            return
        self._snapshot_at = now
        try:
            state = await asyncio.to_thread(self.state, 0, window.game_id)
        except Exception:  # noqa: BLE001 - a snapshot must never stop the game; logged with its traceback
            log.exception("Could not derive the state for the game snapshot")
            return
        if not state:
            return
        feed = self.feed_health(now)
        try:
            used = self.client.quota.status(now).used
        except Exception:  # noqa: BLE001 - the quota readout is decoration here
            used = None
        clock = state.get("clock") if isinstance(state.get("clock"), dict) else {}
        boxes = state.get("box") if isinstance(state.get("box"), dict) else {}
        sides = []
        for team in (window.away, window.home):
            b = boxes.get(team) or {}
            sides.append(f"{team} {b.get('points')} pts {b.get('totalYards')} yds ({b.get('netPassingYards')} pass, {b.get('rushingYards')} rush) {b.get('plays')} plays")
        snap_log.info(
            "game %s %s Q%s %s:%02d %s %s-%s | %s | down %s & %s at %s, ball %s | %s plays, %s drives, %s events | feed %s (last answer %s, %s failures) | viewers %s | player lines %s | quota used %s",
            window.game_id, state.get("status"), state.get("period"), clock.get("minutes", 0) if isinstance(clock.get("minutes"), int) else 0, clock.get("seconds", 0) if isinstance(clock.get("seconds"), int) else 0,
            window.away, state.get("awayScore"), state.get("homeScore"), " / ".join(sides),
            state.get("down"), state.get("distance"), state.get("yardsToGoal"), state.get("possession"),
            (state.get("counts") or {}).get("plays"), (state.get("counts") or {}).get("drives"), (state.get("counts") or {}).get("events"),
            feed.get("state"), feed.get("lastSuccessAt"), feed.get("consecutiveFailures"), len(self._subscribers),
            state.get("playerStatsSource"), used,
        )
        if self._state_recorded_at is None or (now - self._state_recorded_at).total_seconds() >= STATE_RECORD_SECONDS:
            self._state_recorded_at = now
            slim = {k: v for k, v in state.items() if k not in ("plays", "drives")}
            await self._record_raw(window.game_id, now, "state", slim)

    async def _box_answer(self, window: GameWindow, endpoint: str, kind: str, params: dict[str, Any], final: bool) -> Any:
        """One box-score endpoint, recorded. None when the call fails; the other endpoint and the play poll go on."""
        now = self._clock()
        try:
            fetched = await self.client.get(endpoint, params, kind=DataKind.FINISHED_GAME, live=True, use_cache=final)
        except (QuotaBlocked, CfbdError) as exc:
            log.warning("Box poll %s failed: %s", endpoint, exc)
            self._note_error(f"box: {exc}")
            return None
        await self._record_raw(window.game_id, now, kind, fetched.payload)
        return fetched.payload

    async def poll_box(self, window: GameWindow, *, final: bool = False) -> list[LiveEvent]:
        """The team box and player lines from the box-score endpoints. Live values while the game runs,
        the permanent answer once it is final. A failure here never stops the play poll."""
        if window.week is None:
            return []
        self._last_box_poll = self._clock()
        # A bowl is asked for by id: CFBD's postseason is one "week 1" that holds every bowl (Phase 15).
        params: dict[str, Any] = {"id": window.game_id} if window.season_type == gamekeys.POSTSEASON else {"year": self.settings.season, "week": window.week, "team": self.settings.team}
        teams_payload = await self._box_answer(window, "/games/teams", "box-teams", params, final)
        players_payload = await self._box_answer(window, "/games/players", "box-players", params, final)
        teams = parse_records(GameTeamStats, teams_payload, context="live/box").records if teams_payload is not None else []
        players = parse_records(GamePlayerStats, players_payload, context="live/players").records if players_payload is not None else []
        if teams_payload is not None:
            if any(t.id == window.game_id for t in teams):
                if self._box_missing_warned:
                    log.info("The /games/teams answer includes game %s again", window.game_id)
                self._box_missing_warned = False
            elif not self._box_missing_warned:
                self._box_missing_warned = True
                log.warning("The /games/teams answer (%s) does not include game %s; the box score waits for it", _shape(teams_payload), window.game_id)
        events = box_events(window.game_id, teams, players, self._clock())
        if not events:
            return []
        return await self._publish_safely(events, "box") or []

    async def _probe_win_probability(self, window: GameWindow, reason: str) -> None:
        """One uncached /metrics/wp call at halftime and one at the start of the fourth quarter, recorded
        to learn whether CFBD posts in-game win probability. Nothing reads the answer yet."""
        self._probes.add(reason)
        now = self._clock()
        try:
            fetched = await self.client.get("/metrics/wp", {"gameId": window.game_id}, kind=DataKind.FINISHED_GAME, live=True, use_cache=False)
        except (QuotaBlocked, CfbdError) as exc:
            log.warning("In-game win probability probe (%s) failed for game %s: %s", reason, window.game_id, exc)
            self._note_error(f"wp probe: {exc}")
            return
        await self._record_raw(window.game_id, now, "wp-probe", fetched.payload)
        log.info("In-game win probability probe (%s) for game %s answered with %s", reason, window.game_id, _shape(fetched.payload))

    async def fetch_win_probability(self, game_id: int) -> list[dict[str, Any]] | None:
        """L8 after the final: CFBD's play-by-play win probability for the archive. One uncached call so
        an empty early answer is never remembered; None when it is not posted yet or the call fails."""
        now = self._clock()
        try:
            fetched = await self.client.get("/metrics/wp", {"gameId": game_id}, kind=DataKind.FINISHED_GAME, live=True, use_cache=False)
        except (QuotaBlocked, CfbdError) as exc:
            log.warning("Win probability fetch failed for game %s: %s", game_id, exc)
            self._note_error(f"wp: {exc}")
            return None
        await self._record_raw(game_id, now, "wp", fetched.payload)
        series = wp_series(parse_records(PlayWinProbability, fetched.payload, context="live/wp").records)
        return series or None

    def write_archive(self, window: GameWindow, win_probability: list[dict[str, Any]] | None = None, *, partial: bool = False, partial_reason: str | None = None) -> Path | None:
        """X5: the final state of a game this app watched, saved for the Archive. Only games the
        app recorded itself land here; nothing is back-filled. `partial` marks a game whose window
        closed before CFBD posted a final; it never replaces the complete archive of the same game.
        Written to a temporary file first, then moved into place."""
        try:
            if partial and self._complete_archive(window.game_id):
                log.info("Game %s already has a complete archive; the partial one is not written over it", window.game_id)
                return self.archive_dir / f"{window.game_id}.json"
            events = self.store.released(window.game_id, self._clock())
            state = derive_state(events, game_id=window.game_id, home=window.home, away=window.away, mode="archive", rosters=self._rosters if self._rosters_for == window.game_id else None)
            self.archive_dir.mkdir(parents=True, exist_ok=True)
            path = self.archive_dir / f"{window.game_id}.json"
            body = {
                "gameId": window.game_id,
                "season": self.settings.season,
                "week": window.week,
                "seasonType": window.season_type or "regular",  # Phase 15
                "home": window.home,
                "away": window.away,
                "kickoff": window.kickoff.isoformat(),
                "savedAt": self._clock().isoformat(timespec="seconds"),
                "partial": bool(partial),
                "partialReason": partial_reason if partial else None,
                "winProbability": win_probability,
                "state": state,
            }
            temp = self.archive_dir / f"{window.game_id}.json.tmp"
            temp.write_text(json.dumps(body, separators=(",", ":")), encoding="utf-8")
            os.replace(temp, path)
            log.info("Archived game %s to %s%s", window.game_id, path.name, " (partial)" if partial else "")
            return path
        except (OSError, TypeError, ValueError) as exc:
            log.warning("Could not write the archive for game %s: %s", window.game_id, exc)
            self._note_error(f"archive: {exc}")
            return None

    async def _kickoff_recheck_due(self, now: datetime) -> bool:
        """An open window with no play stored yet re-reads the (cached) schedule once a minute, so a
        kickoff that moves or turns TBD before the game starts moves or closes the window."""
        window = self.window
        if window is None or self.mode != "live" or self._final_seen:
            return False
        if self._kickoff_checked_at is not None and (now - self._kickoff_checked_at).total_seconds() < SCHEDULE_CHECK_SECONDS:
            return False
        self._kickoff_checked_at = now
        return not await asyncio.to_thread(self.store.count_kind, window.game_id, "play")

    @staticmethod
    def _schedule_wait(window: GameWindow | None, now: datetime) -> float:
        """The wait before the next schedule check: a minute, or less when the window opens sooner,
        so the window opens and polling starts at opens_at, not up to a minute after it."""
        if window is not None and window.opens_at > now:
            return max(1.0, min(float(SCHEDULE_CHECK_SECONDS), (window.opens_at - now).total_seconds()))
        return float(SCHEDULE_CHECK_SECONDS)

    async def run(self) -> None:
        """The background loop: watch the schedule, poll inside the window while someone is watching."""
        while True:
            try:
                now = self._clock()
                if self.mode == "replay":
                    window = self.window
                    if window is None or not window.contains(now):
                        await self._sleep(1)
                        continue
                    log.warning("The live window for game %s opened during a replay; the replay stops so the real game comes first", window.game_id)
                    await self.stop_replay()
                window = self.window
                if window is not None and not self._final_seen and now > window.closes_at:
                    await self._extend_if_in_progress(window, now)
                if window is not None and (self._final_seen or now > window.closes_at):
                    await self._close_window(window)
                if self.window is None or not self.window.contains(now):
                    self.window = await self.find_window()  # re-read while waiting, so a moved kickoff moves the window
                elif await self._kickoff_recheck_due(now):
                    self.window = await self.find_window(KICKOFF_RECHECK_MAX_AGE)
                window = self.window
                if window is None or not window.contains(now):
                    if self.mode == "live":
                        self.mode = "idle"
                        self.client.live_window = False
                    await self._sleep(self._schedule_wait(window, now))
                    continue
                if self.mode != "live":
                    self._open_window(window)
                if not self.client.capabilities.live_plays:
                    await self._sleep(SCHEDULE_CHECK_SECONDS)
                    continue
                if not self.clients_connected():
                    await self._sleep(CLIENT_WAIT_SECONDS)
                    continue
                try:
                    await self.poll_once(window)
                    self._backoff = 0
                except (QuotaBlocked, CfbdError):
                    self._backoff = min(MAX_BACKOFF_SECONDS, self._backoff * 2 if self._backoff else self.settings.live_poll_seconds * 2)
                await self._snapshot(window)
                if self._final_seen:
                    continue  # the next pass closes the window
                await self._sleep(self.poll_interval())
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - the loop must survive; the failure is logged
                log.exception("Live loop hit an unexpected error; continuing in %d s", SCHEDULE_CHECK_SECONDS)
                self._note_error("live loop: unexpected error, see the log")
                await self._sleep(SCHEDULE_CHECK_SECONDS)

    def start_background(self) -> None:
        if self._poll_task is None or self._poll_task.done():
            self._poll_task = asyncio.get_running_loop().create_task(self.run())

    async def stop_background(self) -> None:
        for task in (self._poll_task, self._replay_task):
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):  # noqa: BLE001 - shutting down
                    pass
        self.client.live_window = False

    # --- replay -------------------------------------------------------------------------------------------

    async def start_replay(self, game_id: int, speed: float = 30.0, source: str = "finished") -> ReplayStatus:
        if self._replay_task is not None and not self._replay_task.done():
            await self.stop_replay()
        speed = max(1.0, min(float(speed), 3600.0))
        self.replay = ReplayStatus(running=True, game_id=game_id, speed=speed, source=source, started_at=self._clock().isoformat(timespec="seconds"))
        self._replay_task = asyncio.get_running_loop().create_task(self._replay_run(game_id, speed, source))
        return self.replay

    async def stop_replay(self) -> ReplayStatus:
        task = self._replay_task
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001 - stopping is the point
                pass
        self.replay.running = False
        if self.mode == "replay":
            self.mode = "idle"
        return self.replay

    async def _load_finished(self, game_id: int) -> tuple[list[tuple[LiveEvent, str | None]], str | None, str | None]:
        schedule = await self.client.get("/games", {"year": self.settings.season, "team": self.settings.team}, kind=DataKind.SCHEDULE)
        games = parse_records(Game, schedule.payload, context="replay/schedule").records
        game = next((g for g in games if g.id == game_id), None)
        if game is None:
            raise ValueError(f"game {game_id} is not on the {self.settings.team} schedule")
        if not game.completed or game.week is None:
            raise ValueError(f"game {game_id} is not finished; only finished games replay")
        params = gamekeys.week_params(game, self.settings.season, self.settings.team)  # a bowl's answer holds all the team's bowls; filtered by game id below
        plays_fetched = await self.client.get("/plays", params, kind=DataKind.FINISHED_GAME)
        drives_fetched = await self.client.get("/drives", params, kind=DataKind.FINISHED_GAME)
        plays = [p for p in parse_records(Play, plays_fetched.payload, context="replay/plays").records if p.game_id in (None, game_id)]
        drives = [d for d in parse_records(Drive, drives_fetched.payload, context="replay/drives").records if d.game_id in (None, game_id)]
        if not plays:
            raise ValueError(f"no plays recorded for game {game_id}")
        return events_from_finished(game_id, plays, drives, game.home_team, game.away_team), game.home_team, game.away_team

    async def _replay_run(self, game_id: int, speed: float, source: str) -> None:
        try:
            key = -game_id  # the replay's own space: the game's real event log is never touched
            await asyncio.to_thread(self.store.clear, key)
            timeline, home, away = await self._load_finished(game_id)
            self._replay_key_for = game_id
            self.mode = "replay"
            self.current_game_id, self.home, self.away = game_id, home, away
            self.replay.total = len(timeline)
            await self.publish([LiveEvent("status", "status", key, self._clock(), status_from_scores(game_id, home, away, 0, 0, 1, {"minutes": 15, "seconds": 0}, None, None, None, None, "pre"))])
            previous_wall: datetime | None = None
            last_scores: tuple[int | None, int | None] = (0, 0)
            for event, wallclock in timeline:
                wall = self._local(wallclock)
                gap = REPLAY_DEFAULT_GAP_SECONDS
                if wall is not None and previous_wall is not None:
                    gap = max(0.0, min(REPLAY_MAX_GAP_SECONDS, (wall - previous_wall).total_seconds()))
                if wall is not None:
                    previous_wall = wall
                if event.kind == "play":
                    await self._sleep(gap / speed)
                event.received_at = self._clock()
                event.game_id = key
                await self.publish([event])
                self.replay.emitted += 1
                if event.kind == "play":
                    data = event.data
                    last_scores = (data.get("homeScore"), data.get("awayScore"))
                    await self.publish([LiveEvent("status", "status", key, self._clock(), status_from_scores(game_id, home, away, last_scores[0], last_scores[1], data.get("period"), data.get("clock"), data.get("offense"), data.get("down"), data.get("distance"), data.get("yardsToGoal"), "in_progress"))])
            await self.publish([LiveEvent("status", "status", key, self._clock(), status_from_scores(game_id, home, away, last_scores[0], last_scores[1], None, None, None, None, None, None, "final"))])
            self.replay.finished = True
            log.info("Replay of game %s finished: %d events", game_id, self.replay.emitted)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - reported on the replay status and logged
            log.exception("Replay of game %s failed", game_id)
            self.replay.error = f"{exc.__class__.__name__}: {exc}"
        finally:
            self.replay.running = False
            if self.mode == "replay":
                self.mode = "idle"
