"""FEAT-14 wave 4 (owner 2026-10-27): Claude Code as the paper's editor and illustrator. Claude's layout is checked before
it is used (every id, the numbers, the quote word for word); its drawings are cleaned to plain shapes and served so that
nothing in them could load or run; the schedule runs the editor every two hours and the drawings twice a day, each only
when there is something new. No Claude and no network here: the answers are made up."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from app.services import writing
from app.services.articles import Article, story_id
from app.services.claude_schedule import ClaudeSchedule, Ledger, paper_slots
from app.services.paper_art import ArtStore, sanitize_svg
from app.services.paper_layout import editor_plan, layout, needs_drawing
from tests.conftest import FakeCfbd
from tests.test_program import pclient, program_app, route_program, set_clock, sites  # noqa: F401 - fixtures used below

ET = ZoneInfo("America/New_York")
GOOD_SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 400"><defs><linearGradient id="g"><stop offset="0" stop-color="#FA4616"/></linearGradient></defs><rect width="600" height="400" fill="url(#g)"/><circle cx="300" cy="200" r="80" fill="#0021A5"/></svg>'


def story(n: int, *, copied: bool = False, photo: bool = False, topic: str = "game", opening: list | None = None) -> dict:
    sid = f"{n:016x}"
    return {"id": sid, "title": f"Story {n} about the Gators", "url": f"https://site.example.invalid/{n}", "source": "On3", "publishedAt": f"2026-10-27T{10 + n % 10:02d}:00:00Z", "topic": topic,
            "players": [], "copied": copied, "photo": f"/media/paper/{sid}.jpg" if photo else None, "cutline": None, "credit": None, "opening": opening or (["First.", "Second."] if copied else []), "words": 400 if copied else 0}


# --- the drawings ----------------------------------------------------------------------------------------------------


def test_a_plain_drawing_is_kept_and_everything_that_could_run_or_load_is_taken_out():
    kept = sanitize_svg(GOOD_SVG)
    assert kept and "circle" in kept and "url(#g)" in kept
    nasty = ('<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)" viewBox="0 0 10 10"><script>alert(1)</script>'
             '<rect width="10" height="10" style="fill:url(http://evil)" onclick="x()"/><image href="http://evil/x.png"/>'
             '<foreignObject><div>hi</div></foreignObject><a href="http://evil"><circle r="3"/></a>'
             '<path d="M0 0L10 10" fill="url(http://evil/#x)"/></svg>')
    cleaned = sanitize_svg(nasty)
    assert cleaned and "rect" in cleaned and "path" in cleaned
    for bad in ("script", "onload", "onclick", "style", "image", "foreignObject", "href", "http://evil", "<a"):
        assert bad not in cleaned, bad


def test_entities_doctypes_huge_or_empty_drawings_are_refused():
    assert sanitize_svg('<!DOCTYPE svg [<!ENTITY a "aaaa">]><svg xmlns="http://www.w3.org/2000/svg"><rect width="&a;"/></svg>') is None
    assert sanitize_svg('<svg xmlns="http://www.w3.org/2000/svg">' + '<rect width="1" height="1"/>' * 3000 + "</svg>") is None
    assert sanitize_svg('<svg xmlns="http://www.w3.org/2000/svg"><script>x</script></svg>') is None  # nothing safe left
    assert sanitize_svg("not a drawing") is None and sanitize_svg(None) is None and sanitize_svg("<svg><rect></svg>") is None


def test_the_art_store_keeps_a_cleaned_drawing_with_its_caption(tmp_path: Path):
    art = ArtStore(tmp_path, 2026)
    sid = story(1)["id"]
    assert art.save(sid, GOOD_SVG, "A drawing of the stadium.")
    assert art.has(sid) == {"src": f"/media/paper-art/{sid}.svg", "caption": "A drawing of the stadium."}
    assert sid in ArtStore(tmp_path, 2026).drawn()  # read back by a fresh store
    assert not art.save("../evil", GOOD_SVG) and not art.save(story(2)["id"], "<svg><script/></svg>")
    assert art.path("../x") is None and art.has(story(3)["id"]) is None


# --- the editor's answer ---------------------------------------------------------------------------------------------


def test_the_editor_and_art_answers_read_leniently():
    value, warnings, error = writing.read("editor", '```json\n{"lead": "0000000000000001", "front": ["a", 2], "sections": [{"name": "X", "stories": ["b"]}], "numbers": [{"big": 17, "words": "x"}]}\n```')
    assert error is None and value["lead"] == "0000000000000001" and value["front"] == ["a"] and value["numbers"] == []
    assert writing.read("art", '{"drawings": [{"storyId": "x", "svg": "<svg/>"}]}')[0]["drawings"][0]["storyId"] == "x"
    assert writing.read("editor", "nothing useful")[0] is None


def test_claudes_plan_is_checked_before_it_is_used():
    rows = [story(1, copied=True, photo=True), story(2, copied=True, opening=['"We will be ready for them on Saturday night," Jon Sumrall said.']), story(3), story(4), story(5, copied=True)]
    by_id = {r["id"]: {**r, "kicker": "x"} for r in rows}
    plan = editor_plan({"lead": rows[1]["id"], "front": ["ffffffffffffffff", rows[2]["id"], rows[1]["id"]], "page2Lead": rows[4]["id"], "sections": [{"name": "Recruiting", "stories": [rows[3]["id"], "made-up"]}],
                        "kickers": {rows[1]["id"]: "The coach", "made-up": "x"}, "numbers": [{"big": "17", "words": "Florida's rank", "storyId": rows[0]["id"]}, {"big": "9", "words": "x", "storyId": "made-up"}],
                        "quote": {"text": "We will be ready for them on Saturday night", "storyId": rows[1]["id"]}}, by_id, "Jon Sumrall")
    assert plan["lead"] == rows[1]["id"] and plan["front"] == [rows[2]["id"]] and plan["page2"] == rows[4]["id"]  # the made-up id and the lead's repeat are out
    assert plan["named"] == {rows[3]["id"]: "Recruiting"} and plan["kickers"] == {rows[1]["id"]: "The coach"}
    assert plan["numbers"] == [{"big": "17", "words": "Florida's rank", "storyId": rows[0]["id"]}]
    assert plan["quote"]["text"] == "We will be ready for them on Saturday night." and plan["quote"]["who"] == "Jon Sumrall"
    invented = editor_plan({"lead": rows[1]["id"], "quote": {"text": "We are going to win by forty points this week", "storyId": rows[1]["id"]}}, by_id, "Jon Sumrall")
    assert invented["quote"] is None  # not in the story's text: never printed
    assert editor_plan({"lead": "nope", "front": ["nope"]}, by_id, None) is None and editor_plan("junk", by_id, None) is None


def test_the_paper_follows_claudes_plan_and_places_new_stories_by_the_rule():
    rows = [story(n, copied=n < 5, photo=n < 3, topic="recruiting" if n > 8 else "game") for n in range(1, 41)]
    answer = {"lead": rows[3]["id"], "front": [rows[0]["id"], rows[8]["id"], rows[1]["id"]], "page2Lead": rows[2]["id"], "sections": [{"name": "The Georgia game", "stories": [r["id"] for r in rows[5:8]]}],
              "kickers": {rows[3]["id"]: "Big news"}, "numbers": [{"big": "5", "words": "straight wins", "storyId": rows[0]["id"]}]}
    built = layout(rows, editor=answer)
    assert built["by"] == "Claude Code" and built["front"]["lead"]["id"] == rows[3]["id"] and built["front"]["lead"]["kicker"] == "Big news"
    assert [c["story"]["id"] for c in built["front"]["row"]] == [rows[0]["id"], rows[8]["id"], rows[1]["id"]]  # the headline-only one in the middle
    assert built["page2"]["lead"]["id"] == rows[2]["id"] and built["front"]["numbers"][0]["big"] == "5"
    assert len(built["order"]) == len(set(built["order"])) == 40  # every story once, the ones Claude never saw too
    names = [item["section"] for page in built["more"] for col in page["columns"] for item in col if "section" in item]
    assert names[0] == "The Georgia game"
    assert layout(rows)["by"] == "the app"


def test_drawings_fill_the_placed_stories_that_have_no_picture():
    rows = [story(1, copied=True, photo=True), story(2, copied=True), story(3), story(4, copied=True), story(5), story(6, copied=True)]
    built = layout(rows, editor={"lead": rows[0]["id"], "front": [rows[1]["id"], rows[2]["id"], rows[3]["id"]], "drawings": [rows[3]["id"]]})
    wanted = [s["id"] for s in needs_drawing(built)]
    assert len(wanted) == 2 and wanted[0] == rows[3]["id"]  # Claude's own pick first, two a run
    drawn = layout(rows, editor={"lead": rows[0]["id"], "front": [rows[1]["id"], rows[2]["id"], rows[3]["id"]]}, art={rows[1]["id"]: {"src": f"/media/paper-art/{rows[1]['id']}.svg", "caption": "A drawing."}})
    picture = next(c["picture"] for c in drawn["front"]["row"] if c["story"]["id"] == rows[1]["id"])
    assert picture == {"kind": "drawn", "src": f"/media/paper-art/{rows[1]['id']}.svg", "cutline": "A drawing.", "credit": "Illustration: Claude Code"}
    assert needs_drawing(None) == [] and needs_drawing({"front": {}}) == []


# --- the schedule ----------------------------------------------------------------------------------------------------


def test_the_editor_runs_every_two_hours_and_the_drawings_twice_a_day():
    now = datetime(2026, 10, 27, 15, 0, tzinfo=timezone.utc)
    slots = paper_slots(now, ET)
    editors = [s for s in slots if s.kind == "editor"]
    assert [s.at.astimezone(ET).hour for s in editors] == [7, 9, 11, 13, 15, 17, 19, 21]
    assert [s.at.astimezone(ET).hour for s in slots if s.kind == "art"] == [10, 16]
    assert editors[0].key == "editor:2026-10-27-07" and editors[0].writing_key == "2026-10-27-07"


def test_the_schedule_offers_the_paper_runs_with_the_other_writing(tmp_path: Path):
    async def none() -> None:
        return None

    async def current(_slot) -> bool:
        return False

    async def start(_slot, _game) -> dict:
        return {"running": True}

    schedule = ClaudeSchedule(ledger=Ledger(tmp_path / "ledger.json"), enabled=lambda: True, command_found=lambda: True, current_game=none, season=lambda: 2026, tz=ET,
                              data_is_current=current, start=start, poll=lambda _s: {"running": False, "ok": True}, writing=True)
    now = datetime(2026, 10, 27, 15, 30, tzinfo=timezone.utc)  # 11:30 AM Eastern
    due = schedule.due(None, now)
    assert due is not None and due.kind in ("editor", "art", "datacheck")
    kinds = {s.kind for s in schedule.upcoming(None, now)}
    assert {"editor", "art"} <= kinds


# --- the whole way, through the real paper ---------------------------------------------------------------------------


def test_an_editor_run_lays_out_the_real_paper_and_a_drawing_is_served(pclient: TestClient, fake_cfbd: FakeCfbd, program_app):  # noqa: F811
    from app.writing_setup import build_job

    route_program(fake_cfbd)
    set_clock(program_app, datetime(2026, 9, 23, 16, 0, tzinfo=timezone.utc))
    store = program_app.state.articles.store
    url = "https://www.cbssports.example.invalid/college-football/news/florida-comeback/"
    sid = story_id(url)
    store.put(Article(id=sid, url=url, title="Florida's comeback puts the Gators back in the SEC race", source="CBS Sports", outcome="copied", paragraphs=["One.", "Two."], words=300, copiedAt="2026-09-23T15:00:00Z"))
    job = pclient.portal.call(build_job, program_app, "editor", "2026-09-23-11")
    assert job is not None and any(s["id"] == sid and s["copied"] for s in job.packet["stories"])
    other = next(s["id"] for s in job.packet["stories"] if s["id"] != sid)
    assert job.save({"lead": other, "front": [sid], "kickers": {other: "Picked by Claude"}}) is True
    edition = pclient.get("/api/newspaper").json()["data"]["edition"]
    assert edition["layout"]["by"] == "Claude Code" and edition["layout"]["front"]["lead"]["id"] == other
    assert edition["layout"]["front"]["lead"]["kicker"] == "Picked by Claude"
    art = program_app.state.rankedweek.art
    assert art.save(other, GOOD_SVG, "A drawing.")
    served = pclient.get(f"/media/paper-art/{other}.svg")
    assert served.status_code == 200 and served.headers["content-type"].startswith("image/svg+xml") and "default-src 'none'" in served.headers["content-security-policy"]
    assert pclient.get("/media/paper-art/../../x.svg").status_code == 404 and pclient.get("/media/paper-art/0123456789abcdef.png").status_code == 404
    status = pclient.get("/api/datastatus?view=newspaper").json()["data"]
    assert any(b["band"] == "The paper laid out by Claude" for b in status["bands"])
    asyncio.run(asyncio.sleep(0))
