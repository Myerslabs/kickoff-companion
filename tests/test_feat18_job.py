"""FEAT-18 the Circle of Blame's weekly job and its answers (spec C.3, C.6, C.7, C.9; the owner's answers of 2026-10-30),
against the simulated league with a fake Claude Code that answers from the pack it is given: no command here is a skip, the
schedule switch, one report a game week, the pack's blocks (each data or "unavailable"), the retry with the errors, a
second failure, a model that is not Opus, the timeout, every source failing, the headlines, Regenerate the host's only,
and a skipped job that never keeps the weekly run due."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.demo.upstream import DemoUpstream
from app.jobs import JobRuns, JobSkipped, run_job
from app.jobs import circle_of_blame as blame_job
from app.jobs.circle_of_blame import BlameJob
from app.jobs.weekly import WeeklyJobs
from app.llm.claude_cli import ClaudeFailed, ClaudeResult
from app.logging_setup import configure_logging, shutdown_logging
from app.main import create_app
from app.services.blame import BlameStore
from tests.conftest import league

SATURDAY = datetime(2026, 9, 26, 22, 0, tzinfo=timezone.utc)
BLOCKS = ["about", "season", "latestGame", "teamStats", "players", "coaching", "talentEdge", "imperialism", "headlines", "lastWeek"]


def pack_of(prompt: str) -> dict[str, Any]:
    return json.loads(re.search(r"<evidence_pack>\s*(.*?)\s*</evidence_pack>", prompt, re.DOTALL).group(1))


def report_for(pack: dict[str, Any], *, shares: tuple[int, ...] = (40, 25, 20, 15), name_coach: bool = True) -> dict[str, Any]:
    week = int(pack["about"]["through"].split()[-1])
    coach = pack["coaching"].get("headCoach") if isinstance(pack.get("coaching"), dict) else None
    names = [("Offensive line", "unit"), ("Third-down defense", "scheme"), ("Roster building", "roster"), ("The schedule", "schedule")]
    if name_coach and isinstance(coach, str) and not coach.startswith("not in"):
        names[3] = (coach, "coach")
    evidence = [{"metric": "Yards per carry", "value": "3.1", "context": "ranks 120th"}, {"metric": "Sacks allowed", "value": "19", "context": "ranks 110th"}]
    return {
        "schema_version": "1", "season": 2026, "week": week, "after_result": "loss", "verdict": "The line loses the line of scrimmage.",
        "slices": [{"name": n, "kind": k, "share_pct": s, "case": "The case.", "evidence": evidence, "trend": "new"} for (n, k), s in zip(names, shares, strict=False)],
        "movement": "First report of the season.", "limitations": ["No snap counts."], "confidence": "medium",
    }


class FakeCli:
    """Answers with `answers` in turn: a callable(pack) -> report, an exception, or raw text."""

    timeout = 300

    def __init__(self, *answers: Any, model: str = "claude-opus-5-5") -> None:
        self.answers = list(answers)
        self.model = model
        self.prompts: list[str] = []

    async def ask(self, system_text: str, system_file: Path | None, prompt: str) -> ClaudeResult:
        self.prompts.append(prompt)
        assert "Circle of Blame" in prompt and "{team}" not in system_text and "Florida" in system_text
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        text = answer if isinstance(answer, str) else json.dumps(answer(pack_of(prompt)))
        return ClaudeResult(text=text, model=self.model, models={self.model: {"outputTokens": 900}}, stdout='{"type":"result"}', stderr="", duration_ms=41000)


@pytest.fixture
def lclient(settings: Settings):
    upstream = DemoUpstream(league(), lambda: SATURDAY, tier=2)
    configure_logging(settings)
    application = create_app(settings, cfbd_transport=httpx.MockTransport(upstream.handler))
    application.state.cfbd._clock = lambda: SATURDAY
    try:
        with TestClient(application, base_url="https://testserver") as client:
            client.portal.call(application.state.live.stop_background)
            client.app_state = application.state  # type: ignore[attr-defined]
            yield client
    finally:
        shutdown_logging()


def use(client: TestClient, cli: Any) -> BlameJob:
    """The registered job, with a fake Claude Code, and Claude on a schedule switched on in Settings unless the test
    set it already (Kickoff Companion 2.0: off until turned on)."""
    state = client.app_state  # type: ignore[attr-defined]
    prefs = Path(state.settings.data_dir) / "settings.json"
    if not prefs.exists():
        prefs.write_text(json.dumps({"scheduledRuns": True}), encoding="utf-8")
    job = BlameJob(state.cfbd, state.settings, cli=cli)
    state.jobs.jobs[blame_job.NAME] = job.run
    return job


def settle(client: TestClient) -> None:
    """Wait on the server's own loop for the run in the background to end."""
    state = client.app_state  # type: ignore[attr-defined]

    async def wait() -> None:
        if state.jobs._task is not None:
            await state.jobs._task

    client.portal.call(wait)


def run(client: TestClient, **options: Any) -> dict[str, Any]:
    state = client.app_state  # type: ignore[attr-defined]
    started = client.portal.call(lambda: state.jobs.start(blame_job.NAME, **options))
    settle(client)
    return state.jobs.runs.get(started["id"])


def test_without_claude_code_the_run_is_skipped_and_said(lclient: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(blame_job, "find_command", lambda command="claude": (None, "C:/Windows"))
    done = run(lclient)
    assert done["status"] == "skipped" and "Claude Code isn't on this computer" in done["message"]
    page = lclient.get("/api/blame/now").json()["data"]
    assert page["available"] is False and "isn't on this computer" in page["message"] and page["failed"] is False
    health = lclient.get("/api/health").json()["data"]
    check = next(c for c in health["checks"] if c["name"] == "weekly jobs")
    assert check["status"] == "ok" and "Circle of Blame skipped" in check["detail"]


def test_a_report_is_written_from_the_pack_once_a_game_week(lclient: TestClient):
    fake = FakeCli(report_for, report_for)
    job = use(lclient, fake)
    done = run(lclient)
    assert done["status"] == "ok", done["message"]
    assert "written by claude-opus-5-5 in 41 s" in done["message"]
    pack = pack_of(fake.prompts[0])
    assert list(pack) == BLOCKS
    for name in BLOCKS:
        assert isinstance(pack[name], dict | list) and pack[name], name
    assert pack["lastWeek"] == {"none": "This is the first report of the season."}
    assert isinstance(pack["season"]["record"], dict) and isinstance(pack["latestGame"]["teamBox"], dict)
    assert pack["latestGame"]["result"] in ("win", "loss", "tie") and pack["players"]["topByUsage"], "the usage list"
    assert pack["talentEdge"] == {"unavailable": "Talent Edge has not been worked out this season"} or "us" in pack["talentEdge"]
    assert "Flavor only" in json.dumps(pack["imperialism"]) or "unavailable" in pack["imperialism"]
    store = BlameStore(job.data_dir, 2026)
    key, record = store.latest()
    assert record["report"]["slices"][0]["name"] == "Offensive line" and record["modelUsed"] == "claude-opus-5-5"
    assert record["promptVersion"] == {"system": "circle_of_blame.system/2", "user": "circle_of_blame.user/1"} and len(record["inputHash"]) == 64
    assert (store.dir / f"{key}.pack.json").is_file()
    again = run(lclient)
    assert again["status"] == "ok" and "already written" in again["message"] and len(fake.prompts) == 1, "one report a game week"
    forced = run(lclient, force=True)
    assert forced["status"] == "ok" and len(fake.prompts) == 2, "a forced run writes it again"
    assert "pageNow" not in pack_of(fake.prompts[1]), "a forced run starts fresh"
    fake.answers.append(report_for)
    refreshed = run(lclient, refresh=True)
    assert refreshed["status"] == "ok" and len(fake.prompts) == 3, "Run with Claude (batch 4) writes it again"
    third = fake.prompts[2]
    assert "pageNow" not in pack_of(third), "the old report never joins the evidence: the name check reads it"
    tail = third[third.index("What the page shows now:"):]
    assert "remove what is out of date" in third and "Offensive line" in tail, "with the report as it stands, after the pack"
    page = lclient.get("/api/blame/now").json()["data"]
    assert page["available"] is True and page["latest"]["key"] == key and "raw" not in page["latest"]
    assert page["history"][0]["top"]["share"] == 40 and page["weeks"][0]["key"] == key and page["canRegenerate"] is True
    one = lclient.get(f"/api/blame/2026/{key}")
    assert one.status_code == 200 and one.json()["data"]["report"]["verdict"]
    assert lclient.get(f"/api/blame/2026/{record['week']}").status_code == 200, "a bare week number"
    missing = lclient.get("/api/blame/2026/week-99")
    assert missing.status_code == 404 and key in missing.json()["errors"][0]["message"]
    status = lclient.get("/api/datastatus?view=blame").json()["data"]
    assert "The report" in json.dumps(status)


def test_a_coach_named_in_the_pack_passes_the_name_guard(lclient: TestClient):
    fake = FakeCli(lambda pack: report_for(pack, name_coach=True))
    use(lclient, fake)
    done = run(lclient)
    coach = pack_of(fake.prompts[0])["coaching"]["headCoach"]
    assert done["status"] == "ok" and isinstance(coach, str)


def test_a_failed_check_is_tried_once_more_with_its_errors(lclient: TestClient):
    fake = FakeCli(lambda pack: report_for(pack, shares=(40, 25, 20, 14)), report_for)
    job = use(lclient, fake)
    done = run(lclient)
    assert done["status"] == "ok" and "on the second try" in done["message"]
    assert "failed these checks" in fake.prompts[1] and "not 99" in fake.prompts[1]
    assert BlameStore(job.data_dir, 2026).latest()[1]["attempts"] == 2


def test_two_failed_checks_publish_nothing_and_keep_the_raw_output(lclient: TestClient):
    bad = lambda pack: report_for(pack, shares=(40, 25, 20))  # noqa: E731 - three slices
    fake = FakeCli(bad, "not json at all")
    job = use(lclient, fake)
    done = run(lclient)
    assert done["status"] == "failed" and "after 2 tries" in done["message"]
    store = BlameStore(job.data_dir, 2026)
    assert store.latest() is None
    key = next(p.stem for p in (store.dir / "failed").glob("*.json"))
    failure = store.load_failure(key)
    assert len(failure["attempts"]) == 2 and failure["attempts"][0]["errors"] and failure["attempts"][1]["stdout"]
    page = lclient.get("/api/blame/now").json()["data"]
    assert page["available"] is False and page["failed"] is True and "unavailable since" in page["message"]


def test_an_answer_from_another_model_fails_at_once(lclient: TestClient):
    fake = FakeCli(ClaudeFailed("The answer came from claude-sonnet-5-5, not Opus; nothing was kept", "out", "err"), report_for)
    job = use(lclient, fake)
    done = run(lclient)
    assert done["status"] == "failed" and "not Opus" in done["message"] and len(fake.prompts) == 1, "never a retry on another model"
    assert BlameStore(job.data_dir, 2026).latest() is None


def test_two_timeouts_fail(lclient: TestClient):
    fake = FakeCli(TimeoutError(), TimeoutError())
    use(lclient, fake)
    done = run(lclient)
    assert done["status"] == "failed" and "no answer in 300 s" in done["message"]


def test_the_schedule_switch_skips_but_regenerate_writes(lclient: TestClient):
    state = lclient.app_state  # type: ignore[attr-defined]
    (Path(state.settings.data_dir) / "settings.json").write_text(json.dumps({"scheduledRuns": False}), encoding="utf-8")
    fake = FakeCli(report_for)
    use(lclient, fake)
    assert run(lclient)["status"] == "skipped"
    answer = lclient.post("/api/blame/2026/latest/regenerate", json={"confirm": True})
    assert answer.status_code == 200, answer.text
    client_run = answer.json()["data"]["run"]
    settle(lclient)
    assert state.jobs.runs.get(client_run["id"])["status"] == "ok" and len(fake.prompts) == 1


def test_regenerate_is_the_hosts_and_wants_a_confirm(lclient: TestClient):
    use(lclient, FakeCli(report_for))
    assert lclient.post("/api/blame/2026/week-4/regenerate", json={}).status_code == 422
    assert lclient.post("/api/blame/2025/week-4/regenerate", json={"confirm": True}).status_code == 422
    state = lclient.app_state  # type: ignore[attr-defined]
    state.host_access.set_pin("4321")
    refused = lclient.post("/api/blame/2026/week-4/regenerate", json={"confirm": True})
    assert refused.status_code == 403 and refused.json()["errors"][0]["code"] == "view_only"
    assert lclient.get("/api/blame/now").json()["data"]["canRegenerate"] is False


def test_every_source_failing_still_reaches_claude(settings: Settings):
    upstream = DemoUpstream(league(), lambda: SATURDAY, tier=2)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(("/games", "/teams/fbs")) and "team" in request.url.params or request.url.path.endswith("/teams/fbs"):
            return upstream.handler(request)
        return httpx.Response(500, json={"message": "down"})

    configure_logging(settings)
    application = create_app(settings, cfbd_transport=httpx.MockTransport(handler))
    application.state.cfbd._clock = lambda: SATURDAY
    try:
        with TestClient(application, base_url="https://testserver") as client:
            client.portal.call(application.state.live.stop_background)
            fake = FakeCli(lambda pack: report_for(pack, name_coach=False))
            (Path(settings.data_dir) / "settings.json").write_text(json.dumps({"scheduledRuns": True}), encoding="utf-8")  # 2.0: off until turned on
            job = BlameJob(application.state.cfbd, application.state.settings, cli=fake)
            result = client.portal.call(job.run)
            pack = pack_of(fake.prompts[0])
            assert result["message"].startswith("The report for week")
            assert "unavailable" in pack["latestGame"]["teamBox"] and "unavailable" in pack["players"] and "unavailable" in pack["headlines"]
            assert "unavailable" in json.dumps(pack["teamStats"]) and pack["coaching"]["headCoach"]
    finally:
        shutdown_logging()


def test_the_headlines_are_titles_from_the_last_eight_days(settings: Settings, tmp_path: Path):
    now = datetime(2026, 10, 25, 9, 0, tzinfo=timezone.utc)
    rows = [
        {"title": "Gators fall at Texas", "url": "https://a.example/1", "source": "ESPN", "feed": "espn", "publishedAt": (now - timedelta(days=1)).isoformat()},
        {"title": "Gators fall at Texas!", "url": "https://b.example/1", "source": "CBS", "feed": "cbs", "publishedAt": (now - timedelta(days=1, hours=2)).isoformat()},
        {"title": "Old news", "url": "https://a.example/2", "source": "ESPN", "feed": "espn", "publishedAt": (now - timedelta(days=9)).isoformat()},
        {"title": "No date", "url": None, "source": "X", "feed": "x"},
    ] + [{"title": f"Story {i}", "url": f"https://c.example/{i}", "source": "Yahoo", "feed": "yahoo", "publishedAt": (now - timedelta(hours=i)).isoformat()} for i in range(50)]
    feeds = Path(settings.data_dir) / "feeds"
    feeds.mkdir(parents=True, exist_ok=True)
    (feeds / "season-2026.json").write_text(json.dumps({"headlines": rows}), encoding="utf-8")
    job = BlameJob(object(), settings, cli=FakeCli(), clock=lambda: now)  # type: ignore[arg-type]
    titles = job.headlines()
    assert len(titles) == 40 and titles[0]["title"] == "Story 0" and "Old news" not in {t["title"] for t in titles}
    assert all(set(t) == {"title", "source", "publishedAt", "url"} for t in titles)


def test_a_skipped_job_never_keeps_the_weekly_run_due(tmp_path: Path):
    async def ok() -> dict[str, Any]:
        return {"week": 4, "message": "fine"}

    async def skip() -> dict[str, Any]:
        raise JobSkipped("Claude Code isn't on this computer")

    runs = JobRuns(tmp_path)
    weekly = WeeklyJobs(runs, 2026, {"talent_edge": ok, "imperialism": ok, "circle_of_blame": skip})
    import asyncio

    done = asyncio.run(weekly.run())
    assert done["status"] == "ok", "a skipped job is not a failure"
    assert [j["status"] for j in done["detail"]["jobs"]] == ["ok", "ok", "skipped"]
    later = datetime.now().astimezone() + timedelta(hours=4)
    assert weekly.due(later) is False, "no retry every three hours for a skip"
    assert asyncio.run(run_job(runs, "circle_of_blame", 2026, skip))["status"] == "skipped"


def test_claude_on_a_schedule_is_off_until_turned_on(lclient: TestClient):
    """Kickoff Companion 2.0: with nothing set in Settings (scheduledRuns null), the weekly run skips the report."""
    state = lclient.app_state  # type: ignore[attr-defined]
    (Path(state.settings.data_dir) / "settings.json").write_text(json.dumps({"scheduledRuns": None}), encoding="utf-8")
    fake = FakeCli(report_for)
    use(lclient, fake)
    done = run(lclient)
    assert done["status"] == "skipped" and "off" in done["message"].lower() and not fake.prompts, "Claude was never asked"
