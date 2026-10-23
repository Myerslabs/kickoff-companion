"""The tray on by default (owner 2026-10-23, the testers' Friday): on Windows every start goes behind the tray icon unless
Tray mode is switched off in Settings. The setting is "auto" (each system's default), "on" or "off"; a settings file from
before keeps the old switch's true or false, and false, the old default nobody chose, now reads as the new default. The
start script, the shortcuts and the packaged program's double-click all follow it."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.paths import Roots
from app.services.prefs import Prefs, PrefsError, PrefsStore, tray_wanted
from tools.package import kickoff

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
    monkeypatch.setattr(launcher, "system", "windows")
    monkeypatch.setattr(launcher, "set_enabled", lambda enabled, tray=False: calls.append(tray) or launcher.status())
    assert client.put("/api/settings", json={"autoStart": True}).status_code == 200
    assert client.put("/api/settings", json={"trayMode": "off"}).status_code == 200
    assert calls == [True, False], "start at login behind the tray by default, in a window once switched off"


def roots(tmp_path: Path, *, program: bool = True, tray: bool = True) -> Roots:
    bundle = tmp_path / "bundle"
    (bundle / "tools").mkdir(parents=True)
    if tray:
        (bundle / "tools" / "tray.ps1").write_text("# tray", encoding="utf-8")
    install = tmp_path / "install"
    (install / "data").mkdir(parents=True)
    return Roots(bundle=bundle, install=install, program=(tmp_path / "KickoffCompanion.exe") if program else None, portable=False)


def test_a_double_click_hands_the_program_to_the_tray(tmp_path: Path):
    started: list[list[str]] = []
    here = roots(tmp_path)
    assert kickoff.tray_handoff([], {}, here, "windows", lambda command, **_: started.append(command)) is True
    command = started[0]
    assert command[0] == "powershell.exe" and str(here.bundle / "tools" / "tray.ps1") in command
    assert command[command.index("-Program") + 1] == str(here.program) and command[command.index("-Root") + 1] == str(here.install)


def test_the_window_stays_when_it_should(tmp_path: Path):
    started: list[list[str]] = []

    def popen(command, **_):
        started.append(command)

    here = roots(tmp_path)
    assert kickoff.tray_handoff(["--check"], {}, here, "windows", popen) is False, "started with options: the window"
    assert kickoff.tray_handoff([], {"KICKOFF_NO_PAUSE": "1"}, here, "windows", popen) is False, "the tray started it: never again"
    assert kickoff.tray_handoff([], {}, here, "linux", popen) is False
    assert kickoff.tray_handoff([], {}, roots(tmp_path / "a", program=False), "windows", popen) is False, "a checkout: start.ps1 decides"
    assert kickoff.tray_handoff([], {}, roots(tmp_path / "b", tray=False), "windows", popen) is False, "no tray script: the window"
    PrefsStore(here.install / "data").update({"trayMode": "off"})
    assert kickoff.tray_handoff([], {}, here, "windows", popen) is False, "switched off in Settings"
    assert started == []

    def broken(command, **_):
        raise OSError("no powershell")

    other = roots(tmp_path / "c")
    assert kickoff.tray_handoff([], {}, other, "windows", broken) is False, "a tray that will not start leaves the window"


def test_the_start_script_and_settings_say_the_same():
    script = (ROOT / "start.ps1").read_text(encoding="utf-8")
    assert "$Tray = $true" in script and '$saved.trayMode -is [string] -and $saved.trayMode -eq "off"' in script
    settings = (ROOT / "static" / "js" / "views" / "settings.js").read_text(encoding="utf-8")
    assert 'toggle(p.trayMode !== "off", (value) => change({ trayMode: value ? "on" : "off" }' in settings
    assert "On by default" in settings
