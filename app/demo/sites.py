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
        if request.method == "GET" and ("rss" in url or "feed" in url or "news" in url):
            # The team's own feed carries only its stories; any national feed carries the whole league.
            national = any(marker in url for marker in ("espn", "theathletic", "national"))
            items = headlines(self.world, now, None if national else self.team)
            return httpx.Response(200, content=rss("Kickoff Companion demo news", items), headers={"content-type": "application/rss+xml"})
        return httpx.Response(404)

    @staticmethod
    def media_handler(request):
        import httpx

        return httpx.Response(404)
