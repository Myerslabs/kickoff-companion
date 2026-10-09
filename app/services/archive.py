"""The Archive (X5): every game this app watched to the final, read back with everything CFBD
posted afterwards (owner direction 2026-09-23: as much data as we can). The file the engine
wrote at the final is the spine (plays, drives, the delayed state, the win probability series);
the box score, player lines, play value and notes come from the program and analytics services,
which cache them for good once the game is final. Nothing is back-filled: a game the app did not
watch is not in the archive."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import timedelta
from pathlib import Path
from typing import Any

from app.api.envelope import utc_now_iso
from app.cfbd.models import Game, PlayerGamePpa, PlayWinProbability, parse_records
from app.services import gamekeys, recap16
from app.services.analytics import AnalyticsService, player_rows, wp_series
from app.services.context16 import peek
from app.services.depth2 import advanced_box
from app.services.parts import Assembled
from app.services.program import ProgramService

log = logging.getLogger("kickoff.archive")


def _num(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


class ArchiveService:
    def __init__(self, data_dir: Path, analytics: AnalyticsService, program: ProgramService, team: str) -> None:
        self.folder = Path(data_dir) / "archive"
        self.analytics = analytics
        self.program = program
        self.team = team

    # --- files ---------------------------------------------------------------------------------------

    def _read(self, path: Path) -> dict[str, Any] | None:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            log.warning("Archive file %s is unreadable: %s", path.name, exc)
            return None
        if not isinstance(raw, dict) or not isinstance(raw.get("gameId"), int) or not isinstance(raw.get("state"), dict):
            log.warning("Archive file %s has the wrong shape; skipped", path.name)
            return None
        return raw

    def _summary(self, raw: dict[str, Any]) -> dict[str, Any]:
        state = raw["state"]
        home, away = raw.get("home"), raw.get("away")
        home_is_us = home == self.team
        return {
            "gameId": raw["gameId"],
            "week": _num(raw.get("week")),
            "seasonType": raw.get("seasonType") if isinstance(raw.get("seasonType"), str) else "regular",
            "kickoff": raw.get("kickoff"),
            "savedAt": raw.get("savedAt"),
            "home": home,
            "away": away,
            "homeIsUs": home_is_us,
            "opponent": away if home_is_us else home,
            "homeScore": _num(state.get("homeScore")),
            "awayScore": _num(state.get("awayScore")),
            "usScore": _num(state.get("homeScore") if home_is_us else state.get("awayScore")),
            "themScore": _num(state.get("awayScore") if home_is_us else state.get("homeScore")),
            "status": state.get("status"),
            "plays": _num((state.get("counts") or {}).get("plays")),
            "hasWinProbability": bool(raw.get("winProbability")),
        }

    def list(self) -> dict[str, Any]:
        games: list[dict[str, Any]] = []
        skipped = 0
        if self.folder.is_dir():
            for path in sorted(self.folder.glob("*.json")):
                raw = self._read(path)
                if raw is None:
                    skipped += 1
                    continue
                games.append(self._summary(raw))
        games.sort(key=lambda g: (g.get("kickoff") or "", g["gameId"]), reverse=True)
        return {"games": games, "count": len(games), "skipped": skipped, "folder": str(self.folder), "fetchedAt": utc_now_iso()}

    # --- one game -------------------------------------------------------------------------------------

    def _file_for(self, game_id: int) -> dict[str, Any] | None:
        path = self.folder / f"{game_id}.json"
        if not path.is_file():
            return None
        return self._read(path)

    async def game(self, game_id: int) -> dict[str, Any] | None:
        """None when the app never archived this game. Everything else is best effort: the archived
        file always answers, and each CFBD block says whether it is there."""
        raw = self._file_for(game_id)
        if raw is None:
            return None
        summary = self._summary(raw)
        errors: list[dict[str, str]] = []

        analytics: Assembled | None = None
        try:
            analytics = await self.analytics.game(game_id)
        except Exception as exc:  # noqa: BLE001 - the archived file still answers; the block says why
            log.exception("Archive analytics failed for %s", game_id)
            errors.append({"code": "analytics_failed", "message": f"analytics: {exc.__class__.__name__}"})
        program: Assembled | None = None
        try:
            program = await self.program.program(game_id)
        except Exception as exc:  # noqa: BLE001
            log.exception("Archive program failed for %s", game_id)
            errors.append({"code": "program_failed", "message": f"program: {exc.__class__.__name__}"})
        if analytics is not None:
            errors.extend(analytics.errors)
        if program is not None:
            errors.extend(program.errors)

        wp = raw.get("winProbability") if isinstance(raw.get("winProbability"), list) and raw.get("winProbability") else None
        adata = analytics.data if analytics is not None else {}
        pdata = program.data if program is not None else {}
        data = {
            **summary,
            "state": raw["state"],
            "winProbability": {"available": True, "series": wp, "source": "archived at the final"} if wp else (adata.get("winProbability") or {"available": False, "series": [], "note": "No win probability was posted for this game."}),
            "ppa": adata.get("ppa") or {"available": False, "note": "Play value is not available for this game."},
            "advancedBox": adata.get("advancedBox"),  # Phase 13: CFBD's advanced box score for the game
            "final": pdata.get("final"),
            "game": pdata.get("game"),
            "us": pdata.get("us"),
            "them": pdata.get("them"),
            "notes": pdata.get("notes"),
            "line": pdata.get("line"),
            "pregame": pdata.get("pregame"),
            "parts": {**(adata.get("parts") or {}), **(pdata.get("parts") or {})},
        }
        recap16.enrich_win_probability(data["winProbability"], summary["homeIsUs"])  # Phase 16 BX: GX-02, GX-09 on an archived series too
        data["recap"] = await self._recap(raw, data["winProbability"].get("series"), advanced=adata.get("advancedBox"), ppa=adata.get("ppa"))  # Phase 16 BX: UX-07
        stale = bool((analytics is not None and analytics.stale) or (program is not None and program.stale))
        return {"data": data, "stale": stale, "errors": errors}

    # --- Phase 16 BX: the postgame recap (UX-07) ------------------------------------------------------------

    @property
    def _client(self) -> Any:
        return self.analytics.client

    @property
    def _year(self) -> int:
        return self.analytics.settings.season

    async def _schedule(self) -> list[Game]:
        """Our schedule as the other pages cached (a peek: never a call)."""
        payload = await peek(self._client, "/games", {"year": self._year, "team": self.team})
        return parse_records(Game, payload, context="archive/schedule peek").records if payload is not None else []

    async def _recap(self, raw: dict[str, Any], series: Any, *, advanced: Any, ppa: Any, schedule: list[Game] | None = None) -> dict[str, Any] | None:
        try:
            return recap16.recap(raw, series, team=self.team, schedule=schedule if schedule is not None else await self._schedule(), advanced=advanced, ppa=ppa)
        except Exception:  # noqa: BLE001 - the recap is an extra; the archived game still answers. Logged with the traceback
            log.exception("Recap failed for %s", raw.get("gameId"))
            return None

    async def recent_recap(self) -> dict[str, Any] | None:
        """The recap of our last game archived at its final within 36 hours, from the archived
        file and what the cache already holds (the post-game win probability, advanced box score and
        play value): never a CFBD call. None when there is no such game."""
        now = self._client._clock()
        schedule = await self._schedule()
        candidates = []
        for g in schedule:
            kickoff = recap16.parse_time(g.start_date)
            if kickoff is not None and timedelta(0) <= now - kickoff <= recap16.RECAP_WINDOW + timedelta(hours=8):
                raw = self._file_for(g.id)
                if raw is not None and recap16.recent(raw, now):
                    candidates.append((raw.get("savedAt") or raw.get("kickoff") or "", g, raw))
        if not candidates:
            return None
        _, game, raw = max(candidates, key=lambda c: c[0])
        series = raw.get("winProbability") if isinstance(raw.get("winProbability"), list) and raw.get("winProbability") else None
        if series is None:
            payload = await peek(self._client, "/metrics/wp", {"gameId": game.id})
            series = wp_series(parse_records(PlayWinProbability, payload, context="recap/wp peek").records) if payload is not None else []
        advanced = advanced_box(await peek(self._client, "/game/box/advanced", {"id": game.id}))
        opponent = gamekeys.opponent_of(game, self.team)
        players: dict[str, list[dict[str, Any]]] = {"us": [], "them": []}
        if game.week is not None:
            for side, school, other in (("us", self.team, opponent), ("them", opponent, self.team)):
                payload = await peek(self._client, "/ppa/players/games", gamekeys.week_params(game, self._year, school)) if school else None
                if payload is not None:
                    players[side] = player_rows(parse_records(PlayerGamePpa, payload, context="recap/ppa peek").records, school or "", other)
        return await self._recap(raw, series, advanced=advanced, ppa={"players": players}, schedule=schedule)

    async def attach_recent_recap(self, data: Any) -> None:
        """/api/newspaper: adds `recap` only when there is one."""
        if not isinstance(data, dict):
            return
        try:
            recap = await self.recent_recap()
        except Exception:  # noqa: BLE001 - the newspaper goes out without the card; logged with the traceback
            log.exception("Recent recap failed")
            return
        if recap is not None:
            data["recap"] = recap

    # --- Phase 18.2: look again two days later -------------------------------------------------------------

    REFRESH_AFTER = timedelta(hours=48)
    REFRESH_FILE = ".refreshed.json"

    def _refreshed(self) -> dict[str, str]:
        try:
            raw = json.loads((self.folder / self.REFRESH_FILE).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return {str(k): str(v) for k, v in raw.items()} if isinstance(raw, dict) else {}

    def _mark_refreshed(self, game_id: int, now: Any) -> None:
        marks = self._refreshed()
        marks[str(game_id)] = now.isoformat(timespec="seconds")
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
            (self.folder / self.REFRESH_FILE).write_text(json.dumps(marks, indent=1), encoding="utf-8")
        except OSError as exc:
            log.warning("Could not note the archive refresh of game %s: %s", game_id, exc)

    async def refresh_finished(self, now: Any) -> list[int]:
        """CFBD corrects a game's stats for a day or two after the final. Two days after kickoff, the cached
        post-game answers of each archived game are dropped once and fetched again, so the Archive shows the corrected
        numbers. At most one refresh per game, a handful of calls each. Returns the games refreshed."""
        from datetime import datetime

        from app.cache import cache_key

        done: list[int] = []
        if not self.folder.is_dir():
            return done
        marks = self._refreshed()
        schedule = await self._schedule()
        by_id = {g.id: g for g in schedule}
        for path in sorted(self.folder.glob("*.json")):
            raw = self._read(path)
            if raw is None:
                continue
            game_id = raw["gameId"]
            game = by_id.get(game_id)
            if game is None or not game.completed or str(game_id) in marks:
                continue
            try:
                start = datetime.fromisoformat(str(game.start_date).replace("Z", "+00:00"))
            except ValueError:
                continue
            if start.tzinfo is None or now - start < self.REFRESH_AFTER:
                continue
            keys = [cache_key("/game/box/advanced", {"id": game_id}), cache_key("/metrics/wp", {"gameId": game_id})]
            for team in (game.home_team, game.away_team):
                if team:
                    keys += [cache_key("/games/teams", gamekeys.box_params(game, self._year, team)), cache_key("/games/players", gamekeys.box_params(game, self._year, team))]
            # Final pass: the cached copies are kept aside and put back when the refetch does not fully succeed, so a
            # CFBD outage during the refresh never leaves the archive game without its box score or win probability.
            kept = {key: await asyncio.to_thread(self._client.cache.get, key) for key in keys}
            for key in keys:
                await asyncio.to_thread(self._client.cache.delete, key)
            complete = False
            try:
                result = await self.game(game_id)  # fetches it all again and caches it
                complete = not (getattr(result, "all_failed", False) or getattr(result, "errors", None))  # every part answered
            except Exception:  # noqa: BLE001 - one game's refresh must not stop the others; logged
                log.exception("Archive refresh of game %s failed", game_id)
            if not complete:
                for key, entry in kept.items():
                    if entry is not None and await asyncio.to_thread(self._client.cache.get, key) is None:
                        ttl = entry.expires_at - entry.fetched_at if entry.expires_at is not None else None
                        await asyncio.to_thread(self._client.cache.put, key, entry.endpoint, entry.params, entry.payload, fetched_at=entry.fetched_at, ttl=ttl)
                log.warning("Archive refresh of game %s did not complete; the earlier copies are kept and it is tried again next time", game_id)
                continue
            self._mark_refreshed(game_id, now)
            done.append(game_id)
            log.info("Archive game %s refreshed with CFBD's corrected post-game numbers", game_id)
        return done
