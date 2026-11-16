"""FEAT-16 Talent Edge (Feature Set v2 Phase A, owner 2026-10-30): the spec's tests (A.9) and the weekly runner's.

Units: every position code of the spec's table and unknown ones, name keys, the match's precedence (recruit record,
then portal, then unrated), the numbers with empty and unrated groups, the blue-chip share's denominator, ranks and
percentiles, a hand-built twelve-player roster with every number worked out by hand, and the same bytes from
shuffled inputs. The job and the answers against the simulated league (no network): Florida end to end with all
seven spider values, a run that cannot get its data, the 404 and 503 answers. The runner's Sunday slot, the
command line against a scripted server, the routes and the status page's check."""

from __future__ import annotations

import asyncio
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.health import _jobs_check
from app.cfbd.models import PlayerTransfer, Recruit, RosterPlayer
from app.config import Settings
from app.demo.upstream import DemoUpstream
from app.jobs import JobFailed, JobRuns, run_job
from app.jobs.cli import main as cli_main
from app.jobs.weekly import JobBusy, WeeklyJobs, slot_start
from app.logging_setup import configure_logging, shutdown_logging
from app.main import create_app
from app.services.talent_edge import (
    EXCLUDED,
    GROUPS,
    POSITIONS,
    PlayerTalent,
    TalentEdgeStore,
    build_table,
    compute_group_metrics,
    cross_units,
    group_of,
    match_players,
    name_key,
    percentile,
    player_rows,
    summary_line,
    team_groups,
)
from tests.conftest import league

S = 2026
SATURDAY = datetime(2026, 9, 26, 22, 0, tzinfo=timezone.utc)  # the league's week 4


def roster(*rows: dict[str, Any]) -> list[RosterPlayer]:
    return [RosterPlayer.model_validate(r) for r in rows]


def recruit(rid: str, year: int | None, rating: Any, stars: Any, school: str = "Alpha") -> Recruit:
    return Recruit.model_validate({"id": rid, "year": year, "rating": rating, "stars": stars, "committedTo": school, "name": f"Recruit {rid}"})


def move(first: str, last: str, to: str, season: int, rating: Any = None, stars: Any = None, date: str = "2025-01-10T00:00:00.000Z") -> PlayerTransfer:
    return PlayerTransfer.model_validate({"firstName": first, "lastName": last, "destination": to, "origin": "Elsewhere", "season": season, "rating": rating, "stars": stars, "transferDate": date})


def player(pid: str, group: str | None, rating: float | None, stars: int | None, year: int | None, source: str = "recruit_id", transfer: bool = False, team: str = "Alpha") -> PlayerTalent:
    return PlayerTalent(pid, team, f"Player {pid}", group or "K", group, rating, stars, year, source, transfer)


# --- positions and names (A.4, A.3) -------------------------------------------------------------------------------


def test_every_code_in_the_spec_table_maps_to_its_group():
    for group, codes in POSITIONS.items():
        for code in codes:
            assert group_of(code) == group, code
            assert group_of(f"  {code.lower()} ") == group, "trimmed, any case"
    assert set(POSITIONS) == set(GROUPS)


@pytest.mark.parametrize("code", ["XYZ", "", None, 7, "WR/CB"])
def test_unknown_codes_are_in_no_group(code):
    assert group_of(code) is None


def test_specialists_and_athletes_are_in_no_group():
    for code in EXCLUDED:
        assert group_of(code) is None


@pytest.mark.parametrize(
    ("first", "last", "same_as"),
    [
        ("Marcus", "O'Neil Jr.", ("Marcus", "ONeil")),
        ("Tre", "Smith-Jones", ("Tre", "Smith Jones")),
        ("Ja'Marr", "Chase  II", ("JaMarr", "Chase")),
        ("D.J.", "Lagway", ("DJ", "Lagway")),
        ("José", "Núñez III", ("Jose", "Nunez")),
        ("  Kam ", "  Davis  Sr ", ("Kam", "Davis")),
    ],
)
def test_name_keys_ignore_suffixes_punctuation_spaces_and_accents(first, last, same_as):
    assert name_key(first, last) == name_key(*same_as)
    assert name_key(first, last).isalpha()


def test_name_keys_keep_different_people_apart_and_survive_junk():
    assert name_key("Ivan", "Smith") != name_key("Ivy", "Smith")
    assert name_key("Vince", "Wilfork") == "vincewilfork", "a name that starts with v keeps it"
    assert name_key(None, None) == ""
    assert name_key(12, ["x"]) == ""


# --- the match (A.3) ----------------------------------------------------------------------------------------------


def one(players: list[PlayerTalent], pid: str) -> PlayerTalent:
    return next(p for p in players if p.player_id == pid)


def test_the_recruit_record_beats_the_portal_and_the_portal_still_flags_the_transfer():
    rows = roster({"id": "1", "firstName": "Ace", "lastName": "Hill", "team": "Alpha", "position": "WR", "recruitIds": ["r1"]})
    players, _ = match_players(rows, {"r1": recruit("r1", 2024, 0.97, 5)}, [move("Ace", "Hill", "Alpha", 2026, 0.88, 3)], S)
    p = one(players, "1")
    assert (p.rating, p.stars, p.recruit_year, p.source, p.is_transfer) == (0.97, 5, 2024, "recruit_id", True)


def test_the_portal_rates_a_transfer_with_no_recruit_record():
    rows = roster({"id": "2", "firstName": "Bo", "lastName": "Reed", "team": "Alpha", "position": "RB", "recruitIds": []})
    players, _ = match_players(rows, {}, [move("Bo", "Reed", "Alpha", 2025, 0.88, 3)], S)
    p = one(players, "2")
    assert (p.rating, p.stars, p.recruit_year, p.source, p.is_transfer) == (0.88, 3, None, "portal", True)


def test_a_player_found_nowhere_is_unrated():
    rows = roster({"id": "3", "firstName": "Cy", "lastName": "Ott", "team": "Alpha", "position": "TE", "recruitIds": ["missing"]})
    p = one(match_players(rows, {}, [], S)[0], "3")
    assert (p.rating, p.stars, p.source, p.is_transfer) == (None, None, "none", False)


def test_the_latest_recruit_class_wins_among_several_ids():
    rows = roster({"id": "4", "firstName": "Dee", "lastName": "Moss", "team": "Alpha", "position": "QB", "recruitIds": ["old", "new", "ghost"]})
    p = one(match_players(rows, {"old": recruit("old", 2022, 0.85, 3), "new": recruit("new", 2024, 0.90, 4)}, [], S)[0], "4")
    assert (p.rating, p.stars, p.recruit_year) == (0.90, 4, 2024)


def test_the_portal_counts_only_moves_to_this_team_in_the_last_three_seasons():
    rows = roster(
        {"id": "5", "firstName": "Eli", "lastName": "Park", "team": "Alpha", "position": "LB"},
        {"id": "6", "firstName": "Fin", "lastName": "Cole", "team": "Alpha", "position": "CB"},
    )
    portal = [move("Eli", "Park", "Alpha", 2023, 0.9, 4), move("Fin", "Cole", "Beta", 2025, 0.9, 4)]
    players, _ = match_players(rows, {}, portal, S)
    assert not one(players, "5").is_transfer, "2023 is outside 2024 to 2026"
    assert not one(players, "6").is_transfer, "he moved to another school"


def test_two_players_with_one_name_on_a_team_are_never_matched_to_the_portal():
    rows = roster(
        {"id": "7", "firstName": "Gus", "lastName": "Lee", "team": "Alpha", "position": "S", "recruitIds": ["g1"]},
        {"id": "8", "firstName": "Gus", "lastName": "Lee Jr.", "team": "Alpha", "position": "DL"},
    )
    players, problems = match_players(rows, {"g1": recruit("g1", 2025, 0.91, 4)}, [move("Gus", "Lee", "Alpha", 2026, 0.8, 3)], S)
    assert one(players, "7").source == "recruit_id" and not one(players, "7").is_transfer
    assert one(players, "8").source == "none" and not one(players, "8").is_transfer
    assert any("share the name key" in p for p in problems)


def test_bad_records_are_skipped_and_named_never_guessed():
    rows = roster(
        {"id": "9", "firstName": "Hal", "lastName": "Vo", "team": None, "position": "QB"},
        {"id": "10", "firstName": "Ian", "lastName": "Wu", "team": "Alpha", "position": "QB", "recruitIds": ["bad"]},
        {"id": "10", "firstName": "Ian", "lastName": "Wu", "team": "Alpha", "position": "QB"},
        {"id": "11", "firstName": "Jo", "lastName": "Xu", "team": "Alpha", "position": "WR", "recruitIds": ["r11"]},
        {"id": "12", "firstName": "Kip", "lastName": "Yi", "team": "Alpha", "position": "WR", "recruitIds": ["r12"]},
    )
    recruits = {"bad": recruit("bad", 2024, float("nan"), 9), "r11": recruit("r11", 2024, 1.7, 0), "r12": recruit("r12", 2024, 0, "5")}
    players, problems = match_players(rows, recruits, [move("Ian", "Wu", "Alpha", 2026, -1, 2)], S)
    assert [p.player_id for p in players] == ["10", "11", "12"], "no team: skipped; the second id 10: skipped"
    assert all(p.rating is None and p.stars is None for p in players), "NaN, 1.7, 0 and a negative rating are no ratings"
    assert len(problems) == 2


def test_a_malformed_payload_parses_record_by_record():
    from app.cfbd.models import parse_records

    parsed = parse_records(RosterPlayer, [{"id": "1", "team": "Alpha", "recruitIds": "r1"}, {"firstName": "No id"}, None, "junk", {"id": "2", "team": "Alpha", "recruitIds": None}], context="test")
    players, _ = match_players(parsed.records, {"r1": recruit("r1", 2024, 0.9, 4)}, [], S)
    assert parsed.skipped >= 2
    assert all(p.source == "none" for p in players), "recruitIds as a string or null finds nothing"


def test_teams_outside_the_fbs_list_are_left_out():
    rows = roster({"id": "1", "team": "Alpha", "position": "QB"}, {"id": "2", "team": "Campbell", "position": "QB"})
    players, _ = match_players(rows, {}, [], S, fbs={"Alpha"})
    assert [p.team for p in players] == ["Alpha"]


# --- the numbers (A.5) --------------------------------------------------------------------------------------------


def test_an_empty_group_has_counts_of_zero_and_no_averages():
    m = compute_group_metrics([], S)
    assert (m.count, m.rated_count, m.avg_rating, m.avg_stars, m.avg_years, m.bcr_pct, m.unrated_count, m.transfer_count) == (0, 0, None, None, None, None, 0, 0)


def test_a_group_with_nobody_rated_has_no_averages_and_no_share():
    m = compute_group_metrics([player("1", "QB", None, None, 2024), player("2", "QB", None, None, None, "none", True)], S)
    assert (m.count, m.rated_count, m.avg_rating, m.avg_stars, m.bcr_pct, m.unrated_count, m.transfer_count) == (2, 0, None, None, None, 2, 1)
    assert m.avg_years == 2.0, "a recruit record with no rating still dates the class"


def test_the_blue_chip_share_is_of_rated_players_not_of_everyone_listed():
    group = [player("1", "WR", 0.95, 5, 2024), player("2", "WR", 0.91, 4, 2023), player("3", "WR", 0.86, 3, 2025), player("4", "WR", None, None, None, "none"), player("5", "WR", None, None, None, "none")]
    m = compute_group_metrics(group, S)
    assert m.bcr_pct == pytest.approx(66.7), "2 of 3 rated, not 2 of 5 listed"


def test_years_since_signing_skip_the_portal_only_ratings():
    m = compute_group_metrics([player("1", "OL", 0.9, 4, 2022), player("2", "OL", 0.88, 3, None, "portal", True)], S)
    assert m.avg_years == 4.0 and m.rated_count == 2


def test_percentiles_run_from_100_first_to_0_last():
    assert percentile(1, 138) == 100 and percentile(138, 138) == 0 and percentile(1, 1) == 100
    assert percentile(70, 139) == 50


# --- the twelve-player roster, by hand ----------------------------------------------------------------------------


def twelve() -> tuple[list[RosterPlayer], dict[str, Recruit], list[PlayerTransfer]]:
    rows = roster(
        {"id": "01", "firstName": "Quinn", "lastName": "One", "team": "Alpha", "position": "QB", "recruitIds": ["qb1"]},
        {"id": "02", "firstName": "Quentin", "lastName": "Two", "team": "Alpha", "position": "QB", "recruitIds": ["qb2a", "qb2b"]},
        {"id": "03", "firstName": "Marcus", "lastName": "O'Neil Jr.", "team": "Alpha", "position": "RB", "recruitIds": []},
        {"id": "04", "firstName": "Wes", "lastName": "Wide", "team": "Alpha", "position": "WR", "recruitIds": ["wr1"]},
        {"id": "05", "firstName": "Walk", "lastName": "On", "team": "Alpha", "position": "WR"},
        {"id": "06", "firstName": "Ty", "lastName": "End", "team": "Alpha", "position": "TE", "recruitIds": ["te1"]},
        {"id": "07", "firstName": "Otis", "lastName": "Tackle", "team": "Alpha", "position": "OT", "recruitIds": ["ol1"]},
        {"id": "08", "firstName": "Cal", "lastName": "Center", "team": "Alpha", "position": "c", "recruitIds": ["ol2"]},
        {"id": "09", "firstName": "Ed", "lastName": "Rush", "team": "Alpha", "position": "EDGE", "recruitIds": ["dl1"]},
        {"id": "10", "firstName": "Lou", "lastName": "Backer", "team": "Alpha", "position": "LB"},
        {"id": "11", "firstName": "Cory", "lastName": "Corner", "team": "Alpha", "position": "CB", "recruitIds": ["cb1"]},
        {"id": "12", "firstName": "Kip", "lastName": "Kicker", "team": "Alpha", "position": "PK", "recruitIds": ["k1"]},
    )
    recruits = {r.id: r for r in [
        recruit("qb1", 2023, 0.95, 4), recruit("qb2a", 2022, 0.85, 3), recruit("qb2b", 2024, 0.90, 4), recruit("wr1", 2026, 0.99, 5),
        recruit("te1", 2024, None, 3), recruit("ol1", 2022, 0.86, 3), recruit("ol2", 2021, 0.80, 2), recruit("dl1", 2025, 0.93, 4),
        recruit("cb1", 2025, 0.91, 4), recruit("k1", 2024, 0.80, 2),
    ]}
    portal = [
        move("Marcus", "ONeil", "Alpha", 2025, 0.88, 3),
        move("Wes", "Wide", "Alpha", 2026, 0.70, 2),
        move("Lou", "Backer", "Alpha", 2023, 0.90, 4),
        move("Cory", "Corner", "Beta", 2024, 0.91, 4),
    ]
    return rows, recruits, portal


def test_the_twelve_player_roster_by_hand():
    rows, recruits, portal = twelve()
    players, problems = match_players(rows, recruits, portal, S)
    assert problems == []
    table = build_table(players, {"Alpha": {"talent": 800.0, "rank": 1, "of": 1}}, {"Alpha": {"abbreviation": "ALP"}}, S, 9, {})
    alpha = table["teams"]["Alpha"]
    assert alpha["summary"] == {"roster": 12, "rated": 9, "ratedByRecruit": 8, "ratedByPortal": 1, "unrated": 3, "transfers": 2, "outsideGroups": 1}
    g = alpha["groups"]
    expect = {
        #           count rated avg      stars  years   bcr    unrated transfers
        "QB": (2, 2, 0.925, 4.0, 2.5, 100.0, 0, 0),
        "RB": (1, 1, 0.88, 3.0, None, 0.0, 0, 1),
        "WR": (2, 1, 0.99, 5.0, 0.0, 100.0, 1, 1),
        "TE": (1, 0, None, None, 2.0, None, 1, 0),
        "OL": (2, 2, 0.83, 2.5, 4.5, 0.0, 0, 0),
        "FRONT7": (2, 1, 0.93, 4.0, 1.0, 100.0, 1, 0),
        "SECONDARY": (1, 1, 0.91, 4.0, 1.0, 100.0, 0, 0),
        "O": (8, 6, 0.8967, 3.5, 2.67, 50.0, 2, 2),
        "D": (3, 2, 0.92, 4.0, 1.0, 100.0, 1, 0),
        "TOT": (11, 8, 0.9025, 3.625, 2.25, 62.5, 3, 2),
    }
    for group, (count, rated, avg, stars, years, bcr, unrated, transfers) in expect.items():
        row = g[group]
        assert (row["count"], row["ratedCount"], row["unratedCount"], row["transferCount"]) == (count, rated, unrated, transfers), group
        for key, want in (("avgRating", avg), ("avgStars", stars), ("avgYears", years), ("bcrPct", bcr)):
            assert row[key] == (None if want is None else pytest.approx(want, abs=0.006)), (group, key)
    assert g["TE"]["rank"] is None and g["TE"]["pct"] is None, "a group with nobody rated is unranked"
    assert g["QB"]["rank"] == 1 and g["QB"]["pct"] == 100
    assert summary_line(alpha) == "#1 talent · 0.90 avg · 62% BCR" or summary_line(alpha) == "#1 talent · 0.90 avg · 63% BCR"


def test_ranks_and_percentiles_across_teams_and_the_cross_units():
    players = [
        *[player(f"a{i}", g, 0.95, 4, 2024, team="Alpha") for i, g in enumerate(GROUPS)],
        *[player(f"b{i}", g, 0.90, 3, 2024, team="Beta") for i, g in enumerate(GROUPS)],
        *[player(f"c{i}", g, 0.85, 3, 2024, team="Gamma") for i, g in enumerate(GROUPS)],
    ]
    table = build_table(players, {}, {}, S, None, {})
    for g in GROUPS:
        assert [table["teams"][t]["groups"][g]["pct"] for t in ("Alpha", "Beta", "Gamma")] == [100, 50, 0]
        assert table["teams"]["Beta"]["groups"][g]["rank"] == 2 and table["teams"]["Beta"]["groups"][g]["of"] == 3
    rows = cross_units(table["teams"]["Alpha"], table["teams"]["Gamma"])
    assert len(rows) == 6
    assert [(r["offense"], r["a_group"], r["b_group"]) for r in rows] == [
        ("a", "WR", "SECONDARY"), ("a", "OL", "FRONT7"), ("a", "RB", "FRONT7"),
        ("b", "SECONDARY", "WR"), ("b", "FRONT7", "OL"), ("b", "FRONT7", "RB"),
    ]
    assert rows[0]["a_rating"] == 0.95 and rows[0]["b_rating"] == 0.85 and rows[3]["a_pct"] == 100


def test_shuffled_inputs_give_the_same_bytes():
    rows, recruits, portal = twelve()
    first, _ = match_players(rows, recruits, portal, S)
    shuffled_rows = list(rows)
    shuffled_portal = list(portal)
    random.Random(7).shuffle(shuffled_rows)
    random.Random(8).shuffle(shuffled_portal)
    second, _ = match_players(shuffled_rows, dict(reversed(list(recruits.items()))), shuffled_portal, S)
    a = json.dumps(build_table(first, {}, {}, S, 9, {"x": 1}))
    b = json.dumps(build_table(list(reversed(second)), {}, {}, S, 9, {"x": 1}))
    assert a == b
    assert json.dumps(player_rows(first)) == json.dumps(player_rows(list(reversed(second))))


def test_the_roll_ups_hold_their_groups_players():
    players = [player("1", "QB", 0.9, 4, 2024), player("2", "SECONDARY", 0.9, 4, 2024), player("3", None, 0.9, 4, 2024)]
    grouped = team_groups(players)
    assert [p.player_id for p in grouped["O"]] == ["1"] and [p.player_id for p in grouped["D"]] == ["2"]
    assert [p.player_id for p in grouped["TOT"]] == ["1", "2"], "the kicker is in no group"


def test_the_store_writes_both_files_and_reads_back_only_its_own_format(tmp_path: Path):
    store = TalentEdgeStore(tmp_path, S)
    rows, recruits, portal = twelve()
    players, _ = match_players(rows, recruits, portal, S)
    assert store.load() is None
    store.save(build_table(players, {}, {}, S, 9, {}), player_rows(players))
    assert store.load()["teams"]["Alpha"]["summary"]["roster"] == 12
    assert [p["id"] for p in store.players("Alpha")][:2] == ["01", "02"] and store.players("Nobody") == []
    store.path.write_text(json.dumps({"format": 99, "teams": {}}), encoding="utf-8")
    assert store.load() is None, "a table this build cannot read is left alone"


# --- the run log and the weekly slot ------------------------------------------------------------------------------


def eastern(*args: int) -> datetime:
    return datetime(*args, tzinfo=timezone(timedelta(hours=-4)))


def test_the_slot_is_the_latest_sunday_six_am():
    assert slot_start(eastern(2026, 11, 1, 6, 0)) == eastern(2026, 11, 1, 6, 0)
    assert slot_start(eastern(2026, 11, 1, 5, 59)) == eastern(2026, 10, 25, 6, 0)
    assert slot_start(eastern(2026, 10, 30, 10, 0)) == eastern(2026, 10, 25, 6, 0), "Friday looks back to last Sunday"
    assert slot_start(eastern(2026, 11, 2, 0, 1)) == eastern(2026, 11, 1, 6, 0)


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def runner(tmp_path: Path, clock: Clock, outcome: list[str]) -> WeeklyJobs:
    async def work() -> dict[str, Any]:
        if outcome and outcome[0] == "fail":
            raise JobFailed("CFBD data missing")
        return {"week": 9, "message": "fine"}

    return WeeklyJobs(JobRuns(tmp_path, clock), S, {"talent_edge": work})


def test_due_at_once_when_never_run_then_weekly_and_a_failure_waits_three_hours(tmp_path: Path):
    asyncio.run(_due_cycle(tmp_path))


async def _due_cycle(tmp_path: Path) -> None:
    clock = Clock(eastern(2026, 10, 30, 10, 0))  # a Friday
    outcome: list[str] = []
    jobs = runner(tmp_path, clock, outcome)
    assert jobs.due(clock.now), "never run: due at once"
    run = await jobs.run()
    assert run["status"] == "ok" and run["week"] == 9
    assert jobs.runs.last("talent_edge", S, "ok") is not None
    clock.now = eastern(2026, 10, 31, 12, 0)
    assert not jobs.due(clock.now), "Saturday: last Sunday's slot is covered by Friday's run"
    clock.now = eastern(2026, 11, 1, 6, 30)
    assert jobs.due(clock.now), "Sunday 6 AM: the new week's slot"
    outcome.append("fail")
    run = await jobs.run()
    assert run["status"] == "failed" and "1 of 1 job failed" in run["message"]
    clock.now = eastern(2026, 11, 1, 8, 0)
    assert not jobs.due(clock.now), "a failure is not retried every hour"
    clock.now = eastern(2026, 11, 1, 9, 31)
    assert jobs.due(clock.now), "three hours later it is"
    outcome.clear()
    assert (await jobs.run())["status"] == "ok"
    assert not jobs.due(eastern(2026, 11, 7, 23, 0))


def test_one_run_at_a_time(tmp_path: Path):
    asyncio.run(_one_at_a_time(tmp_path))


async def _one_at_a_time(tmp_path: Path) -> None:
    gate = asyncio.Event()

    async def slow() -> dict[str, Any]:
        await gate.wait()
        return {"message": "done"}

    jobs = WeeklyJobs(JobRuns(tmp_path), S, {"talent_edge": slow})
    run = jobs.start("talent_edge")
    assert run["status"] == "running" and jobs.running
    with pytest.raises(JobBusy):
        jobs.start("weekly")
    with pytest.raises(KeyError):
        WeeklyJobs(JobRuns(tmp_path / "x"), S, {}).start("nope")
    assert not jobs.due(datetime.now().astimezone())
    gate.set()
    await jobs._task
    assert not jobs.running and jobs.runs.get(run["id"])["status"] == "ok"


def test_an_unexpected_error_is_recorded_by_type_and_a_cut_off_run_reads_failed(tmp_path: Path):
    runs = JobRuns(tmp_path)

    async def broken() -> dict[str, Any]:
        raise ZeroDivisionError("oops")

    run = asyncio.run(run_job(runs, "talent_edge", S, broken))
    assert run["status"] == "failed" and run["message"].startswith("Unexpected error: ZeroDivisionError")
    started = runs.start("talent_edge", S)
    reopened = JobRuns(tmp_path)
    assert reopened.get(started["id"])["status"] == "failed" and "stopped" in reopened.get(started["id"])["message"]


def test_the_log_keeps_the_last_twenty_runs_of_each_job(tmp_path: Path):
    runs = JobRuns(tmp_path)
    for _ in range(25):
        run = runs.start("talent_edge", S)
        runs.finish(run["id"], "ok", "fine")
    runs.finish(runs.start("weekly", S)["id"], "ok", "fine")
    kept = json.loads((tmp_path / "jobs.json").read_text(encoding="utf-8"))["runs"]
    assert sum(1 for r in kept if r["job"] == "talent_edge") == 20 and sum(1 for r in kept if r["job"] == "weekly") == 1


def test_the_status_check_names_a_failure():
    assert _jobs_check({"jobs": {}, "running": None})["status"] == "ok"
    bad = _jobs_check({"jobs": {"talent_edge": {"label": "Talent Edge", "status": "failed", "startedAt": "2026-11-01T06:02:00-04:00", "message": "CFBD data missing"}}, "running": None})
    assert bad["status"] == "degraded" and "CFBD data missing" in bad["detail"]
    assert _jobs_check({"jobs": {}, "running": "talent_edge"})["status"] == "ok"


# --- the job and the answers, against the simulated league --------------------------------------------------------


@pytest.fixture
def lclient(settings: Settings):
    upstream = DemoUpstream(league(), lambda: SATURDAY, tier=2)
    configure_logging(settings)
    application = create_app(settings, cfbd_transport=httpx.MockTransport(upstream.handler))
    application.state.cfbd._clock = lambda: SATURDAY
    try:
        with TestClient(application, base_url="https://testserver") as client:
            client.portal.call(application.state.live.stop_background)
            client.app_state = application.state  # type: ignore[attr-defined]
            client.upstream = upstream  # type: ignore[attr-defined]
            yield client
    finally:
        shutdown_logging()


def test_before_any_run_the_answers_say_why(lclient: TestClient):
    answer = lclient.get(f"/api/talent-edge/{S}/Florida")
    assert answer.status_code == 503
    assert "not been worked out yet" in answer.json()["errors"][0]["message"]


def test_florida_end_to_end(lclient: TestClient):
    state = lclient.app_state  # type: ignore[attr-defined]
    run = lclient.portal.call(state.jobs.run, "talent_edge")
    assert run["status"] == "ok", run["message"]
    assert lclient.upstream.calls.get("/roster") == 1, "every FBS roster in one call"  # type: ignore[attr-defined]
    data = lclient.get(f"/api/talent-edge/{S}/florida").json()["data"]
    assert data["team"] == "Florida", "any case finds CFBD's name"
    for group in GROUPS:
        row = data["groups"][group]
        assert isinstance(row["pct"], int) and 0 <= row["pct"] <= 100, group
        assert isinstance(row["avgRating"], float) and 0 < row["avgRating"] <= 1, group
    assert data["summary"]["roster"] > 60 and data["summary"]["rated"] > 0
    assert isinstance(data["talent"]["rank"], int) and data["summaryLine"]
    assert data["computedWeek"] is None or isinstance(data["computedWeek"], int)
    opponent = "Georgia"
    both = lclient.get(f"/api/talent-edge/{S}/compare", params={"teamA": "Florida", "teamB": opponent}).json()["data"]
    assert both["a"]["team"] == "Florida" and both["b"]["team"] == opponent and len(both["cross_unit"]) == 6
    missing = lclient.get(f"/api/talent-edge/{S}/Swampwater Tech")
    assert missing.status_code == 404 and "Florida" in missing.json()["data"]["validTeams"]
    assert lclient.get(f"/api/talent-edge/{S}/compare", params={"teamA": "Florida", "teamB": "Nobody"}).status_code == 404
    assert lclient.get(f"/api/talent-edge/{S - 1}/Florida").status_code == 503, "a season with no table"
    assert state.talent_edge_stores[S].players("Florida"), "the players are kept for Circle of Blame"


def test_the_same_inputs_give_the_same_file(lclient: TestClient):
    state = lclient.app_state  # type: ignore[attr-defined]
    path = state.settings.data_dir / "season" / str(S) / "talent-edge.json"
    assert lclient.portal.call(state.jobs.run, "talent_edge")["status"] == "ok"
    first = path.read_bytes()
    assert lclient.portal.call(state.jobs.run, "talent_edge")["status"] == "ok"
    assert path.read_bytes() == first


def test_a_run_without_its_data_fails_and_keeps_the_last_good_table(lclient: TestClient):
    state = lclient.app_state  # type: ignore[attr-defined]
    assert lclient.portal.call(state.jobs.run, "talent_edge")["status"] == "ok"
    path = state.settings.data_dir / "season" / str(S) / "talent-edge.json"
    good = path.read_bytes()
    state.cfbd.cache.clear()  # nothing cached to fall back on
    lclient.upstream.fail = lambda p: p == "/roster"  # type: ignore[attr-defined]
    run = lclient.portal.call(state.jobs.run, "talent_edge")
    assert run["status"] == "failed" and "roster:" in run["message"]
    assert path.read_bytes() == good
    assert lclient.get(f"/api/talent-edge/{S}/Florida").status_code == 200, "the pages keep the last good week"
    checks = {c["name"]: c for c in lclient.get("/api/health").json()["data"]["checks"]}
    assert checks["weekly jobs"]["status"] == "degraded"


def test_the_routes_start_and_report_a_run(lclient: TestClient):
    assert lclient.post("/api/jobs/talent_edge/run", json={}).status_code == 422
    assert lclient.post("/api/jobs/nope/run", json={"confirm": True}).status_code == 404
    started = lclient.post("/api/jobs/talent_edge/run", json={"confirm": True})
    assert started.status_code == 200
    run_id = started.json()["data"]["run"]["id"]
    state = lclient.app_state  # type: ignore[attr-defined]


    async def finished() -> None:
        if state.jobs._task is not None:
            await state.jobs._task

    lclient.portal.call(finished)
    assert lclient.get(f"/api/jobs/runs/{run_id}").json()["data"]["status"] == "ok"
    assert lclient.get("/api/jobs/runs/nope").status_code == 404
    status = lclient.get("/api/jobs").json()["data"]
    assert status["jobs"]["talent_edge"]["status"] == "ok" and status["running"] is None
    assert lclient.get("/api/settings").json()["data"]["housekeeping"]["jobs"]["jobs"]["talent_edge"]["label"] == "Talent Edge"


# --- the command line ---------------------------------------------------------------------------------------------


class Server:
    def __init__(self, start: tuple[int, Any], runs: list[dict[str, Any]], health: int = 200) -> None:
        self.start = start
        self.runs = list(runs)
        self.health = health
        self.calls: list[tuple[str, str, Any]] = []

    def __call__(self, method: str, path: str, body: Any = None) -> tuple[int, Any]:
        self.calls.append((method, path, body))
        if path == "/api/health":
            if self.health == 0:
                raise OSError("refused")
            return self.health, {}
        if method == "POST":
            return self.start
        return 200, {"data": self.runs.pop(0) if len(self.runs) > 1 else self.runs[0]}


def test_the_command_asks_the_running_server_and_follows_the_run(settings: Settings):
    running = {"id": "talent_edge-1", "job": "talent_edge", "status": "running"}
    done = {"id": "talent_edge-1", "job": "talent_edge", "status": "ok", "week": 9, "message": "138 teams"}
    server = Server((200, {"data": {"run": running}}), [running, done])
    lines: list[str] = []
    assert cli_main("talent_edge", [], settings, http=server, sleep=lambda _s: None, out=lines.append) == 0
    assert ("POST", "/api/jobs/talent_edge/run", {"confirm": True}) in server.calls
    assert lines[-1] == "talent_edge finished, week 9: 138 teams"
    failed = Server((200, {"data": {"run": running}}), [{**done, "status": "failed", "message": "CFBD data missing"}])
    assert cli_main("talent_edge", [], settings, http=failed, sleep=lambda _s: None, out=lines.append) == 1
    busy = Server((409, {"data": None, "errors": [{"message": "weekly is running"}]}), [])
    assert cli_main("weekly", [], settings, http=busy, out=lines.append) == 2 and "weekly is running" in lines[-1]
    assert cli_main("weekly", ["--season", "2019"], settings, http=Server((200, {}), []), out=lines.append) == 2


def test_with_no_server_the_command_runs_here(settings: Settings, monkeypatch: pytest.MonkeyPatch):
    seen: dict[str, Any] = {}

    async def here(job: str, s: Settings) -> dict[str, Any]:
        seen.update(job=job, season=s.season)
        return {"job": job, "status": "ok", "message": "done here"}

    monkeypatch.setattr("app.jobs.cli._here", here)
    lines: list[str] = []
    assert cli_main("weekly", ["--season", "2025"], settings, http=Server((200, {}), [], health=0), out=lines.append) == 0
    assert seen == {"job": "weekly", "season": 2025} and lines[0].startswith("No server answered")
