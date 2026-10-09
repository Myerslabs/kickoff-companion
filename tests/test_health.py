"""GET /api/health returns the standard envelope and never leaks the key or private keys."""

from __future__ import annotations

import re
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.config import load_settings
from app.logging_setup import configure_logging, shutdown_logging
from app.main import create_app
from app.netinfo import http_url, tablet_url
from tests.conftest import TEST_KEY, FakeCfbd


@pytest.fixture
def settings(tmp_path):
    """This file tests HTTPS=on (the app's own certificate authority); plain HTTP, the default since
    public release Phase 4b, is covered by tests/test_http_default.py."""
    from app.config import load_settings
    from tests.conftest import CONFERENCE, TEAM, TEST_KEY

    return load_settings(env_file=None, cfbd_api_key=TEST_KEY, team=TEAM, conference=CONFERENCE, log_dir=str(tmp_path / "logs"), data_dir=str(tmp_path / "data"), https=True)

FINGERPRINT = re.compile(r"^([0-9A-F]{2}:){31}[0-9A-F]{2}$")


def test_urls_leave_out_default_ports():
    settings = load_settings(env_file=None, cfbd_api_key=TEST_KEY, lan_hostname="football.localdomain", port=8642, https=True)
    assert tablet_url(settings, "192.0.2.105") == "https://football.localdomain:8642"
    assert tablet_url(settings.model_copy(update={"https": False}), "192.0.2.105") == "http://football.localdomain:8642"  # the default since Phase 4b
    assert tablet_url(settings, "192.0.2.105", secure=False) == "http://football.localdomain:8642"
    assert http_url("192.0.2.105", 80) == "http://192.0.2.105"
    assert http_url("192.0.2.105", 443, secure=True) == "https://192.0.2.105"
    assert http_url("192.0.2.105", 8642) == "http://192.0.2.105:8642"


def test_envelope_shape(client: TestClient):
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"data", "meta", "errors"}
    assert set(body["meta"]) == {"fetched_at", "stale", "source", "build", "restartNeeded"}  # restartNeeded: Phase 16 wave 3
    assert isinstance(body["meta"]["build"], str) and len(body["meta"]["build"]) == 12
    assert body["meta"]["stale"] is False
    assert body["meta"]["source"] == "live"
    assert body["errors"] == []
    fetched = datetime.fromisoformat(body["meta"]["fetched_at"].replace("Z", "+00:00"))
    assert fetched.tzinfo is not None


def test_health_reports_server_config_logging_and_tls(client: TestClient):
    data = client.get("/api/health").json()["data"]
    assert data["status"] == "ok"
    assert data["app"]["name"] == "Kickoff Companion"
    assert data["app"]["phase"] == 15
    assert data["server"]["port"] == 8642
    assert data["server"]["tablet_url"].startswith("https://")
    assert data["server"]["setup_url"].startswith("http://") and data["server"]["setup_url"].endswith("/setup")
    assert data["server"]["uptime_seconds"] >= 0
    assert data["config"]["team"] == "Swampwater Tech"
    assert data["config"]["api_key_configured"] is True
    assert data["logging"]["writable"] is True
    assert data["logging"]["file"].endswith("app.log")
    assert data["tls"]["enabled"] is True
    assert FINGERPRINT.match(data["tls"]["ca"]["fingerprint_sha256"])
    assert "127.0.0.1" in data["tls"]["server"]["ip_addresses"]
    names = [check["name"] for check in data["checks"]]
    assert names == ["server", "config", "logging", "tls", "upstream", "quota", "cache", "live"]
    assert all(check["status"] == "ok" for check in data["checks"]), data["checks"]
    # The fake /info answered at startup: Free tier, 1,000 calls, gated features off.
    assert data["quota"]["reconciled"] is True and data["quota"]["budget"] == 1000
    assert data["capabilities"]["tier_name"] == "Free" and data["capabilities"]["live_plays"] is False
    assert data["upstream"]["breaker"]["state"] == "closed" and data["upstream"]["ttl_scale"] == 4
    assert data["cache"]["entries"] == 0


def test_health_reports_upstream_trouble(settings, fake_cfbd):
    fake_cfbd.route("/info", status=503, text="down")
    configure_logging(settings)
    try:
        with TestClient(create_app(settings, cfbd_transport=fake_cfbd.transport), base_url="https://testserver") as client:
            data = client.get("/api/health").json()["data"]
            assert data["status"] == "degraded"
            upstream = next(check for check in data["checks"] if check["name"] == "upstream")
            assert upstream["status"] == "degraded" and "503" in upstream["detail"]
            quota = next(check for check in data["checks"] if check["name"] == "quota")
            assert quota["status"] == "ok" and "not reconciled" in quota["detail"]
            assert data["quota"]["reconciled"] is False
    finally:
        shutdown_logging()


def test_health_never_contains_secrets(client: TestClient):
    text = client.get("/api/health").text
    assert TEST_KEY not in text
    assert "PRIVATE" not in text


def test_lan_hostname_drives_the_tablet_url_and_certificate(tmp_path):
    settings = load_settings(
        env_file=None,
        cfbd_api_key=TEST_KEY,
        log_dir=str(tmp_path / "logs"),
        data_dir=str(tmp_path / "data"),
        lan_hostname="football.localdomain",
        port=9123,
        https=True,
    )
    configure_logging(settings)
    try:
        with TestClient(create_app(settings, cfbd_transport=FakeCfbd().transport), base_url="https://testserver") as client:
            data = client.get("/api/health").json()["data"]
            assert data["server"]["tablet_url"] == "https://football.localdomain:9123"
            assert data["config"]["lan_hostname"] == "football.localdomain"
            assert data["tls"]["server"]["dns_names"][0] == "football.localdomain"
    finally:
        shutdown_logging()


def test_logging_check_degrades_when_file_missing(tmp_path):
    settings = load_settings(
        env_file=None, cfbd_api_key=TEST_KEY, log_dir=str(tmp_path / "logs"), data_dir=str(tmp_path / "data")
    )
    configure_logging(settings)
    try:
        with TestClient(create_app(settings, cfbd_transport=FakeCfbd().transport), base_url="https://testserver") as client:
            shutdown_logging()
            (settings.log_dir / "app.log").unlink()
            data = client.get("/api/health").json()["data"]
            assert data["status"] == "degraded"
            logging_check = next(check for check in data["checks"] if check["name"] == "logging")
            assert logging_check["status"] == "degraded"
            assert "has not been created" in logging_check["detail"]
    finally:
        shutdown_logging()
