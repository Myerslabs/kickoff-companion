"""What the owner's key can do right now.

The tier changes during the year (free in the offseason, paid in season). /info reports the
Patreon level, the monthly limit, what is left, and a `features` object that says exactly
which gated endpoints work. A recorded sample (tests/fixtures/cfbd/info.json) looks like:

    {"patronLevel": 0, "tierName": "Free", "monthlyLimit": 1000, "remainingCalls": 1000,
     "usedCalls": 0, "resetAt": "2026-10-01T00:00:00.000Z", "sharedPool": true,
     "features": {"adjustedMetrics": false, "weather": false, "scoreboard": false,
                  "livePlayByPlay": false, "graphQl": false}}

Real responses win over the tier: a 401 or 403 on a gated endpoint switches that capability
off, a 200 switches it on.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# endpoint -> (capability name, feature key in /info, minimum tier when features are absent)
GATED_ENDPOINTS: dict[str, tuple[str, str, int]] = {
    "/games/weather": ("weather", "weather", 1),
    "/scoreboard": ("scoreboard", "scoreboard", 1),
    "/live/plays": ("live_plays", "livePlayByPlay", 2),
}

TIER_NAMES = {0: "Free", 1: "Tier 1", 2: "Tier 2", 3: "Tier 3", 4: "Tier 4", 5: "Tier 5"}


def _first(payload: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in payload and payload[name] is not None:
            return payload[name]
    lowered = {str(k).lower().replace("_", ""): v for k, v in payload.items()}
    for name in names:
        value = lowered.get(name.lower().replace("_", ""))
        if value is not None:
            return value
    return None


def _to_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        digits = "".join(ch for ch in value if ch.isdigit())
        if digits:
            return int(digits)
    return None


def _to_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return bool(value)
    if isinstance(value, str) and value.strip().lower() in {"true", "false", "yes", "no", "1", "0"}:
        return value.strip().lower() in {"true", "yes", "1"}
    return None


@dataclass
class Capabilities:
    tier_level: int | None = None
    tier_name: str | None = None
    monthly_limit: int | None = None
    remaining_calls: int | None = None
    used_calls: int | None = None
    reset_at: str | None = None
    shared_pool: bool | None = None
    checked_at: datetime | None = None
    source: str = "unknown"  # unknown, info, probe
    weather: bool | None = None
    scoreboard: bool | None = None
    live_plays: bool | None = None
    adjusted_metrics: bool | None = None
    notes: list[str] = field(default_factory=list)

    def update_from_info(self, payload: Any, now: datetime) -> None:
        """Read the /info payload. Tolerates any shape; unknown parts stay unknown."""
        if not isinstance(payload, dict):
            self.notes = [f"/info returned {type(payload).__name__}, not an object"]
            return
        self.checked_at = now
        self.source = "info"
        self.notes = []
        level = _to_int(_first(payload, "patronLevel", "patron_level", "tier", "level"))
        name = _first(payload, "tierName", "patronLevelName", "levelName")
        self.tier_level = level
        self.tier_name = str(name) if name else (TIER_NAMES.get(level, f"tier {level}") if level is not None else None)
        self.monthly_limit = _to_int(_first(payload, "monthlyLimit", "monthlyCalls", "callLimit", "limit"))
        self.remaining_calls = _to_int(_first(payload, "remainingCalls", "remaining_calls", "remaining"))
        self.used_calls = _to_int(_first(payload, "usedCalls", "used_calls", "used"))
        reset = _first(payload, "resetAt", "reset_at", "resets")
        self.reset_at = str(reset) if reset else None
        self.shared_pool = _to_bool(payload.get("sharedPool"))

        features = payload.get("features")
        features = features if isinstance(features, dict) else {}
        for capability, feature_key, minimum_tier in GATED_ENDPOINTS.values():
            value = _to_bool(features.get(feature_key)) if feature_key in features else None
            if value is None and level is not None:
                value = level >= minimum_tier
            setattr(self, capability, value)
        self.adjusted_metrics = _to_bool(features.get("adjustedMetrics")) if "adjustedMetrics" in features else None
        if level is None and not features:
            self.notes.append("/info gave neither a tier level nor features; gated endpoints stay unknown until first use")

    def note_probe(self, endpoint: str, status: int, now: datetime) -> None:
        """Learn from a real response to a gated endpoint."""
        gate = GATED_ENDPOINTS.get(endpoint)
        if gate is None:
            return
        capability = gate[0]
        allowed = 200 <= status < 300
        if status in (401, 403) or allowed:
            if getattr(self, capability) != allowed:
                setattr(self, capability, allowed)
                self.source = "probe"
                verb = "works" if allowed else f"was refused with HTTP {status}"
                self.notes.append(f"{endpoint} {verb} on {now.date()}")

    def allows(self, endpoint: str) -> bool | None:
        gate = GATED_ENDPOINTS.get(endpoint)
        if gate is None:
            return True
        return getattr(self, gate[0])

    def as_dict(self) -> dict[str, Any]:
        return {
            "tier_level": self.tier_level,
            "tier_name": self.tier_name,
            "monthly_limit": self.monthly_limit,
            "remaining_calls": self.remaining_calls,
            "used_calls": self.used_calls,
            "reset_at": self.reset_at,
            "shared_pool": self.shared_pool,
            "checked_at": self.checked_at.isoformat(timespec="seconds") if self.checked_at else None,
            "source": self.source,
            "weather": self.weather,
            "scoreboard": self.scoreboard,
            "live_plays": self.live_plays,
            "adjusted_metrics": self.adjusted_metrics,
            "notes": list(self.notes),
        }
