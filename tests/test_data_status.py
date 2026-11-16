"""ENH-4 (the owner's board of 2026-10-27): the status pill's "how often"
and the Data status card's rows: when each band's source changes, when the app looks and how old its copy is, from the
server's own records (no CFBD call), with Claude's parts marked Due or Not written."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from app.cache import Cache, cache_key
from app.db import Database
from app.services import data_status as D
from app.services.notes import NotesFile

EASTERN = ZoneInfo("America/New_York")
TUESDAY = datetime(2026, 10, 27, 15, 0, tzinfo=timezone.utc)  # 11 AM Eastern, a quiet weekday
SATURDAY = datetime(2026, 10, 31, 15, 0, tzinfo=timezone.utc)
KICKOFF = "2026-10-31T19:30:00Z"


def test_how_often_in_words() -> None:
    assert [D.cadence_words(s) for s in (12, 900, 1800, 3600, 3 * 3600, 86400, 7 * 86400)] == ["every 12 s", "every 15 min", "every 30 min", "hourly", "every 3 h", "daily", "weekly"]
    for junk in (None, 0, -5, "x", 1.5):
        assert D.cadence_words(junk) is None


def test_the_scores_are_checked_every_15_minutes_thursday_to_saturday() -> None:
    assert D.checks("scores", TUESDAY.astimezone(EASTERN)) == ("hourly; every 15 min Thu to Sat", 3600)
    assert D.checks("scores", SATURDAY.astimezone(EASTERN))[1] == 900
    assert D.checks("scores", TUESDAY.astimezone(EASTERN), game_day=True)[1] == 900, "our Friday or bowl game is game day too"
    assert D.checks("lines", TUESDAY.astimezone(EASTERN))[1] == 3600 and D.checks("lines", TUESDAY.astimezone(EASTERN), game_day=True)[1] == 900
    assert D.checks("polls", TUESDAY.astimezone(EASTERN)) == ("Sun, every 20 min until it is out", 7 * 86400), "the owner's example: the AP poll, weekly"
    assert D.checks("live", TUESDAY, live_seconds=12) == ("every 12 s while the game is on", 12)
    assert D.checks("ticker", TUESDAY, ticker_seconds=20)[1] == 20 and D.checks("ticker", TUESDAY)[1] == 300
    assert D.checks("notes", TUESDAY)[1] is None, "Claude's parts are not polled"
    assert D.checks("no such source", TUESDAY) == ("when the page opens", None)


def test_every_band_names_a_known_source() -> None:
    for view, bands in D.PAGE_BANDS.items():
        assert bands, view
        for label, sources in bands:
            assert isinstance(label, str) and label and sources, view
            for source in sources:
                assert source == "ticker" or source in D.SOURCES, f"{view}: {label} names {source}"
    assert [b for b, _s in D.PAGE_BANDS["program"]][:2] == ["Cover: records, scores", "Cover: AP rank"], "the board's order"
    assert D.PAGE_BANDS["myteams"] is D.PAGE_BANDS["season"]


def _ctx(**changes) -> D.Context:
    fetched = {"/games": TUESDAY - timedelta(minutes=32), "/lines": TUESDAY - timedelta(minutes=40), "/rankings": TUESDAY - timedelta(hours=1), "/stats/season": TUESDAY - timedelta(hours=2)}
    changed = {"/rankings": datetime(2026, 10, 25, 18, 14, tzinfo=timezone.utc), "/stats/season": datetime(2026, 10, 26, 8, 0, tzinfo=timezone.utc)}
    base = {
        "now": TUESDAY,
        "tz": EASTERN,
        "fetched": lambda eps: max((fetched[e] for e in eps if e in fetched), default=None),
        "changed": lambda eps: max((changed[e] for e in eps if e in changed), default=None),
        "files": {"headlines": TUESDAY - timedelta(minutes=12)},
        "kickoff": KICKOFF,
    }
    return D.Context(**{**base, **changes})


def _row(answer: dict, band: str) -> dict:
    return next(b for b in answer["bands"] if b["band"] == band)


def test_the_program_card_from_the_servers_records() -> None:
    notes = NotesFile(gameId=401, sections=[{"title": "Keys", "items": ["Run the ball"]}], lineups={"us": {"team": "Florida", "scheme": "11 personnel"}})
    saved = TUESDAY - timedelta(hours=5)
    answer = D.page_status("program", _ctx(notes=notes, notes_saved=saved, writing={"scout": None}))
    assert answer["cadence"] == "hourly" and answer["cadenceSeconds"] == 3600, "the page's quickest look on a Tuesday"
    scores = _row(answer, "Cover: records, scores")
    assert scores == {"band": "Cover: records, scores", "changes": "as games end", "checks": "hourly; every 15 min Thu to Sat", "dataFrom": "2026-10-27T14:28:00Z", "due": None}
    assert _row(answer, "Cover: AP rank")["dataFrom"] == "2026-10-25T18:14:00Z", "a published source is dated by when it came out, not when it was fetched"
    assert _row(answer, "Headlines")["dataFrom"] == "2026-10-27T14:48:00Z"
    assert _row(answer, "Program notes")["dataFrom"] == "2026-10-27T10:00:00Z"
    assert _row(answer, "Lineups")["due"] is None and _row(answer, "Lineups")["dataFrom"], "the depth charts are in the notes"
    availability = _row(answer, "Availability report")
    assert availability["due"] == "Due Thu" and availability["dataFrom"] is None, "two days before a Saturday kickoff (readiness DUE_DAYS)"
    assert _row(answer, "Recruits on hand")["due"] == "Not loaded", "the visitor lists can be had from the Monday: missing, not due"
    assert _row(answer, "Scouting report")["due"] == "Not written"
    schools = _row(answer, "The two schools and the series, the common opponents")
    assert schools["due"] is None, "no copy of the series yet: the card draws a dash for that part"


def test_saturday_the_pill_says_every_15_minutes_and_in_game_every_12_seconds() -> None:
    assert D.page_status("program", _ctx(now=SATURDAY))["cadence"] == "every 15 min"
    live = D.page_status("live", _ctx(now=SATURDAY, live_seconds=12, live_at=SATURDAY - timedelta(seconds=8)))
    assert live["cadence"] == "every 12 s"
    assert _row(live, "Score, plays and win probability")["dataFrom"] == "2026-10-31T14:59:52Z"
    assert D.page_status("unknown page", _ctx()) == {"view": "unknown page", "bands": [], "cadenceSeconds": None, "cadence": None}


def test_a_written_scouting_report_and_a_loaded_availability_report() -> None:
    notes = NotesFile(gameId=401, availability=[{"team": "Georgia", "name": "A Player", "position": "WR", "status": "Out"}], availabilityUpdatedAt="2026-10-29T20:00:00Z")
    answer = D.page_status("program", _ctx(now=datetime(2026, 10, 30, 12, tzinfo=timezone.utc), notes=notes, notes_saved=TUESDAY, writing={"scout": TUESDAY - timedelta(days=1)}))
    assert _row(answer, "Availability report")["dataFrom"] == "2026-10-29T20:00:00Z", "the report's own time"
    assert _row(answer, "Scouting report")["dataFrom"] == "2026-10-26T15:00:00Z"


def test_the_newest_record_in_the_cache_and_the_publication_log(tmp_path: Path) -> None:
    db = Database(tmp_path / "cache.db")
    cache = Cache(db)
    for endpoint, params, minutes in (("/games", {"year": 2026, "team": "Florida"}, 50), ("/games", {"year": 2026, "team": "Georgia"}, 10), ("/lines", {"year": 2026}, 5)):
        cache.put(cache_key(endpoint, params), endpoint, params, [], fetched_at=TUESDAY - timedelta(minutes=minutes), ttl=timedelta(hours=1))
    assert D.newest(db, "cache", "fetched_at", ["/games"]) == TUESDAY - timedelta(minutes=10)
    assert D.newest(db, "cache", "fetched_at", ["/games", "/lines"]) == TUESDAY - timedelta(minutes=5)
    assert D.newest(db, "cache", "fetched_at", ["/never"]) is None
    assert D.newest(db, "cache", "fetched_at", []) is None and D.newest(None, "cache", "fetched_at", ["/games"]) is None
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO publications (key, endpoint, params, schedule, hash, changed_at, checked_at, asked_at, checks) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("/rankings?year=2026", "/rankings", "{}", "polls", "h", "2026-10-25T18:14:00Z", "2026-10-27T14:00:00Z", "2026-10-27T14:00:00Z", 3),
        )
    assert D.newest(db, "publications", "changed_at", ["/rankings"]) == datetime(2026, 10, 25, 18, 14, tzinfo=timezone.utc)
    assert D.newest(db, "no_such_table", "changed_at", ["/rankings"]) is None, "a missing helper table never breaks the card"


def test_the_feeds_time_skips_the_seasons_headline_file_and_damaged_copies(tmp_path: Path) -> None:
    feeds = tmp_path / "feeds"
    feeds.mkdir()
    (feeds / "team.json").write_text(json.dumps({"fetchedAt": "2026-10-27T14:00:00+00:00", "headlines": []}), encoding="utf-8")
    (feeds / "google.json").write_text(json.dumps({"fetchedAt": "2026-10-27T14:30:00+00:00"}), encoding="utf-8")
    (feeds / "season-2026.json").write_text(json.dumps({"fetchedAt": "2026-10-27T15:59:00+00:00"}), encoding="utf-8")
    (feeds / "espn.json").write_text("{not json", encoding="utf-8")
    (feeds / "athletic.json").write_text(json.dumps(["a list"]), encoding="utf-8")
    assert D.feeds_time(feeds) == datetime(2026, 10, 27, 14, 30, tzinfo=timezone.utc)
    assert D.feeds_time(tmp_path / "none") is None
    assert D.newest_file(tmp_path / "none") is None
    assert D.file_time(tmp_path / "none.json") is None


def test_the_endpoint_answers_without_calling_cfbd(client, fake_cfbd) -> None:
    before = len(fake_cfbd.requests)
    data = client.get("/api/datastatus", params={"view": "program", "gameId": "401", "kickoff": KICKOFF}).json()["data"]
    assert len(fake_cfbd.requests) == before, "the card reads the server's records only"
    assert data["view"] == "program" and len(data["bands"]) == len(D.PAGE_BANDS["program"])
    assert data["cadence"] in ("hourly", "every 15 min") and data["pageSeconds"] == 900
    assert set(data["cfbd"]) == {"state", "lastSuccessAt"} and data["serverTime"].endswith("Z")
    assert _row(data, "Scouting report")["due"] == "Not written"
    assert client.get("/api/datastatus", params={"view": "newspaper"}).json()["data"]["pageSeconds"] == 60
    assert client.get("/api/datastatus", params={"view": "live"}).json()["data"]["pageSeconds"] is None, "In Game is told, it does not ask"
    junk = client.get("/api/datastatus", params={"view": "<script>", "gameId": "../../etc"}).json()["data"]
    assert junk["bands"] == [] and junk["cadence"] is None
