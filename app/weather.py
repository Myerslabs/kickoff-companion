"""Game-day weather (P6) from the National Weather Service when the CFBD tier has none.
Two keyless calls: /points/{lat},{lon} names the forecast office and grid, then the daily
forecast lists day and night periods with temperature, wind, sky, and rain chance. The owner
asked for the day's weather, not an hourly read. Verified 2026-09-23 for a home stadium
Stadium (grid JAX 42,32). Cached on disk per stadium for three hours, served stale when the
service is down, paused after repeated failures. Outside the CFBD quota."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

log = logging.getLogger("kickoff.weather")

POINTS_URL = "https://api.weather.gov/points/{lat:.4f},{lon:.4f}"
TIMEOUT = httpx.Timeout(10.0, connect=5.0)
FRESH_SECONDS = 3 * 3600
PAUSE_AFTER_FAILURES = 3
PAUSE_SECONDS = 15 * 60


class Period(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str | None = None
    startTime: str | None = None
    endTime: str | None = None
    isDaytime: bool | None = None
    temperature: float | None = None
    temperatureUnit: str | None = None
    windSpeed: str | None = None
    windDirection: str | None = None
    shortForecast: str | None = None
    detailedForecast: str | None = None
    probabilityOfPrecipitation: dict[str, Any] | None = None

    @property
    def rain_chance(self) -> float | None:
        value = (self.probabilityOfPrecipitation or {}).get("value")
        return float(value) if isinstance(value, (int, float)) else None

    @property
    def wind_mph(self) -> float | None:
        """'8 to 13 mph' -> 13, the top of the range, the number a fan wants."""
        if not self.windSpeed:
            return None
        numbers = [float(part) for part in self.windSpeed.replace("mph", "").replace("to", " ").split() if part.replace(".", "", 1).isdigit()]
        return max(numbers) if numbers else None

    def local_date(self) -> date | None:
        if not self.startTime:
            return None
        try:
            return datetime.fromisoformat(self.startTime).date()
        except ValueError:
            return None


@dataclass
class Forecast:
    day: Period | None
    night: Period | None
    office: str | None
    fetched_at: datetime | None
    stale: bool = False
    error: str | None = None

    def as_dict(self, kickoff_local: datetime | None) -> dict[str, Any]:
        """The weather row the UI draws, for the period that covers kickoff (day or night)."""
        period = self.day
        if kickoff_local is not None and self.night is not None and (kickoff_local.hour >= 18 or self.day is None):
            period = self.night
        if period is None:
            return {"available": False, "source": "National Weather Service", "error": self.error, "stale": self.stale, "fetchedAt": _iso(self.fetched_at)}
        return {
            "available": True,
            "source": "National Weather Service",
            "period": period.name,
            "tempF": period.temperature if (period.temperatureUnit or "F") == "F" else (period.temperature * 9 / 5 + 32 if period.temperature is not None else None),
            "windMph": period.wind_mph,
            "windDir": period.windDirection,
            "sky": period.shortForecast,
            "precipChance": period.rain_chance,
            "detail": period.detailedForecast,
            "day": self.day.shortForecast if self.day else None,
            "night": self.night.shortForecast if self.night else None,
            "stale": self.stale,
            "error": self.error,
            "fetchedAt": _iso(self.fetched_at),
        }


def _iso(dt: datetime | None) -> str | None:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z") if dt else None


def pick_periods(periods: list[Period], game_day: date) -> tuple[Period | None, Period | None]:
    """The daytime and night periods on the game date; None when the forecast does not reach it."""
    day = next((p for p in periods if p.local_date() == game_day and p.isDaytime), None)
    night = next((p for p in periods if p.local_date() == game_day and p.isDaytime is False), None)
    return day, night


def parse_periods(payload: Any) -> tuple[list[Period], int]:
    """Periods from a forecast document, one bad period skipped and counted. Never raises."""
    raw = ((payload or {}).get("properties") or {}).get("periods") if isinstance(payload, dict) else None
    if not isinstance(raw, list):
        return [], 1
    out: list[Period] = []
    skipped = 0
    for item in raw:
        try:
            out.append(Period.model_validate(item))
        except ValidationError:
            skipped += 1
    return out, skipped


class NwsClient:
    def __init__(self, data_dir: Path, transport: httpx.AsyncBaseTransport | None = None, user_agent: str = "KickoffCompanion (personal)", clock=None) -> None:
        self.dir = data_dir / "weather"
        self.dir.mkdir(parents=True, exist_ok=True)
        self._http = httpx.AsyncClient(timeout=TIMEOUT, transport=transport, headers={"User-Agent": user_agent, "Accept": "application/geo+json, application/json"}, follow_redirects=True)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._failures = 0
        self._paused_until = 0.0
        self._lock = asyncio.Lock()

    async def aclose(self) -> None:
        await self._http.aclose()

    def _disk(self, lat: float, lon: float) -> Path:
        return self.dir / f"{lat:.4f}_{lon:.4f}.json"

    def _load(self, lat: float, lon: float) -> tuple[list[Period], str | None, datetime | None]:
        path = self._disk(lat, lon)
        if not path.exists():
            return [], None, None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            periods, _ = parse_periods(raw.get("forecast"))
            return periods, raw.get("office"), datetime.fromisoformat(raw["fetchedAt"])
        except (OSError, ValueError, KeyError, TypeError) as exc:
            log.warning("Stored forecast %s unreadable: %s", path.name, exc)
            return [], None, None

    async def forecast(self, lat: float, lon: float, game_day: date) -> Forecast:
        periods, office, fetched_at = self._load(lat, lon)
        now = self._clock()
        if fetched_at is not None and (now - fetched_at).total_seconds() < FRESH_SECONDS:
            day, night = pick_periods(periods, game_day)
            return Forecast(day, night, office, fetched_at)
        async with self._lock:
            if time.time() < self._paused_until:
                return self._stale(periods, office, fetched_at, game_day, "NWS paused after repeated failures")
            try:
                points = await self._http.get(POINTS_URL.format(lat=lat, lon=lon))
                if points.status_code != 200:
                    return self._failed(periods, office, fetched_at, game_day, f"NWS points HTTP {points.status_code}")
                props = (points.json() or {}).get("properties") or {}
                forecast_url = props.get("forecast")
                if not isinstance(forecast_url, str) or not forecast_url.startswith("https://api.weather.gov/"):
                    return self._failed(periods, office, fetched_at, game_day, "NWS points answer had no forecast link")
                response = await self._http.get(forecast_url)
                if response.status_code != 200:
                    return self._failed(periods, office, fetched_at, game_day, f"NWS forecast HTTP {response.status_code}")
                payload = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                return self._failed(periods, office, fetched_at, game_day, f"NWS {exc.__class__.__name__}")
            parsed, skipped = parse_periods(payload)
            if not parsed:
                return self._failed(periods, office, fetched_at, game_day, "NWS forecast had no periods")
            if skipped:
                log.warning("NWS forecast: skipped %d malformed period(s)", skipped)
            self._failures = 0
            fetched = self._clock()
            office_id = str(props.get("gridId") or office or "")
            try:
                self._disk(lat, lon).write_text(json.dumps({"fetchedAt": fetched.isoformat(), "office": office_id, "forecast": payload}), encoding="utf-8")
            except OSError as exc:
                log.warning("Could not store forecast: %s", exc)
            day, night = pick_periods(parsed, game_day)
            return Forecast(day, night, office_id or None, fetched)

    def _failed(self, periods: list[Period], office: str | None, fetched_at: datetime | None, game_day: date, reason: str) -> Forecast:
        self._failures += 1
        log.warning("Weather fetch failed (%s), %d in a row", reason, self._failures)
        if self._failures >= PAUSE_AFTER_FAILURES:
            self._paused_until = time.time() + PAUSE_SECONDS
            self._failures = 0
        return self._stale(periods, office, fetched_at, game_day, reason)

    def _stale(self, periods: list[Period], office: str | None, fetched_at: datetime | None, game_day: date, reason: str) -> Forecast:
        day, night = pick_periods(periods, game_day)
        return Forecast(day, night, office, fetched_at, stale=fetched_at is not None, error=reason)
