"""Public release Phase 4: the server's own name on the home network (kickoff.local). Never touches the
network: the zeroconf object and the clash check are fakes. Covers the setting, the announcement, a
name another device already answers to, failures that must not stop the server, the certificate and
the addresses the app shows."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import SettingsError, load_settings
from app.netinfo import other_urls, preferred_host, tablet_url
from app.services.mdns import SERVICE_TYPE, Announcer
from app.tls import planned_names
from tests.conftest import CONFERENCE, TEAM, TEST_KEY


class FakeZeroconf:
    def __init__(self, ip: str, *, fail: Exception | None = None) -> None:
        self.ip = ip
        self.fail = fail
        self.registered: list[Any] = []
        self.unregistered: list[Any] = []
        self.closed = False
        self.zeroconf = self

    async def async_register_service(self, info: Any, allow_name_change: bool = False) -> None:
        if self.fail:
            raise self.fail
        self.registered.append((info, allow_name_change))

    async def async_unregister_service(self, info: Any) -> None:
        self.unregistered.append(info)

    async def async_close(self) -> None:
        self.closed = True


def announcer(*, ip: str | None = "192.0.2.10", fail: Exception | None = None, other: str | None = None) -> tuple[Announcer, list[FakeZeroconf]]:
    made: list[FakeZeroconf] = []

    def factory(address: str) -> FakeZeroconf:
        made.append(FakeZeroconf(address, fail=fail))
        return made[-1]

    async def clash(zc: Any, host: str, address: str) -> str | None:
        return other

    return Announcer("kickoff.local", 8642, title="Mudpuppies Kickoff Companion", ip_provider=lambda: ip, factory=factory, conflict_check=clash), made


def run(job: Announcer, then_stop: bool = True) -> None:
    async def scenario() -> None:
        job.start()
        await asyncio.sleep(0)
        await job._task  # type: ignore[misc]
        if then_stop:
            await job.stop()

    asyncio.run(scenario())


def test_the_name_is_announced_for_the_lan_address_and_withdrawn_at_stop():
    job, made = announcer()
    run(job, then_stop=False)
    assert job.status()["state"] == "announced" and job.status()["address"] == "192.0.2.10" and job.since
    info, renames = made[0].registered[0]
    assert made[0].ip == "192.0.2.10" and renames is True
    assert info.server == "kickoff.local." and info.port == 8642 and info.type == SERVICE_TYPE and info.name.startswith("Mudpuppies Kickoff Companion.")
    assert info.parsed_addresses() == ["192.0.2.10"]
    asyncio.run(job.stop())
    assert made[0].unregistered == [info] and made[0].closed and job.status()["state"] == "stopped"


def test_a_name_another_device_answers_to_is_not_announced(caplog):
    job, made = announcer(other="192.0.2.99")
    run(job)
    status = job.status()
    assert status["state"] == "conflict" and "192.0.2.99" in status["error"] and "MDNS_NAME" in status["error"]
    assert made[0].registered == [] and made[0].closed
    assert "Did not announce kickoff.local" in caplog.text


@pytest.mark.parametrize("ip, fail, words", [(None, None, "no LAN address"), ("192.0.2.10", OSError("Address already in use"), "OSError")])
def test_failures_are_logged_and_shown_never_raised(caplog, ip, fail, words):
    job, made = announcer(ip=ip, fail=fail)
    run(job)
    assert job.status()["state"] == "failed" and words in job.status()["error"]
    assert "Could not announce kickoff.local" in caplog.text
    assert all(z.closed for z in made)


def test_off_does_nothing():
    job = Announcer("", 8642, factory=lambda ip: pytest.fail("no network when off"))
    job.start()
    asyncio.run(job.stop())
    assert job.status() == {"host": None, "state": "off", "address": None, "error": None, "since": None}


def settings(tmp_path, **values):
    return load_settings(env_file=None, cfbd_api_key=TEST_KEY, team=TEAM, conference=CONFERENCE, log_dir=str(tmp_path / "logs"), data_dir=str(tmp_path / "data"), **values)


@pytest.mark.parametrize("raw, name", [("kickoff", "kickoff"), (" Kickoff.local ", "kickoff"), ("game-day", "game-day"), ("off", ""), ("", ""), ("None", "")])
def test_the_setting(tmp_path, raw, name):
    s = settings(tmp_path, mdns_name=raw)
    assert s.mdns_name == name and s.mdns_host == (f"{name}.local" if name else "")


@pytest.mark.parametrize("raw", ["kick off", "a.b", "-kickoff", "x" * 64, "kick_off"])
def test_a_bad_name_is_refused_with_a_hint(tmp_path, raw):
    with pytest.raises(SettingsError) as caught:
        settings(tmp_path, mdns_name=raw)
    assert "MDNS_NAME" in str(caught.value) or "network name" in str(caught.value)


def test_the_name_goes_on_the_certificate_and_into_the_addresses(tmp_path):
    s = settings(tmp_path, mdns_name="kickoff")
    dns, _ = planned_names(s)
    assert "kickoff.local" in dns and "localhost" in dns
    assert preferred_host(s, "192.0.2.10") == "kickoff.local"
    assert tablet_url(s, "192.0.2.10") == "http://kickoff.local:8642"  # plain HTTP by default (Phase 4b)
    assert other_urls(s, "192.0.2.10") == ["http://192.0.2.10:8642"]
    assert tablet_url(settings(tmp_path, mdns_name="kickoff", https=True), "192.0.2.10") == "https://kickoff.local:8642"
    router = settings(tmp_path, mdns_name="kickoff", lan_hostname="football.localdomain")
    assert preferred_host(router, "192.0.2.10") == "football.localdomain"  # a router name wins; the others still work
    assert other_urls(router, "192.0.2.10") == ["http://kickoff.local:8642", "http://192.0.2.10:8642"]
    off = settings(tmp_path, mdns_name="off")
    assert "kickoff.local" not in planned_names(off)[0] and preferred_host(off, "192.0.2.10") == "192.0.2.10" and other_urls(off, "192.0.2.10") == []
    assert preferred_host(off, None) == "localhost"


def test_status_page_and_setup_page_show_the_name(app, client: TestClient):
    job, _ = announcer(fail=OSError("blocked"))
    app.state.mdns = job
    run(job)
    health = client.get("/api/health").json()["data"]
    check = next(c for c in health["checks"] if c["name"] == "network name")
    assert check["status"] == "degraded" and "IP address" in check["detail"] and health["server"]["mdns"]["state"] == "failed"
    setup = client.get("/api/setup").json()["data"]
    assert isinstance(setup["other_urls"], list)
