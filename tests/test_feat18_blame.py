"""FEAT-18 Circle of Blame (Feature Set v2 Phase C): the report's checks (spec C.5 and C.9), each
rule with a failing case, and the season's reports on disk."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from app.services.blame import BlameStore, check_report, history, read_answer, week_key

PACK = json.dumps({"coaching": {"headCoach": "Jon Sumrall", "offensiveCoordinator": "Buster Faulkner"}, "players": [{"name": "DJ Lagway", "position": "QB"}]})


def ev(n: int = 2) -> list[dict[str, str]]:
    return [{"metric": f"Metric {i}", "value": str(10 + i), "context": "ranks 100th of 138"} for i in range(n)]


def good() -> dict:
    shares = [35, 25, 20, 12, 8]
    names = [("Offensive line", "unit"), ("Buster Faulkner", "coach"), ("DJ Lagway", "player"), ("Third-down defense", "scheme"), ("The schedule", "schedule")]
    return {
        "schema_version": "1",
        "season": 2026,
        "week": 9,
        "after_result": "loss",
        "verdict": "The line cannot block.",
        "slices": [{"name": n, "kind": k, "share_pct": s, "case": "The case.", "evidence": ev(), "trend": "up"} for (n, k), s in zip(names, shares, strict=True)],
        "movement": "First report of the season.",
        "limitations": ["No snap counts."],
        "confidence": "medium",
    }


def check(report: dict, pack: str = PACK) -> tuple[dict | None, list[str]]:
    return check_report(json.dumps(report), pack, 2026, 9)


def test_a_good_report_passes():
    report, errors = check(good())
    assert errors == [] and report is not None
    assert [s["share_pct"] for s in report["slices"]] == [35, 25, 20, 12, 8]


def test_three_slices_fail():
    r = good()
    r["slices"] = r["slices"][:3]
    r["slices"][0]["share_pct"] = 55
    assert any("4 to 6 slices, not 3" in e for e in check(r)[1])


def test_seven_slices_fail():
    r = good()
    r["slices"] += [copy.deepcopy(r["slices"][0]) | {"name": f"Extra {i}", "share_pct": 0} for i in range(2)]
    errors = check(r)[1]
    assert any("not 7" in e for e in errors) and any("more than 0" in e for e in errors)


def test_shares_summing_to_99_fail():
    r = good()
    r["slices"][4]["share_pct"] = 7
    assert any("sum to exactly 100, not 99" in e for e in check(r)[1])


def test_a_fractional_share_fails():
    r = good()
    r["slices"][0]["share_pct"] = 34.5
    assert any("whole number" in e for e in check(r)[1])
    r["slices"][0]["share_pct"] = 35.0
    assert check(r)[1] == [], "35.0 is a whole number"


def test_an_unknown_kind_fails():
    r = good()
    r["slices"][0]["kind"] = "vibes"
    assert any('kind must be one of' in e and '"vibes"' in e for e in check(r)[1])


def test_an_unknown_trend_fails():
    r = good()
    r["slices"][0]["trend"] = "sideways"
    assert any("trend must be one of" in e for e in check(r)[1])


def test_a_coach_not_in_the_pack_fails():
    r = good()
    r["slices"][1]["name"] = "Billy Napier"
    errors = check(r)[1]
    assert any('"Billy Napier" does not appear in the evidence pack' in e for e in errors), errors


def test_a_player_not_in_the_pack_fails_but_a_unit_may_be_any_name():
    r = good()
    r["slices"][2]["name"] = "Graham Mertz"
    assert any("Graham Mertz" in e for e in check(r)[1])
    r = good()
    r["slices"][0]["name"] = "The secondary"
    assert check(r)[1] == []


def test_one_evidence_item_fails():
    r = good()
    r["slices"][3]["evidence"] = ev(1)
    assert any("at least 2 pieces of evidence" in e for e in check(r)[1])


def test_the_wrong_week_or_season_fails():
    r = good()
    r["week"] = 8
    assert any("week must be 9" in e for e in check(r)[1])


def test_missing_fields_and_wrong_types_fail_with_words():
    r = good()
    del r["verdict"]
    r["slices"][0]["evidence"] = "lots"
    errors = check(r)[1]
    assert any(e.startswith("verdict") for e in errors) and any("slices[0].evidence" in e for e in errors)


def test_a_bad_result_or_confidence_fails():
    r = good()
    r["after_result"] = "moral victory"
    r["confidence"] = "certain"
    errors = check(r)[1]
    assert any("after_result" in e for e in errors) and any("confidence" in e for e in errors)


def test_a_slice_named_twice_fails():
    r = good()
    r["slices"][3]["name"] = "offensive line"
    assert any("named twice" in e for e in check(r)[1])


def test_the_reply_is_read_leniently_but_must_hold_one_object():
    body = json.dumps(good())
    assert read_answer(f"```json\n{body}\n```")[0]["week"] == 9, "fences are tolerated"
    assert read_answer(f"Here it is: {body} Done.")[0]["week"] == 9, "words around it are tolerated"
    assert read_answer("")[1] == "the reply was empty"
    assert read_answer("[1, 2]")[1] == "the reply's JSON was not one object"
    assert read_answer("no json here")[1] == "the reply held no JSON object"
    assert check_report("{nope}", PACK, 2026, 9)[1][0].startswith("the reply's JSON could not be read")


def test_numbers_in_evidence_become_words():
    r = good()
    r["slices"][0]["evidence"][0]["value"] = 2.41
    r["slices"][0]["evidence"][1]["value"] = 118
    report, errors = check(r)
    assert errors == [] and report["slices"][0]["evidence"][0]["value"] == "2.41" and report["slices"][0]["evidence"][1]["value"] == "118"


def test_the_store_keeps_each_week_and_the_strip_reads_them(tmp_path: Path):
    store = BlameStore(tmp_path, 2026)
    assert store.latest() is None and store.keys() == []
    for week, top in ((8, "Defense"), (9, "Offensive line")):
        r = good()
        r["week"] = week
        r["slices"][0]["name"] = top
        store.save(week_key("regular", week), {"label": f"Week {week}", "opponent": "Georgia", "report": r})
    store.save(week_key("postseason", 1), {"label": "Bowl", "report": good()})
    store.save_pack("week-9", {"x": 1})
    (store.dir / "week-10.json").write_text("{broken", encoding="utf-8")
    assert store.keys() == ["week-8", "week-9", "week-10", "post-1"]
    assert [k for k, _ in store.records()] == ["week-8", "week-9", "post-1"], "a broken file is left out"
    assert store.latest()[0] == "post-1"
    strip = history(store.records())
    assert strip[0]["top"] == {"name": "Defense", "kind": "unit", "share": 35} and strip[1]["top"]["name"] == "Offensive line"
    store.save_failure("week-9", {"errors": ["x"]})
    assert store.load_failure("week-9") == {"errors": ["x"]} and store.load_failure("week-1") is None


def test_a_blank_the_pack_leaks_reads_missing_never_null(tmp_path: Path):
    """Owner 2026-11-15 ("fix the null in the note"): the week 11 report's What the pack lacked said "Strength of schedule is null
    in the SP+ block". A new report has the words a blank leaks ("null", "undefined", "NaN") as "missing" in every string; a stored
    report reads the same way, so one written before the prompt asked for plain words shows right too; other words stay as written."""
    raw = good()
    raw["limitations"] = ["Strength of schedule is null in the SP+ block.", "The kicker's long is undefined.", "Annulled plays and a nullified catch stay."]
    raw["movement"] = "The NaN in last week's pass rate is gone."
    raw["slices"][0]["case"] = "Line yards are null for week 3."
    raw["slices"][0]["evidence"][0]["value"] = "null"
    report, errors = check(raw)
    assert errors == [] and report is not None
    assert report["limitations"] == ["Strength of schedule is missing in the SP+ block.", "The kicker's long is missing.", "Annulled plays and a nullified catch stay."]
    assert report["movement"] == "The missing in last week's pass rate is gone."
    assert report["slices"][0]["case"] == "Line yards are missing for week 3."
    assert report["slices"][0]["evidence"][0]["value"] == "missing"
    assert [s["share_pct"] for s in report["slices"]] == [35, 25, 20, 12, 8] and report["week"] == 9, "numbers are left alone"
    # a report stored before the change: read back in plain words, the file itself untouched
    store = BlameStore(tmp_path, 2026)
    stored = good()
    stored["limitations"] = ["Strength of schedule is null in the SP+ block."]
    store.save("week-9", {"week": 9, "label": "Week 9", "report": stored})
    record = store.load("week-9")
    assert record is not None and record["report"]["limitations"] == ["Strength of schedule is missing in the SP+ block."]
    assert record["label"] == "Week 9"
    assert "is null in" in store.path("week-9").read_text(encoding="utf-8"), "the stored file is never rewritten"
    assert store.records()[0][1]["report"]["limitations"] == ["Strength of schedule is missing in the SP+ block."]


def test_the_prompt_asks_for_plain_words_for_a_blank():
    prompt = (Path(__file__).resolve().parents[1] / "app" / "prompts" / "circle_of_blame.system.md").read_text(encoding="utf-8")
    assert prompt.startswith("<!-- prompt-version: circle_of_blame.system/2 (2026-11-15) -->")
    assert "never the word null" in prompt
