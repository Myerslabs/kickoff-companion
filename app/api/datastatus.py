"""The status pill's Data status (ENH-4, the owner's board of 2026-10-27): the server's view of each band on a page.

GET /api/datastatus?view=program&gameId=401856699&kickoff=2026-10-31T19:30:00Z
    {view, bands: [{band, changes, checks, dataFrom, due}], cadenceSeconds, cadence, pageSeconds,
     cfbd: {state, lastSuccessAt}, serverTime}

`pageSeconds` is how often the page itself asks the server (None: In Game's stream). No CFBD call: it reads the server's
own records (app/services/data_status.py). Guests may read it: it holds no setting and no key."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Request

from app.api.envelope import envelope
from app.services import data_status, season_notes
from app.services.notes import load_notes
from app.services.writing import WritingStore

router = APIRouter(tags=["status"])

STREAMED = {"live", "board"}  # the In Game stream: the page is told, it does not ask
EVERY_MINUTE = {"newspaper", "top25"}  # the pages with live matchups refresh each minute


def _cfbd_state(cfbd: Any) -> dict[str, Any]:
    if cfbd is None:
        return {"state": None, "lastSuccessAt": None}
    try:
        status = cfbd.status()
    except Exception:  # noqa: BLE001 - the card says "unknown" rather than break
        return {"state": None, "lastSuccessAt": None}
    breaker = status.get("breaker") if isinstance(status.get("breaker"), dict) else {}
    stats = status.get("stats") if isinstance(status.get("stats"), dict) else {}
    state = {"closed": "answering", "half_open": "testing", "open": "not answering"}.get(breaker.get("state"))
    return {"state": state, "lastSuccessAt": stats.get("last_success_at")}


@router.get("/api/datastatus")
async def datastatus(request: Request, view: str = "", gameId: str | None = None, kickoff: str | None = None) -> Any:
    state = request.app.state
    settings = state.settings
    cfbd = getattr(state, "cfbd", None)
    db = cfbd.cache.db if cfbd is not None else None
    now = cfbd._clock() if cfbd is not None else datetime.now(timezone.utc)
    game_id = gameId.strip() if isinstance(gameId, str) and gameId.strip().isdigit() else None
    notes, notes_saved = None, None
    if game_id:
        notes, _error = load_notes(settings.data_dir, game_id)
        notes_saved = data_status.file_time(settings.data_dir / "notes" / f"{game_id}.json")
    store = WritingStore(settings.data_dir, settings.season)
    written = {}
    for kind, key in (("scout", game_id), ("recap", game_id), ("paper", None), ("editor", None), ("art", None)):  # FEAT-14 wave 4: the editor, the drawings; the Post-Game stop: What decided it
        record = store.load(kind, key) if key else store.latest(kind)
        written[kind] = data_status.parse_time(record.get("writtenAt")) if isinstance(record, dict) else None
    engine = getattr(state, "live", None)
    live_at = None
    if engine is not None:
        try:
            feed = engine.status().get("feed") or {}
            live_at = data_status.parse_time(feed.get("lastSuccessAt"))
        except Exception:  # noqa: BLE001 - no live feed is not an error here
            live_at = None
    ticker = getattr(cfbd, "ticker_ttl", None) if cfbd is not None else None
    season_dir = settings.data_dir / "season" / str(settings.season)
    ctx = data_status.Context(
        now=now,
        tz=settings.tzinfo,
        game_day=bool(getattr(cfbd, "game_day", False)),
        live_seconds=int(settings.live_poll_seconds),
        ticker_seconds=int(ticker.total_seconds()) if ticker is not None else None,
        fetched=lambda endpoints: data_status.newest(db, "cache", "fetched_at", endpoints),
        changed=lambda endpoints: data_status.newest(db, "publications", "changed_at", endpoints),
        files={
            "headlines": data_status.feeds_time(settings.data_dir / "feeds"),
            "articles": state.articles.store.newest_copy() if getattr(state, "articles", None) is not None else None,  # FEAT-14
            "weather": data_status.newest_file(settings.data_dir / "weather"),
            "facts": data_status.file_time(settings.data_dir / "facts.json") or data_status.file_time(season_notes.SHIPPED_FACTS),
            "numbers": data_status.file_time(season_dir / "numbers.json"),
            "talent_edge": data_status.file_time(season_dir / "talent-edge.json"),  # FEAT-16
            "blame": data_status.newest_file(season_dir / "blame", "*.json", skip=("failed",)),  # FEAT-18
            "imperialism": data_status.file_time(season_dir / "imperialism.json"),  # FEAT-17
            "season_loads": data_status.newest_file(season_dir, "*.json", skip=("numbers", "talent-edge", "imperialism")),  # the jobs' files are not Claude's loads
        },
        notes=notes,
        notes_saved=notes_saved,
        kickoff=kickoff,
        writing=written,
        live_at=live_at,
    )
    name = view.strip().lower()
    answer = data_status.page_status(name, ctx)
    prefs = getattr(state, "prefs", None)
    minutes = getattr(getattr(prefs, "prefs", None), "refreshMinutes", 15)
    answer["pageSeconds"] = None if name in STREAMED else 60 if name in EVERY_MINUTE else int(minutes) * 60
    answer["cfbd"] = _cfbd_state(cfbd)
    answer["serverTime"] = data_status.iso_z(now)
    return envelope(answer, source="cache")
