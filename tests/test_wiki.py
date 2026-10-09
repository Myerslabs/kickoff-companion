"""Phase 17 #4: Wikipedia links for the big headers. The football page by title (redirects followed) or by search,
the school from the lead sentence of the football page or else the athletics program's page, the stadium by title;
anything not found is a Wikipedia search link; answers are kept on disk; failures pause the lookups; the demo makes
no lookups; and the route. Wikipedia is scripted here: no test reaches the network."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app import wiki
from app.wiki import WikiClient, lead_link, page_url, search_url

PAGES = {
    "Mudtown Mudpuppies football": "The '''Mudtown Mudpuppies football''' team represents the [[University of Mudtown|Mudtown]] in college football.",
    "Riverbend Otters": "The '''Riverbend Otters''' are the athletic teams that represent [[Riverbend State University]].",
    "Riverbend Otters football": "{{Infobox college football team|institution=[[Wrong Place]]}} The '''Riverbend Otters''' play football.",
}
REDIRECTS = {"Old Field Stadium": "New Field Stadium", "Mudtown Mudpuppies football": "Mudtown Mudpuppies football", "Riverbend Otters football": "Riverbend Otters football", "Riverbend Otters": "Riverbend Otters", "New Field Stadium": "New Field Stadium"}


class FakeWikipedia:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []
        self.down = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        q = {k: v[0] for k, v in parse_qs(urlparse(str(request.url)).query).items()}
        self.calls.append(q)
        if self.down:
            return httpx.Response(503)
        if q.get("action") == "query" and q.get("list") == "search":
            hits = [{"title": "2026 Hilltop Goats football team"}, {"title": "Hilltop Goats football"}] if "Hilltop" in q.get("srsearch", "") else []
            if "Pat Mudd" in q.get("srsearch", ""):
                hits = [{"title": "Mudd Stadium"}, {"title": "2026 Mudtown football team"}, {"title": "Pat Mudd (American football coach)"}]
            return httpx.Response(200, json={"query": {"search": hits}})
        if q.get("action") == "query":
            title = q.get("titles", "")
            landed = REDIRECTS.get(title)
            return httpx.Response(200, json={"query": {"pages": [{"title": landed} if landed else {"title": title, "missing": True}]}})
        if q.get("action") == "parse":
            text = PAGES.get(q.get("page", ""))
            return httpx.Response(200, json={"parse": {"wikitext": text}} if text else {"error": {"code": "missingtitle"}})
        return httpx.Response(404)


@pytest.fixture(autouse=True)
def fast(monkeypatch):
    monkeypatch.setattr(wiki, "SPACING_SECONDS", 0)


def client(tmp_path, fake, **kw):
    return WikiClient(tmp_path, transport=httpx.MockTransport(fake.handler), **kw)


def test_lead_link_skips_templates_and_references():
    assert lead_link("{{Infobox|x=[[Nope]]}} It represents<ref>[[Ref]]</ref> the [[University of X|X]].") == "University of X"
    assert lead_link("No such sentence here [[Somewhere]].") is None
    assert lead_link(None) is None and lead_link(5) is None
    assert lead_link("It represents [[File:Logo.png]] only.") is None


def test_a_team_from_its_football_page(tmp_path):
    fake = FakeWikipedia()
    got = asyncio.run(client(tmp_path, fake).team("Mudtown", "Mudpuppies"))
    assert got == {"football": page_url("Mudtown Mudpuppies football"), "school": page_url("University of Mudtown"), "resolved": True}
    assert got["football"] == "https://en.wikipedia.org/wiki/Mudtown_Mudpuppies_football"
    # kept on disk: a new client answers without a call
    fake2 = FakeWikipedia()
    assert asyncio.run(client(tmp_path, fake2).team("Mudtown", "Mudpuppies")) == got and fake2.calls == []


def test_the_school_from_the_athletics_page_when_the_football_page_has_none(tmp_path):
    got = asyncio.run(client(tmp_path, FakeWikipedia()).team("Riverbend", "Otters"))
    assert got["school"] == page_url("Riverbend State University") and got["resolved"] is True


def test_a_football_page_found_by_search_skips_season_pages(tmp_path):
    got = asyncio.run(client(tmp_path, FakeWikipedia()).team("Hilltop", "Goats"))
    assert got["football"] == page_url("Hilltop Goats football")
    assert got["school"] == search_url("Hilltop university") and got["resolved"] is False


def test_a_stadium_follows_its_redirect_and_an_unknown_one_is_a_search(tmp_path):
    c = client(tmp_path, FakeWikipedia())
    assert asyncio.run(c.venue("Old Field Stadium")) == {"stadium": page_url("New Field Stadium"), "resolved": True}
    assert asyncio.run(c.venue("Nowhere Park")) == {"stadium": search_url("Nowhere Park"), "resolved": False}
    assert asyncio.run(c.venue(None)) == {"stadium": None, "resolved": False}
    assert asyncio.run(c.team("", "X")) == {"football": None, "school": None, "resolved": False}


def test_a_coach_is_found_by_name_and_an_unknown_one_is_a_search(tmp_path):
    fake = FakeWikipedia()
    c = client(tmp_path, fake)
    found = asyncio.run(c.coach("Pat Mudd", "Mudtown"))
    assert found == {"page": page_url("Pat Mudd (American football coach)"), "resolved": True}, "the first hit that names the person: not the stadium, not the season page"
    assert asyncio.run(c.coach("Nobody Known", "Mudtown")) == {"page": search_url("Nobody Known football coach"), "resolved": False}
    assert asyncio.run(c.coach(None)) == {"page": None, "resolved": False}
    calls = len(fake.calls)
    assert asyncio.run(c.coach("Pat Mudd", "Mudtown")) == found and len(fake.calls) == calls, "kept on disk after the first lookup"
    assert asyncio.run(client(tmp_path / "off", FakeWikipedia(), lookups=False).coach("Pat Mudd", "X")) == {"page": search_url("Pat Mudd football coach"), "resolved": False}


def test_failures_fall_back_to_searches_pause_and_retry_later(tmp_path):
    fake = FakeWikipedia()
    fake.down = True
    now = [datetime(2026, 10, 7, tzinfo=timezone.utc)]
    c = client(tmp_path, fake, clock=lambda: now[0])
    got = asyncio.run(c.team("Mudtown", "Mudpuppies"))
    assert got == {"football": search_url("Mudtown football"), "school": search_url("Mudtown university"), "resolved": False}
    calls = len(fake.calls)
    assert calls <= wiki.PAUSE_AFTER_FAILURES
    assert asyncio.run(c.venue("Old Field Stadium"))["resolved"] is False and len(fake.calls) == calls, "paused: no more calls"
    # a search stand-in is tried again after RETRY_SECONDS, once Wikipedia answers
    fake.down = False
    c._paused_until = 0
    now[0] += timedelta(seconds=wiki.RETRY_SECONDS + 1)
    assert asyncio.run(c.team("Mudtown", "Mudpuppies"))["resolved"] is True


def test_a_damaged_store_starts_over(tmp_path):
    (tmp_path / "wiki").mkdir()
    (tmp_path / "wiki" / "links.json").write_text("{nope", encoding="utf-8")
    assert asyncio.run(client(tmp_path, FakeWikipedia()).team("Mudtown", "Mudpuppies"))["resolved"] is True
    stored = json.loads((tmp_path / "wiki" / "links.json").read_text(encoding="utf-8"))
    assert "team:Mudtown" in stored


def test_no_lookups_means_searches_and_no_calls(tmp_path):
    fake = FakeWikipedia()
    c = client(tmp_path, fake, lookups=False)
    assert asyncio.run(c.team("Mudtown", "Mudpuppies"))["football"] == search_url("Mudtown football")
    assert asyncio.run(c.venue("Old Field Stadium"))["stadium"] == search_url("Old Field Stadium")
    assert fake.calls == []


def test_the_route(settings, fake_cfbd):
    from fastapi.testclient import TestClient

    from app.logging_setup import configure_logging, shutdown_logging
    from app.main import create_app

    fake_cfbd.fixture("/teams/fbs", "teams_fbs")
    fake = FakeWikipedia()
    configure_logging(settings)
    application = create_app(settings, cfbd_transport=fake_cfbd.transport, wiki_transport=httpx.MockTransport(fake.handler))
    try:
        with TestClient(application, base_url="https://testserver") as tc:
            tc.portal.call(application.state.live.stop_background)
            body = tc.get("/api/wiki", params=[("team", "Swampwater Tech"), ("team", " "), ("venue", "Old Field Stadium")]).json()
            assert body["errors"] == []
            assert list(body["data"]["teams"]) == ["Swampwater Tech"]
            assert body["data"]["venues"]["Old Field Stadium"]["stadium"] == page_url("New Field Stadium")
            assert tc.get("/api/wiki").json()["data"] == {"teams": {}, "venues": {}, "coaches": {}}
            coaches = tc.get("/api/wiki", params=[("coach", "Pat Mudd|Mudtown"), ("coach", "|x"), ("coach", "Nobody Known|Mudtown")]).json()["data"]["coaches"]
            assert list(coaches) == ["Pat Mudd|Mudtown", "Nobody Known|Mudtown"] and coaches["Pat Mudd|Mudtown"]["resolved"] is True
    finally:
        shutdown_logging()
