"""Win probability (L8) and play value (L9) from CFBD's metrics: the play-by-play win
probability of one game, team PPA (predicted points added) per game, and player PPA for one
week. The helpers shape rows for the program page, the live sheet's postgame mode, and the
archive; the service answers `/api/games/{id}/analytics`.

Until the key reaches Tier 2 the in-game numbers do not exist: `/metrics/wp` fills in after the
final, and per-play PPA rides the live feed only. Every block says whether it has data."""

from __future__ import annotations

import asyncio
from typing import Any

from app.cache import DataKind
from app.cfbd.client import CfbdClient
from app.cfbd.models import Game, PlayerGamePpa, PlayWinProbability, TeamGamePpa
from app.config import Settings
from app.services import gamekeys, recap16
from app.services.depth2 import advanced_box
from app.services.parts import Assembled, Part, PartFetcher, assemble, statuses

SIDES = ("overall", "passing", "rushing")
PLAYER_LIMIT = 12


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def wp_series(records: list[PlayWinProbability]) -> list[dict[str, Any]]:
    """The home side's chance per play in play order. Points without a usable probability are dropped."""
    rows: list[dict[str, Any]] = []
    for record in records:
        wp = _num(record.home_win_probability)
        if wp is None or not 0.0 <= wp <= 1.0:
            continue
        rows.append(
            {
                "play": record.play_number if isinstance(record.play_number, int) else None,
                "homeWp": round(wp, 4),
                "homeScore": record.home_score,
                "awayScore": record.away_score,
                "text": record.play_text,
                "down": record.down,
                "distance": record.distance,
            }
        )
    rows.sort(key=lambda p: p["play"] if p["play"] is not None else 10**9)
    return rows


def side_dict(side: Any) -> dict[str, float | None]:
    return {key: _num(getattr(side, key, None)) for key in SIDES}


def team_game_rows(records: list[TeamGamePpa], team: str) -> list[dict[str, Any]]:
    """One row per game for a team: offense and defense PPA per play, in week order."""
    rows = [
        {"gameId": r.game_id, "week": r.week, "seasonType": r.season_type or "regular", "opponent": r.opponent, "offense": side_dict(r.offense), "defense": side_dict(r.defense)}
        for r in records
        if r.team == team
    ]
    rows.sort(key=lambda r: (r["week"] if isinstance(r["week"], int) else 10**6, r["gameId"]))
    return rows


def season_average(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def avg(side: str, key: str) -> float | None:
        values = [r[side][key] for r in rows if r[side].get(key) is not None]
        return round(sum(values) / len(values), 3) if values else None

    return {"games": len(rows), "offense": {k: avg("offense", k) for k in SIDES}, "defense": {k: avg("defense", k) for k in SIDES}}


def player_rows(records: list[PlayerGamePpa], team: str, opponent: str | None = None, limit: int = PLAYER_LIMIT) -> list[dict[str, Any]]:
    """A team's players for one game (or one week when the opponent is unknown), best value first."""
    rows: list[dict[str, Any]] = []
    for r in records:
        if r.team != team or (opponent and r.opponent != opponent):
            continue
        avg = r.average_ppa
        rows.append(
            {
                "playerId": r.id,
                "name": r.name,
                "position": r.position,
                "opponent": r.opponent,
                "all": _num(avg.all) if avg else None,
                "pass": _num(avg.pass_) if avg else None,
                "rush": _num(avg.rush) if avg else None,
            }
        )
    rows.sort(key=lambda p: (p["all"] is None, -(p["all"] or 0.0)))
    return rows[:limit]


class AnalyticsService:
    """`/api/games/{id}/analytics`: the win probability series and the play value of one of our games."""

    def __init__(self, client: CfbdClient, settings: Settings) -> None:
        self.client = client
        self.settings = settings
        self.fetcher = PartFetcher(client, 4)

    @property
    def year(self) -> int:
        return self.settings.season

    @property
    def team(self) -> str:
        return self.settings.team

    async def game(self, game_id: int) -> Assembled | None:
        """None when the game is not on our schedule. A schedule that cannot be loaded at all
        comes back as an all-failed answer so the route can say why."""
        schedule = await self.fetcher.fetch("schedule", "/games", {"year": self.year, "team": self.team}, Game, DataKind.SCHEDULE)
        parts: dict[str, Part] = {"schedule": schedule}
        now = self.client._clock()
        game = next((g for g in schedule.records if g.id == game_id), None)
        if game is None:
            if schedule.ok:
                return None
            return assemble({"gameId": game_id, "parts": statuses(parts, now)}, parts)

        home_is_us = game.home_team == self.team
        opponent = game.away_team if home_is_us else game.home_team
        wp_kind = DataKind.FINISHED_GAME if game.completed else DataKind.SEASON_STATS
        fetches = [
            self.fetcher.fetch("wp", "/metrics/wp", {"gameId": game_id}, PlayWinProbability, wp_kind),
            self.fetcher.fetch("ppaUs", "/ppa/games", gamekeys.season_params(self.year, self.team, schedule.records), TeamGamePpa, DataKind.SEASON_STATS),
        ]
        if opponent:
            fetches.append(self.fetcher.fetch("ppaThem", "/ppa/games", gamekeys.season_params(self.year, opponent, schedule.records), TeamGamePpa, DataKind.SEASON_STATS))
        if game.week is not None:  # a bowl's answer covers all the team's bowls; player_rows keeps this opponent's
            fetches.append(self.fetcher.fetch("ppaPlayersUs", "/ppa/players/games", gamekeys.week_params(game, self.year, self.team), PlayerGamePpa, DataKind.SEASON_STATS))
            if opponent:
                fetches.append(self.fetcher.fetch("ppaPlayersThem", "/ppa/players/games", gamekeys.week_params(game, self.year, opponent), PlayerGamePpa, DataKind.SEASON_STATS))
        if game.completed:  # Phase 13: CFBD's advanced box score, by quarter, with player value and usage
            fetches.append(self.fetcher.fetch("advancedBox", "/game/box/advanced", {"id": game_id}, None, DataKind.FINISHED_GAME))
        for part in await asyncio.gather(*fetches):
            parts[part.name] = part

        series = wp_series(parts["wp"].records)
        last = series[-1]["homeWp"] if series else None
        us_rows = team_game_rows(parts["ppaUs"].records, self.team)
        them_rows = team_game_rows(parts["ppaThem"].records, opponent) if "ppaThem" in parts and opponent else []
        this_us = next((r for r in us_rows if r["gameId"] == game_id), None)
        this_them = next((r for r in them_rows if r["gameId"] == game_id), None)
        players_us = player_rows(parts["ppaPlayersUs"].records, self.team, opponent) if "ppaPlayersUs" in parts else []
        players_them = player_rows(parts["ppaPlayersThem"].records, opponent or "", self.team) if "ppaPlayersThem" in parts else []
        now = self.client._clock()
        data = {
            "gameId": game_id,
            "week": game.week,
            "completed": bool(game.completed),
            "homeIsUs": home_is_us,
            "home": game.home_team,
            "away": game.away_team,
            "us": self.team,
            "them": opponent,
            "winProbability": {
                "available": bool(series),
                "spread": _num(parts["wp"].records[0].spread) if parts["wp"].records else None,
                "series": series,
                "usFinal": (last if home_is_us else round(1 - last, 4)) if last is not None else None,
                "note": None if series else ("CFBD posts the play-by-play win probability after the final." if not game.completed else "CFBD has not posted win probability for this game."),
            },
            "ppa": {
                "available": bool(this_us or this_them or players_us or players_them),
                "teams": {"us": this_us, "them": this_them},
                "players": {"us": players_us, "them": players_them},
                "note": None if (this_us or players_us) else ("Play value posts after the final, once CFBD grades the game." if not game.completed else "CFBD has not posted play value for this game."),
            },
            "advancedBox": advanced_box(parts["advancedBox"].fetched.payload if parts["advancedBox"].fetched else None) if "advancedBox" in parts else None,
            "parts": statuses(parts, now),
        }
        recap16.enrich_win_probability(data["winProbability"], home_is_us)  # Phase 16 BX: game time (GX-02) and the biggest swings (GX-09)
        return assemble(data, parts)
