"""Capabilities: what the key can do, from /info and from real refusals."""

from __future__ import annotations

from datetime import datetime, timezone

from app.cfbd.capabilities import Capabilities
from tests.conftest import fixture_payload

NOW = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)


def test_recorded_free_tier_info():
    caps = Capabilities()
    caps.update_from_info(fixture_payload("info"), NOW)
    assert caps.tier_level == 0 and caps.tier_name == "Free"
    assert caps.monthly_limit == 1000 and caps.remaining_calls == 1000 and caps.used_calls == 0
    assert caps.reset_at == "2026-10-01T00:00:00.000Z"
    assert caps.shared_pool is True
    assert caps.weather is False and caps.scoreboard is False and caps.live_plays is False
    assert caps.adjusted_metrics is False
    assert caps.source == "info" and caps.checked_at == NOW and caps.notes == []
    assert caps.allows("/live/plays") is False and caps.allows("/games") is True


def test_features_win_over_tier_level():
    caps = Capabilities()
    caps.update_from_info({"patronLevel": 0, "features": {"weather": True, "scoreboard": False}}, NOW)
    assert caps.weather is True and caps.scoreboard is False
    assert caps.live_plays is False  # no feature key: derived from level 0


def test_level_alone_derives_gates():
    caps = Capabilities()
    caps.update_from_info({"patronLevel": 2, "remainingCalls": "29,500"}, NOW)
    assert caps.tier_name == "Tier 2" and caps.remaining_calls == 29500
    assert caps.weather is True and caps.scoreboard is True and caps.live_plays is True
    caps.update_from_info({"patronLevel": 1}, NOW)
    assert caps.live_plays is False and caps.scoreboard is True


def test_unknown_shapes_stay_unknown():
    caps = Capabilities()
    caps.update_from_info(None, NOW)
    assert caps.notes and caps.source == "unknown"
    caps.update_from_info({"something": "else"}, NOW)
    assert caps.tier_level is None and caps.weather is None
    assert any("neither" in note for note in caps.notes)


def test_probes_correct_the_picture():
    caps = Capabilities()
    caps.update_from_info({"patronLevel": 2}, NOW)
    caps.note_probe("/live/plays", 401, NOW)
    assert caps.live_plays is False and caps.source == "probe"
    assert caps.notes and "refused" in caps.notes[0]
    caps.note_probe("/live/plays", 200, NOW)
    assert caps.live_plays is True
    caps.note_probe("/games", 401, NOW)  # not gated: ignored
    assert caps.allows("/games") is True
    caps.note_probe("/scoreboard", 500, NOW)  # a 500 says nothing about the tier
    assert caps.scoreboard is True


def test_as_dict_is_json_friendly():
    caps = Capabilities()
    caps.update_from_info(fixture_payload("info"), NOW)
    data = caps.as_dict()
    assert data["checked_at"].startswith("2026-09-21")
    assert set(data) >= {"tier_name", "monthly_limit", "remaining_calls", "reset_at", "weather", "scoreboard", "live_plays", "notes"}
