"""Phase 13 (stats depth II): the client's patience with a busy endpoint (the Diner Tech night's 429
"Too many concurrent requests" after two timeouts on /stats/season/advanced); the calculations
behind the new tables from recorded answers, with junk; the routes that carry them; and the new
front-end helpers under Node."""

from __future__ import annotations

import shutil
import subprocess
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from app.cache import DataKind
from app.cfbd.client import BULK_TIMEOUT, BUSY_WAIT_SECONDS, ENDPOINT_COOLDOWN, TIMEOUT
from app.cfbd.models import (
    AdjustedTeamMetrics,
    AdvancedSeasonStat,
    ConferenceSP,
    Game,
    KickerPAAR,
    PassingPlay,
    PlayerTransfer,
    PlayerWeightedEPA,
    PollWeek,
    RushingPlay,
    TeamCoreRating,
    TeamRecruitingRanking,
    TeamSP,
    TeamSRS,
    parse_records,
)
from app.services import depth2
from app.services.profiles import advanced_rows
from tests import league_facts as facts
from tests.conftest import PROJECT_ROOT, FakeCfbd, fixture_payload, route_depth2
from tests.test_phase8 import quiet_engine

NOW = datetime(2026, 9, 27, 14, 0, tzinfo=timezone.utc)
BUSY = httpx.Response(429, json={"message": "Too many concurrent requests for this endpoint."})


def setup(app, client: TestClient) -> dict:
    quiet_engine(app, client)
    clock = {"now": NOW, "sleeps": []}
    cfbd = app.state.cfbd
    cfbd._clock = lambda: clock["now"]

    async def sleep(seconds: float) -> None:
        clock["sleeps"].append(seconds)

    cfbd._sleep = sleep
    return clock


def test_a_busy_endpoint_is_retried_patiently_then_rests(app, client: TestClient, fake_cfbd: FakeCfbd):
    clock = setup(app, client)
    cfbd = app.state.cfbd
    fake_cfbd.route("/stats/season/advanced", json=[{"team": "Swampwater Tech"}])
    first = client.portal.call(lambda: cfbd.get("/stats/season/advanced", {"year": 2026}, kind=DataKind.SEASON_STATS))
    assert first.source == "live"
    clock["now"] += timedelta(hours=7)  # past the weekday lifetime
    fake_cfbd.route("/stats/season/advanced", sequence=[BUSY] * 8)
    stale = client.portal.call(lambda: cfbd.get("/stats/season/advanced", {"year": 2026}, kind=DataKind.SEASON_STATS))
    assert stale.stale and fake_cfbd.count("/stats/season/advanced") == 1 + 4
    assert all(s >= BUSY_WAIT_SECONDS for s in clock["sleeps"])  # every retry waited for CFBD to finish
    again = client.portal.call(lambda: cfbd.get("/stats/season/advanced", {"year": 2026}, kind=DataKind.SEASON_STATS))
    assert again.stale and fake_cfbd.count("/stats/season/advanced") == 5  # resting: the cached copy, no call
    clock["now"] += ENDPOINT_COOLDOWN + timedelta(seconds=1)
    fake_cfbd.route("/stats/season/advanced", json=[{"team": "Swampwater Tech", "season": 2026}])
    fresh = client.portal.call(lambda: cfbd.get("/stats/season/advanced", {"year": 2026}, kind=DataKind.SEASON_STATS))
    assert fresh.source == "live" and fake_cfbd.count("/stats/season/advanced") == 6
    assert "/stats/season/advanced" not in cfbd._busy_until


def test_ordinary_retries_stay_quick_and_live_calls_are_never_rested(app, client: TestClient, fake_cfbd: FakeCfbd):
    clock = setup(app, client)
    cfbd = app.state.cfbd
    fake_cfbd.route("/records", sequence=[httpx.Response(503, text="down"), httpx.Response(200, json=[])])
    client.portal.call(lambda: cfbd.get("/records", {"year": 2026}, kind=DataKind.SCHEDULE))
    assert clock["sleeps"] and max(clock["sleeps"]) < BUSY_WAIT_SECONDS  # a 503 is not "busy"
    clock["sleeps"].clear()
    fake_cfbd.route("/live/plays", sequence=[BUSY, BUSY])
    try:
        client.portal.call(lambda: cfbd.get("/live/plays", {"gameId": 1}, kind=DataKind.LIVE, live=True, use_cache=False))
    except Exception:  # noqa: BLE001 - the live call fails; what matters is how long it waited
        pass
    assert all(s < BUSY_WAIT_SECONDS for s in clock["sleeps"]) and "/live/plays" not in cfbd._busy_until


def test_timeouts_by_kind_of_call():
    assert BULK_TIMEOUT.read == 30.0 and TIMEOUT.read == 10.0


# --- the calculations (app/services/depth2.py) from the recorded answers -----------------------------------



def recs(name: str, model):
    return parse_records(model, fixture_payload(name), context=name).records


def test_sos_played_averages_rated_opponents_and_counts_fcs():
    g = lambda gid, home, away, done=True: Game.model_validate({"id": gid, "homeTeam": home, "awayTeam": away, "completed": done})  # noqa: E731
    sp = [TeamSP.model_validate({"team": t, "rating": r}) for t, r in (("A", 10.0), ("B", 20.0), ("C", -5.0))]
    games = [g(1, "A", "B"), g(2, "A", "C"), g(3, "A", "Tuskegee"), g(4, "B", "C", done=False)]
    out = depth2.sos_played(games, sp)
    assert out["A"] == {"rating": 7.5, "games": 2, "fcs": 1, "rank": 3, "of": 3}
    assert out["B"]["rating"] == 10.0 and out["B"]["rank"] == 1 and out["C"]["rating"] == 10.0
    assert depth2.sos_played([], sp) == {}


def test_the_resume_from_the_recorded_schedule():
    schedule = recs("games_team", Game)
    r = depth2.resume(schedule, schedule + recs("games_week", Game), "Swampwater Tech", recs("ratings_sp", TeamSP), recs("rankings", PollWeek))
    rec = facts.record("Swampwater Tech", "records_team")["total"]
    assert r["wins"] == rec["wins"] and r["losses"] == rec["losses"] and r["gamesCounted"] == rec["games"]
    played = [g for g in fixture_payload("games_team") if g["completed"]]
    expected = sum(g["homePostgameWinProbability"] if g["homeTeam"] == "Swampwater Tech" else g["awayPostgameWinProbability"] for g in played)
    assert r["expectedWins"] == pytest.approx(expected, abs=0.01)
    assert r["luck"] == pytest.approx(rec["wins"] - r["expectedWins"], abs=0.01)
    assert len(r["remaining"]["games"]) == sum(1 for g in fixture_payload("games_team") if not g["completed"]) and isinstance(r["remaining"]["averageSp"], float)
    assert all(set(p) == {"week", "seasonType", "ap", "coaches"} for p in r["polls"])


def test_the_portal_joins_by_name_and_destination():
    portal = [PlayerTransfer.model_validate(x) for x in (
        {"firstName": "Aaron", "lastName": "Hamilton", "origin": "Georgia Tech", "destination": "Swampwater Tech", "stars": 3, "rating": 0.89, "transferDate": "2026-01-06T00:00:00Z", "eligibility": "Immediate"},
        {"firstName": "Eric", "lastName": "Singleton Jr.", "origin": "Silver Dollar", "destination": "Swampwater Tech", "stars": 4, "transferDate": "2026-01-02T00:00:00Z"},
        {"firstName": "Aaron", "lastName": "Hamilton", "origin": "Swampwater Tech", "destination": "Troy", "transferDate": "2027-01-01T00:00:00Z"},
    )]
    idx = depth2.portal_index(portal, "Swampwater Tech")
    assert depth2.transfer_for(idx, "Aaron", "Hamilton") == {"from": "Georgia Tech", "stars": 3, "rating": 0.89, "date": "2026-01-06", "eligibility": "Immediate", "position": None}
    assert depth2.transfer_for(idx, "Eric", "Singleton") ["from"] == "Silver Dollar"  # the suffix does not matter
    assert depth2.transfer_for(idx, "Nobody", "Here") is None and depth2.transfer_for({}, None, None) is None
    real = depth2.portal_index(recs("player_portal", PlayerTransfer), "Swampwater Tech")
    assert len(real) >= 5  # a realistic portal class (public release Phase 7 rosters)


def test_class_rank():
    table = fixture_payload("recruiting_teams")
    row = next(r for r in table if r["team"] == "Swampwater Tech")
    assert depth2.class_rank(recs("recruiting_teams", TeamRecruitingRanking), "Swampwater Tech") == {"year": 2026, "rank": row["rank"], "points": row["points"], "of": len(table), "metric": "class:2026"}
    assert depth2.class_rank([], "Swampwater Tech") is None


def test_adjusted_metrics_boards_and_more_ratings():
    adjusted = recs("wepa_team_season_2025", AdjustedTeamMetrics)
    rows = depth2.adjusted_matchup(adjusted, "Swampwater Tech", "Diner Tech")
    assert rows[0]["key"] == "epa" and 1 <= rows[0]["themRank"] <= rows[0]["of"] == len(adjusted)
    assert depth2.adjusted_matchup([], "Swampwater Tech", "Diner Tech") == []
    boards = depth2.player_boards(recs("wepa_players_passing_2025", PlayerWeightedEPA), recs("wepa_players_rushing_2025", PlayerWeightedEPA), recs("wepa_players_kicking", KickerPAAR), team="Swampwater Tech", opponent="Sweet Tea State", conference="Biscuit Belt", fbs=None)
    assert [b["id"] for b in boards] == ["wepa:passing", "wepa:rushing", "paar:kicking"]
    national = boards[2]["national"]
    assert len(national) == 10 and all(national[i]["value"] >= national[i + 1]["value"] for i in range(9)) and national[0]["nationalRank"] == 1
    empty = depth2.player_boards([], [], [], team="Swampwater Tech", opponent=None, conference="Biscuit Belt", fbs=None)
    assert empty[0]["national"] == [] and "not published" in empty[0]["note"]
    more = depth2.more_ratings(recs("ratings_core", TeamCoreRating), recs("ratings_srs_2025", TeamSRS), adjusted)
    top = max(fixture_payload("ratings_core"), key=lambda r: r["overall"])["team"]
    assert more[top]["core"]["rank"] == 1 and more["Swampwater Tech"]["srs"]["value"] is not None
    conf = depth2.conference_rows(recs("ratings_sp_conferences", ConferenceSP))
    assert conf[0]["conference"] == "Biscuit Belt" and conf[0]["rank"] == 1 and len(conf) == 11


def test_opponent_tendencies_from_the_recorded_plays():
    t = depth2.tendencies(recs("rushing_plays_opponent", RushingPlay), recs("passing_plays_opponent", PassingPlay), "Diner Tech")
    games = {r["gameId"] for r in fixture_payload("rushing_plays_opponent")} | {r["gameId"] for r in fixture_payload("passing_plays_opponent")}
    assert t["games"] == len(games) and t["plays"] > 50 * len(games) and 0.3 < t["runRate"] < 0.8
    first = next(r for r in t["bySituation"] if r["key"] == "first")
    assert first["plays"] == first["run"]["plays"] + first["pass"]["plays"]
    assert [d["key"] for d in t["runDirection"]] == ["left", "middle", "right"] and sum(d["plays"] for d in t["runDirection"]) > 25 * len(games)
    assert {d["key"] for d in t["passDepth"]} <= {"short", "deep", "behind_los", "behind line of scrimmage"}
    none = depth2.tendencies([], [], "Sweet Tea State")
    assert none["plays"] == 0 and none["runRate"] is None
    other = depth2.tendencies(recs("rushing_plays_opponent", RushingPlay), [], "Arkansas-Pine Bluff")
    assert other["plays"] < t["plays"]  # the defense's side is its own offense, not Sweet Tea State's


def test_tendencies_count_sacks_as_passes_and_skip_kneels_and_spikes():
    rushes = [RushingPlay.model_validate({"playId": str(i), "offense": "M", "down": 3, "distance": 8, "startYardsToGoal": 50, "rushingYards": y, "isSack": sack, "isKneel": kneel, "success": False}) for i, (y, sack, kneel) in enumerate(((-7, True, False), (-1, False, True), (4, False, False)))]
    passes = [PassingPlay.model_validate({"playId": "p", "offense": "M", "down": 3, "distance": 8, "startYardsToGoal": 50, "totalYards": 0, "isSpike": True})]
    t = depth2.tendencies(rushes, passes, "M")
    third_long = next(r for r in t["bySituation"] if r["key"] == "third_long")
    assert third_long["plays"] == 2 and third_long["run"]["plays"] == 1 and third_long["pass"]["plays"] == 1


def test_the_advanced_box_score_normalizes_and_survives_junk():
    box = depth2.advanced_box(fixture_payload("game_box_advanced"))
    raw = fixture_payload("game_box_advanced")["teams"]
    pick = lambda block: next(row for row in raw[block] if row["team"] == "Swampwater Tech")  # noqa: E731
    assert set(box["teams"]) == {"Swampwater Tech", "Silver Dollar"}
    fl = box["teams"]["Swampwater Tech"]
    assert fl["plays"] == pick("ppa")["plays"] and fl["success"]["overall"]["quarter3"] == pick("successRates")["overall"]["quarter3"]
    assert fl["line"]["lineYards"] == pick("rushing")["lineYardsAverage"] and fl["scoring"]["opportunities"] == pick("scoringOpportunities")["opportunities"]
    assert box["players"][0]["totalPpa"] >= box["players"][-1]["totalPpa"] and box["home"] == "Silver Dollar"
    for junk in (None, [], "x", {}, {"teams": []}, {"teams": {"ppa": "x"}}):
        result = depth2.advanced_box(junk)
        assert result is None or result["teams"] == {}
    partial = depth2.advanced_box({"teams": {"ppa": [{"team": "A", "plays": "many", "overall": {"total": "x"}}, "junk"]}, "players": {"ppa": [{"player": 3}]}})
    assert partial["teams"]["A"]["plays"] is None and partial["teams"]["A"]["ppa"]["overall"]["total"] is None and partial["players"] == []


def test_the_advanced_rows_cover_every_area():
    rows = advanced_rows(recs("stats_season_advanced_fbs", AdvancedSeasonStat), "Swampwater Tech")
    assert len(rows) == 32 and {r["group"] for r in rows} == {"Overall", "Downs", "Run and pass", "Line play", "Havoc", "Finishing drives", "Field position"}
    assert all(r["value"] is not None and r["nationalRank"] is not None for r in rows)
    assert len({r["key"] for r in rows}) == 32
    empty = advanced_rows([], "Swampwater Tech")
    assert all(r["value"] is None and r["nationalRank"] is None for r in empty)


# --- the routes -------------------------------------------------------------------------------------------


def test_the_game_analytics_carry_the_advanced_box(app, client: TestClient, fake_cfbd: FakeCfbd):
    from tests.test_phase8 import route_analytics

    quiet_engine(app, client)
    route_analytics(fake_cfbd)
    route_depth2(fake_cfbd)
    data = client.get("/api/games/526000600/analytics").json()["data"]
    assert data["advancedBox"]["teams"]["Swampwater Tech"]["plays"] == next(r for r in fixture_payload("game_box_advanced")["teams"]["ppa"] if r["team"] == "Swampwater Tech")["plays"]


def test_the_season_carries_the_resume(app, client: TestClient, fake_cfbd: FakeCfbd):
    from tests.test_season import route_season

    quiet_engine(app, client)
    route_season(fake_cfbd)
    data = client.get("/api/season/overview").json()["data"]
    assert data["resume"]["wins"] == facts.record("Swampwater Tech", "records_team")["total"]["wins"] and data["resume"]["expectedWins"] is not None
    assert any(r["group"] == "Havoc" for r in data["advanced"]["rows"])


# --- the front end under Node --------------------------------------------------------------------------------

NODE13 = """import assert from "node:assert/strict";
const [d2Url, coverUrl, cardUrl, recUrl] = process.argv.slice(2);
const d2 = await import(d2Url);
const { openingLine } = await import(coverUrl);
const { transferText } = await import(cardUrl);
const { classRankText } = await import(recUrl);

const groups = d2.groupRows([{ group: "Havoc", key: "a" }, { group: "Overall", key: "b" }, { group: "Havoc", key: "c" }, null, { key: "d" }]);
assert.deepEqual([...groups.keys()], ["Havoc", "Overall", "Other"]);
assert.deepEqual(groups.get("Havoc").map((r) => r.key), ["a", "c"]);

assert.equal(openingLine(-1.5, 2.5, "Silver Dollar", "Swampwater Tech"), "Silver Dollar -1.5");
assert.equal(openingLine(3, 2.5, "Silver Dollar", "Swampwater Tech"), "Swampwater Tech -3");
assert.equal(openingLine(0, 2.5, "Silver Dollar", "Swampwater Tech"), "a pick'em");
assert.equal(openingLine(2.5, 2.5, "Silver Dollar", "Swampwater Tech"), null);
assert.equal(openingLine(null, 2.5, "Silver Dollar", "Swampwater Tech"), null);

assert.equal(transferText({ from: "Georgia Tech", stars: 3, rating: 0.89, date: "2026-01-06", eligibility: "Immediate" }), "From Georgia Tech, 3★ in the portal, 0.8900, entered 2026-01-06, immediate");
assert.equal(transferText({ from: "Silver Dollar" }), "From Silver Dollar");
for (const bad of [null, undefined, {}, { from: "" }, { from: 3 }, "x"]) assert.equal(transferText(bad), null);

assert.equal(classRankText({ rank: 17, of: 221, points: 250.98 }), " Class rank #17 of 221 nationally (250.98 points, 247Sports composite).");
assert.equal(classRankText({ rank: 3 }), " Class rank #3 nationally.");
for (const bad of [null, {}, { rank: "3" }, { rank: NaN }]) assert.equal(classRankText(bad), "");
console.log("ok");
"""


def test_phase13_front_end_helpers_under_node(tmp_path):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    script = tmp_path / "p13.mjs"
    script.write_text(NODE13, encoding="utf-8")
    js = PROJECT_ROOT / "static" / "js"
    args = [(js / "ui" / "depth2.js").as_uri(), (js / "ui" / "cover.js").as_uri(), (js / "ui" / "player-card.js").as_uri(), (js / "views" / "recruiting.js").as_uri()]
    result = subprocess.run([node, str(script), *args], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    assert result.returncode == 0 and "ok" in result.stdout, result.stderr[-1500:]
