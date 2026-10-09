"""Start at login and a double-click icon (Phase 9, owner direction 2026-09-23; every platform since
public release Phase 4). What each system gets:

- Windows: a shortcut in the user's Startup folder and one on the Desktop, both running `start.ps1`
  (with -Tray for the tray icon). Shortcuts are written through PowerShell's WScript.Shell, the one
  supported way to make a .lnk without extra packages.
- Linux (the Steam Deck included): a systemd user service, `~/.config/systemd/user/kickoff-companion.service`,
  enabled so it starts when the user logs in, and a `.desktop` launcher on the Desktop and in the app
  menu (Steam's "Add a Non-Steam Game" lists it from there).
- macOS: a LaunchAgent, `~/Library/LaunchAgents/com.kickoff-companion.server.plist`, loaded at login,
  and a `Kickoff Companion.command` on the Desktop.

Switching on writes the file and registers it; it never starts a second server now (the one running
is already up). Switching off unregisters and removes it. The tray icon is Windows only. Every system
command goes through `runner`, so tests and demo mode never touch the real system.

The packaged program (public release Phase 10, `program` set): shortcuts, the service and the agent run the
program itself with `--login` instead of a start script. Phase 16 wave 3: on Windows the tray switch is offered there
too; its shortcuts run the bundled tools\tray.ps1 with -Program, which starts the program hidden behind the icon."""

from __future__ import annotations

import logging
import os
import plistlib
import shlex
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

log = logging.getLogger("kickoff.launcher")

APP_TITLE = "Kickoff Companion"
SHORTCUT_NAME = "Kickoff Companion.lnk"
# Startup shortcut names from earlier releases: an install that has one still counts as switched on, and
# switching on or off replaces or removes it. None today (the one install with an old name moved, 2026-10-03).
LEGACY_SHORTCUT_NAMES: tuple[str, ...] = ()
DESCRIPTION = "Kickoff Companion server"
SCRIPT_NAME = "start.ps1"  # Windows
SHELL_SCRIPT = "start.sh"  # Linux and macOS
UNIT_NAME = "kickoff-companion.service"
DESKTOP_FILE = "kickoff-companion.desktop"
AGENT_LABEL = "com.kickoff-companion.server"
COMMAND_FILE = "Kickoff Companion.command"
Runner = Callable[[list[str]], tuple[int, str]]


def run_command(args: list[str]) -> tuple[int, str]:
    """Run a system command; (exit code, output). Never raises."""
    try:
        done = subprocess.run(args, capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)
    return done.returncode, (done.stdout + done.stderr).strip()


DESKTOP_RESERVED = frozenset(" \t\n\"'\\><~|&;$*?#()`")  # Desktop Entry spec: an Exec argument with one of these is quoted


def desktop_arg(value: str) -> str:
    """One argument of a .desktop Exec= line. The Desktop Entry spec quotes with double quotes only (not the shell's
    single quotes), escapes " ` $ and \\ inside them, then doubles every backslash as any string value does; % starts a
    field code, so a literal one is doubled."""
    value = value.replace("%", "%%")
    if not DESKTOP_RESERVED.intersection(value):
        return value
    quoted = "".join("\\" + c if c in '"`$\\' else c for c in value)
    return '"' + quoted.replace("\\", "\\\\") + '"'


def open_folder(path: Path, system: str = sys.platform, runner: Callable[[list[str]], Any] | None = None) -> str | None:
    """Show `path` in the system's file manager (the Open button in Settings, public release Phase 10). Returns an
    error text, or None. `runner` stands in for the system call in tests."""
    path = Path(path)
    if not path.is_dir():
        return f"{path} does not exist yet"
    try:
        if system.startswith("win"):
            if runner is not None:
                runner([str(path)])
            else:
                os.startfile(str(path))  # type: ignore[attr-defined]  # the install folder, chosen by this program
        else:
            args = ["open" if system == "darwin" else "xdg-open", str(path)]
            if runner is not None:
                runner(args)
            else:
                subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as exc:
        return f"could not open {path}: {exc}"
    return None


def _run_powershell(args: list[str]) -> tuple[int, str]:
    """Kept for callers that pass a PowerShell script as the only argument."""
    return run_command(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", *args])


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def system_of(platform: str) -> str:
    if platform.startswith("win"):
        return "windows"
    if platform == "darwin":
        return "mac"
    if platform.startswith("linux"):
        return "linux"
    return "other"


class Launcher:
    def __init__(
        self,
        project_root: Path,
        *,
        runner: Runner | None = None,
        platform: str = sys.platform,
        appdata: str | None = None,
        home: str | Path | None = None,
        program: str | Path | None = None,
        static_dir: str | Path | None = None,
        install_root: str | Path | None = None,
    ) -> None:
        self.project_root = Path(project_root)
        self.install_root = Path(install_root) if install_root else self.project_root  # .env, data and logs (the tray's -Root)
        self.program = Path(program) if program else None  # the packaged program, which starts itself
        self.static_dir = Path(static_dir) if static_dir else self.project_root / "static"  # the icon for the Linux launcher
        self.platform = platform
        self.system = system_of(platform)
        self.runner: Runner = runner or (_run_powershell if self.system == "windows" else run_command)
        self.appdata = appdata if appdata is not None else os.environ.get("APPDATA", "")
        self.home = Path(home) if home is not None else Path.home()

    # -- where things go ---------------------------------------------------------------------------------
    @property
    def supported(self) -> bool:
        if self.system == "windows":
            return bool(self.appdata)
        return self.system in ("linux", "mac")

    @property
    def tray_script(self) -> Path:
        """tools\tray.ps1: in the project folder, or bundled beside the program's static folder."""
        return (self.static_dir.parent if self.program else self.project_root) / "tools" / "tray.ps1"

    @property
    def tray_supported(self) -> bool:
        return self.system == "windows" and (self.program is None or self.tray_script.is_file())

    @property
    def script_path(self) -> Path:
        return self.project_root / (SCRIPT_NAME if self.system == "windows" else SHELL_SCRIPT)

    @property
    def launch_path(self) -> Path:
        """What a shortcut or service runs: the packaged program itself, else the start script."""
        return self.program or self.script_path

    def _missing(self) -> str:
        return f"{self.launch_path.name} is missing" + ("" if self.program else " from the project folder")

    def _service_command(self) -> str:
        """The login service's command line: the program itself, or start.sh in service mode."""
        if self.program:
            return f"{shlex.quote(str(self.program))} --login"
        return f"/bin/bash {shlex.quote(str(self.script_path))} --service"

    @property
    def method(self) -> str | None:
        return {"windows": "a shortcut in the Windows Startup folder", "linux": "a systemd user service", "mac": "a LaunchAgent"}.get(self.system)

    @property
    def startup_folder(self) -> Path | None:
        if self.system != "windows" or not self.appdata:
            return None
        return Path(self.appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"

    @property
    def shortcut_path(self) -> Path | None:
        """The file that makes the server start at login."""
        if self.system == "windows":
            folder = self.startup_folder
            return folder / SHORTCUT_NAME if folder else None
        if self.system == "linux":
            return self.home / ".config" / "systemd" / "user" / UNIT_NAME
        if self.system == "mac":
            return self.home / "Library" / "LaunchAgents" / f"{AGENT_LABEL}.plist"
        return None

    @property
    def desktop_path(self) -> Path:
        if self.system == "windows":
            return Path(os.environ.get("USERPROFILE", "") or self.home) / "Desktop" / SHORTCUT_NAME
        if self.system == "mac":
            return self.home / "Desktop" / COMMAND_FILE
        return self.home / "Desktop" / DESKTOP_FILE

    def _legacy(self, folder: Path | None) -> list[Path]:
        return [folder / name for name in LEGACY_SHORTCUT_NAMES if folder and (folder / name).is_file()]

    def _drop_legacy(self, folder: Path | None) -> None:
        for old in self._legacy(folder):
            try:
                old.unlink()
                log.info("Removed the old shortcut %s", old)
            except OSError as exc:
                log.warning("Could not remove the old shortcut %s: %s", old, exc)

    # -- status ------------------------------------------------------------------------------------------
    def is_enabled(self) -> bool:
        path = self.shortcut_path
        return bool(path and (path.is_file() or self._legacy(self.startup_folder)))

    def status(self) -> dict[str, Any]:
        return {
            "supported": self.supported,
            "system": self.system,
            "method": self.method,
            "tray": self.tray_supported,
            "enabled": self.is_enabled(),
            "shortcut": str(self.shortcut_path) if self.shortcut_path else None,
            "script": str(self.launch_path),
            "scriptExists": self.launch_path.is_file(),
            "packaged": self.program is not None,  # public release Phase 10: the program starts itself
            "program": str(self.program) if self.program else None,
        }

    # -- start at login ----------------------------------------------------------------------------------
    def set_enabled(self, enabled: bool, *, tray: bool = False) -> dict[str, Any]:
        """Switch start at login on or off. Returns the status plus an `error` when it failed."""
        if not self.supported:
            return {**self.status(), "error": "start at login is not available on this system"}
        if enabled and not self.launch_path.is_file():
            return {**self.status(), "error": self._missing()}
        if self.system == "windows":
            error = self._windows_login(enabled, tray)
        elif self.system == "linux":
            error = self._linux_login(enabled)
        else:
            error = self._mac_login(enabled)
        if error:
            return {**self.status(), "error": error}
        log.info("Start at login switched %s (%s)", "on" if enabled else "off", self.shortcut_path)
        return self.status()

    def _windows_login(self, enabled: bool, tray: bool) -> str | None:
        path = self.shortcut_path
        assert path is not None
        if not enabled:
            try:
                for old in [path, *self._legacy(self.startup_folder)]:
                    if old.is_file():
                        old.unlink()
            except OSError as exc:
                return f"could not remove the Startup shortcut: {exc}"
            return None
        code, output = self.runner([self._lnk_script(path, tray, login=True)])
        if code != 0:
            return f"could not create the Startup shortcut: {output or 'PowerShell failed'}"
        self._drop_legacy(self.startup_folder)
        return None

    def _lnk_script(self, target: Path, tray: bool, *, login: bool = False) -> str:
        if self.program and tray and self.tray_scripts_ok():  # Phase 16 wave 3: the program behind the tray icon
            exe = "powershell.exe"
            arguments = f"-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File \"{self.tray_script}\" -Program \"{self.program}\" -Root \"{self.install_root}\"" + (" -Login" if login else "")
            workdir = str(self.install_root)
        elif self.program:  # the packaged program runs itself
            exe, arguments, workdir = str(self.program), ("--login" if login else ""), str(self.program.parent)
        else:
            exe = "powershell.exe"
            arguments = f"-NoExit -ExecutionPolicy Bypass -File \"{self.script_path}\"" + (" -Tray" if tray else "") + (" -Login" if login else "")
            workdir = str(self.project_root)
        return (
            f"$s = (New-Object -ComObject WScript.Shell).CreateShortcut({_ps_quote(str(target))}); "
            f"$s.TargetPath = {_ps_quote(exe)}; "
            f"$s.Arguments = {_ps_quote(arguments)}; "
            f"$s.WorkingDirectory = {_ps_quote(workdir)}; "
            f"$s.Description = {_ps_quote(DESCRIPTION)}; "
            f"$s.Save()"
        )

    def tray_scripts_ok(self) -> bool:
        return self.tray_script.is_file()

    def unit_text(self) -> str:
        """The systemd user unit: start.sh in service mode, restarted if it fails."""
        return (
            "[Unit]\n"
            f"Description={DESCRIPTION}\n"
            "After=network-online.target\n"
            "Wants=network-online.target\n\n"
            "[Service]\n"
            "Type=simple\n"
            f"WorkingDirectory={self.project_root}\n"
            f"ExecStart={self._service_command()}\n"
            "Restart=on-failure\n"
            "RestartSec=15\n\n"
            "[Install]\n"
            "WantedBy=default.target\n"
        )

    def _linux_login(self, enabled: bool) -> str | None:
        path = self.shortcut_path
        assert path is not None
        if not enabled:
            if path.is_file():
                self.runner(["systemctl", "--user", "disable", UNIT_NAME])  # a missing systemctl is fine: the file goes anyway
                try:
                    path.unlink()
                except OSError as exc:
                    return f"could not remove {path}: {exc}"
                self.runner(["systemctl", "--user", "daemon-reload"])
            return None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(self.unit_text(), encoding="utf-8")
        except OSError as exc:
            return f"could not write {path}: {exc}"
        for args in (["systemctl", "--user", "daemon-reload"], ["systemctl", "--user", "enable", UNIT_NAME]):
            code, output = self.runner(args)
            if code != 0:
                try:
                    path.unlink()
                except OSError:
                    pass
                return f"systemctl could not enable the service ({output or 'no output'}). Is this a systemd system?"
        return None

    def agent_plist(self) -> bytes:
        """The LaunchAgent: start.sh in service mode at login, restarted if it fails."""
        logs = self.project_root / "logs"
        return plistlib.dumps({
            "Label": AGENT_LABEL,
            "ProgramArguments": [str(self.program), "--login"] if self.program else ["/bin/bash", str(self.script_path), "--service"],
            "WorkingDirectory": str(self.project_root),
            "RunAtLoad": True,
            "KeepAlive": {"SuccessfulExit": False},
            "StandardOutPath": str(logs / "launchd.out.log"),
            "StandardErrorPath": str(logs / "launchd.err.log"),
        })

    def _mac_login(self, enabled: bool) -> str | None:
        path = self.shortcut_path
        assert path is not None
        if not enabled:
            try:
                if path.is_file():
                    path.unlink()
            except OSError as exc:
                return f"could not remove {path}: {exc}"
            return None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(self.agent_plist())
        except OSError as exc:
            return f"could not write {path}: {exc}"
        return None  # launchd loads every agent in the folder at the next login

    # -- the double-click icon ---------------------------------------------------------------------------
    def desktop_shortcut(self, *, tray: bool = False) -> dict[str, Any]:
        """The double-click icon on the Desktop (and in the Linux app menu)."""
        if not self.supported:
            return {"created": False, "error": "a desktop icon is not available on this system"}
        if not self.launch_path.is_file():
            return {"created": False, "error": self._missing()}
        target = self.desktop_path
        if self.system == "windows":
            code, output = self.runner([self._lnk_script(target, tray)])
            if code != 0:
                return {"created": False, "error": f"could not create the Desktop shortcut: {output or 'PowerShell failed'}"}
            self._drop_legacy(target.parent)
            return {"created": True, "path": str(target)}
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            if self.system == "linux":
                target.write_text(self.desktop_entry(), encoding="utf-8")
                menu = self.home / ".local" / "share" / "applications" / DESKTOP_FILE
                menu.parent.mkdir(parents=True, exist_ok=True)
                menu.write_text(self.desktop_entry(), encoding="utf-8")
                menu.chmod(0o755)
            else:
                command = f"exec {shlex.quote(str(self.program))}" if self.program else f"cd {shlex.quote(str(self.project_root))} && exec /bin/bash ./{SHELL_SCRIPT}"
                target.write_text(f"#!/bin/bash\n{command}\n", encoding="utf-8")
            target.chmod(0o755)
        except OSError as exc:
            return {"created": False, "error": f"could not write {target}: {exc}"}
        return {"created": True, "path": str(target)}

    def desktop_entry(self) -> str:
        icon = self.static_dir / "icons" / "icon-192.png"
        command = desktop_arg(str(self.program)) if self.program else f"/bin/bash {desktop_arg(str(self.script_path))}"
        return (
            "[Desktop Entry]\n"
            "Type=Application\n"
            f"Name={APP_TITLE}\n"
            "Comment=Start the Kickoff Companion server\n"
            f"Exec={command}\n"
            f"Path={self.program.parent if self.program else self.project_root}\n"
            f"Icon={icon}\n"
            "Terminal=true\n"
            "Categories=Utility;\n"
        )
