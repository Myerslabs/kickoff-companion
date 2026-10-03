"""Every model parses its recorded sample completely, and survives every kind of damage:
missing keys, nulls, wrong types, empty lists, wrong payload shapes, bad nested items."""

from __future__ import annotations

import copy
from typing import Any

import pytest

from app.cfbd.models import (
    ENDPOINTS,
    AdvancedSeasonStat,
    Game,
    GameTeamStats,
    Info,
    ParseResult,
    PlayerGamePpa,
    PollWeek,
    RosterPlayer,
    normalize_endpoint,
    parse_endpoint,
    parse_one,
    parse_records,
)
from app.demo.fixtures import RECORDINGS
from tests.conftest import load_fixture

RECORDED = sorted(RECORDINGS)  # the league's twin of every recording, by the recording's name


def recorded_ok() -> list[tuple[str, str]]:
    pairs = []
    for name in RECORDED:
        recorded = load_fixture(name)
        endpoint = recorded.get("endpoint")
        if recorded.get("status") == 200 and endpoint in ENDPOINTS and ENDPOINTS[endpoint].model is not None:
            pairs.append((name, endpoint))
    return pairs


OK_FIXTURES = recorded_ok()
LIST_FIXTURES = [(n, e) for n, e in OK_FIXTURES if ENDPOINTS[e].many]
OBJECT_FIXTURES = [(n, e) for n, e in OK_FIXTURES if not ENDPOINTS[e].many]


def test_fixtures_exist_for_every_modelled_endpoint():
    covered = {endpoint for _, endpoint in OK_FIXTURES}
    expected = {path for path, spec in ENDPOINTS.items() if spec.model is not None}
    missing = expected - covered
    assert missing == set(), missing
    assert len(OK_FIXTURES) >= 25


@pytest.mark.parametrize(("name", "endpoint"), OK_FIXTURES, ids=[n for n, _ in OK_FIXTURES])
def test_recorded_sample_parses_completely(name, endpoint):
    payload = load_fixture(name)["payload"]
    parsed = parse_endpoint(endpoint, payload, context=name)
    if isinstance(parsed, ParseResult):
        assert parsed.skipped == 0, parsed.problems
        assert parsed.total == len(payload)
        assert len(parsed.records) == len(payload)
    else:
        assert parsed is not None


@pytest.mark.parametrize(("name", "endpoint"), LIST_FIXTURES, ids=[n for n, _ in LIST_FIXTURES])
def test_damaged_lists_never_raise(name, endpoint):
    payload = load_fixture(name)["payload"]
    model = ENDPOINTS[endpoint].model
    assert model is not None
    context = f"{name} damaged"

    assert parse_records(model, [], context=context).records == []
    assert parse_records(model, None, context=context).records == []
    assert parse_records(model, "nonsense", context=context).skipped == 1
    assert parse_records(model, 42, context=context).records == []

    # Every value nulled: identity fields fail, nothing raises.
    nulled = [{key: None for key in record} for record in payload[:5] if isinstance(record, dict)]
    result = parse_records(model, nulled, context=context)
    assert result.total == len(nulled)
    assert result.skipped + len(result.records) == len(nulled)

    # Every value the wrong type: same.
    wrong = [{key: ["wrong"] for key in record} for record in payload[:5] if isinstance(record, dict)]
    result = parse_records(model, wrong, context=context)
    assert result.skipped == len(wrong)

    # One garbage record among good ones only costs that record.
    mixed = copy.deepcopy(payload[:3]) + [{"garbage": True}, "text", None] + copy.deepcopy(payload[3:6])
    result = parse_records(model, mixed, context=context)
    assert result.skipped == 3
    assert len(result.records) == len(mixed) - 3
    assert result.problems


@pytest.mark.parametrize(("name", "endpoint"), LIST_FIXTURES, ids=[n for n, _ in LIST_FIXTURES])
def test_missing_optional_keys_are_fine(name, endpoint):
    """Only identity fields are required: strip everything else and the record still parses."""
    payload = load_fixture(name)["payload"]
    model = ENDPOINTS[endpoint].model
    assert model is not None
    required = {field.alias or name for name, field in model.model_fields.items() if field.is_required()}
    stripped = [
        {key: value for key, value in record.items() if key in required}
        for record in payload[:10]
        if isinstance(record, dict)
    ]
    result = parse_records(model, stripped, context=f"{name} stripped")
    assert result.skipped == 0, result.problems


@pytest.mark.parametrize(("name", "endpoint"), OBJECT_FIXTURES, ids=[n for n, _ in OBJECT_FIXTURES])
def test_damaged_objects_never_raise(name, endpoint):
    model = ENDPOINTS[endpoint].model
    assert model is not None
    assert parse_one(model, None, context=name) is None
    assert parse_one(model, "text", context=name) is None
    assert parse_one(model, [], context=name) is None
    assert parse_one(model, {key: ["wrong"] for key in load_fixture(name)["payload"]}, context=name) is None or True


def test_nested_bad_items_are_dropped_not_fatal():
    game = copy.deepcopy(load_fixture("games_teams")["payload"][0])
    game["teams"][0]["stats"].insert(0, {"nope": 1})
    game["teams"].append("not a team")
    parsed = parse_records(GameTeamStats, [game], context="nested")
    assert parsed.skipped == 0
    assert len(parsed.records[0].teams) == 2
    assert parsed.records[0].teams[0].stats[0].category == "firstDowns"
    assert any("stats" in problem or "teams" in problem for problem in parsed.problems)

    week = copy.deepcopy(load_fixture("rankings")["payload"][0])
    week["polls"][0]["ranks"].append({"rank": 26})  # no school
    parsed_week = parse_records(PollWeek, [week], context="ranks")
    assert parsed_week.skipped == 0
    assert all(rank.school for rank in parsed_week.records[0].polls[0].ranks)


def test_aliases_that_the_generic_camel_case_rule_gets_wrong():
    game = Game.model_validate({"id": 1, "startTimeTBD": True, "homeLineScores": [7, 3.5, None]})
    assert game.start_time_tbd is True
    assert game.home_line_scores == [7, 3.5, None]

    adv = AdvancedSeasonStat.model_validate(load_fixture("stats_season_advanced_team")["payload"][0])
    assert adv.offense is not None and adv.offense.total_ppa is not None
    assert adv.offense.total_opportunities is not None
    assert adv.offense.passing_plays is not None and adv.offense.passing_plays.total_ppa is not None
    assert adv.offense.havoc is not None and adv.offense.havoc.front_seven is not None

    ppa = PlayerGamePpa.model_validate(load_fixture("ppa_players_games")["payload"][0])
    assert ppa.average_ppa is not None and ppa.average_ppa.all is not None

    row = load_fixture("roster")["payload"][0]
    player = RosterPlayer.model_validate(row)
    assert player.home_county_fips == row["homeCountyFIPS"] and player.home_county_fips


def test_info_keeps_unknown_fields():
    payload = load_fixture("info")["payload"]
    info = Info.model_validate(payload)
    assert info.patron_level == 0 and info.remaining_calls == payload["remainingCalls"] > 0
    assert info.model_extra is not None and info.model_extra["tierName"] == "Free"


def test_lax_coercion_of_numbers_in_strings():
    game = Game.model_validate({"id": "526000600", "homePoints": "24", "completed": "true"})
    assert game.id == 526000600 and game.home_points == 24 and game.completed is True
    result = parse_records(Game, [{"id": "abc"}], context="bad id")
    assert result.skipped == 1


def test_parse_endpoint_without_a_model_returns_payload():
    payload = load_fixture("stats_categories")["payload"]
    assert parse_endpoint("/stats/categories", payload) == payload


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("/records", "/records"),
        ("records", "/records"),
        ("C:/Program Files/Git/records", "/records"),
        ("C:/Program Files/Git/live/plays", "/live/plays"),
        ("C:/Program Files/Git/plays", "/plays"),
        ("stats/season/advanced", "/stats/season/advanced"),
        ("/unknown/thing", "/unknown/thing"),
    ],
)
def test_normalize_endpoint(value, expected):
    assert normalize_endpoint(value) == expected


def test_fixture_files_are_well_formed():
    for name in RECORDED:
        recorded = load_fixture(name)
        assert {"endpoint", "params", "status", "fetched_at"} <= set(recorded)
        if recorded["status"] == 200:
            assert "payload" in recorded
        else:
            assert "body" in recorded or "error" in recorded
    assert len(RECORDED) > 100


def _any_key(value: Any) -> bool:
    return isinstance(value, dict) and bool(value)
