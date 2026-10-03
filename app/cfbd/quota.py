"""The quota ledger and guard. Mandatory: no CFBD call happens without passing check().

Rules from docs/02-ARCHITECTURE.md, "Quota guard":
- Every upstream attempt is recorded, including failures. Counting conservatively is safer
  than being surprised.
- The budget comes from settings until /info gives the live remaining-calls value, after
  which the ledger counts down from that number.
- 75 percent: warning. QUOTA_HARD_STOP_PCT: only live-game calls continue. 97 percent or
  nothing left: everything stops.
- Reconciliation with /info is adaptive: at startup, hourly inside a live game window,
  every 6 hours otherwise, and right after a threshold is crossed. Never more than once per
  10 minutes, since /info is itself a billed call.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

from app.config import Settings
from app.db import Database

log = logging.getLogger("kickoff.quota")

WARNING_PCT = 75
EXHAUSTED_PCT = 97
RECONCILE_IDLE = timedelta(hours=6)
RECONCILE_LIVE = timedelta(hours=1)
RECONCILE_MIN_GAP = timedelta(minutes=10)
RECONCILE_WHEN_EXHAUSTED = timedelta(hours=1)


class QuotaMode(str, Enum):
    NORMAL = "normal"
    WARNING = "warning"  # 75 percent used: UI warning
    RESTRICTED = "restricted"  # hard stop reached: only live-game calls
    EXHAUSTED = "exhausted"  # 97 percent or nothing left: no calls at all


class QuotaBlocked(Exception):
    """Raised by check() when the guard refuses a call. The message says why."""


@dataclass(frozen=True)
class QuotaStatus:
    month: str
    mode: QuotaMode
    budget: int
    used: int
    remaining: int
    pct_used: float
    reason: str
    ledger_calls_this_month: int
    reconciled: bool
    reconciled_at: str | None
    reconciled_remaining: int | None
    calls_since_reconcile: int
    tier_level: int | None
    tier_name: str | None
    reset_at: str | None = None
    upstream_used: int | None = None

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["mode"] = self.mode.value
        return data


def month_of(now: datetime) -> str:
    return now.astimezone(timezone.utc).strftime("%Y-%m")


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds")


class QuotaGuard:
    def __init__(self, db: Database, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.needs_reconcile = True
        self.last_reconcile_attempt: datetime | None = None
        self._last_mode: QuotaMode | None = None

    # --- recording --------------------------------------------------------------

    def record(self, endpoint: str, status: int | None, ok: bool, *, live: bool, now: datetime) -> QuotaMode:
        """Write one attempt to the ledger. Returns the mode after the call and flags a
        reconcile when a threshold was just crossed."""
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO quota_calls (at, month, endpoint, status, ok, live) VALUES (?, ?, ?, ?, ?, ?)",
                (_iso(now), month_of(now), endpoint, status, 1 if ok else 0, 1 if live else 0),
            )
        mode = self.status(now).mode
        if self._last_mode is not None and mode != self._last_mode:
            log.warning("Quota mode changed from %s to %s", self._last_mode.value, mode.value)
            self.needs_reconcile = True
        self._last_mode = mode
        return mode

    def reconcile(
        self,
        *,
        remaining: int | None,
        budget: int | None,
        tier_level: int | None,
        tier_name: str | None,
        raw: Any,
        now: datetime,
    ) -> QuotaStatus:
        """Store what /info said. remaining None means the endpoint gave no usable number."""
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO quota_reconcile (id, at, month, remaining, budget, tier_level, tier_name, raw)"
                " VALUES (1, ?, ?, ?, ?, ?, ?, ?)",
                (
                    _iso(now),
                    month_of(now),
                    remaining,
                    budget,
                    tier_level,
                    tier_name,
                    json.dumps(raw, separators=(",", ":"))[:4000] if raw is not None else None,
                ),
            )
        self.needs_reconcile = False
        self.last_reconcile_attempt = now
        status = self.status(now)
        self._last_mode = status.mode
        return status

    def mark_reconcile_attempt(self, now: datetime) -> None:
        self.last_reconcile_attempt = now

    # --- decisions ----------------------------------------------------------------

    def check(self, *, live: bool, now: datetime, reconciling: bool = False) -> QuotaStatus:
        """Raise QuotaBlocked when the call must not happen. Returns the status otherwise."""
        status = self.status(now)
        if status.mode is QuotaMode.EXHAUSTED:
            if reconciling and self._reconcile_allowed_when_exhausted(now):
                return status
            raise QuotaBlocked(f"CFBD quota exhausted: {status.reason}. Calls resume next month.")
        if status.mode is QuotaMode.RESTRICTED and not live:
            raise QuotaBlocked(
                f"CFBD quota at {status.pct_used:.0f}% of the monthly budget: only live-game calls are"
                " allowed until next month."
            )
        return status

    def should_reconcile(self, now: datetime, *, live_window: bool) -> bool:
        last = self.last_reconcile_attempt
        if last is not None and now - last < RECONCILE_MIN_GAP:
            return False
        if last is None or self.needs_reconcile:
            return True
        interval = RECONCILE_LIVE if live_window else RECONCILE_IDLE
        return now - last >= interval

    def _reconcile_allowed_when_exhausted(self, now: datetime) -> bool:
        last = self.last_reconcile_attempt
        return last is None or now - last >= RECONCILE_WHEN_EXHAUSTED

    # --- status -------------------------------------------------------------------

    def status(self, now: datetime) -> QuotaStatus:
        month = month_of(now)
        with self.db.read() as conn:
            ledger_month = conn.execute("SELECT COUNT(*) FROM quota_calls WHERE month = ?", (month,)).fetchone()[0]
            rec = conn.execute("SELECT * FROM quota_reconcile WHERE id = 1").fetchone()
            since = 0
            if rec is not None and rec["month"] == month:
                since = conn.execute("SELECT COUNT(*) FROM quota_calls WHERE at > ?", (rec["at"],)).fetchone()[0]

        budget = int(self.settings.monthly_call_budget)
        reconciled = rec is not None and rec["month"] == month and rec["remaining"] is not None
        tier_level = int(rec["tier_level"]) if rec is not None and rec["tier_level"] is not None else None
        tier_name = rec["tier_name"] if rec is not None else None
        reset_at: str | None = None
        upstream_used: int | None = None
        if rec is not None and rec["raw"]:
            try:
                raw = json.loads(rec["raw"])
            except ValueError:
                raw = None
            if isinstance(raw, dict):
                reset_at = str(raw.get("resetAt")) if raw.get("resetAt") else None
                used_value = raw.get("usedCalls")
                upstream_used = int(used_value) if isinstance(used_value, int) and not isinstance(used_value, bool) else None

        if reconciled:
            if rec["budget"]:
                budget = int(rec["budget"])
            remaining = max(int(rec["remaining"]) - int(since), 0)
            used = max(budget - remaining, 0)
        else:
            used = int(ledger_month)
            remaining = max(budget - used, 0)

        pct = (used / budget * 100) if budget > 0 else 100.0
        hard_stop = int(self.settings.quota_hard_stop_pct)
        if remaining <= 0 or pct >= EXHAUSTED_PCT:
            mode = QuotaMode.EXHAUSTED
        elif pct >= hard_stop:
            mode = QuotaMode.RESTRICTED
        elif pct >= WARNING_PCT:
            mode = QuotaMode.WARNING
        else:
            mode = QuotaMode.NORMAL

        basis = "CFBD's remaining-calls figure" if reconciled else "the local ledger only (not reconciled yet)"
        reason = f"{used:,} of {budget:,} calls used this month ({pct:.0f}%), {remaining:,} left, based on {basis}"
        return QuotaStatus(
            month=month,
            mode=mode,
            budget=budget,
            used=used,
            remaining=remaining,
            pct_used=round(pct, 1),
            reason=reason,
            ledger_calls_this_month=int(ledger_month),
            reconciled=reconciled,
            reconciled_at=rec["at"] if rec is not None and rec["month"] == month else None,
            reconciled_remaining=int(rec["remaining"]) if reconciled else None,
            calls_since_reconcile=int(since),
            tier_level=tier_level,
            tier_name=tier_name,
            reset_at=reset_at,
            upstream_used=upstream_used,
        )

    def last_reconcile_raw(self, now: datetime) -> tuple[Any, datetime] | None:
        """The last /info payload stored this month, with when it was stored."""
        with self.db.read() as conn:
            rec = conn.execute("SELECT at, month, raw FROM quota_reconcile WHERE id = 1").fetchone()
        if rec is None or rec["month"] != month_of(now) or not rec["raw"]:
            return None
        try:
            payload = json.loads(rec["raw"])
            at = datetime.fromisoformat(rec["at"])
        except (ValueError, TypeError):
            return None
        if at.tzinfo is None:
            at = at.replace(tzinfo=timezone.utc)
        return payload, at

    def calls_by_endpoint(self, now: datetime, *, limit: int = 20) -> list[dict[str, Any]]:
        with self.db.read() as conn:
            rows = conn.execute(
                "SELECT endpoint, COUNT(*) AS calls, SUM(ok) AS ok FROM quota_calls WHERE month = ?"
                " GROUP BY endpoint ORDER BY calls DESC LIMIT ?",
                (month_of(now), limit),
            ).fetchall()
        return [{"endpoint": r["endpoint"], "calls": int(r["calls"]), "ok": int(r["ok"] or 0)} for r in rows]
