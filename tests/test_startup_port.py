"""Post-freeze Wave 1 (owner 2026-10-25): the start that cannot have its port, and the clock of the start.

A running copy of the app is opened instead of a second one; another program is named and the next free port offered, in
the console or through the startup report the tray icon's window reads; `--use-port N` saves the port; health and the log
say when the data was ready and when the first data answered; the tray script and the start script start with no window."""

from __future__ import annotations

import io
import json
import socket
from pathlib import Path

from fastapi.testclient import TestClient

from app import boot, cli, portcheck, serving
from app.config import load_settings
from tests.conftest import TEST_KEY

ROOT = Path(__file__).resolve().parents[1]

NETSTAT = """
Active Connections

  Proto  Local Address          Foreign Address        State           PID
  TCP    0.0.0.0:135            0.0.0.0:0              LISTENING       1180
  TCP    0.0.0.0:8642           0.0.0.0:0              LISTENING       4321
  TCP    127.0.0.1:8642         127.0.0.1:50000        ESTABLISHED     4321
  TCP    [::]:8643              [::]:0                 LISTENING       77
"""


def test_the_holder_is_read_from_the_systems_own_tools():
    assert portcheck.parse_netstat(NETSTAT, 8642) == 4321
    assert portcheck.parse_netstat(NETSTAT, 8643) == 77, "the IPv6 listing too"
    assert portcheck.parse_netstat(NETSTAT, 9999) is None
    assert portcheck.parse_netstat("", 8642) is None and portcheck.parse_netstat(None, 8642) is None  # type: ignore[arg-type]
    assert portcheck.parse_tasklist('"vlc.exe","4321","Console","1","52,112 K"') == "vlc.exe"
    assert portcheck.parse_tasklist("INFO: No tasks are running which match the specified criteria.") is None
    assert portcheck.parse_lsof("p912\ncnode\nf12\n") == (912, "node")
    assert portcheck.parse_lsof("") == (None, None)


def test_the_holder_on_windows_asks_netstat_then_tasklist(monkeypatch):
    asked: list[list[str]] = []

    def run(args: list[str]) -> str:
        asked.append(args)
        return NETSTAT if args[0] == "netstat" else '"vlc.exe","4321","Console","1","52,112 K"'

    monkeypatch.setattr(portcheck, "_run", run)
    assert portcheck.port_holder(8642, system="win32") == {"pid": 4321, "name": "vlc.exe"}
    assert asked[-1][:3] == ["tasklist", "/FI", "PID eq 4321"]
    monkeypatch.setattr(portcheck, "_run", lambda args: "")
    assert portcheck.port_holder(8642, system="win32") is None, "the system did not say"
    assert portcheck.port_holder(8642, system="linux") is None


def test_the_report_names_the_holder_and_the_free_port():
    words = portcheck.describe({"port": 8642, "holder": {"pid": 4321, "name": "vlc.exe"}, "nextPort": 8643})
    assert "Port 8642 is taken by vlc.exe (process 4321)" in words and "Port 8643 is free" in words and "QR code" in words
    python = portcheck.describe({"port": 8642, "holder": {"pid": 9, "name": "python.exe"}, "nextPort": None})
    assert "another copy of Kickoff Companion that is not answering" in python and "set another PORT in .env" in python
    unknown = portcheck.describe({"port": 8642, "holder": None, "nextPort": 8650})
    assert "another program" in unknown and "None" not in unknown


def test_the_next_free_port_skips_a_taken_one():
    taken = socket.socket()
    taken.bind(("127.0.0.1", 0))
    port = taken.getsockname()[1]
    try:
        nxt = portcheck.next_free_port("127.0.0.1", port - 1)
        assert nxt is not None and nxt != port and nxt > port - 1
    finally:
        taken.close()


def test_the_console_is_asked_only_when_there_is_one():
    report = {"port": 8642, "holder": None, "nextPort": 8643}

    class Tty(io.StringIO):
        def isatty(self) -> bool:
            return True

    ask = {"system": "linux", "environ": {}}
    out = io.StringIO()
    assert portcheck.ask_in_console(report, stdin=Tty("\n"), stdout=out, **ask) is True, "Enter takes the offer"
    assert "Start on port 8643 and keep it? [Y/n]" in out.getvalue()
    assert portcheck.ask_in_console(report, stdin=Tty("n\n"), stdout=io.StringIO(), **ask) is False
    assert portcheck.ask_in_console(report, stdin=Tty(""), stdout=io.StringIO(), **ask) is False, "a closed input is a no"
    assert portcheck.ask_in_console(report, stdin=io.StringIO("y\n"), stdout=io.StringIO(), **ask) is False, "no console, no question"
    assert portcheck.ask_in_console({**report, "nextPort": None}, stdin=Tty("y\n"), stdout=io.StringIO(), **ask) is False
    hidden = io.StringIO()
    assert portcheck.ask_in_console(report, stdin=Tty("y\n"), stdout=hidden, system="linux", environ={"KICKOFF_NO_PAUSE": "1"}) is False
    assert hidden.getvalue() == "", "behind the tray icon nobody can answer: no question that would wait forever"
    assert portcheck.interactive(Tty(""), system="win32", environ={}) is False, "on Windows a stand-in without a console handle is not a console"


def test_a_server_with_no_console_never_waits_on_the_question():
    """On Windows the NUL device passes isatty: a start with no one to answer must still leave at once (found 2026-10-25)."""
    import subprocess
    import sys

    probe = (
        "import sys; from app import portcheck; "
        "print(portcheck.ask_in_console({'port': 1, 'holder': None, 'nextPort': 2}))"
    )
    done = subprocess.run([sys.executable, "-c", probe], stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60, cwd=ROOT, check=False)
    assert done.stdout.strip().endswith("False") and "[Y/n]" not in done.stdout, done.stdout + done.stderr


def _settings(tmp_path: Path, port: int):
    env = tmp_path / ".env"
    env.write_text(f"TEAM=Swampwater Tech\nPORT={port}\n", encoding="utf-8")
    return load_settings(env, cfbd_api_key=TEST_KEY, data_dir=tmp_path / "data", log_dir=tmp_path / "logs")


def test_a_running_copy_is_opened_instead_of_a_second(tmp_path: Path, monkeypatch):
    opened: list[str] = []
    monkeypatch.setattr(portcheck, "running_copy", lambda port: {"app": {"name": "Kickoff Companion"}})
    monkeypatch.setattr(serving, "open_in_browser", opened.append)
    settings = _settings(tmp_path, 8642)
    portcheck.write_report(settings.data_dir, {"reason": "port", "port": 8642})
    assert serving.port_taken(settings, open_url="http://localhost:8642/") == portcheck.ALREADY_RUNNING == 6
    assert opened == ["http://localhost:8642/"] and portcheck.read_report(settings.data_dir) is None
    assert serving.PORT_CHANGED != 5 and portcheck.ALREADY_RUNNING != 5, "neither is the in-place restart's code"


def test_another_program_leaves_a_report_for_the_tray(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(portcheck, "running_copy", lambda port: None)
    monkeypatch.setattr(portcheck, "port_holder", lambda port: {"pid": 4321, "name": "vlc.exe"})
    monkeypatch.setattr(portcheck, "next_free_port", lambda host, port: 8643)
    monkeypatch.setattr(portcheck, "ask_in_console", lambda report: False)
    settings = _settings(tmp_path, 8642)
    assert serving.port_taken(settings) == serving.PORT_IN_USE == 4
    report = json.loads((settings.data_dir / "startup-failure.json").read_text(encoding="utf-8"))
    assert report["holder"] == {"pid": 4321, "name": "vlc.exe"} and report["nextPort"] == 8643 and "vlc.exe" in report["message"]


def test_a_yes_in_the_console_saves_the_port_and_serves_again(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(portcheck, "running_copy", lambda port: None)
    monkeypatch.setattr(portcheck, "port_holder", lambda port: None)
    monkeypatch.setattr(portcheck, "next_free_port", lambda host, port: 8643)
    monkeypatch.setattr(portcheck, "ask_in_console", lambda report: True)
    settings = _settings(tmp_path, 8642)
    assert serving.port_taken(settings) == serving.PORT_CHANGED
    text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "PORT=8643" in text and "PORT=8642" not in text and "TEAM=Swampwater Tech" in text


def test_a_restart_never_mistakes_the_old_server_for_a_running_copy(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(portcheck, "running_copy", lambda port: (_ for _ in ()).throw(AssertionError("not asked on a restart")))
    monkeypatch.setattr(portcheck, "port_holder", lambda port: None)
    monkeypatch.setattr(portcheck, "next_free_port", lambda host, port: None)
    monkeypatch.setattr(portcheck, "ask_in_console", lambda report: False)
    assert serving.port_taken(_settings(tmp_path, 8642), restarting=True) == serving.PORT_IN_USE


def test_use_port_saves_the_port_and_refuses_a_bad_one(tmp_path: Path, capsys):
    env = tmp_path / ".env"
    env.write_text("TEAM=Swampwater Tech\nPORT=8642\n", encoding="utf-8")
    assert cli.main(["--use-port", "8643"], env_file=env) == 0
    assert "PORT=8643" in env.read_text(encoding="utf-8") and "saved" in capsys.readouterr().out
    assert cli.main(["--use-port", "80"], env_file=env) == 2
    assert "PORT=8643" in env.read_text(encoding="utf-8")


def test_a_running_copy_opened_is_no_reason_to_pause():
    asked: list[str] = []
    assert cli.pause_before_closing(portcheck.ALREADY_RUNNING, packaged=True, system="win32", owners=1, ask=asked.append) is False
    assert cli.pause_before_closing(portcheck.ALREADY_RUNNING - 2, packaged=True, system="win32", owners=1, ask=asked.append) is True


def test_health_says_when_the_data_was_ready_and_the_log_says_the_first_data(app, client: TestClient, caplog):
    app.state.ready_seconds = None
    app.state.first_data_seconds = None
    server = client.get("/api/health").json()["data"]["server"]
    assert server["ready_seconds"] is None and server["first_data_seconds"] is None
    app.state.ready_seconds = 4.2
    caplog.set_level("INFO", logger="kickoff.main")
    assert client.get("/api/identity").status_code == 200
    first = app.state.first_data_seconds
    assert isinstance(first, float) and any("First data after" in r.getMessage() and "/api/identity" in r.getMessage() for r in caplog.records)
    client.get("/api/identity")
    assert app.state.first_data_seconds == first, "only the first answer counts"
    server = client.get("/api/health").json()["data"]["server"]
    assert server["ready_seconds"] == 4.2 and server["first_data_seconds"] == first


def test_the_start_clock_starts_again_at_a_restart():
    boot.mark()
    assert 0 <= boot.seconds() < 1


def test_the_tray_and_the_start_script_start_with_no_window():
    tray = (ROOT / "tools" / "tray.ps1").read_text(encoding="utf-8")
    assert "CreateNoWindow = $true" in tray and "-WindowStyle Hidden" not in tray, "the server starts with no window"
    assert '"ready_seconds"' in tray and "starting, $seconds s" in tray and "Ready after $took s" in tray
    assert "Copy the report" in tray and '"--use-port"' in tray and "startup-failure.json" in tray
    assert "$AlreadyRunning = 6" in tray and "Show the window" not in tray
    start = (ROOT / "start.ps1").read_text(encoding="utf-8")
    assert "CreateNoWindow = $true" in start and "[Environment]::Exit(0)" in start and "& powershell.exe @trayArgs" not in start
    assert "$code -eq 6" in start
    kickoff = (ROOT / "tools" / "package" / "kickoff.py").read_text(encoding="utf-8")
    assert "CREATE_NO_WINDOW" in kickoff and "CREATE_NEW_CONSOLE" not in kickoff


def test_a_desktop_icon_no_longer_keeps_its_window(tmp_path: Path):
    from app.services.launcher import Launcher

    launcher = Launcher(ROOT, platform="win32", appdata=str(tmp_path), runner=lambda args: (0, ""))
    script = launcher._lnk_script(tmp_path / "Kickoff Companion.lnk", True)
    assert "-NoExit" not in script and "-Tray" in script
