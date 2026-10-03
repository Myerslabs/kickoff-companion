"""A stand-in for the CFBD API, answered from the made-up league.

`DemoUpstream.handler` is an httpx MockTransport handler: the app's own client calls it exactly as
it would call CFBD, through the quota guard and the parsers. The plan (`tier`) gates the same
endpoints CFBD gates (weather and the scoreboard need Tier 1, live play-by-play Tier 2) with the
same 401, and `/info` reports the calls made, so the Data sources page and the locked states can be
exercised without a key.

`load_world` builds the league once and keeps it in a pickle keyed by a hash of this package's
source, so a changed generator never serves a stale league.
"""

from __future__ import annotations

import hashlib
import json
import logging
import pickle
import threading
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.demo import render as R
from app.demo import render_live as RL
from app.demo.season import World, build_world

log = logging.getLogger("kickoff.demo")

TEST_SEASON = 2026
TEST_SEED = 2026
# The moment the test fixtures describe: the Monday after week 3, like the recorded set.
TEST_NOW = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)

ROUTES: dict[str, Callable[[World, dict[str, str], datetime], Any]] = {
    "/calendar": R.r_calendar,
    "/teams/fbs": R.r_teams_fbs,
    "/teams": R.r_teams,
    "/venues": R.r_venues,
    "/coaches": R.r_coaches,
    "/games": R.r_games,
    "/games/teams": R.r_games_teams,
    "/games/players": R.r_games_players,
    "/games/media": R.r_games_media,
    "/games/weather": R.r_games_weather,
    "/lines": R.r_lines,
    "/records": R.r_records,
    "/rankings": R.r_rankings,
    "/ratings/sp": R.r_ratings_sp,
    "/ratings/sp/conferences": R.r_ratings_sp_conferences,
    "/ratings/elo": R.r_ratings_elo,
    "/ratings/fpi": R.r_ratings_fpi,
    "/ratings/srs": R.r_ratings_srs,
    "/ratings/core": R.r_ratings_core,
    "/talent": R.r_talent,
    "/recruiting/players": R.r_recruiting_players,
    "/recruiting/teams": R.r_recruiting_teams,
    "/roster": R.r_roster,
    "/player/portal": R.r_player_portal,
    "/player/search": R.r_player_search,
    "/player/usage": R.r_player_usage,
    "/player/returning": R.r_player_returning,
    "/ppa/games": R.r_ppa_games,
    "/ppa/players/games": R.r_ppa_players_games,
    "/ppa/players/season": R.r_ppa_players_season,
    "/ppa/predicted": R.r_ppa_predicted,
    "/metrics/fg/ep": R.r_metrics_fg_ep,
    "/metrics/wp": R.r_metrics_wp,
    "/metrics/wp/pregame": R.r_wp_pregame,
    "/plays": R.r_plays,
    "/drives": R.r_drives,
    "/stats/season": R.r_stats_season,
    "/stats/season/advanced": R.r_stats_season_advanced,
    "/stats/player/season": R.r_stats_player_season,
    "/stats/categories": R.r_stats_categories,
    "/teams/matchup": R.r_matchup,
    "/wepa/team/season": R.r_wepa_team,
    "/wepa/players/passing": R.r_wepa_players("passing"),
    "/wepa/players/rushing": R.r_wepa_players("rushing"),
    "/wepa/players/kicking": R.r_wepa_players("kicking"),
    "/passing/plays": R.r_passing_plays,
    "/rushing/plays": R.r_rushing_plays,
    "/game/box/advanced": RL.r_box_advanced,
    "/live/plays": RL.r_live_plays,
    "/scoreboard": RL.r_scoreboard,
}

# endpoint -> the lowest plan that may call it (the /info feature it needs)
GATED = {"/games/weather": (1, "weather"), "/scoreboard": (1, "scoreboard"), "/live/plays": (2, "livePlayByPlay")}
TIERS = {0: ("Free", 1_000), 1: ("Tier 1", 5_000), 2: ("Tier 2", 30_000), 3: ("Tier 3", 75_000)}


GENERATOR_MODULES = ("names.py", "league.py", "sim.py", "stats.py", "season.py")  # what the pickled league is made of


def source_hash() -> str:
    digest = hashlib.sha1()
    for name in GENERATOR_MODULES:
        path = Path(__file__).parent / name
        digest.update(name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


def load_world(seed: int = TEST_SEED, season: int = TEST_SEASON, cache_dir: Path | str | None = None) -> World:
    """The league for (seed, season), from the pickle cache when it matches this source."""
    cache = Path(cache_dir) / f"league-{season}-{seed}-{source_hash()}.pickle" if cache_dir else None
    if cache is not None and cache.exists():
        try:
            with cache.open("rb") as fh:
                world = pickle.load(fh)
            if isinstance(world, World):
                return world
        except (OSError, pickle.UnpicklingError, EOFError, AttributeError) as exc:
            log.warning("Demo league cache %s unreadable (%s); building it again", cache, exc)
    world = build_world(seed, season)
    if cache is not None:
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            for old in cache.parent.glob(f"league-{season}-{seed}-*.pickle"):
                old.unlink(missing_ok=True)
            tmp = cache.with_suffix(".tmp")
            with tmp.open("wb") as fh:
                pickle.dump(world, fh, protocol=pickle.HIGHEST_PROTOCOL)
            tmp.replace(cache)
        except OSError as exc:
            log.warning("Could not write the demo league cache %s: %s", cache, exc)
    return world


def answer(world: World, path: str, params: dict[str, str], now: datetime) -> tuple[int, Any]:
    """(status, payload) for one request, without plan gating."""
    route = ROUTES.get(path)
    if route is None:
        return 404, {"message": f"the demo league has no answer for {path}"}
    payload = route(world, params, now)
    if payload is None:
        return 404, {"message": "not found"}
    return 200, payload


class DemoUpstream:
    """An httpx handler answering like CFBD. `clock` returns the current (simulated) time."""

    def __init__(self, world: World, clock: Callable[[], datetime], tier: int = 2, fail: Callable[[str], bool] | None = None) -> None:
        self.world = world
        self.clock = clock
        self.tier = tier
        self.fail = fail
        self.calls: dict[str, int] = {}
        self._lock = threading.Lock()

    @property
    def total_calls(self) -> int:
        return sum(self.calls.values())

    @property
    def counted_calls(self) -> int:
        """Calls that count against the plan: CFBD does not charge for /info (recorded 2026-09-20:
        37 calls made, 31 counted)."""
        return sum(n for path, n in self.calls.items() if path != "/info")

    def info(self) -> dict[str, Any]:
        name, limit = TIERS.get(self.tier, TIERS[2])
        now = self.clock()
        reset = datetime(now.year + (now.month == 12), now.month % 12 + 1, 1, tzinfo=timezone.utc)
        used = self.counted_calls
        return {
            "patronLevel": self.tier, "tierName": name, "monthlyLimit": limit, "remainingCalls": max(0, limit - used), "usedCalls": used,
            "resetAt": reset.strftime("%Y-%m-%dT%H:%M:%S.000Z"), "sharedPool": True, "products": ["cfb"],
            "features": {"adjustedMetrics": self.tier >= 1, "weather": self.tier >= 1, "scoreboard": self.tier >= 1,
                         "livePlayByPlay": self.tier >= 2, "graphQl": self.tier >= 3},
        }

    def handler(self, request):
        import httpx

        path = request.url.path
        params = {k: v for k, v in request.url.params.items()}
        with self._lock:
            self.calls[path] = self.calls.get(path, 0) + 1
        try:
            if self.fail is not None and self.fail(path):
                return _json(httpx, {"message": "simulated upstream failure"}, 500)
            if path == "/info":
                return _json(httpx, self.info())
            gate = GATED.get(path)
            if gate is not None and self.tier < gate[0]:
                return _json(httpx, {"message": "Your API tier does not have access to this endpoint"}, 401)
            status, payload = answer(self.world, path, params, self.clock())
            return _json(httpx, payload, status)
        except Exception as exc:  # noqa: BLE001 - a demo bug must show up as an error, not hang the app
            log.exception("Demo league failed on %s %s", path, params)
            return _json(httpx, {"message": f"demo league error: {exc.__class__.__name__}: {exc}"}, 500)


def _json(httpx, payload: Any, status: int = 200):
    return httpx.Response(status, content=json.dumps(payload, separators=(",", ":")).encode("utf-8"), headers={"content-type": "application/json"})
