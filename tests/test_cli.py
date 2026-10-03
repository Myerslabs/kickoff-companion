"""python -m app --check validates settings and prints a secret-free report."""

from __future__ import annotations

from app.cli import check_report, main
from app.config import load_settings
from tests.conftest import TEST_KEY


def test_check_with_valid_env_file(tmp_path, capsys):
    env = tmp_path / ".env"
    env.write_text(
        f"CFBD_API_KEY={TEST_KEY}\nLAN_HOSTNAME=football.localdomain\nDATA_DIR={(tmp_path / 'data').as_posix()}\n",
        encoding="utf-8",
    )
    assert main(["--check"], env_file=env) == 0
    out = capsys.readouterr().out
    assert "All settings valid" in out
    assert "configured" in out
    assert "http://football.localdomain:8642" in out and "https://" not in out  # plain HTTP by default (Phase 4b)
    assert "http://football.localdomain:8642/setup" in out
    assert "nothing to install on a device" in out and "will be created" not in out
    assert TEST_KEY not in out
    env.write_text(env.read_text(encoding="utf-8") + "HTTPS=on\n", encoding="utf-8")
    assert main(["--check"], env_file=env) == 0
    out = capsys.readouterr().out
    assert "https://football.localdomain:8642" in out and "will be created" in out  # HTTPS=on: the certificates come at the first start


def test_check_with_bad_env_file(tmp_path, capsys):
    env = tmp_path / ".env"
    env.write_text(f"CFBD_API_KEY={TEST_KEY}\nPORT=0\n", encoding="utf-8")
    assert main(["--check"], env_file=env) == 2
    err = capsys.readouterr().err
    assert "PORT" in err
    assert "between 1 and 65535" in err
    assert TEST_KEY not in err


def test_check_with_missing_env_file(tmp_path, capsys, monkeypatch):
    """No .env yet is setup mode (public release Phase 5a): the check passes and points at /welcome."""
    monkeypatch.delenv("TEAM", raising=False)
    monkeypatch.delenv("CONFERENCE", raising=False)
    assert main(["--check"], env_file=tmp_path / "nope.env") == 0
    out = capsys.readouterr().out
    assert "Setup needed" in out and "/welcome" in out and "not yet" in out


def test_report_lists_every_setting_group():
    settings = load_settings(env_file=None, cfbd_api_key=TEST_KEY)
    report = check_report(settings)
    labels = (
        "CFBD_API_KEY", "Team", "Time zone", "Listen on", "Tablet URL", "HTTPS", "Setup page",
        "Quota", "Live poll", "Radio sources", "Log file", "Data folder",
    )
    for label in labels:
        assert label in report
