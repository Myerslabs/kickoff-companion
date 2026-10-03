"""The front end is served from static/, plain HTTP is redirected except for setup, and API
errors use the envelope."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.tls import CA_DOWNLOAD_NAME
from tests.conftest import TEST_KEY


@pytest.fixture
def settings(tmp_path):
    """This file tests HTTPS=on (the app's own certificate authority); plain HTTP, the default since
    public release Phase 4b, is covered by tests/test_http_default.py."""
    from app.config import load_settings
    from tests.conftest import CONFERENCE, TEAM, TEST_KEY

    return load_settings(env_file=None, cfbd_api_key=TEST_KEY, team=TEAM, conference=CONFERENCE, log_dir=str(tmp_path / "logs"), data_dir=str(tmp_path / "data"), https=True)


def test_index_page(client: TestClient):
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["cache-control"] == "no-cache"
    assert "Kickoff Companion" in response.text
    assert "/static/js/app.js" in response.text
    assert 'href="/setup"' in response.text
    assert 'id="app"' in response.text


def test_status_page(client: TestClient):
    response = client.get("/status")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache"
    assert "/static/js/status.js" in response.text
    assert 'class="wordmark"' in response.text
    assert "/static/js/app.js" not in response.text


def test_static_assets(client: TestClient):
    css = client.get("/static/css/tokens.css")
    assert css.status_code == 200
    assert "text/css" in css.headers["content-type"]
    assert "--team-accent" in css.text
    assert client.get("/static/css/components.css").status_code == 200
    assert client.get("/static/css/app.css").status_code == 200
    js = client.get("/static/js/app.js")
    assert js.status_code == 200
    assert "javascript" in js.headers["content-type"]
    assert client.get("/static/js/status.js").status_code == 200
    assert client.get("/static/js/views/season.js").status_code == 200


def test_plain_http_is_redirected_to_https(plain_client: TestClient):
    for path in ("/", "/api/health", "/nowhere"):
        response = plain_client.get(path, follow_redirects=False)
        assert response.status_code == 302, path
        assert response.headers["location"] == f"https://testserver{path}"


def test_setup_pages_are_allowed_over_plain_http(plain_client: TestClient):
    page = plain_client.get("/setup", follow_redirects=False)
    assert page.status_code == 200
    assert "Download certificate" in page.text
    assert "/static/js/setup.js" in page.text

    ca = plain_client.get(f"/setup/{CA_DOWNLOAD_NAME}", follow_redirects=False)
    assert ca.status_code == 200
    assert ca.headers["content-type"].startswith("application/x-x509-ca-cert")
    assert ca.content.startswith(b"-----BEGIN CERTIFICATE-----")
    assert b"PRIVATE" not in ca.content

    assert plain_client.get("/static/css/app.css", follow_redirects=False).status_code == 200
    assert plain_client.get("/static/js/setup.js", follow_redirects=False).status_code == 200

    info = plain_client.get("/api/setup", follow_redirects=False)
    assert info.status_code == 200
    assert info.json()["data"]["scheme"] == "http"


def test_setup_info_over_https(client: TestClient):
    response = client.get("/api/setup")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["scheme"] == "https"
    assert data["https_url"].startswith("https://")
    assert data["setup_url"].startswith("http://") and data["setup_url"].endswith("/setup")
    assert data["download_path"] == f"/setup/{CA_DOWNLOAD_NAME}"
    assert data["ca"]["name"] == "Kickoff Companion Local CA"
    assert len(data["ca"]["fingerprint_sha256"]) == 95
    assert data["server"]["days_left"] > 300
    assert "PRIVATE" not in response.text
    assert TEST_KEY not in response.text


def test_unknown_api_route_returns_envelope(client: TestClient):
    response = client.get("/api/does-not-exist")
    assert response.status_code == 404
    body = response.json()
    assert body["data"] is None
    assert body["errors"][0]["code"] == "not_found"
    assert body["meta"]["source"] == "live"


def test_unknown_page_is_plain_404(client: TestClient):
    response = client.get("/does-not-exist")
    assert response.status_code == 404
    assert "text/plain" in response.headers["content-type"]


def test_docs_are_disabled(client: TestClient):
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404
