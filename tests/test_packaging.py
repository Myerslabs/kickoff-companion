"""Public release Phase 4: one set of pins everywhere. pyproject.toml (what uv reads) and the plain-pip
files carry the same versions, uv.lock locks those versions, and the start scripts exist for every
system with the line endings their shells need."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def pins(path: Path) -> dict[str, str]:
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line and "==" in line:
            name, version = line.split("==", 1)
            out[re.sub(r"\[.*\]", "", name).strip().lower()] = version.strip()
    return out


def project() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def listed(entries: list[str]) -> dict[str, str]:
    out = {}
    for entry in entries:
        name, version = entry.split("==", 1)
        out[re.sub(r"\[.*\]", "", name).strip().lower()] = version.strip()
    return out


def test_pyproject_and_requirements_pin_the_same_versions():
    runtime = listed(project()["project"]["dependencies"])
    dev = listed(project()["dependency-groups"]["dev"])
    pip_runtime = pins(ROOT / "requirements.txt")
    assert {k: v for k, v in pip_runtime.items() if k not in dev} == runtime
    assert {**pins(ROOT / "requirements-dev.txt"), **{k: v for k, v in pip_runtime.items() if k in dev}} == dev


def test_the_lock_holds_every_pinned_version():
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    locked = {p["name"].lower(): p.get("version") for p in lock["package"]}
    groups = project()["dependency-groups"]
    wanted = {**listed(project()["project"]["dependencies"]), **listed(groups["dev"]), **listed(groups["build"])}
    for name, version in wanted.items():
        assert locked.get(name) == version, f"uv.lock has {name} {locked.get(name)}, pyproject pins {version}: run `uv lock`"


def test_python_version_is_supported():
    version = (ROOT / ".python-version").read_text(encoding="utf-8").strip()
    major, minor = (int(x) for x in version.split(".")[:2])
    assert (major, minor) >= (3, 12) and project()["project"]["requires-python"] == ">=3.12"


def test_start_scripts_for_every_system():
    shell = (ROOT / "start.sh").read_bytes()
    assert shell.startswith(b"#!/usr/bin/env bash\n") and b"\r\n" not in shell, "start.sh needs LF line endings for bash"
    text = shell.decode("utf-8")
    assert "--service" in text and "uv\" sync --frozen" in text.replace("$UV", "uv") and "exec \"$PYTHON\" -m app" in text
    ps = (ROOT / "start.ps1").read_text(encoding="utf-8")
    assert "sync --frozen" in ps and "-Tray" in ps and "tools\\tray.ps1" in ps
    assert not (ROOT / "start-gameday.ps1").exists()


def test_the_build_group_matches_its_requirements_file():
    """Public release Phase 10: PyInstaller lives in its own group, so neither users nor the test runs install it."""
    build = listed(project()["dependency-groups"]["build"])
    assert "pyinstaller" in build and pins(ROOT / "requirements-build.txt") == build
    assert "pyinstaller" not in listed(project()["project"]["dependencies"]) and "pyinstaller" not in listed(project()["dependency-groups"]["dev"])
