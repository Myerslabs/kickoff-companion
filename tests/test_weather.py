"""NWS weather: the recorded forecast parses, the game-day day and night periods are picked,
the row picks night for an evening kickoff, malformed periods are skipped, a dead service serves
the stored forecast as stale, and repeated failures pause the client."""

from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx

from app.weather import Forecast, NwsClient, Period, parse_periods, pick_periods

FIXTURES = Path(__file__).parent / "fixtures" / "nws"


def forecast_payload() -> dict:
    return json.loads((FIXTURES / "forecast.json").read_text(encoding="utf-8"))


def points_payload() -> dict:
    return json.loads((FIXTURES / "points.json").read_text(encoding="utf-8"))


def run(coro):
    return asyncio.run(coro)


def test_recorded_forecast_parses_and_picks_the_game_day():
    periods, skipped = parse_periods(forecast_payload())
    assert skipped == 0 and len(periods) >= 12
    first_day = next(p for p in periods if p.isDaytime).local_date()
    day, night = pick_periods(periods, first_day)
    assert day is not None and night is not None and day.isDaytime and night.isDaytime is False
    assert day.temperature and day.wind_mph and day.shortForecast
    assert day.rain_chance is None or 0 <= day.rain_chance <= 100
    assert pick_periods(periods, first_day + timedelta(days=30)) == (None, None)


def test_row_uses_the_night_period_for_an_evening_kickoff():
    periods, _ = parse_periods(forecast_payload())
    game_day = next(p for p in periods if p.isDaytime).local_date()
    day, night = pick_periods(periods, game_day)
    forecast = Forecast(day, night, "JAX", datetime.now(timezone.utc))
    noon = datetime.combine(game_day, datetime.min.time()).replace(hour=15)
    evening = datetime.combine(game_day, datetime.min.time()).replace(hour=19, minute=30)
    assert forecast.as_dict(noon)["period"] == day.name
    assert forecast.as_dict(evening)["period"] == night.name
    row = forecast.as_dict(noon)
    assert row["available"] and row["source"] == "National Weather Service" and isinstance(row["tempF"], (int, float))


def test_malformed_periods_are_skipped():
    periods, skipped = parse_periods({"properties": {"periods": [{"name": "Today", "temperature": "hot"}, "junk", None, {"name": "OK", "startTime": "2026-09-26T06:00:00-04:00", "isDaytime": True, "temperature": 80}]}})
    assert [p.name for p in periods] == ["OK"] and skipped == 3
    assert parse_periods(None) == ([], 1) and parse_periods({"properties": {}}) == ([], 1)
    assert Period(windSpeed="8 to 13 mph").wind_mph == 13 and Period(windSpeed="calm").wind_mph is None and Period().local_date() is None
    assert Period(startTime="not a date").local_date() is None


class FakeNws:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.fail = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(str(request.url))
        if self.fail:
            return httpx.Response(503)
        if "/points/" in str(request.url):
            return httpx.Response(200, json=points_payload())
        return httpx.Response(200, json=forecast_payload())


def make_client(tmp_path: Path, nws: FakeNws) -> tuple[NwsClient, dict]:
    clock = {"now": datetime(2026, 9, 23, 16, 0, tzinfo=timezone.utc)}
    return NwsClient(tmp_path, transport=httpx.MockTransport(nws.handler), clock=lambda: clock["now"]), clock


def test_client_fetches_two_calls_then_serves_from_disk(tmp_path: Path):
    nws = FakeNws()
    client, clock = make_client(tmp_path, nws)
    game_day = date(2026, 9, 23)

    async def scenario():
        first = await client.forecast(29.6499, -82.3486, game_day)
        second = await client.forecast(29.6499, -82.3486, game_day)
        await client.aclose()
        return first, second

    first, second = run(scenario())
    assert first.day is not None and first.office == "JAX" and not first.stale
    assert len(nws.calls) == 2 and second.fetched_at == first.fetched_at
    assert (tmp_path / "weather" / "29.6499_-82.3486.json").exists()


def test_dead_service_serves_stale_and_pauses(tmp_path: Path):
    nws = FakeNws()
    client, clock = make_client(tmp_path, nws)
    game_day = date(2026, 9, 23)

    async def scenario():
        good = await client.forecast(29.6499, -82.3486, game_day)
        clock["now"] += timedelta(hours=4)
        nws.fail = True
        stale = await client.forecast(29.6499, -82.3486, game_day)
        calls = len(nws.calls)
        await client.forecast(29.6499, -82.3486, game_day)
        await client.forecast(29.6499, -82.3486, game_day)
        paused = await client.forecast(29.6499, -82.3486, game_day)
        await client.aclose()
        return good, stale, calls, paused

    good, stale, calls, paused = run(scenario())
    assert stale.stale and stale.error == "NWS points HTTP 503" and stale.day.name == good.day.name
    assert "paused" in paused.error and len(nws.calls) == calls + 2
    row = stale.as_dict(None)
    assert row["available"] and row["stale"]


def test_nothing_stored_and_service_down_is_unavailable_not_a_crash(tmp_path: Path):
    nws = FakeNws()
    nws.fail = True
    client, clock = make_client(tmp_path, nws)

    async def scenario():
        result = await client.forecast(29.6499, -82.3486, date(2026, 9, 26))
        await client.aclose()
        return result

    result = run(scenario())
    assert result.day is None and not result.stale and "503" in result.error
    assert result.as_dict(None) == {"available": False, "source": "National Weather Service", "error": result.error, "stale": False, "fetchedAt": None}
