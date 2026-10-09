"""Wikipedia links for the big team headers (Phase 17 #4, owner 2026-10-07: the logo opens the team's football page,
the team name the school's page, the stadium the stadium's page; big headers only, tables keep the app's team page).

CFBD has no Wikipedia links, and a list of every team can't live in the repo (it names real teams), so the server
looks a team up the first time a header shows it and keeps the answer in data/wiki/links.json for 30 days. Keyless,
outside the CFBD quota, one request at a time with a pause between them (Wikipedia's API etiquette), paused after
repeated failures. Checked against the live API on 2026-10-07 with 20 real teams:

  football  "{school} {mascot} football" by title, following redirects; else the API's search, first result that
            ends in " football" (names like "Miami (OH)" need it).
  school    the first link after "represent..." in the football page's lead ("represents the University of ...");
            else the same in the athletics program's page ("{school} {mascot}"); else a Wikipedia search.
  stadium   the venue name by title, following redirects (CFBD's names lag naming-rights changes and Wikipedia's
            redirects carry them: an old name lands on the stadium's current page); else a Wikipedia search.

Every link is always usable: what can't be resolved is a Wikipedia search for it, so a tap never dead-ends.

    WikiClient(data_dir, transport, user_agent, clock)
      await team(school, mascot) -> {"football": url, "school": url, "resolved": bool}
      await venue(name)          -> {"stadium": url, "resolved": bool}
      await coach(name, school)  -> {"page": url, "resolved": bool}   (Phase 19: a coach's own page)
    page_url(title), search_url(words)
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode

import httpx

log = logging.getLogger("kickoff.wiki")

API = "https://en.wikipedia.org/w/api.php"
PAGE = "https://en.wikipedia.org/wiki/"
TIMEOUT = httpx.Timeout(10.0, connect=5.0)
FRESH_SECONDS = 30 * 86400
RETRY_SECONDS = 6 * 3600  # a lookup that fell back to a search is tried again after this
SPACING_SECONDS = 1.0  # between requests: Wikipedia asks API users not to burst
PAUSE_AFTER_FAILURES = 3
PAUSE_SECONDS = 15 * 60
MAX_NAME = 120
LINK = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")
TEMPLATE = re.compile(r"\{\{(?:[^{}]|\{\{[^{}]*\}\})*\}\}")
REF = re.compile(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>", re.S)
REPRESENT = re.compile(r"\brepresent(?:s|ed|ing)?\b(.{0,240})", re.S | re.I)


def page_url(title: str) -> str:
    return PAGE + quote(title.replace(" ", "_"), safe="()_,'.-:")


def search_url(words: str) -> str:
    return "https://en.wikipedia.org/w/index.php?" + urlencode({"search": words, "title": "Special:Search", "go": "Go"})


def _clean(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join(value.split())
    return text[:MAX_NAME] if text else None


def lead_link(wikitext: Any) -> str | None:
    """The first wiki link after "represent..." in a page's lead, templates and references removed. None when the
    lead has no such sentence. Exported for the tests."""
    if not isinstance(wikitext, str):
        return None
    body = REF.sub("", TEMPLATE.sub("", wikitext))
    match = REPRESENT.search(body)
    if not match:
        return None
    link = LINK.search(match.group(1))
    if not link:
        return None
    title = link.group(1).strip()
    return title if title and not title.lower().startswith(("file:", "image:", "category:")) else None


class WikiClient:
    def __init__(self, data_dir: Path, transport: httpx.AsyncBaseTransport | None = None, user_agent: str = "KickoffCompanion (personal)", clock=None, lookups: bool = True) -> None:
        self.lookups = lookups  # off in the demo: its made-up teams are not on Wikipedia, so every link is a search
        self.dir = data_dir / "wiki"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "links.json"
        agent = f"{user_agent} https://github.com/Myerslabs/kickoff-companion"  # Wikipedia asks for a way to reach the author
        self._http = httpx.AsyncClient(timeout=TIMEOUT, transport=transport, headers={"User-Agent": agent, "Accept": "application/json"}, follow_redirects=True)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._lock = asyncio.Lock()
        self._last = 0.0
        self._failures = 0
        self._paused_until = 0.0
        self._store: dict[str, Any] = self._load()

    async def aclose(self) -> None:
        await self._http.aclose()

    # --- the stored answers ---------------------------------------------------------------------------

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            log.warning("Stored Wikipedia links %s unreadable, starting over: %s", self.path.name, exc)
            return {}
        return {k: v for k, v in raw.items() if isinstance(k, str) and isinstance(v, dict)} if isinstance(raw, dict) else {}

    def _save(self) -> None:
        try:
            self.path.write_text(json.dumps(self._store, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError as exc:
            log.warning("Could not store Wikipedia links: %s", exc)

    def _fresh(self, key: str) -> dict[str, Any] | None:
        entry = self._store.get(key)
        if not isinstance(entry, dict):
            return None
        try:
            age = (self._clock() - datetime.fromisoformat(str(entry.get("checkedAt")))).total_seconds()
        except ValueError:
            return None
        return entry if age < (FRESH_SECONDS if entry.get("resolved") else RETRY_SECONDS) else None

    # --- the API ----------------------------------------------------------------------------------------

    async def _get(self, **params: Any) -> dict[str, Any] | None:
        """One API call, spaced from the last; None on any failure (counted toward the pause)."""
        if not self.lookups or time.time() < self._paused_until:
            return None
        wait = SPACING_SECONDS - (time.monotonic() - self._last)
        if wait > 0:
            await asyncio.sleep(wait)
        self._last = time.monotonic()
        try:
            response = await self._http.get(API, params={**params, "format": "json", "formatversion": 2})
            if response.status_code != 200:
                raise ValueError(f"HTTP {response.status_code}")
            body = response.json()
            if not isinstance(body, dict):
                raise ValueError("not an object")
        except (httpx.HTTPError, ValueError) as exc:
            self._failures += 1
            log.warning("Wikipedia lookup failed (%s), %d in a row", exc, self._failures)
            if self._failures >= PAUSE_AFTER_FAILURES:
                self._paused_until = time.time() + PAUSE_SECONDS
                self._failures = 0
            return None
        self._failures = 0
        return body

    async def _title(self, title: str) -> str | None:
        """The page a title lands on after redirects, or None when there is no such page."""
        body = await self._get(action="query", titles=title, redirects=1)
        pages = ((body or {}).get("query") or {}).get("pages")
        page = pages[0] if isinstance(pages, list) and pages and isinstance(pages[0], dict) else None
        if page is None or page.get("missing") or page.get("invalid"):
            return None
        return _clean(page.get("title"))

    async def _search(self, words: str, ends_with: str | None = None) -> str | None:
        body = await self._get(action="query", list="search", srsearch=words, srlimit=5)
        hits = ((body or {}).get("query") or {}).get("search")
        for hit in hits if isinstance(hits, list) else []:
            title = _clean(hit.get("title")) if isinstance(hit, dict) else None
            if title and (ends_with is None or title.endswith(ends_with)) and not re.match(r"^\d{4} ", title):
                return title
        return None

    async def _lead(self, title: str) -> str | None:
        body = await self._get(action="parse", page=title, prop="wikitext", section=0, redirects=1)
        return lead_link(((body or {}).get("parse") or {}).get("wikitext"))

    # --- what the headers ask for -------------------------------------------------------------------------

    async def team(self, school: Any, mascot: Any) -> dict[str, Any]:
        name = _clean(school)
        if not name:
            return {"football": None, "school": None, "resolved": False}
        nick = _clean(mascot)
        key = f"team:{name}"
        async with self._lock:
            cached = self._fresh(key)
            if cached:
                return {k: cached.get(k) for k in ("football", "school", "resolved")}
            football = await self._title(f"{name} {nick} football") if nick else None
            if football is None:
                football = await self._search(f"{name} {nick or ''} football".replace("  ", " "), ends_with=" football")
            school_title = await self._lead(football) if football else None
            if school_title is None and nick:
                program = await self._title(f"{name} {nick}")
                school_title = await self._lead(program) if program else None
            resolved = football is not None and school_title is not None
            if not self.lookups:
                return {"football": search_url(f"{name} football"), "school": search_url(f"{name} university"), "resolved": False}
            entry = {
                "football": page_url(football) if football else search_url(f"{name} football"),
                "school": page_url(school_title) if school_title else search_url(f"{name} university"),
                "resolved": resolved,
                "checkedAt": self._clock().isoformat(),
            }
            if not resolved:
                log.info("Wikipedia: %s only partly found (football %s, school %s); search links stand in", name, football, school_title)
            self._store[key] = entry
            self._save()
            return {k: entry[k] for k in ("football", "school", "resolved")}

    async def coach(self, name: Any, school: Any = None) -> dict[str, Any]:
        """A coach's own Wikipedia page: the search "{name} {school} football coach", first result whose title names the person
        (every word of the name appears in it); else a Wikipedia search for the name, so a tap never dead-ends."""
        person = _clean(name)
        if not person:
            return {"page": None, "resolved": False}
        place = _clean(school) or ""
        key = f"coach:{person}|{place}"
        async with self._lock:
            cached = self._fresh(key)
            if cached:
                return {k: cached.get(k) for k in ("page", "resolved")}
            if not self.lookups:
                return {"page": search_url(f"{person} football coach"), "resolved": False}
            body = await self._get(action="query", list="search", srsearch=f"{person} {place} football coach".strip(), srlimit=5)
            hits = ((body or {}).get("query") or {}).get("search")
            tokens = [w for w in (re.sub(r"[^a-z]", "", part.lower()) for part in person.split()) if len(w) > 1 and w not in ("jr", "sr", "ii", "iii", "iv")]
            title = None
            for hit in hits if isinstance(hits, list) else []:
                candidate = _clean(hit.get("title")) if isinstance(hit, dict) else None
                squashed = re.sub(r"[^a-z ]", "", candidate.lower()) if candidate else ""
                if candidate and tokens and all(w in squashed for w in tokens) and not re.match(r"^\d{4} ", candidate):  # the whole name, so "Mudd Stadium" is not "Pat Mudd"
                    title = candidate
                    break
            entry = {"page": page_url(title) if title else search_url(f"{person} football coach"), "resolved": title is not None, "checkedAt": self._clock().isoformat()}
            self._store[key] = entry
            self._save()
            return {k: entry[k] for k in ("page", "resolved")}

    async def venue(self, name: Any) -> dict[str, Any]:
        venue = _clean(name)
        if not venue:
            return {"stadium": None, "resolved": False}
        key = f"venue:{venue}"
        async with self._lock:
            cached = self._fresh(key)
            if cached:
                return {k: cached.get(k) for k in ("stadium", "resolved")}
            title = await self._title(venue)
            if not self.lookups:
                return {"stadium": search_url(venue), "resolved": False}
            entry = {"stadium": page_url(title) if title else search_url(venue), "resolved": title is not None, "checkedAt": self._clock().isoformat()}
            self._store[key] = entry
            self._save()
            return {k: entry[k] for k in ("stadium", "resolved")}
