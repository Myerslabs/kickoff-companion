"""Public release Phase 4b: plain HTTP on the home network by default, nothing to install on a device.

A new install creates no certificates and serves every page over HTTP; an install that had HTTPS on keeps
its certificates only so old https:// links still answer, with a redirect to http://. The connect page
and the status page offer a QR code for the server's own addresses (never anything else). The browser on
the host opens the app once the server listens, by the Settings choice."""

from __future__ import annotations

import http.client
import io
import socket
import ssl
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import pytest
import uvicorn
from fastapi.testclient import TestClient

from app.cli import browser_url
from app.config import load_settings
from app.logging_setup import configure_logging, shutdown_logging
from app.main import create_app
from app.services.connect import addresses, local_address, print_qr, qr_svg, qr_text
from app.services.prefs import PrefsStore
from app.serving import DualProtocolServer
from app.tls import TlsState
from tests.conftest import CONFERENCE, TEAM, TEST_KEY, FakeCfbd


def make_settings(tmp_path: Path, **values):
    return load_settings(env_file=None, cfbd_api_key=TEST_KEY, team=TEAM, conference=CONFERENCE, log_dir=str(tmp_path / "logs"), data_dir=str(tmp_path / "data"), **values)


@contextmanager
def app_client(settings, base_url: str = "http://testserver"):
    configure_logging(settings)
    try:
        app = create_app(settings, cfbd_transport=FakeCfbd().transport)
        with TestClient(app, base_url=base_url) as client:
            yield app, client
    finally:
        shutdown_logging()


# --- a new install -----------------------------------------------------------------------------------------------


def test_https_is_off_by_default_and_no_certificate_is_made(tmp_path: Path):
    settings = make_settings(tmp_path)
    assert settings.https is False
    with app_client(settings) as (app, client):
        assert app.state.tls is None and not (settings.data_dir / "certs").exists()
        page = client.get("/", follow_redirects=False)
        assert page.status_code == 200  # no redirect to https
        assert client.get("/setup/kickoff-companion-ca.crt").status_code == 404
        health = client.get("/api/health").json()["data"]
        tls = next(c for c in health["checks"] if c["name"] == "tls")
        assert tls["status"] == "ok" and "nothing to install" in tls["detail"] and health["tls"] == {"enabled": False}
        assert health["server"]["tablet_url"].startswith("http://")


def test_the_connect_page_has_the_address_and_a_qr_code_for_it_only(tmp_path: Path):
    settings = make_settings(tmp_path, mdns_name="kickoff")
    with app_client(settings) as (_, client):
        data = client.get("/api/setup").json()["data"]
        assert data["https"] is False and data["ca"] is None and data["download_path"] is None
        assert data["app_url"].startswith("http://kickoff.local:8642") and data["qr_path"] == "/setup/qr.svg"
        page = client.get("/setup")
        assert page.status_code == 200 and "Connect a phone or tablet" in page.text and 'id="trust-steps"' in page.text
        first = client.get("/setup/qr.svg")
        assert first.status_code == 200 and first.headers["content-type"].startswith("image/svg+xml") and first.text.startswith("<svg")
        known = addresses(settings, None)
        assert client.get("/setup/qr.svg", params={"url": known[-1]}).status_code == 200
        for other in ("https://example.com/", "javascript:alert(1)", known[0] + "x"):
            refused = client.get("/setup/qr.svg", params={"url": other})
            assert refused.status_code == 404 and refused.json()["errors"][0]["code"] == "not_found"


# --- an install that had HTTPS on ------------------------------------------------------------------------------------


def test_old_certificates_answer_https_links_with_a_redirect_to_http(tmp_path: Path):
    TlsState.prepare(make_settings(tmp_path, https=True))  # what the install made while HTTPS was on
    settings = make_settings(tmp_path)
    with app_client(settings, base_url="https://testserver") as (app, client):
        assert app.state.tls is not None
        moved = client.get("/season?x=1", follow_redirects=False)
        assert moved.status_code == 301 and moved.headers["location"] == "http://testserver/season?x=1"
        data = client.get("/api/health", follow_redirects=True).json()["data"]
        assert "old https:// addresses are sent to http://" in next(c for c in data["checks"] if c["name"] == "tls")["detail"]
        assert client.get("/setup/kickoff-companion-ca.crt", follow_redirects=True).status_code == 404  # nothing to install now


@contextmanager
def running(settings):
    configure_logging(settings)
    app = create_app(settings, cfbd_transport=FakeCfbd().transport)
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_config=None, access_log=False, lifespan="on", timeout_graceful_shutdown=2)
    server = DualProtocolServer(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.05)
    try:
        assert server.started
        yield server.bound_ports[0], app
    finally:
        server.should_exit = True
        thread.join(10)
        shutdown_logging()


def test_a_real_server_speaks_plain_http_and_turns_tls_away(tmp_path: Path):
    with running(make_settings(tmp_path)) as (port, _):
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", "/api/health")
        assert conn.getresponse().status == 200
        conn.close()
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        with socket.create_connection(("127.0.0.1", port), timeout=5) as raw, pytest.raises((ssl.SSLError, ConnectionError, OSError)):
            with context.wrap_socket(raw, server_hostname="localhost") as tls:
                tls.sendall(b"GET / HTTP/1.1\r\nHost: x\r\n\r\n")
                if not tls.recv(1):
                    raise ConnectionError("closed")  # a browser falls back to http:// here


def test_a_real_server_with_old_certificates_redirects_a_trusting_device(tmp_path: Path):
    old = TlsState.prepare(make_settings(tmp_path, https=True))
    with running(make_settings(tmp_path)) as (port, _):
        conn = http.client.HTTPSConnection("127.0.0.1", port, context=ssl.create_default_context(cafile=str(old.ca_cert_path)), timeout=5)
        conn.request("GET", "/status")
        response = conn.getresponse()
        assert response.status == 301 and response.getheader("location") == f"http://127.0.0.1:{port}/status"
        conn.close()


# --- the QR code ---------------------------------------------------------------------------------------------------


def test_qr_code_drawings():
    svg = qr_svg("http://kickoff.local:8642/")
    assert svg.startswith('<svg xmlns="http://www.w3.org/2000/svg"') and "#000" in svg and "#fff" in svg  # dark on white whatever the theme
    text = qr_text("http://kickoff.local:8642/")
    lines = text.split("\n")
    assert len({len(line) for line in lines}) == 1 and set(text) <= {"█", "▀", "▄", " ", "\n"}
    assert lines[0] == "█" * len(lines[0])  # the quiet zone is light: a full row of blocks
    shown = io.StringIO()
    assert print_qr("http://kickoff.local:8642/", shown) and "Scan with a phone or tablet" in shown.getvalue()


def test_a_window_that_cannot_show_the_code_is_no_problem(caplog):
    class Ascii(io.StringIO):
        def write(self, value: str) -> int:
            value.encode("ascii")
            return super().write(value)

    assert print_qr("http://kickoff.local:8642/", Ascii()) is False
    assert "status page has it" in caplog.text
    assert print_qr("http://kickoff.local:8642/") is False  # pytest's captured output is not a terminal: nothing printed


# --- the browser on start -----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "choice, login, opens",
    [("manual", False, True), ("manual", True, False), ("always", True, True), ("always", False, True), ("never", False, False), ("never", True, False)],
)
def test_the_browser_opens_by_the_settings_choice(tmp_path: Path, choice: str, login: bool, opens: bool):
    settings = make_settings(tmp_path)
    PrefsStore(settings.data_dir).update({"openBrowser": choice})
    url = browser_url(settings, no_browser=False, login=login)
    assert (url == "http://localhost:8642/") is opens and (url is None) is not opens
    assert browser_url(settings, no_browser=True, login=False) is None
    assert local_address(make_settings(tmp_path, https=True)) == "https://localhost:8642/"


def test_a_server_opens_its_address_once_it_listens(tmp_path: Path, monkeypatch):
    opened: list[str] = []
    monkeypatch.setattr("app.serving.open_in_browser", lambda url: opened.append(url))
    settings = make_settings(tmp_path)
    configure_logging(settings)
    app = create_app(settings, cfbd_transport=FakeCfbd().transport)
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_config=None, access_log=False, lifespan="on", timeout_graceful_shutdown=2)
    server = DualProtocolServer(config, open_url="http://localhost:8642/")
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not opened and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.05)
    server.should_exit = True
    thread.join(10)
    shutdown_logging()
    assert opened == ["http://localhost:8642/"] and server.started


def test_the_setting_is_validated(tmp_path: Path):
    from app.services.prefs import PrefsError

    store = PrefsStore(tmp_path)
    assert store.prefs.openBrowser == "manual"
    with pytest.raises(PrefsError):
        store.update({"openBrowser": "sometimes"})
