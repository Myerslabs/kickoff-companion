"""The Preseason page made visual (ENH-13, the owner's board of 2026-10-30
"Build it as drawn"): what each primary team's section needs beyond the season load, from answers the app already caches.

    now_block(record, games, ap_rank, predicted) -> dict | None   the record so far, the pace over the regular season and
                                         whether that is ahead of the preseason pick, behind it or on it
    starters_block(projected, arrivals, starting) -> dict | None  the projected starters with `new` (an arrival this year)
                                         and `startingNow` (on this week's depth chart; None when there is no chart to say)
    stars_block(stars, lines) -> list    the players to know with their id, face and this season's numbers
    record_of("7-5") -> (7, 5) | None
"""

from __future__ import annotations

import re
from typing import Any

from app.services.lineup_stats import chips_for, index_lines, name_key, short_key

RECORD = re.compile(r"^\s*(\d{1,2})\s*-\s*(\d{1,2})(?:\s*-\s*\d{1,2})?\s*$")


def record_of(text: Any) -> tuple[int, int] | None:
    match = RECORD.match(text) if isinstance(text, str) else None
    return (int(match.group(1)), int(match.group(2))) if match else None


def _line(line: Any) -> dict[str, int] | None:
    if line is None:
        return None
    wins, losses, ties = (getattr(line, k, None) for k in ("wins", "losses", "ties"))
    if not isinstance(wins, int) or not isinstance(losses, int):
        return None
    return {"wins": wins, "losses": losses, "ties": ties if isinstance(ties, int) else 0}


def now_block(record: Any, games: int | None, ap_rank: int | None, predicted: Any) -> dict[str, Any] | None:
    """The record so far beside the pick: `pace` ("9-3") is the win rate carried over the regular season's games, `versus`
    "ahead", "behind" or "on" against the preseason pick's wins (None without a pick or before a game is played)."""
    overall = _line(getattr(record, "total", None))
    if overall is None:
        return None
    conference = _line(getattr(record, "conference_games", None))
    played = overall["wins"] + overall["losses"] + overall["ties"]
    pace = None
    versus = None
    if played and isinstance(games, int) and games >= played:
        wins = round(overall["wins"] / played * games)
        pace = f"{wins}-{games - wins}"
        pick = record_of(getattr(predicted, "overall", None) if predicted is not None else None)
        if pick:
            versus = "ahead" if wins > pick[0] else "behind" if wins < pick[0] else "on"
    return {"overall": overall, "conference": conference, "apRank": ap_rank if isinstance(ap_rank, int) else None, "games": games, "pace": pace, "versus": versus}


def starters_block(projected: Any, arrivals: list[Any], starting: set[str] | None) -> dict[str, Any] | None:
    """Each projected starter with `new` when the load lists him among the arrivals, and `startingNow` when this week's chart
    names him (None for every man when there is no chart this week)."""
    if projected is None:
        return None
    new_keys = {name_key(getattr(m, "name", None)) for m in arrivals or []} - {""}
    out: dict[str, Any] = {}
    for side in ("offense", "defense"):
        rows = []
        for man in getattr(projected, side, None) or []:
            key = name_key(man.name)
            rows.append({"slot": man.slot, "name": man.name, "position": man.position, "new": key in new_keys, "startingNow": None if starting is None else (key in starting or short_key(man.name) in starting)})
        out[side] = rows
    return out if out["offense"] or out["defense"] else None


def stars_block(stars: list[Any], lines: dict[tuple[str, str], Any]) -> list[dict[str, Any]]:
    """The players to know, each matched to CFBD's season lines when he has numbers: his id, his face and up to three numbers
    ("1,402 passing yards" as {"value": "1,402", "label": "passing yards"})."""
    by_player, keys, _names = index_lines(lines or {})
    out = []
    for star in stars or []:
        player_id = keys.get(name_key(star.name)) or keys.get(short_key(star.name))
        numbers = []
        for chip in chips_for(by_player.get(player_id, {}))[:3] if player_id else []:
            value, _, label = chip.partition(" ")
            if value and label:
                numbers.append({"value": f"{int(value):,}" if value.isdigit() else value, "label": label})  # "1,402", as drawn
        out.append({
            "name": star.name, "position": star.position, "honor": star.honor, "why": star.why, "source": star.source if isinstance(star.source, str) and star.source.startswith("https://") else None,
            "playerId": player_id, "headshot": f"/media/headshot/{player_id}" if player_id else None, "numbers": numbers,
        })
    return out
