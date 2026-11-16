"""The tray on by default (owner 2026-10-23, the testers' Friday): on Windows every start goes behind the tray icon unless
Tray mode is switched off in Settings. The setting is "auto" (each system's default), "on" or "off"; a settings file from
before keeps the old switch's true or false, and false, the old default nobody chose, now reads as the new default. The
start script and the shortcuts follow it."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.services.prefs import Prefs, PrefsError, PrefsStore, tray_wanted

ROOT = Path(__file__).resolve().parents[1]


def test_the_default_is_the_systems_and_only_off_keeps_the_window():
    assert Prefs().trayMode == "auto"
    assert tray_wanted("auto", "windows") and tray_wanted("on", "windows")
    assert not tray_wanted("off", "windows")
    assert not tray_wanted("auto", "linux") and not tray_wanted("on", "darwin"), "the tray is Windows only"


@pytest.mark.parametrize(("saved", "read"), [(False, "auto"), (True, "on"), ("off", "off"), ("on", "on"), ("auto", "auto")])
def test_a_file_from_before_reads_as_the_new_default(tmp_path: Path, saved, read):
    (tmp_path / "settings.json").write_text(json.dumps({"trayMode": saved, "theme": "dark"}), encoding="utf-8")
    store = PrefsStore(tmp_path)
    assert store.prefs.trayMode == read and store.error is None


def test_a_bad_word_is_refused_and_an_old_page_still_switches(tmp_path: Path):
    store = PrefsStore(tmp_path)
    with pytest.raises(PrefsError):
        store.update({"trayMode": "sometimes"})
    assert store.update({"trayMode": False}).trayMode == "off", "a page opened before today sends the old false"
    assert store.update({"trayMode": True}).trayMode == "on"
    assert json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))["trayMode"] == "on"


def test_the_shortcuts_follow_the_setting(app, client: TestClient, monkeypatch):
    launcher = app.state.launcher
    calls: list[bool] = []
    monkeypatch.setattr(launcher, "set_enabled", lambda enabled, tray=False: calls.append(tray) or launcher.status())
    assert client.put("/api/settings", json={"autoStart": True}).status_code == 200
    assert client.put("/api/settings", json={"trayMode": "off"}).status_code == 200
    assert calls == [True, False], "start at login behind the tray by default, in a window once switched off"


def test_the_start_script_and_settings_say_the_same():
    script = (ROOT / "start.ps1").read_text(encoding="utf-8")
    assert "$Tray = $true" in script and '$saved.trayMode -is [string] -and $saved.trayMode -eq "off"' in script
    settings = (ROOT / "static" / "js" / "views" / "settings.js").read_text(encoding="utf-8")
    assert 'toggle(p.trayMode !== "off", (value) => change({ trayMode: value ? "on" : "off" }' in settings
    assert "On by default" in settings
