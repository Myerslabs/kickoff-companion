"""Another team's paper (batch 3, owner 2026-11-16: "Headlines + reader"). A device switched to another team reads that
team's stories from its Google News search and the national feeds filtered for it; a school whose name holds it is not it
(Texas State is not Texas); a story opens in the reader, read once and never kept; nothing is written to disk."""

from __future__ import annotations

import asyncio
from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

import app.services.their_paper as their_paper_module
from app.feeds import FeedSpec, parse_feed, team_matcher
from app.services.parts import Part
from app.services.their_paper import BODIES_KEPT, KEEP_SECONDS, TeamsUnavailable, TheirPaper, their_matcher
from tests.test_any_team import OTHER, lclient  # noqa: F401 - the league client fixture

IN_THE_NEWS = "Auburn"  # the league's national feeds carry an Auburn final on its week 4 Saturday


def files(root: Path) -> dict[str, int]:
    return {str(p.relative_to(root)): p.stat().st_mtime_ns for p in root.rglob("*") if p.is_file()}


def test_their_paper_is_that_teams_stories_on_our_pages(lclient: TestClient):  # noqa: F811
    answer = lclient.get(f"/api/newspaper?team={quote(IN_THE_NEWS)}")
    assert answer.status_code == 200, answer.text[:300]
    data = answer.json()["data"]
    assert data["theirs"] is True and data["team"]["school"] == IN_THE_NEWS and "rivals" not in data["team"]
    edition = data["edition"]
    assert edition["kept"] is False and edition["matchups"] == []
    titles = [h["title"] for h in edition["headlines"]]
    assert any("Auburn" in t for t in titles), titles
    layout = edition["layout"]
    assert layout["by"] == "the app" and layout["count"] >= 1, "the paper's own rule, never the Claude editor"
    assert all(isinstance(h.get("readable"), bool) for h in edition["headlines"])


def test_a_school_whose_name_holds_theirs_is_not_them(lclient: TestClient):  # noqa: F811
    team = lclient.portal.call(lclient.app.state.their_paper._team, OTHER)
    assert team is not None and "Texas State" in team["rivals"]
    matcher = team_matcher(OTHER, team["mascot"], team["rivals"])
    assert matcher.matches("Texas holds off Oklahoma in the Red River game")
    assert not matcher.matches("Texas State rolls past Troy 31-10")


def test_our_paper_is_unchanged_and_a_school_not_in_fbs_is_refused(lclient: TestClient):  # noqa: F811
    ours = lclient.get("/api/newspaper").json()["data"]
    assert ours.get("theirs") is not True
    named = lclient.get("/api/newspaper?team=Florida").json()["data"]
    assert named.get("theirs") is not True
    refused = lclient.get("/api/newspaper?team=No%20Such%20School")
    assert refused.status_code == 404


def test_their_paper_and_its_stories_keep_nothing(lclient: TestClient, settings):  # noqa: F811
    lclient.get("/api/newspaper")  # our paper first: its own feed copies and archive are ours to keep
    root = Path(settings.data_dir)
    before = files(root)
    data = lclient.get(f"/api/newspaper?team={quote(IN_THE_NEWS)}").json()["data"]
    readable = [h for h in data["edition"]["headlines"] if h["readable"]]
    opened = [lclient.get(f"/api/paper/story/{h['id']}") for h in readable[:3]]
    after = files(root)
    changed = sorted(k for k in after if before.get(k) != after[k])
    assert not [c for c in changed if "feeds" in c or "paper" in c or "articles" in c], changed
    for answer in opened:
        assert answer.status_code in (200, 404), answer.text[:200]
        if answer.status_code == 200:
            story = answer.json()["data"]
            assert story["paragraphs"] and story["photo"] is None
            assert story["kept"] in (True, False)


def test_a_story_never_served_is_not_read(lclient: TestClient):  # noqa: F811
    missing = lclient.get("/api/paper/story/0123456789abcdef")
    assert missing.status_code == 404


def test_every_story_names_the_team_and_the_program_band_reads_them(lclient: TestClient):  # noqa: F811
    """The review (owner 2026-11-19): a Florida story stood in Texas's paper (its own search feed was trusted as it was), and
    a switched Program's headlines band read ours under "Gators headlines"."""
    team = lclient.get(f"/api/newspaper?team={quote(IN_THE_NEWS)}").json()["data"]["team"]
    matcher = team_matcher(IN_THE_NEWS, team.get("mascot"), ())
    rows = lclient.get(f"/api/newspaper?team={quote(IN_THE_NEWS)}").json()["data"]["edition"]["headlines"]
    assert rows and all(matcher.matches(h["title"]) or matcher.matches(h.get("summary") or "") for h in rows), [h["title"] for h in rows]
    band = lclient.get(f"/api/newspaper/headlines?limit=3&team={quote(IN_THE_NEWS)}")
    assert band.status_code == 200, band.text[:300]
    news = band.json()["data"]["news"]
    assert 0 < len(news) <= 3 and [h["title"] for h in news] == [h["title"] for h in rows][: len(news)]
    assert lclient.get("/api/newspaper/headlines?team=No%20Such%20School").status_code == 404
    ours = lclient.get("/api/newspaper/headlines?limit=3").json()["data"]
    assert "team" not in ours, "no team: our own feeds, as before"


# --- the review of 2026-11-19 ---------------------------------------------------------------------------------------------

SEARCH = b"""<?xml version="1.0"?><rss><channel><title>Google News</title>
<item><title>Auburn Tigers hold off Ole Miss late - AL.com</title><link>https://www.al.com/a</link></item>
<item><title>Tigers roll behind a big night from the backfield - LSU Wire</title><link>https://lsuwire.com/b</link></item>
<item><title>Florida's quarterback questions linger - Gator Country</title><link>https://gatorcountry.com/c</link></item>
</channel></rss>"""

AUBURN = {"school": "Auburn", "mascot": "Tigers", "rivals": []}


class _Feeds:
    def __init__(self, body: bytes = SEARCH) -> None:
        self.body = body
        self.asked: list[str] = []

    async def fetch_body(self, url: str):
        self.asked.append(url)
        return self.body, None


class _Program:
    def __init__(self, part: Part) -> None:
        self.part = part

    async def _core(self):
        return {"teams": self.part}


def test_the_search_feed_is_filtered_too_and_ours_is_not():
    """Item 1: parse_feed filters only the national feeds, so their paper filters every feed itself; ours is unchanged."""
    google = FeedSpec("google", "Google News", "https://news.google.com/rss/search?q=auburn")
    theirs = TheirPaper(None, _Feeds(), None)
    result = asyncio.run(theirs._read(google, their_matcher(AUBURN)))
    assert [h.title for h in result.headlines] == ["Auburn Tigers hold off Ole Miss late"], [h.title for h in result.headlines]
    ours = parse_feed(SEARCH, google, team_matcher("Florida", "Gators"))
    assert len(ours.headlines) == 3, "our own search feed is trusted as it is"


def test_a_shared_mascot_does_not_let_another_school_in(lclient: TestClient):  # noqa: F811
    """Item 2: Auburn's paper names Auburn, not "Tigers" (LSU, Clemson, Missouri); a school whose name holds it stays out."""
    team = lclient.portal.call(lclient.app.state.their_paper._team, IN_THE_NEWS)
    assert team is not None and team["mascot"] == "Tigers"
    matcher = their_matcher(team)
    assert matcher.matches("Auburn Tigers hold off Ole Miss late")
    assert not matcher.matches("Tigers roll past Florida behind a big night from the backfield")
    assert not matcher.matches("LSU Tigers climb to No. 7")
    texas = lclient.portal.call(lclient.app.state.their_paper._team, OTHER)
    assert not their_matcher(texas).matches("Texas State rolls past Troy 31-10")
    assert their_matcher(texas).matches("Texas holds off Oklahoma in the Red River game")
    rows = lclient.get(f"/api/newspaper?team={quote(IN_THE_NEWS)}").json()["data"]["edition"]["headlines"]
    assert all(matcher.matches(h["title"]) for h in rows), [h["title"] for h in rows]


def test_the_feed_bodies_and_the_locks_stay_bounded(lclient: TestClient, monkeypatch):  # noqa: F811
    """Items 3 and 4: a lock only for a school found in FBS; feed bodies expire and never pass BODIES_KEPT."""
    theirs = lclient.app.state.their_paper
    for i in range(20):
        assert lclient.get(f"/api/newspaper?team=Nowhere%20{i}").status_code == 404
    assert not [k for k in theirs._locks if k.startswith("nowhere")], list(theirs._locks)

    paper = TheirPaper(None, _Feeds(), None)
    clock = [1000.0]
    monkeypatch.setattr(their_paper_module.time, "monotonic", lambda: clock[0])
    for i in range(BODIES_KEPT * 3):
        asyncio.run(paper._body(FeedSpec(f"f{i}", "F", f"https://example.com/{i}")))
    assert len(paper._bodies) == BODIES_KEPT
    clock[0] += KEEP_SECONDS + 1
    asyncio.run(paper._body(FeedSpec("late", "F", "https://example.com/late")))
    assert list(paper._bodies) == ["https://example.com/late"], "the expired bodies went"


def test_no_fbs_list_is_a_503_and_an_unknown_school_a_404(lclient: TestClient, monkeypatch):  # noqa: F811
    """Item 5: CFBD's /teams/fbs failed or empty is CFBD's trouble (503), not "No FBS team named X"."""
    failed = TheirPaper(_Program(Part("teams", [], None, "CFBD timed out")), _Feeds(), None)
    with pytest.raises(TeamsUnavailable):
        asyncio.run(failed._team("Auburn"))
    monkeypatch.setattr(lclient.app.state.their_paper, "program", failed.program)
    for path in ("/api/newspaper?team=Auburn", "/api/newspaper/headlines?team=Auburn"):
        answer = lclient.get(path)
        assert answer.status_code == 503, answer.text[:200]
        assert answer.json()["errors"][0]["code"] == "upstream_unavailable"
    monkeypatch.undo()
    assert lclient.get("/api/newspaper?team=No%20Such%20School").status_code == 404
    assert lclient.get("/api/newspaper/headlines?team=No%20Such%20School").status_code == 404


def test_the_team_is_found_whatever_its_case(lclient: TestClient):  # noqa: F811
    """Item 6: "florida" is ours on both routes; "auburn" is Auburn, in CFBD's spelling."""
    assert lclient.get("/api/newspaper?team=florida").json()["data"].get("theirs") is not True
    assert "team" not in lclient.get("/api/newspaper/headlines?limit=3&team=FLORIDA").json()["data"]
    data = lclient.get("/api/newspaper?team=auburn").json()["data"]
    assert data["theirs"] is True and data["team"]["school"] == "Auburn"
    assert lclient.portal.call(lclient.app.state.their_paper._team, "TEXAS")["school"] == "Texas"


def test_a_story_never_served_is_not_found(lclient: TestClient):  # noqa: F811
    """Item 7: an id no paper served is "not_found", not "headline_only"."""
    missing = lclient.get("/api/paper/story/0123456789abcdef")
    assert missing.status_code == 404 and missing.json()["errors"][0]["code"] == "not_found"
