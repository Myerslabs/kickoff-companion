"""The response envelope every /api route returns.

    {
      "data": ...,
      "meta": {"fetched_at": "<ISO 8601 UTC>", "stale": false, "source": "live" | "cache" | "replay", "build": "<id>"},
      "errors": [{"code": "...", "message": "..."}]
    }
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from fastapi.responses import JSONResponse

from app.build import build_id

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
        "meta": {"fetched_at": fetched_at or utc_now_iso(), "stale": bool(stale), "source": source, "build": build_id()},  # build: app.build (Phase 12)
        "errors": list(errors or []),
    }


def error_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=envelope(None, errors=[{"code": code, "message": message}]))
