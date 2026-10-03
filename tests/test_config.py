"""Settings validation: every bad value stops startup with a readable, secret-free message."""

from __future__ import annotations

import pytest

from app.config import DEFAULT_RADIO_SOURCES, PROJECT_ROOT, SettingsError, load_settings
from tests.conftest import TEST_KEY


def write_env(path, body: str, encoding: str = "utf-8") -> None:
    path.write_text(body, encoding=encoding)


def test_defaults_load_with_only_a_key():
    settings = load_settings(env_file=None, cfbd_api_key=TEST_KEY)
    assert settings.team == "Swampwater Tech"
    from app.config import default_season

    assert settings.season == default_season()  # follows the calendar when SEASON is not set
    assert settings.conference == "Biscuit Belt"
    assert settings.host == "0.0.0.0"
    assert settings.port == 8642
    assert settings.timezone == "America/New_York"
    assert settings.monthly_call_budget == 30000
    assert settings.quota_hard_stop_pct == 90
    assert settings.live_poll_seconds == 12
    assert settings.lan_hostname == ""
    assert settings.log_level == "INFO"
    assert settings.log_dir == PROJECT_ROOT / "logs"
    assert settings.data_dir == PROJECT_ROOT / "data"
    assert [s.name for s in settings.radio_sources] == [s.name for s in DEFAULT_RADIO_SOURCES]
    assert settings.api_key_configured is True
    assert settings.env_file_used is None


def test_key_never_appears_in_repr_or_summary():
    settings = load_settings(env_file=None, cfbd_api_key=TEST_KEY)
    assert TEST_KEY not in repr(settings)
    assert TEST_KEY not in str(settings)
    assert TEST_KEY not in str(settings.public_summary())
    assert settings.public_summary()["api_key_configured"] is True


def test_a_missing_key_team_or_conference_means_setup_mode(monkeypatch):
    """Public release Phase 5a: the server starts and the /welcome page asks for them."""
    monkeypatch.delenv("TEAM", raising=False)
    monkeypatch.delenv("CONFERENCE", raising=False)
    blank = load_settings(env_file=None)
    assert blank.setup_needed and not blank.api_key_configured and blank.team == "" and blank.conference == ""
    for value in ("", "   "):
        monkeypatch.setenv("CFBD_API_KEY", value)
        assert load_settings(env_file=None, team="X", conference="Y").setup_needed
    monkeypatch.setenv("CFBD_API_KEY", TEST_KEY)
    assert load_settings(env_file=None, team="Swampwater Tech", conference=" ").setup_needed
    assert not load_settings(env_file=None, team="Swampwater Tech", conference="Biscuit Belt").setup_needed


@pytest.mark.parametrize("bad", ["short", "has space inside" + "x" * 20])
def test_bad_key_values(monkeypatch, bad):
    monkeypatch.setenv("CFBD_API_KEY", bad)
    with pytest.raises(SettingsError) as info:
        load_settings(env_file=None)
    assert "CFBD_API_KEY" in str(info.value)


def test_error_text_never_contains_the_key(monkeypatch):
    monkeypatch.setenv("CFBD_API_KEY", TEST_KEY)
    monkeypatch.setenv("PORT", "0")
    with pytest.raises(SettingsError) as info:
        load_settings(env_file=None)
    assert TEST_KEY not in str(info.value)
    assert TEST_KEY not in repr(info.value)


def test_short_key_error_does_not_echo_it(monkeypatch):
    monkeypatch.setenv("CFBD_API_KEY", "abc")
    with pytest.raises(SettingsError) as info:
        load_settings(env_file=None)
    assert "abc" not in str(info.value).replace("CFBD_API_KEY", "")


@pytest.mark.parametrize(
    ("key", "value", "fragment"),
    [
        ("PORT", "0", "between 1 and 65535"),
        ("PORT", "70000", "between 1 and 65535"),
        ("PORT", "abc", "whole number"),
        ("PORT", "", "is blank"),
        ("SEASON", "1999", "between 2000 and 2100"),
        ("SEASON", "twenty", "whole number"),
        ("HOST", "not-an-ip", "IP address"),
        ("TIMEZONE", "Mars/Olympus", "not a known IANA time zone"),
        ("TIMEZONE", "", "not a known IANA time zone"),
        ("MONTHLY_CALL_BUDGET", "0", "greater than 0"),
        ("MONTHLY_CALL_BUDGET", "-5", "greater than 0"),
        ("QUOTA_HARD_STOP_PCT", "99", "between 50 and 97"),
        ("QUOTA_HARD_STOP_PCT", "10", "between 50 and 97"),
        ("LIVE_POLL_SECONDS", "3", "at least 8"),
        ("LIVE_POLL_SECONDS", "500", "120 seconds or less"),
        ("LAN_HOSTNAME", "bad name!", "not a valid host name"),
        ("LAN_HOSTNAME", "-leading.hyphen", "not a valid host name"),
        ("LOG_LEVEL", "LOUD", "DEBUG, INFO, WARNING, ERROR"),
        ("RADIO_SOURCES", "not json", "JSON list"),
        ("RADIO_SOURCES", "{}", "JSON list"),
        ("RADIO_SOURCES", '[{"name": "x", "kind": "tv", "url": "https://a"}]', "embed"),
        ("RADIO_SOURCES", '[{"name": "x", "kind": "link", "url": "ftp://a"}]', "http"),
        ("RADIO_SOURCES", '[{"name": "", "kind": "link", "url": "https://a"}]', "name"),
        ("RADIO_SOURCES", '["just a string"]', "object"),
    ],
)
def test_each_bad_value_names_the_key(monkeypatch, key, value, fragment):
    monkeypatch.setenv("CFBD_API_KEY", TEST_KEY)
    monkeypatch.setenv(key, value)
    with pytest.raises(SettingsError) as info:
        load_settings(env_file=None)
    message = str(info.value)
    assert key in message
    assert fragment in message
    assert [problem_key for problem_key, _ in info.value.problems] == [key]


@pytest.mark.parametrize("port", ["1", "80", "8642", "65535"])
def test_valid_ports_including_80(monkeypatch, port):
    monkeypatch.setenv("CFBD_API_KEY", TEST_KEY)
    monkeypatch.setenv("PORT", port)
    assert load_settings(env_file=None).port == int(port)


def test_multiple_problems_are_reported_together(monkeypatch):
    monkeypatch.setenv("CFBD_API_KEY", "short")
    monkeypatch.setenv("PORT", "0")
    monkeypatch.setenv("TIMEZONE", "Nowhere/Land")
    monkeypatch.setenv("LIVE_POLL_SECONDS", "2")
    with pytest.raises(SettingsError) as info:
        load_settings(env_file=None)
    keys = {problem_key for problem_key, _ in info.value.problems}
    assert keys == {"CFBD_API_KEY", "PORT", "TIMEZONE", "LIVE_POLL_SECONDS"}
    message = str(info.value)
    for key in keys:
        assert key in message


def test_values_are_normalised(monkeypatch):
    monkeypatch.setenv("CFBD_API_KEY", f"  {TEST_KEY}  ")
    monkeypatch.setenv("TEAM", "  Swampwater Tech ")
    monkeypatch.setenv("LAN_HOSTNAME", "Football.LocalDomain.")
    monkeypatch.setenv("LOG_LEVEL", "debug")
    monkeypatch.setenv("TIMEZONE", " America/Chicago ")
    settings = load_settings(env_file=None)
    assert settings.cfbd_api_key.get_secret_value() == TEST_KEY
    assert settings.team == "Swampwater Tech"
    assert settings.lan_hostname == "football.localdomain"
    assert settings.log_level == "DEBUG"
    assert settings.timezone == "America/Chicago"


def test_blank_radio_sources_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("CFBD_API_KEY", TEST_KEY)
    monkeypatch.setenv("RADIO_SOURCES", "")
    settings = load_settings(env_file=None)
    assert [s.url for s in settings.radio_sources] == [s.url for s in DEFAULT_RADIO_SOURCES]


def test_env_file_is_read_and_reported(tmp_path):
    env = tmp_path / ".env"
    write_env(env, f"CFBD_API_KEY={TEST_KEY}\nPORT=9000\nTEAM=Swampwater Tech\n")
    settings = load_settings(env_file=env)
    assert settings.port == 9000
    assert settings.env_file_used == env
    assert settings.public_summary()["env_file"] == str(env)


def test_env_file_with_bom_and_quotes(tmp_path):
    env = tmp_path / ".env"
    body = (
        f'CFBD_API_KEY="{TEST_KEY}"\n'
        "PORT=9100\n"
        'RADIO_SOURCES=[{"name": "A", "kind": "link", "url": "https://a.example"}, '
        '{"name": "B", "kind": "embed", "url": "https://b.example"}]\n'
    )
    write_env(env, body, encoding="utf-8-sig")
    settings = load_settings(env_file=env)
    assert settings.cfbd_api_key.get_secret_value() == TEST_KEY
    assert settings.port == 9100
    assert [s.name for s in settings.radio_sources] == ["A", "B"]
    assert settings.radio_sources[1].kind == "embed"


def test_unknown_keys_in_env_file_are_ignored(tmp_path):
    env = tmp_path / ".env"
    write_env(env, f"CFBD_API_KEY={TEST_KEY}\nSOMETHING_ELSE=1\n")
    assert load_settings(env_file=env).port == 8642


def test_a_missing_env_file_is_setup_mode_and_where_setup_will_write(tmp_path, monkeypatch):
    monkeypatch.delenv("TEAM", raising=False)
    env = tmp_path / "does-not-exist.env"
    settings = load_settings(env_file=env)
    assert settings.setup_needed and settings.env_path == env and settings.env_file_used is None
    assert load_settings(env_file=None).env_path is None  # environment variables only: setup writes nothing
    monkeypatch.setenv("PORT", "0")
    with pytest.raises(SettingsError) as info:  # a bad value still names the missing file and the example
        load_settings(env_file=env)
    message = str(info.value)
    assert "No settings file found" in message and str(env) in message and ".env.example" in message
    assert info.value.env_file_exists is False


def test_the_season_follows_the_calendar():
    from datetime import date

    from app.config import default_season

    assert default_season(date(2027, 2, 10)) == 2026  # bowls and the title game
    assert default_season(date(2027, 3, 1)) == 2027
    assert default_season(date(2026, 10, 3)) == 2026


def test_process_environment_overrides_env_file(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    write_env(env, f"CFBD_API_KEY={TEST_KEY}\nPORT=9000\n")
    monkeypatch.setenv("PORT", "9500")
    assert load_settings(env_file=env).port == 9500


def test_overrides_win_over_everything(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    write_env(env, f"CFBD_API_KEY={TEST_KEY}\nPORT=9000\n")
    monkeypatch.setenv("PORT", "9500")
    assert load_settings(env_file=env, port=9800).port == 9800


def test_relative_log_dir_is_anchored_to_project_root():
    settings = load_settings(env_file=None, cfbd_api_key=TEST_KEY, log_dir="mylogs")
    assert settings.log_dir == PROJECT_ROOT / "mylogs"


def test_tzinfo_property():
    settings = load_settings(env_file=None, cfbd_api_key=TEST_KEY)
    assert settings.tzinfo.key == "America/New_York"


def test_radio_sources_may_be_empty(monkeypatch):
    """No station is built in (public release Phase 3): an empty list, or none at all, is a valid setting."""
    monkeypatch.setenv("CFBD_API_KEY", TEST_KEY)
    monkeypatch.setenv("RADIO_SOURCES", "[]")
    assert load_settings(env_file=None).radio_sources == []
    monkeypatch.delenv("RADIO_SOURCES")
    assert load_settings(env_file=None).radio_sources == []
