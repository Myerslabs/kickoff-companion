"""The extra-call national lists (Phase 16, stream NV, owner answer 3): recruit ranks per class,
returning production and the blue-chip ratio. The recorded nationwide answers parse; junk records are
skipped and counted and never crash a list or leak NaN; a cold cache costs exactly the expected calls
through the guard and a warm one none for a week; a refused call serves the stale list or a 503;
years outside the five recorded classes are refused before any fetch; the blue-chip ratio agrees with
stats_extra's for Swampwater Tech and the opponent; every page payload that shows one of these numbers names
its list; and every list marks the next opponent."""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.cache import DataKind
from app.cfbd.models import Recruit, ReturningProduction, parse_records
from app.cfbd.quota import QuotaBlocked
from app.services import national_extra
from app.services.national import FAMILIES, METRICS, resolve, validate
from app.services.stats_extra import blue_chip
from tests.conftest import FakeCfbd, fixture_payload, load_fixture
from tests.test_national import route_all

SEASON = 2026
CLASSES = (2023, 2024, 2025, 2026, 2027)


RECORDED = object()


def route_national(fake: FakeCfbd, *, classes: dict[int, Any] | None = None, returning: Any = RECORDED) -> None:
    """The pages' recordings (route_all), plus the nationwide pulls for a request without a team."""
    route_all(fake)
    team_recruits = fake.routes["/recruiting/players"]
    team_returning = fake.routes["/player/returning"]

    def recruits(request: httpx.Request) -> httpx.Response:
        params = request.url.params
        if params.get("team"):
            return team_recruits(request)
        year = int(params.get("year") or 0)
        if classes is not None and year in classes:
            return nan_json(classes[year])
        return httpx.Response(200, json=fixture_payload(f"recruiting_players_national_{year}")) if year in CLASSES else httpx.Response(200, json=[])

    def returning_handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("team"):
            return team_returning(request)
        return httpx.Response(200, json=fixture_payload("player_returning_national")) if returning is RECORDED else nan_json(returning)

    fake.route("/recruiting/players", handler=recruits)
    fake.route("/player/returning", handler=returning_handler)


def nan_json(payload: Any) -> httpx.Response:
    return httpx.Response(200, content=json.dumps(payload).encode(), headers={"content-type": "application/json"})


def strict(text: str) -> Any:
    def refuse(token: str) -> Any:
        raise AssertionError(f"{token} in the answer")

    return json.loads(text, parse_constant=refuse)


def get(client: TestClient, path: str) -> dict[str, Any]:
    response = client.get(path)
    assert response.status_code == 200, (path, response.text[:300])
    return strict(response.text)


def national_calls(fake: FakeCfbd) -> int:
    """Calls to the two nationwide endpoints only (a request with a team is a page's own pull)."""
    return len([r for r in fake.requests if r.url.path in ("/recruiting/players", "/player/returning") and not r.url.params.get("team")])


@pytest.fixture
def fake_cfbd() -> FakeCfbd:
    """A Tier 2 key (30,000 calls), so the cache keeps each kind's own lifetime (a Free key stretches
    every lifetime four times; see CfbdClient.ttl_scale)."""
    fake = FakeCfbd()
    fake.route("/info", json={**fixture_payload("info"), "patronLevel": 2, "tierName": "Tier 2", "monthlyLimit": 30000, "remainingCalls": 30000})
    return fake


EXTRA_KEYS = [f"recruit:{y}" for y in CLASSES] + [national_extra.BLUECHIP_METRIC] + [f"returning:{k}" for k, *_ in national_extra.RETURNING]


# --- the registry ------------------------------------------------------------------------------------------------


def test_registry_and_year_limits():
    for key in EXTRA_KEYS:
        metric = resolve(key, SEASON)
        assert metric is not None and metric.key == key and metric.family in FAMILIES, key
        assert key not in METRICS  # the zero-call registry stays zero-call (test_national asserts it costs nothing)
    for bad in ("recruit:2022", "recruit:2028", "recruit:abc", "recruit:", "returning:nope", "bluechip:other", "bluechip", "returning:percentPPA:x"):
        assert resolve(bad, SEASON) is None, bad
    assert resolve("recruit:2026", SEASON).unit == "player" and resolve("recruit:2026", SEASON).scopes == ("national",)
    assert set(resolve("returning:usage", SEASON).scopes) == {"national", "conference"}
    assert isinstance(validate("recruit:2026", team=None, year="2025", scope=None, conf=None, season=SEASON), str)  # no other year
    assert national_extra.recruit_metric(2022, SEASON) is None and national_extra.recruit_metric(2027, SEASON) == "recruit:2027"
    assert national_extra.recruit_metric(True, SEASON) is None and national_extra.recruit_metric("2026", SEASON) is None
    assert set(national_extra.returning_metrics()) == {"percentPPA", "percentPassing", "percentReceiving", "percentRushing", "usage", "passingUsage", "receivingUsage", "rushingUsage", "totalPPA"}


def test_cache_kinds():
    """A class still signing is kept a week; signed classes and returning production a month."""
    assert national_extra.class_kind(2027, SEASON) is DataKind.RECRUITING
    assert all(national_extra.class_kind(y, SEASON) is DataKind.HISTORY for y in (2023, 2024, 2025, 2026))


@pytest.mark.parametrize("path", ["/api/national/recruit:2022", "/api/national/recruit:2028", "/api/national/recruit:2026?year=2025", "/api/national/recruit:2026?scope=conference", "/api/national/returning:nope", "/api/national/bluechip:ratio?year=2025", "/api/national/bluechip"])
def test_bad_requests_are_404_with_no_call(client: TestClient, fake_cfbd: FakeCfbd, path: str):
    route_national(fake_cfbd)
    before = fake_cfbd.count()
    response = client.get(path)
    assert response.status_code == 404 and fake_cfbd.count() == before


# --- the recordings -------------------------------------------------------------------------------------------------


def test_the_recordings_parse():
    for year in CLASSES:
        recorded = load_fixture(f"recruiting_players_national_{year}")
        assert recorded["params"] == {"year": year} and recorded["endpoint"] == "/recruiting/players"
        parsed = parse_records(Recruit, recorded["payload"], context="t")
        assert parsed.skipped == 0 and len(parsed.records) > 2500
    returning = load_fixture("player_returning_national")
    parsed = parse_records(ReturningProduction, returning["payload"], context="t")
    assert parsed.skipped == 0 and len(parsed.records) >= 130 and returning["params"] == {"year": SEASON}


def test_recruit_list_top_100_and_every_one_of_ours(client: TestClient, fake_cfbd: FakeCfbd):
    route_national(fake_cfbd)
    data = get(client, "/api/national/recruit:2026?team=Diner%20Tech")["data"]
    assert data["unit"] == "player" and data["family"] == "recruit" and data["format"] == "rating100" and data["rankSource"] == "cfbd"
    assert len(data["rows"]) == 100 and data["cut"] == 100 and [r["rank"] for r in data["rows"][:3]] == [1, 2, 3]
    swt_rows = [r for r in fixture_payload("recruiting_players_national_2026") if r.get("committedTo") == "Swampwater Tech" and isinstance(r.get("ranking"), int)]
    below = sorted(r["ranking"] for r in swt_rows if r["ranking"] > 100)
    assert [r["rank"] for r in data["beyond"] if r["isUs"]] == below and below
    assert all(r["isUs"] or r["isFocus"] for r in data["beyond"])
    assert data["us"]["rank"] == min(r["ranking"] for r in swt_rows) and data["us"]["player"]
    assert data["of"] == len([r for r in fixture_payload("recruiting_players_national_2026") if isinstance(r.get("ranking"), int)])
    first = data["rows"][0]
    top = min((r for r in fixture_payload("recruiting_players_national_2026") if isinstance(r.get("ranking"), int)), key=lambda r: r["ranking"])
    assert first["detail"]["stars"] == top["stars"] >= 4 and first["team"] and first["value"] <= 1 and "headshotUrl" not in first


def test_bluechip_agrees_with_stats_extra_for_us_and_the_opponent(client: TestClient, fake_cfbd: FakeCfbd):
    route_national(fake_cfbd)
    data = get(client, "/api/national/bluechip:ratio?team=Diner%20Tech")["data"]

    def team_level(names: list[str]) -> dict[str, Any]:
        return blue_chip({2023 + i: parse_records(Recruit, fixture_payload(n), context="t").records for i, n in enumerate(names)})

    swt = team_level(["recruiting_players_2023", "recruiting_players_2024", "recruiting_players_2025", "recruiting_players"])
    opponent = team_level([f"recruiting_players_opponent_{y}" for y in (2023, 2024, 2025, 2026)])
    assert data["us"]["value"] == swt["ratio"] and data["focus"]["value"] == opponent["ratio"]
    row = next(r for r in data["rows"] if r["team"] == "Swampwater Tech")
    assert row["detail"] == {"blueChips": swt["blueChips"], "signees": swt["signees"]}
    assert data["of"] <= 138 and all(r["value"] is not None for r in data["rows"])
    ranks = [r["rank"] for r in data["rows"]]
    assert ranks == sorted(ranks) and ranks[0] == 1
    conf = get(client, "/api/national/bluechip:ratio?scope=conference")["data"]
    assert conf["conference"] == "Biscuit Belt" and all(r["conference"] == "Biscuit Belt" and r["nationalRank"] for r in conf["rows"]) and conf["of"] == 16


def test_returning_list(client: TestClient, fake_cfbd: FakeCfbd):
    route_national(fake_cfbd)
    data = get(client, "/api/national/returning:percentPPA")["data"]
    recorded = {r["team"]: r["percentPPA"] for r in fixture_payload("player_returning_national")}
    assert data["us"]["value"] == pytest.approx(recorded["Swampwater Tech"], abs=1e-3) and data["us"]["rank"]
    assert data["rows"][0]["value"] == pytest.approx(max(v for v in recorded.values() if v is not None), abs=1e-3)
    assert data["label"] == "Returning production (PPA)" and data["format"] == "pct"
    total = get(client, "/api/national/returning:totalPPA?scope=conference")["data"]
    assert total["conference"] == "Biscuit Belt" and total["format"] == "1f"


def test_every_list_marks_the_next_opponent(client: TestClient, fake_cfbd: FakeCfbd):
    route_national(fake_cfbd)
    for path in ("/api/national/profile:ypp", "/api/national/bluechip:ratio", "/api/national/recruit:2026"):
        data = get(client, path)["data"]
        assert data["next"] == "Diner Tech", path
        marked = [r for r in data["rows"] + data["beyond"] if r["isNext"]]
        assert all(r["team"] == "Diner Tech" for r in marked), path
    assert any(r["isNext"] for r in get(client, "/api/national/profile:ypp")["data"]["rows"])


# --- calls and the guard ------------------------------------------------------------------------------------------


def test_cold_calls_then_warm_for_a_week(app, client: TestClient, fake_cfbd: FakeCfbd):
    route_national(fake_cfbd)
    base = datetime(2026, 9, 28, 16, 0, tzinfo=timezone.utc)
    app.state.cfbd._clock = lambda: base
    get(client, "/api/national/recruit:2026")
    assert national_calls(fake_cfbd) == 1
    get(client, "/api/national/bluechip:ratio")
    assert national_calls(fake_cfbd) == 4  # 2023, 2024, 2025 added; 2026 is shared
    get(client, "/api/national/returning:percentPPA")
    get(client, "/api/national/returning:usage?scope=conference")
    get(client, "/api/national/recruit:2027")
    get(client, "/api/national/recruit:2023")
    assert national_calls(fake_cfbd) == 6  # the whole set: five classes and returning production
    app.state.cfbd._clock = lambda: base + timedelta(days=6, hours=23)
    for key in EXTRA_KEYS:
        get(client, f"/api/national/{key}")
    assert national_calls(fake_cfbd) == 6  # warm within the week: nothing
    app.state.cfbd._clock = lambda: base + timedelta(days=8)
    for key in EXTRA_KEYS:
        get(client, f"/api/national/{key}")
    assert national_calls(fake_cfbd) == 7  # only the open class (2027) is asked again
    app.state.cfbd._clock = lambda: base + timedelta(days=31)
    get(client, "/api/national/bluechip:ratio")
    get(client, "/api/national/returning:percentPPA")
    assert national_calls(fake_cfbd) == 12  # a month on, the signed classes and returning production once each


def test_quota_blocked_serves_stale_or_503(app, client: TestClient, fake_cfbd: FakeCfbd, monkeypatch: pytest.MonkeyPatch):
    route_national(fake_cfbd)
    base = datetime(2026, 9, 28, 16, 0, tzinfo=timezone.utc)
    app.state.cfbd._clock = lambda: base
    fresh = get(client, "/api/national/returning:percentPPA")
    before = fake_cfbd.count()

    def refuse(**_: Any) -> Any:
        raise QuotaBlocked("CFBD quota exhausted: test")

    monkeypatch.setattr(app.state.cfbd.quota, "check", refuse)
    app.state.cfbd._clock = lambda: base + timedelta(days=40)  # every lifetime has passed
    body = get(client, "/api/national/returning:percentPPA")
    assert body["meta"]["stale"] is True and body["data"]["rows"] == fresh["data"]["rows"]
    assert body["data"]["parts"]["returningNational"]["status"] == "stale" and "quota" in body["data"]["parts"]["returningNational"]["error"]
    cold = client.get("/api/national/recruit:2025")  # never fetched: nothing to serve
    assert cold.status_code == 200 and cold.json()["data"]["parts"]["recruitsNational_2025"]["status"] == "error"
    assert fake_cfbd.count() == before  # the guard refused every call
    app.state.national.players_fetcher._memo.clear()
    blank = client.get("/api/national/recruit:2024")
    assert blank.status_code in (200, 503)


def test_quota_blocked_on_a_cold_cache_is_a_503(app, client: TestClient, fake_cfbd: FakeCfbd, monkeypatch: pytest.MonkeyPatch):
    route_national(fake_cfbd)

    def refuse(**_: Any) -> Any:
        raise QuotaBlocked("CFBD quota exhausted: test")

    before = fake_cfbd.count()
    monkeypatch.setattr(app.state.cfbd.quota, "check", refuse)
    for key, part in (("recruit:2026", "recruitsNational_2026"), ("bluechip:ratio", "recruitsNational_2023"), ("returning:percentPPA", "returningNational")):
        response = client.get(f"/api/national/{key}")
        if response.status_code == 200:  # the startup's schedule answer is cached: the list says which part failed
            data = response.json()["data"]
            assert data["rows"] == [] and data["parts"][part]["status"] == "error" and "quota" in data["parts"][part]["error"], key
        else:
            assert response.status_code == 503 and response.json()["errors"][0]["code"] == "upstream_unavailable", key
    assert fake_cfbd.count() == before
    app.state.cfbd.cache.clear()  # nothing cached at all: nothing to serve
    response = client.get("/api/national/recruit:2026")
    assert response.status_code == 503 and response.json()["errors"][0]["code"] == "upstream_unavailable"


def test_a_missing_class_leaves_the_ratio_empty_with_a_note(client: TestClient, fake_cfbd: FakeCfbd):
    route_national(fake_cfbd)
    original = fake_cfbd.routes["/recruiting/players"]
    fake_cfbd.route("/recruiting/players", handler=lambda r: httpx.Response(500, text="boom") if r.url.params.get("year") == "2024" and not r.url.params.get("team") else original(r))
    body = get(client, "/api/national/bluechip:ratio")
    assert body["data"]["rows"] == [] and "did not load" in body["data"]["note"]
    assert body["data"]["parts"]["recruitsNational_2024"]["status"] == "error"
    assert any(e["code"] == "part_unavailable" for e in body["errors"])


# --- malformed payloads -------------------------------------------------------------------------------------------


def test_junk_recruits_are_skipped_and_counted(client: TestClient, fake_cfbd: FakeCfbd):
    good = fixture_payload("recruiting_players_national_2026")[:150]
    junk = [
        {"id": "x1", "name": "No Rank", "committedTo": "Swampwater Tech", "stars": 4, "rating": 0.9},
        {"id": "x2", "name": "String Stars", "ranking": 7, "committedTo": "Swampwater Tech", "stars": "four", "rating": 0.95},
        {"id": "x3", "name": "Null Team", "ranking": 8, "committedTo": None, "stars": 3, "rating": float("nan")},
        {"id": "x4", "ranking": "9", "rating": "high"},
        {"name": "No Id", "ranking": 10},
        "junk",
        None,
        7,
    ]
    route_national(fake_cfbd, classes={2026: good + junk, 2025: {"message": "a dict, not a list"}, 2024: None})
    body = get(client, "/api/national/recruit:2026")
    data = body["data"]
    assert body["data"]["parts"]["recruitsNational_2026"]["skipped"] >= 5 and any(e["code"] == "records_skipped" for e in body["errors"])
    names = {r["player"] for r in data["rows"] + data["beyond"]}
    assert "No Rank" not in names and data["unranked"] >= 1
    for r in data["rows"] + data["beyond"]:
        assert isinstance(r["rank"], int) and (r["value"] is None or math.isfinite(r["value"]))
    for year in (2025, 2024):
        response = client.get(f"/api/national/recruit:{year}")
        assert response.status_code == 200 and strict(response.text)["data"]["rows"] == []


def test_junk_returning_production(client: TestClient, fake_cfbd: FakeCfbd):
    rows = [dict(r) for r in fixture_payload("player_returning_national")]
    swt = next(r for r in rows if r["team"] == "Swampwater Tech")
    swt["percentPPA"] = "x"
    junk = [{"team": None, "percentPPA": 0.5}, {"percentPPA": 0.9}, {"team": "Ghost U", "percentPPA": float("inf")}, "junk", None]
    route_national(fake_cfbd, returning=rows + junk)
    body = get(client, "/api/national/returning:percentPPA")
    data = body["data"]
    assert "Ghost U" not in {r["team"] for r in data["rows"]} and data["us"]["rank"] is None
    assert body["data"]["parts"]["returningNational"]["skipped"] >= 3


@pytest.mark.parametrize("payload", [{"message": "a dict"}, None, [], ["junk", 3]])
def test_returning_payload_shapes(client: TestClient, fake_cfbd: FakeCfbd, payload: Any):
    route_national(fake_cfbd, returning=payload)
    response = client.get("/api/national/returning:percentPPA")
    assert response.status_code == 200
    data = strict(response.text)["data"]
    assert data["rows"] == [] and data["us"]["rank"] is None


# --- the page payloads name their lists ------------------------------------------------------------------------------


def test_page_payloads_carry_the_extra_list_keys(client: TestClient, fake_cfbd: FakeCfbd):
    route_national(fake_cfbd)
    roster = get(client, "/api/roster")["data"]
    ranked = [p for p in roster["players"] if isinstance(p.get("recruitRank"), int)]
    assert ranked and roster["blueChip"]["metric"] == "bluechip:ratio"
    for p in ranked:
        assert p["recruitMetric"] == national_extra.recruit_metric(p["recruitClass"], SEASON)
    assert any(p["recruitMetric"] for p in ranked)
    recruiting = get(client, "/api/recruiting")["data"]
    commits = [c for block in recruiting["classes"] for c in block["commits"]]
    assert commits and all(c["metric"] == (f"recruit:{block['year']}" if isinstance(c["nationalRank"], int) else None) for block in recruiting["classes"] for c in block["commits"])
    program = get(client, "/api/program/next")["data"]
    for side in ("us", "them"):
        block = program["recruiting"][side]
        assert block["blueChip"]["metric"] == "bluechip:ratio"
        assert block["returning"]["metrics"] == national_extra.returning_metrics()
    player_id = next(p["playerId"] for p in ranked if p["recruitMetric"])
    card = get(client, f"/api/players/{player_id}")["data"]
    assert card["player"]["recruit"]["metric"] == national_extra.recruit_metric(card["player"]["recruit"]["year"], SEASON)
    keys = {p["recruitMetric"] for p in ranked if p["recruitMetric"]} | {c["metric"] for c in commits if c["metric"]} | {"bluechip:ratio"} | set(national_extra.returning_metrics().values())
    for key in sorted(keys):
        assert resolve(key, SEASON) is not None, key
        assert client.get(f"/api/national/{key}").status_code == 200, key


def test_matchup_rows_name_their_lists_and_logos_are_local(client: TestClient, fake_cfbd: FakeCfbd):
    route_national(fake_cfbd)
    fake_cfbd.fixture("/talent", "talent")
    body = client.get("/api/matchup?away=Diner%20Tech&home=Swampwater%20Tech")
    assert body.status_code == 200
    data = body.json()["data"]
    assert data["rows"] and all(resolve(r["metric"], SEASON) is not None for r in data["rows"])
    assert {r["metric"].split(":")[0] for r in data["rows"]} == {"profile", "advanced"}
    for side in ("away", "home"):
        logo = data[side]["logo"]
        assert logo is None or logo.startswith("/media/logo/")


# --- page chips: blue-chip and returning-production ranks on the pages (coordinator follow-up, decision 9) -----------

RETURNING_KEYS = [k for k, *_ in national_extra.RETURNING]


def list_rank(client: TestClient, metric: str, team: str) -> tuple[int | None, int | None, bool]:
    data = get(client, f"/api/national/{metric}")["data"]
    row = next((r for r in data["rows"] + data["beyond"] if r.get("team") == team), None)
    return (row["rank"] if row else None), data["of"], bool(row and row["tied"])


def assert_blue_chip_agrees(client: TestClient, block: dict[str, Any], team: str) -> None:
    rank, of, tied = list_rank(client, "bluechip:ratio", team)
    assert rank is not None, team
    assert (block["nationalRank"], block["nationalOf"], block["tied"]) == (rank, of, tied), team
    assert block["metric"] == "bluechip:ratio" and block["ratio"] is not None


def assert_returning_agrees(client: TestClient, block: dict[str, Any], team: str) -> None:
    assert set(block["ranks"]) == set(RETURNING_KEYS) and block["metrics"] == national_extra.returning_metrics()
    for key in RETURNING_KEYS:
        rank, of, tied = list_rank(client, f"returning:{key}", team)
        assert block["ranks"][key] == {"rank": rank, "of": of, "tied": tied}, (team, key)
    assert block["ranks"]["percentPPA"]["rank"] is not None, team


def test_page_chips_agree_with_their_lists(client: TestClient, fake_cfbd: FakeCfbd):
    route_national(fake_cfbd)
    program = get(client, "/api/program/next")["data"]
    for side, team in (("us", "Swampwater Tech"), ("them", "Diner Tech")):
        block = program["recruiting"][side]
        assert block["school"] == team
        assert_blue_chip_agrees(client, block["blueChip"], team)
        assert_returning_agrees(client, block["returning"], team)
    for team in ("Diner Tech", "Swampwater Tech"):
        page = get(client, f"/api/team/{team}")["data"]
        assert_blue_chip_agrees(client, page["recruiting"]["blueChip"], team)
        assert_returning_agrees(client, page["recruiting"]["returning"], team)
    roster = get(client, "/api/roster")["data"]
    assert_blue_chip_agrees(client, roster["blueChip"], "Swampwater Tech")
    assert program["recruiting"]["us"]["blueChip"]["nationalRank"] == roster["blueChip"]["nationalRank"]


def test_page_chips_cost_five_calls_cold_and_none_warm(app, client: TestClient, fake_cfbd: FakeCfbd):
    route_national(fake_cfbd)
    base = datetime.now(timezone.utc)
    app.state.cfbd._clock = lambda: base
    get(client, "/api/program/next")
    assert national_calls(fake_cfbd) == 5  # four signed classes and returning production
    get(client, "/api/team/Diner%20Tech")
    get(client, "/api/team/Swampwater Tech")
    get(client, "/api/roster")
    assert national_calls(fake_cfbd) == 5  # the other pages share the keys
    get(client, "/api/national/bluechip:ratio")
    for key in RETURNING_KEYS:
        get(client, f"/api/national/returning:{key}")
    assert national_calls(fake_cfbd) == 5  # and so do the lists
    app.state.cfbd._clock = lambda: base + timedelta(days=6, hours=23)
    get(client, "/api/program/next")
    get(client, "/api/team/Diner%20Tech")
    get(client, "/api/roster")
    assert national_calls(fake_cfbd) == 5  # warm for the week (the signed classes and returning are kept a month)
    app.state.cfbd._clock = lambda: base + timedelta(days=31)
    get(client, "/api/program/next")
    assert national_calls(fake_cfbd) == 10  # a month on: the five keys once more


def test_a_failed_pull_shows_the_value_without_a_rank(client: TestClient, fake_cfbd: FakeCfbd):
    route_national(fake_cfbd)
    classes = fake_cfbd.routes["/recruiting/players"]
    returning = fake_cfbd.routes["/player/returning"]
    fake_cfbd.route("/recruiting/players", handler=lambda r: classes(r) if r.url.params.get("team") or r.url.params.get("year") != "2024" else httpx.Response(500, text="boom"))
    fake_cfbd.route("/player/returning", handler=lambda r: returning(r) if r.url.params.get("team") else httpx.Response(503, text="down"))
    response = client.get("/api/program/next")
    assert response.status_code == 200
    body = strict(response.text)
    us = body["data"]["recruiting"]["us"]
    assert us["blueChip"]["ratio"] is not None and us["blueChip"]["nationalRank"] is None and us["blueChip"]["nationalOf"] is None
    assert us["returning"]["percentPPA"] is not None and all(r["rank"] is None and r["of"] is None for r in us["returning"]["ranks"].values())
    parts = body["data"]["parts"]
    assert parts["recruitsNational_2024"]["status"] == "error" and parts["returningNational"]["status"] == "error"
    assert {e["message"].split(":")[0] for e in body["errors"] if e["code"] == "part_unavailable"} >= {"recruitsNational_2024", "returningNational"}
    team = strict(client.get("/api/team/Diner%20Tech").text)["data"]["recruiting"]
    assert team["blueChip"]["nationalRank"] is None and team["blueChip"]["ratio"] is not None


def test_a_quota_refusal_shows_the_value_without_a_rank(app, client: TestClient, fake_cfbd: FakeCfbd, monkeypatch: pytest.MonkeyPatch):
    route_national(fake_cfbd)
    real_get = app.state.cfbd.get

    async def guarded(endpoint: str, params: dict[str, Any] | None = None, **kwargs: Any) -> Any:
        if endpoint in ("/recruiting/players", "/player/returning") and not (params or {}).get("team"):
            raise QuotaBlocked("CFBD quota at 95% of the monthly budget: only live-game calls are allowed until next month.")
        return await real_get(endpoint, params, **kwargs)

    monkeypatch.setattr(app.state.cfbd, "get", guarded)
    body = strict(client.get("/api/roster").text)
    assert body["data"]["blueChip"]["ratio"] is not None and body["data"]["blueChip"]["nationalRank"] is None
    assert "quota" in body["data"]["parts"]["recruitsNational_2026"]["error"]
    assert national_calls(fake_cfbd) == 0
    program = strict(client.get("/api/program/next").text)["data"]["recruiting"]["them"]
    assert program["blueChip"]["nationalRank"] is None and all(r["rank"] is None for r in program["returning"]["ranks"].values())


def test_malformed_pulls_never_break_a_page(client: TestClient, fake_cfbd: FakeCfbd):
    junk_class = fixture_payload("recruiting_players_national_2025")[:400] + [{"id": "j1", "committedTo": "Swampwater Tech", "stars": "five"}, {"committedTo": None}, "junk", None, 7, {"id": "j2", "committedTo": {"school": "x"}}]
    junk_returning = [{"team": "Swampwater Tech", "percentPPA": "x", "usage": float("nan")}, {"team": None}, {"percentPPA": 0.5}, "junk", None] + [dict(r) for r in fixture_payload("player_returning_national") if r["team"] != "Swampwater Tech"]
    route_national(fake_cfbd, classes={2025: junk_class, 2024: {"message": "a dict"}}, returning=junk_returning)
    response = client.get("/api/program/next")
    assert response.status_code == 200
    body = strict(response.text)
    us, them = body["data"]["recruiting"]["us"], body["data"]["recruiting"]["them"]
    assert us["returning"]["ranks"]["percentPPA"]["rank"] is None  # Swampwater Tech's figure is junk there: no rank, no crash
    assert them["returning"]["ranks"]["percentPPA"]["rank"] is not None
    assert body["data"]["parts"]["returningNational"]["skipped"] >= 3
    assert us["blueChip"]["ratio"] is not None
    page = strict(client.get("/api/team/Swampwater Tech").text)["data"]["recruiting"]
    assert page["returning"] is None or all(isinstance(r["tied"], bool) for r in page["returning"]["ranks"].values())


def test_page_ranks_unit():
    """PageRanks alone: the same tables as the lists, ties shared, a missing part leaves None."""
    from app.services.parts import Part

    def recruit(i: int, team: str, stars: int) -> Recruit:
        return Recruit.model_validate({"id": str(i), "committedTo": team, "stars": stars})

    years = national_extra.bluechip_years(SEASON)
    fetched = type("F", (), {"fetched_at": datetime.now(timezone.utc), "stale": False, "error": None})()
    classes = {y: [recruit(1, "A", 5), recruit(2, "B", 4), recruit(3, "C", 3)] for y in years}
    parts = {f"recruitsNational_{y}": Part(f"recruitsNational_{y}", classes[y], fetched) for y in years}
    ranks = national_extra.PageRanks(parts, SEASON, {"A", "B", "C", "D"})
    assert ranks.bluechip == {"A": {"rank": 1, "of": 3, "tied": True}, "B": {"rank": 1, "of": 3, "tied": True}, "C": {"rank": 3, "of": 3, "tied": False}}
    block = ranks.bluechip_block({"ratio": 1.0}, "D")
    assert block["nationalRank"] is None and block["metric"] == "bluechip:ratio"
    assert ranks.returning == {} and ranks.returning_block(None, "A") is None
    missing = national_extra.PageRanks({}, SEASON, None)
    assert missing.bluechip_block({"ratio": 0.5}, "A")["nationalRank"] is None
    assert missing.returning_block({"percentPPA": 0.5}, "A")["ranks"]["percentPPA"] == {"rank": None, "of": None, "tied": False}
