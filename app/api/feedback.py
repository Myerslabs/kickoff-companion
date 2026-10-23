"""Feedback with the logs, and the logs alone (owner 2026-10-23). Sending is open to every device, guests too (it changes
nothing shared); reading a report or a log is the host's, since a log says what everyone did.

    POST /api/feedback                 a report: kind, text, name, page, device, the tablet's trail; saved with the server
                                       log of the same window and the status snapshot (app/services/feedback.py)
    GET  /api/feedback                 the host's list, newest first
    GET  /api/feedback/{id}            one report with its trail, its log and its email (the sender's mail app sends it)
    GET  /api/feedback/{id}/zip        the report's folder as a zip
    GET  /api/logs/download            every log file and the status snapshot as a zip (About and help, the status page)
    GET  /api/logs/tail?lines=200      the log's last lines, for Copy
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Query, Request, Response
from pydantic import ValidationError

from app import APP_NAME, SUPPORT_EMAIL, __version__
from app.api.envelope import envelope, error_response
from app.guests import is_host
from app.services.feedback import FeedbackIn, FeedbackStore

router = APIRouter(tags=["feedback"])
log = logging.getLogger("kickoff.api.feedback")

def _store(request: Request) -> FeedbackStore:
    return request.app.state.feedback


def _host(request: Request) -> bool:
    return is_host(request.scope, getattr(request.app.state, "host_access", None))


def _refused() -> Any:
    return error_response(403, "host_only", "Feedback reports and logs open on the host's devices only: they say what everyone did.")


def snapshot(request: Request) -> dict[str, Any]:
    """What the status page shows, and the settings (no secret lives in them); each part on its own, so one that fails
    leaves a note instead of losing the report."""
    from app.api.health import health
    from app.api.settings import _payload

    out: dict[str, Any] = {"version": __version__}
    for name, build in (("health", lambda: health(request).get("data")), ("settings", lambda: _payload(request))):
        try:
            out[name] = build()
        except Exception as exc:  # noqa: BLE001 - a snapshot part that fails must not cost the report; it says why
            log.warning("The feedback snapshot's %s part failed: %s", name, exc)
            out[name] = {"error": f"{type(exc).__name__}: {exc}"}
    return out


def mail_of(request: Request, report_id: str) -> dict[str, str] | None:
    """The report as an email to the developer (owner 2026-10-23: like a crash reporter, from the sender's own mail app)."""
    store = _store(request)
    found = store.get(report_id)
    return store.mail(found, __version__, SUPPORT_EMAIL, APP_NAME) if found else None


@router.post("/api/feedback")
async def send(request: Request) -> Any:
    try:
        raw = await request.json()
    except ValueError:
        return error_response(400, "bad_json", "The report must be JSON.")
    try:
        report = FeedbackIn.model_validate(raw if isinstance(raw, dict) else {})
    except ValidationError as exc:
        first = exc.errors()[0] if exc.errors() else {}
        where = ".".join(str(p) for p in first.get("loc", ())) or "the report"
        return error_response(422, "bad_report", f"{where}: {first.get('msg', 'not valid')}")
    host = _host(request)
    try:
        saved = _store(request).save(report, snapshot(request), host=host)
    except OSError as exc:
        log.error("A feedback report could not be saved: %s", exc)
        return error_response(500, "not_saved", f"The report could not be saved on the server computer ({exc.strerror or exc}).")
    return envelope({**saved, "mail": mail_of(request, saved["id"]), "canDownload": host}, source="live")


@router.get("/api/feedback")
async def reports(request: Request) -> Any:
    if not _host(request):
        return _refused()
    return envelope(_store(request).list(), source="live")


@router.get("/api/feedback/{report_id}")
async def report(report_id: str, request: Request) -> Any:
    if not _host(request):
        return _refused()
    found = _store(request).get(report_id)
    if found is None:
        return error_response(404, "no_report", "No feedback report by that name.")
    return envelope({**found, "mail": _store(request).mail(found, __version__, SUPPORT_EMAIL, APP_NAME)}, source="live")


@router.get("/api/feedback/{report_id}/zip")
async def report_zip(report_id: str, request: Request) -> Any:
    if not _host(request):
        return _refused()
    data = _store(request).zip_bytes(report_id)
    if data is None:
        return error_response(404, "no_report", "No feedback report by that name.")
    return Response(data, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="feedback-{report_id}.zip"', "Cache-Control": "no-store"})


@router.get("/api/logs/download")
async def logs_download(request: Request) -> Any:
    if not _host(request):
        return _refused()
    store = _store(request)
    stamp = store.clock().strftime("%Y%m%d-%H%M")
    return Response(store.logs_zip(snapshot(request)), media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="kickoff-logs-{stamp}.zip"', "Cache-Control": "no-store"})


@router.get("/api/logs/tail")
async def logs_tail(request: Request, lines: int = Query(default=200, ge=1, le=2000)) -> Any:
    if not _host(request):
        return _refused()
    return envelope({"text": _store(request).tail(lines), "lines": lines}, source="live")
