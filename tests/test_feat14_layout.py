"""FEAT-14 wave 3 (the owner's boards of 2026-10-27): the paper's pages from the week's stories by the app's own rule,
the earlier weeks folded, and where a story sits for the reader. No network: stories are made up here."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from app.services.articles import Article, story_id
from app.services.paper_layout import LayoutStore, find_quote, folded_weeks, layout, lead_title
from tests.conftest import FakeCfbd
from tests.test_program import pclient, program_app, route_program, set_clock, sites  # noqa: F401 - fixtures used below

ET = ZoneInfo("America/New_York")


def story(n: int, *, copied: bool = False, photo: bool = False, topic: str = "game", hours: int | None = None, players: list | None = None, source: str = "On3", opening: list | None = None) -> dict:
    sid = f"{n:016x}"
    return {
        "id": sid, "title": f"Story number {n} about the Gators and their week", "url": f"https://site.example.invalid/{n}", "source": source,
        "publishedAt": f"2026-10-{27 - (hours or n) // 24:02d}T{23 - (hours or n) % 24:02d}:00:00Z", "topic": topic, "players": players or [],
        "copied": copied, "photo": f"/media/paper/{sid}.jpg" if photo else None, "cutline": "A caption." if photo else None, "credit": "A Photographer" if photo else None,
        "opening": opening or (["A first paragraph of the story.", "A second paragraph."] if copied else []), "words": 600 if copied else 0, "author": None,
    }


def week() -> list[dict]:
    return [
        story(1, copied=True, photo=True, source="Florida Athletics", opening=['"Florida-Georgia is different, and anybody that says otherwise is not being real," Jon Sumrall said Monday.', "More."]),
        story(2, copied=True, photo=True, topic="coach"),
        story(3, topic="coach"),
        story(4, copied=True, players=[{"playerId": "4433", "name": "Tramell Jones Jr.", "team": "Florida"}]),
        story(5, copied=True, topic="rankings"),
        *[story(n, topic=("recruiting" if n % 3 else "rankings")) for n in range(6, 40)],
        story(40, topic="other-sport"),
        {"title": None}, "junk", story(1, copied=True),
    ]


def test_every_story_lands_once_and_the_front_page_is_laid_out_as_drawn():
    built = layout(week(), coach="Jon Sumrall")
    ids = [s for s in built["order"]]
    assert len(ids) == len(set(ids)) == built["count"] == 39  # the soccer story and the junk are out, the repeat once
    front = built["front"]
    assert front["lead"]["id"] == story(1)["id"] and front["picture"]["kind"] == "photo"  # a copied story with its photo leads
    assert front["leadBriefs"] == []  # a lead with text needs no briefs in its columns
    row = front["row"]
    assert len(row) == 3 and row[1]["first"] == "head"  # the middle story leads with its head: no two heads side by side
    assert all(c["also"] for c in row if not c["story"]["copied"])  # a headline-only story takes an Also brief
    assert front["quote"]["who"] == "Jon Sumrall" and "Florida-Georgia is different" in front["quote"]["text"]


def test_page_two_and_the_rest_fill_three_even_columns_with_section_heads():
    built = layout(week(), coach=None)
    p2 = built["page2"]
    assert p2["lead"]["copied"] and len(p2["briefs"]) == 8 and all(not b["copied"] for b in p2["briefs"])
    assert built["front"]["quote"] is None
    more = built["more"]
    assert more and more[0]["page"] == 3 and sum(p["count"] for p in more) == built["count"] - 1 - 3 - sum(1 for c in built["front"]["row"] if c["also"]) - 1 - len(p2["row"]) - sum(1 for c in p2["row"] if c["also"]) - 8
    columns = more[0]["columns"]
    assert len(columns) == 3 and all(col and "section" in col[0] for col in columns if col)  # each column opens with its section's name
    heights = [sum(19 * max(1, -(-len(i.get("title", "")) // 30)) + 42 if "id" in i else 30 for i in col) for col in columns]
    assert max(heights) - min(heights) <= 200, heights  # even columns: no hole at the foot of one


def test_a_related_photo_or_a_headshot_when_a_story_has_none():
    rows = [
        story(1, copied=True, photo=True, players=[{"playerId": "4433", "name": "Tramell Jones Jr."}]),
        story(2, copied=True, photo=True, topic="coach"),
        story(3, players=[{"playerId": "4433", "name": "Tramell Jones Jr."}]),
        story(4, players=[{"playerId": 5150, "name": "Jadan Baugh"}]),
        story(5),
    ]
    built = layout(rows)
    pictures = {c["story"]["id"]: c["picture"] for c in built["front"]["row"]}
    assert pictures[story(3)["id"]] is None or pictures[story(3)["id"]]["kind"] in ("related", "headshot")
    assert pictures[story(4)["id"]]["kind"] == "headshot" and pictures[story(4)["id"]]["src"] == "/media/headshot/5150"


def test_a_week_with_nothing_copied_still_fills_the_leads_columns():
    built = layout([story(n) for n in range(1, 20)])
    assert built["front"]["lead"]["copied"] is False and len(built["front"]["leadBriefs"]) == 6


def test_an_empty_or_broken_week_is_an_empty_paper():
    for rows in (None, [], ["x", {"id": 3}], [{"id": "a", "title": "  "}]):
        built = layout(rows)
        assert built["front"]["lead"] is None and built["count"] == 0 and built["more"] == [] and built["page2"] is None


def test_the_quote_is_short_and_by_our_coach():
    long = story(1, copied=True, opening=['"' + "word " * 40 + '" Sumrall said.'])
    other = story(2, copied=True, opening=['"We will be ready for them on Saturday," Kirby Smart said.'])
    good = story(3, copied=True, opening=['"We will be ready for them on Saturday," Jon Sumrall said Tuesday.'])
    assert find_quote([long, other], "Jon Sumrall") is None
    assert find_quote([long, other, good], "Jon Sumrall")["storyId"] == good["id"]
    assert find_quote([good], None) is None


def game(week_no: int, start: str, opponent: str, us: int | None, them: int | None, home: bool = True):
    return SimpleNamespace(week=week_no, season_type="regular", start_date=start, home_team="Florida" if home else opponent, away_team=opponent if home else "Florida",
                           home_points=us if home else them, away_points=them if home else us, completed=us is not None)


def test_the_earlier_weeks_fold_with_their_final_and_the_record_after():
    games = [game(6, "2026-10-10T19:00:00Z", "South Carolina", 19, 38), game(7, "2026-10-17T20:00:00Z", "Texas", 27, 24, home=False), game(9, "2026-10-31T19:30:00Z", "Georgia", None, None)]
    editions = [
        {"key": "week-6", "label": "Week 6", "opponent": "South Carolina", "homeAway": "home", "saved": False, "current": False},
        {"key": "week-7", "label": "Week 7", "opponent": "Texas", "homeAway": "away", "saved": True, "current": False, "weekEnd": "2026-10-19T06:59:00Z"},
        {"key": "week-8", "label": "Week 8", "opponent": None, "homeAway": None, "saved": True, "current": False, "weekEnd": "2026-10-26T06:59:00Z"},
        {"key": "week-9", "label": "Week 9", "current": True},
        "junk", {"key": None},
    ]
    rows = folded_weeks(editions, games, "Florida", "week-9", tz=ET, leads={"week-8": "A Long Wait, A Big Moment For Jones"})
    assert [r["key"] for r in rows] == ["week-8", "week-7", "week-6"]
    bye, texas, carolina = rows
    assert bye["bye"] and bye["lead"] == "A Long Wait, A Big Moment For Jones" and bye["record"] == "1-1" and bye["weekOf"] == "2026-10-19"
    assert texas["final"] == "Florida 27, Texas 24" and texas["won"] and texas["record"] == "1-1" and texas["weekOf"] == "2026-10-12"
    assert carolina["final"] == "South Carolina 38, Florida 19" and carolina["won"] is False and carolina["record"] == "0-1"
    assert folded_weeks(None, None, "Florida", None, tz=ET) == []


def test_lead_title_and_the_readers_place_in_its_week(tmp_path: Path):
    rows = week()
    assert lead_title(rows) == story(1)["title"] and lead_title([]) is None
    store = LayoutStore(tmp_path, 2026)
    built = layout(rows)
    store.save("week-9", built)
    store.save("week-9", built)  # unchanged: not written again
    store.save("../evil", built)
    second = built["order"][1]
    place = store.place(second)
    assert place["key"] == "week-9" and place["position"] == 2 and place["count"] == built["count"]
    assert place["prev"]["id"] == built["order"][0] and place["next"]["id"] == built["order"][2]
    assert all(r["id"] != second for r in place["related"]) and len(place["related"]) <= 6
    assert store.place("ffffffffffffffff") is None
    assert not (tmp_path / "season" / "2026" / "paper" / "layout-../evil.json").exists()


def test_the_paper_and_the_reader_carry_the_layout(pclient: TestClient, fake_cfbd: FakeCfbd, program_app):  # noqa: F811
    route_program(fake_cfbd)
    set_clock(program_app, datetime(2026, 9, 23, 16, 0, tzinfo=timezone.utc))
    store = program_app.state.articles.store
    url = "https://www.cbssports.example.invalid/college-football/news/florida-comeback/"
    sid = story_id(url)
    store.put(Article(id=sid, url=url, title="Florida's comeback puts the Gators back in the SEC race", source="CBS Sports", outcome="copied", paragraphs=["One.", "Two."], words=300, copiedAt="2026-09-23T15:00:00Z"))
    data = pclient.get("/api/newspaper").json()["data"]
    edition = data["edition"]
    assert edition["layout"]["count"] >= 1 and isinstance(data.get("folded"), list)
    shown = next(h for h in edition["headlines"] if h["id"] == sid)
    assert shown["copied"] is True and shown["opening"] == ["One.", "Two."]
    assert edition["layout"]["front"]["lead"]["id"] == sid  # the one copied story leads
    reader = pclient.get(f"/api/paper/story/{sid}").json()["data"]
    assert reader["paper"]["position"] == 1 and reader["paper"]["count"] == edition["layout"]["count"]
