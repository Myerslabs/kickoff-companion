"""Public release Phase 10: the packaged program. The two roots (the bundle and the install), the demo league's cache
key without source files, the pause before a double-clicked window closes, the launcher running the program itself,
the Settings and status facts about the files, and the build tooling's pure parts. Nothing here runs PyInstaller;
tools/package/build.py smoke-tests the real build on every system in the release workflow."""

from __future__ import annotations

import plistlib
import re
import shlex
from pathlib import Path

import pytest

from app.cli import pause_before_closing
from app.demo import upstream
from app.paths import PORTABLE_MARKER, Roots, app_data_dir, is_frozen
from app.services.launcher import Launcher, open_folder
from tools.package import build

ROOT = Path(__file__).resolve().parents[1]


def frozen_layout(tmp_path: Path) -> tuple[Path, Path]:
    """A packaged program's folder: the program beside its _internal bundle."""
    program = tmp_path / "KickoffCompanion" / "KickoffCompanion.exe"
    bundle = program.parent / "_internal"
    bundle.mkdir(parents=True)
    program.write_bytes(b"MZ")
    return program, bundle


class TestRoots:
    def test_a_checkout_uses_the_project_folder_for_both(self):
        roots = Roots.resolve(frozen=False)
        assert roots.bundle == roots.install == ROOT and roots.program is None and not roots.portable and not roots.packaged

    def test_the_packaged_program_reads_its_bundle_and_writes_to_app_data(self, tmp_path):
        program, bundle = frozen_layout(tmp_path)
        roots = Roots.resolve(frozen=True, bundle=bundle, executable=program, system="win32", environ={"LOCALAPPDATA": str(tmp_path / "Local")}, home=tmp_path)
        assert roots.bundle == bundle.resolve() and roots.install == tmp_path / "Local" / "Kickoff Companion"
        assert roots.program == program.resolve() and roots.packaged and not roots.portable
        described = roots.describe()
        assert described["packaged"] is True and described["portable"] is False
        assert described["install"] == str(roots.install) and described["bundle"] == str(bundle.resolve()) and described["program"] == str(program.resolve())

    def test_a_portable_marker_keeps_the_files_beside_the_program(self, tmp_path):
        program, bundle = frozen_layout(tmp_path)
        (program.parent / PORTABLE_MARKER).write_text("", encoding="utf-8")
        roots = Roots.resolve(frozen=True, bundle=bundle, executable=program, system="win32", environ={}, home=tmp_path)
        assert roots.install == program.parent.resolve() and roots.portable and roots.describe()["portable"] is True

    @pytest.mark.parametrize(
        "system, environ, expected",
        [
            ("win32", {"LOCALAPPDATA": "C:/Users/x/AppData/Local"}, Path("C:/Users/x/AppData/Local") / "Kickoff Companion"),
            ("win32", {}, Path("/home/x") / "AppData" / "Local" / "Kickoff Companion"),
            ("darwin", {}, Path("/home/x") / "Library" / "Application Support" / "Kickoff Companion"),
            ("linux", {"XDG_DATA_HOME": "/xdg"}, Path("/xdg") / "kickoff-companion"),
            ("linux", {}, Path("/home/x") / ".local" / "share" / "kickoff-companion"),
        ],
    )
    def test_app_data_folders_by_system(self, system, environ, expected):
        assert app_data_dir(system, environ, Path("/home/x")) == expected

    def test_is_frozen_needs_both_of_pyinstallers_marks(self):
        class Plain:
            pass

        class Frozen:
            frozen = True
            _MEIPASS = "somewhere"

        class HalfFrozen:
            frozen = True

        assert not is_frozen(Plain()) and is_frozen(Frozen()) and not is_frozen(HalfFrozen())


class TestDemoLeagueKey:
    def test_the_checkout_hashes_its_generator_sources(self):
        folder = ROOT / "app" / "demo"
        value = upstream.source_hash(folder)
        assert re.fullmatch(r"[0-9a-f]{12}", value) and value == upstream.hash_sources(folder) == upstream.source_hash()

    def test_the_packaged_program_reads_the_hash_its_build_wrote(self, tmp_path):
        (tmp_path / upstream.SOURCE_HASH_FILE).write_text("0123456789ab\n", encoding="utf-8")
        assert upstream.hash_sources(tmp_path) is None and upstream.source_hash(tmp_path) == "0123456789ab"

    def test_no_sources_and_no_hash_file_is_a_clear_error(self, tmp_path):
        with pytest.raises(RuntimeError, match="demo-sources.sha1"):
            upstream.source_hash(tmp_path)
        (tmp_path / upstream.SOURCE_HASH_FILE).write_text("not a hash", encoding="utf-8")
        with pytest.raises(RuntimeError, match="does not hold"):
            upstream.source_hash(tmp_path)


class TestPauseBeforeClosing:
    def test_a_double_clicked_packaged_program_waits_after_a_failure(self):
        asked: list[str] = []
        assert pause_before_closing(4, packaged=True, system="win32", owners=1, ask=asked.append) is True
        assert len(asked) == 1 and "Enter" in asked[0]

    @pytest.mark.parametrize("code, packaged, system, owners", [(0, True, "win32", 1), (4, False, "win32", 1), (4, True, "linux", 1), (4, True, "darwin", 1), (4, True, "win32", 2)])
    def test_everything_else_closes_at_once(self, code, packaged, system, owners):
        assert pause_before_closing(code, packaged=packaged, system=system, owners=owners, ask=lambda prompt: pytest.fail("asked")) is False

    def test_a_closed_stdin_never_raises(self):
        def closed(prompt: str) -> None:
            raise EOFError

        assert pause_before_closing(2, packaged=True, system="win32", owners=1, ask=closed) is True


class TestLauncherRunsTheProgram:
    def test_windows_shortcuts_target_the_program_with_login(self, tmp_path):
        program, _ = frozen_layout(tmp_path)
        scripts: list[str] = []
        launcher = Launcher(tmp_path / "appdata", runner=lambda args: scripts.append(args[0]) or (0, ""), platform="win32", appdata=str(tmp_path / "Roaming"), home=tmp_path, program=program)
        status = launcher.status()
        assert status["packaged"] is True and status["program"] == str(program) and status["tray"] is False
        assert status["script"] == str(program) and status["scriptExists"] is True
        assert launcher.set_enabled(True, tray=True).get("error") is None
        assert f"$s.TargetPath = '{program}'" in scripts[0] and "$s.Arguments = '--login'" in scripts[0] and f"$s.WorkingDirectory = '{program.parent}'" in scripts[0]
        assert "start.ps1" not in scripts[0] and "-Tray" not in scripts[0] and "powershell.exe" not in scripts[0]
        assert launcher.desktop_shortcut()["created"] is True and "$s.Arguments = ''" in scripts[1]

    def test_linux_service_and_launcher_run_the_program(self, tmp_path):
        program, bundle = frozen_layout(tmp_path)
        (bundle / "static" / "icons").mkdir(parents=True)
        calls: list[list[str]] = []
        launcher = Launcher(tmp_path / "share", runner=lambda args: calls.append(args) or (0, ""), platform="linux", home=tmp_path / "home", program=program, static_dir=bundle / "static")
        quoted = shlex.quote(str(program))
        assert f"ExecStart={quoted} --login" in launcher.unit_text() and "start.sh" not in launcher.unit_text()
        entry = launcher.desktop_entry()
        assert f"Exec={quoted}\n" in entry and f"Icon={bundle / 'static' / 'icons' / 'icon-192.png'}" in entry and f"Path={program.parent}\n" in entry
        assert launcher.set_enabled(True).get("error") is None and ["systemctl", "--user", "enable", "kickoff-companion.service"] in calls
        assert launcher.tray_supported is False

    def test_mac_agent_and_command_run_the_program(self, tmp_path):
        program, _ = frozen_layout(tmp_path)
        home = tmp_path / "home"
        launcher = Launcher(tmp_path / "support", runner=lambda args: (1, "never called"), platform="darwin", home=home, program=program)
        plist = plistlib.loads(launcher.agent_plist())
        assert plist["ProgramArguments"] == [str(program), "--login"]
        assert launcher.desktop_shortcut()["created"] is True
        assert (home / "Desktop" / "Kickoff Companion.command").read_text(encoding="utf-8") == f"#!/bin/bash\nexec {shlex.quote(str(program))}\n"

    def test_a_missing_program_is_reported_plainly(self, tmp_path):
        launcher = Launcher(tmp_path, runner=lambda args: (0, ""), platform="win32", appdata=str(tmp_path), program=tmp_path / "gone.exe")
        assert launcher.set_enabled(True)["error"] == "gone.exe is missing"
        assert launcher.desktop_shortcut()["error"] == "gone.exe is missing"

    def test_a_checkout_still_runs_its_start_scripts(self, tmp_path):
        (tmp_path / "start.ps1").write_text("", encoding="utf-8")
        scripts: list[str] = []
        launcher = Launcher(tmp_path, runner=lambda args: scripts.append(args[0]) or (0, ""), platform="win32", appdata=str(tmp_path))
        assert launcher.status()["packaged"] is False and launcher.tray_supported is True
        assert launcher.set_enabled(True, tray=True).get("error") is None and "$s.TargetPath = 'powershell.exe'" in scripts[0] and "-Tray -Login" in scripts[0]


class TestOpenFolder:
    def test_opens_with_the_systems_command(self, tmp_path):
        calls: list[list[str]] = []
        assert open_folder(tmp_path, system="linux", runner=calls.append) is None and calls[-1] == ["xdg-open", str(tmp_path)]
        assert open_folder(tmp_path, system="darwin", runner=calls.append) is None and calls[-1] == ["open", str(tmp_path)]
        assert open_folder(tmp_path, system="win32", runner=calls.append) is None and calls[-1] == [str(tmp_path)]

    def test_a_missing_folder_is_an_error_not_a_window(self, tmp_path):
        error = open_folder(tmp_path / "nope", system="win32", runner=lambda args: pytest.fail("opened"))
        assert error is not None and "does not exist" in error


def test_settings_and_health_say_where_the_files_are(client):
    files = client.get("/api/settings").json()["data"]["files"]
    assert files["packaged"] is False and files["portable"] is False and files["program"] is None
    assert files["install"] == str(ROOT) and files["bundle"] == str(ROOT) and files["dataDir"] and files["logDir"]
    health = client.get("/api/health").json()["data"]["server"]["files"]
    assert health["install"] == str(ROOT) and health["packaged"] is False


def test_the_folder_opens_only_from_the_server_computer(client, monkeypatch):
    refused = client.post("/api/settings/open-folder")
    assert refused.status_code == 403 and refused.json()["errors"][0]["code"] == "not_here"
    opened: list[Path] = []
    monkeypatch.setattr("app.api.settings._on_server_computer", lambda request: True)
    monkeypatch.setattr("app.api.settings.open_folder", lambda folder: opened.append(Path(folder)))
    assert client.post("/api/settings/open-folder").status_code == 200 and opened == [ROOT]
    files = client.get("/api/settings").json()["data"]["files"]
    assert client.post("/api/settings/open-folder?which=data").status_code == 200 and opened[-1] == Path(files["dataDir"])
    assert client.post("/api/settings/open-folder?which=logs").status_code == 200 and opened[-1] == Path(files["logDir"])
    assert client.post("/api/settings/open-folder?which=secrets").status_code == 400
    monkeypatch.setattr("app.api.settings.open_folder", lambda folder: "no file manager here")
    failed = client.post("/api/settings/open-folder")
    assert failed.status_code == 500 and failed.json()["errors"][0]["message"] == "no file manager here"


class TestBuildTooling:
    def test_archive_names_by_system(self):
        assert build.archive_name("0.12.0", "win32", "AMD64") == "KickoffCompanion-0.12.0-windows-x64"
        assert build.archive_name("0.12.0", "darwin", "arm64") == "KickoffCompanion-0.12.0-macos-arm64"
        assert build.archive_name("0.12.0", "linux", "x86_64") == "KickoffCompanion-0.12.0-linux-x64"

    def test_the_version_resource_carries_the_version(self):
        text = build.version_info_text("0.12.0")
        assert "filevers=(0, 12, 0, 0)" in text and "StringStruct('ProductVersion', '0.12.0')" in text and "Myers Labs" in text
        assert build.version_tuple("1.2") == (1, 2, 0, 0) and build.version_tuple("0.12.0") == (0, 12, 0, 0)

    def test_the_icon_is_a_png_in_an_ico_wrapper(self):
        png = (ROOT / "static" / "icons" / "icon-192.png").read_bytes()
        ico = build.ico_bytes(png)
        assert ico[:6] == b"\x00\x00\x01\x00\x01\x00" and ico[6] == 192 and ico[7] == 192 and ico[22:] == png
        with pytest.raises(ValueError):
            build.png_size(b"not a png at all, really not")

    def test_staging_writes_the_hash_the_program_reads(self, tmp_path):
        files = build.write_staging(tmp_path, ROOT / "static")
        assert files["hash"].read_text(encoding="utf-8").strip() == upstream.source_hash()
        assert files["icon"].is_file() and "VSVersionInfo" in files["version"].read_text(encoding="utf-8")
        assert upstream.source_hash(tmp_path) == upstream.source_hash()  # a bundle with the hash file alone keys the league the same way

    def test_the_spec_bundles_what_the_program_reads(self):
        spec = (ROOT / "tools" / "package" / "kickoff.spec").read_text(encoding="utf-8")
        for needed in ('"static"', '".env.example"', '"radio_stations.json"', '"demo-sources.sha1"', 'collect_data_files("tzdata")', 'hiddenimports=["app.main"]', "upx=False", "console=True"):
            assert needed in spec, needed
        assert "onefile" not in spec.lower()

    def test_the_release_workflow_builds_on_every_system_and_attaches_the_archives(self):
        text = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        for needed in ("windows-latest", "ubuntu-latest", "macos-latest", "tools/package/build.py", "gh release upload", "--group build", "github.event.repository.name == 'kickoff-companion'", "app/__init__.py says"):
            assert needed in text, needed

    def test_build_files_are_ignored_and_the_entry_runs_main_then_pauses(self):
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        assert "tools/package/out/" in ignore and "/dist/" in ignore
        entry = (ROOT / "tools" / "package" / "kickoff.py").read_text(encoding="utf-8")
        assert "from app.cli import main, pause_before_closing" in entry and "pause_before_closing(code)" in entry
