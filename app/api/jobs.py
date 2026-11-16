"""The weekly jobs (Feature Set v2): their last runs, one run by id, and a run started by hand.

GET  /api/jobs                    every job's last run, the one running, the schedule
GET  /api/jobs/runs/{run_id}      one run (the command line follows a run with it)
POST /api/jobs/{name}/run         {"confirm": true}: start "weekly" or one job; 409 while another runs

Starting a run is a change, so a guest's device is refused (app/guests.py), like every change."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.api.envelope import envelope, error_response
from app.jobs.weekly import JobBusy

router = APIRouter(tags=["jobs"])


class RunRequest(BaseModel):
    confirm: bool = False


@router.get("/api/jobs")
async def jobs(request: Request) -> Any:
    return envelope(request.app.state.jobs.status(), source="live")


@router.get("/api/jobs/runs/{run_id}")
async def one_run(run_id: str, request: Request) -> Any:
    run = request.app.state.jobs.runs.get(run_id[:80])
    if run is None:
        return error_response(404, "not_found", "No such run.")
    return envelope(run, source="live")


@router.post("/api/jobs/{name}/run")
async def start(name: str, body: RunRequest, request: Request) -> Any:
    runner = request.app.state.jobs
    if name not in runner.names():
        return error_response(404, "not_found", f"No job named {name[:40]}. The jobs: {', '.join(runner.names())}.")
    if not body.confirm:
        return error_response(422, "confirm", "Confirm the run.")
    try:
        run = runner.start(name)
    except JobBusy as exc:
        busy = exc.args[0] if exc.args and isinstance(exc.args[0], dict) else {}
        return JSONResponse(status_code=409, content=envelope({"running": busy}, errors=[{"code": "busy", "message": f"{busy.get('job', 'Another job')} is running (started {busy.get('startedAt')})."}]))
    return envelope({"run": run}, source="live")
