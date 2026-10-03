"""The CFBD plan behind the key, in plain words (public release Phase 5a): which profile the app runs,
what the key includes, how this month's calls are going, and a note for everything a bigger plan adds.

Two profiles:
- Free (a free key, and Tier 1 for now): lean. Cache lifetimes stretch (app/cfbd/client.py ttl_scale),
  the ticker refreshes every 20 minutes instead of 5, the server never refreshes published data on its
  own (prewarm), and more primary teams, secondary teams and the My teams ticker wait for a Tier 2 key. Everything a free key can get is still shown.
- Tier 2 and up: full.

Nothing is hidden for the plan: a feature the key does not include stays on its page with a note saying
which plan shows it, and a link to CFBD's plans. The forecast projects this month's calls from the pace
so far, so a free key sees early when the month will run short."""

from __future__ import annotations

import calendar
from datetime import datetime, timezone
from typing import Any

PLANS_URL = "https://collegefootballdata.com/api-tiers"
KEY_URL = "https://collegefootballdata.com/key"
LEAN_BUDGET = 20_000  # below this many calls a month the app runs the Free profile
TIER2 = 2

# id, label, the tier that shows it, what it is. "available" comes from the key itself.
FEATURES: list[tuple[str, str, int, str]] = [
    ("core", "Schedule, standings, polls, ratings, stats, rosters, recruiting, team pages", 0, "Every season page. A free key refreshes them less often, so its calls last the month."),
    ("postgame", "Box scores, play-by-play and win probability after each game", 0, "The Archive and the Game program after the final."),
    ("weather", "CFBD game weather", 1, "Forecast and conditions from CFBD. Without it the app uses the National Weather Service, free."),
    ("scoreboard", "Live scores across the country", 1, "The ticker and the Live sheet's scores while games are on. Without it scores refresh from the schedule."),
    ("live_plays", "Live play-by-play for your game", 2, "The Live sheet follows every snap: drives, plays, box score and win probability as they happen."),
    ("liked", "More primary teams, secondary teams and the My teams ticker", 2, "Up to four more primary teams, their pages ready the moment a device connects; secondary schools, conferences and states on the My teams page and in the My teams view of every ranked list; a ticker of just your teams."),
]


def profile(capabilities: Any, budget: int | None) -> str:
    """'tier2' for a Tier 2 or bigger key, else 'free'. An unknown tier goes by the monthly budget."""
    level = getattr(capabilities, "tier_level", None)
    if isinstance(level, int):
        return "tier2" if level >= TIER2 else "free"
    return "free" if (budget or 0) < LEAN_BUDGET else "tier2"


def lean(client: Any) -> bool:
    """Whether the app runs the Free profile right now."""
    status = client.quota.status(client._clock())
    return profile(client.capabilities, status.budget) == "free"


def allows_liked(capabilities: Any) -> bool:
    level = getattr(capabilities, "tier_level", None)
    return isinstance(level, int) and level >= TIER2


def _available(feature: str, caps: Any) -> bool | None:
    if feature in ("core", "postgame"):
        return True
    if feature == "liked":
        level = getattr(caps, "tier_level", None)
        return None if level is None else level >= TIER2
    return getattr(caps, feature, None)


def forecast(used: int | None, budget: int | None, now: datetime, reset_at: str | None = None) -> dict[str, Any]:
    """This month's calls at the pace so far: the projected total and whether it fits."""
    days = calendar.monthrange(now.year, now.month)[1]
    elapsed = max((now - now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)).total_seconds() / 86400, 0.25)
    if not isinstance(used, int) or not isinstance(budget, int) or budget <= 0:
        return {"projected": None, "fits": None, "runsOutOn": None, "text": "Not enough to go on yet."}
    projected = round(used / elapsed * days)
    fits = projected <= budget
    runs_out = None
    if not fits and used > 0:
        day = int(budget / (used / elapsed)) + 1
        runs_out = now.replace(day=min(max(day, 1), days)).date().isoformat()
    text = (f"On pace for about {projected:,} of {budget:,} calls this month." if fits
            else f"On pace for about {projected:,} calls, more than the {budget:,} this month allows; the app will lean on its cache from around {runs_out}.")
    return {"projected": projected, "fits": fits, "runsOutOn": runs_out, "text": text}


def summary(client: Any, now: datetime | None = None) -> dict[str, Any]:
    """Everything the welcome page and Settings show about the plan. Makes no call."""
    now = now or datetime.now(timezone.utc)
    caps = client.capabilities
    quota = client.quota.status(client._clock()).as_dict()
    budget = quota.get("budget")
    used = quota.get("used")
    which = profile(caps, budget)
    features = []
    for fid, label, needs, what in FEATURES:
        available = _available(fid, caps)
        note = None if available else f"Shows with a {'Tier 1' if needs == 1 else 'Tier 2'} key."
        features.append({"id": fid, "label": label, "needs": needs, "available": available, "what": what, "note": note})
    return {
        "tierLevel": caps.tier_level,
        "tierName": caps.tier_name or ("Free" if caps.tier_level == 0 else None),
        "profile": which,
        "profileLabel": "Free: lean" if which == "free" else "Tier 2: full",
        "monthlyLimit": caps.monthly_limit or budget,
        "used": used,
        "remaining": quota.get("remaining"),
        "resetAt": caps.reset_at or quota.get("reset_at"),
        "checkedAt": caps.checked_at.isoformat(timespec="seconds") if caps.checked_at else None,
        "forecast": forecast(used, budget, now),
        "features": features,
        "likedAllowed": allows_liked(caps),
        "plansUrl": PLANS_URL,
        "keyUrl": KEY_URL,
    }
