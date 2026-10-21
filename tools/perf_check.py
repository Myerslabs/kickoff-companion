"""Measure the pages' speed against a running server (freeze wave F7, 2026-10-20).

    .\\.venv\\Scripts\\python tools\\perf_check.py [base] [label]

For the main routes: the warm latency (four calls each, the median of the last three), the size on the wire and decoded,
and whether the answer came compressed. Then a first open: the page, every script it leads to (the static imports, followed)
and the stylesheets, how many files, how much on the wire, and their cache headers. The usual target is the demo
(`python -m app --demo --no-browser`, http://127.0.0.1:8650); a real install works the same (the label names the run).
The numbers of 2026-10-20 are in docs/02-ARCHITECTURE.md, "Speed on the home network".
"""

from __future__ import annotations

import gzip
import json
import re
import statistics
import sys
import time
import urllib.parse
import urllib.request

ROUTES = (
    "/api/program/next",
    "/api/roster",
    "/api/season/overview",
    "/api/newspaper",
    "/api/team/{team}",
    "/api/season/leaders",
    "/api/top25",
    "/api/ratings",
    "/api/grades?group=QB",
    "/api/ticker",
    "/api/health",
)
ROUNDS = 4
IMPORT = re.compile(r'^import .*? from "(\./[^"]+|\.\./[^"]+)";', re.M)
REFS = re.compile(r'(?:src|href)="(/static/[^"]+)"')


def get(base: str, path: str) -> tuple[float, int, int, dict[str, str]]:
    """(milliseconds, bytes on the wire, bytes decoded, headers lower-cased) of one GET that accepts gzip."""
    request = urllib.request.Request(base + path, headers={"Accept-Encoding": "gzip"})
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 - the address is the caller's own server
        raw = response.read()
        headers = {k.lower(): v for k, v in response.headers.items()}
    took = (time.perf_counter() - started) * 1000
    body = gzip.decompress(raw) if headers.get("content-encoding") == "gzip" else raw
    return took, len(raw), len(body), headers


def wait_for(base: str, seconds: float = 120) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            urllib.request.urlopen(base + "/api/health", timeout=3).read()  # noqa: S310
            return True
        except Exception:  # noqa: BLE001 - not up yet
            time.sleep(1)
    return False


def our_school(base: str) -> str | None:
    try:
        identity = json.loads(urllib.request.urlopen(base + "/api/identity", timeout=30).read())  # noqa: S310
    except Exception:  # noqa: BLE001 - no identity, no team page in the run
        return None
    data = identity.get("data") if isinstance(identity.get("data"), dict) else identity
    school = data.get("school") if isinstance(data, dict) else None
    return school if isinstance(school, str) and school else None


def resolve(folder: str, relative: str) -> str:
    out: list[str] = []
    for part in (folder + "/" + relative).split("/"):
        if part == "..":
            out.pop()
        elif part != ".":
            out.append(part)
    return "/".join(out)


def first_open(base: str) -> tuple[int, int, dict[str, int]]:
    """Every static file a first open asks for: the page's scripts and stylesheets, each script's static imports."""
    index = urllib.request.urlopen(base + "/", timeout=30).read().decode("utf-8", "replace")  # noqa: S310
    queue = [ref for ref in REFS.findall(index) if ref.endswith((".js", ".css"))]
    seen: set[str] = set()
    count = total = 0
    cache: dict[str, int] = {}
    while queue:
        path = queue.pop()
        if path in seen:
            continue
        seen.add(path)
        try:
            _ms, wire, _body, headers = get(base, path)
        except Exception:  # noqa: BLE001 - a missing file is the page's problem, not the measurement's
            continue
        count += 1
        total += wire
        cache[headers.get("cache-control", "")] = cache.get(headers.get("cache-control", ""), 0) + 1
        if path.endswith(".js"):
            text = urllib.request.urlopen(base + path, timeout=30).read().decode("utf-8", "replace")  # noqa: S310
            folder = path.rsplit("/", 1)[0]
            queue.extend(resolve(folder, imported) for imported in IMPORT.findall(text))
    return count, total, cache


def main(argv: list[str]) -> int:
    base = (argv[1] if len(argv) > 1 else "http://127.0.0.1:8650").rstrip("/")
    label = argv[2] if len(argv) > 2 else "run"
    if not wait_for(base):
        print(f"No server answered at {base}/api/health within two minutes.")
        return 1
    school = our_school(base)
    print(f"== {label} ==")
    for route in ROUTES:
        if "{team}" in route:
            if not school:
                continue
            route = route.replace("{team}", urllib.parse.quote(school))
        times: list[float] = []
        wire = body = 0
        headers: dict[str, str] = {}
        try:
            for _ in range(ROUNDS):
                took, wire, body, headers = get(base, route)
                times.append(took)
        except Exception as exc:  # noqa: BLE001 - the route is reported, the run goes on
            print(f"{route:28} failed: {exc}")
            continue
        print(f"{route:28} warm {statistics.median(times[1:]):6.0f} ms  wire {wire / 1024:6.1f} KB  body {body / 1024:6.1f} KB  {headers.get('content-encoding', '')}")
    count, total, cache = first_open(base)
    print(f"first open: {count} static files, {total / 1024:.0f} KB on the wire; cache headers {cache}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
