"""FEAT-3 (owner 2026-10-23: "backfill this season's played games for team #1"; 2026-10-27, what was left: the Archive): a
game of ours that finished before this install watched one is rebuilt from CFBD's play-by-play after the final, its drives
and its win probability, and saved for the Archive like a watched game, marked `backfilled`. A few games a housekeeping
tick, as paced calls; a game with no plays posted waits six hours; a rebuilt game never gets the two-day second look."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.cache import DataKind
from tests.conftest import FakeCfbd, fixture_payload
from tests.test_live import LAST_GAME, route_live

NOW = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)


def _prime_schedule(app, client: TestClient) -> None:
    """Our schedule in the cache, as the Season page leaves it (the back-fill only peeks)."""

    async def prime() -> None:
        await app.state.cfbd.get("/games", {"year": 2026, "team": "Florida"}, kind=DataKind.SCHEDULE)

    client.portal.call(prime)


def test_a_game_played_before_the_install_is_rebuilt_for_the_archive(app, client: TestClient, fake_cfbd: FakeCfbd):
    route_live(fake_cfbd)
    client.portal.call(app.state.live.stop_background)  # no live window over the test
    archive = app.state.archive
    assert client.portal.call(archive.backfill, NOW) == [], "no schedule cached: nothing asked, nothing saved"
    _prime_schedule(app, client)
    done = client.portal.call(archive.backfill, NOW)
    assert LAST_GAME in done
    raw = json.loads((archive.folder / f"{LAST_GAME}.json").read_text(encoding="utf-8"))
    last = next(g for g in fixture_payload("games_team") if g["id"] == LAST_GAME)
    assert raw["backfilled"] is True and raw["partial"] is False and raw["week"] == last["week"]
    state = raw["state"]
    assert state["status"] == "final" and state["homeScore"] == last["homePoints"] and state["awayScore"] == last["awayPoints"]
    assert state["counts"]["plays"] == len(fixture_payload("plays")) and state["counts"]["drives"] > 5
    assert raw["winProbability"], "CFBD's curve is kept with the game"
    # the Archive lists it and opens it, saying it was rebuilt
    games = client.get("/api/archive").json()["data"]["games"]
    row = next(g for g in games if g["gameId"] == LAST_GAME)
    assert row["backfilled"] is True and row["usScore"] == last["awayPoints"] and row["plays"] == len(fixture_payload("plays"))
    page = client.get(f"/api/archive/{LAST_GAME}")
    assert page.status_code == 200 and page.json()["data"]["winProbability"]["source"].startswith("CFBD's")
    # a second tick within six hours asks CFBD for nothing: the saved game is done, the games with no plays wait
    before = fake_cfbd.count()
    assert client.portal.call(archive.backfill, NOW + timedelta(hours=1)) == []
    assert fake_cfbd.count() == before
    # and the two-day second look leaves a rebuilt game alone
    assert LAST_GAME not in client.portal.call(archive.refresh_finished, NOW + timedelta(days=3))


def test_a_game_the_app_watched_is_never_rebuilt(app, client: TestClient, fake_cfbd: FakeCfbd):
    route_live(fake_cfbd)
    client.portal.call(app.state.live.stop_background)
    archive = app.state.archive
    archive.folder.mkdir(parents=True, exist_ok=True)
    watched = {"gameId": LAST_GAME, "home": "Fresno State", "away": "Florida", "state": {"status": "final", "homeScore": 1, "awayScore": 2}, "savedAt": "2026-09-26T23:00:00+00:00"}
    (archive.folder / f"{LAST_GAME}.json").write_text(json.dumps(watched), encoding="utf-8")
    _prime_schedule(app, client)
    assert LAST_GAME not in client.portal.call(archive.backfill, NOW)
    assert json.loads((archive.folder / f"{LAST_GAME}.json").read_text(encoding="utf-8")) == watched, "the watched game's file is untouched"


def test_a_failing_cfbd_leaves_the_game_for_later(app, client: TestClient, fake_cfbd: FakeCfbd):
    import httpx

    route_live(fake_cfbd)
    client.portal.call(app.state.live.stop_background)
    _prime_schedule(app, client)
    fake_cfbd.route("/plays", handler=lambda r: httpx.Response(500, json={"message": "down"}))
    archive = app.state.archive
    assert client.portal.call(archive.backfill, NOW) == []
    assert not (archive.folder / f"{LAST_GAME}.json").exists()
    fake_cfbd.fixture("/plays", "plays")
    assert client.portal.call(archive.backfill, NOW + timedelta(hours=1)) == [], "tried again only after six hours"
    assert LAST_GAME in client.portal.call(archive.backfill, NOW + timedelta(hours=7))
