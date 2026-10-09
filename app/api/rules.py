"""GET /api/rules/penalties: the penalty book for the Live sheet's penalty panel (Phase 17 #21). The fouls,
their plain-words explanations, yards, rule numbers and rule-book pages, from app/penalties.json, with the
source (the NCAA rules book's address). No CFBD call."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.api.envelope import envelope
from app.live.penalties import penalty_book

router = APIRouter(tags=["rules"])


@router.get("/api/rules/penalties")
async def penalties() -> Any:
    book = penalty_book()
    errors = [] if book["penalties"] else [{"code": "no_penalty_book", "message": "The penalty list could not be read; see the server log."}]
    return envelope({"source": book["source"], "penalties": book["penalties"]}, source="live", errors=errors)
