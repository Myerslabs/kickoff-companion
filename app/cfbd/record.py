"""Record one real response per endpoint into tests/fixtures/cfbd/.

    python -m app.cfbd.record            record everything (about 45 billed calls)
    python -m app.cfbd.record --only /records --only /games
    python -m app.cfbd.record --extra    record only the additions (about 21 calls), or one set:
      --extra week      the next week's slate, lines, win probability, media, all records, prior rosters (9)
      --extra players   recruiting classes, one all-D1 player stat call per category, opponent roster (12)
      --extra program   venues, opponent coaches and schedule, earlier box scores (about 7)
      --extra live      Tier 2 only: the live document of the last finished game, the scoreboard, CFBD weather (3)
      --extra stats     player season PPA and usage, team talent, returning production, opponent recruiting classes (about 12)
      --extra depth2    Phase 13: advanced box score, portal, class ranks, opponent-adjusted metrics, CORE, SRS,
                        conference SP+, the next opponent's rushing and passing plays (14)
      --extra postseason  Phase 15: last season's bowls and playoff: the slate, one playoff team's schedule
                        with and without seasonType, its last game through every per-game endpoint, polls (17)
      --extra search    Phase 15: CFBD's player search, a narrow and a broad term (2)
      --extra national  Phase 16: every recruit in five classes (this year -3 to next year) and every
                        team's returning production, for the national lists (6)

Runs on the owner's machine with the key from .env, through the normal client (quota guard,
ledger, breaker), with the cache bypassed so every sample is fresh. Errors are recorded too:
a 403 on a tier-gated endpoint is a useful fixture. Each file holds the request, the status,
and the payload, so tests can rebuild the exact upstream behaviour without the network.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.cache import DataKind
from app.cfbd.client import CfbdClient, CfbdError, CfbdRequestError
from app.cfbd.models import ENDPOINTS, ParseResult, normalize_endpoint, parse_endpoint
from app.config import PROJECT_ROOT, Settings, SettingsError, load_settings
from app.db import Database, database_path
from app.logging_setup import configure_logging

FIXTURE_DIR = PROJECT_ROOT / "tests" / "fixtures" / "cfbd"
log = logging.getLogger("kickoff.record")


def fixture_name(endpoint: str, suffix: str = "") -> str:
    base = endpoint.strip("/").replace("/", "_")
    return f"{base}_{suffix}" if suffix else base


def _write(name: str, data: dict[str, Any], *, compact: bool = False) -> Path:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    path = FIXTURE_DIR / f"{name}.json"
    if compact:
        path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    else:
        path.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    return path


def _fbs_schools() -> set[str]:
    """Schools from the recorded /teams/fbs, used to trim the all-D1 player stat fixtures."""
    path = FIXTURE_DIR / "teams_fbs.json"
    if not path.exists():
        return set()
    payload = json.loads(path.read_text(encoding="utf-8")).get("payload") or []
    return {t.get("school") for t in payload if isinstance(t, dict) and t.get("school")}


def _count(payload: Any) -> int | None:
    return len(payload) if isinstance(payload, list) else None


class Recorder:
    def __init__(self, client: CfbdClient, settings: Settings, only: set[str], extra_only: bool = False, extra_sets: tuple[str, ...] | None = None) -> None:
        self.client = client
        self.settings = settings
        self.only = only
        self.extra_only = extra_only
        self.extra_sets = extra_sets or self.EXTRA_SETS
        self.rows: list[dict[str, Any]] = []

    async def capture(self, endpoint: str, params: dict[str, Any] | None = None, *, suffix: str = "", trim_to_fbs: bool = False, compact: bool = False) -> Any:
        """Call one endpoint, write the fixture, return the payload (or None on error).

        trim_to_fbs keeps only FBS teams' rows (the all-D1 player stat calls run to 64,000 records
        and 15 MB otherwise) and writes compact JSON. The app filters the same way at runtime."""
        if self.only and endpoint not in self.only:
            return None
        name = fixture_name(endpoint, suffix)
        spec = ENDPOINTS.get(endpoint)
        kind = spec.kind if spec else DataKind.REFERENCE
        started = datetime.now(timezone.utc)
        row: dict[str, Any] = {"name": name, "endpoint": endpoint, "params": params or {}}
        try:
            fetched = await self.client.get(endpoint, params, kind=kind, use_cache=False)
        except CfbdRequestError as exc:
            row.update(status=exc.status, error=str(exc), records=None)
            _write(name, {**row, "fetched_at": started.isoformat(), "body": exc.body, "payload": None})
            self.rows.append(row)
            return None
        except CfbdError as exc:
            row.update(status=None, error=str(exc), records=None)
            _write(name, {**row, "fetched_at": started.isoformat(), "payload": None})
            self.rows.append(row)
            return None

        payload = fetched.payload
        trimmed = None
        if trim_to_fbs and isinstance(payload, list):
            fbs_schools = _fbs_schools()
            kept = [r for r in payload if isinstance(r, dict) and r.get("team") in fbs_schools]
            trimmed = f"FBS teams only ({len(kept)} of {len(payload)} records), compact JSON"
            payload = kept
        parsed = parse_endpoint(endpoint, payload)
        skipped = parsed.skipped if isinstance(parsed, ParseResult) else 0
        problems = parsed.problems[:3] if isinstance(parsed, ParseResult) else []
        row.update(
            status=200,
            records=_count(payload),
            skipped=skipped,
            problems=problems,
            bytes=len(json.dumps(payload, separators=(",", ":"))),
        )
        if trimmed:
            row["trimmed"] = trimmed
        _write(name, {**row, "fetched_at": fetched.meta["fetched_at"], "payload": payload}, compact=bool(trimmed) or compact)
        self.rows.append(row)
        return payload

    EXTRA_SETS = ("week", "players", "program", "live", "stats", "depth2", "postseason", "search", "national")

    async def extras(self, year: int, team: str, next_week: int, sets: tuple[str, ...] = EXTRA_SETS, opponent: str | None = None) -> None:
        """Additions after the first recording.

        week (2026-09-21): the newspaper slate for the next week and prior rosters for player history.
        players (2026-09-23, Phase 4): recruiting classes for the roster join and next year's commits,
        one all-D1 player stat call per leader-board category, and the next opponent's roster.
        program (2026-09-23, Phase 5): every venue (coordinates for the weather lookup), the next
        opponent's coaches and schedule, and the box scores of the earlier finished games.
        live (2026-09-23, Phase 8, Tier 2): the live document of our last finished game as
        /live/plays serves it after the final, the FBS scoreboard, and CFBD's game weather.
        stats (2026-09-23, Phase 10): player season PPA and usage for both teams, team talent, returning
        production, and the opponent's last four recruiting classes for the blue-chip ratio.
        """
        if "week" in sets:
            await self.capture("/games", {"year": year, "week": next_week}, suffix="week")
            await self.capture("/lines", {"year": year, "week": next_week}, suffix="week")
            await self.capture("/metrics/wp/pregame", {"year": year, "week": next_week}, suffix="week")
            await self.capture("/games/media", {"year": year, "week": next_week}, suffix="week")
            await self.capture("/records", {"year": year}, suffix="all")
            for past in range(year - 4, year):
                await self.capture("/roster", {"team": team, "year": past}, suffix=str(past))
        if "players" in sets:
            for cls in list(range(year - 4, year)) + [year + 1]:
                await self.capture("/recruiting/players", {"year": cls, "team": team}, suffix=str(cls))
            for category in ("rushing", "receiving", "defensive", "interceptions", "kicking", "punting"):
                await self.capture("/stats/player/season", {"year": year, "category": category}, suffix=f"all_{category}", trim_to_fbs=True)
            if opponent:
                await self.capture("/roster", {"team": opponent, "year": year}, suffix="opponent")
        if "program" in sets:
            await self.capture("/venues")
            if opponent:
                await self.capture("/coaches", {"team": opponent, "year": year}, suffix="opponent")
                await self.capture("/games", {"year": year, "team": opponent}, suffix="opponent")
            games = json.loads((FIXTURE_DIR / "games_team.json").read_text(encoding="utf-8")).get("payload") or []
            weeks = sorted({g["week"] for g in games if isinstance(g, dict) and g.get("completed") and g.get("week")})
            for week in weeks:
                if not (FIXTURE_DIR / f"games_teams_{week}.json").exists() and week != max(weeks, default=None):
                    await self.capture("/games/teams", {"year": year, "week": week, "team": team}, suffix=str(week))
                    await self.capture("/games/players", {"year": year, "week": week, "team": team}, suffix=str(week))

        if "live" in sets:
            games = json.loads((FIXTURE_DIR / "games_team.json").read_text(encoding="utf-8")).get("payload") or []
            finished = [g for g in games if isinstance(g, dict) and g.get("completed") and isinstance(g.get("id"), int) and g.get("week")]
            last = max(finished, key=lambda g: g["week"]) if finished else None
            if last:
                await self.capture("/live/plays", {"gameId": last["id"]})
            await self.capture("/scoreboard", {"classification": "fbs"}, suffix="fbs")
            await self.capture("/games/weather", {"year": year, "week": next_week, "team": team}, suffix="tier2")

        if "depth2" in sets:
            await self.depth2(year, team)
        if "postseason" in sets:
            await self.postseason(year - 1)
        if "search" in sets:  # Phase 15: CFBD's player search, one narrow and one broad term
            await self.capture("/player/search", {"searchTerm": "Smith"}, suffix="name")
            await self.capture("/player/search", {"searchTerm": "Smith", "year": year}, suffix="smith")
        if "national" in sets:  # Phase 16: nationwide lists for recruit rank, blue-chip ratio, returning production
            for cls in range(year - 3, year + 2):
                await self.capture("/recruiting/players", {"year": cls}, suffix=f"national_{cls}", compact=True)
            await self.capture("/player/returning", {"year": year}, suffix="national", compact=True)
        if "stats" in sets:
            await self.capture("/ppa/players/season", {"year": year, "team": team})
            await self.capture("/player/usage", {"year": year, "team": team})
            await self.capture("/talent", {"year": year})
            await self.capture("/player/returning", {"year": year, "team": team})
            if opponent:
                await self.capture("/ppa/players/season", {"year": year, "team": opponent}, suffix="opponent")
                await self.capture("/player/usage", {"year": year, "team": opponent}, suffix="opponent")
                await self.capture("/player/returning", {"year": year, "team": opponent}, suffix="opponent")
                for cls in range(year - 3, year + 1):
                    await self.capture("/recruiting/players", {"year": cls, "team": opponent}, suffix=f"opponent_{cls}")

    async def depth2(self, year: int, team: str) -> None:
        """Phase 13 (2026-09-26): our last finished game's advanced box score, the transfer
        portal, recruiting class ranks for this class and the next, opponent-adjusted team and player
        metrics and kicker PAAR, CORE, SRS and conference SP+, and the next opponent's season of
        rushing and passing plays for its tendencies. The next opponent comes from the schedule by date."""
        games = json.loads((FIXTURE_DIR / "games_team.json").read_text(encoding="utf-8")).get("payload") or []
        now = datetime.now(timezone.utc).isoformat()
        dated = [g for g in games if isinstance(g, dict) and g.get("startDate") and g.get("id")]
        played = [g for g in dated if str(g["startDate"]) < now]
        ahead = sorted((g for g in dated if str(g["startDate"]) >= now), key=lambda g: str(g["startDate"]))
        last = max(played, key=lambda g: str(g["startDate"])) if played else None
        opponent = None
        if ahead:
            nxt = ahead[0]
            opponent = nxt.get("awayTeam") if nxt.get("homeTeam") == team else nxt.get("homeTeam")
        if last:
            await self.capture("/game/box/advanced", {"id": last["id"]})
        await self.capture("/player/portal", {"year": year})
        await self.capture("/recruiting/teams", {"year": year})
        await self.capture("/recruiting/teams", {"year": year + 1}, suffix=str(year + 1))
        await self.capture("/wepa/team/season", {"year": year})
        await self.capture("/wepa/players/passing", {"year": year})
        await self.capture("/wepa/players/rushing", {"year": year})
        await self.capture("/wepa/players/kicking", {"year": year})
        await self.capture("/ratings/core", {"year": year})
        await self.capture("/ratings/srs", {"year": year})
        await self.capture("/ratings/sp/conferences", {"year": year})
        if opponent:
            await self.capture("/rushing/plays", {"year": year, "team": opponent}, suffix="opponent")
            await self.capture("/passing/plays", {"year": year, "team": opponent}, suffix="opponent")
        print(f"depth2: last finished game {last and last.get('id')}, next opponent {opponent}")

    async def postseason(self, year: int) -> None:
        """Phase 15 (2026-09-27): a finished postseason to build bowl and playoff support against. The
        team is the one with the most postseason games (a playoff finalist); its last game goes through
        every per-game endpoint the app uses, by id where CFBD takes one and by week plus seasonType
        otherwise. The schedule is recorded with and without seasonType to learn CFBD's default."""
        slate = await self.capture("/games", {"year": year, "seasonType": "postseason", "classification": "fbs"}, suffix=f"post_{year}")
        games = [g for g in slate or [] if isinstance(g, dict) and g.get("id")]
        if not games:
            print("postseason: no postseason games recorded; stopping")
            return
        count: dict[str, int] = {}
        for g in games:
            for side in ("homeTeam", "awayTeam"):
                if g.get(side):
                    count[g[side]] = count.get(g[side], 0) + 1
        team = max(sorted(count), key=lambda t: count[t])
        mine = sorted((g for g in games if team in (g.get("homeTeam"), g.get("awayTeam"))), key=lambda g: str(g.get("startDate")))
        last = mine[-1]
        week = last.get("week")
        await self.capture("/games", {"year": year, "team": team}, suffix=f"team_{year}_default")
        await self.capture("/games", {"year": year, "team": team, "seasonType": "both"}, suffix=f"team_{year}_both")
        await self.capture("/calendar", {"year": year}, suffix=str(year))
        await self.capture("/rankings", {"year": year}, suffix=f"{year}_default")
        await self.capture("/rankings", {"year": year, "seasonType": "both"}, suffix=f"{year}_both")
        await self.capture("/games/teams", {"id": last["id"]}, suffix="post")
        await self.capture("/games/players", {"id": last["id"]}, suffix="post")
        await self.capture("/drives", {"year": year, "week": week, "team": team, "seasonType": "postseason"}, suffix="post")
        await self.capture("/plays", {"year": year, "week": week, "team": team, "seasonType": "postseason"}, suffix="post")
        await self.capture("/metrics/wp", {"gameId": last["id"]}, suffix="post")
        await self.capture("/game/box/advanced", {"id": last["id"]}, suffix="post")
        await self.capture("/ppa/games", {"year": year, "team": team, "seasonType": "both"}, suffix="post")
        await self.capture("/ppa/players/games", {"year": year, "week": week, "team": team, "seasonType": "postseason"}, suffix="post")
        await self.capture("/metrics/wp/pregame", {"year": year, "week": week, "seasonType": "postseason"}, suffix="post")
        await self.capture("/games/media", {"year": year, "seasonType": "postseason"}, suffix="post")
        await self.capture("/lines", {"year": year, "team": team, "seasonType": "postseason"}, suffix="post")
        print(f"postseason: {year}, {len(games)} games; {team} played {len(mine)}; last game {last['id']} week {week}")

    async def run_extras_only(self) -> None:
        """Record only the extras and merge them into the existing manifest. Never touches /info."""
        year, team = self.settings.season, self.settings.team
        manifest_path = FIXTURE_DIR / "MANIFEST.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
        next_week = (manifest.get("next_game") or {}).get("week")
        opponent = (manifest.get("next_game") or {}).get("opponent")
        if not next_week:
            games = json.loads((FIXTURE_DIR / "games_team.json").read_text(encoding="utf-8")).get("payload") or []
            upcoming = [g for g in games if isinstance(g, dict) and not g.get("completed") and g.get("week")]
            nxt = min(upcoming, key=lambda g: g["week"]) if upcoming else None
            next_week = nxt["week"] if nxt else 1
            opponent = (nxt.get("awayTeam") if nxt.get("homeTeam") == team else nxt.get("homeTeam")) if nxt else None
        ledger_before = self.client.quota.status(datetime.now(timezone.utc)).ledger_calls_this_month
        await self.extras(year, team, next_week, self.extra_sets, opponent)
        ledger_after = self.client.quota.status(datetime.now(timezone.utc)).ledger_calls_this_month

        by_name = {row["name"]: row for row in manifest.get("recordings", [])}
        for row in self.rows:
            by_name[row["name"]] = row
        manifest["recordings"] = list(by_name.values())
        manifest.setdefault("extra_runs", []).append(
            {"recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "calls_made": ledger_after - ledger_before, "names": [row["name"] for row in self.rows]}
        )
        manifest.setdefault("season", year)
        manifest.setdefault("team", team)
        manifest.setdefault("calls_made", 0)
        _write("MANIFEST", manifest)
        print(f"\nRecorded {len(self.rows)} extra fixtures for week {next_week} (billed this run: {ledger_after - ledger_before})")
        for row in self.rows:
            print(f"  {row['name']:32} {str(row.get('status') or 'ERR'):>5} records={row.get('records')} skipped={row.get('skipped', '-')}" + (f"  {row['error'][:80]}" if row.get("error") else "") + (f"  first problem: {row['problems'][0]}" if row.get("problems") else ""))

    async def run(self) -> None:
        if self.extra_only:
            await self.run_extras_only()
            return
        year, team, conference = self.settings.season, self.settings.team, self.settings.conference
        ledger_before = self.client.quota.status(datetime.now(timezone.utc)).ledger_calls_this_month

        info = await self.capture("/info")  # a good /info answer reconciles the quota by itself
        calendar = await self.capture("/calendar", {"year": year})
        games = await self.capture("/games", {"year": year, "team": team}, suffix="team")

        completed = [g for g in (games or []) if isinstance(g, dict) and g.get("completed") and g.get("week")]
        upcoming = [g for g in (games or []) if isinstance(g, dict) and not g.get("completed") and g.get("week")]
        last = max(completed, key=lambda g: g["week"]) if completed else None
        nxt = min(upcoming, key=lambda g: g["week"]) if upcoming else None
        last_week = last["week"] if last else 1
        last_id = last.get("id") if last else None
        next_week = nxt["week"] if nxt else last_week
        opponent = None
        if nxt:
            opponent = nxt.get("awayTeam") if nxt.get("homeTeam") == team else nxt.get("homeTeam")
        if last:
            log.info("Last completed game: week %s, id %s. Next: week %s vs %s", last_week, last_id, next_week, opponent)

        current_week = last_week
        for week in calendar or []:
            if isinstance(week, dict) and week.get("week") and str(week.get("startDate", "")) <= datetime.now(timezone.utc).isoformat():
                current_week = week["week"]

        await self.capture("/records", {"year": year, "team": team}, suffix="team")
        await self.capture("/records", {"year": year, "conference": conference}, suffix="conference")
        await self.capture("/rankings", {"year": year, "week": current_week})
        await self.capture("/stats/season", {"year": year, "team": team}, suffix="team")
        await self.capture("/stats/season", {"year": year, "classification": "fbs"}, suffix="fbs")
        await self.capture("/stats/season/advanced", {"year": year, "team": team}, suffix="team")
        await self.capture("/stats/season/advanced", {"year": year, "classification": "fbs"}, suffix="fbs")
        await self.capture("/stats/player/season", {"year": year, "team": team}, suffix="team")
        await self.capture("/stats/player/season", {"year": year, "conference": conference}, suffix="conference")
        await self.capture("/stats/player/season", {"year": year, "category": "passing"}, suffix="all_passing")
        await self.capture("/roster", {"team": team, "year": year})
        await self.capture("/recruiting/players", {"year": year, "team": team})
        await self.capture("/teams", {"conference": conference}, suffix="conference")
        await self.capture("/teams/fbs", {"year": year})
        await self.capture("/games/media", {"year": year, "team": team})
        await self.capture("/lines", {"year": year, "team": team})
        await self.capture("/games/weather", {"year": year, "team": team})
        if opponent:
            await self.capture("/teams/matchup", {"team1": team, "team2": opponent})
        await self.capture("/metrics/wp/pregame", {"year": year, "week": next_week, "team": team})
        await self.capture("/ppa/games", {"year": year, "team": team})
        await self.capture("/ppa/players/games", {"year": year, "week": last_week, "team": team})
        await self.capture("/ratings/sp", {"year": year})
        await self.capture("/ratings/elo", {"year": year})
        await self.capture("/ratings/fpi", {"year": year})
        await self.capture("/stats/categories")
        await self.capture("/games/teams", {"year": year, "week": last_week, "team": team})
        await self.capture("/games/players", {"year": year, "week": last_week, "team": team})
        await self.capture("/drives", {"year": year, "week": last_week, "team": team})
        await self.capture("/plays", {"year": year, "week": last_week, "team": team})
        if last_id:
            await self.capture("/metrics/wp", {"gameId": last_id})
            await self.capture("/live/plays", {"gameId": last_id}, suffix="finished_game")
        await self.capture("/scoreboard", {"classification": "fbs"})
        await self.extras(year, team, next_week, self.EXTRA_SETS, opponent)
        info_after = await self.capture("/info", suffix="after")

        ledger_after = self.client.quota.status(datetime.now(timezone.utc)).ledger_calls_this_month
        manifest = {
            "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "season": year,
            "team": team,
            "last_completed_game": {"week": last_week, "id": last_id},
            "next_game": {"week": next_week, "opponent": opponent},
            "calls_made": ledger_after - ledger_before,
            "info_before": info,
            "info_after": info_after,
            "recordings": self.rows,
        }
        _write("MANIFEST", manifest)
        self.print_summary(manifest)

    def print_summary(self, manifest: dict[str, Any]) -> None:
        print(f"\nRecorded {len(self.rows)} fixtures into {FIXTURE_DIR}")
        print(f"{'fixture':40} {'status':>6} {'records':>8} {'skipped':>8} {'bytes':>10}")
        for row in self.rows:
            status = row.get("status")
            print(
                f"{row['name']:40} {str(status) if status else 'ERR':>6} "
                f"{str(row.get('records')) if row.get('records') is not None else '-':>8} "
                f"{str(row.get('skipped', '-')):>8} {str(row.get('bytes', '-')):>10}"
                + (f"   {row['error'][:80]}" if row.get("error") else "")
                + (f"   first problem: {row['problems'][0]}" if row.get("problems") else "")
            )
        print(f"\nBilled calls this run: {manifest['calls_made']}")
        print(f"/info before: {json.dumps(manifest['info_before'])}")
        print(f"/info after:  {json.dumps(manifest['info_after'])}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cfbd.record", description=__doc__.split("\n\n")[0])
    parser.add_argument("--only", action="append", default=[], help="record only this endpoint path (repeatable)")
    parser.add_argument("--extra", nargs="?", const="all", default=None, help="record only the additions and merge them into the manifest: all, week, or players")
    args = parser.parse_args(argv)
    extra_sets = None if args.extra in (None, "all") else tuple(args.extra.split(","))
    if extra_sets and any(name not in Recorder.EXTRA_SETS for name in extra_sets):
        parser.error(f"--extra takes all or one of {', '.join(Recorder.EXTRA_SETS)}, not {args.extra}")
    try:
        settings = load_settings()
    except SettingsError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    configure_logging(settings)

    async def run() -> None:
        db = Database(database_path(settings.data_dir))
        client = CfbdClient(settings, db)
        try:
            await Recorder(client, settings, {normalize_endpoint(value) for value in args.only}, extra_only=args.extra is not None, extra_sets=extra_sets).run()
        finally:
            await client.aclose()
            db.close()

    asyncio.run(run())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
