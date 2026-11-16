"""Circle of Blame (FEAT-18): the weekly job's reports, read back (no CFBD call, no Claude call of its own).

GET  /api/blame/now                              the page's one answer: the latest report, the season strip, the weeks, the
                                                 last run, whether this device may Regenerate; with no report yet,
                                                 `available` false and the words why (never an error page)
GET  /api/blame/{season}/weeks                   [{key, week, label, opponent, result}] in order
GET  /api/blame/{season}/history                 each week's slices and its top one, for the season strip
GET  /api/blame/{season}/{week}                  one report ("week-9", "post-1", or 9), its headlines and how it was made
POST /api/blame/{season}/{week}/regenerate       the host's only ({"confirm": true}): the job again for the latest week,
                                                 forced; answers the run to poll at /api/jobs/runs/{id}

The raw output Claude Code gave stays on disk (data/season/<year>/blame/), never in an answer."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.api.envelope import envelope, error_response
from app.guests import is_host
from app.jobs import last_of, read_runs
from app.jobs.circle_of_blame import NAME
from app.jobs.weekly import JobBusy
from app.services.blame import BlameStore, history

router = APIRouter(tags=["blame"])
PUBLIC = ("season", "key", "week", "gameId", "label", "opponent", "home", "neutral", "score", "people", "generatedAt", "modelUsed", "promptVersion", "inputHash", "attempts", "durationMs", "status", "report", "headlines")


class RegenerateRequest(BaseModel):
    confirm: bool = False


def _store(request: Request, season: int) -> BlameStore:
    return BlameStore(request.app.state.settings.data_dir, season)


def _key(week: str) -> str:
    text = str(week).strip().lower()
    return f"week-{text}" if text.isdigit() else text


def _public(record: dict[str, Any]) -> dict[str, Any]:
    return {k: record.get(k) for k in PUBLIC}


def _runs(request: Request, season: int) -> dict[str, Any]:
    runs = read_runs(request.app.state.settings.data_dir)
    jobs = getattr(request.app.state, "jobs", None)
    current = getattr(jobs, "current", None) or {}
    return {"last": last_of(runs, NAME, season), "lastGood": last_of(runs, NAME, season, "ok"), "running": current.get("job") in (NAME, "weekly"), "runningId": current.get("id")}


def _why(season: int, runs: dict[str, Any]) -> tuple[str, bool]:
    last = runs.get("last") or {}
    if runs.get("running"):
        return "The Circle of Blame is being written now; it takes a few minutes.", False
    if last.get("status") == "skipped":
        return f"No Circle of Blame yet: {last.get('message')}.", False
    if last.get("status") == "failed":
        return f"The Circle of Blame for {season} is unavailable since {last.get('startedAt')}: {last.get('message')}", True
    return f"The Circle of Blame for {season} has not been written yet. The server writes it Sundays from 6 AM, after our game.", False


def _weeks(records: list[tuple[str, dict[str, Any]]]) -> list[dict[str, Any]]:
    return [{"key": k, "week": r.get("week"), "label": r.get("label"), "opponent": r.get("opponent"), "result": (r.get("report") or {}).get("after_result")} for k, r in records]


@router.get("/api/blame/now")
async def now(request: Request) -> Any:
    season = request.app.state.settings.season
    store = _store(request, season)
    records = store.records()
    runs = _runs(request, season)
    host = is_host(request.scope, request.app.state.host_access)
    if not records:
        message, failed = _why(season, runs)
        return envelope({"available": False, "season": season, "message": message, "failed": failed, "runs": runs, "canRegenerate": host}, source="cache")
    key, latest = records[-1]
    failure = store.load_failure(key)
    return envelope({
        "available": True,
        "season": season,
        "ourTeam": request.app.state.settings.team,
        "latest": _public(latest),
        "weeks": _weeks(records),
        "history": history(records),
        "runs": runs,
        "lastFailure": {"at": failure.get("at"), "attempts": len(failure.get("attempts") or [])} if failure and (failure.get("at") or "") > (latest.get("generatedAt") or "") else None,
        "canRegenerate": host,
    }, source="cache")


@router.get("/api/blame/{season}/weeks")
async def weeks(request: Request, season: int) -> Any:
    return envelope({"season": season, "weeks": _weeks(_store(request, season).records())}, source="cache")


@router.get("/api/blame/{season}/history")
async def season_history(request: Request, season: int) -> Any:
    return envelope({"season": season, "history": history(_store(request, season).records())}, source="cache")


@router.get("/api/blame/{season}/{week}")
async def one_week(request: Request, season: int, week: str) -> Any:
    store = _store(request, season)
    record = store.load(_key(week))
    if record is None:
        known = [k for k, _r in store.records()]
        return JSONResponse(status_code=404, content=envelope({"weeks": known}, errors=[{"code": "not_found", "message": f"No Circle of Blame for {season} {week}." + (f" Written: {', '.join(known)}." if known else " None is written yet.")}]))
    return envelope(_public(record), source="cache")


@router.post("/api/blame/{season}/{week}/regenerate")
async def regenerate(request: Request, season: int, week: str, body: RegenerateRequest) -> Any:
    if not is_host(request.scope, request.app.state.host_access):
        return error_response(403, "view_only", "Only the host can write the Circle of Blame again.")
    if not body.confirm:
        return error_response(422, "confirm", "Confirm the run.")
    if season != request.app.state.settings.season:
        return error_response(422, "season", f"Only {request.app.state.settings.season}'s latest week can be written again.")
    latest = _store(request, season).latest()
    if latest is not None and _key(week) != latest[0]:
        return error_response(422, "week", f"Only the latest week ({latest[0]}) can be written again; the job always writes our latest final.")
    try:
        run = request.app.state.jobs.start(NAME, force=True)
    except JobBusy as exc:
        busy = exc.args[0] if exc.args and isinstance(exc.args[0], dict) else {}
        return JSONResponse(status_code=409, content=envelope({"running": busy}, errors=[{"code": "busy", "message": f"{busy.get('job', 'Another job')} is running (started {busy.get('startedAt')})."}]))
    return envelope({"run": run}, source="live")
