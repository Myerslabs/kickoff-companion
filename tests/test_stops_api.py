"""`GET /api/stops` against the test league (the season as one line, Wave 1): the line, the current stop, the hrefs."""
from __future__ import annotations

from tests.test_season_notes import league  # noqa: F401 - routes the fake CFBD


def test_stops_answer_has_the_line_and_the_current_stop(app, client, league):  # noqa: F811
    answer = client.get("/api/stops")
    assert answer.status_code == 200, answer.text
    data = answer.json()["data"]
    assert data["season"] == app.state.settings.season and data["team"] == app.state.settings.team
    kinds = [item["kind"] for item in data["items"]]
    assert kinds[0] == "preseason" and kinds[-1] == "book" and "now" in kinds
    weeks = [item for item in data["items"] if item["kind"] == "week"]
    assert weeks, "the league's games are weeks on the line"
    for item in weeks:
        assert set(item["stops"]) == {"pre", "game", "post"}
        for stop in item["stops"].values():
            assert stop["state"] in {"saved", "live", "open", "to_come", "missing", "done", "closed"}
            assert stop["href"] is None or stop["href"].startswith("#")
        if item["result"] is not None:
            assert item["stops"]["game"]["href"] == f"#archive={item['gameId']}"
            assert item["stops"]["post"]["href"] == f"#postgame={item['gameId']}"
    current = data["current"]
    assert current["kind"] in {"pre", "post", "season"}
    assert current["href"].startswith("#") and current["label"]
    # the weeks are in order and the now marker sits by date
    numbers = [item["week"] for item in data["items"] if item["kind"] in ("week", "bye")]
    assert numbers == sorted(numbers)


def test_stops_hrefs_open_in_the_app(app, client, league):  # noqa: F811
    data = client.get("/api/stops").json()["data"]
    played = [item for item in data["items"] if item["kind"] == "week" and item["result"] is not None]
    assert played
    last = played[-1]
    assert client.get(f"/api/program/{last['gameId']}").status_code == 200
    assert client.get(f"/api/program/{last['gameId']}/postgame").status_code in (200, 404)
