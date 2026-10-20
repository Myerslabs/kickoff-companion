"""Freeze wave F3 (2026-10-20): one fact, one source.

- One coaches resolver: the game's notes, then the season's coaches load, then CFBD's head coach.
- The preseason load's season-long injuries join the Injury Report and the week's availability rows.
- The facts bands take CFBD's stadium figures where it has them.
- The Roster page's position groups badge the notes' order (lineup_orders).
- One record formatter on the front end (ui/dom.js recordText), tested in the fake browser."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from app.api.program import facts_with_venue
from app.cfbd.models import Coach
from app.services.coaches import cfbd_head_coach, resolve
from app.services.injuries import season_long_rows
from app.services.players import depth_for, lineup_orders
from tests.fakedom import needs_node, run_scenario

# --- the coaches resolver ---------------------------------------------------------------------------------------------


def test_the_notes_outrank_the_load_which_outranks_cfbd():
    out = resolve("Alpha", notes={"headCoach": "Notes Head", "offensiveCoordinator": " "}, season={"headCoach": "Load Head", "offensiveCoordinator": "Load OC", "defensiveCoordinator": "Load DC"}, cfbd_head="CFBD Head")
    assert out["headCoach"] == "Notes Head" and out["offensiveCoordinator"] == "Load OC" and out["defensiveCoordinator"] == "Load DC"
    assert out["sources"] == {"headCoach": "notes", "offensiveCoordinator": "season", "defensiveCoordinator": "season"}
    assert out["source"] == "The game's notes" and out["team"] == "Alpha"


def test_cfbd_names_the_head_coach_only_and_an_empty_answer_names_nobody():
    out = resolve("Alpha", cfbd_head="CFBD Head")
    assert out["headCoach"] == "CFBD Head" and out["offensiveCoordinator"] is None and out["sources"] == {"headCoach": "cfbd"} and out["source"] == "CFBD"
    nobody = resolve("Alpha", notes="junk", season=None)
    assert nobody["headCoach"] is None and nobody["sources"] == {} and nobody["source"] is None


def test_cfbd_head_coach_reads_the_coaches_answer():
    records = [
        Coach.model_validate({"id": 1, "firstName": "Pat", "lastName": "Whistler", "seasons": [{"school": "Alpha", "year": 2025}, {"school": "Alpha", "year": 2026}]}),
        Coach.model_validate({"id": 2, "firstName": "Lee", "lastName": "Clipboard", "seasons": [{"school": "Beta", "year": 2026}]}),
        "junk",
    ]
    assert cfbd_head_coach(records, "Alpha", 2026) == "Pat Whistler"
    assert cfbd_head_coach(records, "Beta", 2026) == "Lee Clipboard"
    assert cfbd_head_coach(records, "Gamma", 2026) is None and cfbd_head_coach(records, "Alpha", 2024) is None


# --- the preseason injuries -------------------------------------------------------------------------------------------


def test_season_long_rows_carry_the_status_detail_and_return():
    rows = season_long_rows([
        SimpleNamespace(name="Hurt Guy", position="WR", status="Out for the season", detail="ACL", expectedReturn="2027"),
        SimpleNamespace(name="Sat Guy", position=None, status=None, detail=None, expectedReturn=None),
        SimpleNamespace(name="  ", position="QB", status="Out", detail=None, expectedReturn=None),
    ])
    assert rows == [
        {"name": "Hurt Guy", "team": None, "position": "WR", "status": "Out for the season", "note": "ACL; back 2027", "preseason": True},
        {"name": "Sat Guy", "team": None, "position": None, "status": "Not reported", "note": None, "preseason": True},
    ]
    assert season_long_rows(None) == []


# --- the stadium facts -------------------------------------------------------------------------------------------------


def test_facts_take_cfbd_stadium_figures_where_it_has_them():
    facts = {"school": "Alpha", "stadium": "Old Name Field", "capacity": 80000, "stadiumOpened": 1930, "founded": 1853}
    out = facts_with_venue(facts, {"venue": "Alpha Stadium", "capacity": 88548, "yearBuilt": 1930, "city": "Town"})
    assert out["stadium"] == "Alpha Stadium" and out["capacity"] == 88548 and out["stadiumOpened"] == 1930 and out["founded"] == 1853 and out["venueSource"] == "CFBD"
    assert facts["capacity"] == 80000, "the facts file's own dict is left alone"
    kept = facts_with_venue(facts, {"city": "Town", "capacity": 0, "venue": " ", "yearBuilt": True})
    assert kept["capacity"] == 80000 and kept["stadium"] == "Old Name Field" and kept["venueSource"] == "notes"
    assert facts_with_venue(None, {"venue": "X"}) is None and facts_with_venue(facts, None)["venueSource"] == "notes"


# --- the roster's badges ------------------------------------------------------------------------------------------------


def test_lineup_orders_by_name_and_the_number_only_for_a_name_the_roster_lacks():
    lineup = SimpleNamespace(slots=[
        SimpleNamespace(players=[SimpleNamespace(number=12, name="Q One"), SimpleNamespace(number=None, name="Q Two Jr."), "junk"]),
        SimpleNamespace(players=[SimpleNamespace(number=7, name="Back Two"), SimpleNamespace(number=12, name="Q One")]),  # a starter who also returns kicks keeps 1
        SimpleNamespace(players=[SimpleNamespace(number=3, name="T.J. Spelled-Odd")]),
        "junk",
    ])
    orders = lineup_orders(lineup)
    assert orders["names"] == {"q one": 1, "q two": 2, "back two": 1, "tj spelled odd": 1}
    assert orders["numbers"]["#12"] == (1, "q one") and orders["numbers"]["#7"] == (1, "back two") and orders["numbers"]["#3"] == (1, "tj spelled odd")
    roster = {"q one", "q two", "back two", "other seven", "tj spelledodd"}
    assert depth_for(orders, 12, "Q One", roster) == 1 and depth_for(orders, 99, "Q Two Jr.", roster) == 2
    assert depth_for(orders, 7, "Other Seven", roster) is None, "number 7 on the chart names Back Two, a roster player: the other number 7 gets nothing"
    assert depth_for(orders, 3, "TJ SpelledOdd", roster) == 1, "the chart's spelling is nobody the roster knows: the number decides"
    assert depth_for(orders, None, "Nobody", roster) is None
    assert lineup_orders(None) == {"names": {}, "numbers": {}} and lineup_orders(SimpleNamespace(slots=None))["names"] == {}


# --- the one record formatter, in the fake browser ---------------------------------------------------------------------

SCENARIOS = r"""
scenarios.records = async () => {
  const { recordText } = await import(moduleUrl("ui/dom.js"));
  assert.equal(recordText({ wins: 6, losses: 1 }), "6-1");
  assert.equal(recordText({ wins: 6, losses: 1, ties: 1 }), "6-1-1");
  assert.equal(recordText({ wins: 6, losses: 1, ties: 0 }), "6-1");
  assert.equal(recordText({ wins: "6", losses: 1 }), null);
  assert.equal(recordText(null), null);
  // every page writes its record through it: a tie reads the same on the cover, the schedule and the paper's box
  const { coachRow } = await import(moduleUrl("views/team.js"));
  assert.equal(coachRow({ wins: 6, losses: 2, ties: 1 }).recordText, "6-2-1");
};
"""


@needs_node
def test_every_page_writes_a_record_the_same_way(tmp_path: Path) -> None:
    run_scenario(tmp_path, SCENARIOS, "records")
