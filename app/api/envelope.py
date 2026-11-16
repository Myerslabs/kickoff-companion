"""The response envelope every /api route returns.

    {
      "data": ...,
      "meta": {"fetched_at": "<ISO 8601 UTC>", "stale": false, "source": "live" | "cache" | "replay", "build": "<id>",
               "restartNeeded": false, "claudeSignedOut": null | "<ISO 8601 UTC>",
               "seasonSwitch": null | {"switched": {from, to, at}} | {"failed": {to, error}}},
      "errors": [{"code": "...", "message": "..."}]
    }

claudeSignedOut (2026-11-15): when Claude Code was found signed out on the server computer, until a run gets through
(app/services/claude_signin.py); the page's To do and Data status card say so.

seasonSwitch (rollover R2): for two weeks after the app moved to the next season by itself, what it moved from and to; while
a due switch fails, why (app/services/rollover.py). The To do says so on the host's devices.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from fastapi.responses import JSONResponse

from app.build import build_id, code_changed
from app.services.claude_signin import signed_out_since
from app.services.rollover import notice as season_switch

Source = Literal["live", "cache", "replay"]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def envelope(
    data: Any,
    *,
    stale: bool = False,
    source: Source = "live",
    fetched_at: str | None = None,
    errors: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    return {
        "data": data,
        "meta": {"fetched_at": fetched_at or utc_now_iso(), "stale": bool(stale), "source": source, "build": build_id(), "restartNeeded": code_changed(), "claudeSignedOut": signed_out_since(), "seasonSwitch": season_switch()},  # build: app.build (Phase 12); restartNeeded: Phase 16 wave 3; claudeSignedOut: 2026-11-15; seasonSwitch: rollover R2
        "errors": list(errors or []),
    }


def error_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=envelope(None, errors=[{"code": code, "message": message}]))
