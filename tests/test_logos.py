"""The logo store (Phase 16, G3-10, P-08, DS-07): a logo is fetched once from CFBD's CDN and served
from disk after, a missing logo is a 404 remembered for a week, an oversized or non-PNG answer is
refused and remembered, a timeout or 5xx is retried once and then a 404 that is tried again later,
repeated failures pause the store, bad ids never reach upstream, and no payload the tablet reads
carries a CDN URL."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.logging_setup import configure_logging, shutdown_logging
from app.main import create_app
from app.services import logos
from app.services.logos import LogoStore, logo_fields, logo_path
from tests.conftest import ROLES, TEAM, FakeCfbd, fixture_payload

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


class FakeCdn:
    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.responses: dict[str, httpx.Response | Exception | list] = {}
        self.default = httpx.Response(200, content=PNG, headers={"content-type": "image/png"})

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        folder, _size, name = request.url.path.strip("/").split("/")
        key = f"{name.removesuffix('.png')}{'-dark' if folder == 'logos-dark' else ''}"
        answer = self.responses.get(key, self.default)
        if isinstance(answer, list):  # a sequence: one answer per request, the last one repeats
            answer = answer.pop(0) if len(answer) > 1 else answer[0]
        if isinstance(answer, Exception):
            raise answer
        return answer

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)


@pytest.fixture
def cdn() -> FakeCdn:
    return FakeCdn()


@pytest.fixture
def logo_app(settings: Settings, fake_cfbd: FakeCfbd, cdn: FakeCdn):
    configure_logging(settings)
    application = create_app(settings, cfbd_transport=fake_cfbd.transport, logo_transport=cdn.transport)

    async def no_wait(_: float) -> None:
        return None

    application.state.logos._sleep = no_wait
    yield application
    shutdown_logging()


@pytest.fixture
def logo_client(logo_app):
    with TestClient(logo_app, base_url="https://testserver") as test_client:
        yield test_client


def test_logo_is_fetched_once_then_served_from_disk(logo_client: TestClient, logo_app, cdn: FakeCdn):
    first = logo_client.get("/media/logo/57")
    assert first.status_code == 200 and first.headers["content-type"] == "image/png" and first.content == PNG
    assert first.headers["cache-control"] == "public, max-age=2592000"
    assert str(cdn.requests[0].url) == "https://cdn.collegefootballdata.com/logos/256/57.png"
    second = logo_client.get("/media/logo/57")
    assert second.status_code == 200 and len(cdn.requests) == 1
    assert (logo_app.state.settings.data_dir / "logos" / "57.png").read_bytes() == PNG
    dark = logo_client.get("/media/logo/57?v=dark")
    assert dark.status_code == 200 and str(cdn.requests[-1].url) == "https://cdn.collegefootballdata.com/logos-dark/256/57.png"
    assert (logo_app.state.settings.data_dir / "logos" / "57-dark.png").exists()
    assert logo_app.state.logos.stats["served_from_disk"] == 1 and logo_app.state.logos.stats["fetched"] == 2


def test_missing_logo_is_a_404_remembered_for_a_week(logo_client: TestClient, logo_app, cdn: FakeCdn):
    cdn.responses["99"] = httpx.Response(404)
    first = logo_client.get("/media/logo/99")
    assert first.status_code == 404 and first.headers["cache-control"] == "public, max-age=86400"
    second = logo_client.get("/media/logo/99")
    assert second.status_code == 404 and len(cdn.requests) == 1 and second.headers["x-logo"] == "no logo (remembered)"
    marker = json.loads((logo_app.state.settings.data_dir / "logos" / "99.miss.json").read_text(encoding="utf-8"))
    assert marker["reason"] == "404" and marker["at"] > 0


def test_a_broken_miss_marker_is_ignored(logo_client: TestClient, logo_app, cdn: FakeCdn):
    (logo_app.state.settings.data_dir / "logos" / "12.miss.json").write_text("[not json", encoding="utf-8")
    assert logo_client.get("/media/logo/12").status_code == 200 and len(cdn.requests) == 1


@pytest.mark.parametrize(
    ("answer", "reason"),
    [
        (httpx.Response(200, content=b"\x89PNG" + b"\x00" * (logos.MAX_BYTES + 1), headers={"content-type": "image/png"}), "size cap"),
        (httpx.Response(200, content=b"<html>login</html>", headers={"content-type": "text/html"}), "not an image"),
        (httpx.Response(200, content=b"GIF89a....", headers={"content-type": "image/gif"}), "not a png"),
        (httpx.Response(200, content=b"", headers={"content-type": "image/png"}), "empty"),
    ],
)
def test_oversized_or_non_png_answers_are_refused_and_remembered(logo_client: TestClient, logo_app, cdn: FakeCdn, answer, reason):
    cdn.responses["7"] = answer
    first = logo_client.get("/media/logo/7")
    assert first.status_code == 404, reason
    assert "did not return a usable PNG" in first.headers["x-logo"] and first.headers["cache-control"] == "public, max-age=86400"
    assert not (logo_app.state.settings.data_dir / "logos" / "7.png").exists()
    assert logo_client.get("/media/logo/7").status_code == 404 and len(cdn.requests) == 1


def test_a_timeout_is_retried_once_then_a_404_tried_again_later(logo_client: TestClient, logo_app, cdn: FakeCdn):
    cdn.responses["8"] = httpx.ReadTimeout("slow")
    first = logo_client.get("/media/logo/8")
    assert first.status_code == 404 and first.headers["cache-control"] == "no-cache" and "ReadTimeout" in first.headers["x-logo"]
    assert len(cdn.requests) == 2  # one retry, bounded
    del cdn.responses["8"]
    assert logo_client.get("/media/logo/8").status_code == 200 and len(cdn.requests) == 3


def test_a_5xx_then_success_is_one_logo(logo_client: TestClient, cdn: FakeCdn):
    cdn.responses["61"] = [httpx.Response(503), httpx.Response(200, content=PNG, headers={"content-type": "image/png"})]
    assert logo_client.get("/media/logo/61").status_code == 200 and len(cdn.requests) == 2


def test_repeated_failures_pause_the_store(logo_client: TestClient, logo_app, cdn: FakeCdn):
    cdn.default = httpx.Response(503)
    for team_id in range(1, logos.PAUSE_AFTER_FAILURES + 1):
        assert logo_client.get(f"/media/logo/{team_id}").status_code == 404
    asked = len(cdn.requests)
    assert asked == logos.PAUSE_AFTER_FAILURES * logos.ATTEMPTS
    paused = logo_client.get("/media/logo/500")
    assert paused.status_code == 404 and "paused" in paused.headers["x-logo"] and paused.headers["cache-control"] == "no-cache"
    assert len(cdn.requests) == asked and logo_app.state.logos.paused_until > 0


@pytest.mark.parametrize("path", ["/media/logo/abc", "/media/logo/57x", "/media/logo/1234567890", "/media/logo/57?v=sepia", "/media/logo/-1"])
def test_bad_ids_and_variants_never_reach_upstream(logo_client: TestClient, cdn: FakeCdn, path: str):
    response = logo_client.get(path)
    assert response.status_code == 404 and len(cdn.requests) == 0


def test_the_same_logo_asked_at_once_is_fetched_once(settings: Settings, cdn: FakeCdn):
    store = LogoStore(settings.data_dir, transport=cdn.transport)

    async def scenario() -> list:
        try:
            return await asyncio.gather(*(store.get("57") for _ in range(6)))
        finally:
            await store.aclose()

    results = asyncio.run(scenario())
    assert all(r.path is not None for r in results) and len(cdn.requests) == 1


def test_logo_fields_are_local_urls_and_guard_junk():
    cdn_list = ["https://cdn.collegefootballdata.com/logos/500/57.png", "https://cdn.collegefootballdata.com/logos-dark/500/57.png"]
    assert logo_fields(57, cdn_list) == {"logo": "/media/logo/57", "logoDark": "/media/logo/57?v=dark"}
    assert logo_fields(57, cdn_list[:1]) == {"logo": "/media/logo/57", "logoDark": None}
    assert logo_fields(57, None) == {"logo": None, "logoDark": None}
    assert logo_fields(57, "not a list") == {"logo": None, "logoDark": None}
    assert logo_fields(None, cdn_list) == {"logo": None, "logoDark": None}
    assert logo_fields(True, cdn_list) == {"logo": None, "logoDark": None}
    assert logo_fields("57; rm", cdn_list) == {"logo": None, "logoDark": None}
    assert logo_fields(57, [None, 5, "https://elsewhere/a.png", "https://elsewhere/b.png"]) == {"logo": "/media/logo/57", "logoDark": "/media/logo/57?v=dark"}
    assert logo_path(2005) == "/media/logo/2005" and logo_path(2005, "dark") == "/media/logo/2005?v=dark"


def _our_id() -> int:
    return next(t["id"] for t in fixture_payload("teams_fbs") if t["school"] == TEAM)


def test_no_payload_the_tablet_reads_carries_a_cdn_url(client: TestClient, fake_cfbd: FakeCfbd):
    from tests.test_national import route_all

    route_all(fake_cfbd)
    fake_cfbd.fixture("/player/search", "player_search_name")
    paths = [
        "/api/season/overview", "/api/program/next", "/api/search?q=swa", "/api/search?q=din&wide=1", "/api/roster", "/api/team/Diner%20Tech",
        "/api/team/Swampwater Tech", "/api/season/leaders", "/api/ratings", "/api/recruiting", f"/api/players/{ROLES['QBID']}",
        "/api/national/profile:ypp", "/api/national/rating:sp?scope=conference", "/api/national/board:passing:YDS?team=Diner%20Tech", "/api/national/poll:AP", "/api/national/class:2026",
    ]
    for path in paths:
        response = client.get(path)
        assert response.status_code == 200, path
        assert "cdn.collegefootballdata.com" not in response.text, path
        assert "/media/logo/" in response.text or path in ("/api/ratings", "/api/recruiting"), path  # those two send no logos
    overview = client.get("/api/season/overview").json()["data"]
    US_ID = _our_id()
    assert overview["team"]["logo"] == f"/media/logo/{US_ID}" and overview["team"]["logoDark"] == f"/media/logo/{US_ID}?v=dark"
    assert all(r["logo"].startswith("/media/logo/") for r in overview["standings"] if r["logo"])
