"""The headshot proxy: a PNG is fetched once and served from disk after, a missing photo is a
404 remembered for a week, an upstream failure is a 404 that is retried later, bad ids never
reach upstream, and repeated failures pause the fetcher."""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.logging_setup import configure_logging, shutdown_logging
from app.main import create_app
from app.services import media
from tests.conftest import FakeCfbd

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


class FakeEspn:
    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.responses: dict[str, httpx.Response] = {}
        self.default = httpx.Response(200, content=PNG, headers={"content-type": "image/png"})

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        player_id = request.url.path.rsplit("/", 1)[-1].removesuffix(".png")
        return self.responses.get(player_id, self.default)

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)


@pytest.fixture
def espn() -> FakeEspn:
    return FakeEspn()


@pytest.fixture
def media_app(settings: Settings, fake_cfbd: FakeCfbd, espn: FakeEspn):
    configure_logging(settings)
    application = create_app(settings, cfbd_transport=fake_cfbd.transport, media_transport=espn.transport)
    yield application
    shutdown_logging()


@pytest.fixture
def media_client(media_app):
    with TestClient(media_app, base_url="https://testserver") as test_client:
        yield test_client


def test_headshot_is_fetched_once_then_served_from_disk(media_client: TestClient, media_app, espn: FakeEspn):
    first = media_client.get("/media/headshot/4658456")
    assert first.status_code == 200 and first.headers["content-type"] == "image/png" and first.content == PNG
    assert first.headers["cache-control"] == "public, max-age=604800"
    second = media_client.get("/media/headshot/4658456")
    assert second.status_code == 200 and len(espn.requests) == 1
    stored = media_app.state.settings.data_dir / "headshots" / "4658456.png"
    assert stored.exists() and stored.read_bytes() == PNG
    assert media_app.state.headshots.stats["served_from_disk"] == 1


def test_missing_photo_is_a_404_remembered_for_a_week(media_client: TestClient, espn: FakeEspn):
    espn.responses["55"] = httpx.Response(404)
    first = media_client.get("/media/headshot/55")
    assert first.status_code == 404 and first.headers["cache-control"] == "public, max-age=86400"
    second = media_client.get("/media/headshot/55")
    assert second.status_code == 404 and len(espn.requests) == 1
    assert second.headers["x-headshot"] == "no photo (remembered)"


def test_upstream_error_is_a_404_that_is_retried(media_client: TestClient, espn: FakeEspn):
    espn.responses["77"] = httpx.Response(503)
    first = media_client.get("/media/headshot/77")
    assert first.status_code == 404 and first.headers["cache-control"] == "no-cache"
    del espn.responses["77"]
    second = media_client.get("/media/headshot/77")
    assert second.status_code == 200 and len(espn.requests) == 2


def test_non_png_answer_is_treated_as_missing(media_client: TestClient, espn: FakeEspn):
    espn.responses["88"] = httpx.Response(200, content=b"<html>not found</html>", headers={"content-type": "text/html"})
    response = media_client.get("/media/headshot/88")
    assert response.status_code == 404 and response.headers["cache-control"] == "public, max-age=86400"


def test_bad_ids_never_reach_upstream(media_client: TestClient, espn: FakeEspn):
    for bad in ("abc", "../etc", "1" * 13):
        response = media_client.get(f"/media/headshot/{bad}")
        assert response.status_code == 404, bad
    assert espn.requests == []


def test_repeated_failures_pause_the_fetcher(media_client: TestClient, espn: FakeEspn, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(media, "PAUSE_AFTER_FAILURES", 3)
    for pid in ("1", "2", "3"):
        espn.responses[pid] = httpx.Response(500)
        assert media_client.get(f"/media/headshot/{pid}").status_code == 404
    calls = len(espn.requests)
    paused = media_client.get("/media/headshot/4")
    assert paused.status_code == 404 and paused.headers["x-headshot"].startswith("headshot fetches paused")
    assert len(espn.requests) == calls
