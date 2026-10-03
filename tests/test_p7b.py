"""Public release Phase 7b: the shot chart (pass zones and run lanes from the play text, released plays only), and
the TV crew and both coaching staffs from the notes (CFBD has the network and head coaches only)."""

from __future__ import annotations

import json

from app.live.analysis import PASS_ZONES, RUN_LANES, shot_chart
from app.services import notes_paste
from tests.test_live_state_10a import HOME, live_doc, live_state

US, THEM = "Home U", "Away U"


def play(text: str, play_type: str, *, offense: str = US, success: bool | None = True, gained: object = 5, rush_pass: str | None = None) -> dict:
    return {"offense": offense, "playType": play_type, "text": text, "success": success, "yardsGained": gained, "rushPass": rush_pass}


# The wording is the live feed's (checked against the recorded live documents of 2026-10-03); the names are made up.
PLAYS = [
    play("(14:57) Shotgun #12 A.Passer pass complete short left to #6 B.Catch caught at Home23, for 9 yards to the Home34", "Pass Reception", gained=9),
    play("(13:59) Shotgun #12 A.Passer pass incomplete short middle to #6 B.Catch thrown to Away44 broken up by #1 C.Cover", "Pass Incompletion", success=False, gained=0),
    play("(13:23) No Huddle-Shotgun #12 A.Passer pass complete deep left to #6 B.Catch caught at Away35, for 24 yards", "Pass Reception", gained=24),
    play("(12:00) #12 A.Passer pass intercepted deep right by #3 D.Hawk at the Away20", "Pass Interception Return", success=False, gained=0),
    play("(11:10) #12 A.Passer sacked by #90 E.Rush for a loss of 7 yards", "Sack", success=False, gained=-7),
    play("(10:40) #12 A.Passer pass incomplete, thrown away", "Pass Incompletion", success=False, gained=0),
    play("(14:05) Shotgun #13 F.Back rush left for 22 yards gain to the Home46", "Rush", gained=22),
    play("(13:49) Shotgun #13 F.Back rush right for 3 yards loss to the Home43", "Rush", success=False, gained=-3),
    play("(10:30) No Huddle-Shotgun #13 F.Back rush middle for 1 yard loss to the Away13", "Rush", success=False, gained=-1),
    play("(09:30) #13 F.Back rush up the middle for 4 yards", "Rush", success=None, gained=float("nan")),
    play("(09:00) #13 F.Back runs a draw for 3 yards", "Rush", gained=3),
    play("(08:00) Kickoff: #40 K.Leg kicks 65 yards", "Kickoff", gained=0),
    play("(07:00) #8 Other pass complete short left to #2 X for 10 yards", "Pass Reception", offense=THEM, gained=10),
]


def test_passes_go_to_their_zones_with_completions_success_and_yards():
    chart = shot_chart(PLAYS, (US, THEM))
    us = chart[US]
    assert set(us["passes"]) == set(PASS_ZONES) and set(us["runs"]) == set(RUN_LANES)
    assert us["passes"]["short-left"] == {"attempts": 1, "completions": 1, "yards": 9, "success": {"made": 1, "of": 1}, "successRate": 1.0, "completionRate": 1.0, "yardsPerAttempt": 9.0}
    assert us["passes"]["short-middle"]["attempts"] == 1 and us["passes"]["short-middle"]["completions"] == 0 and us["passes"]["short-middle"]["successRate"] == 0.0
    assert us["passes"]["deep-left"]["yards"] == 24 and us["passes"]["deep-right"]["attempts"] == 1 and us["passes"]["deep-right"]["completions"] == 0  # an interception is an attempt
    assert us["passes"]["deep-middle"]["attempts"] == 0 and us["passes"]["deep-middle"]["successRate"] is None
    assert us["sacks"] == 1 and us["unzoned"] == {"passes": 1, "runs": 1}  # the throwaway and the draw have no zone


def test_runs_go_to_their_lanes_and_junk_never_counts():
    us = shot_chart(PLAYS, (US, THEM))[US]
    assert us["runs"]["left"]["attempts"] == 1 and us["runs"]["left"]["successRate"] == 1.0
    assert us["runs"]["right"]["yards"] == -3 and us["runs"]["middle"]["attempts"] == 2  # "rush up the middle" is the middle
    middle = us["runs"]["middle"]
    assert middle["yards"] == -1 and middle["success"] == {"made": 0, "of": 1}  # NaN yards and an unjudged play add nothing


def test_each_offense_keeps_its_own_chart_and_others_are_ignored():
    chart = shot_chart(PLAYS + [play("pass complete short left", "Pass Reception", offense="Stranger")], (US, THEM))
    assert set(chart) == {US, THEM} and chart[THEM]["passes"]["short-left"]["attempts"] == 1
    assert shot_chart([], (US, None)) == {US: shot_chart([], (US,))[US]}
    assert shot_chart([{"offense": US}, {}, {"playType": None, "text": None}], (US, THEM))[US]["sacks"] == 0


def test_the_live_state_carries_the_chart_from_released_plays():
    state = live_state()
    chart = state["shotChart"][HOME]
    charted = sum(c["attempts"] for c in chart["passes"].values()) + sum(c["attempts"] for c in chart["runs"].values())
    offense = [p for p in state["plays"] if p.get("offense") == HOME]
    assert 0 < charted <= len(offense)
    early = live_doc()
    early["drives"] = early["drives"][:1]  # fewer plays released: fewer charted
    fewer = live_state(early)["shotChart"][HOME]
    assert sum(c["attempts"] for c in fewer["passes"].values()) <= sum(c["attempts"] for c in chart["passes"].values())


def test_the_prompt_asks_for_the_tv_crew_and_the_coordinators():
    assert '"broadcast"' in notes_paste.DEFAULT_PROMPT and "TV only, not radio" in notes_paste.DEFAULT_PROMPT
    assert "offensive coordinator and defensive coordinator" in notes_paste.DEFAULT_PROMPT
    shape = json.loads(notes_paste.shape_example("Home U", "Away U", "Some Conf"))
    assert shape["broadcast"]["sideline"] and shape["coaches"]["us"]["team"] == "Home U" and shape["coaches"]["them"]["team"] == "Away U"


def test_an_answer_with_only_the_crew_and_staffs_reads_and_junk_is_left_out():
    answer = {"broadcast": {"network": "ABC", "playByPlay": "Pat Caller", "analyst": "Sam Color", "sideline": ["Lee Field", 7, None]},
              "coaches": {"us": {"headCoach": "Head Us", "offensiveCoordinator": "Oc Us", "defensiveCoordinator": "Dc Us"}, "them": {"headCoach": "Head Them"}},
              "sources": [{"label": "release", "url": "https://example.invalid/r"}]}
    reading = notes_paste.read_answer(json.dumps(answer), 7)
    assert reading.notes is not None, reading.error
    assert reading.notes.broadcast.sideline == ["Lee Field"] and reading.summary["coaches"] == 4
    assert reading.summary["broadcast"]["playByPlay"] == "Pat Caller"
    wrong = notes_paste.read_answer(json.dumps({**answer, "broadcast": "ESPN", "coaches": [1]}), 7)
    assert wrong.notes is None or (wrong.notes.broadcast is None and wrong.notes.coaches is None)
