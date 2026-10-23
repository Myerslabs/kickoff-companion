"""The trivia (owner 2026-10-21): questions from the facts, the game-day session and its master file, the routes a guest
may write to, the Settings switches, the demo league's facts."""

from __future__ import annotations

import asyncio
import json
import random
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace as NS
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.demo.facts import league_facts, write_demo_facts
from app.demo.league import League
from app.services.season_prompts import read_facts
from app.services.trivia import DAY_HOURS, OPEN_SECONDS, QUIET_AFTER, TriviaError, TriviaService, clean_name
from app.services.trivia_questions import KINDS, make_question, pick_question
from tests.conftest import CONFERENCE, TEAM

TZ = ZoneInfo("America/New_York")
KICKOFF = datetime(2026, 10, 24, 19, 30, tzinfo=TZ)


@pytest.fixture(scope="module")
def league() -> League:
    return League(2026)


@pytest.fixture
def rows(league) -> dict:
    return league_facts(league, 2026)


def service(tmp_path: Path, rows: dict, now: list[datetime], state=None, pace="15", trivia=True, board=True) -> TriviaService:
    window = NS(game_id=1, home=TEAM, away="Diner Tech", kickoff=KICKOFF)
    live = NS(window=window, state=state or (lambda delay: None))
    prefs = NS(prefs=NS(trivia=trivia, triviaBoard=board, triviaPace=pace, delaySeconds=0))
    return TriviaService(tmp_path, 2026, TZ, lambda: now[0], prefs, lambda: rows, live, TEAM)


def tick(svc: TriviaService, at: datetime, games=None, answer_as: str | None = None) -> None:
    """One look at the clock; with `answer_as`, that team answers whatever opened (so the quiet rule stays out of it)."""

    async def games_on():
        return games or []

    asyncio.run(svc.tick(at, games_on))
    if answer_as:
        q = svc.now_for(answer_as, at)["question"]
        if q and q.get("yourPick") is None:
            svc.answer(answer_as, q["id"], 0, at)


# --- questions ---------------------------------------------------------------------------------------------------------


def test_the_demo_league_facts_pass_the_apps_parser_and_build_every_kind(rows):
    conference = rows[TEAM]["conference"]
    schools = [s for s, r in rows.items() if r["conference"] == conference]
    batch = {"conference": conference, "season": 2026, "author": "demo", "teams": [{"school": s, **{k: v for k, v in rows[s].items() if k not in ("conference", "savedAt", "checkedAt")}} for s in schools]}
    reading = read_facts(json.dumps(batch), conference, schools)
    assert reading.value is not None and not reading.warnings, (reading.error, reading.warnings)
    built = {k for s in list(rows)[:40] for k in KINDS if make_question(rows, s, set(KINDS) - {k}, random.Random(1), "x", date(2026, 10, 24))}
    assert built >= {"stadium", "founded", "capacity", "mascotName", "fightSong", "trophy", "date", "firstSeason", "conferenceSince", "winningestCoach", "longestWinStreak", "recordCrowd"}


def test_a_question_has_three_distinct_choices_one_right_and_no_future_year(rows):
    asked: list[dict] = []
    for i in range(30):
        q = pick_question(rows, [TEAM, "Diner Tech"], asked, random.Random(i), f"q{i}", date(2026, 10, 24))
        if q is None:
            break
        asked.append(q.as_dict())
        assert len(q.choices) == 3 and len(set(q.choices)) == 3 and 0 <= q.answer < 3 and q.text and q.fact
        assert all(int(c) <= 2026 for c in q.choices if c.isdigit()), q.choices
    kinds = [(q["school"], q["kind"]) for q in asked]
    assert len(kinds) == len(set(kinds)), "a kind is asked once a day per school"
    assert len(asked) >= 12, "two demo schools give a day's worth"
    same = pick_question(rows, [TEAM], [], random.Random(5), "again", date(2026, 10, 24))
    assert same.as_dict() == pick_question(rows, [TEAM], [], random.Random(5), "again", date(2026, 10, 24)).as_dict(), "deterministic for a seed"


def test_malformed_facts_build_nothing_and_never_raise():
    rows = {"A": {"founded": "x", "stadium": None, "heismans": [None, 5, "no year"], "rivalries": "junk", "dates": [{"date": "junk", "event": 3}, "x"], "retiredNumbers": ["nobody"], "longestWinStreak": "none", "recordCrowd": 7}, "B": "junk", "C": {"stadium": "C Field"}}
    assert make_question(rows, "A", set(), random.Random(1), "q", date(2026, 10, 24)) is None
    assert make_question(rows, "B", set(), random.Random(1), "q", date(2026, 10, 24)) is None
    assert make_question(rows, "C", set(), random.Random(1), "q", date(2026, 10, 24)) is None, "one stadium and no other schools' stadiums: no decoys"
    assert pick_question(rows, ["A", "B", "C", "Nobody"], [], random.Random(1), "q", date(2026, 10, 24)) is None
    assert make_question({}, "A", set(), random.Random(1), "q") is None


# --- the session --------------------------------------------------------------------------------------------------------


def test_joining_is_case_sensitive_starts_the_day_and_welcomes_a_team_back(tmp_path, rows):
    now = [KICKOFF - timedelta(hours=3)]
    svc = service(tmp_path, rows, now)
    assert svc.game_day(now[0]) and svc.now_for(None, now[0])["day"] is None
    first = svc.join("Couch Coordinators", now[0])
    assert first["new"] and first["welcome"] is None and first["day"] == "2026-10-24"
    other = svc.join("couch coordinators", now[0])
    assert other["new"], "a different case is a different team"
    with pytest.raises(TriviaError):
        svc.join("   ", now[0])
    with pytest.raises(TriviaError):
        svc.join("x" * 41, now[0])
    assert clean_name("  Nana's   Nachos ") == "Nana's Nachos"
    tick(svc, now[0])
    q = svc.now_for("Couch Coordinators", now[0])["question"]
    assert q and q["open"] and "answer" not in q and "fact" not in q, "the popup never carries the answer"
    assert svc.now_for("couch coordinators", now[0])["question"]["id"] == q["id"], "every tablet gets the same question"
    assert svc.now_for(None, now[0])["question"] is None, "a tablet that did not join sees no question"
    shown = svc.now_for(None, now[0], board=True)["question"]
    assert shown and shown["id"] == q["id"] and "answer" not in shown and shown["yourPick"] is None, "the big screen shows the open question, never its answer"
    day = svc.data["days"]["2026-10-24"]
    right = day["questions"][0]["answer"]
    svc.answer("Couch Coordinators", q["id"], right, now[0] + timedelta(seconds=5))
    later = now[0] + timedelta(seconds=OPEN_SECONDS + 1)
    with pytest.raises(TriviaError):
        svc.answer("couch coordinators", q["id"], 0, later)
    tick(svc, later)
    assert svc.now_for("Couch Coordinators", later)["team"]["today"] == [1, 1] and svc.now_for("couch coordinators", later)["team"]["today"] == [0, 1]
    # a later day: the welcome carries the season so far
    svc.end_day(later, by="host")
    next_week = [KICKOFF + timedelta(days=7)]
    svc2 = service(tmp_path, rows, next_week)
    back = svc2.join("Couch Coordinators", next_week[0])
    assert not back["new"] and back["welcome"] == "Welcome back, Couch Coordinators: 1 of 1 this season before today" and back["seasonBefore"] == [1, 1]
    assert svc2.now_for("Couch Coordinators", next_week[0])["team"]["season"] == [1, 1]


def test_the_pace_outside_our_game_and_one_at_each_break_inside_it(tmp_path, rows):
    now = [KICKOFF - timedelta(hours=2)]
    state = {"status": "pre"}
    svc = service(tmp_path, rows, now, state=lambda d: state)
    svc.join("A", now[0])
    tick(svc, now[0], answer_as="A")
    day = svc.data["days"]["2026-10-24"]
    assert len(day["questions"]) == 1 and day["questions"][0]["context"] == "pre"
    tick(svc, now[0] + timedelta(minutes=14), answer_as="A")
    assert len(day["questions"]) == 1, "fifteen minutes between questions"
    tick(svc, now[0] + timedelta(minutes=15), answer_as="A")
    assert len(day["questions"]) == 2
    assert svc.now_for("A", now[0] + timedelta(minutes=16))["day"]["next"].startswith("Next at ")
    # the game (owner 2026-10-22: "They should fire at the end of the quarters, and halftime"): nothing while the clock runs
    state.update({"status": "in_progress", "period": 1, "clock": {"minutes": 7, "seconds": 59}})
    t = KICKOFF + timedelta(minutes=20)
    tick(svc, t)
    assert len(day["questions"]) == 2, "no fifteen-minute pace and no question while the quarter is on"
    assert svc.now_for("A", t)["day"]["next"] == "Next at the end of the 1st quarter"
    state["clock"] = {"minutes": 0, "seconds": 0}
    tick(svc, t + timedelta(minutes=10), answer_as="A")
    assert len(day["questions"]) == 3 and day["questions"][-1]["context"] == "game" and day["questions"][-1]["period"] == 1 and day["periods"] == [1]
    assert day["questions"][-1]["school"] in (TEAM, "Diner Tech"), "during the game, the two schools playing"
    state.update({"period": 2, "clock": {"minutes": 14, "seconds": 30}})
    tick(svc, t + timedelta(minutes=13))
    assert len(day["questions"]) == 3, "one a break: the start of the 2nd does not ask the 1st again"
    assert svc.now_for("A", t + timedelta(minutes=13))["day"]["next"] == "Next at halftime"
    # halftime seen only after the feed moved on: the first three minutes of the 3rd still ask it
    state.update({"period": 3, "clock": {"minutes": 13, "seconds": 10}})
    tick(svc, t + timedelta(minutes=60), answer_as="A")
    assert len(day["questions"]) == 4 and day["periods"] == [1, 2], "halftime's question"
    # the end of the 3rd missed entirely: never asked late
    state.update({"period": 4, "clock": {"minutes": 9, "seconds": 0}})
    tick(svc, t + timedelta(minutes=95))
    assert len(day["questions"]) == 4 and day["periods"] == [1, 2], "a missed break is not asked late"
    assert svc.now_for("A", t + timedelta(minutes=95))["day"]["next"] == "Next at the end of the game"
    # tied after four: the 4th's 0:00 is the end of regulation's question; overtime asks nothing more
    state["clock"] = {"minutes": 0, "seconds": 0}
    tick(svc, t + timedelta(minutes=110), answer_as="A")
    assert len(day["questions"]) == 5 and day["periods"] == [1, 2, 4]
    state.update({"period": 5, "clock": {"minutes": 0, "seconds": 0}})
    tick(svc, t + timedelta(minutes=120))
    assert len(day["questions"]) == 5, "no question in overtime"
    state.update({"status": "final"})
    tick(svc, t + timedelta(minutes=122))
    assert len(day["questions"]) == 5, "the end of the game was asked already: the pace takes over, fifteen minutes after"
    tick(svc, t + timedelta(minutes=140), answer_as="A")
    assert len(day["questions"]) == 6 and day["questions"][-1]["context"] == "post", "after the final the pace is back"


def test_the_final_asks_the_end_of_the_game_once(tmp_path, rows):
    now = [KICKOFF + timedelta(hours=3)]
    state = {"status": "in_progress", "period": 4, "clock": {"minutes": 1, "seconds": 0}}
    svc = service(tmp_path, rows, now, state=lambda d: state)
    svc.join("A", now[0])
    tick(svc, now[0])
    day = svc.data["days"]["2026-10-24"]
    assert day["questions"] == []
    state.update({"status": "final", "clock": {"minutes": 0, "seconds": 0}})
    tick(svc, now[0] + timedelta(minutes=2), answer_as="A")
    assert len(day["questions"]) == 1 and day["questions"][0]["period"] == 4 and day["questions"][0]["context"] == "game", "the end of the game, about the two schools"
    tick(svc, now[0] + timedelta(minutes=3))
    assert len(day["questions"]) == 1, "once"
    # junk clocks and periods ask nothing
    for bad in ({"status": "in_progress", "period": None, "clock": None}, {"status": "in_progress", "period": "2", "clock": {"minutes": 0}}, {"status": "in_progress", "period": 0, "clock": {"minutes": 0, "seconds": 0}}):
        fresh = service(tmp_path / str(len(str(bad))), rows, now, state=lambda d, b=bad: b)
        fresh.join("B", now[0])
        tick(fresh, now[0])
        assert fresh.data["days"]["2026-10-24"]["questions"] == [], bad


def test_the_game_only_pace_and_the_switches(tmp_path, rows):
    now = [KICKOFF - timedelta(hours=2)]
    svc = service(tmp_path, rows, now, pace="game")
    svc.join("A", now[0])
    tick(svc, now[0] + timedelta(minutes=30))
    assert not svc.data["days"]["2026-10-24"]["questions"] and svc.now_for("A", now[0])["day"]["next"] == "Next during our game"
    off = service(tmp_path, rows, now, trivia=False)
    tick(off, now[0] + timedelta(minutes=31))
    assert not off.data["days"]["2026-10-24"]["questions"] and off.now_for("A", now[0])["on"] is False
    quiet = service(tmp_path, rows, now, board=False)
    assert quiet.now_for("A", now[0])["standings"] == [] and quiet.now_for("A", now[0])["board"] is False


def test_three_unanswered_questions_end_the_day_and_a_join_starts_it_again(tmp_path, rows):
    now = [KICKOFF - timedelta(hours=4)]
    svc = service(tmp_path, rows, now)
    svc.join("A", now[0])
    at = now[0]
    for _ in range(QUIET_AFTER):
        tick(svc, at)
        at += timedelta(minutes=15)
    tick(svc, at)  # tallies the third
    day = svc.data["days"]["2026-10-24"]
    assert day["endedAt"] and day["endedBy"] == "quiet" and day["quiet"] == QUIET_AFTER
    assert svc.now_for("A", at)["day"]["endedAt"] and svc.now_for("A", at)["question"] is None
    assert svc.join("B", at + timedelta(minutes=1))["day"] == "2026-10-24" and day["endedAt"] is None, "a join reopens the day"
    assert svc.end_day(at + timedelta(minutes=2), by="host")["endedBy"] == "host"
    assert svc.end_day(at + timedelta(minutes=3)) is None, "nothing running"
    old = service(tmp_path, rows, [at + timedelta(hours=DAY_HOURS + 1)])
    old.data["days"]["2026-10-24"]["endedAt"] = None
    assert old.current_day(at + timedelta(hours=DAY_HOURS + 1)) is None and old.data["days"]["2026-10-24"]["endedBy"] == "night"


def test_leave_rename_mark_and_the_page(tmp_path, rows):
    now = [KICKOFF - timedelta(hours=1)]
    marks: list[tuple] = []
    svc = service(tmp_path, rows, now)
    svc.on_mark = lambda *args: marks.append(args)
    svc.join("Couch Coordinators", now[0])
    svc.join("Nana's Nachos", now[0])
    tick(svc, now[0])
    q = svc.now_for("Couch Coordinators", now[0])["question"]
    svc.answer("Nana's Nachos", q["id"], svc.data["days"]["2026-10-24"]["questions"][0]["answer"], now[0])
    later = now[0] + timedelta(minutes=2)
    tick(svc, later)
    assert svc.rename("Couch Coordinators", "Couch Coordinators II")["name"] == "Couch Coordinators II"
    with pytest.raises(TriviaError):
        svc.rename("Couch Coordinators II", "Nana's Nachos")
    with pytest.raises(TriviaError):
        svc.rename("Nobody", "Someone")
    page = svc.page_for("Couch Coordinators II", later, is_host=True)
    assert page["isHost"] and page["team"]["name"] == "Couch Coordinators II" and page["team"]["today"] == [0, 1]
    assert [b["name"] for b in page["board"]] == ["Nana's Nachos", "Couch Coordinators II"] and page["board"][0]["today"] == [1, 1]
    assert page["questions"][0]["answer"] is not None and page["questions"][0]["fact"] and page["questions"][0]["answered"] == 1
    assert page["seasonTable"][0]["span"].startswith("since ") and page["seasonTable"][0]["our"]["opponent"] == "Diner Tech"
    assert page["best"]["asked"] == 1 and page["teamsThisSeason"] == 2
    mark = svc.mark(q["id"], "The year is wrong", later)
    assert mark["school"] == q["school"] and marks and marks[0][0] == q["school"] and marks[0][2] == "The year is wrong"
    assert svc.page_for("Nana's Nachos", later)["questions"][0]["marked"] is True
    with pytest.raises(TriviaError):
        svc.mark("nope", "", later)
    svc.leave("Nana's Nachos")
    assert [b["name"] for b in svc.page_for(None, later)["board"]] == ["Couch Coordinators II"] and svc.now_for("Nana's Nachos", later)["team"]["hidden"]
    assert svc.join("Nana's Nachos", later)["welcome"] is None and not svc.data["teams"]["Nana's Nachos"]["hidden"], "joining again unhides"
    saved = json.loads((tmp_path / "trivia.json").read_text(encoding="utf-8"))
    assert saved["season"] == 2026 and set(saved) == {"format", "season", "teams", "days", "marks"} and saved["marks"][0]["note"] == "The year is wrong"


def test_a_damaged_or_old_file_is_set_aside(tmp_path, rows):
    (tmp_path / "trivia.json").write_text("{broken", encoding="utf-8")
    now = [KICKOFF]
    svc = service(tmp_path, rows, now)
    assert svc.data["teams"] == {} and list(tmp_path.glob("trivia.bad-*.json"))
    (tmp_path / "trivia.json").write_text(json.dumps({"format": 1, "season": 2025, "teams": {"Old": {}}, "days": {}, "marks": []}), encoding="utf-8")
    fresh = service(tmp_path, rows, now)
    assert fresh.data["teams"] == {} and (tmp_path / "trivia-2025.json").is_file()
    (tmp_path / "trivia.json").write_text(json.dumps({"season": 2026, "teams": {"A": "junk", "B": {}}, "days": {"x": "junk", "y": {"questions": "junk"}}, "marks": "junk"}), encoding="utf-8")
    kept = service(tmp_path, rows, now)
    assert set(kept.data["teams"]) == {"B"} and kept.data["days"] == {} and kept.data["marks"] == []
    assert kept.now_for("B", now[0])["team"]["today"] == [0, 0], "a team row without its lists still answers"


# --- the routes, the guests, the settings ------------------------------------------------------------------------------


def demo_facts_for(app, league) -> None:
    write_demo_facts(app.state.settings.data_dir, league, 2026)


def test_the_routes_let_a_guest_join_and_answer_and_the_host_end(client: TestClient, app, league):
    demo_facts_for(app, league)
    app.state.live.window = NS(game_id=1, home=TEAM, away="Diner Tech", kickoff=app.state.cfbd._clock())
    app.state.live.state = lambda delay: None
    app.state.host_access.set_pin("1234")
    guest = client  # no cookie, not the server computer in the test client: a guest
    assert guest.get("/api/trivia/now").json()["data"]["gameDay"] is True
    joined = guest.post("/api/trivia/join", json={"name": "Section 12"}).json()["data"]
    assert joined["name"] == "Section 12" and joined["new"]
    assert guest.post("/api/trivia/join", json={"name": " "}).status_code == 400
    now = guest.get("/api/trivia/now?name=Section%2012").json()["data"]
    assert now["question"] and now["team"]["joined"] and "answer" not in now["question"]
    assert guest.post("/api/trivia/answer", json={"name": "Section 12", "questionId": now["question"]["id"], "choice": 1}).status_code == 200
    assert guest.post("/api/trivia/answer", json={"name": "Section 12", "questionId": now["question"]["id"], "choice": 7}).status_code == 422
    assert guest.post("/api/trivia/rename", json={"name": "Section 12", "newName": "Section 13"}).json()["data"]["name"] == "Section 13"
    assert guest.post("/api/trivia/mark", json={"questionId": now["question"]["id"], "note": "hmm"}).status_code == 200
    page = guest.get("/api/trivia?name=Section%2013").json()["data"]
    assert page["isHost"] is False and page["team"]["name"] == "Section 13" and len(page["questions"]) == 1
    refused = guest.post("/api/trivia/end", json={})
    assert refused.status_code == 403, "a guest cannot end the day"
    assert guest.put("/api/settings", json={"trivia": False}).status_code == 403, "nor change the settings"
    assert guest.post("/api/trivia/leave", json={"name": "Section 13"}).status_code == 200
    app.state.host_access.clear()
    host = client
    assert host.post("/api/trivia/end", json={}).json()["data"]["endedBy"] == "host"
    assert host.post("/api/trivia/end", json={}).json()["data"]["ended"] is False
    facts = app.state.season_notes.facts_for(now["question"]["school"])
    assert facts and facts["marks"] and facts["marks"][0]["note"] == "hmm", "the mark reached the facts file"


def test_the_settings_carry_the_three_switches(client: TestClient):
    prefs = client.get("/api/settings").json()["data"]["prefs"]
    assert prefs["trivia"] is True and prefs["triviaBoard"] is True and prefs["triviaPace"] == "15"
    assert client.put("/api/settings", json={"triviaPace": "30", "trivia": False}).status_code == 200
    assert client.get("/api/trivia/now").json()["data"]["on"] is False and client.get("/api/trivia/now").json()["data"]["pace"] == "30"
    assert client.put("/api/settings", json={"triviaPace": "hourly"}).status_code in (400, 422)


def test_the_demo_facts_file_is_written_once(tmp_path, league):
    path = write_demo_facts(tmp_path, league, 2026)
    assert path and path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert TEAM in data["teams"] and data["teams"][TEAM]["conference"] == CONFERENCE and data["batches"][CONFERENCE]["author"] == "the demo"
    assert write_demo_facts(tmp_path, league, 2026) is None, "an install's own facts are kept"
