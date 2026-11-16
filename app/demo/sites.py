"""The demo's stand-ins for the keyless sites: news feeds and the weather service.

Headlines are written from the league's own results and schedule (a recap per final game, a
preview per upcoming one), as RSS 2.0 the feed parser reads like any other. Forecasts are made up
in the National Weather Service's shapes, seasonal for the date. Links point at a reserved
.invalid host, so nothing in the demo leads anywhere real; headshots always miss.
"""

from __future__ import annotations

import json
import random
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from xml.sax.saxutils import escape

from app.demo import names as N
from app.demo.season import World

DEMO_HOST = "https://news.kickoff-demo.invalid"

RECAP_FORMS = (
    "{w} beats {l} {ws}-{ls}",
    "{w} holds off {l}, {ws}-{ls}",
    "{w} rolls past {l} {ws}-{ls}",
    "{l} falls to {w} {ls}-{ws}",
    "Takeaways from {w}'s {ws}-{ls} win over {l}",
)
PREVIEW_FORMS = (
    "{a} at {h}: what to watch",
    "{h} hosts {a} this week",
    "Three questions as {a} visits {h}",
    "Injury notes ahead of {a} at {h}",
)


def headlines(world: World, now: datetime, team: str | None = None, limit: int = 30) -> list[dict]:
    """Recaps of final games and previews of the next week's, newest first."""
    league = world.league
    data = world.seasons[world.season]
    us = league.team(team) if team else None
    rows: list[dict] = []
    final = world.final(world.season, now)
    for r in reversed(final[-160:]):
        h, a = league.by_id[r.slot.home], league.by_id[r.slot.away]
        if us is not None and us.id not in (h.id, a.id):
            continue
        rng = random.Random(r.id)
        w, l_ = (h, a) if r.home_points > r.away_points else (a, h)
        ws, ls = max(r.home_points, r.away_points), min(r.home_points, r.away_points)
        title = rng.choice(RECAP_FORMS).format(w=w.school, l=l_.school, ws=ws, ls=ls)
        rows.append({"title": title, "link": f"{DEMO_HOST}/recap/{r.id}", "when": r.end + timedelta(minutes=rng.randint(20, 300))})
    upcoming = [r for r in data.records if r.slot.start > now and r.slot.start - now < timedelta(days=6)
                and (r.slot.announce is None or r.slot.announce <= now)]
    for r in upcoming[:80]:
        h, a = league.by_id[r.slot.home], league.by_id[r.slot.away]
        if us is not None and us.id not in (h.id, a.id):
            continue
        rng = random.Random(r.id * 7)
        when = min(now - timedelta(minutes=rng.randint(5, 600)), r.slot.start - timedelta(hours=6))
        rows.append({"title": rng.choice(PREVIEW_FORMS).format(h=h.school, a=a.school), "link": f"{DEMO_HOST}/preview/{r.id}", "when": when})
    rows = [row for row in rows if row["when"] <= now]
    rows.sort(key=lambda row: row["when"], reverse=True)
    return rows[:limit]


def _record(world: World, game_id: int):
    for data in world.seasons.values():
        for r in data.records:
            if r.slot.id == game_id:
                return r
    return None


def article_page(world: World, path: str) -> str | None:
    """FEAT-14: a made-up story page for a recap or preview link, in an ordinary publisher's shape (the copier reads it like
    any other: the article's paragraphs, the photo in og:image with its caption under it)."""
    import re as _re

    m = _re.match(r"^/(recap|preview)/(\d+)$", path)
    r = _record(world, int(m.group(2))) if m else None
    if r is None:
        return None
    league = world.league
    h, a = league.by_id[r.slot.home], league.by_id[r.slot.away]
    venue = f"{r.slot.venue.name} in {r.slot.venue.city}"
    day = r.slot.start.strftime("%A, %B %d").replace(" 0", " ")
    if m.group(1) == "recap":
        w, l_ = (h, a) if r.home_points > r.away_points else (a, h)
        ws, ls = max(r.home_points, r.away_points), min(r.home_points, r.away_points)
        title = f"{w.school} beats {l_.school} {ws}-{ls}"
        quarters = ", ".join(f"{x}-{y}" for x, y in zip(r.away_lines, r.home_lines, strict=False))
        paras = [
            f"{w.school} beat {l_.school} {ws}-{ls} on {day} at {venue}, a game that turned on a long drive in the second half.",
            f"The quarters went {quarters}, away team first, and the {w.mascot} never trailed after the break.",
            f"{l_.school}'s coach said the team will look at the film on Sunday and move on to next week's opponent.",
            f"{w.school}'s coach praised the defense, which forced two punts in a row late to hold the lead, and said the team will enjoy the win for a night.",
            "This is a made-up story in the test league, written by the app's simulator so the newspaper has whole stories to show.",
        ]
        color = w.color
    else:
        title = f"{a.school} at {h.school}: what to watch"
        paras = [
            f"{a.school} visits {h.school} on {day} at {venue}, one of the week's games the paper is watching.",
            f"The {h.mascot} have been strong at home this season, and the {a.mascot} will need a clean game on the road to keep up.",
            "Both coaches said this week that the game will come down to the lines, and to which team wins the turnover battle.",
            "Kickoff is set, the weather looks clear, and the stadium is expected to be full for this one.",
            "This is a made-up story in the test league, written by the app's simulator so the newspaper has whole stories to show.",
        ]
        color = h.color
    photo = f"{DEMO_HOST}/photo/{r.slot.id}.png?c={color.lstrip('#')}"
    body = "".join(f"<p>{escape(p)}</p>" for p in paras)
    caption = escape(f"The scene at {r.slot.venue.name}. (Photo: Test League Photographer)")
    return (
        f"<html><head><title>{escape(title)}</title><meta property='og:image' content='{escape(photo)}'></head><body>"
        f"<nav><a href='/'>Home</a> <a href='/scores'>Scores</a></nav><article><h1>{escape(title)}</h1>"
        f"<p>By: Demo Writer</p><picture><img src='{escape(photo)}' alt=''></picture><div class='s-image-caption'>{caption}</div>{body}</article>"
        "<footer>The test league. Nothing here is real.</footer></body></html>"
    )


def photo_png(color: str, width: int = 320, height: int = 200) -> bytes:
    """A plain picture in a team's color (a made-up photo for the test league's stories)."""
    import struct
    import zlib

    try:
        rgb = bytes(int(color[i : i + 2], 16) for i in (0, 2, 4))
    except (ValueError, IndexError):
        rgb = b"\x33\x66\x99"
    rows = b"".join(b"\x00" + rgb * width for _ in range(height))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b"")


def rss(title: str, items: list[dict]) -> bytes:
    body = [f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>{escape(title)}</title><link>{DEMO_HOST}/</link>']
    for item in items:
        body.append(
            f"<item><title>{escape(item['title'])}</title><link>{escape(item['link'])}</link>"
            f"<pubDate>{format_datetime(item['when'].astimezone(timezone.utc))}</pubDate></item>"
        )
    body.append("</channel></rss>")
    return "".join(body).encode("utf-8")


def nws_points(lat: float, lon: float) -> dict:
    return {"properties": {"gridId": "DMO", "gridX": 10, "gridY": 10, "forecast": "https://api.weather.gov/gridpoints/DMO/10,10/forecast",
                           "timeZone": "America/New_York", "relativeLocation": {"properties": {"city": "Demo", "state": "FL"}}}}


def nws_forecast(now: datetime) -> dict:
    rng = random.Random(now.date().toordinal())
    month = now.month
    high = {8: 89, 9: 84, 10: 75, 11: 65, 12: 57, 1: 55}.get(month, 75)
    periods = []
    start = datetime.combine(now.date(), datetime.min.time(), timezone(timedelta(hours=-4))) + timedelta(hours=6)
    for i in range(14):
        day = i % 2 == 0
        begin = start + timedelta(hours=12 * i)
        temp = high + rng.randint(-4, 4) if day else high - rng.randint(12, 20)
        sky = rng.choice(("Sunny", "Mostly Sunny", "Partly Cloudy", "Mostly Cloudy", "Chance Showers"))
        rain = 0 if "Showers" not in sky else rng.randint(20, 50)
        periods.append({
            "number": i + 1, "name": begin.strftime("%A") + ("" if day else " Night"), "startTime": begin.isoformat(),
            "endTime": (begin + timedelta(hours=12)).isoformat(), "isDaytime": day, "temperature": temp, "temperatureUnit": "F",
            "temperatureTrend": None, "probabilityOfPrecipitation": {"unitCode": "wmoUnit:percent", "value": rain},
            "windSpeed": f"{rng.randint(3, 8)} to {rng.randint(9, 15)} mph", "windDirection": rng.choice(("N", "NE", "E", "SE", "S", "SW", "W", "NW")),
            "icon": "https://api.weather.gov/icons/land/day/few?size=medium", "shortForecast": sky if day else sky.replace("Sunny", "Clear"),
            "detailedForecast": f"{sky}. {'High' if day else 'Low'} near {temp}.",
        })
    return {"type": "Feature", "properties": {"units": "us", "generatedAt": now.isoformat(), "updateTime": now.isoformat(), "periods": periods}}


class DemoSites:
    """An httpx handler for every keyless site the app fetches: feeds and the weather service."""

    def __init__(self, world: World, clock: Callable[[], datetime], team: str = N.OUR_SCHOOL) -> None:
        self.world = world
        self.clock = clock
        self.team = team

    def handler(self, request):
        import httpx

        url = str(request.url)
        now = self.clock()
        if "weather.gov/points" in url:
            return httpx.Response(200, content=json.dumps(nws_points(0, 0)).encode(), headers={"content-type": "application/geo+json"})
        if "weather.gov" in url:
            return httpx.Response(200, content=json.dumps(nws_forecast(now)).encode(), headers={"content-type": "application/geo+json"})
        if url.startswith(DEMO_HOST):  # FEAT-14: the copier reads the test league's stories and their photos
            path = request.url.path
            if path == "/robots.txt":
                return httpx.Response(404)
            if path.startswith("/photo/"):
                return httpx.Response(200, content=photo_png(request.url.params.get("c", "336699")), headers={"content-type": "image/png"})
            page = article_page(self.world, path)
            if page is not None:
                return httpx.Response(200, text=page, headers={"content-type": "text/html; charset=utf-8"})
            return httpx.Response(404)
        if request.method == "GET" and ("rss" in url or "feed" in url or "news" in url):
            # The team's own feed carries only its stories; any national feed carries the whole league.
            national = any(marker in url for marker in ("espn", "theathletic", "cbssports", "yahoo", "national"))
            items = headlines(self.world, now, None if national else self.team)
            return httpx.Response(200, content=rss("Kickoff Companion demo news", items), headers={"content-type": "application/rss+xml"})
        return httpx.Response(404)

    @staticmethod
    def media_handler(request):
        import httpx

        return httpx.Response(404)
