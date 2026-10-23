"""A game week on a CFBD key, rehearsed against the made-up league (freeze wave F2, 2026-10-20): how many calls a
viewer's week costs, by endpoint and by day, and whether a month of them fits the key's budget.

    .\\.venv\\Scripts\\python tools\\quota_rehearsal.py                       the free tier, a daily viewer
    .\\.venv\\Scripts\\python tools\\quota_rehearsal.py --pattern weekend     a viewer who opens the app Saturday and Sunday
    .\\.venv\\Scripts\\python tools\\quota_rehearsal.py --tier 2              the Tier 2 profile (30,000 a month)
    .\\.venv\\Scripts\\python tools\\quota_rehearsal.py --json report.json    the numbers as a file too

The app is built in this process against the demo league (app/demo, no network, no key), its clock set to the Monday
before the demo team's game and moved through the week step by step. At each step the pages a viewer would open are
asked for through the app's own routes (the server's cost is the same whether a browser or this script asks), and the
In Game sheet is kept open through the game, its status, state and ticker asked every five minutes as the page does.
At the end the app's quota ledger (every CFBD call, attempts included) is read back.

The patterns:
  weekend  Saturday late morning: the Pre-Game Program, the paper, the Top 25; the game on In Game; Sunday morning:
           Season, the program, the paper, the Top 25.
  daily    the weekend, plus every weekday evening the program, Season, the paper and the Top 25, and one more page a
           day (the opponent's team page, Leaders, Roster, Advanced Team Ratings, Recruiting with the Injury Report).

The month is the week times 4.35 (a 30.4-day month); the first month also pays one cold start and one visit of every
page (about 130 calls on the free profile, measured 2026-10-16). Exit code 0 when the projected month fits the budget
with the reserve to spare, 1 when it does not, 2 when the rehearsal could not run."""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sqlite3
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.demo.run import CACHE_DIR, SimClock, build, demo_season, next_game  # noqa: E402
from app.demo.upstream import load_world  # noqa: E402

EASTERN = ZoneInfo("America/New_York")
MON, TUE, WED, THU, FRI, SAT, SUN = range(7)
WEEKS_A_MONTH = 30.4 / 7
FIRST_MONTH_EXTRA = 130  # a cold start plus one visit of every page on the free profile (measured 2026-10-16)
LIVE_TICK = timedelta(minutes=5)  # In Game asks its status every minute and the ticker every minute; the slate moves every 20 (free) or 5
TOP25_TICK = timedelta(minutes=15)
BUDGETS = {0: 1000, 1: 5000, 2: 30000}

# What each page asks the server for (the routes that can cost CFBD calls; the rest are free and left out).
PAGES: dict[str, list[str]] = {
    "program": ["/api/program/next", "/api/newspaper", "/api/live/status", "/api/today"],
    "season": ["/api/season/overview"],
    "newspaper": ["/api/newspaper"],
    "top25": ["/api/top25?delay=45"],
    "live": ["/api/live/status", "/api/live/state?delay=45", "/api/ticker?delay=45", "/api/program/next"],
    "leaders": ["/api/season/leaders", "/api/grades?group=QB"],
    "roster": ["/api/roster"],
    "recruiting": ["/api/recruiting"],
    "ratings": ["/api/ratings"],
    "injuries": ["/api/injuries"],
    "myteams": ["/api/season/overview"],  # board 9 (2026-10-22): the old My Teams address opens the Season page
}


class JumpClock(SimClock):
    """The demo's clock with a way to set the time: the rehearsal moves it from step to step."""

    def jump(self, moment: datetime) -> None:
        self.sim0 = moment
        self.mono0 = time.monotonic()


def at(day: datetime, weekday: int, hour: int, minute: int = 0) -> datetime:
    """`weekday` of the week that starts on Monday `day` (Eastern), at hour:minute."""
    local = (day + timedelta(days=weekday)).replace(hour=hour, minute=minute, second=0, microsecond=0)
    return local


def weekend_pattern(monday: datetime, kickoff: datetime, final: datetime) -> list[tuple[datetime, list[str]]]:
    steps: list[tuple[datetime, list[str]]] = [
        (at(monday, SAT, 11, 0), ["program", "newspaper", "top25"]),
        (at(monday, SUN, 10, 0), ["season", "program", "newspaper", "top25"]),
    ]
    moment = kickoff - timedelta(minutes=30)
    last_top25 = None
    while moment <= final + timedelta(minutes=30):
        pages = ["live"]
        if last_top25 is None or moment - last_top25 >= TOP25_TICK:
            pages.append("top25")
            last_top25 = moment
        steps.append((moment, pages))
        moment += LIVE_TICK
    return steps


def daily_pattern(monday: datetime, kickoff: datetime, final: datetime) -> list[tuple[datetime, list[str]]]:
    extra = {MON: ["team_opponent"], TUE: ["leaders"], WED: ["roster"], THU: ["ratings"], FRI: ["recruiting", "injuries"]}
    steps = weekend_pattern(monday, kickoff, final)
    for weekday in (MON, TUE, WED, THU, FRI):
        steps.append((at(monday, weekday, 19, 0), ["program", "season", "newspaper", "top25", *extra[weekday]]))
    return steps


PATTERNS = {"weekend": weekend_pattern, "daily": daily_pattern}


def dig(value: Any, key: str) -> Any:
    """The first value under `key` anywhere in a JSON answer."""
    if isinstance(value, dict):
        if key in value:
            return value[key]
        for v in value.values():
            found = dig(v, key)
            if found is not None:
                return found
    elif isinstance(value, list):
        for v in value:
            found = dig(v, key)
            if found is not None:
                return found
    return None


async def open_pages(client: Any, pages: list[str], opponent: str | None, note: list[str]) -> None:
    routes: list[str] = []
    for page in pages:
        if page == "team_opponent":
            if opponent:
                routes.append(f"/api/team/{opponent}")
            continue
        routes += PAGES.get(page, [])
    answers = await asyncio.gather(*(client.get(route) for route in routes), return_exceptions=True)
    for route, answer in zip(routes, answers, strict=True):
        if isinstance(answer, Exception):
            note.append(f"{route}: {answer.__class__.__name__}")
        elif answer.status_code >= 400:
            note.append(f"{route}: HTTP {answer.status_code}")
    if "program" in pages:  # the program page asks for its game's leaders and the players to watch once it knows the game
        program = next((a for r, a in zip(routes, answers, strict=True) if r == "/api/program/next" and not isinstance(a, Exception)), None)
        if program is not None and program.status_code < 400:
            data = program.json().get("data") or {}
            game_id = dig(data.get("game") or data, "gameId")
            if game_id:
                more = [f"/api/program/{game_id}/leaders"]
                home, away = dig(data, "homeTeam"), dig(data, "awayTeam")
                if isinstance(home, str) and isinstance(away, str):
                    more.append(f"/api/grades/teams?teams={home},{away}")
                await asyncio.gather(*(client.get(route) for route in more), return_exceptions=True)


def ledger(db_path: Path, since: str = "") -> tuple[list[tuple[str, int, int, int]], list[tuple[str, int]]]:
    """The ledger by endpoint and by day, from `since` (an ISO time; the ledger stores UTC, close enough for a week)."""
    conn = sqlite3.connect(db_path)
    try:
        by_endpoint = conn.execute(
            "SELECT endpoint, COUNT(*), SUM(live), SUM(CASE WHEN ok THEN 0 ELSE 1 END) FROM quota_calls WHERE at >= ? GROUP BY endpoint ORDER BY 2 DESC, 1",
            (since,),
        ).fetchall()
        by_day = conn.execute("SELECT substr(at, 1, 10), COUNT(*) FROM quota_calls WHERE at >= ? GROUP BY 1 ORDER BY 1", (since,)).fetchall()
    finally:
        conn.close()
    return [(str(e), int(n), int(live or 0), int(failed or 0)) for e, n, live, failed in by_endpoint], [(str(d), int(n)) for d, n in by_day]


async def rehearse(tier: int, pattern: str, data_dir: Path, verbose: bool, weeks: int = 2) -> dict[str, Any]:
    """`weeks` game weeks in a row, the demo team's next games; the last one is the steady state (a warm cache), the
    first carries the cold start."""
    import httpx

    world = load_world(season=demo_season(), seed=2026, cache_dir=CACHE_DIR)
    game = next_game(world)
    games = [game]
    while len(games) < weeks:
        following = next_game(world, after=games[-1].end)
        if following is games[-1] or following.end <= games[-1].end:
            break
        games.append(following)
    steps: list[tuple[datetime, list[str]]] = []
    week_starts: list[datetime] = []
    for g in games:
        kickoff = g.slot.start.astimezone(EASTERN)
        final = g.end.astimezone(EASTERN)
        monday = (kickoff - timedelta(days=kickoff.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        week_starts.append(monday)
        steps += PATTERNS[pattern](monday, kickoff, final)
    steps.sort(key=lambda s: s[0])
    kickoff = games[-1].slot.start.astimezone(EASTERN)
    final = games[-1].end.astimezone(EASTERN)
    monday = week_starts[0]
    last_monday = week_starts[-1]
    clock = JumpClock(monday, 60.0)
    application, asgi, upstream, settings = build(world, clock, data_dir, 8699, "127.0.0.1", tier, None)
    opponent = None
    for team_id in (game.slot.home, game.slot.away):
        team = world.league.team(team_id)
        if team is not None and team.school != settings.team:
            opponent = team.school
    problems: list[str] = []
    started = time.monotonic()
    async with application.router.lifespan_context(application):
        await asyncio.sleep(0.5)  # the startup reconcile with /info, so the profile is known
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=asgi), base_url="http://localhost", timeout=120) as client:
            for moment, pages in steps:
                clock.jump(moment)
                await open_pages(client, pages, opponent, problems)
                if verbose:
                    print(f"  {moment:%a %H:%M}  {', '.join(pages)}  ledger {application.state.cfbd.quota.status(clock()).ledger_calls_this_month}", flush=True)
            clock.jump(at(last_monday, SUN, 23, 59))
            status = application.state.cfbd.quota.status(clock())
            blocked = int(application.state.cfbd.stats.get("blocked_by_quota", 0))
            profile = "free" if application.state.cfbd.lean_profile else "full"
    since = at(last_monday, MON, 0, 0).astimezone(timezone.utc).isoformat(timespec="seconds")  # the ledger stores UTC
    by_endpoint, by_day = ledger(data_dir / "kickoff.db", since=since)
    all_endpoints, _all_days = ledger(data_dir / "kickoff.db")
    week = sum(n for _, n, _, _ in by_endpoint)
    total = sum(n for _, n, _, _ in all_endpoints)
    return {
        "tier": tier,
        "pattern": pattern,
        "profile": profile,
        "budget": BUDGETS.get(tier, 30000),
        "weeks": len(games),
        "game": f"{kickoff:%a %b %d %H:%M} ET, final {final:%H:%M}",
        "steps": len(steps),
        "week": week,
        "coldWeeks": total - week,
        "month": round(week * WEEKS_A_MONTH),
        "firstMonth": round(week * WEEKS_A_MONTH) + FIRST_MONTH_EXTRA,
        "byEndpoint": [{"endpoint": e, "calls": n, "live": live, "failed": failed} for e, n, live, failed in by_endpoint],
        "byDay": [{"day": d, "calls": n} for d, n in by_day],
        "blockedByQuota": blocked,
        "ledgerMode": status.mode.value,
        "problems": problems[:20],
        "realSeconds": round(time.monotonic() - started, 1),
        "upstreamCalls": upstream.total_calls,
    }


def report(result: dict[str, Any], reserve: float) -> int:
    budget = result["budget"]
    room = budget * (1 - reserve)
    print(f"\nQuota rehearsal: tier {result['tier']} ({result['profile']} profile), the {result['pattern']} pattern, {result['weeks']} weeks, the last game {result['game']}")
    print(f"{result['steps']} steps in {result['realSeconds']} s of real time; the upstream saw {result['upstreamCalls']} calls in all, {result['coldWeeks']} of them before the last week (the cold start).")
    print("The last week, a warm cache:\n")
    print(f"{'Endpoint':<28}{'Calls':>7}{'Live':>6}{'Failed':>8}")
    for row in result["byEndpoint"]:
        print(f"{row['endpoint']:<28}{row['calls']:>7}{row['live']:>6}{row['failed']:>8}")
    print("\nBy day: " + ", ".join(f"{d['day'][5:]} {d['calls']}" for d in result["byDay"]))
    print(f"\nThe week: {result['week']} calls. A month at this pace: about {result['month']:,} ({result['firstMonth']:,} the first month, with the cold start).")
    if result["blockedByQuota"]:
        print(f"The guard refused {result['blockedByQuota']} calls during the week (ledger mode at the end: {result['ledgerMode']}).")
    if result["problems"]:
        print("Routes that did not answer: " + "; ".join(result["problems"]))
    fits = result["month"] <= room
    print(f"\nBudget {budget:,} a month with {int(reserve * 100)}% in reserve = {int(room):,} to spend: {'FITS' if fits else 'DOES NOT FIT'} ({result['month']:,} projected).")
    return 0 if fits else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python tools/quota_rehearsal.py", description=__doc__.split("\n\n")[0])
    parser.add_argument("--tier", type=int, choices=(0, 1, 2), default=0, help="the CFBD plan to imitate (default 0, the free tier)")
    parser.add_argument("--pattern", choices=sorted(PATTERNS), default="daily", help="how often the viewer opens the app (default daily)")
    parser.add_argument("--reserve", type=float, default=0.3, help="the share of the budget to keep unspent (default 0.3)")
    parser.add_argument("--weeks", type=int, default=2, help="game weeks to run; the last one is reported (default 2: the first carries the cold start)")
    parser.add_argument("--json", type=Path, default=None, help="also write the numbers to this file")
    parser.add_argument("--verbose", action="store_true", help="print every step with the ledger's count")
    args = parser.parse_args(argv)
    data_dir = Path(tempfile.mkdtemp(prefix="kickoff-rehearsal-"))
    try:
        result = asyncio.run(rehearse(args.tier, args.pattern, data_dir, args.verbose, weeks=max(1, args.weeks)))
    except Exception as exc:  # noqa: BLE001 - the report must say why
        print(f"The rehearsal could not run: {exc.__class__.__name__}: {exc}", file=sys.stderr)
        return 2
    finally:
        shutil.rmtree(data_dir, ignore_errors=True)
    code = report(result, args.reserve)
    if args.json:
        args.json.write_text(json.dumps(result, indent=1), encoding="utf-8")
        print(f"Written to {args.json}")
    return code


if __name__ == "__main__":
    sys.exit(main())
