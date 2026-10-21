"""The conference race (F8 feature 1, owner 2026-10-21): the lines, the games left, the best records, clinched and out,
the four lines in words, who has to lose, the week's games that help, the title game left out, the memo."""

from __future__ import annotations

from app.cfbd.models import Game
from app.services import race as race_module
from app.services.race import SPOTS, conference_games, lines_of, our_lines, race, status_of, watch_list

CONF = "Biscuit Belt"
OTHER = "Gravy Coast"


def game(gid: int, week: int, home: str, away: str, home_pts: int | None = None, away_pts: int | None = None, *, conf: str = CONF, conf_game: bool = True, notes: str | None = None, season_type: str = "regular") -> Game:
    done = home_pts is not None and away_pts is not None
    return Game.model_validate(
        {
            "id": gid,
            "season": 2026,
            "week": week,
            "seasonType": season_type,
            "startDate": f"2026-{9 + week // 5:02d}-{(week * 7) % 28 + 1:02d}T19:30:00.000Z",
            "completed": done,
            "conferenceGame": conf_game,
            "homeTeam": home,
            "homeConference": conf,
            "homePoints": home_pts,
            "awayTeam": away,
            "awayConference": conf,
            "awayPoints": away_pts,
            "notes": notes,
        }
    )


def week9() -> list[Game]:
    """Four teams after five rounds of a six-team league, three conference games left each (the mock's shape):
    Silver 5-0, Diner 4-1, Swamp 4-1, Armadillo 4-1, Bass 3-2, Apple 3-2 ... then the rest."""
    g = []
    played = [
        ("Silver", "Bass"), ("Silver", "Apple"), ("Silver", "Bagel"), ("Silver", "Cedar"), ("Silver", "Mill"),
        ("Diner", "Bass"), ("Diner", "Apple"), ("Diner", "Bagel"), ("Diner", "Cedar"), ("Mill", "Diner"),
        ("Swamp", "Bass"), ("Swamp", "Apple"), ("Swamp", "Bagel"), ("Swamp", "Cedar"), ("Mill", "Swamp"),
        ("Armadillo", "Bass"), ("Armadillo", "Apple"), ("Armadillo", "Bagel"), ("Armadillo", "Cedar"), ("Mill", "Armadillo"),
        ("Bass", "Bagel"), ("Bass", "Cedar"), ("Bass", "Mill"), ("Apple", "Bagel"), ("Apple", "Cedar"), ("Apple", "Mill"),
        ("Bagel", "Cedar"), ("Bagel", "Mill"), ("Cedar", "Mill"),
    ]
    gid = 100
    for index, (winner, loser) in enumerate(played):
        week = 1 + index // 6
        gid += 1
        g.append(game(gid, week, winner, loser, 28, 14))
    # Bass and Apple beat the bottom three only; recount: Bass beat Bagel, Cedar, Mill (3 wins) and lost to Silver, Diner,
    # Swamp, Armadillo (4 losses); Apple likewise; Bagel beat Cedar and Mill; Cedar beat Mill. The top four beat all four
    # below them and Silver beat nobody above it yet: the games among the top four are the ones left.
    left = [
        (9, "Diner", "Swamp"), (9, "Bass", "Armadillo"), (9, "Apple", "Silver"),
        (10, "Swamp", "Bagel"), (10, "Silver", "Armadillo"), (10, "Diner", "Cedar"),
        (11, "Avalanche", "Swamp"), (11, "Diner", "Armadillo"), (11, "Silver", "Diner"),
    ]
    for week, home, away in left:
        gid += 1
        g.append(game(gid, week, home, away))
    return g


def test_the_lines_count_conference_games_only_and_the_title_game_stays_out():
    games = week9()
    games.append(game(900, 9, "Swamp", "Outsider", conf="Gravy Coast", conf_game=False))  # a non-conference game
    games.append(game(901, 15, "Silver", "Diner", notes="Biscuit Belt Championship"))  # the title game, left out
    games.append(game(902, 3, "Swamp", "Nobody", 10, 10))  # a tie counts for nobody
    lines = lines_of(games, CONF)
    assert sorted(lines) == ["Apple", "Armadillo", "Avalanche", "Bagel", "Bass", "Cedar", "Diner", "Mill", "Nobody", "Silver", "Swamp"]
    assert (lines["Silver"].wins, lines["Silver"].losses, len(lines["Silver"].left), lines["Silver"].best) == (5, 0, 3, 8)
    assert (lines["Swamp"].wins, lines["Swamp"].losses, len(lines["Swamp"].left), lines["Swamp"].best) == (4, 1, 3, 7)
    assert (lines["Bass"].wins, lines["Bass"].losses, len(lines["Bass"].left)) == (3, 4, 1)
    assert all(g.id != 901 for g in conference_games(games, CONF)) and all(g.id != 900 for g in conference_games(games, CONF))


def test_status_by_counting_and_by_playing_the_games_out():
    lines = lines_of(week9(), CONF)
    assert status_of(lines, "Silver")["status"] == "alive"  # 5-0 with three left: Diner and Swamp can both reach 7, and Silver's worst is 5
    assert status_of(lines, "Bagel")["status"] == "out"  # 2-5 with one left can reach 3; Silver and Diner already have 4 and 5
    assert status_of(lines, "Swamp")["status"] == "alive"
    # a settled race: nothing left, the top two have clinched, the rest are out
    settled = [g for g in week9() if g.completed] + [game(300, 9, "Diner", "Swamp", 21, 20), game(301, 9, "Silver", "Apple", 30, 3)]
    lines = lines_of(settled, CONF)
    assert status_of(lines, "Silver")["status"] == "clinched" and status_of(lines, "Diner")["status"] == "clinched"
    assert status_of(lines, "Swamp")["status"] == "out" and status_of(lines, "Armadillo")["status"] == "out"
    # a tie at the line: two teams level on the last day with nothing to separate them in the arithmetic
    tie = [g for g in week9() if g.completed] + [game(300, 9, "Swamp", "Diner", 21, 20), game(301, 9, "Silver", "Apple", 30, 3), game(302, 9, "Armadillo", "Bass", 9, 7)]
    lines = lines_of(tie, CONF)
    assert status_of(lines, "Silver")["status"] == "clinched"
    assert status_of(lines, "Swamp")["status"] == "tiebreaker" and status_of(lines, "Armadillo")["status"] == "tiebreaker", "5-1 and 5-1 for one spot: a tiebreaker, said so"


def test_our_lines_in_words():
    lines = lines_of(week9(), CONF)
    out = our_lines(lines, "Swamp", "alive")
    by_key = {line["key"]: line for line in out}
    assert by_key["winOut"]["lead"] == "Win out (3 left)"
    assert by_key["winOut"]["text"] == "in, unless Diner and Armadillo win out too; then a tiebreaker.", "Silver may finish above us: two spots"
    assert by_key["allButOne"]["lead"] == "Win all but one" and by_key["allButOne"]["text"] == "in only if Diner loses twice more and Armadillo loses once more.", by_key["allButOne"]
    assert by_key["next"]["lead"] == "Beat Diner" and "no worse than" in by_key["next"]["text"] and "no better than" in by_key["next"]["text"]
    assert by_key["clinch"]["lead"] == "Clinch number" and by_key["clinch"]["text"].startswith("5: ") and "counts one" in by_key["clinch"]["text"]
    assert "no worse than third" in by_key["next"]["text"], "a win Saturday with Diner beaten: Silver and Armadillo can still be level or above"
    assert our_lines(lines, "Swamp", "clinched") == [] and our_lines(lines, "Swamp", "out") == []
    assert our_lines(lines, "Nobody", "alive") == []


def test_the_weeks_games_that_help_us():
    lines = lines_of(week9(), CONF)
    rows = watch_list(lines, "Swamp", 9, "alive")
    assert rows[0]["ours"] is True and rows[0]["pullFor"] == "Swamp" and {rows[0]["home"], rows[0]["away"]} == {"Diner", "Swamp"}
    others = {(r["home"], r["away"]): r for r in rows[1:]}
    assert ("Bass", "Armadillo") in others and others[("Bass", "Armadillo")]["pullFor"] == "Bass", "an Armadillo loss takes a team level with us out of the way"
    assert "loss by Armadillo" in others[("Bass", "Armadillo")]["why"]
    assert ("Apple", "Silver") in others and others[("Apple", "Silver")]["pullFor"] == "Apple", "a Silver loss opens the spot above"
    assert all(r["ours"] is False for r in rows[1:]) and len(rows) == 3
    assert watch_list(lines, "Swamp", 10, "alive")[0]["ours"] is True
    assert watch_list(lines, "Swamp", 9, "out") == [] and watch_list(lines, "Swamp", None, "alive") == []


def test_the_race_as_the_pages_see_it():
    games = week9()
    result = race(games, "Swamp", CONF, week=9, stamp="2026-10-21T10:00:00Z")
    assert result is not None and result["conference"] == CONF and result["spots"] == SPOTS and result["week"] == 9 and result["settled"] is False
    top = [row["team"] for row in result["standings"][:4]]
    assert top[0] == "Silver" and set(top[1:]) == {"Armadillo", "Diner", "Swamp"}
    us = result["us"]
    assert us["team"] == "Swamp" and us["confWins"] == 4 and us["confLosses"] == 1 and us["left"] == 3 and us["best"] == 7 and us["status"] == "alive" and us["exact"] is True
    assert [row["status"] for row in result["standings"] if row["team"] == "Bagel"] == ["out"]
    assert {line["key"] for line in result["lines"]} >= {"winOut", "allButOne", "next", "clinch"}
    assert result["watch"][0]["ours"] is True and len(result["helps"]) == len(result["watch"])
    assert race(games, "Swamp", CONF, week=9, stamp="2026-10-21T10:00:00Z") is result, "the same games again: the same answer, not played out again"
    assert race(games, "Swamp", "", week=9) is None and race(games, "Outsider", CONF) is None
    assert race(games, "Swamp", CONF)["week"] == 9, "the week defaults to our next conference game's"
    race_module._MEMO.clear()


def test_a_big_early_season_falls_back_to_counting():
    games = []
    gid = 0
    teams = [f"T{i}" for i in range(16)]
    for week in range(1, 9):
        for i in range(0, 16, 2):
            gid += 1
            games.append(game(gid, week, teams[(i + week) % 16], teams[(i + 1 + week) % 16]))
    result = race(games, "T0", CONF, week=1)
    assert result is not None and result["us"]["status"] == "alive" and result["us"]["exact"] is False
    assert all(row["status"] == "alive" for row in result["standings"])
