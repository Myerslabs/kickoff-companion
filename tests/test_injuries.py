"""The Injury Report (owner 2026-10-10): a team's injuries week by week from the game notes' availability reports.

The service reads only the cached schedule and the notes files (no CFBD call). Rows are given to a team by their own
`team` field, else by the school named at the start of the note, the longest name winning; a row naming neither team
is kept apart, never guessed. Broken, missing and empty notes files never break the page."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from app.services.injuries import injury_report, row_team, team_names
from app.services.notes import AvailabilityRow, load_notes

US = "Swampwater Tech"
TEAMS = {
    US: {"school": US, "mascot": "Mudpuppies", "abbreviation": "SWT"},
    "Diner Tech": {"school": "Diner Tech", "mascot": "Cooks", "abbreviation": "DT"},
    "Diner Tech State": {"school": "Diner Tech State", "mascot": "Grills", "abbreviation": "DTS"},
    "Lake Effect": {"school": "Lake Effect", "mascot": "Squalls", "abbreviation": "LE"},
}


def game(gid: int, week: int, home: str, away: str, completed: bool, **extra) -> SimpleNamespace:
    return SimpleNamespace(id=gid, week=week, home_team=home, away_team=away, completed=completed, start_date=f"2026-09-{week or 30:02d}T19:00:00Z", neutral_site=False, season_type="regular", notes=None, **extra)


GAMES = [
    game(1, 1, US, "Lake Effect", True),
    game(2, 2, "Diner Tech", US, True),
    game(3, 3, US, "Diner Tech State", False),
    game(4, 4, "Lake Effect", US, False),
]


def write(data_dir: Path, gid: int, payload: object) -> None:
    folder = data_dir / "notes"
    folder.mkdir(exist_ok=True)
    (folder / f"{gid}.json").write_text(payload if isinstance(payload, str) else json.dumps(payload), encoding="utf-8")


def report(data_dir: Path, team: str = US) -> dict:
    return injury_report(GAMES, lambda gid: load_notes(data_dir, gid), us=US, team=team, teams=TEAMS, season=2026)


def test_names_longest_first() -> None:
    names = team_names("Diner Tech", TEAMS["Diner Tech"])
    assert names[0] == "diner tech cooks" and "dt" in names and "cooks" in names
    assert team_names("Nowhere", None) == ["nowhere"]


def test_row_team_by_field_then_note_longest_name_wins() -> None:
    sides = {s: team_names(s, TEAMS[s]) for s in ("Diner Tech", "Diner Tech State")}
    assert row_team(AvailabilityRow(name="A", team="Diner Tech State"), sides) == ("Diner Tech State", False)
    assert row_team(AvailabilityRow(name="A", note="Diner Tech State. Knee"), sides) == ("Diner Tech State", True)
    assert row_team(AvailabilityRow(name="A", note="Diner Tech. Knee"), sides) == ("Diner Tech", True)
    assert row_team(AvailabilityRow(name="A", note="Diner Technical issue"), sides) == (None, False), "a name inside a longer word is no match"
    assert row_team(AvailabilityRow(name="A", note="ankle"), sides) == (None, False)
    assert row_team(AvailabilityRow(name="A", team="  "), sides) == (None, False)


def test_a_longer_name_a_suffix_or_a_shared_mascot_is_never_guessed() -> None:
    """Review 2026-10-10: "Lake Effect St." is no Lake Effect, in the team field or in the note; a name both teams share
    (a mascot) settles nothing; a parenthesis after the name is another school."""
    teams = {"Lake Effect": {"mascot": "Squalls", "abbreviation": "LE"}, "Diner Tech": {"mascot": "Squalls", "abbreviation": "DT"}}
    sides = {s: team_names(s, teams[s]) for s in teams}
    assert row_team(AvailabilityRow(name="A", team="Lake Effect St."), sides) == (None, False)
    assert row_team(AvailabilityRow(name="A", note="Lake Effect St. Knee"), sides) == (None, False)
    assert row_team(AvailabilityRow(name="A", note="Lake Effect (OH) knee"), sides) == (None, False)
    assert row_team(AvailabilityRow(name="A", team="Squalls"), sides) == (None, False), "both teams' mascot"
    assert row_team(AvailabilityRow(name="A", team="Squalls", note="Diner Tech. Knee"), sides) == ("Diner Tech", True), "the note settles a shared mascot"
    assert row_team(AvailabilityRow(name="A", team="lake effect."), sides) == ("Lake Effect", False), "case and a trailing period are fine"
    assert row_team(AvailabilityRow(name="A", note="Lake Effect - ankle"), sides) == ("Lake Effect", True)
    assert row_team(AvailabilityRow(name="A", note="Lake Effect"), sides) == ("Lake Effect", True)


def test_our_report_newest_first_with_the_next_game(tmp_path: Path) -> None:
    write(tmp_path, 1, {"gameId": 1, "availability": [
        {"name": "Zed Out", "position": "WR", "status": "Out", "note": "Swampwater Tech. Knee, week 1"},
        {"name": "Al Probable", "position": "LB", "status": "Probable", "team": "Swampwater Tech", "note": "ankle"},
        {"name": "Them Guy", "position": "QB", "status": "Out", "note": "Lake Effect. Shoulder"},
        {"name": "Who Knows", "position": "OL", "status": "Questionable", "note": "hand"},
    ], "availabilitySource": "Conference report", "availabilityUpdatedAt": "2026-09-01"})
    data = report(tmp_path)
    assert data["isUs"] is True and data["team"]["school"] == US
    assert [g["gameId"] for g in data["games"]] == [3, 2, 1], "the next game, then the played ones, newest first"
    assert data["games"][0]["next"] is True and data["games"][0]["completed"] is False
    first = data["games"][-1]
    assert first["reported"] and first["source"] == "Conference report" and first["updatedAt"] == "2026-09-01"
    assert [r["name"] for r in first["rows"]] == ["Zed Out", "Al Probable"], "Out before Probable; the opponent's player is not ours"
    assert first["rows"][0]["note"] == "Knee, week 1", "the team named in the note is taken off it"
    assert first["rows"][1]["note"] == "ankle", "a row with its own team keeps its note"
    assert [r["name"] for r in first["unassigned"]] == ["Who Knows"], "a row naming neither team is kept apart"
    assert data["counts"] == {"games": 3, "reports": 1}
    assert data["games"][1]["notes"] is False and data["games"][1]["rows"] == []


def test_an_opponents_report_from_our_games_against_it(tmp_path: Path) -> None:
    write(tmp_path, 1, {"gameId": 1, "availability": [{"name": "Them Guy", "position": "QB", "status": "Out", "note": "Lake Effect Squalls; shoulder"}, {"name": "Who Knows", "status": "Questionable"}]})
    data = report(tmp_path, team="Lake Effect")
    assert data["isUs"] is False
    assert [g["gameId"] for g in data["games"]] == [4, 1], "both meetings, newest first"
    assert [r["name"] for r in data["games"][1]["rows"]] == ["Them Guy"]
    assert data["games"][1]["rows"][0]["note"] == "Shoulder"
    assert data["games"][1]["unassigned"] == [], "another team's report never shows the unplaced rows"
    assert data["games"][1]["rows"][0]["position"] == "QB"
    none = report(tmp_path, team="Diner Tech State")
    assert [g["gameId"] for g in none["games"]] == [3]


def test_broken_and_odd_notes_files_never_break_it(tmp_path: Path) -> None:
    write(tmp_path, 1, "{ not json")
    write(tmp_path, 2, [1, 2, 3])
    data = report(tmp_path)
    by_id = {g["gameId"]: g for g in data["games"]}
    assert by_id[1]["notes"] is False and "not valid JSON" in by_id[1]["error"]
    assert by_id[2]["notes"] is False and "object" in by_id[2]["error"]
    write(tmp_path, 1, {"gameId": 1, "availability": [{"name": "Only Name"}, {"position": "WR"}, "junk", None]})
    first = {g["gameId"]: g for g in report(tmp_path)["games"]}[1]
    assert first["unassigned"] == [{"name": "Only Name", "team": None, "position": None, "status": "Not reported", "note": None}], "a bad row is dropped, a bare one kept"


def test_no_games_and_postseason(tmp_path: Path) -> None:
    assert injury_report([], lambda gid: (None, None), us=US, team=US, teams=TEAMS, season=2026)["games"] == []
    bowl = game(9, None, US, "Diner Tech", True)
    bowl.season_type = "postseason"
    bowl.notes = "Vrbo Fiesta Bowl"
    data = injury_report([*GAMES[:2], bowl], lambda gid: (None, None), us=US, team=US, teams=TEAMS, season=2026)
    assert data["games"][0]["gameId"] == 9 and data["games"][0]["label"] == "Vrbo Fiesta Bowl"
