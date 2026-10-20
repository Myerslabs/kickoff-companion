"""The playoff picture (owner 2026-10-20): if the season ended today, every week, as a bracket.

Rules-based from the Season page's answers: the five highest-ranked conference leaders in, seven at large, straight
seeding, seeds 1 to 4 with a bye, the first round at the higher seed's home; the AP poll until the committee ranks."""

from __future__ import annotations

from app.cfbd.models import PollWeek, TeamRecords, TeamSP
from app.services.playoff import PLAYOFF_FORMAT, conference_leaders, picture, playoff_block


def rec(team: str, conference: str | None, cw: int, cl: int, w: int, losses: int) -> TeamRecords:
    return TeamRecords.model_validate({"team": team, "year": 2026, "conference": conference, "total": {"games": w + losses, "wins": w, "losses": losses, "ties": 0}, "conferenceGames": {"games": cw + cl, "wins": cw, "losses": cl, "ties": 0}})


def sp(team: str, rating: float) -> TeamSP:
    return TeamSP.model_validate({"team": team, "year": 2026, "rating": rating})


def poll(week: int, name: str, schools: list[tuple[int, str]]) -> PollWeek:
    return PollWeek.model_validate({"season": 2026, "seasonType": "regular", "week": week, "polls": [{"poll": name, "ranks": [{"rank": r, "school": s} for r, s in schools]}]})


RECORDS = [
    rec("A1", "Alpha", 3, 0, 6, 0), rec("A2", "Alpha", 2, 1, 5, 1), rec("A3", "Alpha", 1, 2, 4, 2), rec("A4", "Alpha", 0, 3, 3, 3),
    rec("B1", "Beta", 3, 0, 6, 0), rec("B2", "Beta", 2, 1, 5, 1), rec("B3", "Beta", 1, 2, 4, 2), rec("B4", "Beta", 0, 3, 2, 4),
    rec("C1", "Gamma", 2, 0, 6, 0), rec("C2", "Gamma", 1, 1, 5, 1), rec("C3", "Gamma", 0, 2, 4, 2),
    rec("D1", "Delta", 2, 0, 5, 1), rec("D2", "Delta", 1, 1, 5, 1), rec("D3", "Delta", 0, 2, 4, 2),
    rec("E1", "Epsilon", 2, 0, 5, 1), rec("E2", "Epsilon", 0, 2, 2, 4),
    rec("N1", "FBS Independents", 0, 0, 6, 0),
]
SP = [sp("D1", 12.0), sp("B4", 5.0), sp("E2", 1.0), sp("A1", 30.0)]
AP_WEEK_7 = [(1, "A1"), (2, "B1"), (3, "A2"), (4, "B2"), (5, "C1"), (6, "C2"), (7, "B3"), (8, "A3"), (9, "C3"), (10, "D2"), (11, "D3"), (12, "E1"), (13, "N1"), (20, "A4")]
AP_WEEK_6 = [(1, "B1"), (2, "A1"), (3, "A2"), (4, "B2"), (5, "C1"), (6, "C2"), (7, "B3"), (8, "A3"), (9, "D2"), (10, "C3"), (11, "D3"), (12, "E1"), (13, "N1")]
TEAMS = {r.team: {"conference": r.conference, "abbreviation": r.team} for r in RECORDS}


def test_the_leaders_follow_the_conference_record_then_the_ranking():
    position = {"A1": 1, "B1": 2, "D2": 10, "D1": 21}
    leaders = conference_leaders(RECORDS, TEAMS, position)
    assert leaders["Alpha"] == "A1" and leaders["Beta"] == "B1" and leaders["Gamma"] == "C1"
    assert leaders["Delta"] == "D1", "the conference record decides, not the poll"
    assert "FBS Independents" not in leaders, "an independent has no title to win"
    # a conference with no conference game yet goes by the ranking
    fresh = [rec("X1", "Zeta", 0, 0, 2, 0), rec("X2", "Zeta", 0, 0, 1, 1)]
    assert conference_leaders(fresh, {}, {"X2": 9})["Zeta"] == "X2"
    assert conference_leaders(fresh, {}, {})["Zeta"] == "X1", "then the record"


def test_the_field_is_five_champions_and_seven_at_large_seeded_straight():
    pic = picture([poll(6, "AP Top 25", AP_WEEK_6), poll(7, "AP Top 25", AP_WEEK_7)], RECORDS, SP, "C3", TEAMS)
    assert pic["source"] == "AP" and pic["week"] == 7 and pic["previousWeek"] == 6
    seeds = {e["school"]: e["seed"] for e in pic["field"]}
    assert seeds == {"A1": 1, "B1": 2, "A2": 3, "B2": 4, "C1": 5, "C2": 6, "B3": 7, "A3": 8, "C3": 9, "D2": 10, "E1": 11, "D1": 12}
    champions = {e["conference"]: e for e in pic["champions"]}
    assert all(champions[c]["in"] for c in ("Alpha", "Beta", "Gamma", "Delta", "Epsilon"))
    by_school = {e["school"]: e for e in pic["field"]}
    assert by_school["D1"]["autoBid"] and by_school["D1"]["rankBasis"] == "SP+" and by_school["D1"]["champion"] == "Delta", "an unranked leader is placed by SP+ and still in"
    assert by_school["A2"]["autoBid"] is False and by_school["A2"]["champion"] is None
    assert [e["school"] for e in pic["firstFourOut"]] == ["D3", "N1", "A4", "B4"]
    assert [e["seed"] for e in pic["lastFourIn"]] == [7, 8, 9, 10]
    assert pic["format"] == PLAYOFF_FORMAT and len(pic["field"]) == PLAYOFF_FORMAT["teams"]


def test_the_bracket_pairs_the_seeds_the_standard_way():
    pic = picture([poll(7, "AP Top 25", AP_WEEK_7)], RECORDS, SP, "A1", TEAMS)
    first = pic["bracket"]["firstRound"]
    assert [(g["home"]["seed"], g["away"]["seed"]) for g in first] == [(8, 9), (5, 12), (7, 10), (6, 11)]
    assert [q["home"]["seed"] for q in pic["bracket"]["quarterfinals"]] == [1, 4, 2, 3]
    assert [q["from"] for q in pic["bracket"]["quarterfinals"]] == ["FR1", "FR2", "FR3", "FR4"]
    assert pic["bracket"]["semifinals"][0]["from"] == ["QF1", "QF2"] and pic["bracket"]["final"]["from"] == ["SF1", "SF2"]
    assert first[0]["label"] == "(9) at (8)"


def test_our_line_names_the_seed_the_host_or_the_place_out():
    weeks = [poll(7, "AP Top 25", AP_WEEK_7)]
    assert picture(weeks, RECORDS, SP, "A1", TEAMS)["us"] == {"school": "A1", "seed": 1, "status": "bye", "outBy": None, "line": "A1: the 1st seed, with a first-round bye"}
    assert picture(weeks, RECORDS, SP, "A3", TEAMS)["us"]["line"] == "A3: the 8th seed, hosting (9) C3"
    assert picture(weeks, RECORDS, SP, "C3", TEAMS)["us"]["line"] == "C3: the 9th seed, at (8) A3"
    out = picture(weeks, RECORDS, SP, "D3", TEAMS)["us"]
    assert out["status"] == "out" and out["outBy"] == 1 and out["line"] == "D3: the 1st team out"
    assert picture(weeks, RECORDS, SP, "E2", TEAMS)["us"]["line"].startswith("E2: out, ")
    assert picture(weeks, RECORDS, SP, "Nobody", TEAMS)["us"]["status"] == "unknown"


def test_last_week_gives_each_team_its_move():
    pic = picture([poll(6, "AP Top 25", AP_WEEK_6), poll(7, "AP Top 25", AP_WEEK_7)], RECORDS, SP, "C3", TEAMS)
    by_school = {e["school"]: e for e in pic["field"]}
    assert by_school["A1"]["lastSeed"] == 2 and by_school["B1"]["lastSeed"] == 1, "the poll swapped the top two"
    assert by_school["C3"]["lastSeed"] == 10 and by_school["D2"]["lastSeed"] == 9
    assert by_school["A2"]["lastSeed"] == 3


def test_the_committee_outranks_the_ap_poll_once_it_speaks():
    committee = poll(10, "Playoff Committee Rankings", [(1, "B1"), (2, "A1"), (3, "C1")] + [(r, s) for r, s in AP_WEEK_7 if s not in ("A1", "B1", "C1")][:9])
    pic = picture([poll(7, "AP Top 25", AP_WEEK_7), poll(10, "AP Top 25", AP_WEEK_7), committee], RECORDS, SP, "B1", TEAMS)
    assert pic["source"] == "committee" and pic["sourceLabel"] == "the committee's ranking" and pic["week"] == 10
    assert pic["field"][0]["school"] == "B1" and pic["previousWeek"] is None, "the committee's first week has no last week"
    assert picture([], RECORDS, SP, "B1", TEAMS) is None, "no poll, no picture"


def test_the_band_carries_the_picture_before_the_committee_ranks():
    block = playoff_block([poll(7, "AP Top 25", AP_WEEK_7)], [], "C3", TEAMS, records=RECORDS, sp=SP)
    assert block is not None and block["rankings"] == [] and block["rounds"] == []
    assert block["picture"]["us"]["seed"] == 9
    assert playoff_block([], [], "C3", TEAMS, records=RECORDS, sp=SP) is None
    assert playoff_block([poll(7, "AP Top 25", AP_WEEK_7)], [], "C3", TEAMS) is None, "without records (the old callers) no picture and no band"
