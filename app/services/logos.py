"""Team logos (Phase 16, audit G3-10, P-08, DS-07): fetched once from CFBD's logo CDN, stored under
data/logos/, and served by our own route (/media/logo/{team_id}?v=light|dark) so the tablet never
talks to a third-party host (CLAUDE.md, Environment 5). Modelled on the headshot store.

CFBD's /teams/fbs lists each team's logos at fixed paths keyed by the team id (recorded 2026-09-20:
https://cdn.collegefootballdata.com/logos/500/57.png and logos-dark/500/57.png, sizes 16 to 500),
so the store builds the upstream URL from the id alone. The CDN is not the CFBD API: a logo costs
no quota, but the fetch still follows the network rules. Each fetch has a timeout and one retry with
a short backoff, a body over the size cap or not a PNG is remembered as a miss, a 404 is remembered
for a week, at most four fetches run at once, one fetch per logo at a time, and after repeated
failures the store pauses for ten minutes and answers 404 from memory (the circuit breaker). The
page falls back to the team's mono tile on any 404."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

log = logging.getLogger("kickoff.logos")

LOGO_URL = "https://cdn.collegefootballdata.com/{folder}/{size}/{id}.png"
SIZE = 256  # drawn at 20 to 72 CSS pixels; 256 stays sharp on a 2x tablet screen at the largest
VARIANTS = {"light": "logos", "dark": "logos-dark"}
ID_PATTERN = re.compile(r"^\d{1,9}$")
TIMEOUT = httpx.Timeout(8.0, connect=4.0)
ATTEMPTS = 2  # one retry on a network error or a 5xx
RETRY_BACKOFF_SECONDS = 0.5
MISS_TTL_SECONDS = 7 * 24 * 3600
PAUSE_AFTER_FAILURES = 5
PAUSE_SECONDS = 10 * 60
MAX_BYTES = 1024 * 1024
CONCURRENCY = 4
PNG_SIGNATURE = b"\x89PNG"


def logo_path(team_id: Any, variant: str = "light") -> str | None:
    """Our own URL for a team's logo, or None without a usable id."""
    if isinstance(team_id, bool) or not isinstance(team_id, (int, str)) or not ID_PATTERN.match(str(team_id)):
        return None
    return f"/media/logo/{team_id}" if variant == "light" else f"/media/logo/{team_id}?v=dark"


def logo_fields(team_id: Any, logos: Any) -> dict[str, str | None]:
    """{logo, logoDark} for a team block: local URLs, never the CDN's. A variant CFBD does not list
    for the team is None, so the page draws the mono tile instead of asking for a missing file."""
    urls = [u for u in logos if isinstance(u, str)] if isinstance(logos, list) else []
    known = any("/logos/" in u or "/logos-dark/" in u for u in urls)
    has_dark = any("/logos-dark/" in u for u in urls) if known else len(urls) > 1  # CFBD's list: light first, dark second
    return {"logo": logo_path(team_id) if urls else None, "logoDark": logo_path(team_id, "dark") if urls and has_dark else None}


@dataclass
class Logo:
    path: Path | None  # a PNG on disk, or None
    cached: bool  # answered from disk or memory without asking the CDN
    reason: str | None = None


class LogoStore:
    def __init__(
        self,
        data_dir: Path,
        transport: httpx.AsyncBaseTransport | None = None,
        user_agent: str = "KickoffCompanion",
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        self.dir = data_dir / "logos"
        self.dir.mkdir(parents=True, exist_ok=True)
        self._http = httpx.AsyncClient(timeout=TIMEOUT, transport=transport, headers={"User-Agent": user_agent, "Accept": "image/png,image/*"}, follow_redirects=True)
        self._sleep = sleep or asyncio.sleep
        self._gate = asyncio.Semaphore(CONCURRENCY)
        self._locks: dict[str, asyncio.Lock] = {}
        self.failures = 0
        self.paused_until = 0.0
        self.stats = {"served_from_disk": 0, "fetched": 0, "misses": 0, "failures": 0}

    async def aclose(self) -> None:
        await self._http.aclose()

    @staticmethod
    def valid(team_id: str, variant: str) -> bool:
        return bool(ID_PATTERN.match(team_id or "")) and variant in VARIANTS

    def _stem(self, team_id: str, variant: str) -> str:
        return team_id if variant == "light" else f"{team_id}-dark"

    def _png(self, stem: str) -> Path:
        return self.dir / f"{stem}.png"

    def _miss(self, stem: str) -> Path:
        return self.dir / f"{stem}.miss.json"

    def _miss_is_fresh(self, stem: str) -> bool:
        path = self._miss(stem)
        if not path.exists():
            return False
        try:
            stamp = json.loads(path.read_text(encoding="utf-8")).get("at", 0)
        except (OSError, ValueError, AttributeError):
            return False
        try:
            return (time.time() - float(stamp or 0)) < MISS_TTL_SECONDS
        except (TypeError, ValueError):
            return False

    def _remember_miss(self, stem: str, reason: str) -> None:
        try:
            self._miss(stem).write_text(json.dumps({"at": time.time(), "reason": reason}), encoding="utf-8")
        except OSError as exc:
            log.warning("Could not record logo miss for %s: %s", stem, exc)

    def _on_disk(self, stem: str) -> Path | None:
        png = self._png(stem)
        try:
            return png if png.exists() and png.stat().st_size > 0 else None
        except OSError:
            return None

    async def get(self, team_id: str, variant: str = "light") -> Logo:
        if not self.valid(team_id, variant):
            return Logo(None, True, "invalid id or variant")
        stem = self._stem(team_id, variant)
        hit = self._on_disk(stem)
        if hit is not None:
            self.stats["served_from_disk"] += 1
            return Logo(hit, True)
        lock = self._locks.setdefault(stem, asyncio.Lock())
        async with lock:  # one fetch per logo: a table of 20 rows asking at once costs one request each
            hit = self._on_disk(stem)
            if hit is not None:
                self.stats["served_from_disk"] += 1
                return Logo(hit, True)
            if self._miss_is_fresh(stem):
                self.stats["misses"] += 1
                return Logo(None, True, "no logo (remembered)")
            now = time.time()
            if now < self.paused_until:
                return Logo(None, False, f"logo fetches paused for {int(self.paused_until - now)} s after repeated failures")
            async with self._gate:
                return await self._fetch(team_id, variant, stem)

    async def _fetch(self, team_id: str, variant: str, stem: str) -> Logo:
        url = LOGO_URL.format(folder=VARIANTS[variant], size=SIZE, id=team_id)
        response: httpx.Response | None = None
        problem = ""
        for attempt in range(1, ATTEMPTS + 1):
            try:
                response = await self._http.get(url)
            except httpx.HTTPError as exc:
                response, problem = None, exc.__class__.__name__
            else:
                if response.status_code < 500:
                    break
                problem = f"HTTP {response.status_code}"
            if attempt < ATTEMPTS:
                await self._sleep(RETRY_BACKOFF_SECONDS * attempt)
        if response is None or response.status_code >= 500:
            self._note_failure(problem)
            return Logo(None, False, f"upstream error: {problem}")
        if response.status_code == 404:
            self.failures = 0
            self._remember_miss(stem, "404")
            self.stats["misses"] += 1
            return Logo(None, False, "no logo")
        if response.status_code != 200:
            self._note_failure(f"HTTP {response.status_code}")
            return Logo(None, False, f"upstream HTTP {response.status_code}")
        content_type = response.headers.get("content-type", "")
        body = response.content
        if not content_type.startswith("image/") or not body or len(body) > MAX_BYTES or not body.startswith(PNG_SIGNATURE):
            self.failures = 0
            self._remember_miss(stem, f"not a usable png ({content_type or 'no type'}, {len(body)} bytes)")
            self.stats["misses"] += 1
            return Logo(None, False, "upstream did not return a usable PNG")
        png = self._png(stem)
        try:
            tmp = png.with_suffix(".tmp")
            tmp.write_bytes(body)
            tmp.replace(png)
        except OSError as exc:
            log.warning("Could not store logo %s: %s", stem, exc)
            return Logo(None, False, f"could not store: {exc.strerror or exc}")
        self.failures = 0
        self.stats["fetched"] += 1
        return Logo(png, False)

    def _note_failure(self, reason: str) -> None:
        self.failures += 1
        self.stats["failures"] += 1
        log.warning("Logo fetch failed (%s), %d in a row", reason, self.failures)
        if self.failures >= PAUSE_AFTER_FAILURES:
            self.paused_until = time.time() + PAUSE_SECONDS
            self.failures = 0
            log.warning("Pausing logo fetches for %d minutes", PAUSE_SECONDS // 60)
