"""FEAT-17 the Imperialism Map (Feature Set v2 Phase B, owner 2026-10-30): the spec's tests (B.12) and the job's.

The shares add up exactly; the weighted split (owner 2026-10-30, over the spec's nearest-campus rule) on a hand-worked line
of ten cells and a square, every team one solid piece; the start map kept per season and dealt again when its inputs
change; the capped take, a loser with fewer cells than the
cap, a team at zero winning land back, an FCS side and an unfinished or tied game moving nothing; Selection Sunday's split
with the leftover cells to the best seeds; the playoff taking everything; a made-up season twice to the same bytes; a
snapshot packed and read back. The committed grid and enrollment table checked; the projection run both ways; the Census
outline read. The job against the simulated league and the answers, including their 404 and 503."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.cfbd.models import Game
from app.config import Settings
from app.demo.upstream import DemoUpstream
from app.logging_setup import configure_logging, shutdown_logging
from app.main import create_app
from app.services.imperialism import (
    Board,
    ImperialismError,
    ImperialismStore,
    Season,
    TeamSpot,
    build_table,
    deal,
    decisive,
    home_cells,
    pack,
    quotas,
    read_enrollment,
    unpack,
)
from app.services.imperialism_grid import Grid, hawaii, load_grid, lower48, neighbors, read_states, unit
from tests.conftest import league

NOW = datetime(2026, 12, 31, tzinfo=timezone.utc)
SATURDAY = datetime(2026, 9, 26, 22, 0, tzinfo=timezone.utc)


def grid_of(cells: list[tuple[int, int, float, float]]) -> Grid:
    """A small grid from (col, row, lat, lon)."""
    g = Grid(side=1.0, x0=0.0, y0=0.0, ids=list(range(len(cells))), cols=[c[0] for c in cells], rows=[c[1] for c in cells], regions=["lower48"] * len(cells), lats=[c[2] for c in cells], lons=[c[3] for c in cells])
    g.vectors = [unit(la, lo) for la, lo in zip(g.lats, g.lons, strict=True)]
    return g


def line() -> Grid:
    """Ten cells in a row along the 30th parallel, a degree of longitude apart (col 0 at 90 W)."""
    return grid_of([(c, 0, 30.0, -90.0 + c) for c in range(10)])


def square(n: int = 6) -> Grid:
    """An n x n patch, half a degree apart."""
    return grid_of([(c, r, 30.0 + 0.5 * r, -90.0 + 0.5 * c) for c in range(n) for r in range(n)])


def spots(*rows: tuple[str, int, float, float]) -> list[TeamSpot]:
    return [TeamSpot(key, i, quota, lat, lon, unit(lat, lon)) for i, (key, quota, lat, lon) in enumerate(rows)]


def game(gid: int, week: int, home: str, away: str, hp: int | None, ap: int | None, *, completed: bool = True, start: str = "2026-09-05T17:00:00.000Z", season_type: str = "regular", notes: str | None = None, playoff: dict[str, Any] | None = None) -> Game:
    return Game.model_validate({"id": gid, "season": 2026, "week": week, "seasonType": season_type, "startDate": start, "completed": completed, "homeTeam": home, "awayTeam": away, "homePoints": hp, "awayPoints": ap, "notes": notes, "playoff": playoff})


# --- the shares (B.3) -----------------------------------------------------------------------------------------------


def test_shares_add_up_exactly_for_138_awkward_enrollments():
    enrollment = {f"School {i:03}": 1000 + (i * 7919) % 97003 for i in range(138)}
    for cells in (12050, 12000, 11999, 137, 1):
        shares = quotas(enrollment, cells)
        assert sum(shares.values()) == cells
        total = sum(enrollment.values())
        assert all(cells * e // total <= shares[t] <= cells * e // total + 1 for t, e in enrollment.items())


def test_a_tie_for_the_last_cell_goes_to_the_first_name():
    assert quotas({"Bravo": 1000, "Alpha": 1000, "Charlie": 1000}, 10) == {"Alpha": 4, "Bravo": 3, "Charlie": 3}
    assert quotas({}, 10) == {}


# --- the deal, worked by hand (B.3) ---------------------------------------------------------------------------------


def test_the_start_grows_from_each_campus_on_a_line_of_ten_cells():
    # v3 (owner 2026-10-30: "the schools need to be anchored in their locations"): A (5 cells) at col 0, B (3) at col 9, C (2)
    # between cols 4 and 5. Each grows from its own campus cell, in turns, toward its share: A 0 to 3, C 4 and 5, B 7 to 9,
    # and the one cell left (col 6) to the neighbor whose campus reaches it first at its speed.
    teams = spots(("A", 5, 30.0, -90.0), ("B", 3, 30.0, -81.0), ("C", 2, 30.0, -85.5))
    owners = deal(line(), teams)
    homes = home_cells(line(), teams)
    assert [owners[h] for h in homes] == [0, 1, 2], "every team holds its own campus"
    assert pieces(line(), owners) == {0: 1, 1: 1, 2: 1}, "one stretch each"
    assert owners[0] == 0 and owners[9] == 1 and owners[homes[2]] == 2


def pieces(grid: Grid, owners: list[int]) -> Counter:
    near = grid.neighbor_ids()
    seen, count = [False] * len(owners), Counter()
    for start in range(len(owners)):
        if seen[start]:
            continue
        count[owners[start]] += 1
        todo, seen[start] = [start], True
        while todo:
            x = todo.pop()
            for n in near[x]:
                if not seen[n] and owners[n] == owners[start]:
                    seen[n] = True
                    todo.append(n)
    return count


def test_the_start_anchors_every_team_on_its_campus_in_one_solid_piece():
    g = square(6)
    teams = spots(("A", 6, 30.0, -90.0), ("B", 6, 32.5, -87.5), ("C", 6, 30.0, -87.5), ("D", 6, 32.5, -90.0), ("E", 6, 31.0, -89.0), ("F", 6, 31.5, -88.0))
    owners = deal(g, teams)
    homes = home_cells(g, teams)
    assert [owners[h] for h in homes] == list(range(6)), "each team on its own campus"
    assert pieces(g, owners) == {i: 1 for i in range(6)}
    assert all(abs(n - 6) <= 1 for n in Counter(owners).values()), "with room around, every team comes within a cell of its share"
    assert sum(Counter(owners).values()) == g.count and deal(g, teams) == owners, "the whole map, and the same inputs give the same map"


def test_two_campuses_in_one_cell_each_get_their_own():
    g = square(6)
    teams = spots(("A", 18, 31.0, -89.0), ("B", 18, 31.01, -89.01))
    homes = home_cells(g, teams)
    assert homes[0] != homes[1], "the second campus takes the nearest free cell"
    owners = deal(g, teams)
    assert owners[homes[0]] == 0 and owners[homes[1]] == 1


def test_a_crowded_team_is_not_shut_in_at_once():
    # a small school beside a big one: the equal first turns give it its ring before the big one's share-by-share turns
    g = square(6)
    teams = spots(("Big", 30, 31.0, -89.0), ("Small", 6, 31.0, -88.5))
    owners = deal(g, teams)
    assert Counter(owners)[1] >= 6


def test_the_start_map_is_kept_and_dealt_again_when_its_inputs_change():
    g, enrollment, fbs, campuses, regular, post = small_season()
    first = Season(g, enrollment, fbs, campuses, NOW)
    first.replay(regular, post, None, "-")
    assert first.dealt
    key = first.start_key("v1")
    again = Season(g, enrollment, fbs, campuses, NOW)
    assert again.start_key("v1") == key and again.start_key("v2") != key, "a new grid deals again"
    again.replay(regular, post, None, "-", first.start)
    assert not again.dealt and again.start == first.start
    assert [s.owners for s in again.snapshots] == [s.owners for s in first.snapshots]
    wrong = Season(g, enrollment, fbs, campuses, NOW)
    wrong.replay(regular, post, None, "-", [0] * g.count)
    assert wrong.dealt, "a kept map that does not meet the shares is worked out again"
    moved = dict(campuses)
    moved["T00"] = (campuses["T00"][0] + 0.5, campuses["T00"][1])
    assert Season(g, enrollment, fbs, moved, NOW).start_key("v1") != key, "a campus that moves deals again"


def test_the_deal_covers_the_map_even_when_the_shares_do_not():
    owners = deal(line(), spots(("A", 4, 30.0, -90.0), ("B", 3, 30.0, -81.0)))
    assert all(o in (0, 1) for o in owners) and owners[0] == 0 and owners[9] == 1, "the cells no share asked for go to the neighbor that reaches them first"


# --- the takes (B.4, B.7) -------------------------------------------------------------------------------------------


def board_of(owners: list[int], teams: list[TeamSpot], grid: Grid | None = None) -> Board:
    return Board(grid or line(), teams, owners)


def test_a_capped_take_moves_the_winners_starting_size_nearest_first():
    teams = spots(("A", 2, 30.0, -90.0), ("B", 8, 30.0, -81.0))
    board = board_of([0, 0, 1, 1, 1, 1, 1, 1, 1, 1], teams)
    moved = board.capped_take(0, 1)
    assert moved == [2, 3], "the two of B's cells nearest A's land"
    assert board.owners == [0, 0, 0, 0, 1, 1, 1, 1, 1, 1]


def test_a_loser_with_fewer_cells_than_the_cap_loses_them_all():
    teams = spots(("A", 6, 30.0, -90.0), ("B", 4, 30.0, -81.0))
    board = board_of([0, 0, 0, 0, 0, 0, 0, 0, 1, 1], teams)
    assert board.capped_take(0, 1) == [8, 9] and board.cells[1] == set()


def test_a_team_at_zero_wins_land_back_from_its_campus():
    teams = spots(("A", 3, 30.0, -90.0), ("B", 7, 30.0, -81.0))
    board = board_of([1] * 10, teams)
    assert board.capped_take(0, 1) == [0, 1, 2], "with no land, the cells nearest its campus"


def test_the_playoff_takes_everything():
    teams = spots(("A", 3, 30.0, -90.0), ("B", 7, 30.0, -81.0))
    board = board_of([0, 0, 0, 1, 1, 1, 1, 1, 1, 1], teams)
    assert len(board.take_all(0, 1)) == 7 and board.owners == [0] * 10


def test_unfinished_tied_and_unscored_games_decide_nothing():
    assert decisive(game(1, 1, "A", "B", 21, 14)) == ("A", "B")
    assert decisive(game(1, 1, "A", "B", 14, 21)) == ("B", "A")
    for g in (game(1, 1, "A", "B", 21, 14, completed=False), game(1, 1, "A", "B", 14, 14), game(1, 1, "A", "B", None, None), game(1, 1, "A", "B", 21, None)):
        assert decisive(g) is None


# --- Selection Sunday (B.6) -----------------------------------------------------------------------------------------


def test_selection_splits_the_pool_evenly_with_the_leftover_to_the_best_seeds():
    g = square(6)  # 36 cells
    teams = spots(("A", 6, 30.0, -90.0), ("B", 6, 32.5, -87.5), ("C", 6, 30.0, -87.5), ("D", 6, 32.5, -90.0), ("E", 6, 31.0, -89.0), ("F", 6, 31.5, -88.0))
    owners = [cell // 6 for cell in range(g.count)]  # a column each: the selection's own test, whatever the start rule
    board = Board(g, teams, owners)
    before = Counter(board.owners)
    moved = board.selection([1, 0])  # B is the top seed, then A; C to F are out
    after = Counter(board.owners)
    pool = sum(before[i] for i in (2, 3, 4, 5))
    assert pool == 24
    assert after[1] - before[1] == 12 and after[0] - before[0] == 12, "an even split"
    assert all(after[i] == 0 for i in (2, 3, 4, 5)), "everyone outside the field ends at zero"
    assert sum(moved.values()) == 24 and all(to in (0, 1) and frm in (2, 3, 4, 5) for to, frm in moved)
    board2 = Board(g, teams, owners)
    board2.move([c for c, o in enumerate(board2.owners) if o == 5][:1], 1)  # 23 cells in the pool: one left over
    before2 = Counter(board2.owners)
    board2.selection([0, 1])
    after2 = Counter(board2.owners)
    assert after2[0] - before2[0] == 12 and after2[1] - before2[1] == 11, "the leftover cell to the top seed"


# --- a whole made-up season (B.5, B.7, determinism) -------------------------------------------------------------------


def small_season() -> tuple[Grid, dict[str, int], dict[str, dict[str, Any]], dict[str, tuple[float, float]], list[Game], list[Game]]:
    g = square(8)  # 64 cells
    names = [f"T{i:02}" for i in range(14)]
    enrollment = {n: 10000 + 1500 * i for i, n in enumerate(names)}
    campuses = {n: (30.0 + 0.25 * (i % 4) * 3, -90.0 + 0.25 * (i // 4) * 3) for i, n in enumerate(names)}
    fbs = {n: {"abbreviation": n} for n in names}
    regular = []
    gid = 1
    for week in range(1, 4):
        for i in range(0, 14, 2):
            a, b = names[(i + week) % 14], names[(i + week * 3 + 1) % 14]
            if a == b:
                continue
            regular.append(game(gid, week, a, b, 20 + (gid % 7), 17, start=f"2026-09-{week * 7:02d}T17:00:00.000Z"))
            gid += 1
    regular.append(game(gid, 3, names[0], "Campbell", 52, 3, start="2026-09-21T17:00:00.000Z"))  # an FCS side: nothing moves
    regular.append(game(gid + 1, 4, names[1], names[2], 24, 21, start="2026-09-28T17:00:00.000Z", notes="Conference Championship"))
    seeds = names[:12]
    post = [
        game(500 + i, 1, seeds[i], seeds[11 - i], 30, 10, season_type="postseason", start="2026-12-20T17:00:00.000Z", playoff={"competition": "cfp", "round": "first_round", "homeSeed": i + 1, "awaySeed": 12 - i})
        for i in range(4, 8) if i < 11 - i
    ]
    post.append(game(600, 1, names[12], names[13], 31, 28, season_type="postseason", start="2026-12-22T17:00:00.000Z", notes="A bowl"))
    return g, enrollment, fbs, campuses, regular, post


def run_season() -> tuple[Season, dict[str, Any]]:
    g, enrollment, fbs, campuses, regular, post = small_season()
    season = Season(g, enrollment, fbs, campuses, NOW)
    season.replay(regular, post, [(n, i + 1) for i, n in enumerate(sorted(fbs)[:12])], "/playoffs/cfp/participants")
    return season, build_table(season, fbs, 4, {}, "test")


def test_the_table_names_each_campus_and_starting_size():
    season, table = run_season()
    start = season.snapshots[0].owners
    assert all(isinstance(t["home"], int) and start[t["home"]] == t["index"] for t in table["teams"]), "every school starts on its own campus"
    held = Counter(start)
    assert all(t["quota"] == held[t["index"]] for t in table["teams"]), "a win takes up to the land a school was dealt"
    assert sum(t["share"] for t in table["teams"]) == len(start), "the enrollment shares still add up to the map"
    from app.api.imperialism import _teams

    assert _teams({"teams": [{"team": "A", "index": 0, "quota": 3, "home": 5, "id": None}]}, None)[0]["home"] == 5


def test_a_kept_start_map_must_anchor_every_school():
    g, enrollment, fbs, campuses, regular, post = small_season()
    first = Season(g, enrollment, fbs, campuses, NOW)
    first.replay(regular, post, None, "-")
    shifted = first.start[1:] + first.start[:1]
    again = Season(g, enrollment, fbs, campuses, NOW)
    again.replay(regular, post, None, "-", shifted)
    assert again.dealt and again.start == first.start, "a kept map that moved a school off its campus is dealt again"


def test_a_season_twice_gives_the_same_bytes():
    _s1, first = run_season()
    _s2, second = run_season()
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_the_season_goes_start_weeks_selection_playoff():
    season, table = run_season()
    labels = [(s["phase"], s["label"]) for s in table["snapshots"]]
    assert labels[0] == ("regular", "Start") and ("regular", "CCG") in labels
    assert ("selection", "Selection Sunday") in labels and labels[-1] == ("postseason", "R1")
    selection = next(s for s in season.snapshots if s.phase == "selection")
    field = {season.index[n] for n in sorted(season.index)[:12]}
    assert set(Counter(selection.owners)) <= field, "after Selection Sunday only the twelve hold land"
    assert all(sum(Counter(s.owners).values()) == 64 for s in season.snapshots)
    assert any(e["rule"] == "none" and e["loser"] == "Campbell" for e in season.events), "the FCS game moved nothing"
    bowl = next(e for e in season.events if e["gameId"] == 600)
    assert bowl["cellsMoved"] == 0 and bowl["rule"] == "none", "a bowl after Selection Sunday: the loser holds nothing"
    r1 = [e for e in season.events if e["rule"] == "winner_take_all"]
    assert r1 and all(Counter(season.snapshots[-1].owners)[season.index[e["loser"]]] == 0 for e in r1)
    assert season.snapshots[0].records["T00"] == (0, 0) and season.snapshots[-1].records["T00"][0] >= 1


def test_no_field_stops_before_selection_and_says_so():
    g, enrollment, fbs, campuses, regular, _post = small_season()
    season = Season(g, enrollment, fbs, campuses, NOW)
    season.replay(regular, [], None, "/playoffs/cfp/participants")
    assert season.notes == ["CFP field not yet known"] and season.snapshots[-1].phase == "regular"


def test_a_week_still_being_played_is_in_progress():
    g, enrollment, fbs, campuses, regular, _post = small_season()
    pending = game(999, 3, "T03", "T04", None, None, completed=False, start="2026-09-21T23:00:00.000Z")
    season = Season(g, enrollment, fbs, campuses, datetime(2026, 9, 21, 20, tzinfo=timezone.utc))
    season.replay([g2 for g2 in regular if g2.week <= 3] + [pending], [], None, "-")
    assert [s.partial for s in season.snapshots if s.label == "Wk 3"] == [True]


def test_a_school_with_no_enrollment_row_is_named():
    g, enrollment, fbs, campuses, _regular, _post = small_season()
    with pytest.raises(ImperialismError, match="T13"):
        Season(g, {k: v for k, v in enrollment.items() if k != "T13"}, fbs, campuses, NOW)


# --- packing and the store (B.8) ------------------------------------------------------------------------------------


def test_a_snapshot_packs_and_unpacks(tmp_path: Path):
    owners = [i % 138 for i in range(12050)]
    assert unpack(pack(owners)) == owners
    assert pack(owners) == pack(list(owners)), "no timestamp in the gzip: the same bytes"
    _season, table = run_season()
    store = ImperialismStore(tmp_path, 2026)
    assert store.load() is None
    store.save(table)
    back = store.load()
    assert back["season"] == 2026 and back["snapshots"][0]["owners"] == unpack(table["snapshots"][0]["holdings"])
    store.path.write_text(json.dumps({"format": 99}), encoding="utf-8")
    assert store.load() is None


def test_the_enrollment_table_is_checked(tmp_path: Path):
    path = tmp_path / "e.csv"
    path.write_text("cfbd_school,enrollment,source,source_year,note\nA,999,x,2023,\nB,12x,x,2023,\nC,5000,x,2023,\nC,6000,x,2023,\n,5000,x,2023,\n", encoding="utf-8")
    with pytest.raises(ImperialismError) as caught:
        read_enrollment(path)
    words = str(caught.value)
    assert "A: enrollment '999'" in words and "B: enrollment '12x'" in words and "C: listed twice" in words and "no school" in words


# --- the committed files ---------------------------------------------------------------------------------------------


def test_the_committed_grid_and_enrollment_fit_together():
    grid = load_grid()
    assert grid.ids == list(range(grid.count)) and 11800 <= grid.count <= 12300
    enrollment = read_enrollment()
    assert len(enrollment) >= 138 and all(v >= 1000 for v in enrollment.values())
    shares = quotas(enrollment, grid.count)
    assert sum(shares.values()) == grid.count
    island = sum(1 for r in grid.regions if r == "hawaii")
    assert shares["Hawai'i"] <= island, "Hawaii's starting land fits on the islands (the enlarged inset)"
    near = grid.neighbor_ids()
    assert all(len(n) <= 6 for n in near)
    assert all(c in near[n] for c, ns in enumerate(near) for n in ns), "neighbors are mutual"


def test_the_projection_runs_both_ways_and_the_outline_reads():
    for proj, (lon, lat) in ((lower48(), (-82.35, 29.65)), (lower48(), (-122.4, 47.6)), (hawaii(), (-157.82, 21.29))):
        x, y = proj.forward(lon, lat)
        back = proj.inverse(x, y)
        assert abs(back[0] - lon) < 1e-6 and abs(back[1] - lat) < 1e-6
        assert 0 <= x <= 960 and 0 <= y <= 600
    kml = """<?xml version="1.0"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document><Placemark><ExtendedData><SchemaData>
      <SimpleData name="STUSPS">FL</SimpleData></SchemaData></ExtendedData><MultiGeometry><Polygon><outerBoundaryIs><LinearRing><coordinates>
      -87,30 -80,30 -80,25 -87,25 -87,30</coordinates></LinearRing></outerBoundaryIs></Polygon></MultiGeometry></Placemark>
      <Placemark><ExtendedData><SchemaData><SimpleData name="STUSPS">AK</SimpleData></SchemaData></ExtendedData><Polygon><outerBoundaryIs><LinearRing><coordinates>
      -150,60 -140,60 -140,65 -150,60</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark></Document></kml>"""
    states = read_states(kml)
    assert list(states) == ["FL"] and len(states["FL"][0]) == 5
    assert sorted(neighbors(2, 3)) == sorted([(2, 2), (2, 4), (1, 2), (1, 3), (3, 2), (3, 3)])
    assert sorted(neighbors(3, 3)) == sorted([(3, 2), (3, 4), (2, 3), (2, 4), (4, 3), (4, 4)])


# --- the job and the answers, against the simulated league ------------------------------------------------------------


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


def test_before_any_run_the_map_says_why(lclient: TestClient):
    answer = lclient.get("/api/imperialism/2026/all")
    assert answer.status_code == 503 and "not been worked out yet" in answer.json()["errors"][0]["message"]


def test_the_job_and_every_answer(lclient: TestClient):
    state = lclient.app_state  # type: ignore[attr-defined]
    assert state.jobs.names() == ["weekly", "talent_edge", "imperialism", "circle_of_blame"], "the spec's order"
    run = lclient.portal.call(state.jobs.run, "imperialism")
    assert run["status"] == "ok", run["message"]
    assert "dealt and replayed" in run["message"]
    kept = lclient.portal.call(state.jobs.run, "imperialism")
    assert kept["status"] == "ok" and "dealt" not in kept["message"], "the second run keeps the start map"
    every = lclient.get("/api/imperialism/2026/all").json()["data"]
    assert every["ourTeam"] == "Florida" and every["snapshots"][0]["label"] == "Start"
    cells = every["cells"]
    assert all(len(s["owners"]) == cells for s in every["snapshots"])
    names = [t["team"] for t in every["teams"]]
    assert "Florida" in names and all(isinstance(t["quota"], int) for t in every["teams"])
    weeks = lclient.get("/api/imperialism/2026/weeks").json()["data"]["weeks"]
    assert [w["label"] for w in weeks] == [s["label"] for s in every["snapshots"]]
    last = weeks[-1]
    one = lclient.get(f"/api/imperialism/2026/{last['phase']}/{last['week']}").json()["data"]
    assert sum(r["cells"] for r in one["leaderboard"]) == cells and one["leaderboard"][0]["rank"] == 1
    assert lclient.get("/api/imperialism/2026/regular/99").status_code == 404
    team = lclient.get("/api/imperialism/2026/team/florida").json()["data"]
    assert team["team"] == "Florida" and len(team["weeks"]) == len(weeks) and team["now"]["of"] >= 1
    missing = lclient.get("/api/imperialism/2026/team/Swampwater Tech")
    assert missing.status_code == 404 and "Florida" in missing.json()["data"]["validTeams"]
    grid = lclient.get("/api/imperialism/grid")
    body = grid.json()["data"]
    assert grid.headers["cache-control"] == "no-cache" and len(body["cells"]) == 2 * body["count"] == 2 * cells
    kept = lclient.get(f"/api/imperialism/grid?v={body['version']}")
    assert "immutable" in kept.headers["cache-control"], "the tablet keeps the grid until it changes"
    assert lclient.get("/api/imperialism/2025/all").status_code == 503


def test_the_page_answer_and_its_data_status(lclient: TestClient):
    before = lclient.get("/api/imperialism/now")
    assert before.status_code == 200, "the page's answer is never an error page"
    assert before.json()["data"]["available"] is False and "not been worked out yet" in before.json()["data"]["message"]
    state = lclient.app_state  # type: ignore[attr-defined]
    assert lclient.portal.call(state.jobs.run, "imperialism")["status"] == "ok"
    now = lclient.get("/api/imperialism/now").json()["data"]
    assert now["available"] is True and now["ourTeam"] == "Florida" and now["runs"]["lastGood"]["status"] == "ok"
    florida = next(t for t in now["teams"] if t["team"] == "Florida")
    assert florida["logo"].startswith("/media/logo/") and florida["logoDark"].endswith("?v=dark"), "each team's id becomes its logo"
    assert now["upcoming"] and now["upcoming"][-1] == "Final", "the weeks still to come, the playoff last"
    assert now["events"] and all(e["cellsMoved"] > 0 and "winnerPoints" in e for e in now["events"])
    assert now["schedule"] and all(g["opponent"] != "Florida" and isinstance(g["home"], bool) for g in now["schedule"]), "our games for the Next line"
    assert all(len(s["owners"]) == now["cells"] for s in now["snapshots"])
    status = lclient.get("/api/datastatus?view=imperialism").json()["data"]
    words = json.dumps(status)
    assert "The map, every week" in words and "Sundays from 6 AM" in words
