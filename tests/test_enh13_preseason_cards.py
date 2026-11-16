"""ENH-13, the Preseason page made visual (the owner's board of 2026-10-30, "Build it as drawn"): the picks beside the record so
far and its pace, the players to know with their numbers, the projected starters on the field with the arrivals and who still
starts, the storylines as cards; the season prompt asks for the three new parts."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.cfbd.models import PlayerStat
from app.services import season_prompts
from app.services.players import lines_from
from app.services.preseason_cards import now_block, record_of, stars_block, starters_block
from app.services.season_notes import Move, Outlook, PreseasonTeam, ProjectedStarters, Star
from tests.conftest import TEAM, follow_conference
from tests.fakedom import needs_node, run_scenario
from tests.test_season_notes import preseason_answer


def test_a_record_and_its_pace():
    assert record_of("7-5") == (7, 5) and record_of(" 10 - 2 ") == (10, 2) and record_of("7-5-1") == (7, 5)
    assert record_of("about seven") is None and record_of(None) is None
    line = lambda w, lo, t=0: SimpleNamespace(wins=w, losses=lo, ties=t)  # noqa: E731
    rec = SimpleNamespace(total=line(5, 2), conference_games=line(3, 2))
    got = now_block(rec, 12, 20, SimpleNamespace(overall="6-6"))
    assert got["overall"] == {"wins": 5, "losses": 2, "ties": 0} and got["conference"]["wins"] == 3 and got["apRank"] == 20
    assert got["pace"] == "9-3" and got["versus"] == "ahead", "5-2 carried over 12 games, ahead of a 6-6 pick"
    assert now_block(rec, 12, None, SimpleNamespace(overall="10-2"))["versus"] == "behind"
    assert now_block(rec, 12, None, SimpleNamespace(overall="9-3"))["versus"] == "on"
    assert now_block(rec, 12, None, None)["versus"] is None, "no pick: no verdict"
    assert now_block(SimpleNamespace(total=line(0, 0), conference_games=None), 12, None, None)["pace"] is None, "before a game: no pace"
    assert now_block(SimpleNamespace(total=line(5, 2)), None, None, None)["pace"] is None, "no schedule: no pace"
    assert now_block(None, 12, 3, None) is None and now_block(SimpleNamespace(total=SimpleNamespace(wins="x", losses=1)), 12, None, None) is None


def test_the_starters_new_and_still_starting():
    projected = ProjectedStarters.model_validate({"offense": [{"slot": "QB", "name": "Aaron Philo", "position": "QB"}, {"slot": "LT", "name": "Austin Barber"}, {"name": "no slot"}], "defense": [{"slot": "CB", "name": "Jordan Castell"}]})
    arrivals = [Move(name="Aaron Philo Jr.", kind="Transfer")]
    got = starters_block(projected, arrivals, {"aaron philo", "j castell"})
    qb, lt = got["offense"]
    assert len(got["offense"]) == 2, "a starter with no slot is left out"
    assert qb["new"] is True and lt["new"] is False, "an arrival is new, whatever his suffix"
    assert qb["startingNow"] is True and lt["startingNow"] is False and got["defense"][0]["startingNow"] is True, "matched by the first initial too"
    assert starters_block(projected, arrivals, None)["offense"][0]["startingNow"] is None, "no chart this week: no mark"
    assert starters_block(None, [], None) is None and starters_block(ProjectedStarters(), [], None) is None


def test_the_stars_matched_to_their_numbers():
    rows = [{"season": 2026, "playerId": "77", "player": "Aaron Philo", "position": "QB", "team": "Florida", "conference": "SEC", "category": "passing", "statType": st, "stat": v}
            for st, v in (("YDS", "1402"), ("ATT", "200"), ("TD", "11"), ("PCT", "0.66"))]
    lines = lines_from([PlayerStat.model_validate(r) for r in rows])
    stars = [Star(name="Aaron Philo", position="QB", honor="Davey O'Brien watch list", why="The offense runs through him.", source="https://example.com/a"), Star(name="Nobody Here", honor="Breakout pick", source="javascript:x")]
    got = stars_block(stars, lines)
    philo, nobody = got
    assert philo["playerId"] == "77" and philo["headshot"] == "/media/headshot/77"
    assert philo["numbers"][0] == {"value": "1,402", "label": "passing yards"} and len(philo["numbers"]) <= 3
    assert nobody["playerId"] is None and nobody["numbers"] == [] and nobody["source"] is None, "no numbers, never a bad link"
    assert stars_block([], {}) == []


def test_the_models_and_the_prompt_ask_for_the_parts():
    outlook = Outlook.model_validate({"predictedRecord": {"overall": "7-5", "conference": "4-4", "source": "ESPN FPI"}, "projectedStarters": {"offense": [{"slot": "QB", "name": "A"}, "junk"]}, "stars": [{"name": "B", "honor": "x"}, {"honor": "no name"}]})
    assert outlook.predictedRecord.overall == "7-5" and len(outlook.projectedStarters.offense) == 1 and len(outlook.stars) == 1, "damaged rows dropped"
    assert PreseasonTeam.model_validate({"school": "Florida", "outlook": {"summary": "x"}}).outlook.stars == []
    text = season_prompts.PRESEASON_PROMPT + season_prompts.preseason_shape("Florida") + season_prompts.SEASON_PROMPT
    for word in ("predictedRecord", "projectedStarters", "stars", "never a sportsbook"):
        assert word in text, word


@pytest.fixture
def routed(fake_cfbd, app):
    from tests.test_program import route_program

    route_program(fake_cfbd)
    follow_conference(app)
    return fake_cfbd


def test_the_preseason_page_carries_the_parts(client, routed, app):
    answer = preseason_answer(arrivals=[{"name": "New Guy", "kind": "Transfer", "detail": "from Elsewhere"}])
    answer = answer.replace('"predictions": [{"title": "Preseason poll", "detail": "No. 20"}]}', '"predictions": [{"title": "Preseason poll", "detail": "No. 20"}], "predictedRecord": {"overall": "6-6", "conference": "3-5"}, "projectedStarters": {"offense": [{"slot": "QB", "name": "New Guy"}]}, "stars": [{"name": "New Guy", "honor": "Breakout pick"}]}')
    assert '"predictedRecord"' in answer
    assert client.post("/api/season-notes/save", json={"kind": "preseason", "key": TEAM, "text": answer}).json()["data"]["saved"] is True
    ours = client.get("/api/preseason").json()["data"]["teams"][0]
    assert ours["school"] == TEAM
    assert ours["starters"]["offense"][0] == {**ours["starters"]["offense"][0], "slot": "QB", "name": "New Guy", "new": True}
    assert ours["stars"][0]["name"] == "New Guy" and ours["stars"][0]["honor"] == "Breakout pick"
    assert "now" in ours, "the record so far, when the season's records answer"


SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object \w+\]/;
const text = (node) => (node ? node.textContent : "");

const FL = {
  school: "Florida", conference: "SEC",
  now: { overall: { wins: 5, losses: 2, ties: 0 }, conference: { wins: 3, losses: 2, ties: 0 }, apRank: 20, games: 12, pace: "9-3", versus: "ahead" },
  stars: [
    { name: "Aaron Philo", position: "QB", honor: "Davey O'Brien watch list", why: "The offense runs through him.", playerId: "77", headshot: "/media/headshot/77", numbers: [{ value: "1,402", label: "passing yards" }, { value: "11", label: "TD" }] },
    { name: "Lacota Dippre", position: "TE", honor: "Breakout pick", why: null, playerId: null, headshot: null, numbers: [] },
    { name: "", honor: "no name" },
  ],
  starters: {
    offense: [{ slot: "QB", name: "Aaron Philo", new: true, startingNow: true }, { slot: "LT", name: "Emeka Ugorji", new: true, startingNow: false }, { slot: "C", name: "Center Man", new: false, startingNow: true }, { slot: "X", name: "Eric Singleton Jr.", new: true, startingNow: null }],
    defense: [{ slot: "CB", name: "Corner One", new: false, startingNow: true }, { slot: "FS", name: "Safety One", new: true, startingNow: false }],
  },
  preseason: {
    outlook: {
      predictedRecord: { overall: "6-6", conference: "3-5", source: "ESPN FPI, Aug 2026" },
      predictions: [{ title: "Conference media poll", detail: "picked 9th" }, { title: "Preseason AP poll", detail: "unranked (received votes)" }],
      storylines: [{ title: "Quarterback", detail: "Philo, then Jones late at Missouri." }],
      positionBattles: [{ title: "Left tackle", detail: "Two transfers." }],
    },
    departures: [{ name: "Caleb Banks", kind: "NFL draft", detail: "Round 1, pick 18 (Minnesota)" }, { name: "Jake Slaughter", kind: "NFL draft", detail: "Round 2" }, { name: "DJ Lagway", kind: "Transfer" }],
    arrivals: [{ name: "Aaron Philo", kind: "Transfer" }, { name: "Davian Groce", kind: "Freshman" }],
    coachingChanges: [{ title: "New head coach", detail: "Jon Sumrall" }],
  },
};

scenarios.parts = async () => {
  installWindow();
  await useTeam();
  const { picksPart, starsPart, startersPart, storiesPart } = await import(moduleUrl("views/preseason.js"));
  const picks = picksPart(FL);
  const pt = text(picks);
  assert.ok(pt.includes("Predicted") && pt.includes("6-6") && pt.includes("3-5 SEC") && pt.includes("ESPN FPI"), pt);
  assert.ok(pt.includes("picked 9th") && pt.includes("So far") && pt.includes("5-2") && pt.includes("No. 20 AP") && pt.includes("on pace for 9-3"), pt);
  assert.ok(pt.includes("ahead of the picks"));
  assert.ok(picks.querySelector(".pre-chip--good"), "green ahead of the pick");
  assert.ok(picks.querySelector(".pre-tile__value--words"), "a long prediction in words, not a big number");
  const stars = starsPart(FL);
  assert.equal(stars.querySelectorAll(".pre-star").length, 2, "a star with no name is left out");
  assert.equal(stars.querySelectorAll("button.pre-star").length, 1, "only a matched player opens his card");
  assert.ok(text(stars).includes("Davey O'Brien watch list") && text(stars).includes("1,402") && text(stars).includes("passing yards"));
  assert.ok(stars.querySelector("img").getAttribute("src") === "/media/headshot/77" && text(stars).includes("LD"), "a face, else the initials");
  const starters = startersPart(FL);
  assert.ok(text(starters).includes("gold ring: new this year") && text(starters).includes("green dot"), text(starters));
  assert.equal(starters.querySelectorAll(".pre-man").length, 4, "the offense first");
  assert.equal(starters.querySelectorAll(".pre-man--new").length, 3);
  assert.equal(starters.querySelectorAll(".pre-man__now").length, 2);
  const defense = starters.querySelectorAll(".seg button").find((b) => text(b) === "Defense");
  defense.click();
  assert.equal(starters.querySelectorAll(".pre-man").length, 2, "the defense on its own field");
  assert.equal(defense.getAttribute("aria-pressed"), "true");
  const stories = storiesPart(FL);
  const st = text(stories);
  assert.ok(st.includes("Quarterback") && st.includes("Position battle: Left tackle") && st.includes("Gone to the draft") && st.includes("2 picks, Caleb Banks"), st);
  assert.ok(st.includes("2 arrivals") && st.includes("1 transfer") && st.includes("4 of the 6 projected starters are new") && st.includes("A new staff"), st);
  for (const node of [picks, stars, starters, stories]) assert.ok(!RAW.test(text(node)), text(node));
  // nothing loaded: nothing drawn
  for (const fn of [picksPart, starsPart, startersPart, storiesPart]) assert.equal(fn({ school: "X" }), null);
  assert.equal(picksPart({ now: { overall: { wins: "x" } } }), null);
};
"""


@needs_node
def test_the_parts_in_a_fake_browser(tmp_path: Path) -> None:
    run_scenario(tmp_path, SCENARIOS, "parts")
