"""Phase 17 #21: penalties read out of the play text, the penalty book, and the route that serves it."""

from __future__ import annotations

import json
import re

import pytest

from app.live import penalties
from app.live.penalties import PENALTIES_FILE, penalties_in, penalty_book

RECORDED = [
    ("(12:40) PENALTY OUR False Start (#52 A.Lineman) 5 yards from OPP08 to OPP13. NO PLAY", "false-start", 5),
    ("pass incomplete short left PENALTY OPP Pass Interference (#22 B.Corner Jr.) 11 yard from OPP00", "pass-interference", 11),
    ("out of bounds PENALTY OUR UNR: Unnecessary Roughness (#25 C.Safety) 15 yards from OUR35", "unnecessary-roughness", 15),
    ("PENALTY O-U Delay Of Game (#12 D.Passer) 5 yards from OPP05 to OPP10. NO PLAY", "delay-of-game", 5),
    ("PENALTY Mascots Kick Catch Interference 15 yards", "kick-catch-interference", 15),
    ("rush for 11 yards PENALTY OPP Face Mask (#5 E.Backer) 9 yards to the OUR17", "face-mask", 9),
    ("PENALTY OUR Illegal Block In Back (#4 F.Gunner) 10 yards", "block-in-back", 10),
    ("PENALTY OPP Roughing The Kicker 15 yards", "roughing-the-kicker", 15),
]


@pytest.mark.parametrize(("text", "key", "yards"), RECORDED)
def test_each_recorded_shape_names_its_foul_and_yards(text, key, yards):
    found = penalties_in(text)
    assert [f["key"] for f in found] == [key]
    assert found[0]["yards"] == yards and found[0]["declined"] is False


def test_declined_offsetting_and_two_flags_on_one_play():
    assert penalties_in("PENALTY OPP Holding declined")[0] == {"key": "holding", "name": "Holding", "yards": None, "declined": True, "offsetting": False}
    two = penalties_in("PENALTY OUR Offside (#9 G.End) 5 yards, PENALTY OPP False Start 5 yards, off-setting")
    assert [f["key"] for f in two] == ["offside", "false-start"] and two[1]["offsetting"] is True


@pytest.mark.parametrize("junk", [None, 5, "", "rush for 3 yards", "PENALTY OPP Zorbing 5 yards", ["PENALTY"], {"text": "PENALTY"}, "PENALTY"])
def test_no_known_foul_is_an_empty_list(junk):
    assert penalties_in(junk) == []


def test_the_longest_name_wins():
    assert penalties_in("PENALTY OPP Roughing The Passer 15 yards")[0]["key"] == "roughing-the-passer"
    assert penalties_in("PENALTY OPP Running Into The Kicker 5 yards")[0]["key"] == "running-into-the-kicker"


def test_the_book_is_whole_and_points_at_the_rules_book():
    book = penalty_book()
    assert book["source"]["url"].startswith("https://") and book["source"]["url"].endswith(".pdf")
    keys = [p["key"] for p in book["penalties"]]
    assert len(keys) == len(set(keys)) >= 30
    aliases = [a.lower() for p in book["penalties"] for a in p["aliases"]]
    assert len(aliases) == len(set(aliases)), "an alias names one foul"
    for p in book["penalties"]:
        assert p["what"].strip() and p["calls"], p["key"]
        for call in p["calls"]:
            assert re.fullmatch(r"\d{1,2}-\d{1,2}(-\d{1,2})?", call["rule"]), (p["key"], call["rule"])
            assert isinstance(call["page"], int) and 1 <= call["page"] <= 260 and call["who"] and call["result"]


def test_a_broken_book_is_empty_not_a_crash(tmp_path, monkeypatch):
    bad = tmp_path / "penalties.json"
    for content in ["{not json", json.dumps({"penalties": "no"}), json.dumps({"penalties": [{"key": "x"}, "junk", None]})]:
        bad.write_text(content, encoding="utf-8")
        monkeypatch.setattr(penalties, "PENALTIES_FILE", bad)
        penalty_book.cache_clear()
        penalties._aliases.cache_clear()
        assert penalty_book()["penalties"] == []
        assert penalties_in("PENALTY OPP Holding 10 yards") == []
    monkeypatch.setattr(penalties, "PENALTIES_FILE", PENALTIES_FILE)
    penalty_book.cache_clear()
    penalties._aliases.cache_clear()


def test_the_route_serves_the_book(client):
    body = client.get("/api/rules/penalties").json()
    assert body["errors"] == [] and body["data"]["source"]["url"].endswith(".pdf")
    assert any(p["key"] == "holding" for p in body["data"]["penalties"])
