"""Bowl and playoff games (Phase 15): one place that knows how CFBD numbers the postseason.

Recorded 2025 postseason (tests/fixtures/cfbd/*_post*.json, 2026-09-27):
- `/games?year&team` without seasonType already returns the postseason games; so does `/rankings`.
- Every postseason game is `seasonType: "postseason"`, `week: 1`, from mid-December to the title game
  in January. A playoff team plays up to four of them, all "week 1".
- A week-keyed call (`/plays`, `/drives`, `/ppa/players/games`, `/metrics/wp/pregame`) asked with
  `seasonType=postseason&week=1&team=X` answers for every postseason game X played, so the answer must
  be cut to the one game (by gameId, or by opponent where the rows carry no id). Without seasonType
  the same call means regular-season week 1.
- `/games/teams` and `/games/players` take `id`, so a postseason box score is asked for by game id.

So a game is keyed by its week in the regular season (unchanged cache keys and part names) and by its
id in the postseason, and postseason games sort after the regular season by kickoff.
"""

from __future__ import annotations

from typing import Any

POSTSEASON = "postseason"


def is_post(game: Any) -> bool:
    return (getattr(game, "season_type", None) or "regular") == POSTSEASON


def order(game: Any) -> tuple[int, int, str]:
    """Sort key: the regular season by week, then the postseason by kickoff."""
    post = is_post(game)
    return (1 if post else 0, 0 if post else (getattr(game, "week", None) or 0), getattr(game, "start_date", None) or "")


def tag(game: Any) -> str:
    """A part-name suffix unique within a season: the week, or p<id> for a postseason game."""
    return f"p{game.id}" if is_post(game) else str(game.week)


def week_params(game: Any, year: int, team: str) -> dict[str, Any]:
    """Parameters for a week-keyed endpoint (plays, drives, player PPA by game, pregame odds, weather,
    ppa games). A postseason game adds seasonType; its answer covers every postseason game of the team
    and must go through only_game / only_opponent."""
    params: dict[str, Any] = {"year": year, "week": game.week, "team": team}
    if is_post(game):
        params["seasonType"] = POSTSEASON
    return params


def box_params(game: Any, year: int, team: str) -> dict[str, Any]:
    """Parameters for /games/teams and /games/players: the week in the regular season (the cache keys
    the app has always used), the game id in the postseason."""
    if is_post(game):
        return {"id": game.id}
    return {"year": year, "week": game.week, "team": team}


def only_game(records: list[Any], game: Any, attr: str = "game_id") -> list[Any]:
    """Rows of one game from a week-keyed answer. Regular-season rows pass through (a team plays once
    a week); postseason rows are kept only when their game id matches."""
    if not is_post(game):
        return records
    return [r for r in records if getattr(r, attr, None) == game.id]


def only_opponent(records: list[Any], game: Any, opponent: str | None) -> list[Any]:
    """For rows with no game id (player PPA by game): postseason rows against this opponent only."""
    if not is_post(game) or not opponent:
        return records
    return [r for r in records if getattr(r, "opponent", None) == opponent]


def poll_order(week: Any) -> tuple[int, int]:
    """Poll weeks in time order: the regular season, then the postseason's final poll."""
    return (1 if (getattr(week, "season_type", None) or "regular") == POSTSEASON else 0, getattr(week, "week", None) or 0)


def label(game: Any) -> str | None:
    """How a postseason game is named on the page: CFBD's notes ("Vrbo Fiesta Bowl", "College Football
    Playoff Semifinal at ..."), or None for a regular-season game."""
    if not is_post(game):
        return None
    notes = getattr(game, "notes", None)
    return notes.strip() if isinstance(notes, str) and notes.strip() else "Bowl game"


def playoff_round(game: Any) -> str | None:
    """The playoff round: CFBD's bracket block when present (roundName), else read from the notes;
    None when the game is not a playoff game."""
    block = getattr(game, "playoff", None)
    if block is not None and (getattr(block, "competition", None) or "").lower() == "cfp":
        name = getattr(block, "round_name", None)
        if isinstance(name, str) and name.strip():
            return name.strip()
    notes = (getattr(game, "notes", None) or "").lower()
    if "college football playoff" not in notes and "cfp" not in notes:
        return None
    if "championship" in notes and "national" in notes:
        return "Championship"
    for word, name in (("semifinal", "Semifinal"), ("quarterfinal", "Quarterfinal"), ("first round", "First round")):
        if word in notes:
            return name
    return "Playoff"


def opponent_of(game: Any, team: str | None) -> str | None:
    if game is None or not team:
        return None
    if getattr(game, "home_team", None) == team:
        return getattr(game, "away_team", None)
    if getattr(game, "away_team", None) == team:
        return getattr(game, "home_team", None)
    return None


def season_params(year: int, team: str | None, games: list[Any]) -> dict[str, Any]:
    """Parameters for a whole-season per-game list (/ppa/games): once the schedule holds a postseason
    game, ask for both season types so the bowl is in it; before that, the key the app always used."""
    params: dict[str, Any] = {"year": year, "team": team}
    if any(is_post(g) for g in games):
        params["seasonType"] = "both"
    return params
