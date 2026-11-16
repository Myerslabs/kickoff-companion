"""The season line's Wave 6, second half (owner 2026-11-15: By the numbers on Thursday, "This sounds good"; "Article
replaces the box"): the paper's own article, written by Claude from the app's numbers and refused when a figure is not in
it, kept as a copied story, leading page 2 of the week's paper; its slot in the schedule. No network and no Claude Code:
fake processes and made-up packets."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.services import paper_articles as A
from app.services import writing as W
from app.services.articles import ArticleStore
from app.services.claude_schedule import after_slots, week_slots
from app.services.paper_layout import layout
from tests.test_feat14_layout import story
from tests.test_top25 import lclient, league_app  # noqa: F401 - fixtures used below

ET = ZoneInfo("America/New_York")
PACKET = {
    "team": "Florida", "opponent": "Kentucky", "week": 11, "line": {"formatted": "Kentucky -3", "overUnder": 52.5},
    "us": {"school": "Florida", "record": {"wins": 5, "losses": 4}}, "them": {"school": "Kentucky", "record": "7-2"},
    "figures": [
        {"metric": "profile:third", "what": "Third down", "us": {"value": "42.0%", "nationalRank": 49, "of": 138}, "them": {"value": "34.9%", "nationalRank": 111, "of": 138}},
        {"metric": "profile:tfl_pg", "what": "Tackles for loss per game", "us": {"value": "6.9", "nationalRank": 13, "of": 138}, "them": None},
        {"metric": "profile:takeaways_pg", "what": "Takeaways per game", "us": {"value": "1.8", "nationalRank": 7, "of": 138}, "them": {"value": "0.9", "nationalRank": 113, "of": 138}},
    ],
    "usWinProbability": 0.418,
}
GOOD = {
    "headline": "Third down could decide it in Lexington",
    "dek": "Kentucky converts 34.9% on third down, 111th of 138.",
    "paragraphs": [
        "Florida's front makes 6.9 tackles for loss a game, 13th in the country, and takes the ball away 1.8 times a game.",
        "Kentucky is 7-2 and favored by 3, with a total of 52.5; Florida is 5-4 with a 42% chance to win.",
        "Florida is 49th on third down at 42.0%. The fourth quarter will tell.",
    ],
}


# --- the figure check -------------------------------------------------------------------------------------------------------


def test_the_figures_a_text_writes():
    assert A.numbers_in("Kentucky converts 34.9% on third down, 111th of 138; 7-2 and No. 13 with 1,572 points, +0.20 PPA at 6:15") == ["34.9%", "111", "138", "7", "2", "13", "1572", "0.20", "6", "15"]
    assert A.numbers_in("QB1 and WR2 at the 3rd") == ["3"], "a digit inside a word is no figure"
    assert A.numbers_in(None) == [] and A.numbers_in(5) == []


def test_an_article_from_the_data_passes():
    assert A.check(GOOD, PACKET) is None


@pytest.mark.parametrize(
    ("text", "stray"),
    [
        ("Florida wins by 17.", "17"),                       # a margin no one handed it
        ("Kentucky converts 35.1% on third down.", "35.1%"),  # a rate the data does not hold
        ("Florida is 48th on third down.", "48"),             # a rank off by one
        ("A 2027 commit was in the stands.", "2027"),         # a year from memory
        ("Tackles for loss: 6.95 a game.", "6.95"),           # more decimals than the data's 6.9
    ],
)
def test_a_figure_not_in_the_data_refuses_the_article(text, stray):
    refused = A.check({**GOOD, "paragraphs": [*GOOD["paragraphs"], text]}, PACKET)
    assert refused and refused.startswith("figures not in the app's numbers:") and stray in refused


def test_rates_ranks_and_small_counts_are_read_kindly():
    assert A.check({"headline": "Three keys and the 4th quarter", "paragraphs": ["35% on third down, the 113th takeaway rate."]}, PACKET) is None
    assert A.check({"headline": "x", "paragraphs": ["42 percent", "a 0.4 chance"]}, PACKET) is None, "42 from 0.418 as a percent; 0.4 rounded"
    assert A.check("an article", PACKET) == "the answer is not an article"
    many = A.check({"headline": "x", "paragraphs": [" ".join(str(n) for n in range(500, 512))]}, PACKET)
    assert many.endswith("and more")


# --- kept as a copied story ----------------------------------------------------------------------------------------------------


def test_a_kept_article_is_a_copied_story_with_its_kicker(tmp_path: Path):
    store = ArticleStore(tmp_path, 2026)
    assert A.keep(store, "numbers", "week-11", GOOD) is True
    assert A.keep(store, "numbers", "week-11", GOOD) is False, "the same article again changes nothing"
    sid = A.article_id("numbers", "week-11")
    assert len(sid) == 16 and sid == A.article_id("numbers", "week-11") != A.article_id("numbers", "week-12")
    article = store.get(sid)
    assert article.outcome == "copied" and article.title == GOOD["headline"] and article.paragraphs[0] == GOOD["dek"] and article.source == A.SOURCES["numbers"]
    row = A.row(store, "numbers", "week-11")
    assert row["id"] == sid and row["copied"] and row["app"] and row["kicker"] == "By the numbers" and row["opening"] == article.paragraphs[:3]
    assert A.row(store, "numbers", "week-12") is None and A.row(store, "nonsense", "week-11") is None and A.row(None, "numbers", "week-11") is None
    assert A.keep(store, "numbers", "week-12", {"headline": " ", "paragraphs": ["x"]}) is False and A.keep(store, "other", "k", GOOD) is False


def test_the_papers_own_article_leads_page_2_and_never_the_front():
    store_row = {"id": A.article_id("numbers", "week-11"), "title": GOOD["headline"], "source": A.SOURCES["numbers"], "publishedAt": "2026-10-27T12:00:00Z",
                 "topic": "game", "copied": True, "photo": None, "opening": ["a", "b"], "words": 300, "kicker": "By the numbers", "app": True}
    rows = [store_row, story(1, copied=True, hours=3), story(2, copied=True, hours=4), *[story(n, hours=n) for n in range(5, 20)]]
    built = layout(rows, page2_lead=store_row["id"])
    assert built["front"]["lead"]["id"] != store_row["id"]
    assert built["page2"]["lead"]["id"] == store_row["id"] and built["page2"]["lead"]["app"] is True and built["page2"]["lead"]["kicker"] == "By the numbers"
    assert {"page": 2, "id": store_row["id"], "words": GOOD["headline"]} in built["front"]["inside"]
    alone = layout([store_row], page2_lead=store_row["id"])
    assert alone["front"]["lead"] is None and alone["page2"]["lead"]["id"] == store_row["id"], "even alone it waits for page 2"


# --- the schedule ---------------------------------------------------------------------------------------------------------------


def test_by_the_numbers_runs_thursday_morning():
    kickoff = datetime(2026, 11, 14, 23, 15, tzinfo=timezone.utc)  # Sat 6:15 PM EST
    numbers = next(s for s in week_slots(401856884, kickoff, ET, week=11) if s.kind == "numbers")
    assert numbers.key == "numbers:week-11" and numbers.writing_key == "week-11"
    assert numbers.at == datetime(2026, 11, 12, 10, 0, tzinfo=ET).astimezone(timezone.utc), "Thursday 10 AM, before the paper's stories"
    paper = next(s for s in week_slots(401856884, kickoff, ET, week=11) if s.kind == "paper")
    assert numbers.at < paper.at
    assert not any(s.kind == "numbers" for s in week_slots(401856884, kickoff, ET, week=None))
    assert [s.kind for s in after_slots(401856884, kickoff)] == ["recap", "review"], "the morning after: What decided it and the review"


# --- the runner refuses a stray figure --------------------------------------------------------------------------------------------


def test_the_runner_refuses_an_article_with_a_figure_not_in_the_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    answers = [{**GOOD, "paragraphs": [*GOOD["paragraphs"], "Florida wins by 17."]}, GOOD]

    class FakeProcess:
        def __init__(self, handle) -> None:
            self.handle, self.returncode = handle, None

        async def communicate(self, input=None):
            self.handle.write("```json\n" + json.dumps(answers.pop(0)) + "\n```\n")
            self.handle.flush()
            self.returncode = 0
            return None, None

        async def wait(self) -> int:
            return 0

        def kill(self) -> None:
            pass

    async def spawn(*args, **kwargs):
        return FakeProcess(kwargs["stdout"])

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    tool = tmp_path / "claude.exe"
    tool.write_bytes(b"MZ")
    saved: list = []
    runner = W.WritingRunner(tmp_path / "data", tmp_path / "logs")
    job = W.Job("numbers", "week-11", "Florida", PACKET, lambda answer: saved.append(answer) or True, "By the numbers", check=lambda answer: A.check(answer, PACKET))

    def run() -> None:
        async def go() -> None:
            await runner.start(job, str(tool))
            await runner.task

        asyncio.run(go())

    run()
    assert runner.error and runner.error.startswith("the answer was refused, figures not in the app's numbers: 17") and saved == [] and not runner.saved
    run()
    assert runner.error is None and runner.saved and saved and saved[0]["headline"] == GOOD["headline"]


def test_the_kind_is_known_and_says_the_rule():
    spec = W.KINDS["numbers"]
    assert spec.search is False and "must appear in the data" in spec.task and "refused" in spec.task
    answer, _warnings, error = W.read("numbers", "```json\n" + json.dumps(GOOD) + "\n```")
    assert error is None and answer["headline"] == GOOD["headline"]
    assert W.read("numbers", '{"dek": "only a dek"}')[2] is not None, "no headline and no paragraphs: no article"


# --- in the paper ------------------------------------------------------------------------------------------------------------------


def test_the_week_papers_by_the_numbers_leads_page_2_and_takes_the_rails_box(lclient: TestClient, league_app):  # noqa: F811
    first = lclient.get("/api/newspaper?delay=0").json()["data"]
    key = first["edition"]["key"]
    assert key and not key.endswith("-sunday")
    A.keep(league_app.state.articles.store, "numbers", key, GOOD)
    data = lclient.get("/api/newspaper?delay=0").json()["data"]
    lead2 = data["edition"]["layout"]["page2"]["lead"]
    assert lead2["id"] == A.article_id("numbers", key) and lead2["app"] is True and lead2["kicker"] == "By the numbers"
    assert data["edition"]["layout"]["front"]["lead"]["id"] != lead2["id"]
    story_page = lclient.get(f"/api/paper/story/{lead2['id']}").json()["data"]
    assert story_page["title"] == GOOD["headline"] and story_page["paragraphs"][0] == GOOD["dek"], "the reader opens it like any story"


def test_the_sunday_paper_has_no_article_of_its_own(lclient: TestClient, league_app):  # noqa: F811
    league_app.state.test_clock["now"] = datetime(2026, 9, 27, 22, 0, tzinfo=timezone.utc)  # Sunday evening after our game
    league_app.state.cfbd.cache.clear()
    data = lclient.get("/api/newspaper?delay=0").json()["data"]
    assert data["edition"]["key"].endswith("-sunday")
    lead2 = (data["edition"]["layout"].get("page2") or {}).get("lead")
    assert not (isinstance(lead2, dict) and lead2.get("app") is True), "By the numbers leads a week's paper only"
