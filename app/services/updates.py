"""Is there a newer release? (Phase 16 wave 3, the 2026-10-07 list: "update check".) Once a day the server asks GitHub
for the public repository's releases and compares the newest with the version it runs (app.__version__). Keyless,
outside the CFBD quota, the answer kept in data/update.json, paused after failures, and off with the "Check for
updates" setting. It only tells; it never downloads or installs anything.

    UpdateChecker(data_dir, transport, user_agent, clock, enabled)
      await status(force=False) -> {current, latest, newer, url, notes, publishedAt, prerelease, checkedAt, error, enabled}
    version_key("v0.12.1") -> (0, 12, 1) or None
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from app import REPO_URL, __version__
from app.services.answers import atomic_write

log = logging.getLogger("kickoff.updates")

RELEASES_API = "https://api.github.com/repos/Myerslabs/kickoff-companion/releases?per_page=10"
TIMEOUT = httpx.Timeout(10.0, connect=5.0)
FRESH_SECONDS = 24 * 3600
PAUSE_SECONDS = 6 * 3600
VERSION = re.compile(r"^v?(\d+)\.(\d+)(?:\.(\d+))?$")


def version_key(tag: Any) -> tuple[int, int, int] | None:
    if not isinstance(tag, str):
        return None
    m = VERSION.match(tag.strip())
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class UpdateChecker:
    def __init__(self, data_dir: Path, transport: httpx.AsyncBaseTransport | None = None, user_agent: str = "KickoffCompanion", clock: Callable[[], datetime] | None = None, enabled: Callable[[], bool] | None = None, current: str = __version__) -> None:
        self.path = Path(data_dir) / "update.json"
        self._http = httpx.AsyncClient(timeout=TIMEOUT, transport=transport, headers={"User-Agent": user_agent, "Accept": "application/vnd.github+json"}, follow_redirects=True)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._enabled = enabled or (lambda: True)
        self.current = current
        self._lock = asyncio.Lock()
        self._paused_until = 0.0
        self._quiet_until = 0.0  # a private repository lists nothing: ask again tomorrow, say nothing

    async def aclose(self) -> None:
        await self._http.aclose()

    def _stored(self) -> dict[str, Any]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return raw if isinstance(raw, dict) else {}

    def _answer(self, stored: dict[str, Any], error: str | None = None) -> dict[str, Any]:
        latest = stored.get("latest") if isinstance(stored.get("latest"), str) else None
        mine, theirs = version_key(self.current), version_key(latest)
        return {
            "enabled": self._enabled(),
            "current": self.current,
            "latest": latest,
            "newer": bool(mine and theirs and theirs > mine),
            "url": stored.get("url") if isinstance(stored.get("url"), str) and stored["url"].startswith("https://github.com/") else f"{REPO_URL}/releases",
            "notes": stored.get("notes") if isinstance(stored.get("notes"), str) else None,
            "publishedAt": stored.get("publishedAt") if isinstance(stored.get("publishedAt"), str) else None,
            "prerelease": bool(stored.get("prerelease")),
            "checkedAt": stored.get("checkedAt") if isinstance(stored.get("checkedAt"), str) else None,
            "error": error,
        }

    async def status(self, force: bool = False) -> dict[str, Any]:
        stored = self._stored()
        if not self._enabled():
            return self._answer(stored)
        try:
            age = (self._clock() - datetime.fromisoformat(stored["checkedAt"].replace("Z", "+00:00"))).total_seconds()
        except (KeyError, TypeError, ValueError, AttributeError):
            age = None
        if not force and age is not None and age < FRESH_SECONDS:
            return self._answer(stored)
        async with self._lock:
            if time.time() < self._quiet_until and not force:
                return self._answer(stored)
            if time.time() < self._paused_until and not force:
                return self._answer(stored, "GitHub didn't answer earlier; the app tries again later.")
            try:
                response = await self._http.get(RELEASES_API)
                if response.status_code in (401, 403, 404):
                    # A private repository (or none yet) shows GitHub's API nothing to list: that is not a failure, so the
                    # app asks again tomorrow and says nothing in Settings (Phase 18.4).
                    self._quiet_until = time.time() + FRESH_SECONDS
                    log.info("Update check: GitHub lists no releases for the project (HTTP %s); nothing to compare.", response.status_code)
                    return self._answer(stored)
                if response.status_code != 200:
                    raise ValueError(f"HTTP {response.status_code}")
                releases = response.json()
                if not isinstance(releases, list):
                    raise ValueError("not a list")
            except (httpx.HTTPError, ValueError) as exc:
                self._paused_until = time.time() + PAUSE_SECONDS
                log.warning("Update check failed: %s", exc)
                return self._answer(stored, f"The update check didn't get an answer ({exc}).")
            self._paused_until = 0.0
            best: dict[str, Any] | None = None
            for item in releases:
                if not isinstance(item, dict) or item.get("draft"):
                    continue
                key = version_key(item.get("tag_name"))
                if key and (best is None or key > version_key(best.get("tag_name"))):
                    best = item
            fresh = {"checkedAt": _iso(self._clock())}
            if best is not None:
                body = best.get("body") if isinstance(best.get("body"), str) else ""
                fresh.update({
                    "latest": str(best.get("tag_name")).lstrip("v"),
                    "url": best.get("html_url"),
                    "notes": body.strip()[:600] or None,
                    "publishedAt": best.get("published_at"),
                    "prerelease": bool(best.get("prerelease")),
                })
            try:
                atomic_write(self.path, json.dumps(fresh, indent=1) + "\n")
            except OSError as exc:
                log.warning("Could not keep the update check: %s", exc)
            answer = self._answer(fresh)
            if answer["newer"]:
                log.info("A newer release is out: %s (running %s)", answer["latest"], self.current)
            return answer
