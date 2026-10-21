"""Freeze wave F6 (2026-10-21), the package and the other systems: the wheel's entry point and the installed roots, the
package metadata, Linux held awake through systemd-inhibit, npm's claude.cmd shim resolved to node and the script with
the prompt on stdin (B7), the launcher's package-install case, the build tool archiving a program already in place
(signed), and the workflows: the wheel built and checked on three systems, PyPI and SignPath dormant until set up, the
Linux program on the older base, every page checked on the three systems."""

from __future__ import annotations

import asyncio
import importlib.util
import os
import signal
import sys
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from app.maintenance import KeepAwake
from app.paths import INSTALL_MARKER, Roots
from app.services import notes_task
from app.services.launcher import Launcher
from app.services.notes_task import PROMPT_LEAD, NotesRunner
from tools.package import build

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "packaging" / "pypi" / "kickoff_companion"

SHIM = r"""@ECHO off
GOTO start
:find_dp0
SET dp0=%~dp0
EXIT /b
:start
SETLOCAL
CALL :find_dp0

IF EXIST "%dp0%\node.exe" (
  SET "_prog=%dp0%\node.exe"
) ELSE (
  SET "_prog=node"
  SET PATHEXT=%PATHEXT:;.JS;=;%
)

endLocal & goto #_undefined_# 2>NUL || title %COMSPEC% & "%_prog%"  "%dp0%\node_modules\@anthropic-ai\claude-code\cli.js" %*
"""


# --- the package: its roots, its entry point, its metadata ------------------------------------------------------------------


def test_the_installed_package_reads_its_folder_and_writes_to_app_data(tmp_path: Path):
    folder = tmp_path / "site-packages" / "kickoff_companion"
    (folder / "app").mkdir(parents=True)
    (folder / INSTALL_MARKER).write_text("the package's folder\n", encoding="utf-8")
    roots = Roots.resolve(frozen=False, project_folder=folder, system="win32", environ={"LOCALAPPDATA": str(tmp_path / "Local")}, home=tmp_path)
    assert roots.bundle == folder and roots.install == tmp_path / "Local" / "Kickoff Companion"
    assert roots.installed and not roots.packaged and not roots.portable and roots.program is None
    assert roots.describe()["installed"] is True and roots.describe()["install"] == str(roots.install)
    plain = Roots.resolve(frozen=False, project_folder=tmp_path / "checkout", system="win32", environ={}, home=tmp_path)
    assert plain.install == plain.bundle == tmp_path / "checkout" and not plain.installed and plain.describe()["installed"] is False
    assert (ENTRY / INSTALL_MARKER).is_file(), "the marker ships inside the package"


def test_the_entry_point_hands_over_to_the_app(monkeypatch):
    spec = importlib.util.spec_from_file_location("kickoff_companion_entry", ENTRY / "__init__.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    seen: list = []
    import app.cli

    monkeypatch.setattr(app.cli, "main", lambda argv=None: seen.append(argv) or 7)
    try:
        assert module.main(["--check"]) == 7 and seen == [["--check"]]
        assert sys.path[0] == str(ENTRY), "the package's own folder leads the path, so `import app` finds the app inside it"
    finally:
        while str(ENTRY) in sys.path:
            sys.path.remove(str(ENTRY))
    main_text = (ENTRY / "__main__.py").read_text(encoding="utf-8")
    assert "from kickoff_companion import main" in main_text and "raise SystemExit(main())" in main_text


def test_the_package_metadata_builds_one_package_from_the_checkout():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = data["project"]
    assert project["name"] == "kickoff-companion" and "version" in project["dynamic"] and project["readme"] == "README.md"
    assert project["scripts"] == {"kickoff-companion": "kickoff_companion:main"}
    assert data["build-system"]["build-backend"] == "hatchling.build" and data["build-system"]["requires"] == ["hatchling==1.27.0"]
    hatch = data["tool"]["hatch"]
    assert hatch["version"] == {"path": "app/__init__.py"}
    wheel = hatch["build"]["targets"]["wheel"]
    assert wheel["include"] == ["/packaging/pypi/kickoff_companion", "/app", "/static"], "anchored, so no other folder named app or static is swept in"
    assert wheel["sources"] == {"packaging/pypi": "", "app": "kickoff_companion/app", "static": "kickoff_companion/static"}
    assert wheel["force-include"] == {".env.example": "kickoff_companion/.env.example"}
    assert "**/__pycache__" in wheel["exclude"]
    assert data["tool"]["uv"]["package"] is False, "uv sync leaves the checkout as it was; uv build makes the wheel"
    assert project["urls"]["Repository"] == "https://github.com/Myerslabs/kickoff-companion"
    for name in ("__init__.py", "__main__.py", INSTALL_MARKER):
        assert (ENTRY / name).is_file()
    assert (ROOT / "LICENSE").is_file() and (ROOT / ".env.example").is_file()


# --- Linux held awake --------------------------------------------------------------------------------------------------------


def test_linux_with_systemd_is_held_awake_and_let_go_as_a_session(caplog):
    child = SimpleNamespace(pid=4242, waited=False, terminated=False)
    child.wait = lambda timeout=None: setattr(child, "waited", True)
    child.terminate = lambda: setattr(child, "terminated", True)
    ended: list = []
    awake = KeepAwake(platform="linux", spawn=lambda: child, has_inhibit=lambda: True, end=ended.append)
    assert awake.supported
    with caplog.at_level("INFO", logger="kickoff.maintenance"):
        awake.set(True)
        assert awake.held and ended == []
        awake.set(False)
    assert ended == [child] and child.waited and not child.terminated and not awake.held
    assert any("kept awake" in r.message for r in caplog.records) and any("may sleep" in r.message for r in caplog.records)
    without = KeepAwake(platform="linux", has_inhibit=lambda: False)
    with caplog.at_level("INFO", logger="kickoff.maintenance"):
        without.set(True)
        without.set(True)
    assert not without.supported and not without.held
    assert sum("without systemd-inhibit" in r.message for r in caplog.records) == 1


def test_ending_the_inhibit_child_signals_its_whole_session_and_falls_back(monkeypatch):
    sent: list = []
    monkeypatch.setattr(os, "killpg", lambda pid, sig: sent.append((pid, sig)), raising=False)
    awake = KeepAwake(platform="linux", has_inhibit=lambda: True)
    child = SimpleNamespace(pid=77, terminated=False)
    child.terminate = lambda: setattr(child, "terminated", True)
    awake._end_child(child)
    assert sent == [(77, signal.SIGTERM)] and not child.terminated

    def gone(pid, sig):
        raise ProcessLookupError(pid)

    monkeypatch.setattr(os, "killpg", gone, raising=False)
    awake._end_child(child)
    assert child.terminated, "a session already gone: the one process is ended the plain way"
    mac = KeepAwake(platform="darwin", spawn=lambda: None)
    other = SimpleNamespace(pid=78, terminated=False)
    other.terminate = lambda: setattr(other, "terminated", True)
    sent.clear()
    mac._end_child(other)
    assert other.terminated and sent == [], "caffeinate is one process"


# --- the claude.cmd shim and the prompt on stdin (B7) -------------------------------------------------------------------------


def test_npms_shim_resolves_to_node_and_the_script(tmp_path: Path, monkeypatch):
    shim = tmp_path / "claude.cmd"
    shim.write_text(SHIM, encoding="utf-8")
    script = tmp_path / "node_modules" / "@anthropic-ai" / "claude-code" / "cli.js"
    script.parent.mkdir(parents=True)
    script.write_text("// cli\n", encoding="utf-8")
    monkeypatch.setattr(notes_task.shutil, "which", lambda name: "/usr/bin/node" if name == "node" else None)
    assert NotesRunner.command_args(str(shim)) == ["/usr/bin/node", str(script)], "node from the path when none sits beside the shim"
    beside = tmp_path / "node.exe"
    beside.write_bytes(b"MZ")
    assert NotesRunner.command_args(str(shim)) == [str(beside), str(script)], "the node beside the shim first, as the shim itself does"
    monkeypatch.setattr(notes_task.shutil, "which", lambda name: None)
    beside.unlink()
    assert NotesRunner.command_args(str(shim)) == [str(shim)], "no node to be found: the shim runs as it is"
    script.unlink()
    assert NotesRunner.command_args(str(shim)) == [str(shim)], "the script gone: the shim as it is"
    plain = tmp_path / "claude.exe"
    plain.write_bytes(b"MZ")
    assert NotesRunner.command_args(str(plain)) == [str(plain)]
    odd = tmp_path / "other.cmd"
    odd.write_text("@echo off\r\nsomething else\r\n", encoding="utf-8")
    assert NotesRunner.command_args(str(odd)) == [str(odd)]


def test_the_notes_runner_sends_the_prompt_on_stdin(tmp_path: Path, monkeypatch):
    calls: list = []

    class FakeProcess:
        def __init__(self) -> None:
            self.returncode: int | None = None
            self.given: bytes | None = None
            self.killed = False

        async def communicate(self, input: bytes | None = None):
            self.given = input
            self.returncode = 0
            return None, None

        async def wait(self) -> int:
            return self.returncode or 0

        def kill(self) -> None:
            self.killed = True

    fake = FakeProcess()

    async def spawn(*args, **kwargs):
        calls.append((args, kwargs))
        return fake

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    runner = NotesRunner(tmp_path / "data", tmp_path / "logs", who=lambda: None, season=2026)
    runner.log_dir.mkdir(parents=True)  # start() makes it before a run
    runner.started_at = datetime.now(timezone.utc)
    tool = tmp_path / "claude.exe"
    tool.write_bytes(b"MZ")
    prompt = "Write the notes.\n" + "x" * 20000  # longer than a cmd.exe line could carry
    asyncio.run(runner._run(str(tool), prompt, 526000600))
    args, kwargs = calls[0]
    assert list(args[:3]) == [str(tool), "-p", PROMPT_LEAD] and prompt not in args and "--output-format" in args
    assert kwargs["stdin"] is asyncio.subprocess.PIPE and fake.given == prompt.encode("utf-8")
    assert runner.exit_code == 0 and not fake.killed and runner.finished_at is not None
    assert runner.error and "no usable notes" in runner.error, "the fake wrote no answer, and that is said plainly"
    season = (ROOT / "app" / "services" / "season_task.py").read_text(encoding="utf-8")
    assert "stdin=asyncio.subprocess.PIPE" in season and "communicate(batch.prompt.encode" in season and "NotesRunner.command_args(executable)" in season and "PROMPT_LEAD" in season


# --- the launcher, the build tool, the workflows, the docs -----------------------------------------------------------------


def test_the_package_install_offers_no_login_start(tmp_path: Path):
    launcher = Launcher(tmp_path, platform="win32", appdata=str(tmp_path / "Roaming"), installed=True)
    assert not launcher.supported and launcher.status()["installed"] is True
    assert "package install" in launcher.set_enabled(True)["error"]
    usual = Launcher(tmp_path, platform="win32", appdata=str(tmp_path / "Roaming"))
    assert usual.supported and usual.status()["installed"] is False


def test_the_build_tool_archives_a_program_already_in_place(tmp_path: Path, capsys):
    dist = tmp_path / "dist"
    program = build.program_path(dist)
    program.parent.mkdir(parents=True)
    program.write_bytes(b"MZ signed")
    (program.parent / "_internal").mkdir()
    (program.parent / "_internal" / "python3.dll").write_bytes(b"MZ")
    assert build.main(["--dist", str(dist), "--archive-only", "--no-smoke"]) == 0
    archives = [p for p in dist.iterdir() if p.name.startswith("KickoffCompanion-") and not p.name.endswith(".sha256")]
    assert len(archives) == 1 and (dist / f"{archives[0].name}.sha256").read_text(encoding="utf-8").endswith(f"  {archives[0].name}\n")
    assert program.read_bytes() == b"MZ signed", "the program in place is archived, never rebuilt"
    assert build.main(["--dist", str(tmp_path / "empty"), "--archive-only", "--no-smoke"]) == 1
    assert "--archive-only needs the built program" in capsys.readouterr().out


def test_the_release_workflow_builds_the_wheel_and_stays_dormant_until_set_up():
    release = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "os: [windows-latest, ubuntu-22.04, macos-latest]" in release, "the Linux program on the oldest Ubuntu GitHub runs"
    assert "uv build --out-dir dist" in release and "uvx --from dist/kickoff_companion-*.whl kickoff-companion --check" in release
    assert "pypa/gh-action-pypi-publish@release/v1" in release and "environment: pypi" in release and "id-token: write" in release
    assert "vars.PYPI_PUBLISH == 'true'" in release, "nothing is published until the owner has set PyPI up"
    assert "signpath/github-action-submit-signing-request@v1.1" in release and release.count("vars.SIGNPATH_ORGANIZATION_ID != ''") == 3
    assert "secrets.SIGNPATH_API_TOKEN" in release and "project-slug: kickoff-companion" in release
    assert "build.py --dist dist --no-archive" in release and "build.py --dist dist --archive-only" in release, "the archive is made from the folder as it ships, signed or not"
    tests = (ROOT / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
    assert "  pages:" in tests and "tools/page_check.py --interact --layout --rules --scroll" in tests and "--no-sandbox" in tests
    check = (ROOT / "tools" / "page_check.py").read_text(encoding="utf-8")
    assert '"--no-sandbox", action="store_true"' in check and 'extra=("--no-sandbox",) if args.no_sandbox else ()' in check


def test_the_docs_carry_the_uv_line_the_sequoia_steps_and_the_signing_policy():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "uvx kickoff-companion" in readme and "## Code signing policy" in readme and "SignPath Foundation" in readme and "Open Anyway" in readme
    setup = (ROOT / "docs" / "05-SETUP.md").read_text(encoding="utf-8")
    assert "uvx kickoff-companion" in setup and "Open Anyway" in setup and "systemd-inhibit" in setup
