"""Facts about the made-up league's games, read from the same answers the fake CFBD serves, so a
test can say "the score the archive shows is the game's score" without writing the number down.
Public release Phase 3: these replace the numbers the tests used to copy from the recordings."""

from __future__ import annotations

from typing import Any

from tests.conftest import ROLES, fixture_payload

US = "Swampwater Tech"


def game(game_id: int | str, name: str = "games_team") -> dict[str, Any]:
    """A game row from a /games answer by id."""
    return next(g for g in fixture_payload(name) if str(g.get("id")) == str(game_id))


def last_game() -> dict[str, Any]:
    return game(ROLES["LASTGAME"])


def next_game_row() -> dict[str, Any]:
    return next(g for g in fixture_payload("games_team") if not g.get("completed"))


def scores(row: dict[str, Any], us: str = US) -> tuple[int, int]:
    """(ours, theirs) for a final game row."""
    home = row["homeTeam"] == us
    return (row["homePoints"], row["awayPoints"]) if home else (row["awayPoints"], row["homePoints"])


def live_doc() -> dict[str, Any]:
    """The live document of our last game (final)."""
    return fixture_payload("live_plays")


def live_counts(doc: dict[str, Any] | None = None) -> tuple[int, int]:
    """(plays, drives) in a live document."""
    doc = doc or live_doc()
    drives = [d for d in doc.get("drives") or [] if isinstance(d, dict)]
    return sum(len(d.get("plays") or []) for d in drives), len(drives)


def live_team(team: str = US, doc: dict[str, Any] | None = None) -> dict[str, Any]:
    doc = doc or live_doc()
    return next(t for t in doc.get("teams") or [] if t.get("team") == team)


def wp_points() -> int:
    return len(fixture_payload("metrics_wp"))


def team_box(team: str = US, name: str = "games_teams") -> dict[str, str]:
    """A /games/teams side as {category: stat}."""
    side = next(t for t in fixture_payload(name)[0]["teams"] if t["team"] == team)
    return {s["category"]: s["stat"] for s in side["stats"]}


def abbreviation(school: str) -> str:
    return next(t["abbreviation"] for t in fixture_payload("teams_fbs") if t["school"] == school)


def team_id(school: str) -> int:
    return next(t["id"] for t in fixture_payload("teams_fbs") if t["school"] == school)


def ap_rank(school: str) -> int | None:
    """The team's rank in the AP poll of the `rankings` answer, or None when unranked."""
    for week in fixture_payload("rankings"):
        for poll in week.get("polls") or []:
            if poll.get("poll") == "AP Top 25":
                return next((r["rank"] for r in poll["ranks"] if r["school"] == school), None)
    return None


def line(game_id: int | str, name: str = "lines") -> dict[str, Any]:
    """The first provider's line for a game."""
    return next(g for g in fixture_payload(name) if str(g["id"]) == str(game_id))["lines"][0]


def outlet(game_id: int | str, name: str = "games_media") -> str | None:
    return next((m["outlet"] for m in fixture_payload(name) if str(m["id"]) == str(game_id) and m.get("mediaType") == "tv"), None)


def record(school: str, name: str = "records_all") -> dict[str, Any]:
    return next(r for r in fixture_payload(name) if r["team"] == school)


def capacity(school: str) -> int:
    return next(t["location"]["capacity"] for t in fixture_payload("teams_fbs") if t["school"] == school)


def ppa_play_counts(team: str = US) -> dict[str, int]:
    """Each player's PPA play count this season (the simulated truth the app's total/average must recover)."""
    from app.demo.render import _ppa_season
    from app.demo.upstream import TEST_NOW
    from tests.conftest import league

    world = league()
    totals, team_of, _ = _ppa_season(world, world.final(world.season, TEST_NOW))
    tid = world.league.team(team).id
    return {world.league.players[str(pid)].name: c["all_n"] for pid, c in totals.items() if team_of[pid] == tid and str(pid) in world.league.players}


def returning(team: str = US) -> dict[str, Any]:
    return next(r for r in fixture_payload("player_returning_national") if r["team"] == team)
