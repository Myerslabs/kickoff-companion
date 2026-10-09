"""Phase 18.6: the host PIN and view-only guests, Invite friends, the monitors and the board launcher, the sign-in page."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.guests import cookie_value, is_host
from app.services.host import COOKIE, HostAccess, LockedOut, PinError
from app.services.screens import BoardLauncher, kiosk_command


def test_a_pin_is_four_to_eight_digits_and_stored_hashed(tmp_path):
    access = HostAccess(tmp_path)
    assert not access.pin_set
    for bad in ("123", "123456789", "12ab", "", None, 1234):
        with pytest.raises(PinError):
            access.set_pin(bad)
    access.set_pin("4321")
    assert access.pin_set and "4321" not in (tmp_path / "host.json").read_text(encoding="utf-8")
    assert HostAccess(tmp_path).pin_set, "survives a restart"
    assert access.verify("4321") and not access.verify("0000")
    assert access.valid_token(access.token()) and not access.valid_token("nope") and not access.valid_token(None)


def test_changing_the_pin_signs_old_cookies_out(tmp_path):
    access = HostAccess(tmp_path)
    access.set_pin("1111")
    old = access.token()
    access.set_pin("2222")
    assert not access.valid_token(old) and access.valid_token(access.token())
    access.clear()
    assert not access.pin_set and not access.valid_token(old) and access.verify("anything")


def test_five_wrong_pins_lock_an_address_out_for_a_minute(tmp_path):
    now = [0.0]
    access = HostAccess(tmp_path, clock=lambda: now[0])
    access.set_pin("1234")
    for _ in range(5):
        assert access.verify("0000", "10.0.0.9") is False
    with pytest.raises(LockedOut):
        access.verify("1234", "10.0.0.9")  # even the right PIN waits
    assert access.verify("1234", "10.0.0.8"), "another address is not locked"
    now[0] = 61.0
    assert access.verify("1234", "10.0.0.9")


def test_a_damaged_host_file_keeps_every_device_a_guest(tmp_path):
    # final pass: a host file that exists but cannot be read never makes everyone the host; the PIN reads as set and
    # matches nothing until the server computer sets it again (and no file at all still means no PIN)
    assert not HostAccess(tmp_path).pin_set
    (tmp_path / "host.json").write_text("{not json", encoding="utf-8")
    damaged = HostAccess(tmp_path)
    assert damaged.pin_set and damaged.damaged and damaged.verify("1234") is False and damaged.token() == ""
    (tmp_path / "host.json").write_text('{"salt": 1}', encoding="utf-8")
    assert HostAccess(tmp_path).pin_set
    damaged.set_pin("2468")
    repaired = HostAccess(tmp_path)
    assert repaired.pin_set and not repaired.damaged and repaired.verify("2468")


def scope(client_host="10.0.0.9", cookie=None):
    headers = [(b"cookie", f"{COOKIE}={cookie}".encode())] if cookie else []
    return {"type": "http", "client": (client_host, 1), "headers": headers}


def test_who_is_a_host(tmp_path):
    access = HostAccess(tmp_path)
    assert is_host(scope(), access), "no PIN: everyone"
    access.set_pin("1234")
    assert not is_host(scope(), access)
    assert is_host(scope("127.0.0.1"), access), "the server computer"
    assert is_host(scope(cookie=access.token()), access)
    assert not is_host(scope(cookie="wrong"), access)
    assert cookie_value({"headers": [(b"cookie", b"\xff\xfe=;;")]}) in (None, "")


def test_guests_look_and_the_host_changes(client: TestClient, app):
    assert client.put("/api/settings", json={"delaySeconds": 20}).status_code == 200  # no PIN yet: everyone is the host
    app.state.host_access.set_pin("1234")
    assert client.get("/api/settings").status_code == 200
    refused = client.put("/api/settings", json={"delaySeconds": 25})
    assert refused.status_code == 403 and refused.json()["errors"][0]["code"] == "view_only"
    assert client.post("/api/client-log", json={"events": []}).status_code != 403, "the error report stays open"
    assert client.post("/api/host/login", json={"pin": "0000"}).status_code == 403
    assert client.post("/api/host/login", json={"pin": "1234"}).status_code == 200
    assert client.put("/api/settings", json={"delaySeconds": 25}).status_code == 200, "signed in: the host"
    status = client.get("/api/host").json()["data"]
    assert status["pinSet"] and status["isHost"]
    client.cookies.clear()
    assert client.get("/api/host").json()["data"]["isHost"] is False


def test_the_first_pin_is_set_from_the_server_computer_only(client: TestClient, app):
    assert client.post("/api/host/pin", json={"pin": "1234"}).status_code == 403  # the test client is another device
    assert not app.state.host_access.pin_set
    app.state.host_access.set_pin("1234")
    client.post("/api/host/login", json={"pin": "1234"})
    assert client.post("/api/host/pin", json={"pin": "5678"}).status_code == 200, "a signed-in host may change it"
    assert client.request("DELETE", "/api/host").json()["data"]["pinSet"] is False


def test_invite_gives_an_ip_address_a_qr_and_warnings(client: TestClient, monkeypatch):
    monkeypatch.setattr("app.api.host.lan_ip", lambda: "192.168.0.20")
    data = client.get("/api/invite").json()["data"]
    assert data["url"].startswith("http://192.168.0.20:") and data["qrPath"].startswith("/setup/qr.svg?url=http://192.168.0.20")
    assert any("No host PIN" in w for w in data["warnings"]) and data["copyUrl"] is None, "no copy link while the repository is private"
    monkeypatch.setattr("app.api.host.lan_ip", lambda: "8.8.4.4")
    assert any("public network" in w for w in client.get("/api/invite").json()["data"]["warnings"])
    monkeypatch.setattr("app.api.host.lan_ip", lambda: "192.168.137.1")
    assert any("hotspot" in w for w in client.get("/api/invite").json()["data"]["warnings"])
    monkeypatch.setattr("app.api.host.lan_ip", lambda: None)
    data = client.get("/api/invite").json()["data"]
    assert data["url"] is None and data["qrPath"] is None and "no network address" in data["warnings"][0]


def test_the_qr_route_draws_the_servers_own_ip_address(client: TestClient, monkeypatch):
    monkeypatch.setattr("app.api.setup.lan_ip", lambda: "192.168.0.20")
    url = f"http://192.168.0.20:{client.app.state.settings.port}/"
    qr = client.get("/setup/qr.svg", params={"url": url})
    assert qr.status_code == 200 and qr.headers["content-type"].startswith("image/svg")
    assert client.get("/setup/qr.svg", params={"url": "http://evil.example/"}).status_code == 404


def test_the_kiosk_command_places_the_window_on_the_chosen_monitor(tmp_path):
    screen = {"x": 1920, "y": 0, "width": 3840, "height": 2160}
    command = kiosk_command(r"C:\Edge\msedge.exe", "http://localhost:8642/#board", screen, tmp_path)
    assert command[:3] == [r"C:\Edge\msedge.exe", "--kiosk", "http://localhost:8642/#board"]
    assert "--window-position=1920,0" in command and "--window-size=3840,2160" in command and "--edge-kiosk-type=fullscreen" in command
    assert f"--user-data-dir={tmp_path}" in command
    chrome = kiosk_command("/usr/bin/chromium", "http://localhost/", None, tmp_path)
    assert "--edge-kiosk-type=fullscreen" not in chrome and not any(a.startswith("--window-position") for a in chrome)


def test_the_launcher_reports_a_missing_browser_and_a_gone_screen(tmp_path, monkeypatch):
    launcher = BoardLauncher(tmp_path)
    monkeypatch.setattr("app.services.screens.find_browser", lambda: None)
    assert "No Edge or Chrome" in launcher.open("http://localhost/", None)["error"]
    monkeypatch.setattr("app.services.screens.find_browser", lambda: "/bin/browser")
    monkeypatch.setattr("app.services.screens.list_screens", lambda: [{"index": 0, "x": 0, "y": 0, "width": 10, "height": 10, "name": "S"}])
    assert "not connected" in launcher.open("http://localhost/", 3)["error"]
    assert launcher.close() is False


def test_board_routes_work_only_from_the_server_computer(client: TestClient):
    data = client.get("/api/board/screens").json()["data"]
    assert isinstance(data["screens"], list) and data["serverComputer"] is False
    assert client.post("/api/board/open", json={"screen": 0}).status_code == 403
    assert client.post("/api/board/close").status_code == 403


def test_the_sign_in_page_is_served(client: TestClient):
    page = client.get("/portal")
    assert page.status_code == 200 and "Open the game" in page.text
