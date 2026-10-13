"""On this day (the Prompts phase, wave B, owner 2026-10-13: "a popup system similar to 'the stadium was built
84 years ago today'"; item 6 makes it a note at the top of the page, never a popup). The facts prompt collects dated
events for every school; this picks the ones whose month and day are today, for the teams the reader follows and this
week's opponent, and says how many years ago. No call, no file: it reads what the facts file holds.

    on_this_day(facts_by_school, schools, today) -> [{school, event, date, years}]   in the schools' order, oldest first
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

FULL_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")


def on_this_day(facts: dict[str, Any], schools: list[str], today: date) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for school in schools:
        if not isinstance(school, str) or school in seen:
            continue
        seen.add(school)
        row = facts.get(school) if isinstance(facts, dict) else None
        dates = row.get("dates") if isinstance(row, dict) else None
        mine: list[dict[str, Any]] = []
        for item in dates if isinstance(dates, list) else []:
            if not isinstance(item, dict):
                continue
            match = FULL_DATE.match(str(item.get("date") or ""))
            event = item.get("event")
            if not match or not isinstance(event, str) or not event.strip():
                continue
            year, month, day = (int(x) for x in match.groups())
            if (month, day) != (today.month, today.day) or year >= today.year or year < 1800:
                continue
            mine.append({"school": school, "event": event.strip(), "date": match.group(0), "years": today.year - year})
        out.extend(sorted(mine, key=lambda e: -e["years"]))
    return out
