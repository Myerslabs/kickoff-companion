"""Live routes: the delayed state, the Server-Sent Events stream with reconnect and a feed-health
ping, the replay controls, the engine status, and the Phase 6 debug page."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from app import shutdown as shutdown_signal
from app.api.envelope import envelope, error_response
from app.build import build_id
from app.config import STATIC_DIR
from app.live.engine import LiveEngine

router = APIRouter(tags=["live"])

PING_SECONDS = 15  # a ping with the feed health goes out whenever nothing else has for this long (contract C2)
PENDING_TICK_SECONDS = 1.0
MAX_DELAY = 120


def _delay(value: float) -> float:
    return max(0.0, min(float(value), MAX_DELAY))


def _sse(event: str, data: Any, event_id: int | None = None) -> str:
    head = f"id: {event_id}\n" if event_id is not None else ""
    return f"{head}event: {event}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n"


@router.get("/api/live/state")
async def live_state(request: Request, delay: float = Query(0, ge=0, le=MAX_DELAY)) -> Any:
    engine: LiveEngine = request.app.state.live
    engine.note_state_poll()
    state = await asyncio.to_thread(engine.state, _delay(delay))
    if state is None:
        return envelope({"mode": engine.mode, "status": "idle", "engine": engine.status()}, source="live")
    state["engine"] = engine.status()
    return envelope(state, source="replay" if engine.mode == "replay" else "live")


@router.get("/api/live/sync")
async def live_sync(request: Request, tapAt: str | None = Query(None, max_length=40)) -> Any:  # noqa: N803 - the query name the browser sends
    """"Sync to my TV": without tapAt, stamps the tap with server time now; with it, the snaps that
    tap can mean and the delay each one suggests. Pre-snap facts only, never a play's result."""
    engine: LiveEngine = request.app.state.live
    if tapAt is None:
        tap = engine._clock()
    else:
        try:
            tap = datetime.fromisoformat(tapAt.replace("Z", "+00:00"))
        except ValueError:
            return error_response(422, "bad_tap", "tapAt must be an ISO time from an earlier sync call")
        if tap.tzinfo is None:
            tap = tap.replace(tzinfo=timezone.utc)
    return envelope(await asyncio.to_thread(engine.sync, tap), source="live")


@router.get("/api/live/status")
async def live_status(request: Request) -> Any:
    engine: LiveEngine = request.app.state.live
    return envelope(engine.status(), source="live")


@router.get("/api/live/stream")
async def live_stream(request: Request, delay: float = Query(0, ge=0, le=MAX_DELAY), ttl: float = Query(0, ge=0, le=3600)) -> Any:
    """Server-Sent Events: `state` events carry the full delayed state; `id` is the last released seq.
    A reconnecting browser sends Last-Event-ID and gets what it missed. `hello` and `ping` carry the
    feed health (contract C1); a ping goes out whenever nothing else has for PING_SECONDS. `ttl` ends
    the stream after that many seconds (the browser reconnects on its own); 0 keeps it open."""
    engine: LiveEngine = request.app.state.live
    delay_seconds = _delay(delay)
    last_id = request.headers.get("last-event-id", "0")
    after_seq = int(last_id) if last_id.isdigit() else 0
    loop = asyncio.get_running_loop()
    ends_at = loop.time() + ttl if ttl else None

    async def generate():
        queue = engine.subscribe()
        try:
            yield _sse("hello", {"delaySeconds": delay_seconds, "mode": engine.mode, "gameId": engine.current_game_id, "feed": engine.feed_health(), "build": build_id()})
            last_sent = loop.time()
            sent_seq = after_seq
            while True:
                if await request.is_disconnected():
                    break
                if shutdown_signal.stopping():
                    yield "event: bye\ndata: {}\n\n"  # the browser reconnects on its own once the server is back
                    break
                if ends_at is not None and loop.time() >= ends_at:
                    yield "event: bye\ndata: {}\n\n"
                    break
                game_id = engine.current_game_id
                released = await asyncio.to_thread(engine.released_since, game_id, delay_seconds, sent_seq) if game_id else []
                if released:
                    sent_seq = max(e.seq or sent_seq for e in released)
                    state = await asyncio.to_thread(engine.state, delay_seconds)
                    if state is not None:
                        state["new"] = [e.id for e in released]
                        state["feed"] = engine.feed_health()  # a busy stream sends no pings, so every frame carries the feed health too
                        yield _sse("state", state, sent_seq)
                        last_sent = loop.time()
                    continue
                quiet_for = loop.time() - last_sent
                if quiet_for >= PING_SECONDS:
                    feed = engine.feed_health()
                    yield _sse("ping", {"feed": feed, "serverTime": feed["checkedAt"]})
                    last_sent = loop.time()
                    continue
                pending = bool(game_id) and await asyncio.to_thread(engine.pending, game_id, delay_seconds, sent_seq)
                wait = min(PENDING_TICK_SECONDS if pending else PING_SECONDS, PING_SECONDS - quiet_for)
                if ends_at is not None:
                    wait = min(wait, ends_at - loop.time())
                try:
                    await asyncio.wait_for(queue.get(), timeout=max(0.05, wait))
                except TimeoutError:
                    pass  # time to look again: a delayed event may be due, or a ping
        finally:
            engine.unsubscribe(queue)

    return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


class ReplayRequest(BaseModel):
    gameId: int = Field(gt=0)
    speed: float = Field(default=30.0, ge=1, le=3600)
    source: str = "finished"


@router.get("/api/live/replay")
async def replay_status(request: Request) -> Any:
    engine: LiveEngine = request.app.state.live
    return envelope(engine.replay.as_dict(), source="replay")


@router.post("/api/live/replay")
async def replay_start(body: ReplayRequest, request: Request) -> Any:
    engine: LiveEngine = request.app.state.live
    if engine.mode == "live" and engine.window is not None and engine.window.contains(engine._clock()):
        return error_response(409, "live_window_open", "A live game window is open; replay is refused so it cannot mix with real events.")
    status = await engine.start_replay(body.gameId, body.speed, body.source)
    return envelope(status.as_dict(), source="replay")


@router.delete("/api/live/replay")
async def replay_stop(request: Request) -> Any:
    engine: LiveEngine = request.app.state.live
    status = await engine.stop_replay()
    return envelope(status.as_dict(), source="replay")


@router.get("/debug/live", include_in_schema=False)
async def debug_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "debug-live.html", media_type="text/html", headers={"Cache-Control": "no-cache"})
