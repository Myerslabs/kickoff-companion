"""The season as one line (Wave 1, 2026-10-30): the stops' rules, dates and the line the rail draws."""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.services.stops import Checks, GameRow, Status, backstop_at, closed_out, current_stop, post_open, pre_open_at, season_line

ET = ZoneInfo("America/New_York")


def at(y: int, m: int, d: int, h: int = 12, mi: int = 0) -> datetime:
    return datetime(y, m, d, h, mi, tzinfo=ET)


def game(game_id: int, week: int, kickoff: datetime, opponent: str, home_away: str = "home", *, completed: bool = False, us: int | None = None, them: int | None = None) -> GameRow:
    return GameRow(game_id, week, kickoff, opponent, home_away, completed, us, them)


# Florida's 2026 schedule as the cache has it: weeks 1-7 played, week 8 a bye, Georgia on Saturday October 31
SEASON = [
    game(1, 1, at(2026, 9, 5, 19), "Florida Atlantic", completed=True, us=66, them=21),
    game(2, 2, at(2026, 9, 12, 19), "Campbell", completed=True, us=52, them=3),
    game(3, 3, at(2026, 9, 19, 15, 30), "Auburn", "away", completed=True, us=44, them=39),
    game(4, 4, at(2026, 9, 26, 19), "Ole Miss", completed=True, us=52, them=28),
    game(5, 5, at(2026, 10, 3, 12), "Missouri", "away", completed=True, us=17, them=45),
    game(6, 6, at(2026, 10, 10, 19), "South Carolina", completed=True, us=19, them=38),
    game(7, 7, at(2026, 10, 17, 19, 30), "Texas", "away", completed=True, us=27, them=24),
    game(9, 9, at(2026, 10, 31, 15, 30), "Georgia", "neutral"),
    game(10, 10, at(2026, 11, 7, 19), "Oklahoma"),
    game(13, 13, at(2026, 11, 27, 15, 30), "Florida State", "away"),
]


def all_saved(g: GameRow) -> Status:
    return Status(pre_locked=g.completed, archived=g.completed, post_locked=g.completed, post_locked_at=g.kickoff + timedelta(days=2) if g.completed else None, checks=Checks(final=g.completed, poll=g.completed))


def test_pre_opens_thursday_for_a_saturday_game_and_the_day_before_a_thursday_or_friday_game():
    assert pre_open_at(at(2026, 10, 31, 15, 30)) == at(2026, 10, 29, 6, 0)  # Saturday: Thursday 6 AM
    assert pre_open_at(at(2026, 11, 27, 15, 30)) == at(2026, 11, 26, 6, 0)  # Friday: Thursday, the day before
    assert pre_open_at(at(2026, 11, 5, 19, 30)) == at(2026, 11, 4, 6, 0)  # Thursday: Wednesday
    assert pre_open_at(at(2026, 11, 1, 12)) == at(2026, 10, 29, 6, 0)  # a Sunday game keeps its week's Thursday


def test_backstop_is_the_tuesday_after_at_six():
    assert backstop_at(at(2026, 10, 31, 15, 30)) == at(2026, 11, 3, 6, 0)
    assert backstop_at(at(2026, 11, 27, 15, 30)) == at(2026, 12, 1, 6, 0)
    assert backstop_at(at(2026, 11, 3, 19)) == at(2026, 11, 10, 6, 0), "a Tuesday game waits for the next Tuesday"


def test_closed_out_by_the_checklist_or_the_backstop():
    kick = at(2026, 10, 31, 15, 30)
    assert closed_out(Checks(final=True, poll=True, recap=True), kick, at(2026, 11, 1, 14)) is True
    assert closed_out(Checks(final=True, poll=True, recap=False), kick, at(2026, 11, 1, 14)) is False
    assert closed_out(Checks(final=True, poll=False), kick, at(2026, 11, 3, 6)) is True, "Tuesday 6 AM closes it with the poll still out"
    assert Checks(final=True, poll=False, recap=False).missing() == ["poll", "recap"]


def test_post_open_until_locked_or_backstop():
    kick = at(2026, 10, 17, 19, 30)
    assert post_open(kick, False, at(2026, 10, 18, 9)) is True
    assert post_open(kick, True, at(2026, 10, 18, 9)) is False
    assert post_open(kick, False, at(2026, 10, 20, 6)) is False, "the backstop passed: the loop writes the lock, the Season leads"
    assert post_open(kick, False, at(2026, 10, 17, 12)) is False, "before kickoff nothing is post"


def test_current_stop_through_a_game_week():
    def status(g: GameRow) -> Status:
        s = all_saved(g)
        if g.game_id == 9:  # Georgia: the final comes, then the poll, then What decided it
            s.post_locked = False
            s.post_locked_at = None
        return s

    games = [g for g in SEASON]
    # Monday of the bye week and Wednesday of the game week: the Season leads
    assert current_stop(games, at(2026, 10, 26, 9), status)["kind"] == "season"
    assert current_stop(games, at(2026, 10, 28, 23), status)["kind"] == "season"
    # Thursday 6 AM: the Pre-Game of Georgia
    thursday = current_stop(games, at(2026, 10, 29, 6), status)
    assert (thursday["kind"], thursday["gameId"], thursday["href"]) == ("pre", 9, "#program=9")
    assert thursday["detail"] == "Week 9 · vs Georgia"
    # during the game: still the Pre-Game (In Game is its own tab)
    assert current_stop(games, at(2026, 10, 31, 17), status)["kind"] == "pre"
    # the final: the Post-Game leads until it closes out
    played = [g if g.game_id != 9 else game(9, 9, g.kickoff, "Georgia", "neutral", completed=True, us=20, them=27) for g in games]
    checks = Checks(final=True, poll=False, recap=False)

    def live_post(g: GameRow) -> Status:
        s = status(g)
        if g.game_id == 9:
            s.checks = checks
        return s

    sunday = current_stop(played, at(2026, 11, 1, 9), live_post)
    assert (sunday["kind"], sunday["gameId"], sunday["href"]) == ("post", 9, "#postgame=9")
    assert sunday["detail"] == "Week 9 · vs Georgia · L 20-27"
    checks.poll = checks.recap = True
    assert current_stop(played, at(2026, 11, 1, 15), live_post)["kind"] == "season", "every check in: the Season leads"
    checks.recap = False
    assert current_stop(played, at(2026, 11, 2, 9), live_post)["kind"] == "post", "What decided it still out on Monday: the Post-Game stays"
    assert current_stop(played, at(2026, 11, 3, 6), live_post)["kind"] == "season", "Tuesday 6 AM: the backstop closes it"


def test_pre_opens_early_when_thursdays_run_landed():
    def status(g: GameRow) -> Status:
        s = all_saved(g)
        if g.game_id == 9:
            s.pre_opened_at = at(2026, 10, 28, 19, 40)  # Wednesday evening: the availability run came early
        return s

    assert current_stop(SEASON, at(2026, 10, 28, 20), status)["kind"] == "pre"
    assert current_stop(SEASON, at(2026, 10, 28, 19), status)["kind"] == "season"


def test_season_line_places_byes_the_now_marker_and_the_book():
    line = season_line(SEASON, at(2026, 10, 29, 12), status=all_saved)
    kinds = [item["kind"] for item in line["items"]]
    assert kinds[0] == "preseason" and kinds[-1] == "book"
    weeks = [item.get("week") for item in line["items"] if item["kind"] in ("week", "bye")]
    assert weeks == [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13], "weeks 8, 11 and 12 are byes"
    byes = [item for item in line["items"] if item["kind"] == "bye"]
    assert byes[0]["date"].startswith("2026-10-24"), "the bye takes the Saturday of its week"
    at_now = kinds.index("now")
    assert line["items"][at_now - 1]["kind"] == "bye" and line["items"][at_now + 1]["week"] == 9, "now sits after the bye and before Georgia's week"
    assert line["current"]["kind"] == "pre"
    assert line["items"][-1]["state"] == "to_come" and line["items"][-1]["href"] is None


def test_week_items_carry_the_three_stops_with_dates_states_and_hrefs():
    line = season_line(SEASON, at(2026, 10, 29, 12), status=all_saved)
    by_week = {item["week"]: item for item in line["items"] if item["kind"] == "week"}
    texas = by_week[7]
    assert texas["result"] == {"usPoints": 27, "themPoints": 24, "won": True}
    assert texas["stops"]["pre"]["state"] == "saved" and texas["stops"]["pre"]["href"] == "#program=7?tab=pre"
    assert texas["stops"]["pre"]["date"].startswith("2026-10-15T06:00")
    assert texas["stops"]["game"]["state"] == "done" and texas["stops"]["game"]["href"] == "#archive=7"
    assert texas["stops"]["post"]["state"] == "saved" and texas["stops"]["post"]["href"] == "#postgame=7" and texas["stops"]["post"]["date"].startswith("2026-10-19")
    georgia = by_week[9]
    assert georgia["stops"]["pre"]["state"] == "live" and georgia["stops"]["pre"]["href"] == "#program=9"
    assert georgia["stops"]["game"]["state"] == "to_come" and georgia["stops"]["game"]["href"] is None
    assert georgia["stops"]["post"]["state"] == "to_come" and georgia["stops"]["post"]["href"] is None
    assert by_week[10]["stops"]["pre"]["state"] == "open", "a week ahead is open to look at"


def test_a_game_played_before_the_lock_shows_no_pre_stop():
    def status(g: GameRow) -> Status:
        s = all_saved(g)
        if g.game_id in (1, 2):
            s.pre_locked = False
        return s

    line = season_line(SEASON, at(2026, 10, 29, 12), status=status)
    week1 = next(item for item in line["items"] if item.get("week") == 1)
    assert week1["stops"]["pre"]["state"] == "missing" and week1["stops"]["pre"]["href"] is None


def test_a_live_post_carries_its_checks_and_backstop():
    played = [g if g.game_id != 9 else game(9, 9, g.kickoff, "Georgia", "neutral", completed=True, us=20, them=27) for g in SEASON]

    def status(g: GameRow) -> Status:
        s = all_saved(g)
        if g.game_id == 9:
            s.post_locked = False
            s.post_locked_at = None
            s.checks = Checks(final=True, poll=True, recap=False)
        return s

    line = season_line(played, at(2026, 11, 1, 9), status=status)
    georgia = next(item for item in line["items"] if item.get("week") == 9)
    post = georgia["stops"]["post"]
    assert post["state"] == "live" and post["href"] == "#postgame=9"
    assert post["checks"] == {"final": True, "poll": True, "recap": False}
    assert post["backstop"].startswith("2026-11-03T06:00")
    assert line["current"]["kind"] == "post"


def test_the_book_opens_when_every_post_is_closed():
    played = [game(g.game_id, g.week, g.kickoff, g.opponent, g.home_away, completed=True, us=1, them=0) for g in SEASON]
    line = season_line(played, at(2026, 12, 5, 12), status=all_saved, book_href="#book")  # rollover R3: the season in review leads once it is over
    assert line["items"][-1] == {"kind": "book", "state": "open", "href": "#book", "label": "Season book", "date": None}
    assert line["current"]["kind"] == "book" and line["current"]["href"] == "#book"


def test_empty_season_has_a_preseason_and_a_book_only():
    line = season_line([], at(2026, 8, 1, 12), status=all_saved)
    assert [item["kind"] for item in line["items"]] == ["preseason", "now", "book"]
    assert line["current"]["kind"] == "season"
