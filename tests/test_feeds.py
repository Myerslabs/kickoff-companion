"""Headline feeds: the four made-up samples parse, national feeds are filtered to our team,
duplicates merge, malformed documents and items are counted not fatal, a dead feed serves its
last good headlines as stale, and repeated failures pause the feed. The betting filter has its
own tests in test_program_10a.py."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

from app.feeds import FeedResult, FeedSpec, FeedStore, Headline, TeamMatcher, merge_headlines, parse_feed, team_feeds, team_matcher
from tests.conftest import TEAM

FIXTURES = Path(__file__).parent / "fixtures" / "feeds"  # made-up headlines in the shapes the real feeds send
MASCOT = "Mudpuppies"
SPECS = {spec.id: spec for spec in team_feeds(TEAM, MASCOT, "https://news.example.invalid/rss?path=football")}
MATCHER = team_matcher(TEAM, MASCOT)


def sample(feed_id: str) -> bytes:
    return (FIXTURES / f"{feed_id}.xml").read_bytes()


def run(coro):
    return asyncio.run(coro)


@pytest.mark.parametrize("feed_id", ["team", "espn", "athletic", "google"])
def test_sample_feeds_parse(feed_id: str):
    headlines, skipped, _ = parse_feed(sample(feed_id), SPECS[feed_id], MATCHER)
    assert skipped == 0
    if feed_id in ("team", "google"):
        assert len(headlines) >= 10
    for h in headlines:
        assert h.title and (h.url is None or h.url.startswith("http"))
        assert h.published_at is None or h.published_at.endswith("Z")
        assert h.feed == feed_id and h.source


def test_national_feeds_keep_our_headlines_only():
    for feed_id in ("espn", "athletic"):
        headlines = parse_feed(sample(feed_id), SPECS[feed_id], MATCHER).headlines
        assert headlines and all((TEAM in h.title or MASCOT in h.title) for h in headlines)
    body = b"""<rss><channel>
      <item><title>Okra Valley Pods name a starter</title><link>https://x/1</link></item>
      <item><title>Okra Valley State loses again</title><link>https://x/2</link></item>
      <item><title>North Okra Valley and OVS meet</title><link>https://x/3</link></item>
      <item><title>Okra Valley State at Okra Valley this week</title><link>https://x/4</link></item>
      <item><title>Brisket State rolls</title><link>https://x/5</link></item>
    </channel></rss>"""
    matcher = team_matcher("Okra Valley", "Pods", ["Okra Valley State", "OVS", "North Okra Valley"])
    headlines = parse_feed(body, FeedSpec("t", "T", "https://x", team_only=True), matcher).headlines
    assert [h.title for h in headlines] == ["Okra Valley Pods name a starter", "Okra Valley State at Okra Valley this week"]
    assert parse_feed(body, FeedSpec("t", "T", "https://x", team_only=True)).headlines == []  # no team known: nothing passes


def test_team_matcher_edges():
    assert not TeamMatcher([]).matches("anything")
    m = TeamMatcher(["Pods"], [])
    assert m.matches("pods win") and not m.matches("Podsville") and not m.matches(None)


def test_google_titles_drop_the_source_suffix():
    headlines = parse_feed(sample("google"), SPECS["google"], MATCHER).headlines
    assert headlines and not any(h.title.endswith(" - Gravy Gazette") for h in headlines)


def test_malformed_documents_and_items():
    spec = FeedSpec("t", "T", "https://x")
    assert parse_feed(b"not xml at all", spec) == ([], 1, 0)
    assert parse_feed(b"", spec) == ([], 1, 0)
    body = b"""<rss><channel>
      <item><title>Good</title><link>https://x/1</link><pubDate>Tue, 23 Sep 2026 10:00:00 GMT</pubDate></item>
      <item><link>https://x/2</link></item>
      <item><title></title></item>
      <item><title>Bad link</title><link>javascript:alert(1)</link><pubDate>garbage</pubDate></item>
    </channel></rss>"""
    headlines, skipped, betting = parse_feed(body, spec)
    assert [h.title for h in headlines] == ["Good", "Bad link"] and skipped == 2 and betting == 0
    assert headlines[0].published_at == "2026-09-23T10:00:00Z"
    assert headlines[1].url is None and headlines[1].published_at is None


def test_atom_documents_parse_too():
    body = b"""<feed xmlns="http://www.w3.org/2005/Atom">
      <entry><title>Atom headline</title><link href="https://x/a"/><published>2026-09-23T10:00:00-04:00</published></entry>
    </feed>"""
    headlines, skipped, _ = parse_feed(body, FeedSpec("a", "Atom", "https://x"))
    assert skipped == 0 and headlines[0].url == "https://x/a" and headlines[0].published_at == "2026-09-23T14:00:00Z"


def test_merge_removes_duplicates_and_sorts_newest_first():
    a = FeedResult(SPECS["team"], [Headline("Mudpuppies win big!", "https://a/1", "SWT", "team", "2026-09-20T00:00:00Z"), Headline("Older", "https://a/2", "SWT", "team", "2026-09-10T00:00:00Z")])
    b = FeedResult(SPECS["google"], [Headline("Mudpuppies win big", "https://b/1", "Site", "google", "2026-09-21T00:00:00Z"), Headline("Newest", "https://b/2", "Site", "google", "2026-09-22T00:00:00Z")])
    merged = merge_headlines([a, b])
    assert [h["title"] for h in merged] == ["Newest", "Mudpuppies win big!", "Older"]


class FakeSites:
    def __init__(self) -> None:
        self.responses: dict[str, httpx.Response] = {}
        self.calls: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(str(request.url))
        return self.responses.get(str(request.url), httpx.Response(200, content=sample("team"), headers={"content-type": "application/xml"}))


def make_store(tmp_path: Path, sites: FakeSites) -> tuple[FeedStore, dict]:
    clock = {"now": datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)}
    store = FeedStore(tmp_path, feeds=(SPECS["team"], SPECS["google"]), transport=httpx.MockTransport(sites.handler), clock=lambda: clock["now"], matcher=MATCHER)
    return store, clock


def test_store_fetches_once_then_serves_from_memory_and_disk(tmp_path: Path):
    sites = FakeSites()
    store, clock = make_store(tmp_path, sites)

    async def scenario():
        first = await store.get(SPECS["team"])
        again = await store.get(SPECS["team"])
        store._memory.clear()
        from_disk = await store.get(SPECS["team"])
        await store.aclose()
        return first, again, from_disk

    first, again, from_disk = run(scenario())
    assert first.headlines and not first.stale and first.error is None
    assert len(sites.calls) == 1 and again.fetched_at == first.fetched_at
    assert (tmp_path / "feeds" / "team.json").exists()
    assert [h.title for h in from_disk.headlines] == [h.title for h in first.headlines]


def test_dead_feed_serves_stale_then_pauses(tmp_path: Path):
    sites = FakeSites()
    store, clock = make_store(tmp_path, sites)

    async def scenario():
        good = await store.get(SPECS["team"])
        clock["now"] += timedelta(hours=2)
        sites.responses[SPECS["team"].url] = httpx.Response(503)
        stale = await store.get(SPECS["team"])
        calls = len(sites.calls)
        for _ in range(2):
            store._memory.clear()
            await store.get(SPECS["team"])
        paused = await store.get(SPECS["team"])
        await store.aclose()
        return good, stale, calls, paused

    good, stale, calls, paused = run(scenario())
    assert stale.stale and stale.error == "HTTP 503" and [h.title for h in stale.headlines] == [h.title for h in good.headlines]
    assert stale.status(clock["now"])["status"] == "stale"
    assert "paused" in (paused.error or "") and len(sites.calls) == calls + 2


def test_feed_that_never_worked_is_an_error_not_a_crash(tmp_path: Path):
    sites = FakeSites()
    store, clock = make_store(tmp_path, sites)
    sites.responses[SPECS["google"].url] = httpx.Response(200, content=b"<html>blocked</html>", headers={"content-type": "text/html"})

    async def scenario():
        result = await store.get(SPECS["google"])
        await store.aclose()
        return result

    result = run(scenario())
    assert result.headlines == [] and result.fetched_at is None and result.error == "answer was not a feed"
    assert result.status(clock["now"])["status"] == "error"
