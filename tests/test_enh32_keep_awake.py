"""ENH-32 (owner 2026-10-27): keep the server computer awake while it is plugged in, never on battery, with a Server
Settings switch (plugged, games, off) and a line on the status page."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from app.maintenance import ES_CONTINUOUS, ES_SYSTEM_REQUIRED, KeepAwake, Maintenance
from app.services.prefs import Prefs

NOW = datetime(2026, 10, 27, 15, 0, tzinfo=timezone.utc)


def awake(plugged: bool | None, calls: list[int] | None = None) -> KeepAwake:
    return KeepAwake(platform="win32", state_call=(calls if calls is not None else []).append, power_call=lambda: plugged)


def test_plugged_mode_holds_on_mains_power_and_never_on_battery_even_in_a_game_window():
    assert awake(True).wanted("plugged", window_open=False) is True
    on_battery = awake(False)
    assert on_battery.wanted("plugged", window_open=True) is False  # his answer: never on battery, even on game day
    assert on_battery.reason == "on battery"


def test_a_computer_that_cannot_say_how_it_is_powered_counts_as_plugged_in():
    unknown = awake(None)
    assert unknown.wanted("plugged", window_open=False) is True and unknown.reason == "plugged in"


def test_games_mode_is_the_old_behavior_and_off_never_holds():
    games = awake(False)
    assert games.wanted("games", window_open=True) is True  # the game window decides, not the power
    assert games.wanted("games", window_open=False) is False
    off = awake(True)
    assert off.wanted("off", window_open=True) is False and off.reason == "off in Server Settings"


def test_an_unknown_mode_reads_as_the_default():
    k = awake(True)
    assert k.wanted("sometimes", window_open=False) is True and k.mode == "plugged"


def test_a_failing_power_call_is_logged_and_counts_as_plugged_in(caplog):
    def boom() -> bool | None:
        raise OSError("no power status")

    k = KeepAwake(platform="win32", state_call=lambda _flags: None, power_call=boom)
    with caplog.at_level("WARNING", logger="kickoff.maintenance"):
        assert k.wanted("plugged", window_open=False) is True
    assert any("how the computer is powered" in r.message for r in caplog.records)


def test_elsewhere_nothing_is_held_and_the_status_says_so():
    k = KeepAwake(platform="linux", power_call=lambda: True)
    k.set(k.wanted("plugged", window_open=False))
    assert k.held is False and k.status()["supported"] is False


def test_the_housekeeping_tick_follows_the_switch_and_unplugging(tmp_path: Path):
    calls: list[int] = []
    power = {"plugged": True}
    mode = {"value": "plugged"}
    m = Maintenance(
        data_dir=tmp_path / "data", backup_dir=tmp_path / "b", keep=7, window_open=lambda: False, backups_enabled=lambda: False,
        clock=lambda: NOW, awake=KeepAwake(platform="win32", state_call=calls.append, power_call=lambda: power["plugged"]), awake_mode=lambda: mode["value"],
    )
    asyncio.run(m.tick())
    assert m.awake.held and calls == [ES_CONTINUOUS | ES_SYSTEM_REQUIRED]
    power["plugged"] = False
    asyncio.run(m.tick())
    assert not m.awake.held and calls[-1] == ES_CONTINUOUS
    status = m.status()["keepAwake"]
    assert status == {"supported": True, "holding": False, "mode": "plugged", "pluggedIn": False, "reason": "on battery"}
    power["plugged"] = True
    mode["value"] = "off"
    asyncio.run(m.tick())
    assert not m.awake.held


def test_the_switch_defaults_to_plugged_and_refuses_other_values(client: TestClient):
    assert Prefs().keepAwake == "plugged"
    assert client.get("/api/settings").json()["data"]["prefs"]["keepAwake"] == "plugged"
    saved = client.put("/api/settings", json={"keepAwake": "games"}).json()
    assert saved["errors"] == [] and saved["data"]["prefs"]["keepAwake"] == "games"
    assert client.put("/api/settings", json={"keepAwake": "always"}).status_code == 422


def test_settings_and_the_status_page_say_what_it_is_doing(client: TestClient):
    housekeeping = client.get("/api/settings").json()["data"]["housekeeping"]
    assert set(housekeeping["keepAwake"]) == {"supported", "holding", "mode", "pluggedIn", "reason"}
    check = next(c for c in client.get("/api/health").json()["data"]["checks"] if c["name"] == "keep awake")
    assert check["status"] == "ok" and check["detail"]
