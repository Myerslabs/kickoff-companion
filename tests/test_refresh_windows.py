"""Run with Claude's windows (batch 4 part 3, owner 2026-11-19): each page refreshes until its window closes, never after."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services.refresh_windows import post_closes_at, window_for

ET = timezone(timedelta(hours=-5))
KICK = datetime(2026, 11, 21, 12, 0, tzinfo=ET)  # a Saturday noon


def test_preseason_until_the_first_kickoff() -> None:
    first = datetime(2026, 9, 5, 19, 0, tzinfo=ET)
    assert window_for("preseason", now=first - timedelta(minutes=1), first_kickoff=first).open
    assert not window_for("preseason", now=first, first_kickoff=first).open, "not retroactive"
    assert window_for("preseason", now=first).open, "an unknown first kickoff leaves it open"


def test_pre_until_its_kickoff() -> None:
    assert window_for("pre", now=KICK - timedelta(hours=1), kickoff=KICK).open
    shut = window_for("pre", now=KICK, kickoff=KICK)
    assert not shut.open and "kickoff" in shut.reason
    assert not window_for("pre", now=KICK, kickoff=None).open


def test_post_from_the_final_until_monday_morning() -> None:
    assert post_closes_at(KICK) == datetime(2026, 11, 23, 6, 0, tzinfo=ET)
    assert post_closes_at(datetime(2026, 11, 23, 19, 0, tzinfo=ET)) == datetime(2026, 11, 30, 6, 0, tzinfo=ET), "a Monday game: the Monday after"
    assert not window_for("post", now=KICK - timedelta(hours=1), kickoff=KICK).open, "not before the game"
    assert window_for("post", now=KICK + timedelta(hours=20), kickoff=KICK).open
    assert not window_for("post", now=datetime(2026, 11, 23, 6, 0, tzinfo=ET), kickoff=KICK).open


def test_season_and_book_until_the_day_after_the_title_game() -> None:
    title = datetime(2027, 1, 18, 19, 30, tzinfo=ET)
    for kind in ("season", "book"):
        assert window_for(kind, now=title + timedelta(hours=12), title_final_at=title).open
        assert not window_for(kind, now=title + timedelta(days=1), title_final_at=title).open
        assert window_for(kind, now=title + timedelta(days=30)).open, "an unknown title game leaves it open"


def test_a_page_with_nothing_of_claudes() -> None:
    assert not window_for("standings", now=KICK).open
