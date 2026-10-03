"""One upstream piece of an assembled answer, shared by the season, leaders, roster, recruiting,
and player services: fetch through the client, parse record by record, and report how it went.
A part that fails is reported, never raised, so the rest of the answer still goes out."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from app.cache import DataKind
from app.cfbd.client import CfbdClient, CfbdError, Fetched
from app.cfbd.models import CfbdModel, parse_records
from app.cfbd.quota import QuotaBlocked

log = logging.getLogger("kickoff.parts")


def calendar_week(weeks: list[Any], now: datetime) -> int | None:
    """The regular-season week CFBD's /calendar says `now` falls in (startDate <= now <= endDate),
    else None (the off-season, the postseason, or a calendar that did not load). Phase 12: the
    slate and the ticker on a Saturday we do not play."""
    for week in weeks:
        if str(getattr(week, "season_type", None) or "regular") != "regular" or not isinstance(getattr(week, "week", None), int):
            continue
        start, end = _time(getattr(week, "start_date", None)), _time(getattr(week, "end_date", None))
        if start is not None and end is not None and start <= now <= end:
            return week.week
    return None


def calendar_slot(weeks: list[Any], now: datetime) -> tuple[int, str] | None:
    """(week, seasonType) of the calendar week `now` falls in, the postseason included (Phase 15:
    CFBD's postseason is one "week 1" from mid-December to the title game), else None."""
    for week in weeks:
        if not isinstance(getattr(week, "week", None), int):
            continue
        start, end = _time(getattr(week, "start_date", None)), _time(getattr(week, "end_date", None))
        if start is not None and end is not None and start <= now <= end:
            return week.week, str(getattr(week, "season_type", None) or "regular")
    return None


def _time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass
class Part:
    """The parsed records plus how they were obtained."""

    name: str
    records: list[Any] = field(default_factory=list)
    fetched: Fetched | None = None
    error: str | None = None
    skipped: int = 0
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.fetched is not None

    def status(self, now: datetime) -> dict[str, Any]:
        if self.fetched is None:
            return {"status": "error", "fetchedAt": None, "ageSeconds": None, "error": self.error, "skipped": self.skipped}
        age = max(0.0, (now - self.fetched.fetched_at).total_seconds())
        return {
            "status": "stale" if self.fetched.stale else "ok",
            "fetchedAt": iso(self.fetched.fetched_at),
            "ageSeconds": round(age),
            "error": self.fetched.error,
            "skipped": self.skipped,
        }


class PartFetcher:
    """Fetches parts through one client with a small concurrency limit. Parsed records are
    remembered per (endpoint, params, fetched_at) so a cached 30,000-row payload is validated
    once, not on every page view."""

    MEMO_LIMIT = 40

    def __init__(self, client: CfbdClient, concurrency: int = 4) -> None:
        self.client = client
        self._gate = asyncio.Semaphore(concurrency)
        self._memo: dict[tuple[str, tuple[tuple[str, str], ...], str], tuple[list[Any], int, list[str]]] = {}

    async def fetch(self, name: str, endpoint: str, params: dict[str, Any], model: type[CfbdModel] | None, kind: DataKind, max_age: timedelta | None = None) -> Part:
        async with self._gate:
            try:
                fetched = await self.client.get(endpoint, params, kind=kind, max_age=max_age)
            except (QuotaBlocked, CfbdError) as exc:
                log.warning("Part %s unavailable: %s", name, exc)
                return Part(name, error=str(exc))
            except Exception as exc:  # noqa: BLE001 - one broken part must not kill the answer; it is logged
                log.exception("Part %s failed unexpectedly", name)
                return Part(name, error=f"unexpected error: {exc.__class__.__name__}")
        if model is None:  # a payload kept as JSON (the advanced box score): the caller normalizes it with guards
            return Part(name, [], fetched, None, 0, [])
        key = (endpoint, tuple(sorted(fetched.params.items())), iso(fetched.fetched_at) or "")
        hit = self._memo.get(key)
        if hit is None:
            parsed = parse_records(model, fetched.payload, context=name)
            hit = (parsed.records, parsed.skipped, parsed.problems)
            if len(self._memo) >= self.MEMO_LIMIT:
                self._memo.pop(next(iter(self._memo)))
            self._memo[key] = hit
        records, skipped, problems = hit
        return Part(name, records, fetched, None, skipped, problems)


@dataclass
class Assembled:
    """What a service hands the route: the data plus the envelope fields derived from its parts."""

    data: dict[str, Any]
    fetched_at: str | None
    stale: bool
    source: str
    errors: list[dict[str, str]]
    all_failed: bool


def assemble(data: dict[str, Any], parts: dict[str, Part]) -> Assembled:
    ok = [part for part in parts.values() if part.ok]
    errors = [{"code": "part_unavailable", "message": f"{part.name}: {part.error}"} for part in parts.values() if not part.ok]
    for part in parts.values():
        if part.ok and part.skipped:
            errors.append({"code": "records_skipped", "message": f"{part.name}: skipped {part.skipped} malformed record(s)"})
    oldest = min((part.fetched.fetched_at for part in ok), default=None)
    return Assembled(
        data=data,
        fetched_at=iso(oldest),
        stale=any(part.fetched.stale for part in ok),
        source="live" if any(part.fetched.source == "live" for part in ok) else "cache",
        errors=errors,
        all_failed=not ok,
    )


def statuses(parts: dict[str, Part], now: datetime) -> dict[str, dict[str, Any]]:
    return {name: part.status(now) for name, part in parts.items()}
