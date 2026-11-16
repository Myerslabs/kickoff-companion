"""Last season, for the new season's prompts (rollover R3, "next season's starter"; owner 2026-11-15, the plan: "the 2027
season prompts get 2026's results and Claude's 2026 lessons, labelled as last season"). Read from the season in review kept
at the switch (data/season/<year>/book/overview.json) and the lessons kept with their season; empty when neither exists
(before the first switch on this computer). No call of its own.

    last_season_text(data_dir, season) -> str   the block appended to the season load's and the preseason prompts
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.rollover_setup import read_book
from app.services.writing import Lessons

log = logging.getLogger("kickoff.prompts")

MAX_LESSONS = 12


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _record(block: Any) -> str | None:
    b = block if isinstance(block, dict) else {}
    wins, losses, ties = _int(b.get("wins")), _int(b.get("losses")), _int(b.get("ties"))
    if wins is None:
        return None
    return f"{wins}-{losses or 0}" + (f"-{ties}" if ties else "")


def last_season_text(data_dir: Path, season: int) -> str:
    year = int(season) - 1
    kept = read_book(Path(data_dir), year, "overview")
    data = kept["envelope"].get("data") if kept is not None and isinstance(kept["envelope"].get("data"), dict) else {}
    try:
        lessons = Lessons(Path(data_dir), year).for_prompt()[0][-MAX_LESSONS:]
    except Exception:  # noqa: BLE001 - the prompt goes without them; logged
        log.warning("Last season's lessons could not be read for the prompt", exc_info=True)
        lessons = []
    if not data and not lessons:
        return ""
    lines = [f"\n\n## Last season ({year}), for context only", f"Background for the {season} outlook. Do not report any of it as {season} fact; check anything you carry over."]
    record = data.get("record") if isinstance(data.get("record"), dict) else {}
    overall, conference = _record(record.get("overall")), _record(record.get("conference"))
    team = data.get("team") if isinstance(data.get("team"), dict) else {}
    if overall:
        ranks = [f"AP No. {record['apRank']}" if _int(record.get("apRank")) else None, f"CFP No. {record['cfpRank']}" if _int(record.get("cfpRank")) else None]
        sp = (data.get("ratings") or {}).get("sp") if isinstance(data.get("ratings"), dict) else None
        if isinstance(sp, dict) and _int(sp.get("rank")):
            ranks.append(f"SP+ #{sp['rank']}")
        conf_name = team.get("conferenceShort") or team.get("conference") or "conference"
        lines.append(f"- Final record {overall}" + (f" ({conference} {conf_name})" if conference else "") + (f"; {', '.join(r for r in ranks if r)}" if any(ranks) else "") + ".")
    games = [g for g in data.get("schedule") or [] if isinstance(g, dict) and g.get("completed") is True]
    for g in games:
        opponent = (g.get("opponent") or {}).get("school") if isinstance(g.get("opponent"), dict) else None
        week = _int(g.get("week"))
        result = g.get("result") if isinstance(g.get("result"), str) else ""
        us, them = _int(g.get("usPoints")), _int(g.get("themPoints"))
        if opponent and us is not None and them is not None:
            lines.append(f"- {'Week ' + str(week) if week is not None else 'Bowl'}: {result} {us}-{them} vs {opponent}".replace("  ", " "))
    if lessons:
        lines.append(f"What the weekly reviews learned in {year} (about sources and habits; players named in them may have moved on):")
        lines += [f"- {t}" for t in lessons if isinstance(t, str) and t.strip()]
    return "\n".join(lines) + "\n"
