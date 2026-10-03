"""Phase 10a, contract C3: the live state carries CFBD's own success data (the feed's team rate,
the per-play flag on scrimmage plays only), drive results in the drive bar's codes with the
feed's words kept beside them, and red-zone trips counted from the snaps. Everything runs on
the made-up league's Tier 2 live document of our last game, the finished-game /plays and /drives for
the same game, and malformed input. No network."""

from __future__ import annotations

import copy
import math
import re
from datetime import datetime, timezone
from typing import Any

import pytest

from app.cfbd.models import Drive, LiveGame, Play, parse_one, parse_records
from app.demo.sim import PLAY_TYPE_IDS
from app.live.events import DRIVE_RESULTS, LiveEvent, drive_result, events_from_finished, events_from_live, feed_success, is_scrimmage, play_success
from app.live.state import derive_state
from tests.conftest import PROJECT_ROOT, fixture_payload
from tests.league_facts import US, last_game, live_counts

LAST = last_game()
LAST_GAME = LAST["id"]
HOME, AWAY = LAST["homeTeam"], LAST["awayTeam"]
SEEN = datetime(2026, 9, 21, 0, 0, tzinfo=timezone.utc)
PLAY_COUNT, DRIVE_COUNT = live_counts()

# Every play type CFBD's live feed has shown (the recording) or the league can send, classified by hand
# for C3: a snap on a scrimmage down is judged; kicks, timeouts, penalties with no play, and period
# markers are not.
FIXTURE_SCRIMMAGE = {"Rush", "Pass Reception", "Pass Incompletion", "Sack", "Rushing Touchdown", "Passing Touchdown", "Interception", "Pass Interception Return",
                     "Fumble Recovery (Own)", "Fumble Recovery (Opponent)", "Interception Return Touchdown", "Fumble Return Touchdown", "Safety"}
FIXTURE_NOT_SCRIMMAGE = {"Kickoff", "Penalty", "Timeout", "Field Goal Good", "End Period", "Punt", "Punt Return", "End of Game", "End of Half", "Field Goal Missed",
                         "Kickoff Return (Offense)", "Kickoff Return Touchdown", "Punt Return Touchdown", "Two Point Rush", "Two Point Pass"}
# The drive results the live feed words (the recording's, and the league's for the rest of DRIVE_RESULTS).
LIVE_WORDS = {"Touchdown", "Field Goal", "Punt", "Interception", "End of Half", "Downs", "End of Game", "Missed Field Goal", "Fumble", "Interception Return Touchdown", "Safety"}


def live_doc() -> dict[str, Any]:
    return copy.deepcopy(fixture_payload("live_plays"))


def live_state(doc: dict[str, Any] | None = None) -> dict[str, Any]:
    game = parse_one(LiveGame, doc if doc is not None else live_doc(), context="t")
    assert game is not None
    return derive_state(events_from_live(game, SEEN), game_id=LAST_GAME, home=HOME, away=AWAY)


def finished_state() -> dict[str, Any]:
    plays = parse_records(Play, fixture_payload("plays"), context="t").records
    drives = parse_records(Drive, fixture_payload("drives"), context="t").records
    timeline = events_from_finished(LAST_GAME, plays, drives, HOME, AWAY)
    return derive_state([event for event, _ in timeline], game_id=LAST_GAME, home=HOME, away=AWAY, mode="replay")


def independent_red_zone(doc: dict[str, Any]) -> dict[str, dict[str, int]]:
    """C3 counted straight from the raw document with the hand classification above: a trip when
    the offense ran a scrimmage play at the 20 or closer (the drive's end when it has no plays),
    never on a drive the clock ended; a score when the trip ended in a touchdown or field goal."""
    out: dict[str, dict[str, int]] = {}
    for drive in doc["drives"]:
        side = out.setdefault(drive["offense"], {"scores": 0, "trips": 0})
        if drive["result"] in ("End of Half", "End of Game"):
            continue
        plays = drive.get("plays") or []
        if plays:
            trip = any(p["playType"] in FIXTURE_SCRIMMAGE and p["team"] == drive["offense"] and p["yardsToGoal"] <= 20 for p in plays)
        else:
            trip = drive["endYardsToGoal"] <= 20
        if trip:
            side["trips"] += 1
            side["scores"] += drive["result"] in ("Touchdown", "Field Goal")
    return out


def snaps(doc: dict[str, Any], team: str) -> int:
    """The team's snaps in a document, counted with the hand classification: what the box calls plays."""
    return sum(1 for d in doc["drives"] for p in d["plays"] if p.get("playType") in FIXTURE_SCRIMMAGE and p.get("team") == team)


def drive_bar_sets() -> tuple[set[str], set[str]]:
    """The SCORES and TURNOVERS sets of static/js/ui/drive-bar.js, read from the source."""
    source = (PROJECT_ROOT / "static" / "js" / "ui" / "drive-bar.js").read_text(encoding="utf-8")

    def one(name: str) -> set[str]:
        match = re.search(rf"const {name} = new Set\(\[(.*?)\]\)", source, re.S)
        assert match, f"{name} is not in drive-bar.js"
        return set(re.findall(r'"([^"]+)"', match.group(1)))

    return one("SCORES"), one("TURNOVERS")


def event(kind: str, eid: str, data: Any, seq: int = 0) -> LiveEvent:
    return LiveEvent(eid, kind, 1, SEEN, data, seq=seq)


# --- play types and the scrimmage rule -----------------------------------------------------------------------------


def test_every_play_type_in_the_live_document_is_classified():
    doc = live_doc()
    types = {p.get("playType") for d in doc["drives"] for p in d["plays"]}
    assert types <= FIXTURE_SCRIMMAGE | FIXTURE_NOT_SCRIMMAGE  # a new type in a new recording must be classified here first
    assert set(PLAY_TYPE_IDS) <= FIXTURE_SCRIMMAGE | FIXTURE_NOT_SCRIMMAGE  # and every type the league can send
    assert FIXTURE_SCRIMMAGE.isdisjoint(FIXTURE_NOT_SCRIMMAGE)
    assert all(is_scrimmage(t) for t in FIXTURE_SCRIMMAGE)
    assert not any(is_scrimmage(t) for t in FIXTURE_NOT_SCRIMMAGE)


def test_tries_markers_and_unknown_types_are_not_scrimmage():
    for kick_or_try in ("Extra Point Good", "Extra Point Missed", "Blocked PAT", "Two Point Rush", "Two Point Pass", "Two-Point Conversion", "Defensive 2pt Conversion", "Offensive 1pt Safety", "Kickoff Return (Offense)", "Blocked Punt", "Punt Return Touchdown", "Field Goal Missed", "Blocked Field Goal", "Missed Field Goal Return", "End of Half", "End of Regulation", "Start of Period", "Uncategorized", "placeholder"):
        assert not is_scrimmage(kick_or_try), kick_or_try
    for snap in ("Fumble Recovery (Own)", "Fumble Recovery (Opponent)", "Fumble Return Touchdown", "Interception Return Touchdown", "Safety", "Pass Completion"):
        assert is_scrimmage(snap), snap
    assert not is_scrimmage(None) and not is_scrimmage("") and not is_scrimmage("   ") and not is_scrimmage(5)  # type: ignore[arg-type]


def test_local_rule_is_scrimmage_only_and_turnovers_fail():
    assert play_success(1, 10, 5, "Rush", False) is True and play_success(2, 10, 6, "Rush", False) is False
    assert play_success(3, 2, 0, "Passing Touchdown", True) is True
    assert play_success(2, 10, 0, "Interception Return Touchdown", True) is False  # a pick-six is the offense failing
    assert play_success(1, 10, 12, "Fumble Recovery (Opponent)", False) is False
    assert play_success(1, 10, 20, "Kickoff", False) is None and play_success(1, 10, 5, "Timeout", False) is None
    assert play_success(1, 10, 5, None, False) is None and play_success(0, 10, 5, "Rush", False) is None and play_success(True, 10, 5, "Rush", False) is None  # type: ignore[arg-type]
    assert play_success(1, 10, "5", "Rush", False) is None and play_success(1, None, 5, "Rush", False) is None  # type: ignore[arg-type]


def test_feed_success_keeps_only_a_boolean_on_a_scrimmage_play():
    assert feed_success(True, "Rush") is True and feed_success(False, "Sack") is False
    assert feed_success(True, "Kickoff") is None and feed_success(False, "Timeout") is None and feed_success(True, "Penalty") is None
    assert feed_success("true", "Rush") is None and feed_success(1, "Rush") is None and feed_success(None, "Rush") is None
    assert feed_success(True, None) is None


# --- drive results ---------------------------------------------------------------------------------------------------


def test_drive_result_codes_hit_the_drive_bar_sets():
    scores, turnovers = drive_bar_sets()
    codes = set(DRIVE_RESULTS.values())
    assert {"TD", "FG"} <= scores
    assert {"INT", "INT TD", "FUMBLE", "FUMBLE TD", "DOWNS", "MISSED FG"} <= turnovers
    assert codes - scores - turnovers == {"PUNT", "END OF HALF", "END OF GAME", "SAFETY"}  # shown neutral
    assert drive_result("Touchdown") == "TD" and drive_result("Field Goal Good") == "FG" and drive_result("Blocked Field Goal") == "MISSED FG"
    assert drive_result("Interception Return Touchdown") == "INT TD" and drive_result("Fumble Lost") == "FUMBLE" and drive_result("Turnover on Downs") == "DOWNS"
    assert drive_result("  field   GOAL ") == "FG" and drive_result("End of Half") == "END OF HALF" and drive_result("Safety") == "SAFETY"
    for code in codes | {"TD", "FG", "PUNT", "INT", "DOWNS", "END OF HALF", "END OF GAME"}:  # the /drives vocabulary maps to itself
        assert drive_result(code) == code


@pytest.mark.parametrize(
    "words, code",
    [
        ("Missed FG", "MISSED FG"),
        ("FG Missed", "MISSED FG"),
        ("Blocked FG", "MISSED FG"),
        ("Interception Touchdown", "INT TD"),
        ("Interception TD", "INT TD"),
        ("INT TD", "INT TD"),
        ("Fumble Touchdown", "FUMBLE TD"),
        ("Fumble Return TD", "FUMBLE TD"),
        ("Fumble TD", "FUMBLE TD"),
    ],
)
def test_short_result_words_the_recording_lacks_still_reach_the_turnover_set(words, code):
    _, turnovers = drive_bar_sets()
    assert drive_result(words) == code and code in turnovers


def test_drive_results_are_codes_with_the_feed_words_kept():
    doc = live_doc()
    raw = {d["id"]: d["result"] for d in doc["drives"]}
    assert set(raw.values()) <= LIVE_WORDS and {"Touchdown", "Punt", "End of Game"} <= set(raw.values())
    state = live_state(doc)
    assert len(state["drives"]) == DRIVE_COUNT
    for drive in state["drives"]:
        assert drive["result"] not in LIVE_WORDS and drive["result"] == drive["result"].upper()
        assert drive["resultText"] == raw[drive["id"]]
        assert drive["result"] == drive_result(raw[drive["id"]])
    assert {d["result"] for d in state["drives"]} == {drive_result(w) for w in raw.values()} <= set(DRIVE_RESULTS.values())


# --- the real live document -----------------------------------------------------------------------------------------


def test_red_zone_matches_an_independent_count():
    doc = live_doc()
    expected = independent_red_zone(doc)
    state = live_state(doc)
    got = {team: state["box"][team]["redZone"] for team in (HOME, AWAY)}
    print(f"red zone, live document: {got}")
    assert got == expected
    assert sum(t["trips"] for t in got.values()) >= 2 and all(t["scores"] <= t["trips"] for t in got.values())


def test_success_rate_is_the_feed_rate_and_there_is_no_local_count():
    doc = live_doc()
    rates = {t["team"]: t["successRate"] for t in doc["teams"]}
    state = live_state(doc)
    assert state["box"][HOME]["successRate"] == rates[HOME] and state["box"][AWAY]["successRate"] == rates[AWAY]
    assert all(0 < rates[t] < 1 for t in (HOME, AWAY))
    assert state["box"][HOME]["successCounts"] is None and state["box"][AWAY]["successCounts"] is None
    for team in (HOME, AWAY):  # the play counting for other stats is unchanged: the offense's snaps
        assert state["box"][team]["plays"] == snaps(doc, team)


def test_success_flag_only_on_scrimmage_plays():
    doc = live_doc()
    raw = {p["id"]: p for d in doc["drives"] for p in d["plays"]}
    state = live_state(doc)
    judged = 0
    for play in state["plays"]:
        source = raw[play["id"]]
        if source["playType"] in FIXTURE_SCRIMMAGE:
            assert play["success"] is source["success"]
            judged += 1
        else:
            assert play["success"] is None, source["playType"]
    assert judged == sum(1 for p in raw.values() if p["playType"] in FIXTURE_SCRIMMAGE) > 100
    assert sum(1 for p in raw.values() if p["playType"] in FIXTURE_NOT_SCRIMMAGE and p["success"] is True) >= 1  # what the old code would have judged
    last = raw[state["lastPlay"]["id"]]  # the game's final snap, judged like any other (public release Phase 7: no fixed play)
    snaps_in_order = [p for p in raw.values() if p["playType"] in FIXTURE_SCRIMMAGE]
    assert last is snaps_in_order[-1] and state["lastPlay"]["success"] is last["success"]  # the end-of-game markers after it are not plays


def cut_after(doc: dict[str, Any], stop) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any] | None]:
    """The document as a poll would have seen it right after the first play matching stop.
    Returns the cut document, that play, and the newest scrimmage play with a flag before it."""
    before: dict[str, Any] | None = None
    for d_index, drive in enumerate(doc["drives"]):
        for p_index, play in enumerate(drive["plays"]):
            if stop(play):
                cut = copy.deepcopy(doc)
                cut["drives"] = cut["drives"][: d_index + 1]
                cut["drives"][-1]["plays"] = cut["drives"][-1]["plays"][: p_index + 1]
                cut["drives"][-1]["result"] = ""
                cut["status"] = "in progress"
                return cut, play, before
            if play["playType"] in FIXTURE_SCRIMMAGE and isinstance(play["success"], bool):
                before = play
    raise AssertionError("no play matched")


def test_cut_at_the_first_timeout_last_play_is_the_snap_before_it():
    cut, timeout, before = cut_after(live_doc(), lambda p: p["playType"] == "Timeout")
    assert before is not None and before["playType"] in FIXTURE_SCRIMMAGE and timeout["success"] is False  # CFBD flags the timeout; C3 does not judge it
    state = live_state(cut)
    newest = state["plays"][0]
    assert newest["id"] == timeout["id"] and newest["success"] is None
    assert state["lastPlay"]["id"] == before["id"] and state["lastPlay"]["success"] is before["success"]
    assert state["drives"][-1]["result"] is None and state["drives"][-1]["resultText"] is None and state["currentDriveId"] == cut["drives"][-1]["id"]


def test_cut_at_a_penalty_cfbd_called_a_success_is_not_judged():
    cut, penalty, before = cut_after(live_doc(), lambda p: p["playType"] == "Penalty" and p["success"] is True)
    state = live_state(cut)
    assert state["plays"][0]["id"] == penalty["id"] and state["plays"][0]["success"] is None
    assert before is not None and state["lastPlay"]["id"] == before["id"]


# --- finished-game replay (no CFBD flag, no feed block) ---------------------------------------------------------------


def test_finished_replay_keeps_a_sensible_last_play_and_red_zone():
    state = finished_state()
    got = {team: state["box"][team]["redZone"] for team in (HOME, AWAY)}
    print(f"red zone, finished /plays and /drives: {got}")
    assert got == independent_red_zone(live_doc())  # same game, same answer from the other source
    assert is_scrimmage(state["lastPlay"]["playType"]) and isinstance(state["lastPlay"]["success"], bool) and state["lastPlay"]["text"]
    assert all(p["success"] is None for p in state["plays"] if not is_scrimmage(p["playType"]))
    assert all(isinstance(p["success"], bool) for p in state["plays"] if is_scrimmage(p["playType"]) and isinstance(p["down"], int) and 1 <= p["down"] <= 4)
    for team in (HOME, AWAY):
        assert state["box"][team]["successRate"] is None and state["box"][team]["successCounts"] is None  # C3: no feed block in a replay
    assert {d["result"] for d in state["drives"]} == {drive_result(d["result"]) for d in live_doc()["drives"]}
    assert all(d["resultText"] == d["result"] for d in state["drives"])


# --- malformed input -------------------------------------------------------------------------------------------------


def test_malformed_drive_results_on_the_model_path():
    game = parse_one(LiveGame, live_doc(), context="t")
    assert game is not None
    game.drives[0].result = None
    game.drives[1].result = ""
    game.drives[2].result = 7  # type: ignore[assignment]  (the model refuses it; this is what the normalizer does if one slips past)
    game.drives[3].result = "Something New "
    drives = {e.data["id"]: e.data for e in events_from_live(game, SEEN) if e.kind == "drive"}
    changed = live_doc()  # the same four drives without a usable result, for the independent count
    for i, result in enumerate((None, "", None, "Something New ")):
        changed["drives"][i]["result"] = result
    first, second, third, fourth = (drives[game.drives[i].id] for i in range(4))
    assert first["result"] is None and first["resultText"] is None
    assert second["result"] is None and second["resultText"] is None
    assert third["result"] is None and third["resultText"] is None
    assert fourth["result"] == "SOMETHING NEW" and fourth["resultText"] == "Something New "
    state = derive_state(events_from_live(game, SEEN), game_id=LAST_GAME, home=HOME, away=AWAY)
    for team in (HOME, AWAY):  # a drive that lost its result is a trip without a score
        assert state["box"][team]["redZone"] == independent_red_zone(changed)[team]


def test_malformed_drive_results_in_stored_events():
    events = [
        event("drive", "drive:a", {"id": "a", "number": 1, "offense": "A", "result": 7, "endYardsToGoal": 5}),
        event("drive", "drive:b", {"id": "b", "number": "2", "offense": "A", "result": "  ", "endYardsToGoal": 0}),
        event("drive", "drive:c", {"id": "c", "number": 3, "offense": "B", "result": "Touchdown", "endYardsToGoal": 0}),
        event("drive", "drive:d", {"id": "d", "number": 4, "offense": "B", "result": "Field Goal Good", "resultText": 9, "endYardsToGoal": 12}),
        event("drive", "drive:e", {"id": "e", "number": 5, "offense": "B", "result": "End of Half", "endYardsToGoal": 3}),
        event("drive", "drive:f", "not a drive"),
    ]
    state = derive_state(events, game_id=1, home="A", away="B")
    by_id = {d["id"]: d for d in state["drives"]}
    assert by_id["a"]["result"] is None and by_id["b"]["result"] is None and by_id["c"]["result"] == "TD" and by_id["c"]["resultText"] == "Touchdown"
    assert by_id["d"]["result"] == "FG" and by_id["d"]["resultText"] == "Field Goal Good" and by_id["e"]["result"] == "END OF HALF"
    assert state["box"]["A"]["redZone"] == {"scores": 0, "trips": 2}  # no plays yet: the drive's end decides; no result, no score
    assert state["box"]["B"]["redZone"] == {"scores": 2, "trips": 2}  # end of half never counts
    assert state["counts"]["drives"] == 5


def test_play_success_given_as_a_string():
    doc = live_doc()
    doc["drives"][0]["plays"][1]["success"] = "true"  # a word the model reads as a boolean
    doc["drives"][0]["plays"][2]["success"] = "maybe"  # one it cannot: since Phase 11 that field reads as empty and the play stays
    game = parse_one(LiveGame, doc, context="t")
    assert game is not None
    plays = [e.data for e in events_from_live(game, SEEN) if e.kind == "play"]
    assert len(plays) == PLAY_COUNT and all(p["success"] in (True, False, None) for p in plays)
    assert next(p for p in plays if p["id"] == doc["drives"][0]["plays"][2]["id"])["success"] is None
    game.drives[0].plays[1].success = "false"  # type: ignore[assignment]  (a string that slipped past the model)
    plays = {e.data["id"]: e.data for e in events_from_live(game, SEEN) if e.kind == "play"}
    assert plays[game.drives[0].plays[1].id]["success"] is None
    stored = [
        event("play", "play:1", {"id": "1", "period": 1, "clock": {"minutes": 10, "seconds": 0}, "playNumber": 1, "offense": "A", "playType": "Rush", "yardsGained": 3, "success": False}),
        event("play", "play:2", {"id": "2", "period": 1, "clock": {"minutes": 9, "seconds": 30}, "playNumber": 2, "offense": "A", "playType": "Rush", "yardsGained": 9, "success": "true"}),
    ]
    state = derive_state(stored, game_id=1, home="A", away="B")
    assert state["plays"][0]["success"] is None and state["lastPlay"]["id"] == "1"


def test_missing_play_type_is_not_judged_or_counted():
    doc = live_doc()
    target = next(p for d in doc["drives"] if d["offense"] == US for p in d["plays"] if p["playType"] == "Rush")
    del target["playType"]
    state = live_state(doc)
    play = next(p for p in state["plays"] if p["id"] == target["id"])
    assert play["playType"] is None and play["success"] is None
    assert state["box"][US]["plays"] == snaps(live_doc(), US) - 1  # one fewer snap than the full document
    stored = [
        event("play", "play:1", {"id": "1", "period": "2", "clock": "junk", "playNumber": None, "offense": "A", "playType": 5, "yardsGained": True, "flags": "turnover", "success": True}),
        event("play", "play:2", {"id": "2", "period": 1, "clock": {"minutes": None, "seconds": 3}, "offense": "A", "yardsGained": 4, "down": 3, "distance": "2", "success": True}),
        event("play", "play:3", ["not", "a", "play"]),
    ]
    state = derive_state(stored, game_id=1, home="A", away="B")
    assert state["counts"]["plays"] == 2 and state["box"]["A"]["plays"] == 0 and state["box"]["A"]["turnovers"] == 0
    assert state["lastPlay"] is None and all(p["success"] is None for p in state["plays"])


@pytest.mark.parametrize("rate", ["0.375", None, True, math.nan, 37.5, -0.1, "missing"])
def test_team_block_with_a_bad_or_missing_success_rate(rate):
    block = {"plays": 10} if rate == "missing" else {"successRate": rate, "plays": 10}
    status = {"status": "in_progress", "homeScore": 0, "awayScore": 0, "teams": {"A": block, "B": {"successRate": 0.5, "plays": 10}}}
    state = derive_state([event("status", "status", status)], game_id=1, home="A", away="B")
    assert state["box"]["A"]["successRate"] is None and state["box"]["A"]["successCounts"] is None
    assert state["box"]["B"]["successRate"] == 0.5


@pytest.mark.parametrize("block", ["junk", None, 0.4, ["successRate", 0.4]])
def test_team_block_that_is_not_an_object(block):
    status = {"status": "in_progress", "teams": {"A": block, "B": {"successRate": 0.5, "plays": 10}}}
    state = derive_state([event("status", "status", status)], game_id=1, home="A", away="B")
    assert state["box"]["A"]["successRate"] is None and state["box"]["B"]["successRate"] == 0.5


def test_zero_play_team_block_shows_no_rate_before_the_first_snap():
    doc = live_doc()  # the reviewer's case: the feed says 0 plays and 0 success, the log has snaps
    first, second = doc["teams"][0]["team"], doc["teams"][1]["team"]
    doc["teams"][0]["successRate"] = 0
    doc["teams"][0]["plays"] = 0
    state = live_state(doc)
    assert state["box"][first]["plays"] == snaps(doc, first) > 0 and state["box"][first]["successRate"] is None
    assert state["box"][second]["successRate"] == doc["teams"][1]["successRate"]
    pregame = live_doc()  # a document before kickoff: both blocks zero, no drives yet
    pregame["drives"] = []
    for team in pregame["teams"]:
        team["successRate"], team["plays"] = 0, 0
    state = live_state(pregame)
    assert state["counts"]["plays"] == 0 and state["lastPlay"] is None
    assert state["box"][HOME]["successRate"] is None and state["box"][AWAY]["successRate"] is None
    assert state["feedStats"][US]["plays"] == 0  # the feed's own block is still passed through as sent


def test_success_rate_falls_back_to_the_box_count_when_the_feed_has_no_play_count():
    doc = live_doc()
    rates = {t["team"]: t["successRate"] for t in doc["teams"]}
    for team in doc["teams"]:
        del team["plays"]
    state = live_state(doc)
    assert state["box"][HOME]["successRate"] == rates[HOME] and state["box"][AWAY]["successRate"] == rates[AWAY]
    snaps = [event("play", "play:1", {"id": "1", "period": 1, "clock": {"minutes": 14, "seconds": 0}, "offense": "A", "defense": "B", "playType": "Rush", "yardsGained": 4})]
    for plays in (None, "12", True, math.inf):  # not a usable count: the box decides
        status = {"status": "in_progress", "teams": {"A": {"successRate": 0.4, "plays": plays}, "B": {"successRate": 0.6, "plays": plays}}}
        state = derive_state(snaps + [event("status", "status", status, seq=1)], game_id=1, home="A", away="B")
        assert state["box"]["A"]["plays"] == 1 and state["box"]["A"]["successRate"] == 0.4
        assert state["box"]["B"]["plays"] == 0 and state["box"]["B"]["successRate"] is None


def test_team_blocks_missing_or_malformed_on_the_model_path():
    doc = live_doc()
    first, second = doc["teams"][0]["team"], doc["teams"][1]["team"]
    rate = doc["teams"][0]["successRate"]
    doc["teams"][0]["successRate"] = str(rate)  # a numeric string the model reads as a number
    del doc["teams"][1]["successRate"]
    state = live_state(doc)
    assert state["box"][first]["successRate"] == rate and state["box"][second]["successRate"] is None
    game = parse_one(LiveGame, live_doc(), context="t")
    assert game is not None
    game.teams[0].success_rate = str(rate)  # type: ignore[assignment]  (a string that slipped past the model)
    game.teams = game.teams[1:]  # and the other block gone entirely
    game.teams[0].success_rate = None
    state = derive_state(events_from_live(game, SEEN), game_id=LAST_GAME, home=HOME, away=AWAY)
    assert state["box"][HOME]["successRate"] is None and state["box"][AWAY]["successRate"] is None
    for status in ({"status": "final", "teams": "junk"}, {"status": "final", "teams": None}, {"status": "final"}):
        state = derive_state([event("status", "status", status)], game_id=1, home="A", away="B")
        assert state["box"]["A"]["successRate"] is None and state["feedStats"] == status.get("teams")


# --- red zone edges --------------------------------------------------------------------------------------------------


def red_zone(plays: list[dict[str, Any]], drive: dict[str, Any]) -> dict[str, int]:
    events = [event("drive", f"drive:{drive['id']}", drive)] + [event("play", f"play:{p['id']}", p) for p in plays]
    return derive_state(events, game_id=1, home="A", away="B")["box"]["A"]["redZone"]


def snap(pid: str, ytg: Any, *, ptype: str = "Rush", offense: str = "A", clock: int = 10) -> dict[str, Any]:
    return {"id": pid, "driveId": "d", "period": 1, "clock": {"minutes": clock, "seconds": 0}, "offense": offense, "playType": ptype, "yardsToGoal": ytg, "yardsGained": 5}


def test_red_zone_edges():
    touchdown = {"id": "d", "number": 1, "offense": "A", "result": "TD", "endYardsToGoal": 0}
    assert red_zone([snap("1", 75), snap("2", 45)], touchdown) == {"scores": 0, "trips": 0}  # a long touchdown never snapped inside the 20
    assert red_zone([snap("1", 75), snap("2", 20)], touchdown) == {"scores": 1, "trips": 1}  # the 20 itself counts
    field_goal = {**touchdown, "result": "FG", "endYardsToGoal": 22}
    assert red_zone([snap("1", 30), snap("2", 8), snap("3", 22, ptype="Field Goal Good")], field_goal) == {"scores": 1, "trips": 1}  # backed out and kicked: still a trip
    punt = {**touchdown, "result": "PUNT", "endYardsToGoal": 25}
    assert red_zone([snap("1", 30), snap("2", 15, ptype="Penalty"), snap("3", 25)], punt) == {"scores": 0, "trips": 0}  # a flag inside the 20 is not a snap
    assert red_zone([snap("1", 30), snap("2", 10, offense="B")], punt) == {"scores": 0, "trips": 0}  # the other team's return is not this offense
    assert red_zone([snap("1", 30), snap("2", True), snap("3", "12")], punt) == {"scores": 0, "trips": 0}  # junk yard lines never count
    half = {**touchdown, "result": "End of Half", "endYardsToGoal": 5}
    assert red_zone([snap("1", 9)], half) == {"scores": 0, "trips": 0}
    assert red_zone([], {**touchdown, "endYardsToGoal": 3}) == {"scores": 1, "trips": 1}  # no plays in the log yet: the drive's end decides
    assert red_zone([], {**touchdown, "endYardsToGoal": None}) == {"scores": 0, "trips": 0}
    missed = {**touchdown, "result": "Missed Field Goal", "endYardsToGoal": 14}
    assert red_zone([snap("1", 14)], missed) == {"scores": 0, "trips": 1}
    finished_style = {**touchdown, "result": "PASSING TD"}  # the drive bar's synonym still scores
    assert red_zone([snap("1", 4)], finished_style) == {"scores": 1, "trips": 1}
