"""The final-pass fixes (2026-10-09), each with the defect it closes: the ticker and the LIVE marker hold at the
final until the delayed sheet has shown it (live-1, live-2), penalties go to the flagged team (sides-1), an injury
run never replaces a notes file it cannot read (backend-new-1), the wide-search rule counts every wide value
(security-1), every answer refuses framing (security-4), a CFBD outage is a 503 and never "not on our schedule"
(backend-pages-1), and spoiler mode lists the panels it missed (views-5, asks-12)."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.limits import wide_search
from app.live.events import LiveEvent
from app.live.state import derive_state
from app.services import notes_paste
from app.services.notes import NotesFile
from app.services.ticker import TickerService
from tests.conftest import FakeCfbd

NOW = datetime(2026, 10, 10, 23, 30, tzinfo=timezone.utc)


# --- the final and the delay -----------------------------------------------------------------------------------


def _fake_engine(**over: Any) -> Any:
    base = {"current_game_id": 7, "mode": "idle", "has_events": lambda gid: True, "state": lambda delay, gid: None, "final_released": lambda now, delay: True}
    base.update(over)
    return SimpleNamespace(**base)


def _ours(engine: Any, status: str = "final", home: Any = 31, away: Any = 24, delay: float = 45.0, detail: str | None = "Final") -> tuple:
    return asyncio.run(TickerService._ours(SimpleNamespace(engine=engine), 7, status, detail, home, away, delay, NOW))  # type: ignore[arg-type]


def test_ticker_holds_the_final_until_the_delayed_sheet_has_it():
    # The feed (and CFBD's /games) say final, the engine has gone idle, but at this device's delay the released
    # state is still in the fourth quarter: the entry stays live with the delayed score, never the final one.
    delayed = {"status": "in_progress", "period": 4, "clock": {"minutes": 0, "seconds": 41}, "homeScore": 24, "awayScore": 24}
    engine = _fake_engine(state=lambda delay, gid: delayed, final_released=lambda now, delay: False)
    kind, text, home, away = _ours(engine)
    assert kind == "live" and (home, away) == (24, 24) and "Final" not in str(text)
    # once the delayed state is final, the final score shows
    engine = _fake_engine(state=lambda delay, gid: {"status": "final", "homeScore": 31, "awayScore": 24})
    assert _ours(engine)[0] == "final" and _ours(engine)[2:] == (31, 24)


def test_ticker_shows_no_score_before_a_play_is_released():
    # Decision 15: nothing released yet (a pregame state at this delay) means no score at all, not 0-0
    engine = _fake_engine(mode="live", state=lambda delay, gid: {"status": "pre", "homeScore": 0, "awayScore": 0})
    assert _ours(engine, status="pre", home=0, away=0, detail="7:00 PM") == ("pre", "7:00 PM", None, None)
    assert _ours(engine, status="live", home=7, away=0) == ("live", "In progress", None, None)
    # the engine holds nothing for the game (nobody watched): CFBD's live line shows no score either
    assert _ours(_fake_engine(has_events=lambda gid: False), status="live", home=14, away=3) == ("live", "In progress", None, None)
    # a final the feed saw but this device's delay has not reached is still "in progress" with no score
    assert _ours(_fake_engine(has_events=lambda gid: False, final_released=lambda now, delay: False))[0:2] == ("live", "In progress")


def test_live_marker_holds_through_the_delay(app):
    engine = app.state.live
    window = SimpleNamespace(game_id=7, kickoff=NOW - timedelta(hours=3), opens_at=NOW - timedelta(hours=3, minutes=30), closes_at=NOW + timedelta(hours=2), cap=NOW + timedelta(hours=7), contains=lambda now: True)
    engine.window = window
    engine._clock = lambda: NOW
    assert engine.status(0)["window"]["inProgress"] is True
    engine._final_seen = True
    engine._final_seen_at = NOW - timedelta(seconds=20)
    assert engine.status(0)["window"]["inProgress"] is False  # a device with no delay has seen the final
    assert engine.status(45)["window"]["inProgress"] is True  # one 45 s behind has not
    assert engine.status(20)["window"]["inProgress"] is False
    # the window closes on the final; the marker still holds for the delayed device, and only for it
    engine._last_closed = window
    engine.window = None
    assert engine.status(0)["window"] is None
    held = engine.status(45)["window"]
    assert held is not None and held["inProgress"] is True and held["gameId"] == 7
    engine._final_seen_at = NOW - timedelta(seconds=60)
    assert engine.status(45)["window"] is None


def test_status_route_takes_the_delay(client: TestClient):
    assert client.get("/api/live/status?delay=45").status_code == 200
    assert client.get("/api/live/status?delay=999").status_code == 422


# --- penalties go to the flagged team ------------------------------------------------------------------------


def _play(eid: str, **data: Any) -> LiveEvent:
    base = {"driveId": "d1", "offense": "Swamp", "defense": "Bayou", "playType": "Rush", "text": "run for 3 yards", "yardsGained": 3, "down": 1, "distance": 10, "flags": []}
    base.update(data)
    return LiveEvent(eid, "play", 1, NOW, base, seq=int(eid[1:]))


def test_penalties_are_counted_against_the_flagged_team():
    events = [
        _play("p1"),
        _play("p2", playType="Penalty", text="PENALTY BAYOU Pass Interference (#22 A.Jordan) 11 yards from SWAMP35 to SWAMP46. NO PLAY", yardsGained=0),
        _play("p3", playType="Penalty", text="PENALTY SWAMP False Start (#52 H.Moore) 5 yards. NO PLAY", yardsGained=0),
        _play("p4", playType="Penalty", text="A flag with no team named. NO PLAY", yardsGained=0),
    ]
    state = derive_state(events, game_id=1, home="Swamp", away="Bayou")
    counts = {name: box["penalties"]["count"] for name, box in _boxes(state).items()}
    assert counts == {"Swamp": 1, "Bayou": 1}, counts  # the offense's flag and the defense's each on their own side; the unreadable one uncounted


def _boxes(state: dict[str, Any]) -> dict[str, Any]:
    for key in ("box", "boxes", "teamStats", "situational"):
        value = state.get(key)
        if isinstance(value, dict) and all(isinstance(v, dict) and "penalties" in v for v in value.values()) and value:
            return value
    raise AssertionError(f"no team boxes in the state: {sorted(state)}")


# --- an injury run never replaces a notes file it cannot read ------------------------------------------------


def test_injury_merge_refuses_an_unreadable_notes_file(tmp_path):
    path = notes_paste.notes_path(tmp_path, 55)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"gameId": 55, "author": "me", "writtenAt": "2026-10-05T12:00:00Z", "notes": [{"title": "Scheme"}],  oops', encoding="utf-8")
    before = path.read_text(encoding="utf-8")
    update = NotesFile(gameId=55, author="bot", writtenAt="2026-10-09T12:00:00Z", availability=[{"name": "A. Back", "position": "RB", "status": "Out"}])
    with pytest.raises(notes_paste.NotesUnreadable):
        notes_paste.merge_availability(tmp_path, 55, update)
    assert path.read_text(encoding="utf-8") == before  # untouched
    # with no file at all a small one is still created
    assert notes_paste.merge_availability(tmp_path, 56, update) is True
    saved = json.loads(notes_paste.notes_path(tmp_path, 56).read_text(encoding="utf-8"))
    assert saved["availability"][0]["name"] == "A. Back"


# --- security ------------------------------------------------------------------------------------------------


def test_wide_search_counts_every_wide_value():
    assert wide_search("q=a&wide=1") and wide_search("wide=2&q=a") and wide_search("q=a&wide=true") and wide_search("q=a&wide=on")
    assert not wide_search("q=a") and not wide_search("q=a&wide=0") and not wide_search("q=a&wide=false") and not wide_search("q=a&wide=")


def test_every_answer_refuses_framing(client: TestClient):
    for url in ("/", "/api/health", "/static/index.html", "/portal", "/nope"):
        response = client.get(url)
        assert response.headers.get("x-frame-options") == "DENY", url
        assert response.headers.get("content-security-policy") == "frame-ancestors 'none'", url
        assert response.headers.get("x-content-type-options") == "nosniff", url


# --- a CFBD outage is never "not on our schedule" ---------------------------------------------------------------


def test_program_and_notes_say_cfbd_is_down_not_404(client: TestClient, fake_cfbd: FakeCfbd):
    for path in ("/games", "/teams/fbs", "/records", "/rankings", "/stats/season"):
        fake_cfbd.route(path, status=500, text="boom")
    for url in ("/api/program/next", "/api/program/526002342", "/api/program/526002342/leaders", "/api/notes/prompt?gameId=526002342"):
        response = client.get(url)
        assert response.status_code == 503, (url, response.status_code, response.text[:200])
        assert "not on our schedule" not in response.text
    preview = client.post("/api/notes/preview", json={"gameId": 526002342, "text": "{}"})
    assert preview.status_code == 503 and "not on our schedule" not in preview.text


# --- spoiler mode lists the panels it missed -------------------------------------------------------------------


def test_spoiler_lists_the_quarter_line_live_points_and_squares():
    js = (__import__("pathlib").Path(__file__).resolve().parents[1] / "static" / "js" / "ui" / "spoiler.js").read_text(encoding="utf-8")
    css = (__import__("pathlib").Path(__file__).resolve().parents[1] / "static" / "css" / "components.css").read_text(encoding="utf-8")
    for selector in (".qline", ".scores__pts", ".form__sq", ".score-words"):
        assert selector in js, selector
        assert f"{selector}," in css or f"{selector})" in css, selector
