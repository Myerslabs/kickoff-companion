"""The made-up league's stand-ins for the recorded CFBD fixtures, by the same names.

Every recording in the private set (tests/fixtures/cfbd) has a twin here: the same endpoint asked
the equivalent question of the league. the recorded team becomes the demo's own team, the recorded opponent its
next opponent, week 3 its last game, the 2025 postseason the league's previous postseason, and so on.
`league_fixture(world, name)` returns the twin in the recorded envelope ({name, endpoint, params,
status, payload}), so a test can load either set by name.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.demo import names as N
from app.demo.season import World
from app.demo.upstream import TEST_NOW, DemoUpstream

# name -> (endpoint, params with {placeholders}, plan tier the call is made on)
RECORDINGS: dict[str, tuple[str, dict[str, str], int]] = {
    "calendar": ("/calendar", {"year": "{S}"}, 2),
    "calendar_2025": ("/calendar", {"year": "{S-1}"}, 2),
    "coaches_opponent": ("/coaches", {"team": "{OPP}", "year": "{S}"}, 2),
    "drives": ("/drives", {"year": "{S}", "week": "{LASTWEEK}", "team": "{US}"}, 2),
    "drives_post": ("/drives", {"year": "{S-1}", "week": "1", "team": "{POSTTEAM}", "seasonType": "postseason"}, 2),
    "game_box_advanced": ("/game/box/advanced", {"id": "{LASTGAME}"}, 2),
    "game_box_advanced_post": ("/game/box/advanced", {"id": "{POSTGAME}"}, 2),
    "games_media": ("/games/media", {"year": "{S}", "team": "{US}"}, 2),
    "games_media_post": ("/games/media", {"year": "{S-1}", "seasonType": "postseason"}, 2),
    "games_media_week": ("/games/media", {"year": "{S}", "week": "{NEXTWEEK}"}, 2),
    "games_opponent": ("/games", {"year": "{S}", "team": "{OPP}"}, 2),
    "games_players": ("/games/players", {"year": "{S}", "week": "{LASTWEEK}", "team": "{US}"}, 2),
    "games_players_1": ("/games/players", {"year": "{S}", "week": "{FIRSTWEEK}", "team": "{US}"}, 2),
    "games_players_2": ("/games/players", {"year": "{S}", "week": "{SECONDWEEK}", "team": "{US}"}, 2),
    "games_players_post": ("/games/players", {"id": "{POSTGAME}", "year": "{S-1}"}, 2),
    "games_post_2025": ("/games", {"year": "{S-1}", "seasonType": "postseason", "classification": "fbs"}, 2),
    "games_team": ("/games", {"year": "{S}", "team": "{US}"}, 2),
    "games_team_2025_both": ("/games", {"year": "{S-1}", "team": "{POSTTEAM}", "seasonType": "both"}, 2),
    "games_team_2025_default": ("/games", {"year": "{S-1}", "team": "{POSTTEAM}"}, 2),
    "games_teams": ("/games/teams", {"year": "{S}", "week": "{LASTWEEK}", "team": "{US}"}, 2),
    "games_teams_1": ("/games/teams", {"year": "{S}", "week": "{FIRSTWEEK}", "team": "{US}"}, 2),
    "games_teams_2": ("/games/teams", {"year": "{S}", "week": "{SECONDWEEK}", "team": "{US}"}, 2),
    "games_teams_post": ("/games/teams", {"id": "{POSTGAME}", "year": "{S-1}"}, 2),
    "games_weather": ("/games/weather", {"year": "{S}", "team": "{US}"}, 0),
    "games_weather_tier2": ("/games/weather", {"year": "{S}", "week": "{NEXTWEEK}", "team": "{US}"}, 2),
    "games_week": ("/games", {"year": "{S}", "week": "{NEXTWEEK}"}, 2),
    "info": ("/info", {}, 0),
    "info_after": ("/info", {}, 0),
    "lines": ("/lines", {"year": "{S}", "team": "{US}"}, 2),
    "lines_post": ("/lines", {"year": "{S-1}", "team": "{POSTTEAM}", "seasonType": "postseason"}, 2),
    "lines_week": ("/lines", {"year": "{S}", "week": "{NEXTWEEK}"}, 2),
    "live_plays": ("/live/plays", {"gameId": "{LASTGAME}"}, 2),
    "live_plays_finished_game": ("/live/plays", {"gameId": "{LASTGAME}"}, 0),
    "metrics_fg_ep": ("/metrics/fg/ep", {}, 2),
    "metrics_wp": ("/metrics/wp", {"gameId": "{LASTGAME}"}, 2),
    "metrics_wp_post": ("/metrics/wp", {"gameId": "{POSTGAME}"}, 2),
    "metrics_wp_pregame": ("/metrics/wp/pregame", {"year": "{S}", "week": "{NEXTWEEK}", "team": "{US}"}, 2),
    "metrics_wp_pregame_post": ("/metrics/wp/pregame", {"year": "{S-1}", "week": "1", "seasonType": "postseason"}, 2),
    "metrics_wp_pregame_week": ("/metrics/wp/pregame", {"year": "{S}", "week": "{NEXTWEEK}"}, 2),
    "passing_plays_opponent": ("/passing/plays", {"year": "{S}", "team": "{OPP}"}, 2),
    "player_portal": ("/player/portal", {"year": "{S}"}, 2),
    "player_returning": ("/player/returning", {"year": "{S}", "team": "{US}"}, 2),
    "player_returning_national": ("/player/returning", {"year": "{S}"}, 2),
    "player_returning_opponent": ("/player/returning", {"year": "{S}", "team": "{OPP}"}, 2),
    "player_search_name": ("/player/search", {"searchTerm": "{QB}"}, 2),
    "player_search_smith": ("/player/search", {"searchTerm": "Smith", "year": "{S}"}, 2),
    "player_usage": ("/player/usage", {"year": "{S}", "team": "{US}"}, 2),
    "player_usage_opponent": ("/player/usage", {"year": "{S}", "team": "{OPP}"}, 2),
    "plays": ("/plays", {"year": "{S}", "week": "{LASTWEEK}", "team": "{US}"}, 2),
    "plays_post": ("/plays", {"year": "{S-1}", "week": "1", "team": "{POSTTEAM}", "seasonType": "postseason"}, 2),
    "ppa_games": ("/ppa/games", {"year": "{S}", "team": "{US}"}, 2),
    "ppa_games_post": ("/ppa/games", {"year": "{S-1}", "team": "{POSTTEAM}", "seasonType": "both"}, 2),
    "ppa_players_games": ("/ppa/players/games", {"year": "{S}", "week": "{LASTWEEK}", "team": "{US}"}, 2),
    "ppa_players_games_post": ("/ppa/players/games", {"year": "{S-1}", "week": "1", "team": "{POSTTEAM}", "seasonType": "postseason"}, 2),
    "ppa_players_season": ("/ppa/players/season", {"year": "{S}", "team": "{US}"}, 2),
    "ppa_players_season_all": ("/ppa/players/season", {"year": "{S}", "threshold": "50"}, 2),
    "ppa_players_season_opponent": ("/ppa/players/season", {"year": "{S}", "team": "{OPP}"}, 2),
    "ppa_predicted_1_10": ("/ppa/predicted", {"down": "1", "distance": "10"}, 2),
    "ppa_predicted_4_3": ("/ppa/predicted", {"down": "4", "distance": "3"}, 2),
    "rankings": ("/rankings", {"year": "{S}", "week": "{DONEWEEK}"}, 2),
    "rankings_2025_both": ("/rankings", {"year": "{S-1}", "seasonType": "both"}, 2),
    "rankings_2025_default": ("/rankings", {"year": "{S-1}"}, 2),
    "ratings_core": ("/ratings/core", {"year": "{S}"}, 2),
    "ratings_elo": ("/ratings/elo", {"year": "{S}"}, 2),
    "ratings_fpi": ("/ratings/fpi", {"year": "{S}"}, 2),
    "ratings_sp": ("/ratings/sp", {"year": "{S}"}, 2),
    "ratings_sp_conferences": ("/ratings/sp/conferences", {"year": "{S}"}, 2),
    "ratings_srs": ("/ratings/srs", {"year": "{S}"}, 2),
    "ratings_srs_2025": ("/ratings/srs", {"year": "{S-1}"}, 2),
    "records_all": ("/records", {"year": "{S}"}, 2),
    "records_conference": ("/records", {"year": "{S}", "conference": "{CONF}"}, 2),
    "records_team": ("/records", {"year": "{S}", "team": "{US}"}, 2),
    "recruiting_players": ("/recruiting/players", {"year": "{S}", "team": "{US}"}, 2),
    "recruiting_players_2022": ("/recruiting/players", {"year": "{S-4}", "team": "{US}"}, 2),
    "recruiting_players_2023": ("/recruiting/players", {"year": "{S-3}", "team": "{US}"}, 2),
    "recruiting_players_2024": ("/recruiting/players", {"year": "{S-2}", "team": "{US}"}, 2),
    "recruiting_players_2025": ("/recruiting/players", {"year": "{S-1}", "team": "{US}"}, 2),
    "recruiting_players_2027": ("/recruiting/players", {"year": "{S+1}", "team": "{US}"}, 2),
    "recruiting_players_national_2023": ("/recruiting/players", {"year": "{S-3}"}, 2),
    "recruiting_players_national_2024": ("/recruiting/players", {"year": "{S-2}"}, 2),
    "recruiting_players_national_2025": ("/recruiting/players", {"year": "{S-1}"}, 2),
    "recruiting_players_national_2026": ("/recruiting/players", {"year": "{S}"}, 2),
    "recruiting_players_national_2027": ("/recruiting/players", {"year": "{S+1}"}, 2),
    "recruiting_players_opponent_2023": ("/recruiting/players", {"year": "{S-3}", "team": "{OPP}"}, 2),
    "recruiting_players_opponent_2024": ("/recruiting/players", {"year": "{S-2}", "team": "{OPP}"}, 2),
    "recruiting_players_opponent_2025": ("/recruiting/players", {"year": "{S-1}", "team": "{OPP}"}, 2),
    "recruiting_players_opponent_2026": ("/recruiting/players", {"year": "{S}", "team": "{OPP}"}, 2),
    "recruiting_teams": ("/recruiting/teams", {"year": "{S}"}, 2),
    "recruiting_teams_2027": ("/recruiting/teams", {"year": "{S+1}"}, 2),
    "roster": ("/roster", {"team": "{US}", "year": "{S}"}, 2),
    "roster_2022": ("/roster", {"team": "{US}", "year": "{S-4}"}, 2),
    "roster_2023": ("/roster", {"team": "{US}", "year": "{S-3}"}, 2),
    "roster_2024": ("/roster", {"team": "{US}", "year": "{S-2}"}, 2),
    "roster_2025": ("/roster", {"team": "{US}", "year": "{S-1}"}, 2),
    "roster_opponent": ("/roster", {"team": "{OPP}", "year": "{S}"}, 2),
    "rushing_plays_opponent": ("/rushing/plays", {"year": "{S}", "team": "{OPP}"}, 2),
    "scoreboard": ("/scoreboard", {"classification": "fbs"}, 0),
    "scoreboard_fbs": ("/scoreboard", {"classification": "fbs"}, 2),
    "stats_categories": ("/stats/categories", {}, 2),
    "stats_player_season_all_defensive": ("/stats/player/season", {"year": "{S}", "category": "defensive"}, 2),
    "stats_player_season_all_interceptions": ("/stats/player/season", {"year": "{S}", "category": "interceptions"}, 2),
    "stats_player_season_all_kicking": ("/stats/player/season", {"year": "{S}", "category": "kicking"}, 2),
    "stats_player_season_all_passing": ("/stats/player/season", {"year": "{S}", "category": "passing"}, 2),
    "stats_player_season_all_punting": ("/stats/player/season", {"year": "{S}", "category": "punting"}, 2),
    "stats_player_season_all_receiving": ("/stats/player/season", {"year": "{S}", "category": "receiving"}, 2),
    "stats_player_season_all_rushing": ("/stats/player/season", {"year": "{S}", "category": "rushing"}, 2),
    "stats_player_season_conference": ("/stats/player/season", {"year": "{S}", "conference": "{CONF}"}, 2),
    "stats_player_season_team": ("/stats/player/season", {"year": "{S}", "team": "{US}"}, 2),
    "stats_season_advanced_fbs": ("/stats/season/advanced", {"year": "{S}", "classification": "fbs"}, 2),
    "stats_season_advanced_team": ("/stats/season/advanced", {"year": "{S}", "team": "{US}"}, 2),
    "stats_season_fbs": ("/stats/season", {"year": "{S}", "classification": "fbs"}, 2),
    "stats_season_team": ("/stats/season", {"year": "{S}", "team": "{US}"}, 2),
    "talent": ("/talent", {"year": "{S}"}, 2),
    "teams_conference": ("/teams", {"conference": "{CONF}"}, 2),
    "teams_fbs": ("/teams/fbs", {"year": "{S}"}, 2),
    "teams_matchup": ("/teams/matchup", {"team1": "{US}", "team2": "{OPP}"}, 2),
    "venues": ("/venues", {}, 2),
    "wepa_players_kicking": ("/wepa/players/kicking", {"year": "{S}"}, 2),
    "wepa_players_passing": ("/wepa/players/passing", {"year": "{S}"}, 2),
    "wepa_players_passing_2025": ("/wepa/players/passing", {"year": "{S-1}"}, 2),
    "wepa_players_rushing": ("/wepa/players/rushing", {"year": "{S}"}, 2),
    "wepa_players_rushing_2025": ("/wepa/players/rushing", {"year": "{S-1}"}, 2),
    "wepa_team_season": ("/wepa/team/season", {"year": "{S}"}, 2),
    "wepa_team_season_2025": ("/wepa/team/season", {"year": "{S-1}"}, 2),
}


def roles(world: World, now: datetime = TEST_NOW) -> dict[str, str]:
    """The values the placeholders stand for at `now`."""
    league = world.league
    season = world.season
    us = league.team(N.OUR_SCHOOL)
    data = world.seasons[season]
    ours = sorted((r for r in data.records if us.id in (r.slot.home, r.slot.away) and r.slot.season_type == "regular"), key=lambda r: r.slot.start)
    done = [r for r in ours if r.end <= now]
    ahead = [r for r in ours if r.end > now]
    last = done[-1] if done else ours[0]
    nxt = ahead[0] if ahead else ours[-1]
    opp = league.by_id[nxt.slot.away if nxt.slot.home == us.id else nxt.slot.home]
    prev = world.seasons[season - 1]
    final = next(r for r in prev.records if r.slot.playoff and r.slot.playoff.get("round") == "championship")
    champion = final.slot.home if final.home_points > final.away_points else final.slot.away
    qb = league.players[str(data.sides[us.id].qbs[0])]
    rb = league.players[str(data.sides[us.id].rbs[0])]
    their_qb = league.players[str(data.sides[opp.id].qbs[0])]
    weeks_done = [r.slot.week for r in data.records if r.end <= now and r.slot.season_type == "regular"]
    return {
        "S": str(season), "S-1": str(season - 1), "S-2": str(season - 2), "S-3": str(season - 3), "S-4": str(season - 4), "S+1": str(season + 1),
        "US": us.school, "OPP": opp.school, "CONF": us.conference, "LASTWEEK": str(last.slot.week), "NEXTWEEK": str(nxt.slot.week),
        "FIRSTWEEK": str(ours[0].slot.week), "SECONDWEEK": str(ours[1].slot.week), "LASTGAME": str(last.id), "POSTGAME": str(final.id),
        "POSTTEAM": league.by_id[champion].school, "QB": qb.last, "DONEWEEK": str(max(weeks_done) if weeks_done else 1),
        # public release Phase 7: the players tests follow, so a roster change never breaks them by id
        "QBID": qb.id, "QBNAME": f"{qb.first} {qb.last}", "RBID": rb.id, "RBNAME": f"{rb.first} {rb.last}",
        "OPPQBID": their_qb.id, "OPPQBNAME": f"{their_qb.first} {their_qb.last}",
    }


def resolve(template: dict[str, str], values: dict[str, str]) -> dict[str, str]:
    out = {}
    for key, value in template.items():
        if value.startswith("{") and value.endswith("}"):
            value = values[value[1:-1]]
        out[key] = value
    return out


def league_fixture(world: World, name: str, now: datetime = TEST_NOW, values: dict[str, str] | None = None) -> dict[str, Any]:
    """The league's twin of a recorded fixture, in the recorded envelope."""
    endpoint, template, tier = RECORDINGS[name]
    params = resolve(template, values or roles(world, now))
    upstream = DemoUpstream(world, lambda: now, tier=tier)

    class _Request:
        class url:  # noqa: N801 - mimics httpx.Request.url
            path = endpoint

    _Request.url.params = params  # type: ignore[attr-defined]
    response = upstream.handler(_Request)
    status = response.status_code
    payload = response.json() if status == 200 else None
    records = len(payload) if isinstance(payload, list) else None
    recorded = {k: int(v) if isinstance(v, str) and v.isdigit() else v for k, v in params.items()}  # numbers as the client sent them
    envelope = {"name": name, "endpoint": endpoint, "params": recorded, "status": status, "records": records, "skipped": 0,
                "problems": [], "fetched_at": now.isoformat(timespec="seconds"), "payload": payload}
    if status != 200:
        envelope["body"] = response.text
    return envelope
