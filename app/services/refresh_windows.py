"""When a page's Claude writing may still be refreshed (batch 4 part 3, owner 2026-11-19).

Run with Claude refreshes what a page already holds. Each page has a window; once it closes the page is frozen and no run
changes it, so nothing is retroactive:

    preseason   the Preseason Magazine, until the season's first kickoff ("preseason stays up until the first kick, but not
                retroactive")
    pre         a week's Pre-Game Program, until its own kickoff (the kickoff lock saves it then)
    post        a week's Post-Game Program, from the final until 6 AM the Monday after (the Sunday paper is about the game,
                Monday on is about the new week)
    season      My Team and the season book (the postseason), until the season is over: the day after the national
    book        championship game ("postseason keeps updating until national championship game is over and the day after")

Pure: the caller passes the times it knows. A time it does not know leaves the window open (the run itself still guards
what it writes).

    Window(open, reason, closes_at)
    window_for(kind, now=, kickoff=, first_kickoff=, title_final_at=)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta

KINDS = ("preseason", "pre", "post", "season", "book")
POST_CLOSE_HOUR = 6  # the Monday after the game, 6 AM local
TITLE_GRACE = timedelta(days=1)


@dataclass(frozen=True)
class Window:
    open: bool
    reason: str
    closes_at: datetime | None = None


def post_closes_at(kickoff: datetime) -> datetime:
    """6 AM local on the Monday after the game (a game played Monday: the Monday after that)."""
    day = kickoff.date()
    days = (7 - day.weekday()) % 7 or 7
    return datetime.combine(day + timedelta(days=days), time(POST_CLOSE_HOUR), tzinfo=kickoff.tzinfo)


def window_for(kind: str, *, now: datetime, kickoff: datetime | None = None, first_kickoff: datetime | None = None, title_final_at: datetime | None = None) -> Window:
    if kind == "preseason":
        if first_kickoff is not None and now >= first_kickoff:
            return Window(False, "The Preseason Magazine was kept at the first kickoff.", first_kickoff)
        return Window(True, "Until the first kickoff.", first_kickoff)
    if kind == "pre":
        if kickoff is None:
            return Window(False, "This game has no kickoff time yet.")
        if now >= kickoff:
            return Window(False, "This Pre-Game was kept at kickoff.", kickoff)
        return Window(True, "Until kickoff.", kickoff)
    if kind == "post":
        if kickoff is None or now < kickoff:
            return Window(False, "The game has not been played yet.")
        closes = post_closes_at(kickoff)
        if now >= closes:
            return Window(False, "This Post-Game was kept on the Monday after the game.", closes)
        return Window(True, "Until Monday morning.", closes)
    if kind in ("season", "book"):
        if title_final_at is not None and now >= title_final_at + TITLE_GRACE:
            return Window(False, "The season is over: kept the day after the national championship game.", title_final_at + TITLE_GRACE)
        return Window(True, "Until the day after the national championship game.", title_final_at + TITLE_GRACE if title_final_at else None)
    return Window(False, "Claude wrote nothing on this page.")
