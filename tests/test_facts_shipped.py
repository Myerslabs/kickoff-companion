"""The preloaded facts (owner 2026-10-21): the file shipped with the app under the install's own facts, outside the season
folder with a date per school, the fields the trivia needs, the yearly refresh in the schedule's missing rule, the build
tool, and the shipped file itself covering every FBS school of the season."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from app.services import season_notes
from app.services.season_notes import FACTS_FRESH_DAYS, SHIPPED_FACTS, SeasonNotes, TeamFacts, shipped_facts
from tests.conftest import TEAM
from tools import facts_build

ROOT = Path(__file__).resolve().parents[1]
FBS_FIXTURE = ROOT / "tests" / "fixtures" / "cfbd" / "teams_fbs.json"


def shipped(tmp_path: Path, teams: dict, checked: str = "2026-10-21") -> Path:
    path = tmp_path / "shipped.json"
    path.write_text(json.dumps({"format": 1, "checkedAt": checked, "author": "test", "schools": len(teams), "teams": teams}), encoding="utf-8")
    return path


def test_the_shipped_file_sits_under_the_installs_own_facts(tmp_path: Path, monkeypatch):
    path = shipped(tmp_path, {TEAM: {"founded": 1900, "stadium": "Shipped Field", "conference": "Biscuit Belt", "mascotName": "Mud"}, "Other U": {"founded": 1950, "conference": "Biscuit Belt"}})
    monkeypatch.setattr(season_notes, "SHIPPED_FACTS", path)
    notes = SeasonNotes(tmp_path / "data", 2026)
    facts = notes.facts()
    assert facts["shipped"] == ["Other U", TEAM] and facts["teams"][TEAM]["shipped"] is True and facts["teams"][TEAM]["checkedAt"] == "2026-10-21"
    ours = notes.facts_for(TEAM)
    assert ours["stadium"] == "Shipped Field" and ours["mascotName"] == "Mud" and ours["shipped"] is True and ours["checkedAt"] == "2026-10-21" and ours["traditions"] == []
    # the install loads its own: that school is overlaid, the other stays shipped
    from app.services import season_prompts

    answer = json.dumps({"conference": "Biscuit Belt", "season": 2026, "author": "Chat", "teams": [{"school": TEAM, "founded": 1900, "stadium": "Own Field", "stadiumNickname": "The Bog", "firstSeason": 1906, "conferenceTitleYears": [1991, 1996], "winningestCoach": "Coach One, 100 wins (1990 to 2001)", "retiredNumbers": ["Player (No. 15)"], "traditions": ["The chomp"]}], "sources": [{"title": "s", "url": "https://x"}]})
    reading = season_prompts.read_facts(answer, "Biscuit Belt", [TEAM, "Other U"])
    assert reading.value is not None, reading.error
    kept = notes.save_facts(reading.value, "Biscuit Belt", [TEAM, "Other U"])
    assert kept["kept"] == [TEAM] and notes.facts_file == tmp_path / "data" / "facts.json" and notes.facts_file.is_file(), "the install's facts live outside the season folder"
    ours = notes.facts_for(TEAM)
    assert ours["stadium"] == "Own Field" and ours["stadiumNickname"] == "The Bog" and ours["firstSeason"] == 1906 and ours["conferenceTitleYears"] == [1991, 1996] and ours["retiredNumbers"] == ["Player (No. 15)"] and ours["traditions"] == ["The chomp"]
    assert ours["shipped"] is False and ours["checkedAt"] == ours["savedAt"]
    assert notes.facts_for("Other U")["shipped"] is True and notes.facts()["shipped"] == ["Other U"]
    assert notes.facts_for("Nobody") is None and notes.facts_for(None) is None


def test_the_seasons_old_facts_file_is_carried_over_once(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(season_notes, "SHIPPED_FACTS", tmp_path / "none.json")
    notes = SeasonNotes(tmp_path / "data", 2026)
    old = notes.dir / "facts.json"
    old.parent.mkdir(parents=True)
    old.write_text(json.dumps({"teams": {TEAM: {"founded": 1900, "conference": "Biscuit Belt", "savedAt": "2026-09-01T12:00:00Z"}}, "batches": {"Biscuit Belt": {"savedAt": "2026-09-01T12:00:00Z", "teams": 1, "of": 2}}}), encoding="utf-8")
    assert notes.facts_for(TEAM)["founded"] == 1900 and notes.facts_file.is_file(), "read from the season folder once, then kept outside it"
    assert notes.facts_for(TEAM)["checkedAt"] == "2026-09-01T12:00:00Z", "an older save counts as checked then"
    assert notes.facts()["shipped"] == []


def test_a_damaged_or_missing_shipped_file_leaves_the_installs_facts_working(tmp_path: Path, monkeypatch):
    path = tmp_path / "shipped.json"
    path.write_text("{broken", encoding="utf-8")
    monkeypatch.setattr(season_notes, "SHIPPED_FACTS", path)
    notes = SeasonNotes(tmp_path / "data", 2026)
    assert notes.facts() == {"teams": {}, "batches": {}, "shipped": []}
    assert shipped_facts(tmp_path / "missing.json") == {}
    path.write_text(json.dumps({"teams": {"A": {"founded": 1}, "bad": "junk"}}), encoding="utf-8")
    assert list(shipped_facts(path)["teams"]) == ["A"], "a bad row is dropped"


def test_stale_facts_and_the_status_say_so(tmp_path: Path, monkeypatch):
    assert SeasonNotes.facts_stale(None, date(2026, 10, 21)) and SeasonNotes.facts_stale("junk", date(2026, 10, 21))
    assert not SeasonNotes.facts_stale("2026-10-21", date(2026, 10, 21)) and not SeasonNotes.facts_stale("2026-10-21T15:00:00Z", date(2027, 10, 21))
    assert SeasonNotes.facts_stale("2026-10-21", date(2026, 10, 21).replace(year=2027, month=10, day=22))
    assert FACTS_FRESH_DAYS == 365
    path = shipped(tmp_path, {"A": {"founded": 1, "conference": "C"}, "B": {"founded": 2, "conference": "C"}}, checked="2025-01-01")
    monkeypatch.setattr(season_notes, "SHIPPED_FACTS", path)
    notes = SeasonNotes(tmp_path / "data", 2026)
    status = notes.status([TEAM], {"C": ["A", "B"]}, date(2026, 10, 21))
    batch = status["facts"][0]
    assert batch["saved"] == 2 and batch["shipped"] == 2 and batch["checkedAt"] == "2025-01-01" and batch["stale"] is True and status["factsSaved"] == 2
    fresh = shipped(tmp_path, {"A": {"founded": 1, "conference": "C"}}, checked="2026-10-01")
    monkeypatch.setattr(season_notes, "SHIPPED_FACTS", fresh)
    batch = SeasonNotes(tmp_path / "data2", 2026).status([TEAM], {"C": ["A", "B"]}, date(2026, 10, 21))["facts"][0]
    assert batch["saved"] == 1 and batch["stale"] is False, "a conference short of a school is missing, not stale"


def test_the_schedule_asks_again_for_facts_a_year_old(client, app, monkeypatch):
    rows = [{"conference": "C", "schools": 2, "saved": 2, "savedAt": None, "shipped": 2, "checkedAt": "2025-01-01", "stale": True}]
    monkeypatch.setattr(app.state.season_notes, "status", lambda *args, **kwargs: {"factsSaved": 2, "coachesOf": 2, "facts": rows})
    step = next(s for s in app.state.prompt_runs.steps if s.kind == "facts")
    assert client.portal.call(step.missing) == "facts a year old for the C"
    rows[0]["stale"] = False
    assert client.portal.call(step.missing) is None, "fresh and complete: nothing to ask"
    monkeypatch.setattr(app.state.season_notes, "status", lambda *args, **kwargs: {"factsSaved": 1, "coachesOf": 2, "facts": rows})
    assert client.portal.call(step.missing) == "1 of 2 teams"


def test_the_build_tool_merges_batches_and_names_what_is_missing(tmp_path: Path, capsys):
    fbs = tmp_path / "fbs.json"
    fbs.write_text(json.dumps([{"school": "Alpha U", "conference": "C", "classification": "fbs"}, {"school": "Beta U", "conference": "C", "classification": "fbs"}, {"school": "Gamma U", "conference": "D", "classification": "fbs"}, {"school": "Lower", "conference": "X", "classification": "fcs"}]), encoding="utf-8")
    batch = tmp_path / "c.json"
    batch.write_text(json.dumps({"conference": "C", "season": 2026, "author": "test", "sources": [{"title": "t", "url": "https://x"}], "teams": [
        {"school": "Alpha U", "founded": 1900, "stadium": "A Field", "stadiumOpened": 1930, "capacity": 50000, "firstSeason": 1901, "allTimeRecord": "500-300-10", "nationalTitles": [1950], "conferenceTitles": 3, "conferenceTitleYears": [1950, 1960, 1970], "heismans": ["Someone (1960)"], "bowlRecord": "10-5", "rivalries": [{"rival": "Beta U", "trophy": "The Cup", "firstMeeting": 1905, "record": "50-40-2"}], "headCoachRecord": "Coach, 20-10, since 2024", "winningestCoach": "Old Coach, 200 wins (1950 to 1975)", "longestWinStreak": "20 games (1951 to 1952)", "recordCrowd": "60,000, Beta U, 1999-11-20", "retiredNumbers": ["Someone (No. 1)"], "mascotName": "Al", "mascotOrigin": "A bird.", "colorsOrigin": "Blue and gold since 1900.", "fightSong": "Alpha Forever", "traditions": ["The walk"], "nflAlumni": ["A Player"], "dates": [{"date": "1901-10-05", "event": "The first game."}]},
        {"school": "Beta  U", "founded": 1910},
        {"school": "Stranger", "founded": 1},
    ]}), encoding="utf-8")
    out = tmp_path / "schools.json"
    code = facts_build.main([str(batch), "--fbs", str(fbs), "--checked", "2026-10-21", "--out", str(out)])
    printed = capsys.readouterr().out
    built = json.loads(out.read_text(encoding="utf-8"))
    assert code == 1 and built["schools"] == 1 and built["checkedAt"] == "2026-10-21" and list(built["teams"]) == ["Alpha U"]
    alpha = built["teams"]["Alpha U"]
    assert alpha["conference"] == "C" and alpha["checkedAt"] == "2026-10-21" and alpha["winningestCoach"].startswith("Old Coach") and alpha["sources"][0]["url"] == "https://x"
    assert "no facts for Beta U" in printed and "no facts for Gamma U" in printed and "Lower" not in printed, "every FBS school is wanted, no FCS one"
    assert "Stranger" in printed and "Beta  U" in printed, "a stranger and a misspelling are named"
    assert TeamFacts.model_validate({"school": "Alpha U", **{k: v for k, v in alpha.items() if k not in ("conference", "checkedAt", "sources")}}).mascotName == "Al"
    assert TeamFacts.model_validate({"school": "Old U", "founded": 1766, "stadiumOpened": "1599"}).model_dump(include={"founded", "stadiumOpened"}) == {"founded": 1766, "stadiumOpened": None}, "a colonial founding year is kept, a year before 1600 is not"


def test_the_shipped_file_covers_every_fbs_school_of_the_season():
    """The public tree carries no CFBD recording, so the coverage against the season's FBS list runs where the
    fixture is; the file's own shape and depth are checked everywhere."""
    assert SHIPPED_FACTS.is_file(), "app/facts/schools.json ships with the app"
    data = shipped_facts(SHIPPED_FACTS)
    assert data["checkedAt"] and len(data["teams"]) >= 130, "every FBS school of the season"
    if FBS_FIXTURE.is_file():
        fbs = facts_build.fbs_list(FBS_FIXTURE)
        missing = [s for s in fbs if s not in data["teams"]]
        assert not missing, f"no facts for {missing}"
        assert len(data["teams"]) >= len(fbs)
    thin = []
    for school, row in data["teams"].items():
        facts = TeamFacts.model_validate({**row, "school": school})
        if not facts.stadium or not facts.founded or len(facts.dates) < 3:
            thin.append(school)
        assert row.get("conference") and row.get("checkedAt"), school
    assert not thin, f"a stadium, a founding year and three dated events at least: {thin}"


@pytest.mark.skipif(not FBS_FIXTURE.is_file(), reason="the CFBD recordings stay private; the public tree has none")
def test_the_fbs_fixture_is_the_seasons_list():
    fbs = facts_build.fbs_list(FBS_FIXTURE)
    assert len(fbs) >= 130 and all(isinstance(c, str) and c for c in fbs.values())


# --- the preloading (owner 2026-10-22): coaches, rumored costs and the season load shipped for one season -------------


def _shipped(path: Path, season: int, teams: dict) -> Path:
    path.write_text(json.dumps({"format": 1, "season": season, "checkedAt": "2026-10-22", "author": "Claude research", "teams": teams}), encoding="utf-8")
    return path


def test_the_shipped_season_files_sit_under_the_installs_own_for_their_season(tmp_path: Path, monkeypatch):
    from app.services.season_notes import CoachesBatch, PreseasonTeam, TeamCoaches

    monkeypatch.setattr(season_notes, "SHIPPED_COACHES", _shipped(tmp_path / "coaches.json", 2026, {"Home U": {"conference": "Big Pie", "headCoach": "Shipped Coach", "offensiveCoordinator": "Ship OC", "defensiveCoordinator": None}, "Away U": {"conference": "Big Pie", "headCoach": "Away Coach"}, "bad": 5}))
    monkeypatch.setattr(season_notes, "SHIPPED_COSTS", _shipped(tmp_path / "costs.json", 2026, {"Home U": {"school": "Home U", "totalUsd": 20500000, "note": "rumored"}, "Broken U": {"school": 5}}))
    monkeypatch.setattr(season_notes, "SHIPPED_PRESEASON", _shipped(tmp_path / "preseason.json", 2026, {"Home U": {"school": "Home U", "staff": [{"name": "Shipped Coach", "role": "Head coach"}], "birthdates": []}, "Damaged U": {"staff": "x"}}))
    notes = SeasonNotes(tmp_path / "data", 2026)
    # every page reads the shipped rows, marked as such, with the shipped file's date
    assert notes.coaches_for("Home U")["headCoach"] == "Shipped Coach" and notes.coaches_for("Home U")["shipped"] is True
    assert notes.coaches_for("Home U")["checkedAt"] == "2026-10-22"
    assert notes.costs_for("Home U")["totalUsd"] == 20500000 and "Broken U" not in notes.costs()["teams"], "a damaged shipped row is left out"
    assert isinstance(notes.preseason_for("Home U"), PreseasonTeam) and "Damaged U" not in notes.preseason()
    # the install's own load wins, and saving never writes the shipped rows into the install's file
    batch = CoachesBatch(conference="Big Pie", teams=[TeamCoaches(school="Home U", headCoach="Own Coach")])
    notes.save_coaches(batch, "Big Pie", ["Home U", "Away U"])
    assert notes.coaches_for("Home U")["headCoach"] == "Own Coach" and notes.coaches_for("Home U")["shipped"] is False
    assert notes.coaches_for("Away U")["shipped"] is True
    own = json.loads(notes.coaches_path.read_text(encoding="utf-8"))
    assert list(own["teams"]) == ["Home U"], "the install's file holds its own rows only"
    # the status counts the shipped rows and their date, so Load data can say "Preloaded Oct 22"
    status = notes.status(["Home U"], {"Big Pie": ["Home U", "Away U"]}, date(2026, 10, 22))
    assert status["coachesSaved"] == 2 and status["coaches"][0]["shipped"] == 1 and status["shipped"]["coaches"] == 1
    assert status["preseason"][0]["shipped"] is True and status["preseason"][0]["checkedAt"] == "2026-10-22" and status["shipped"]["preseason"] == 1
    assert status["shipped"]["checkedAt"]["costs"] == "2026-10-22" and status["costsSaved"] == 1
    # last season's shipped files are not this season's
    assert SeasonNotes(tmp_path / "data", 2027).coaches_for("Away U") is None
    assert SeasonNotes(tmp_path / "data", 2027).preseason() == {}


def test_a_shipped_season_load_counts_as_loaded_for_the_reminder():
    from app.services.readiness import readiness

    status = {"season": 2026, "preseason": [{"school": "Home U", "savedAt": None, "shipped": True}], "coachesSaved": 2, "coachesOf": 2, "costsSaved": 2, "factsSaved": 2}
    assert readiness(status, None, None)["ready"] is True, "preloaded with the program: the To do does not nag"
    status["preseason"][0]["shipped"] = False
    assert readiness(status, None, None)["ready"] is False


def test_the_shipped_season_files_are_real_and_name_fbs_schools():
    """The files shipped tonight (2026-10-22): every FBS school's coaches; costs and the season load where found. The public
    tree carries no CFBD recording, so the names are checked against the season's FBS list where the fixture is; the
    files' own shape and depth are checked everywhere."""
    from tools.facts_build import fbs_list

    files = (season_notes.SHIPPED_DIR / "coaches.json", season_notes.SHIPPED_DIR / "costs.json", season_notes.SHIPPED_DIR / "preseason.json")
    for path in files:
        data = season_notes.shipped_file(path)
        assert data and data["season"] == 2026 and data["checkedAt"], path.name
    coaches = season_notes.shipped_file(files[0])["teams"]
    assert len(coaches) >= 130, "every FBS school's coaches"
    recording = Path(__file__).resolve().parent / "fixtures" / "cfbd" / "teams_fbs.json"
    if recording.is_file():
        fbs = fbs_list(recording)
        for path in files:
            assert set(season_notes.shipped_file(path)["teams"]) <= set(fbs), f"{path.name}: every school is an FBS school as CFBD spells it"
        assert len(coaches) == len(fbs), "every FBS school's coaches"
