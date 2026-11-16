"""The notes laid out (Wave 5; owner 2026-11-15, the board "Build as drawn"):
three keys to the game, three or four of the program's own figures named by Claude and filled by the app, and the one matchup
to watch, each piece checked and left out on its own. Malformed layouts (missing keys, nulls, wrong types, empty lists,
unknown figures, lengths broken) never break the notes, the prompt asks for the layout with the figures to choose from, and a
new layout replaces the old one whole."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.services import notes_layout as L
from app.services import notes_paste
from app.services.notes import NotesFile, load_notes, notes_path
from tests.conftest import FakeCfbd
from tests.test_program import route_program

PROFILE = {
    "us": [
        {"side": "offense", "label": "Third down", "key": "third", "metric": "profile:third", "value": 0.42, "format": "pct", "higherIsBetter": True, "nationalRank": 49, "nationalOf": 138, "conferenceRank": 8, "conferenceOf": 16},
        {"side": "defense", "label": "Tackles for loss per game", "key": "tfl_pg", "metric": "profile:tfl_pg", "value": 6.889, "format": "1f", "higherIsBetter": True, "nationalRank": 13, "nationalOf": 138, "conferenceRank": 3, "conferenceOf": 16},
        {"side": "defense", "label": "Takeaways per game", "key": "takeaways_pg", "metric": "profile:takeaways_pg", "value": 1.778, "format": "1f", "higherIsBetter": True, "nationalRank": 7, "nationalOf": 138, "conferenceRank": 1, "conferenceOf": 16},
        {"side": "offense", "label": "Turnovers lost per game", "key": "to_lost_pg", "metric": "profile:to_lost_pg", "value": 0.778, "format": "1f", "nationalRank": 13, "nationalOf": 138},
        {"side": "offense", "label": "Broken", "metric": "profile:broken", "value": None},  # no number: never offered, never drawn
        "junk",
    ],
    "them": [
        {"side": "offense", "label": "Third down", "key": "third", "metric": "profile:third", "value": 0.349, "format": "pct", "nationalRank": 111, "nationalOf": 138, "conferenceRank": 16, "conferenceOf": 16},
        {"side": "offense", "label": "Turnovers lost per game", "key": "to_lost_pg", "metric": "profile:to_lost_pg", "value": 2.0, "format": "1f", "nationalRank": 129, "nationalOf": 138, "conferenceRank": 15, "conferenceOf": 16},
        {"side": "offense", "label": "NaN row", "metric": "profile:nan", "value": float("nan")},
        {"side": "offense", "label": "A bool", "metric": "profile:bool", "value": True},
    ],
    "games": {"us": 9, "them": 9},
}
ADVANCED = {"us": [{"side": "offense", "label": "Success rate", "metric": "advanced:offense_success_rate", "value": 0.439, "format": "pct", "nationalRank": 54, "nationalOf": 138}], "them": []}
SCHOOLS = {"us": "Florida", "them": "Kentucky"}
KEYS = [
    {"line": "Keep Philo upright.", "text": "Kentucky's front of Mi'Quise Humphrey-Grace, Cedric Works and Sam Greene faces a line that may start Caden Jones at right tackle."},
    {"line": "Take the ball away.", "text": "Kentucky gives it up more than almost anyone, and Florida takes it away more than almost anyone."},
    {"line": "Hold up without Thornton.", "text": "With Bryce Thornton and Dijon Johnson out, the backups face Kenny Minchey and Kenny Darby."},
]
NUMBERS = [{"team": "them", "metric": "profile:to_lost_pg"}, {"team": "us", "metric": "profile:takeaways_pg"}, {"team": "them", "metric": "profile:third"}, {"team": "us", "metric": "profile:tfl_pg"}]
WATCH = {"line": "Florida's right side against Kentucky's front.", "text": "With Emeka Ugorji's status unclear, Caden Jones may start at right tackle, and Aaron Philo is back as the starter."}
GOOD = {"keys": KEYS, "numbers": NUMBERS, "watch": WATCH}


@pytest.fixture(autouse=True)
def quiet_log():
    L._logged.clear()
    yield
    L._logged.clear()


def test_the_layout_as_drawn_is_filled_from_the_programs_own_numbers():
    out = L.resolve(GOOD, PROFILE, ADVANCED, SCHOOLS, "SEC")
    assert out and out["dropped"] == [] and out["conference"] == "SEC"
    assert [k["line"] for k in out["keys"]] == ["Keep Philo upright.", "Take the ball away.", "Hold up without Thornton."]
    assert [(n["team"], n["metric"]) for n in out["numbers"]] == [(n["team"], n["metric"]) for n in NUMBERS]
    third = out["numbers"][2]
    assert third == {"team": "them", "school": "Kentucky", "metric": "profile:third", "label": "Third down", "side": "offense", "value": 0.349, "format": "pct", "higherIsBetter": None, "rank": 111, "of": 138, "conferenceRank": 16, "conferenceOf": 16}
    assert out["watch"] == WATCH


def test_claude_never_writes_a_number_the_app_shows():
    sneaky = {**GOOD, "numbers": [{"team": "them", "metric": "profile:third", "value": 0.99, "rank": 1, "label": "Best in the land"}, *NUMBERS[1:]]}
    third = L.resolve(sneaky, PROFILE, ADVANCED, SCHOOLS)["numbers"][0]
    assert third["value"] == 0.349 and third["rank"] == 111 and third["label"] == "Third down", "the program's figure, never the answer's"


@pytest.mark.parametrize("layout", [None, "layout", 42, [], {}, {"keys": None, "numbers": None, "watch": None}, {"keys": [], "numbers": [], "watch": {}}])
def test_nothing_usable_draws_the_band_as_today(layout):
    assert L.resolve(layout, PROFILE, ADVANCED, SCHOOLS) is None


def test_a_bad_piece_is_left_out_alone():
    bad_keys = {**GOOD, "keys": [KEYS[0], {"line": None}, "junk", {"line": "One two three four five six seven eight nine.", "text": "Too long a line."}]}
    out = L.resolve(bad_keys, PROFILE, ADVANCED, SCHOOLS)
    assert out["keys"] == [] and len(out["numbers"]) == 4 and out["watch"], "the keys go; the numbers and the matchup stay"
    assert any("1 usable of the 3 needed" in d for d in out["dropped"])
    assert any("longer than 8 words" in d for d in out["dropped"])

    unknown = {**GOOD, "numbers": [{"team": "them", "metric": "profile:made_up"}, {"team": "nobody", "metric": "profile:third"}, {"metric": "profile:third"}, "junk", {"team": "us", "metric": 5}, NUMBERS[0], NUMBERS[0], NUMBERS[1]]}
    out = L.resolve(unknown, PROFILE, ADVANCED, SCHOOLS)
    assert out["numbers"] == [] and len(out["keys"]) == 3, "two known figures (one twice) are not a strip"
    assert any("profile:made_up is not in the program's numbers for them" in d for d in out["dropped"])

    long_watch = {**GOOD, "watch": {"line": "Short.", "text": " ".join(["word"] * 41)}}
    out = L.resolve(long_watch, PROFILE, ADVANCED, SCHOOLS)
    assert out["watch"] is None and len(out["keys"]) == 3 and len(out["numbers"]) == 4
    assert L.resolve({**GOOD, "watch": {"text": "No line."}}, PROFILE, ADVANCED, SCHOOLS)["watch"] is None
    assert L.resolve({**GOOD, "watch": "a string"}, PROFILE, ADVANCED, SCHOOLS)["watch"] is None


def test_four_keys_keep_three_and_five_figures_keep_four():
    more = {**GOOD, "keys": [*KEYS, {"line": "A fourth key.", "text": "Never shown."}], "numbers": [*NUMBERS, {"team": "us", "metric": "advanced:offense_success_rate"}]}
    out = L.resolve(more, PROFILE, ADVANCED, SCHOOLS)
    assert len(out["keys"]) == 3 and len(out["numbers"]) == 4


def test_without_the_programs_numbers_the_strip_waits_and_the_words_stay():
    for profile, advanced in ((None, None), ({}, {}), ({"us": "junk", "them": None}, {"us": [None]})):
        out = L.resolve(GOOD, profile, advanced, SCHOOLS)
        assert out["numbers"] == [] and len(out["keys"]) == 3 and out["watch"] == WATCH


def test_a_figure_that_is_not_a_number_is_never_offered_or_drawn():
    out = L.resolve({**GOOD, "numbers": [{"team": "us", "metric": "profile:broken"}, {"team": "them", "metric": "profile:nan"}, {"team": "them", "metric": "profile:bool"}, *NUMBERS[:2]]}, PROFILE, ADVANCED, SCHOOLS)
    assert out["numbers"] == []
    offered = {row["metric"] for row in L.figures(PROFILE, ADVANCED, SCHOOLS)}
    assert {"profile:broken", "profile:nan", "profile:bool"}.isdisjoint(offered)


def test_the_model_drops_bad_entries_and_never_raises():
    raw = {"gameId": 1, "layout": {"keys": [KEYS[0], None, 5, {"text": "no line"}, {"line": ["x"]}], "numbers": [NUMBERS[0], {"team": "us"}, None], "watch": ["not", "an", "object"]}}
    notes = NotesFile.model_validate(raw)
    assert [k.line for k in notes.layout.keys] == ["Keep Philo upright."]
    assert [(n.team, n.metric) for n in notes.layout.numbers] == [("them", "profile:to_lost_pg")]
    assert notes.layout.watch is None
    for layout in (None, "text", 7, [], {"keys": "x", "numbers": {}, "watch": 3}):
        assert NotesFile.model_validate({"gameId": 1, "sections": [{"heading": "H", "paragraphs": ["P."]}], "layout": layout}).sections, "the notes stay whatever the layout holds"


def test_a_notes_file_with_a_layout_loads(tmp_path: Path):
    path = notes_path(tmp_path, 9)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"gameId": 9, "author": "Claude", "layout": GOOD}), encoding="utf-8")
    notes, error = load_notes(tmp_path, 9)
    assert error is None and notes.layout.watch.line == WATCH["line"] and len(notes.layout.numbers) == 4


def test_the_figures_are_offered_side_by_side():
    rows = L.figures(PROFILE, ADVANCED, SCHOOLS)
    third = next(r for r in rows if r["metric"] == "profile:third")
    assert third["us"]["text"] == "42.0%" and third["them"]["text"] == "34.9%" and third["them"]["rank"] == 111
    success = next(r for r in rows if r["metric"] == "advanced:offense_success_rate")
    assert success["them"] is None
    text = L.figures_text(rows, "Florida", "Kentucky")
    assert "profile:third | Third down (offense) | Florida 42.0%, #49 of 138 | Kentucky 34.9%, #111 of 138" in text
    assert "advanced:offense_success_rate | Success rate (offense) | Florida 43.9%, #54 of 138 | Kentucky –" in text
    assert L.figures_text(None, "F", "K") == "" and L.figures_text(["junk", {"metric": 5}], "F", "K") == ""
    assert L._fmt(0.196, "+2f") == "+0.20" and L._fmt(401.2, "0f") == "401" and L._fmt(None, "1f") == "–" and L._fmt(3, None) == "3"


WHO = SimpleNamespace(school="Florida", name="Florida Gators", conference="SEC")
GAME = {"gameId": 401856884, "home": "Kentucky", "away": "Florida", "kickoff": "2026-11-14T23:15:00Z"}


def test_the_full_prompt_asks_for_the_layout_with_the_figures(tmp_path: Path):
    figures = L.figures(PROFILE, ADVANCED, SCHOOLS)
    prompt = notes_paste.build_prompt(tmp_path, WHO, {**GAME, "figures": figures}, 2026)
    assert '"layout"' in prompt and "exactly three keys to the game for Florida" in prompt and '"them" for Kentucky' in prompt
    assert "never write a number here" in prompt and "profile:third | Third down (offense) | Florida 42.0%, #49 of 138 | Kentucky 34.9%, #111 of 138" in prompt
    bare = notes_paste.build_prompt(tmp_path, WHO, GAME, 2026)
    assert '"layout"' in bare and 'leave "numbers" as an empty list' in bare and "profile:third |" not in bare
    assert '"layout"' not in notes_paste.build_parts_prompt(WHO, GAME, 2026, ["visitors"]), "a part's run asks for its part only"
    assert '"layout"' not in notes_paste.build_injury_prompt(WHO, GAME, 2026)


def test_an_edited_template_still_asks_for_the_layout(tmp_path: Path):
    notes_paste.write_template(tmp_path, "My own prompt for {team} against {opponent}. {shape}")
    prompt = notes_paste.build_prompt(tmp_path, WHO, {**GAME, "figures": L.figures(PROFILE, ADVANCED, SCHOOLS)}, 2026)
    assert prompt.startswith("My own prompt for Florida against Kentucky.") and '"layout"' in prompt and "profile:tfl_pg |" in prompt


def test_a_pasted_answer_keeps_its_layout(tmp_path: Path):
    answer = "Here you go:\n```json\n" + json.dumps({"gameId": 401856884, "author": "Claude", "sections": [{"heading": "Key matchups", "paragraphs": ["Words."]}], "sources": [{"label": "S", "url": "https://x"}], "layout": GOOD}) + "\n```"
    reading = notes_paste.read_answer(answer, 401856884)
    assert reading.notes is not None and reading.notes.layout is not None and len(reading.notes.layout.keys) == 3


def test_a_new_layout_replaces_the_old_whole_and_none_keeps_it(tmp_path: Path):
    first = NotesFile.model_validate({"gameId": 7, "author": "Claude", "sections": [{"heading": "A", "paragraphs": ["One."]}], "layout": GOOD})
    notes_paste.save_notes(tmp_path, 7, first)
    newer = {"keys": [{"line": "New one.", "text": "x"}, {"line": "New two.", "text": "y"}, {"line": "New three.", "text": "z"}], "numbers": NUMBERS[:3], "watch": {"line": "A new matchup."}}
    assert notes_paste.merge_notes(tmp_path, 7, NotesFile.model_validate({"gameId": 7, "author": "Claude", "layout": newer})) is True
    saved = json.loads(notes_path(tmp_path, 7).read_text(encoding="utf-8"))["layout"]
    assert [k["line"] for k in saved["keys"]] == ["New one.", "New two.", "New three."] and len(saved["numbers"]) == 3
    assert saved["watch"] == {"line": "A new matchup."}, "the old matchup's words never ride along with the new line"
    notes_paste.merge_notes(tmp_path, 7, NotesFile.model_validate({"gameId": 7, "author": "Claude", "sections": [{"heading": "B", "paragraphs": ["Two."]}]}))
    kept = json.loads(notes_path(tmp_path, 7).read_text(encoding="utf-8"))
    assert kept["layout"]["watch"] == {"line": "A new matchup."} and kept["sections"][0]["heading"] == "B", "an answer without a layout keeps the one there"


class FakeService:
    def __init__(self, result=None, error: Exception | None = None) -> None:
        self.result, self.error, self.asked = result, error, []

    async def program(self, game_id):
        self.asked.append(game_id)
        if self.error:
            raise self.error
        return self.result


def test_the_figures_come_from_the_programs_answer_or_not_at_all():
    good = FakeService(SimpleNamespace(data={"game": {"gameId": 5}, "us": {"school": "Florida"}, "them": {"school": "Kentucky"}, "profile": PROFILE, "advanced": ADVANCED}))
    rows = asyncio.run(L.program_figures(good, 5))
    assert good.asked == [5] and any(r["metric"] == "profile:third" for r in rows)
    assert asyncio.run(L.program_figures(FakeService(error=RuntimeError("CFBD down")), 5)) is None
    assert asyncio.run(L.program_figures(FakeService(SimpleNamespace(data={"game": None})), 5)) is None
    assert asyncio.run(L.program_figures(FakeService(None), 5)) is None
    assert asyncio.run(L.program_figures(None, 5)) is None and asyncio.run(L.program_figures(good, "5")) is None


def test_the_program_carries_the_layout_filled_from_its_own_numbers(client: TestClient, fake_cfbd: FakeCfbd):
    route_program(fake_cfbd)
    first = client.get("/api/program/next").json()["data"]
    game_id = first["game"]["gameId"]
    us = [r for r in first["profile"]["us"] if isinstance(r.get("value"), int | float)]
    them = [r for r in first["profile"]["them"] if isinstance(r.get("value"), int | float)]
    assert len(us) >= 2 and len(them) >= 2, "the fixtures' program has a profile for both teams"
    numbers = [{"team": "us", "metric": us[0]["metric"]}, {"team": "them", "metric": them[0]["metric"]}, {"team": "us", "metric": us[1]["metric"]}, {"team": "them", "metric": "profile:made_up"}]
    path = notes_path(client.app.state.settings.data_dir, game_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"gameId": game_id, "author": "Claude", "writtenAt": "2026-11-14T18:00:00Z", "sections": [{"heading": "Key matchups", "paragraphs": ["Words."]}], "layout": {"keys": KEYS, "numbers": numbers, "watch": WATCH}}), encoding="utf-8")
    data = client.get(f"/api/program/{game_id}").json()["data"]
    layout = data["notes"]["layout"]
    assert len(layout["keys"]) == 3 and layout["watch"]["line"] == WATCH["line"]
    assert [n["metric"] for n in layout["numbers"]] == [us[0]["metric"], them[0]["metric"], us[1]["metric"]]
    assert layout["numbers"][0]["value"] == us[0]["value"] and layout["numbers"][1]["value"] == them[0]["value"]
    assert any("profile:made_up" in d for d in layout["dropped"])
    path.unlink()
    assert client.get(f"/api/program/{game_id}").json()["data"]["notes"]["layout"] is None, "no notes, no layout"


def test_the_notes_prompt_route_names_the_figures(client: TestClient, fake_cfbd: FakeCfbd):
    route_program(fake_cfbd)
    body = client.get("/api/notes/prompt").json()
    prompt = body["data"]["prompt"]
    assert '"layout"' in prompt and "| what it is |" in prompt and "profile:" in prompt
