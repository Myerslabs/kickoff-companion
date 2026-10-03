"""The one-port server on loopback: HTTPS for a device that trusts the CA, plain HTTP
redirected, setup pages reachable over plain HTTP, junk and silence handled quietly."""

from __future__ import annotations

import http.client
import json
import logging
import socket
import ssl
import threading
import time
from contextlib import contextmanager

import pytest
import uvicorn

from app import serving
from app.logging_setup import configure_logging, shutdown_logging
from app.main import create_app
from app.serving import DualProtocolServer, bind_listener
from app.tls import CA_DOWNLOAD_NAME, TlsState
from tests.conftest import FakeCfbd


@pytest.fixture
def settings(tmp_path):
    """This file tests HTTPS=on (the app's own certificate authority); plain HTTP, the default since
    public release Phase 4b, is covered by tests/test_http_default.py."""
    from app.config import load_settings
    from tests.conftest import CONFERENCE, TEAM, TEST_KEY

    return load_settings(env_file=None, cfbd_api_key=TEST_KEY, team=TEAM, conference=CONFERENCE, log_dir=str(tmp_path / "logs"), data_dir=str(tmp_path / "data"), https=True)


@contextmanager
def running_server(settings, tls: TlsState):
    app = create_app(settings, tls, cfbd_transport=FakeCfbd().transport)
    config = uvicorn.Config(
        app, host="127.0.0.1", port=0, log_config=None, access_log=False, lifespan="on", timeout_graceful_shutdown=2
    )
    server = DualProtocolServer(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert server.started, "server did not start"
    try:
        yield server.bound_ports[0]
    finally:
        server.should_exit = True
        thread.join(10)
        assert not thread.is_alive(), "server did not stop"


@pytest.fixture
def live(settings):
    configure_logging(settings)
    tls = TlsState.prepare(settings)
    with running_server(settings, tls) as port:
        yield port, tls
    shutdown_logging()


def trusted_context(tls: TlsState) -> ssl.SSLContext:
    return ssl.create_default_context(cafile=str(tls.ca_cert_path))


def https_get(port: int, tls: TlsState, path: str):
    conn = http.client.HTTPSConnection("127.0.0.1", port, context=trusted_context(tls), timeout=5)
    try:
        conn.request("GET", path)
        response = conn.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        conn.close()


def http_get(port: int, path: str):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.request("GET", path)
        response = conn.getresponse()
        return response.status, {k.lower(): v for k, v in response.getheaders()}, response.read()
    finally:
        conn.close()


def test_https_works_for_a_device_that_trusts_the_ca(live):
    port, tls = live
    status, _, body = https_get(port, tls, "/api/health")
    assert status == 200
    data = json.loads(body)["data"]
    assert data["status"] == "ok"
    assert data["server"]["tablet_url"].startswith("https://")
    assert any(check["name"] == "tls" and check["status"] == "ok" for check in data["checks"])


def test_plain_http_is_redirected_to_https(live):
    port, _ = live
    status, headers, _ = http_get(port, "/api/health")
    assert status == 302
    assert headers["location"] == f"https://127.0.0.1:{port}/api/health"
    status, headers, _ = http_get(port, "/")
    assert status == 302
    assert headers["location"] == f"https://127.0.0.1:{port}/"


def test_setup_page_and_ca_download_work_over_plain_http(live):
    port, tls = live
    status, headers, body = http_get(port, "/setup")
    assert status == 200
    assert headers["content-type"].startswith("text/html")
    assert b"Download certificate" in body

    status, headers, body = http_get(port, f"/setup/{CA_DOWNLOAD_NAME}")
    assert status == 200
    assert headers["content-type"].startswith("application/x-x509-ca-cert")
    assert body.startswith(b"-----BEGIN CERTIFICATE-----")
    assert body == tls.ca_cert_path.read_bytes()
    assert b"PRIVATE" not in body

    status, _, body = http_get(port, "/api/setup")
    assert status == 200
    assert json.loads(body)["data"]["scheme"] == "http"


def test_untrusted_client_is_refused_and_the_server_carries_on(live, caplog):
    port, tls = live
    caplog.set_level(logging.INFO, logger="kickoff.serving")
    for _ in range(2):
        conn = http.client.HTTPSConnection("127.0.0.1", port, context=ssl.create_default_context(), timeout=5)
        with pytest.raises(ssl.SSLError):
            conn.request("GET", "/")
        conn.close()

    def handshake_records():
        return [r for r in caplog.records if "TLS handshake" in r.getMessage()]

    deadline = time.monotonic() + 3
    while time.monotonic() < deadline and len(handshake_records()) < 2:
        time.sleep(0.05)
    records = handshake_records()
    assert len(records) == 2
    assert all("setup page" in r.getMessage() for r in records)
    # The first failure from a device is a WARNING, repeats within the interval are INFO.
    assert [r.levelno for r in records] == [logging.WARNING, logging.INFO]

    status, _, _ = https_get(port, tls, "/api/health")
    assert status == 200


def test_junk_bytes_do_no_harm(live):
    port, tls = live
    with socket.create_connection(("127.0.0.1", port), timeout=5) as sock:
        sock.sendall(b"\x00\x01\x02 junk\r\n\r\n")
        try:
            sock.recv(1024)
        except OSError:
            pass
    status, _, _ = https_get(port, tls, "/api/health")
    assert status == 200


def test_silent_connection_is_dropped_after_the_peek_timeout(live, monkeypatch):
    port, tls = live
    monkeypatch.setattr(serving, "PEEK_TIMEOUT", 0.3)
    with socket.create_connection(("127.0.0.1", port), timeout=5) as sock:
        try:
            assert sock.recv(1) == b""
        except (ConnectionResetError, ConnectionAbortedError):
            pass
    status, _, _ = https_get(port, tls, "/api/health")
    assert status == 200


def test_bind_listener_refuses_a_port_already_in_use():
    first = bind_listener("127.0.0.1", 0)
    first.listen()  # as the server's is; Linux lets two sockets bind one port until one of them listens
    try:
        port = first.getsockname()[1]
        with pytest.raises(OSError):
            bind_listener("127.0.0.1", port)
    finally:
        first.close()
