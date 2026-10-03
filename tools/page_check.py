"""Open every page of the app with real data in headless Edge and fail if any shows the words
undefined, null, NaN, Infinity or [object Object] (Phase 15, the design rule "a missing value renders
as a dash").

    .\\.venv\\Scripts\\python tools\\page_check.py            start the simulator, check every page, stop
    .\\.venv\\Scripts\\python tools\\page_check.py --url http://127.0.0.1:8650   check a server already running
    .\\.venv\\Scripts\\python tools\\page_check.py --size 820x1180    the same pages on a portrait tablet
    .\\.venv\\Scripts\\python tools\\page_check.py --group F NV       only some streams' routes

The simulator (tools/live_sim.py) is the real app against the made-up league (app/demo), so this costs
no CFBD calls. Routes name the league's teams and games through placeholders ({US} the demo team,
{OPP} the opponent in the game under way, {LIVE} that game, {LAST} and {NEXT} the demo team's games
before and after it, {S} the season), filled in from the league before the pages load. Edge (headless, driven over its DevTools protocol) loads each page, waits
for its loading skeletons to go, and reads the text a reader would see; each hit is printed with its
surroundings.
Exit status 0 when every page is clean, 1 when any is not, 2 when Edge or the server is missing.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Phase 16: one group per stream. Each stream adds its routes to its own group only (hotspot rule), so
# parallel branches never edit the same lines. ROUTES is every group, in this order, without repeats.
ROUTE_GROUPS: dict[str, list[str]] = {
    # --- F: every page as it stood before Phase 16, plus a flyout team page ---
    "F": [
        "season", "newspaper", "program", "live", "leaders", "roster", "recruiting", "ratings",
        "archive", "glossary", "settings", "team={US}", "team={OPP}",
    ],
    # --- NV: national lists (national=<metric>?team=&year=&scope=), search, glossary ---
    "NV": [
        "national=profile:ypp", "national=profile:ypp_d?team={OPP}&scope=conference", "national=advanced:defense_explosiveness",
        "national=board:passing:YDS", "national=poll:AP", "national=rating:sp", "national=class:{S}",
        "national=recruit:{S}", "national=returning:percentPPA", "national=bluechip:ratio?scope=conference",
        "national=profile:ypp?year={S-1}&team={OPP}", "national=nope:nothing",
    ],
    # --- SEASON: Season, team pages, Ratings ---
    "SEASON": ["season", "season=polls:Coaches", "team={US}", "team={OPP}", "ratings", "ratings=sp", "ratings=elo?team={OPP}"],
    # --- PROGRAM: Game program (the simulator's game under way, a finished one, an upcoming one) ---
    "PROGRAM": ["program", "program={LIVE}", "program={LAST}", "program={NEXT}"],
    # --- PEOPLE: Leaders, Roster, Recruiting, the player card ---
    "PEOPLE": [
        "leaders", "leaders=passing:YDS:national", "leaders=defensive:TOT:conference", "leaders=ppa:all:opponent",
        "leaders=usage:overall:national", "roster", "recruiting", "recruiting=national", "recruiting={S+1}:where",
    ],
    # --- PROFILES: configure, profiles ---
    "PROFILES": [],
    # --- SCORES: Newspaper, ticker ---
    "SCORES": [],
    # --- LIVE: Live sheet, Archive ---
    "LIVE": [],
    # --- DS: shell ---
    "DS": [],
    # --- public release Phase 5b: My teams, the opponents and My teams lists ---
    "MYTEAMS": ["myteams", "national=rating:sp?scope=opponents", "national=profile:ypp?scope=mine", "national=board:passing:YDS?scope=opponents"],
}
ROUTES = list(dict.fromkeys(route for group in ROUTE_GROUPS.values() for route in group))
DEFAULT_SIZE = (1180, 820)
BAD = re.compile(r"\b(undefined|null|NaN|Infinity)\b|\[object Object\]")
# Any Chromium browser with the DevTools protocol works: Edge on Windows, Chrome or Chromium elsewhere.
EDGE_PATHS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
]
BROWSER_COMMANDS = ("msedge", "microsoft-edge", "microsoft-edge-stable", "google-chrome", "google-chrome-stable", "chrome", "chromium", "chromium-browser")
# Text the app shows on purpose that contains one of the words (none today); matched against the hit's context.
ALLOWED: list[re.Pattern[str]] = []


def find_edge() -> str | None:
    for path in EDGE_PATHS:
        if os.path.exists(path):
            return path
    return next((found for found in (shutil.which(name) for name in BROWSER_COMMANDS) if found), None)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_for(url: str, seconds: float = 90) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{url}/api/health", timeout=3) as response:
                if response.status == 200:
                    return True
        except OSError:
            time.sleep(0.5)
    return False


class Edge:
    """Headless Edge driven over its DevTools protocol (websockets ships with uvicorn[standard]).
    Each page is loaded, given time for its fetches (until no loading skeleton is left, or the
    budget runs out), and its visible text read with document.body.innerText. Unlike --dump-dom this
    also works on the Live sheet, whose event stream never goes quiet."""

    def __init__(self, path: str, profile: str, size: tuple[int, int] = DEFAULT_SIZE) -> None:
        self.port = free_port()
        self.size = size
        self.proc = subprocess.Popen([path, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check", f"--user-data-dir={profile}", f"--remote-debugging-port={self.port}", f"--window-size={size[0]},{size[1]}", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.ws = None
        self.next_id = 0
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/json/list", timeout=3) as response:
                    targets = json.loads(response.read())
                page = next((t for t in targets if t.get("type") == "page"), None)
                if page:
                    from websockets.sync.client import connect

                    self._conn = connect(page["webSocketDebuggerUrl"], max_size=None)
                    self.ws = self._conn.__enter__()
                    # --window-size sets the outer window; this sets the viewport the page lays out in
                    self.call("Emulation.setDeviceMetricsOverride", width=size[0], height=size[1], deviceScaleFactor=1, mobile=False)
                    return
            except OSError:
                pass
            time.sleep(0.3)
        raise RuntimeError("Edge's debugging port did not answer")

    def call(self, method: str, **params: object) -> dict:
        self.next_id += 1
        mine = self.next_id
        self.ws.send(json.dumps({"id": mine, "method": method, "params": params}))
        while True:
            message = json.loads(self.ws.recv(timeout=60))
            if message.get("id") == mine:
                return message.get("result") or {}

    def text_of(self, url: str, budget_ms: int) -> str:
        self.call("Page.navigate", url="about:blank")
        self.call("Page.navigate", url=url)
        deadline = time.monotonic() + budget_ms / 1000
        time.sleep(1.5)
        while time.monotonic() < deadline:
            busy = self.call("Runtime.evaluate", expression="document.readyState !== 'complete' || !!document.querySelector('.skel')", returnByValue=True)
            if not busy.get("result", {}).get("value"):
                break
            time.sleep(0.5)
        time.sleep(1.0)  # one more beat for the last redraw
        result = self.call("Runtime.evaluate", expression="document.body ? document.body.innerText : ''", returnByValue=True)
        return str(result.get("result", {}).get("value") or "")

    def close(self) -> None:
        try:
            if self.ws is not None:
                self._conn.__exit__(None, None, None)
        finally:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()


def check_page(edge: Edge, url: str, budget_ms: int) -> tuple[list[str], int]:
    text = re.sub(r"\s+", " ", edge.text_of(url, budget_ms))
    hits = []
    for match in BAD.finditer(text):
        context = text[max(0, match.start() - 60): match.end() + 60].strip()
        if any(p.search(context) for p in ALLOWED):
            continue
        hits.append(context)
    return hits, len(text)


def parse_size(value: str) -> tuple[int, int]:
    """'820x1180' -> (820, 1180); argparse reports anything else."""
    match = re.fullmatch(r"\s*(\d{3,4})\s*[xX]\s*(\d{3,4})\s*", value or "")
    if not match:
        raise argparse.ArgumentTypeError(f"size must look like 1180x820, not {value!r}")
    return int(match.group(1)), int(match.group(2))


def league_values() -> dict[str, str]:
    """The placeholders' values: the simulator's league, at the game it opens on."""
    from urllib.parse import quote

    sys.path.insert(0, str(ROOT))
    from app.demo import names as N
    from app.demo.run import CACHE_DIR, demo_season, next_game
    from app.demo.upstream import load_world

    world = load_world(season=demo_season(), seed=2026, cache_dir=CACHE_DIR)
    league = world.league
    us = league.team(N.OUR_SCHOOL)
    live = next_game(world)
    ours = sorted((r for r in world.seasons[world.season].records if us.id in (r.slot.home, r.slot.away) and r.slot.season_type == "regular"),
                  key=lambda r: r.slot.start)
    before = [r for r in ours if r.slot.start < live.slot.start]
    after = [r for r in ours if r.slot.start > live.slot.start]
    opp = league.by_id[live.slot.away if live.slot.home == us.id else live.slot.home]
    season = world.season
    return {"US": quote(us.school), "OPP": quote(opp.school), "LIVE": str(live.id), "LAST": str((before or ours)[-1].id),
            "NEXT": str((after or ours)[0].id), "S": str(season), "S-1": str(season - 1), "S+1": str(season + 1)}


def fill(route: str, values: dict[str, str]) -> str:
    for key, value in values.items():
        route = route.replace("{" + key + "}", value)
    return route


def routes_for(groups: list[str] | None, routes: list[str] | None) -> list[str]:
    """The routes to check: --routes as given, else the chosen groups, else every group."""
    if routes:
        return routes
    if groups:
        unknown = [g for g in groups if g not in ROUTE_GROUPS]
        if unknown:
            raise SystemExit(f"unknown group(s) {', '.join(unknown)}; known: {', '.join(ROUTE_GROUPS)}")
        return list(dict.fromkeys(route for g in groups for route in ROUTE_GROUPS[g]))
    return ROUTES


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--url", help="check a server that is already running instead of starting the simulator")
    parser.add_argument("--budget", type=int, default=15000, help="milliseconds Edge lets each page run (default 15000)")
    parser.add_argument("--routes", nargs="*", default=None, help="routes to check (default: every group)")
    parser.add_argument("--group", nargs="*", default=None, help=f"only these streams' routes ({', '.join(ROUTE_GROUPS)})")
    parser.add_argument("--size", type=parse_size, default=DEFAULT_SIZE, help="viewport as WIDTHxHEIGHT (default 1180x820; the portrait tablet is 820x1180)")
    args = parser.parse_args(argv)
    args.routes = routes_for(args.group, args.routes)
    if any("{" in route for route in args.routes):
        values = league_values()
        args.routes = [fill(route, values) for route in args.routes]

    edge = find_edge()
    if edge is None:
        print("No Edge, Chrome or Chromium found; install one or add its path to EDGE_PATHS.", file=sys.stderr)
        return 2
    sim = None
    base = args.url.rstrip("/") if args.url else None
    if base is None:
        port = free_port()
        base = f"http://127.0.0.1:{port}"
        sim = subprocess.Popen([sys.executable, str(ROOT / "tools" / "live_sim.py"), "--port", str(port), "--speed", "4", "--start", "75", "--no-browser"], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        if not wait_for(base):
            print(f"No server answered at {base}.", file=sys.stderr)
            return 2
        failures = 0
        with tempfile.TemporaryDirectory(prefix="kickoff-page-check-", ignore_cleanup_errors=True) as profile:
            browser = Edge(edge, profile, args.size)
            print(f"Viewport {args.size[0]}x{args.size[1]}, {len(args.routes)} route(s).")
            try:
                results = [(route, *check_page(browser, f"{base}/#{route}", args.budget)) for route in args.routes]
            finally:
                browser.close()
            for route, hits, size in results:
                if size < 120:  # the shell alone is about 100 characters; an empty-state page is more
                    print(f"  ?  #{route}: the page came back nearly empty ({size} characters)")
                    failures += 1
                elif hits:
                    failures += 1
                    print(f"FAIL #{route}: {len(hits)} hit(s)")
                    for hit in hits[:5]:
                        print(f"       ...{hit}...")
                else:
                    print(f"  ok #{route} ({size:,} characters of text)")
        print("Every page is clean." if failures == 0 else f"{failures} page(s) need a look.")
        return 0 if failures == 0 else 1
    finally:
        if sim is not None:
            sim.terminate()
            try:
                sim.wait(timeout=15)
            except subprocess.TimeoutExpired:
                sim.kill()


if __name__ == "__main__":
    raise SystemExit(main())
