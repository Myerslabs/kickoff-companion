"""FEAT-14 (owner 2026-10-27): the paper's stories copied whole onto this computer, without Claude and without the network
in these tests. The pages are made up in the shapes of the team site, Yahoo and an ordinary article page; the refusals,
robots.txt, the paywall, the photo checks and the routes are each tried."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from app.feeds import TeamMatcher, team_site_echo
from app.services import articles as A
from app.services.articles import Article, ArticleCopier, ArticleStore, clean, copyable, extract, story_id

NOW = datetime(2026, 10, 27, 15, 0, tzinfo=timezone.utc)
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64

BODY = [
    "Florida and Georgia have met every year since 1926 except one, and this is the hundredth season of the annual game between the two schools.",
    "It is also the first game in three decades played away from Jacksonville, because the stadium there is under renovation and the game moves north to Atlanta.",
    "The Gators come in ranked for the first time in six years after a comeback win on the road, and the Bulldogs come in after a home loss on a last-second field goal.",
    "The coach said Monday that the quarterback job stays open all week, that a decision comes midweek, and that there will be no big announcement for this game or any other.",
]


def article_html(title: str, paragraphs: list[str], image: str | None = "https://img.example.invalid/lead.jpg", extra: str = "") -> str:
    meta = f'<meta property="og:image" content="{image}">' if image else ""
    body = "".join(f"<p>{p}</p>" for p in paragraphs)
    return (
        f"<html><head><title>{title}</title>{meta}<meta name='author' content='Pat Writer'></head><body>"
        f"<nav><a href='/'>Home</a> <a href='/news'>News</a> <a href='/scores'>Scores</a></nav>"
        f"<article><h1>{title}</h1>{body}{extra}</article>"
        f"<footer>Copyright Example Sports. All rights reserved. Privacy policy. Terms of use.</footer></body></html>"
    )


# --- the text --------------------------------------------------------------------------------------------------


def test_the_team_site_caption_becomes_the_cutline_and_its_leftovers_go():
    text = "\n".join(
        [
            "LJ McCray is pumped after a sack at Texas on Oct. 17. (Photo: Hannah White/UAA Communications)",
            "LJ McCray's Comeback Is Picking Up Steam",
            "Tuesday, October 27, 2026 | Football",
            "Share:",
            "By: Ryan Roddy, FloridaGators.com Student Writer",
            *BODY,
            "2026 Single-Game Tickets",
            "Single-game tickets are on sale for the home games against Oklahoma and Vanderbilt this November.",
        ]
    )
    got = clean(text, "LJ McCray's Comeback Is Picking Up Steam")
    assert got.cutline == "LJ McCray is pumped after a sack at Texas on Oct. 17."
    assert got.credit == "Hannah White/UAA Communications"
    assert got.author == "Ryan Roddy, FloridaGators.com Student Writer"
    assert got.paragraphs == BODY  # the ticket notice and everything after it are gone


def test_yahoo_bylines_timestamps_ads_and_photo_credits_go():
    text = "\n".join(
        [
            "USA TODAY Sports projects same bowl game, opponent for Florida after bye",
            "Story by",
            "USA TODAY Sports projects same bowl game, opponent for Florida after bye",
            "Adam Dubbin, Gators Wire",
            "Tue, October 27, 2026 at 4:41 PM UTC·",
            "1 min read",
            "Advertisement",
            BODY[0],
            "Advertisement",
            BODY[1],
            "Nov 1, 2025; Jacksonville, Florida, USA; Florida Gators quarterback DJ Lagway (2) runs a play. Mandatory Credit: Travis Register-Imagn Images",
            "(Travis Register, IMAGN IMAGES via Reuters Connect)",
            "Florida Gators quarterback DJ Lagway (2) runs against Georgia Bulldogs during the second half.",
            BODY[2],
        ]
    )
    got = clean(text, "USA TODAY Sports projects same bowl game, opponent for Florida after bye", author="Adam Dubbin; Gators Wire")
    assert got.paragraphs == [BODY[0], BODY[1], BODY[2]]


def test_a_scoreboard_strip_above_the_story_is_skipped():
    text = "\n".join(["Completed Event: Football at Auburn on September 19, 2026 , Win , 44, to, 39", "Final", "Football", "44", "at Auburn", "39", *BODY])
    assert clean(text, "Broadcast Information: Florida vs. Georgia").paragraphs == BODY


def test_extract_reads_an_article_page_and_its_photo():
    got = extract(article_html("Florida-Georgia moves to Atlanta", BODY * 2), "https://news.example.invalid/story/1", "Florida-Georgia moves to Atlanta")
    assert got.reason is None and got.words >= A.MIN_WORDS
    assert got.image == "https://img.example.invalid/lead.jpg"
    assert any("hundredth season" in p for p in got.paragraphs)
    assert not any("Copyright" in p or "Home" == p for p in got.paragraphs)


def test_extract_says_why_there_is_no_article():
    assert extract("", "https://x.example.invalid/a", "T").reason == "no article text on the page"
    assert extract("<html><body><p>Short teaser.</p></body></html>", "https://x.example.invalid/a", "T").reason == "no article text on the page"
    paywall = article_html("Big story", BODY[:2], extra="<p>Subscribe to continue reading this story and every other one on the site today.</p>")
    assert extract(paywall, "https://x.example.invalid/a", "Big story").reason in ("behind a paywall", "no article text on the page")
    assert extract("<<<not html at all>>>" * 50, "https://x.example.invalid/a", "T").paragraphs == []


def test_the_lead_photos_own_caption_is_the_cutline_and_another_pictures_is_never_borrowed():
    lead = "https://images.example.invalid/resize?url=https%3A%2F%2Fcdn.example.invalid%2Fimages%2FMcCray_LJ__5280.jpg&width=1600"
    page = (
        '<picture><source srcset="https://images.example.invalid/resize?url=https%3A%2F%2Fcdn.example.invalid%2Fimages%2FMcCray_LJ__5280.jpg&amp;height=600">'
        '<img src="https://images.example.invalid/resize?url=https%3A%2F%2Fcdn.example.invalid%2Fimages%2FMcCray_LJ__5280.jpg&amp;height=300" alt="McCray"></picture>'
        '<div class="s-image-caption"><div class="s-image-caption__content"><div data-test-id="s-image-caption__text">LJ McCray is pumped after a sack at Texas. (Photo: Hannah White/UAA Communications)</div></div></div>'
        '<p>Story text.</p><figure><img src="/images/McCray_LJ__5402.jpg"><figcaption>Another moment, another photo. (Photo: Someone Else)</figcaption></figure>'
    )
    assert A.photo_caption(page, lead) == ("LJ McCray is pumped after a sack at Texas.", "Hannah White/UAA Communications")
    only_other = '<figure><img src="/images/McCray_LJ__5402.jpg"><figcaption>Another moment. (Photo: Someone Else)</figcaption></figure>'
    assert A.photo_caption(only_other, lead) == (None, None)
    wire = '<figure><img src="https://s.example.invalid/lead-photo.jpg"><figcaption>Nov 1, 2025; Jacksonville, Florida, USA; Florida quarterback runs a play. Mandatory Credit: Travis Register-Imagn Images</figcaption></figure>'
    assert A.photo_caption(wire, "https://s.example.invalid/lead-photo.jpg") == ("Nov 1, 2025; Jacksonville, Florida, USA; Florida quarterback runs a play.", "Travis Register-Imagn Images")
    assert A.photo_caption("<p>no pictures</p>", lead) == (None, None) and A.photo_caption(page, None) == (None, None)


def test_syndication_footers_end_the_story_and_a_short_brief_still_counts():
    text = "\n".join([*BODY[:2], "Follow us @GatorsWire on X, formerly known as Twitter.", "More text that is not the story."])
    assert clean(text, "T").paragraphs == BODY[:2]
    text = "\n".join([*BODY[:2], "This article originally appeared on Gators Wire: The headline", "More."])
    assert clean(text, "T").paragraphs == BODY[:2]
    brief = article_html("Florida-Oklahoma kicks off at 7:45", [BODY[0], "The game will be televised on SEC Network, the conference announced on Monday afternoon, and it is the Saluting Those Who Serve game."])
    assert extract(brief, "https://team.example.invalid/x", "Florida-Oklahoma kicks off at 7:45").paragraphs  # about 45 words: a real brief


def test_a_story_keeps_one_id_and_only_direct_links_are_copied():
    assert story_id("https://www.example.invalid/a/b/?utm_source=x") == story_id("http://WWW.example.invalid/a/b#top")
    assert story_id(None, "Gators win") == story_id("", "Gators  WIN!")
    assert story_id("https://news.google.com/rss/articles/abc") != story_id("https://news.google.com/rss/articles/xyz")
    assert copyable("https://floridagators.com/news/2026/10/26/x") and copyable("https://sports.yahoo.com/a.html")
    assert not copyable("https://news.google.com/rss/articles/abc") and not copyable("https://theathletic.com/1/")
    assert not copyable("javascript:alert(1)") and not copyable(None)


def test_the_team_sites_own_items_in_google_news_are_echoes():
    matcher = TeamMatcher(["Florida", "Gators"])
    assert team_site_echo({"feed": "google", "source": "Florida Gators", "title": "No. 10 Gators close fall"}, matcher)
    assert not team_site_echo({"feed": "team", "source": "Florida Gators", "title": "x"}, matcher)
    assert not team_site_echo({"feed": "google", "source": "On3", "title": "x"}, matcher)
    assert not team_site_echo({"feed": "google", "source": "Florida Gators"}, None)


# --- the copier ------------------------------------------------------------------------------------------------


class Sites:
    """Made-up publishers keyed by URL; anything unlisted is a 404."""

    def __init__(self) -> None:
        self.pages: dict[str, httpx.Response | Exception] = {}
        self.calls: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.calls.append(url)
        answer = self.pages.get(url)
        if isinstance(answer, Exception):
            raise answer
        return answer if answer is not None else httpx.Response(404)


def copier(tmp_path: Path, sites: Sites, now: list[datetime] | None = None) -> ArticleCopier:
    clock = now or [NOW]

    async def no_wait(_seconds: float) -> None:
        return None

    return ArticleCopier(ArticleStore(tmp_path / "data", 2026), transport=httpx.MockTransport(sites.handler), clock=lambda: clock[0], sleep=no_wait)


def row(url: str, title: str = "Florida-Georgia moves to Atlanta", hours_ago: int = 3) -> dict:
    return {"title": title, "url": url, "source": "Florida Athletics", "feed": "team", "publishedAt": (NOW - timedelta(hours=hours_ago)).isoformat().replace("+00:00", "Z")}


def test_a_story_is_copied_with_its_photo_and_the_paper_gets_its_opening(tmp_path: Path):
    sites = Sites()
    url = "https://team.example.invalid/news/2026/10/26/florida-georgia"
    sites.pages[url] = httpx.Response(200, text=article_html("Florida-Georgia moves to Atlanta", BODY * 3), headers={"content-type": "text/html"})
    sites.pages["https://img.example.invalid/lead.jpg"] = httpx.Response(200, content=PNG, headers={"content-type": "image/png"})
    c = copier(tmp_path, sites)
    assert asyncio.run(c.run([row(url)])) == 1
    article = c.store.get(story_id(url))
    assert article.outcome == "copied" and article.words >= A.MIN_WORDS and article.copiedAt
    assert article.photo == f"{article.id}.png" and c.store.photo_path(article.photo).read_bytes() == PNG
    shown = c.store.annotate([row(url), {"title": "Headline only", "url": "https://news.google.com/rss/articles/x"}])
    assert shown[0]["copied"] is True and shown[0]["photo"] == f"/media/paper/{article.photo}" and shown[0]["opening"]
    assert sum(len(p) for p in shown[0]["opening"][:-1]) < A.TEXT_CHARS
    assert shown[1]["copied"] is False and shown[1]["photo"] is None and shown[1]["opening"] == []
    asyncio.run(c.aclose())


def test_robots_no_and_a_refusal_keep_the_headline_and_the_refusing_site_is_not_asked_again(tmp_path: Path):
    sites = Sites()
    sites.pages["https://shy.example.invalid/robots.txt"] = httpx.Response(200, text="User-agent: GatorsGameDay\nDisallow: /\n")
    sites.pages["https://wall.example.invalid/a"] = httpx.Response(402, text="Payment required")
    c = copier(tmp_path, sites)
    shy = asyncio.run(c.copy_one(row("https://shy.example.invalid/story")))
    assert shy.outcome == "headline" and "robots" in shy.reason
    assert "https://shy.example.invalid/story" not in sites.calls
    walled = asyncio.run(c.copy_one(row("https://wall.example.invalid/a", "First")))
    assert walled.outcome == "headline" and "402" in walled.reason
    before = len(sites.calls)
    second = asyncio.run(c.copy_one(row("https://wall.example.invalid/b", "Second")))
    assert second.outcome == "headline" and "refused" in second.reason and len(sites.calls) == before
    assert "wall.example.invalid" in c.status()["refusing"]
    asyncio.run(c.aclose())


def test_a_bot_wall_answer_counts_as_a_refusal(tmp_path: Path):
    sites = Sites()
    sites.pages["https://espn.example.invalid/story/1"] = httpx.Response(202, text="")
    c = copier(tmp_path, sites)
    assert asyncio.run(c.copy_one(row("https://espn.example.invalid/story/1"))).outcome == "headline"
    asyncio.run(c.aclose())


def test_a_failing_page_is_tried_once_more_after_its_wait_then_stays_headline_only(tmp_path: Path):
    sites = Sites()
    url = "https://slow.example.invalid/a"
    sites.pages[url] = httpx.Response(503)
    clock = [NOW]
    c = copier(tmp_path, sites, clock)
    first = asyncio.run(c.copy_one(row(url)))
    assert first.outcome == "pending" and first.attempts == 1 and first.nextTry
    assert c.wanted([row(url)]) == []  # waiting for its hour
    clock[0] = NOW + A.RETRY_AFTER + timedelta(minutes=1)
    assert c.wanted([row(url)])
    second = asyncio.run(c.copy_one(row(url)))
    assert second.outcome == "headline" and "2 tries" in second.reason
    asyncio.run(c.aclose())


def test_a_timeout_waits_for_a_retry_and_a_site_that_keeps_failing_is_paused(tmp_path: Path):
    sites = Sites()
    for n in range(3):
        sites.pages[f"https://down.example.invalid/{n}"] = httpx.ConnectTimeout("too slow")
    c = copier(tmp_path, sites)
    for n in range(3):
        assert asyncio.run(c.copy_one(row(f"https://down.example.invalid/{n}", f"Story {n}"))).outcome == "pending"
    assert "down.example.invalid" in c.status()["paused"]
    asyncio.run(c.aclose())


def test_a_photo_that_is_not_a_picture_is_left_out_but_the_story_is_copied(tmp_path: Path):
    sites = Sites()
    url = "https://team.example.invalid/news/x"
    sites.pages[url] = httpx.Response(200, text=article_html("Florida-Georgia moves to Atlanta", BODY * 3), headers={"content-type": "text/html"})
    sites.pages["https://img.example.invalid/lead.jpg"] = httpx.Response(200, text="<html>not a picture</html>", headers={"content-type": "text/html"})
    c = copier(tmp_path, sites)
    article = asyncio.run(c.copy_one(row(url)))
    assert article.outcome == "copied" and article.photo is None
    asyncio.run(c.aclose())


def test_only_recent_direct_stories_are_wanted_and_offer_runs_in_the_background(tmp_path: Path):
    sites = Sites()
    c = copier(tmp_path, sites)
    rows = [row("https://a.example.invalid/1"), row("https://news.google.com/rss/articles/x", "Google"), row("https://b.example.invalid/old", "Old", hours_ago=24 * 12), {"title": None}, "junk"]
    assert [r["url"] for r in c.wanted(rows)] == ["https://a.example.invalid/1"]

    async def scenario() -> None:
        c.offer(rows)
        assert c.status()["running"] is True
        await c._task

    asyncio.run(scenario())
    assert c.store.get(story_id("https://a.example.invalid/1")).outcome == "headline"  # a 404 page: the story is gone
    asyncio.run(c.aclose())


def test_a_damaged_story_file_is_skipped_and_counted(tmp_path: Path):
    store = ArticleStore(tmp_path / "data", 2026)
    store.dir.mkdir(parents=True)
    (store.dir / "0123456789abcdef.json").write_text("{not json", encoding="utf-8")
    (store.dir / "fedcba9876543210.json").write_text('{"id": "fedcba9876543210", "outcome": "copied", "paragraphs": ["x"], "words": "many"}', encoding="utf-8")
    assert store.all() == [] and store.skipped == 2


# --- the routes ------------------------------------------------------------------------------------------------


def test_the_reader_route_serves_a_copied_story_and_says_why_others_have_none(app, client: TestClient):
    store: ArticleStore = app.state.articles.store
    sid = story_id("https://team.example.invalid/news/x")
    store.put(Article(id=sid, url="https://www.team.example.invalid/news/x", title="Florida-Georgia moves to Atlanta", source="Florida Athletics", outcome="copied", paragraphs=BODY, words=460, author="Pat Writer", photo=f"{sid}.png", cutline="The Gators at practice.", credit="Hannah White", copiedAt="2026-10-26T21:40:00Z"))
    store.photos.mkdir(parents=True, exist_ok=True)
    (store.photos / f"{sid}.png").write_bytes(PNG)
    data = client.get(f"/api/paper/story/{sid}").json()["data"]
    assert data["paragraphs"] == BODY and data["readMinutes"] == 2 and data["host"] == "team.example.invalid"
    assert data["photo"] == f"/media/paper/{sid}.png"
    photo = client.get(f"/media/paper/{sid}.png")
    assert photo.status_code == 200 and photo.content == PNG and photo.headers["content-type"] == "image/png"
    other = story_id("https://wall.example.invalid/a")
    store.put(Article(id=other, title="Behind a wall", outcome="headline", reason="the site refuses automated readers (HTTP 402)"))
    refused = client.get(f"/api/paper/story/{other}")
    assert refused.status_code == 404 and "402" in refused.text
    assert client.get("/api/paper/story/not-an-id").status_code == 404
    assert client.get("/media/paper/../../settings.json").status_code == 404
    assert client.get("/media/paper/0123456789abcdef.exe").status_code == 404
    status = client.get("/api/paper/status").json()["data"]
    assert status["copied"] == 1 and status["headline"] == 1
