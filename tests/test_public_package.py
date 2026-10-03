"""Public release Phase 8: the package a new user sees. The double-click launchers start the same scripts, the scripts
install uv on a first start by hand only (never at login), the app says where it comes from with a link to copy
and credits CFBD, and the README, LICENSE and NOTICE agree on the publisher and the repository."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import DATA_CREDIT, PUBLISHER, REPO_URL

ROOT = Path(__file__).resolve().parent.parent


def read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_every_system_has_a_double_click_launcher_that_runs_the_start_script():
    cmd = (ROOT / "Kickoff Companion.cmd").read_bytes()
    assert b"\r\n" in cmd, "a Windows batch file runs reliably only with CRLF"
    assert b'powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*' in cmd and b'cd /d "%~dp0"' in cmd
    mac = read("Kickoff Companion.command")
    assert mac.startswith("#!/bin/bash") and 'exec ./start.sh "$@"' in mac
    linux = read("Kickoff Companion.sh")
    assert linux.startswith("#!/usr/bin/env bash") and "konsole" in linux and 'exec ./start.sh "$@"' in linux
    assert "eol=crlf" in read(".gitattributes")


@pytest.mark.skipif(shutil.which("git") is None or not (ROOT / ".git").exists(), reason="no git checkout (a ZIP download)")
def test_the_unix_launchers_are_executable_in_git():
    out = subprocess.run(["git", "ls-files", "-s", "Kickoff Companion.command", "Kickoff Companion.sh", "start.sh"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    modes = {line.split("\t")[1]: line.split()[0] for line in out.splitlines()}
    assert modes == {"Kickoff Companion.command": "100755", "Kickoff Companion.sh": "100755", "start.sh": "100755"}


@pytest.mark.skipif(shutil.which("bash") is None, reason="no bash here")
def test_the_shell_scripts_parse():
    for name in ("start.sh", "Kickoff Companion.command", "Kickoff Companion.sh"):
        assert subprocess.run(["bash", "-n", name], cwd=ROOT, capture_output=True).returncode == 0, name  # relative: a Windows bash may not read drive paths


def test_uv_is_installed_on_a_first_start_by_hand_only():
    ps1 = read("start.ps1")
    assert "if (-not $uv -and -not (Test-Path -LiteralPath $python) -and -not $Login)" in ps1
    assert "Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression" in ps1
    sh = read("start.sh")
    assert 'if [ -z "$UV" ] && [ ! -x "$PYTHON" ] && [ "$SERVICE" -eq 0 ]; then' in sh
    assert "curl -LsSf https://astral.sh/uv/install.sh | sh" in sh and "wget -qO- https://astral.sh/uv/install.sh | sh" in sh


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
    for launcher in ("Kickoff Companion.cmd", "Kickoff Companion.command", "Kickoff Companion.sh"):
        assert f"`{launcher}`" in readme
    assert license_text.startswith("MIT License") and "Copyright (c) 2026 Myers Labs" in license_text
    assert "Data provided by CollegeFootballData.com" in notice and "Not affiliated" in notice and "OFL.txt" in notice
    links = re.findall(r"\]\(([^)#]+)\)", readme)
    for link in links:
        if not link.startswith("http"):
            assert (ROOT / link).exists(), link
