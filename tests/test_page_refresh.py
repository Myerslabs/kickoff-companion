"""Run with Claude (batch 4 part 3, owner 2026-11-19): the page a route names, what a refresh changed, the log no one is shown,
and the refresh block every prompt carries."""
from __future__ import annotations

import json
from pathlib import Path

from app.services.page_refresh import MAX_PATHS, Page, RefreshLog, diff, page_of
from app.services.writing import REFRESH_RULES, build_prompt, refresh_text


def test_the_page_a_route_names() -> None:
    assert page_of("#program") == Page("pre", None), "the bare Pre-Game is the next game's"
    assert page_of("#program=401") == Page("pre", 401)
    assert page_of("#program=401?tab=pre") == Page("pre", 401)
    assert page_of("#program=401?tab=post") == Page("post", 401), "a played game's Post-Game reached through #program"
    assert page_of("program=401") == Page("pre", 401)
    assert page_of("#postgame=9") == Page("post", 9)
    assert page_of("#postgame") is None, "a Post-Game names its game"
    assert page_of("#preseason") == Page("preseason")
    assert page_of("#season") == Page("season")
    assert page_of("#review") == Page("book")
    assert page_of("#newspaper") == Page("paper")
    assert page_of("#picks") == Page("picks") and page_of("#top25") == Page("picks")
    assert page_of("#trivia") == Page("trivia") and page_of("#blame") == Page("season")
    for none in ("#season?team=Georgia", "#program=401?team=Vanderbilt", "#newspaper?team=Georgia", "#season=Georgia", "#review=2025", "#standings", "#settings", "", "#", "x", None, 7, ["#program"], "#program=-3", "#program=abc"):
        assert page_of(none) is None, none
    assert Page("pre", 1).label == "The Pre-Game Program" and Page("zzz").label == "This page"


def test_what_a_refresh_changed() -> None:
    before = {"headline": "Old", "keys": ["A", "B"], "writtenAt": "2026-11-18", "sources": [{"label": "ESPN"}]}
    after = {"headline": "New", "keys": ["A"], "writtenAt": "2026-11-19", "sources": [{"label": "ESPN"}, {"label": "247"}], "extra": {"x": 1}}
    d = diff(before, after)
    assert (d["added"], d["removed"], d["changed"]) == (2, 1, 1)
    assert d["paths"]["changed"] == ["headline"] and d["paths"]["removed"] == ["keys[1]"]
    assert "sources[1].label" in d["paths"]["added"] and "extra.x" in d["paths"]["added"]
    assert diff(None, {"a": 1})["added"] == 1 and diff({"a": 1}, None)["removed"] == 1
    assert diff(None, None)["added"] == 0
    assert diff({"a": []}, {"a": [1]})["added"] == 1
    big = diff({}, {"k": list(range(MAX_PATHS * 2))})
    assert big["added"] == MAX_PATHS * 2 and len(big["paths"]["added"]) == MAX_PATHS


def test_the_log_no_one_is_shown(tmp_path: Path) -> None:
    book = RefreshLog(tmp_path)
    book.add({"route": "#program=1", "piece": "notes", "ok": True})
    book.add({"route": "#program=1", "piece": "scout", "ok": False, "error": "x"})
    with book.path.open("a", encoding="utf-8") as handle:
        handle.write("not json\n[1]\n")
    rows = book.rows()
    assert [r["piece"] for r in rows] == ["notes", "scout"], "a damaged line is skipped"
    assert book.path == tmp_path / "claude" / "refresh-log.jsonl"
    assert RefreshLog(tmp_path / "none").rows() == []


def test_the_log_never_raises(tmp_path: Path) -> None:
    blocker = tmp_path / "claude"
    blocker.write_text("a file where the folder goes", encoding="utf-8")
    RefreshLog(tmp_path).add({"x": 1})  # logged, not raised


def test_the_refresh_block() -> None:
    text = refresh_text({"headline": "Gators roll", "keys": ["Run the ball"]})
    assert REFRESH_RULES in text and "Gators roll" in text and "remove what is out of date" in text
    long = refresh_text({"a": "x" * 20_000}, limit=500)
    assert "(cut short)" in long and len(long) < 2_000
    plain = build_prompt("scout", "Florida", {"opponent": "Vanderbilt"})
    assert REFRESH_RULES not in plain, "a first run has no refresh block"
    again = build_prompt("scout", "Florida", {"opponent": "Vanderbilt"}, so_far={"summary": "Vandy is solid.", "writtenAt": "2026-11-18T10:00Z", "model": "m"})
    assert REFRESH_RULES in again and "Vandy is solid." in again
    tail = again[again.index("What the page shows now:"):]
    assert "writtenAt" not in tail and '"model"' not in tail, "the stamps stay out of what Claude refreshes"
    json.loads(tail.split("```json\n", 1)[1].split("\n```", 1)[0])
