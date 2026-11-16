"""Public release Phase 8: the package a new user sees, Windows only since ENH-26. The double-click launcher starts the
script, the script installs uv on a first start by hand only (never at login), the app says where it comes from with a link to copy
and credits CFBD, and the README, LICENSE and NOTICE agree on the publisher and the repository."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from app import DATA_CREDIT, PUBLISHER, REPO_URL

ROOT = Path(__file__).resolve().parent.parent


def read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_the_double_click_launcher_runs_the_start_script():
    cmd = (ROOT / "Kickoff Companion.cmd").read_bytes()
    assert b"\r\n" in cmd, "a Windows batch file runs reliably only with CRLF"
    assert b'powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*' in cmd and b'cd /d "%~dp0"' in cmd
    assert "eol=crlf" in read(".gitattributes")


def _working_bash() -> bool:
    """A bash that runs: Windows may have only the WSL stub, which prints a message and fails."""
    if shutil.which("bash") is None:
        return False
    try:
        probe = subprocess.run(["bash", "-c", "echo ok"], capture_output=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return probe.returncode == 0 and probe.stdout.strip() == b"ok"


def test_uv_is_installed_on_a_first_start_by_hand_only():
    ps1 = read("start.ps1")
    assert "if (-not $uv -and -not (Test-Path -LiteralPath $python) -and -not $Login)" in ps1
    assert "Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression" in ps1


def test_the_app_says_where_it_comes_from_and_credits_cfbd(client: TestClient):
    about = client.get("/api/settings").json()["data"]["about"]
    assert about["publisher"] == PUBLISHER == "Myers Labs" and about["repoUrl"] == REPO_URL and about["dataCredit"] == DATA_CREDIT
    status = client.get("/status").text
    assert REPO_URL in status and "Data provided by CollegeFootballData.com" in status and "free from Myers Labs" in status
    settings_js = read("static/js/views/settings.js")
    assert f'const REPO_URL = "{REPO_URL}"' in settings_js and "Copy the link" in settings_js and "available for free from" in settings_js


def test_readme_license_and_notice_agree():
    readme, license_text, notice = read("README.md"), read("LICENSE"), read("NOTICE")
    assert REPO_URL in readme and "Available for free from Myers Labs" in readme
    assert "`Kickoff Companion.cmd`" in readme
    assert license_text.startswith("MIT License") and "Copyright (c) 2026 Myers Labs" in license_text
    assert "Data provided by CollegeFootballData.com" in notice and "Not affiliated" in notice and "OFL.txt" in notice
    links = re.findall(r"\]\(([^)#]+)\)", readme)
    for link in links:
        if not link.startswith("http"):
            assert (ROOT / link).exists(), link


def test_a_first_start_shows_its_progress_and_keeps_a_log():
    """0.11.1: a new computer's first start says what it is doing while uv fetches Python and the packages (it
    used to sit silent for minutes), finds uv where the installer was told to put it, and writes logs/start.log."""
    ps1 = read("start.ps1")
    assert "& $uv sync --frozen --no-dev" in ps1 and "Getting Python and the app's packages ready" in ps1
    assert '$env:UV_PYTHON_PREFERENCE = "only-managed"' in ps1  # never Windows' Store stub for python
    assert "sync --frozen --quiet --no-dev --inexact" in ps1
    assert 'Join-Path $logDir "start.log"' in ps1 and "STOPPED: $message" in ps1  # BUG-24: in LOG_DIR when .env moves it
    assert "$env:UV_INSTALL_DIR" in ps1 and "$env:XDG_BIN_HOME" in ps1


def test_the_launcher_follows_data_dir_and_log_dir():
    """BUG-24: start.ps1 and the tray read DATA_DIR and LOG_DIR from .env, as the server does, so an update that changed
    the packages still runs uv sync and the tray's failure window, Show the log and the tray mode read the right place."""
    for name in ("start.ps1", "tools/tray.ps1"):
        ps1 = read(name)
        assert 'Resolve-Folder "DATA_DIR" "data"' in ps1 and 'Resolve-Folder "LOG_DIR" "logs"' in ps1, name
        assert "[Environment]::ExpandEnvironmentVariables" in ps1, name
        assert 'Join-Path $dataDir "update-sync.json"' in ps1, name
    assert 'Join-Path $dataDir "settings.json"' in read("start.ps1")
    tray = read("tools/tray.ps1")
    assert 'Join-Path $logDir "app.log"' in tray and 'Join-Path $dataDir "startup-failure.json"' in tray


def test_data_dir_and_log_dir_expand_environment_variables(monkeypatch, tmp_path):
    """BUG-24: DATA_DIR=%LOCALAPPDATA%\\Gators\\data in .env means that folder, not a folder of that name."""
    from app.config import Settings

    monkeypatch.setenv("GATORS_TEST_HOME", str(tmp_path))
    settings = Settings(_env_file=None, data_dir="%GATORS_TEST_HOME%/data", log_dir="$GATORS_TEST_HOME/logs")
    assert settings.data_dir == tmp_path / "data" and settings.log_dir == tmp_path / "logs"


def test_settings_saved_by_notepad_still_load(tmp_path):
    from app.services.prefs import PrefsStore

    (tmp_path / "settings.json").write_bytes(b'\xef\xbb\xbf{"openBrowser": "never", "theme": "light"}')
    store = PrefsStore(tmp_path)
    assert store.error is None and store.prefs.openBrowser == "never" and store.prefs.theme == "light"
