"""The made-up league (public release Phase 2): shapes match CFBD's, the app's parsers take every
answer whole, the numbers add up, the clock hides the future, and nothing is copied or real.

The league is built once per test run (about ten seconds) and kept in pytest's cache folder.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import timedelta
from pathlib import Path

import httpx
import pytest

from app.cfbd.models import ENDPOINTS, parse_endpoint
from app.demo import names as N
from app.demo import stats as S
from app.demo.fixtures import RECORDINGS, league_fixture, roles
from app.demo.league import League
from app.demo.season import World
from app.demo.shapes import compare, shape_of
from app.demo.sim import GameSim, Side
from app.demo.sites import DemoSites, headlines
from app.demo.upstream import TEST_NOW, DemoUpstream, answer, load_world

ROOT = Path(__file__).resolve().parents[1]
SHAPES = ROOT / "tests" / "fixtures" / "league" / "shapes.json"
RECORDED = ROOT / "tests" / "fixtures" / "cfbd"


@pytest.fixture(scope="session")
def world(pytestconfig, tmp_path_factory) -> World:
    cache = getattr(pytestconfig, "cache", None)  # absent under -p no:cacheprovider
    folder = Path(cache.mkdir("demo-league")) if cache is not None else tmp_path_factory.mktemp("demo-league")
    return load_world(cache_dir=folder)


@pytest.fixture(scope="session")
def values(world) -> dict[str, str]:
    return roles(world)


@pytest.fixture(scope="session")
def twins(world, values) -> dict[str, dict]:
    return {name: league_fixture(world, name, values=values) for name in RECORDINGS}


def ask(world: World, path: str, **params: str):
    status, payload = answer(world, path, {k: str(v) for k, v in params.items()}, TEST_NOW)
    assert status == 200, (path, params, payload)
    return payload


# -- the contract -----------------------------------------------------------------------------
def test_every_recording_has_a_twin_and_a_shape():
    shapes = json.loads(SHAPES.read_text(encoding="utf-8"))
    assert set(shapes) == set(RECORDINGS)
    assert len(RECORDINGS) >= 120
    if RECORDED.is_dir():
        recorded = {p.stem for p in RECORDED.glob("*.json")} - {"MANIFEST"}
        assert recorded == set(RECORDINGS), sorted(recorded ^ set(RECORDINGS))


def test_shapes_hold_no_values():
    """shapes.json is public: field names and JSON types only."""
    def walk(node, path="$"):
        assert set(node) <= {"t", "k", "i"}, path
        assert set(node.get("t", [])) <= {"null", "bool", "int", "float", "str", "list", "dict"}, path
        for key, child in node.get("k", {}).items():
            walk(child, f"{path}.{key}")
        if "i" in node:
            walk(node["i"], f"{path}[]")

    shapes = json.loads(SHAPES.read_text(encoding="utf-8"))
    for name, spec in shapes.items():
        assert set(spec) == {"endpoint", "status", "empty", "shape"}, name
        walk(spec["shape"], name)


def test_twins_match_cfbd_shapes(twins):
    shapes = json.loads(SHAPES.read_text(encoding="utf-8"))
    problems = []
    for name, spec in shapes.items():
        twin = twins[name]
        if twin["status"] != spec["status"]:
            problems.append(f"{name}: status {twin['status']} != {spec['status']}")
            continue
        payload = twin["payload"]
        if spec["empty"] or payload in (None, [], {}):
            if not spec["empty"]:
                problems.append(f"{name}: empty where CFBD sent data")
            continue
        problems += [f"{name}: {p}" for p in compare(spec["shape"], shape_of(payload))]
    assert problems == []


def test_the_app_parses_every_twin_whole(twins):
    for name, twin in twins.items():
        if twin["status"] != 200 or twin["endpoint"] not in ENDPOINTS:
            continue
        result = parse_endpoint(twin["endpoint"], twin["payload"], context=name)
        if hasattr(result, "skipped"):
            assert result.skipped == 0 and not result.problems, (name, result.problems[:3])
        elif ENDPOINTS[twin["endpoint"]].model is not None:
            assert result is not None, name


def test_compare_finds_missing_extra_and_wrong_types():
    cfbd = shape_of([{"a": 1, "b": "x", "c": {"d": 1.5}}])
    assert compare(cfbd, shape_of([{"a": 2.0, "b": None, "c": {"d": 2}}])) == []
    problems = compare(cfbd, shape_of([{"a": "1", "c": {"d": 1, "e": 2}}]))
    assert any(".b: missing" in p for p in problems)
    assert any(".e: not a CFBD field" in p for p in problems)
    assert any(".a: type ['str']" in p for p in problems)


# -- made up, not copied -------------------------------------------------------------------------
def test_league_size_and_names(world):
    fbs = world.league.fbs
    assert len(fbs) == 136
    assert len({t.school for t in world.league.teams}) == len(world.league.teams)
    assert len({t.abbr for t in fbs}) == 136
    assert world.league.team(N.OUR_SCHOOL) is not None
    assert {t.conference for t in fbs} == {c for c, _, _ in N.CONFERENCES}


@pytest.mark.skipif(not (RECORDED / "teams_fbs.json").is_file(), reason="needs the private recordings")
def test_no_real_school_or_mascot():
    real = json.loads((RECORDED / "teams_fbs.json").read_text(encoding="utf-8"))["payload"]
    schools = {t["school"].lower() for t in real}
    pairs = {(t["school"].lower(), (t.get("mascot") or "").lower()) for t in real}
    conferences = {(t.get("conference") or "").lower() for t in real}
    for conference, _short, members in N.CONFERENCES:
        if conference != "FBS Independents":
            assert conference.lower() not in conferences
        for school, mascot, _ in members:
            assert school.lower() not in schools, school
            assert (school.lower(), mascot.lower()) not in pairs


def test_no_real_broadcaster_or_bookmaker():
    real = {"espn", "abc", "fox", "cbs", "nbc", "fs1", "sec network", "acc network", "btn", "draftkings", "fanduel", "bovada", "espn bet"}
    for name in N.NETWORKS + N.PROVIDERS:
        assert name.lower() not in real


def test_demo_links_lead_nowhere(world):
    rows = headlines(world, TEST_NOW)
    assert rows
    assert all(".invalid/" in row["link"] for row in rows)


# -- the numbers add up -------------------------------------------------------------------------
def test_line_scores_and_boxes_add_up(world):
    data = world.seasons[world.season - 1]
    for r in data.records[::17]:
        assert sum(r.home_lines) == r.home_points and sum(r.away_lines) == r.away_points
        assert r.home_points != r.away_points
        for side in (0, 1):
            team = r.counts[side]
            lines = r.lines[side]
            assert team["pass_yds"] == sum(c["pass_yds"] for c in lines.values())
            assert team["pass_yds"] == sum(c["rec_yds"] for c in lines.values())
            assert team["pass_comp"] == sum(c["rec"] for c in lines.values())
            assert team["rush_yds"] == sum(c["rush_yds"] for c in lines.values())
            points = r.home_points if side == 0 else r.away_points
            tds = team["pass_td"] + team["rush_td"] + team["int_td"] + team["kr_td"]
            assert points >= 6 * tds


def test_plays_replay_the_recorded_result(world):
    data = world.seasons[world.season]
    for r in data.records[::40]:
        result = world.simulate(r.id)
        assert (result.home_points, result.away_points) == (r.home_points, r.away_points)
        last = result.plays[-1]
        assert (last.home_after, last.away_after) == (r.home_points, r.away_points)


def test_season_shape_is_realistic(world):
    data = world.seasons[world.season - 1]
    regular = [r for r in data.records if r.slot.season_type == "regular" and r.slot.week <= 14]
    games = Counter()
    for r in regular:
        games[r.slot.home] += 1
        games[r.slot.away] += 1
    assert all(games[t.id] == 12 for t in world.league.fbs)
    points = [p for r in regular for p in (r.home_points, r.away_points)]
    assert 25 <= sum(points) / len(points) <= 34
    champs = [r for r in data.records if r.slot.week == 15]
    assert len(champs) == 10
    playoff = [r for r in data.records if r.slot.playoff]
    assert len(playoff) == 11
    assert sorted({r.slot.playoff["bracketSlot"] for r in playoff}) == sorted(["FR1", "FR2", "FR3", "FR4", "QF1", "QF2", "QF3", "QF4", "SF1", "SF2", "CH"])


def test_no_team_is_booked_twice_in_a_week(world):
    for data in world.seasons.values():
        seen = set()
        for r in data.records:
            if r.slot.season_type != "regular":
                continue
            for tid in (r.slot.home, r.slot.away):
                if world.league.by_id[tid].is_fbs:
                    assert (tid, r.slot.week) not in seen
                    seen.add((tid, r.slot.week))


def test_same_seed_same_league():
    a, b = League(7, 2026), League(7, 2026)
    assert [t.school for t in a.teams] == [t.school for t in b.teams]
    assert [(g.id, g.home, g.away, g.start) for g in a.schedules[2026]] == [(g.id, g.home, g.away, g.start) for g in b.schedules[2026]]
    assert sorted(a.players) == sorted(b.players)
    assert League(8, 2026).teams[1].color != a.teams[1].color or League(8, 2026).schedules[2026][0].id != a.schedules[2026][0].id


def _side(i: int) -> Side:
    base = i * 100
    return Side(team_id=i, school=f"T{i}", abbr=f"T{i}", offense=0, defense=0, special=0, pass_rate=0.5, qbs=[base + 1],
                rbs=[base + 2, base + 3], targets=[(base + 10, 0.5), (base + 11, 0.5)], dline=[base + 20, base + 21],
                lbs=[base + 30], dbs=[base + 40, base + 41], kicker=base + 50, punter=base + 51, returner=base + 10,
                holder=base + 51, snapper=base + 52)


def test_a_game_is_deterministic_and_whole():
    one = GameSim(99, _side(1), _side(2), 0.0).run()
    two = GameSim(99, _side(1), _side(2), 0.0).run()
    assert [(p.ptype, p.gained, p.clock) for p in one.plays] == [(p.ptype, p.gained, p.clock) for p in two.plays]
    assert one.plays[-1].ptype == "End of Game"
    assert sum(1 for p in one.plays if p.ptype == "End Period") == 4
    scrim = S.scrimmage(one.plays, 0) + S.scrimmage(one.plays, 1)
    assert 110 <= len(scrim) <= 190
    assert all(1 <= p.ytg <= 99 for p in scrim)


# -- the clock ----------------------------------------------------------------------------------
def test_future_games_have_no_result(world, values):
    games = ask(world, "/games", year=world.season, team=values["US"])
    done = [g for g in games if g["completed"]]
    ahead = [g for g in games if not g["completed"]]
    assert done and ahead
    assert all(g["homePoints"] is None and g["homeLineScores"] is None for g in ahead)
    assert all(isinstance(g["homePoints"], int) for g in done)
    assert all(g["week"] <= int(values["LASTWEEK"]) for g in done)
    # championships and bowls are not on the schedule until they are set
    assert all(g["seasonType"] == "regular" and g["week"] <= 14 for g in games)


def test_polls_and_boxes_wait_for_the_clock(world, values):
    weeks = [w["week"] for w in ask(world, "/rankings", year=world.season)]
    assert weeks and max(weeks) <= int(values["DONEWEEK"]) + 1
    nxt = [g for g in ask(world, "/games", year=world.season, team=values["US"]) if not g["completed"]][0]
    assert ask(world, "/games/teams", id=nxt["id"]) == []
    assert answer(world, "/game/box/advanced", {"id": str(nxt["id"])}, TEST_NOW)[0] == 404


def test_live_document_grows_through_a_game(world, values):
    nxt = [g for g in ask(world, "/games", year=world.season, team=values["US"]) if not g["completed"]][0]
    data = world.seasons[world.season]
    r = data.by_id[nxt["id"]]
    from app.demo.render_live import live_document

    before = live_document(world, r, r.slot.start - timedelta(minutes=5))
    assert before["status"] == "scheduled" and before["drives"] == []
    middle = live_document(world, r, r.slot.start + timedelta(minutes=80))
    assert middle["status"] == "in_progress" and middle["drives"]
    after = live_document(world, r, r.end + timedelta(minutes=1))
    assert after["status"] == "Final"
    count = lambda doc: sum(len(d["plays"]) for d in doc["drives"])  # noqa: E731
    assert 0 < count(middle) < count(after)
    points = {t["homeAway"]: t["points"] for t in after["teams"]}
    assert (points["home"], points["away"]) == (r.home_points, r.away_points)


# -- the upstream -------------------------------------------------------------------------------
def _get(upstream: DemoUpstream, path: str, **params: str) -> httpx.Response:
    return upstream.handler(httpx.Request("GET", f"http://cfbd.demo.invalid{path}", params=params))


def test_plans_gate_like_cfbd(world):
    free = DemoUpstream(world, lambda: TEST_NOW, tier=0)
    assert _get(free, "/scoreboard").status_code == 401
    assert _get(free, "/games/weather", year="2026").status_code == 401
    assert _get(free, "/live/plays", gameId="1").status_code == 401
    assert _get(free, "/games", year="2026", week="1").status_code == 200
    info = _get(free, "/info").json()
    assert info["tierName"] == "Free" and info["monthlyLimit"] == 1000
    assert info["usedCalls"] == 4 and info["features"]["livePlayByPlay"] is False  # /info itself is free, as at CFBD
    paid = DemoUpstream(world, lambda: TEST_NOW, tier=2)
    assert _get(paid, "/scoreboard", classification="fbs").status_code == 200
    assert _get(paid, "/info").json()["features"]["livePlayByPlay"] is True
    assert _get(paid, "/nothing/here").status_code == 404


def test_upstream_reports_its_own_bugs_as_500(world):
    upstream = DemoUpstream(world, lambda: TEST_NOW, tier=2, fail=lambda path: path == "/plays")
    assert _get(upstream, "/plays", year="2026", week="1").status_code == 500
    assert _get(upstream, "/games", year="2026", week="1").status_code == 200


def test_demo_sites_answer_feeds_and_weather(world):
    sites = DemoSites(world, lambda: TEST_NOW)
    feed = sites.handler(httpx.Request("GET", "https://example.invalid/rss?path=football"))
    assert feed.status_code == 200 and b"<item>" in feed.content
    points = sites.handler(httpx.Request("GET", "https://api.weather.gov/points/30.0,-82.0"))
    forecast = sites.handler(httpx.Request("GET", points.json()["properties"]["forecast"]))
    assert len(forecast.json()["properties"]["periods"]) == 14
    assert DemoSites.media_handler(httpx.Request("GET", "https://a.invalid/x.png")).status_code == 404


def test_the_cache_matches_a_fresh_build(world, tmp_path):
    """A pickled league is the league: the same records come back."""
    import pickle

    path = tmp_path / "w.pickle"
    path.write_bytes(pickle.dumps(world, protocol=pickle.HIGHEST_PROTOCOL))
    again = pickle.loads(path.read_bytes())
    a = world.seasons[world.season].records[:20]
    b = again.seasons[again.season].records[:20]
    assert [(r.id, r.home_points, r.away_points) for r in a] == [(r.id, r.home_points, r.away_points) for r in b]


def test_demo_takes_the_next_free_port():
    import socket

    from app.demo.run import DEFAULT_PORT, PORT_TRIES, pick_port

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen(1)
        taken = busy.getsockname()[1]
        assert pick_port("127.0.0.1", taken) is None  # a port asked for by name is never swapped
        chosen = pick_port("127.0.0.1", None)
        assert chosen is None or DEFAULT_PORT <= chosen < DEFAULT_PORT + PORT_TRIES
