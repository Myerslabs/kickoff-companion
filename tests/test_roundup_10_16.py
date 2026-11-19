"""The 2026-10-16 roundup (owner): the season loads cover my primary and secondary teams and the next opponent only, so
the first load is quick; Claude Code's runs report their progress to the loading bar (/api/prompts/progress) so the pages
can wait for the end; the notes file's location comes with this week's notes, for notes written by hand; a team page
says whether the loads cover its school."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from app.api.prompts import progress
from tests.conftest import CONFERENCE, TEAM, fixture_payload, follow_conference
from tests.test_season_notes import league  # noqa: F401 - routes the fake CFBD

FBS = {t["school"]: t["conference"] for t in fixture_payload("teams_fbs")}


def next_opponent(client) -> str | None:
    program = client.get("/api/program/next").json()["data"]
    return (program.get("them") or {}).get("school")


def covered(status: dict[str, Any], kind: str = "coaches") -> int:
    return sum(b["schools"] for b in status[kind])


def test_the_loads_cover_my_teams_and_the_next_opponent_only(client, fake_cfbd):
    from tests.test_program import route_program

    route_program(fake_cfbd)
    opponent = next_opponent(client)
    mine = {TEAM} | ({opponent} if opponent in FBS else set())
    status = client.get("/api/season-notes").json()["data"]
    assert status["coachesOf"] == len(mine) == covered(status) == covered(status, "facts") == covered(status, "costs")
    assert {b["conference"] for b in status["coaches"]} == {FBS[s] for s in mine}, "a conference of nobody I follow is not there"
    prompt = client.get("/api/season-notes/prompt", params={"kind": "coaches", "key": "all"}).json()["data"]["prompt"]
    strangers = [s for s, c in FBS.items() if s not in mine and c != FBS[TEAM]]
    assert TEAM in prompt and strangers and not any(f" {s};" in prompt or prompt.rstrip().endswith(s) for s in strangers[:20])
    assert client.get("/api/season-notes/prompt", params={"kind": "facts", "key": next(c for c in set(FBS.values()) if c not in {FBS[s] for s in mine})}).status_code == 404


def test_a_followed_conference_no_longer_widens_the_loads(client, league, app):  # noqa: F811
    """Replaces "following a conference adds its schools": that behavior is gone. Batch 3 (owner 2026-11-19): "I want
    to take out all the secondary teams ... Let's just have one team listed, and a change team for the switch." A
    likedConferences saved before (the league fixture saves one) leaves the loads at our team and the next opponent."""
    follow_conference(app)
    status = client.get("/api/season-notes").json()["data"]
    opponent = next_opponent(client)
    assert opponent and status["coachesOf"] == 2 == covered(status) == covered(status, "facts") == covered(status, "costs")
    assert next(b for b in status["coaches"] if b["conference"] == CONFERENCE)["schools"] == 1, "of our conference, our team alone"
    assert {b["conference"] for b in status["coaches"]} == {FBS[TEAM], FBS[opponent]}


def test_a_conference_saved_before_is_run_again_for_a_new_opponent(client, league, app):  # noqa: F811
    """The set moves with the next opponent, so 'missing' looks school by school, not at the conference's saved stamp.
    Since batch 3 (owner 2026-11-19, one team) no school joins by following a conference; the opponent changing is
    what brings a new school into a conference saved before."""
    from app.api.season_notes import start_season_run
    from app.services import season_prompts
    from tests.test_season_notes import coaches_answer

    opponent = next_opponent(client)
    conference = FBS[opponent]
    last_week = next(s for s, c in sorted(FBS.items()) if c == conference and s != opponent)
    notes = app.state.season_notes
    notes.save_coaches(season_prompts.read_coaches(coaches_answer(schools=[last_week]), conference, [last_week]).value, conference, [last_week])
    assert notes.coaches_for(last_week), "last week's opponent of the same conference was saved"
    assert client.post("/api/season-notes/save", json={"kind": "coaches", "key": CONFERENCE, "text": coaches_answer(schools=[TEAM])}).json()["data"]["saved"]
    asked: list[str] = []

    async def fake_start(kind, batches, command):
        asked.extend(b.key for b in batches)
        return {"running": True}

    app.state.season_runner.start = fake_start
    client.portal.call(lambda: start_season_run(SimpleNamespace(app=app), "coaches", None, True))
    assert conference in asked and CONFERENCE not in asked, "the new opponent is still missing; our team is loaded"
    asked.clear()
    assert client.post("/api/season-notes/save", json={"kind": "coaches", "key": conference, "text": coaches_answer(schools=[opponent])}).json()["data"]["saved"]
    client.portal.call(lambda: start_season_run(SimpleNamespace(app=app), "coaches", None, True))
    assert conference not in asked


def test_a_team_page_says_whether_the_loads_cover_it(client, fake_cfbd, app):
    """Our team and the next opponent are covered; a stranger is not, and since batch 3 (owner 2026-11-19, one team)
    following its conference no longer brings it in."""
    from tests.test_program import route_program

    route_program(fake_cfbd)
    opponent = next_opponent(client)
    assert client.get(f"/api/team/{TEAM}").json()["data"]["inLoadSet"] is True
    assert client.get(f"/api/team/{opponent}").json()["data"]["inLoadSet"] is True
    stranger = next(s for s, c in FBS.items() if s not in (TEAM, opponent) and c != FBS[TEAM])
    assert client.get(f"/api/team/{stranger}").json()["data"]["inLoadSet"] is False
    follow_conference(app, FBS[stranger])
    assert client.get(f"/api/team/{stranger}").json()["data"]["inLoadSet"] is False, "a liked conference no longer brings its schools in"


def test_the_notes_file_location_comes_with_this_weeks_notes(client, league, app):  # noqa: F811
    notes = client.get("/api/prompts").json()["data"]["notes"]
    assert notes["gameId"] and notes["file"].endswith(f"{notes['gameId']}.json") and notes["fileExists"] is False
    assert notes["example"] is None, "a data folder without the example says nothing about it"
    (app.state.settings.data_dir / "notes").mkdir(parents=True, exist_ok=True)
    (app.state.settings.data_dir / "notes" / "_example.json").write_text("{}", encoding="utf-8")
    again = client.get("/api/prompts").json()["data"]["notes"]
    assert again["example"].endswith("_example.json")
    program = client.get(f"/api/program/{notes['gameId']}").json()["data"]
    assert program["notes"]["file"] == notes["file"], "the Pre-Game Program's notes band has the same location"


# --- the loading bar's one question ----------------------------------------------------------------------------------


def runners(runs=None, season=None, notes=None) -> SimpleNamespace:
    idle_runs = {"running": False, "finishedAt": None, "steps": []}
    idle_season = {"running": False, "kind": None, "batches": []}
    idle_notes = {"running": False, "finishedAt": None, "mode": "full"}
    return SimpleNamespace(
        settings=SimpleNamespace(claude_command="claude"),
        prompt_runs=SimpleNamespace(status=lambda: runs or idle_runs),
        season_runner=SimpleNamespace(status=lambda command: season or idle_season),
        notes=SimpleNamespace(status=lambda command: notes or idle_notes),
    )


def test_progress_when_nothing_runs_says_when_the_last_run_ended():
    idle = progress(runners(notes={"running": False, "finishedAt": "2026-10-16T14:00:00Z", "mode": "full"}, season={"running": False, "kind": "facts", "batches": [{"key": "A", "state": "saved", "finishedAt": "2026-10-16T15:00:00Z"}]}))
    assert idle["running"] is False and idle["fraction"] is None and idle["lastFinishedAt"] == "2026-10-16T15:00:00Z"
    assert progress(runners())["lastFinishedAt"] is None


def test_progress_of_the_one_run_counts_its_steps_and_the_season_batches_inside():
    steps = [{"kind": "preseason", "label": "The season load", "state": "skipped"}, {"kind": "coaches", "label": "Coaches", "state": "running"}, {"kind": "costs", "label": "Roster costs", "state": "waiting"}, {"kind": "notes", "label": "This week's notes", "state": "waiting"}]
    season = {"running": True, "kind": "coaches", "batches": [{"key": "East", "state": "saved"}, {"key": "West", "state": "running"}]}
    p = progress(runners(runs={"running": True, "startedAt": "2026-10-16T14:00:00Z", "steps": steps}, season=season))
    assert p["running"] is True and p["label"] == "Coaches" and p["detail"] == "step 2 of 4, West (2 of 2)"
    assert abs(p["fraction"] - (1 + 0.5) / 4) < 1e-9 and p["startedAt"] == "2026-10-16T14:00:00Z" and p["run"]["steps"] == steps


def test_progress_of_a_season_run_alone_and_of_the_notes():
    season = {"running": True, "kind": "facts", "batches": [{"key": "East", "state": "saved", "startedAt": "2026-10-16T14:00:00Z"}, {"key": "West", "state": "running"}, {"key": "North", "state": "waiting"}]}
    p = progress(runners(season=season))
    assert p["label"] == "School history and facts" and p["detail"] == "West, 2 of 3" and abs(p["fraction"] - 1 / 3) < 1e-9
    n = progress(runners(notes={"running": True, "startedAt": "2026-10-16T14:00:00Z", "mode": "injuries", "finishedAt": None}))
    assert n["running"] is True and n["label"] == "The injury report" and n["fraction"] is None, "no steps: the bar moves without a fraction"


def test_the_progress_route_answers_without_a_cfbd_call(client, fake_cfbd):
    before = len(fake_cfbd.requests)
    body = client.get("/api/prompts/progress").json()
    assert body["data"]["running"] is False and "run" in body["data"]
    assert len(fake_cfbd.requests) == before
