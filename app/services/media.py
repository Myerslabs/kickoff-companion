"""Headshots (X2): fetched once from the public ESPN pattern the architecture doc names
(verified 2026-09-23 with three roster athlete IDs), stored under data/headshots/, and served
by our own route so the tablet never talks to a third-party host. A miss is remembered for a
week so a player without a photo costs one upstream call, not one per view. After repeated
upstream failures the fetcher pauses for ten minutes and answers 404 from memory."""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

log = logging.getLogger("kickoff.media")

HEADSHOT_URL = "https://a.espncdn.com/i/headshots/college-football/players/full/{id}.png"
ID_PATTERN = re.compile(r"^\d{1,12}$")
TIMEOUT = httpx.Timeout(8.0, connect=4.0)
MISS_TTL_SECONDS = 7 * 24 * 3600
PAUSE_AFTER_FAILURES = 5
PAUSE_SECONDS = 10 * 60
MAX_BYTES = 4 * 1024 * 1024


@dataclass
class Headshot:
    path: Path | None  # a PNG on disk, or None for a miss
    cached: bool
    reason: str | None = None


class HeadshotStore:
    def __init__(self, data_dir: Path, transport: httpx.AsyncBaseTransport | None = None, user_agent: str = "KickoffCompanion") -> None:
        self.dir = data_dir / "headshots"
        self.dir.mkdir(parents=True, exist_ok=True)
        self._http = httpx.AsyncClient(timeout=TIMEOUT, transport=transport, headers={"User-Agent": user_agent, "Accept": "image/png,image/*"}, follow_redirects=True)
        self.failures = 0
        self.paused_until = 0.0
        self.stats = {"served_from_disk": 0, "fetched": 0, "misses": 0, "failures": 0}

    async def aclose(self) -> None:
        await self._http.aclose()

    @staticmethod
    def valid_id(player_id: str) -> bool:
        return bool(ID_PATTERN.match(player_id or ""))

    def _png(self, player_id: str) -> Path:
        return self.dir / f"{player_id}.png"

    def _miss(self, player_id: str) -> Path:
        return self.dir / f"{player_id}.miss.json"

    def _miss_is_fresh(self, player_id: str) -> bool:
        path = self._miss(player_id)
        if not path.exists():
            return False
        try:
            stamp = json.loads(path.read_text(encoding="utf-8")).get("at", 0)
        except (OSError, ValueError):
            return False
        return (time.time() - float(stamp or 0)) < MISS_TTL_SECONDS

    def _remember_miss(self, player_id: str, reason: str) -> None:
        try:
            self._miss(player_id).write_text(json.dumps({"at": time.time(), "reason": reason}), encoding="utf-8")
        except OSError as exc:
            log.warning("Could not record headshot miss for %s: %s", player_id, exc)

    async def get(self, player_id: str) -> Headshot:
        if not self.valid_id(player_id):
            return Headshot(None, True, "invalid id")
        png = self._png(player_id)
        if png.exists() and png.stat().st_size > 0:
            self.stats["served_from_disk"] += 1
            return Headshot(png, True)
        if self._miss_is_fresh(player_id):
            self.stats["misses"] += 1
            return Headshot(None, True, "no photo (remembered)")
        now = time.time()
        if now < self.paused_until:
            return Headshot(None, False, f"headshot fetches paused for {int(self.paused_until - now)} s after repeated failures")

        try:
            response = await self._http.get(HEADSHOT_URL.format(id=player_id))
        except httpx.HTTPError as exc:
            self._note_failure(f"{exc.__class__.__name__}")
            return Headshot(None, False, f"upstream error: {exc.__class__.__name__}")

        if response.status_code == 404:
            self.failures = 0
            self._remember_miss(player_id, "404")
            self.stats["misses"] += 1
            return Headshot(None, False, "no photo")
        if response.status_code != 200:
            self._note_failure(f"HTTP {response.status_code}")
            return Headshot(None, False, f"upstream HTTP {response.status_code}")
        content_type = response.headers.get("content-type", "")
        body = response.content
        if not content_type.startswith("image/") or not body or len(body) > MAX_BYTES or not body.startswith(b"\x89PNG"):
            self.failures = 0
            self._remember_miss(player_id, f"not a png ({content_type or 'no type'}, {len(body)} bytes)")
            self.stats["misses"] += 1
            return Headshot(None, False, "upstream did not return a PNG")
        try:
            tmp = png.with_suffix(".tmp")
            tmp.write_bytes(body)
            tmp.replace(png)
        except OSError as exc:
            log.warning("Could not store headshot %s: %s", player_id, exc)
            return Headshot(None, False, f"could not store: {exc.strerror or exc}")
        self.failures = 0
        self.stats["fetched"] += 1
        return Headshot(png, False)

    def _note_failure(self, reason: str) -> None:
        self.failures += 1
        self.stats["failures"] += 1
        log.warning("Headshot fetch failed (%s), %d in a row", reason, self.failures)
        if self.failures >= PAUSE_AFTER_FAILURES:
            self.paused_until = time.time() + PAUSE_SECONDS
            self.failures = 0
            log.warning("Pausing headshot fetches for %d minutes", PAUSE_SECONDS // 60)
