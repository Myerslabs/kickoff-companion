"""Another team's paper (batch 3, owner 2026-11-16: "She wants to be able to switch teams at will, like to the gators
opponent so she can see what they are talking about"; "Headlines + reader").

A device switched to another FBS team opens this instead of our paper: that team's Google News search and the national
feeds read for its school and mascot (the same feeds as ours, filtered for it), the last week's stories ranked by the
paper's own rule (`paper_layout.layout`, no Claude editor), laid out on our paper's pages. A story with a direct link opens
in the reader, read once when it is opened (`ArticleCopier.read_once`). Nothing is kept: no feed copy on disk, no
archive, no edition, no layout, no copied story; the answers live in memory for ten minutes.

    TheirPaper.paper(school)   the answer for /api/newspaper?team=<school>, or None for a school not in FBS
                               (TeamsUnavailable when CFBD's FBS list cannot be read, so the page says so, not "no team")
    TheirPaper.read(sid)       one of its stories for the reader, or (None, why)
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from typing import Any

from app.feeds import FeedResult, FeedSpec, merge_headlines, parse_feed, team_feeds, team_matcher
from app.services.articles import Article, ArticleCopier, copyable, story_id
from app.services.identity import identity_from_teams
from app.services.logos import logo_fields
from app.services.paper import topic_of
from app.services.paper_layout import layout

log = logging.getLogger("kickoff.paper.theirs")

KEEP_SECONDS = 10 * 60  # one team's answer, and one feed's raw answer, reused this long
TEAMS_KEPT = 12  # the teams remembered at once (a device switching around)
STORIES_KEPT = 60  # stories read for the reader, remembered at once
INDEX_KEPT = 1500  # story ids served, so the reader can find the row behind one
DAYS = 7  # "this week's" stories: the last seven days
HEADLINES = 60
BODIES_KEPT = 16  # raw feed answers kept at once: the four national feeds and a dozen teams' searches (up to 3 MB each)


class TeamsUnavailable(Exception):
    """CFBD's FBS list (/teams/fbs) could not be read or came back empty, so no school can be checked (review 2026-11-19:
    a 503, not "No FBS team named X")."""


class TheirPaper:
    def __init__(self, program: Any, feeds: Any, copier: ArticleCopier, *, clock=None) -> None:
        self.program = program
        self.feeds = feeds
        self.copier = copier
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._papers: OrderedDict[str, tuple[float, dict[str, Any]]] = OrderedDict()
        self._bodies: OrderedDict[str, tuple[float, bytes | None, str | None]] = OrderedDict()
        self._index: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._stories: OrderedDict[str, tuple[float, Article]] = OrderedDict()
        # one per FBS school asked for, made only once the name is found in the FBS list (review 2026-11-19: a lock per
        # string typed would grow forever), so never more than the FBS schools
        self._locks: dict[str, asyncio.Lock] = {}

    async def _team(self, school: str) -> dict[str, Any] | None:
        """The school's own record from the season's FBS list (its mascot names it in the feeds), found whatever its case
        and answered in CFBD's spelling; None for a school not in it. TeamsUnavailable when the list cannot be read."""
        parts = await self.program._core()
        part = parts.get("teams") if isinstance(parts, dict) else None
        records = list(part.records) if part is not None and part.ok else []
        if not records:
            why = (part.error if part is not None else None) or "no answer"
            log.warning("Another team's paper: CFBD's FBS list is unavailable (%s)", why)
            raise TeamsUnavailable(why)
        wanted = school.casefold()
        for team in records:
            name = getattr(team, "school", None)
            if isinstance(name, str) and name.casefold() == wanted:
                who = identity_from_teams(records, name)  # the schools whose names hold this one's (Texas State is not Texas), as ours
                return {"school": name, "mascot": team.mascot or None, "abbreviation": team.abbreviation or None, "conference": team.conference or None, "rivals": list(who.rivals), **logo_fields(team.id, team.logos)}
        return None

    async def _body(self, spec: FeedSpec) -> tuple[bytes | None, str | None]:
        """One feed's raw answer, shared by every team asked for within KEEP_SECONDS (the national feeds are the same
        answer for all of them)."""
        now = time.monotonic()
        kept = self._bodies.get(spec.url)
        if kept is not None and now - kept[0] < KEEP_SECONDS:
            return kept[1], kept[2]
        body, error = await self.feeds.fetch_body(spec.url)
        now = time.monotonic()
        self._bodies[spec.url] = (now, body, error)
        self._bodies.move_to_end(spec.url)
        # review 2026-11-19: never more than BODIES_KEPT, and none past its time (a body can be 3 MB)
        for url in [u for u, (at, _, _) in self._bodies.items() if now - at >= KEEP_SECONDS]:
            del self._bodies[url]
        while len(self._bodies) > BODIES_KEPT:
            self._bodies.popitem(last=False)
        return body, error

    async def _read(self, spec: FeedSpec, matcher: Any) -> FeedResult:
        body, error = await self._body(spec)
        if body is None:
            return FeedResult(spec, [], None, False, error or "no answer")
        # the review (owner 2026-11-19): every story must name the team, the search's too (a Florida story in Texas's
        # paper came through the team's own search feed, which our paper trusts as it is). parse_feed filters only the
        # national feeds (spec.team_only), so the filter runs here for every feed; our own paper's parse is unchanged.
        parsed = parse_feed(body, spec, matcher)
        named = [h for h in parsed.headlines if matcher.matches(h.title)]
        return FeedResult(spec, named, self._clock(), False, None, parsed.skipped, parsed.betting)

    async def paper(self, school: str) -> dict[str, Any] | None:
        name = school.strip() if isinstance(school, str) else ""
        if not name:
            return None
        kept = self._papers.get(name.casefold())
        if kept is not None and time.monotonic() - kept[0] < KEEP_SECONDS:
            self._papers.move_to_end(name.casefold())
            return kept[1]
        team = await self._team(name)  # raises TeamsUnavailable when the FBS list cannot be read
        if team is None:
            return None
        key = team["school"].casefold()
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            kept = self._papers.get(key)
            if kept is not None and time.monotonic() - kept[0] < KEEP_SECONDS:
                return kept[1]
            answer = await self._build(team)
            self._papers[key] = (time.monotonic(), answer)
            self._papers.move_to_end(key)
            while len(self._papers) > TEAMS_KEPT:
                self._papers.popitem(last=False)
            return answer

    async def _build(self, team: dict[str, Any]) -> dict[str, Any]:
        school, mascot = team["school"], team.get("mascot")
        specs = team_feeds(school, mascot)
        matcher = their_matcher(team)
        results = list(await asyncio.gather(*(self._read(spec, matcher) for spec in specs)))
        now = self._clock()
        cutoff = (now - timedelta(days=DAYS)).isoformat()
        rows: list[dict[str, Any]] = []
        for h in merge_headlines(results, limit=HEADLINES):
            published = h.get("publishedAt") if isinstance(h.get("publishedAt"), str) else None
            if published is not None and published < cutoff:
                continue
            sid = story_id(h.get("url"), h.get("title"))
            known = self.copier.store.get(sid)
            copied = known is not None and known.outcome == "copied" and bool(known.paragraphs)
            row = {
                "id": sid,
                "title": h.get("title"),
                "url": h.get("url"),
                "source": h.get("source") or "",
                "feed": h.get("feed") or "",
                "publishedAt": published,
                "topic": topic_of(h.get("title")),
                "copied": copied,
                "readable": copied or copyable(h.get("url")),  # opens in the reader, read once when it is opened
                "opening": known.paragraphs[:3] if copied and known else [],
                "words": known.words if copied and known else 0,
            }
            rows.append(row)
            self._index[sid] = row
            self._index.move_to_end(sid)
        while len(self._index) > INDEX_KEPT:
            self._index.popitem(last=False)
        built = layout(rows)
        for story in _stories_in(built):
            row = self._index.get(story.get("id"))
            if row is not None:
                story["readable"] = row["readable"]
        if not rows:
            log.info("Another team's paper (%s): no stories in the last %d days", school, DAYS)
        return {
            "season": getattr(self.program, "year", None),
            "today": now.astimezone(self.program.settings.tzinfo).date().isoformat(),
            "team": {k: v for k, v in team.items() if k != "rivals"},
            "theirs": True,
            "edition": {"key": None, "current": True, "label": "The last seven days", "week": None, "season": getattr(self.program, "year", None), "headlines": rows, "matchups": [], "layout": built, "kept": False},
            "feeds": {r.feed.id: {"name": r.feed.name, **r.status(now)} for r in results},
        }

    async def headlines(self, school: str, limit: int = 10) -> list[dict[str, Any]] | None:
        """The team's newest stories for a program's headlines band (/api/newspaper/headlines?team=), from its paper as
        built (no feed read of their own); None for a school not in FBS."""
        answer = await self.paper(school)
        if answer is None:
            return None
        rows = (answer.get("edition") or {}).get("headlines") or []
        return [r for r in rows if isinstance(r, dict)][: max(0, int(limit))]

    def served(self, sid: str) -> bool:
        """Whether this story id was served in one of these papers (still remembered), so the reader can tell a story it
        never served ("not_found") from one it served but could not read ("headline_only")."""
        return sid in self._index or sid in self._stories

    async def read(self, sid: str) -> tuple[Article | None, str]:
        """One of the served stories for the reader, read once and remembered in memory a while; never kept on disk."""
        kept = self._stories.get(sid)
        if kept is not None and time.monotonic() - kept[0] < KEEP_SECONDS * 6:
            return kept[1], ""
        row = self._index.get(sid)
        if row is None:
            return None, "That story is not on this server."
        article, why = await self.copier.read_once(row)
        if article is not None:
            self._stories[sid] = (time.monotonic(), article)
            while len(self._stories) > STORIES_KEPT:
                self._stories.popitem(last=False)
        return article, why


def their_matcher(team: dict[str, Any]) -> Any:
    """Which headlines name another team: its school's name, never the bare mascot (review 2026-11-19: a shared mascot let
    LSU's and Clemson's "Tigers" stories into Auburn's paper; "Auburn Tigers" still holds "Auburn"). The schools whose
    names hold this one's stay out, as in ours (Texas State is not Texas)."""
    return team_matcher(team["school"], None, team.get("rivals") or ())


def _stories_in(built: dict[str, Any]) -> list[dict[str, Any]]:
    """Every story object the layout placed (the lead, its briefs, the rows, page 2, page 3's columns)."""
    out: list[dict[str, Any]] = []
    front = built.get("front") or {}
    page2 = built.get("page2") or {}
    for story in [front.get("lead"), *(front.get("leadBriefs") or []), page2.get("lead"), *(page2.get("briefs") or [])]:
        if isinstance(story, dict):
            out.append(story)
    for cell in [*(front.get("row") or []), *(page2.get("row") or [])]:
        for key in ("story", "also"):
            if isinstance(cell, dict) and isinstance(cell.get(key), dict):
                out.append(cell[key])
    for page in built.get("more") or []:
        for column in page.get("columns") or []:
            out.extend(item for item in column if isinstance(item, dict) and "id" in item)
    return out
