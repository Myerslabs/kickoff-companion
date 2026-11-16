"""ENH-15 (owner 2026-10-23): the Series band shows every meeting, in columns past ten; Getting there for a game's stadium:
the way there in the device's own maps app, a QR code for the printed program, and the parking, tailgating, gates and the
rest from a Claude Code run per stadium (once a season, the primary teams' stadiums and this week's), printable alone."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.cfbd.models import Matchup
from app.services.claude_schedule import trip_slots
from app.services.program import ProgramService
from app.services.trip import destination, google_directions, shipped_trip, venue_block
from app.services.writing import build_prompt, read
from tests.fakedom import needs_node, run_scenario

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "cfbd"


@pytest.mark.skipif(not FIXTURE.is_dir(), reason="the CFBD recordings stay private; the public tree has none")
def test_the_series_carries_every_meeting():
    payload = json.loads((FIXTURE / "teams_matchup.json").read_text(encoding="utf-8"))["payload"]
    series = ProgramService._series(SimpleNamespace(team="Florida"), [Matchup.model_validate(payload)], "Ole Miss")
    assert len(series["games"]) == len(payload["games"]) > 10, "every meeting CFBD keeps"
    assert series["games"][0]["season"] >= series["games"][-1]["season"], "newest first"
    assert series["lastTen"] == series["games"][:10], "the ten the older pages read"
    assert ProgramService._series(SimpleNamespace(team="Florida"), [], "Ole Miss") is None


def test_a_venue_block_and_its_link():
    ever = {"id": 3712, "name": "EverBank Stadium", "city": "Jacksonville", "state": "FL", "zip": "32202", "latitude": 30.323889, "longitude": -81.6375}
    assert destination(ever) == "30.323889,-81.637500"
    assert destination({"name": "Some Field", "city": "Town", "state": "GA"}) == "Some Field, Town, GA", "no coordinates: the name and the town"
    assert destination({"latitude": True, "longitude": "x"}) is None and destination(None) is None
    assert google_directions(ever) == "https://www.google.com/maps/dir/?api=1&destination=30.323889,-81.637500"
    block = venue_block(ever)
    assert block["venueId"] == 3712 and block["name"] == "EverBank Stadium" and block["mapUrl"].startswith("https://www.google.com/maps/dir/")
    assert block["qr"].startswith("data:image/svg+xml"), "a QR code a second phone scans from the printed program"
    assert venue_block({"name": None}) is None, "nowhere to go: no block"


def test_a_shipped_stadium_reads_like_a_written_one(tmp_path: Path):
    path = tmp_path / "trips.json"
    path.write_text(json.dumps({"3712": {"name": "EverBank Stadium", "checkedAt": "2026-10-30", "address": "1 EverBank Stadium Dr", "parking": [{"name": "Lot J", "detail": "Pre-paid"}, "junk"], "bagPolicy": "Clear bags."}, "1": {"nothing": True}}), encoding="utf-8")
    got = shipped_trip(3712, path)
    assert got["shipped"] is True and got["writtenAt"] == "2026-10-30T12:00:00Z" and got["parking"] == [{"name": "Lot J", "detail": "Pre-paid"}]
    assert shipped_trip(1, path) is None, "a row with none of the parts is not usable"
    assert shipped_trip(2, path) is None and shipped_trip(3712, tmp_path / "missing.json") is None
    (tmp_path / "bad.json").write_text("{nope", encoding="utf-8")
    assert shipped_trip(3712, tmp_path / "bad.json") is None


def test_the_shipped_file_is_whole():
    raw = json.loads((ROOT / "app" / "facts" / "trips.json").read_text(encoding="utf-8"))
    for vid, row in raw.items():
        assert vid.isdigit() and row.get("name") and row.get("checkedAt")
        assert shipped_trip(int(vid)) is not None, vid


def test_the_trip_answer_and_prompt():
    answer, warnings, error = read("trip", '```json\n{"address": "1 Main St", "parking": [{"name": "Lot J", "detail": "$40"}, 7], "gates": "Two hours before kickoff."}\n```')
    assert error is None and answer["parking"] == [{"name": "Lot J", "detail": "$40"}] and warnings, "a damaged lot is left out, not the answer"
    assert read("trip", '{"sources": []}')[0] is None, "an answer with none of the parts is refused"
    prompt = build_prompt("trip", "Florida", {"venue": "EverBank Stadium", "game": {"home": "Florida", "away": "Georgia"}})
    assert "Getting there sheet for EverBank Stadium" in prompt and "gameDay" in prompt and "Never guess a price" in prompt


def test_the_trip_slots_once_a_season_a_stadium():
    tz = ZoneInfo("America/New_York")
    now = datetime(2026, 10, 30, 16, 0, tzinfo=timezone.utc)  # a Friday
    slots = trip_slots([3712, 3634, 3712, True, "x"], now, tz, 2026)
    assert [s.key for s in slots] == ["trip:2026:3712", "trip:2026:3634"], "each stadium once, the season in the key"
    assert all(s.kind == "trip" and s.at <= now < s.until for s in slots), "due from this week's Monday afternoon"
    assert slots[0].writing_key == "3712"


def test_the_trip_route_serves_the_shipped_stadium(app, client: TestClient, monkeypatch: pytest.MonkeyPatch):
    import app.api.writing as routes

    monkeypatch.setattr(routes, "shipped_trip", lambda key: {"address": "1 EverBank Stadium Dr", "shipped": True, "writtenAt": "2026-10-30T12:00:00Z"} if key == "3712" else None)
    got = client.get("/api/writing/trip/3712").json()["data"]
    assert got["written"]["shipped"] is True and got["written"]["address"].startswith("1 EverBank")
    assert client.get("/api/writing/trip/1").json()["data"]["written"] is None
    from app.services.writing import WritingStore

    settings = app.state.settings
    WritingStore(settings.data_dir, settings.season).save("trip", "3712", {"address": "Own run"})
    assert client.get("/api/writing/trip/3712").json()["data"]["written"]["address"] == "Own run", "the install's own run wins"


SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object \w+\]/;
const text = (node) => (node ? node.textContent : "");
const flush = async () => { for (let i = 0; i < 8; i += 1) await new Promise((resolve) => setImmediate(resolve)); };

scenarios.series = async () => {
  installWindow();
  const { seriesTable, seriesColumnCount, seriesRows } = await import(moduleUrl("ui/series.js"));
  const meet = (season, hs, as) => ({ season, homeTeam: season % 2 ? "Florida" : "Georgia", awayTeam: season % 2 ? "Georgia" : "Florida", homeScore: hs, awayScore: as, winner: hs > as ? (season % 2 ? "Florida" : "Georgia") : (season % 2 ? "Georgia" : "Florida") });
  const games = Array.from({ length: 27 }, (_, i) => meet(2025 - i, 20 + (i % 5), 17));
  assert.equal(seriesRows({ games }, "Florida").length, 27, "every meeting");
  assert.equal(seriesRows({ lastTen: games.slice(0, 10) }, "Florida").length, 10, "an old lock's ten");
  assert.equal(seriesColumnCount(800, 27), 2);
  assert.equal(seriesColumnCount(1500, 27), 3, "no more columns than tens of meetings");
  assert.equal(seriesColumnCount(1500, 100), 4, "four at most");
  assert.equal(seriesColumnCount(300, 27), 1, "a phone: one column");
  assert.equal(seriesColumnCount(1500, 8), 1, "ten or fewer: one table");
  const long = seriesTable({ games }, { us: "Florida", caption: "Series" });
  assert.ok(long.className.includes("series-cols"), "a long series in columns");
  const cols = long.querySelectorAll(".series-cols__col");
  assert.equal(cols.length, 2);
  assert.equal(text(cols[0].querySelector(".series-cols__span")), "2025 to 2012", "each column headed by its years, newest first");
  assert.equal(cols[0].querySelectorAll("tbody tr").length + cols[1].querySelectorAll("tbody tr").length, 27);
  const short = seriesTable({ games: games.slice(0, 6) }, { us: "Florida" });
  assert.ok(!short.className.includes("series-cols") && short.querySelectorAll("tbody tr").length === 6, "a short series stays one table");
  assert.ok(!RAW.test(text(long)));
};

scenarios.directions = async () => {
  installWindow();
  const { directionsHref, directionsLink } = await import(moduleUrl("ui/directions.js"));
  const { setMapApp, mapApp } = await import(moduleUrl("prefs.js"));
  const place = { name: "EverBank Stadium", city: "Jacksonville", state: "FL", latitude: 30.323889, longitude: -81.6375 };
  assert.equal(directionsHref(place, "google"), "https://www.google.com/maps/dir/?api=1&destination=30.323889%2C-81.637500");
  assert.ok(directionsHref(place, "apple").startsWith("https://maps.apple.com/?daddr=30.323889%2C-81.637500&q=EverBank"));
  assert.equal(directionsHref(place, "waze"), "https://waze.com/ul?ll=30.323889%2C-81.637500&navigate=yes");
  assert.equal(directionsHref({ name: "Some Field", city: "Town" }, "google"), "https://www.google.com/maps/dir/?api=1&destination=Some%20Field%2C%20Town", "no coordinates: the name");
  assert.equal(directionsHref({}, "google"), null);
  assert.equal(directionsHref(null), null);
  assert.equal(mapApp(), "google", "Google Maps when none is chosen");
  const link = directionsLink(place);
  assert.equal(link.tagName.toLowerCase(), "a");
  assert.equal(link.getAttribute("target"), "_blank");
  assert.equal(text(link), "Directions in Google Maps");
  setMapApp("waze");
  assert.ok(directionsLink(place).getAttribute("href").startsWith("https://waze.com/"), "the device's choice");
  assert.equal(setMapApp("nope"), "google", "an unknown choice is Google Maps");
  setMapApp("ask");
  const ask = directionsLink(place);
  const button = ask.querySelector("button");
  const apps = ask.querySelector(".directions__apps");
  assert.ok(button && apps.hasAttribute("hidden"), "Ask each time: a button, the three apps hidden");
  button.click();
  assert.equal(apps.hasAttribute("hidden"), false);
  assert.equal(apps.querySelectorAll("a").length, 3);
  assert.equal(directionsLink({}), null, "nowhere to go: no link");
  setMapApp("google");
};

scenarios.trip = async () => {
  installWindow();
  await useTeam();
  const { tripBand, PROGRAM_BANDS, coverConditions } = await import(moduleUrl("views/program.js"));
  const trip = { venueId: 3712, name: "EverBank Stadium", city: "Jacksonville", state: "FL", latitude: 30.323889, longitude: -81.6375, qr: "data:image/svg+xml;charset=utf-8,%3Csvg%3E%3C%2Fsvg%3E" };
  route("/api/writing/trip/3712", () => envelope({ kind: "trip", key: "3712", written: { address: "1 EverBank Stadium Dr, Jacksonville, FL 32202", parking: [{ name: "Lot J", detail: "Pre-paid only, opens 7 AM" }, { name: "" }], gates: "Gates open two hours before kickoff.", bagPolicy: "Clear bags 12 x 6 x 12.", tailgating: ["Tents allowed in Lot J."], gameDay: ["Kickoff 3:30 PM on ABC."], sources: [{ label: "Stadium", url: "https://example.com" }], shipped: true, writtenAt: "2026-10-30T12:00:00Z" }, running: false, commandFound: true }));
  route("/api/writing/trip/9", () => envelope({ kind: "trip", key: "9", written: null, running: false, commandFound: true }));
  const b = tripBand({ trip });
  document.body.append(b);
  await flush();
  const t = text(b);
  assert.ok(b.querySelector("#program-trip"), "its own id, for the flyout and the print");
  assert.ok(t.includes("EverBank Stadium") && t.includes("Jacksonville, FL"), t);
  assert.ok(b.querySelector(".trip__qr img").getAttribute("src").startsWith("data:image/svg+xml"), "the QR code");
  assert.ok(b.querySelector("a.directions").getAttribute("href").startsWith("https://www.google.com/maps/dir/"), "the way there");
  assert.ok(b.querySelectorAll("button").some((x) => text(x) === "Print Getting there"), "its own Print");
  assert.ok(t.includes("Lot J") && t.includes("Pre-paid only") && t.includes("Clear bags") && t.includes("Kickoff 3:30 PM"), t);
  assert.equal(b.querySelectorAll(".trip__lots li").length, 1, "a lot with no name is left out");
  assert.ok(t.includes("Researched for the app") && t.includes("Policies change"), t);
  assert.ok(!RAW.test(t), t);
  const empty = tripBand({ trip: { ...trip, venueId: 9, qr: "javascript:alert(1)" } });
  document.body.append(empty);
  await flush();
  assert.ok(text(empty).includes("once a season") && text(empty).includes("EverBank Stadium"), "the stadium and its link before the run");
  assert.equal(empty.querySelector(".trip__qr"), null, "only a data image for the QR code");
  assert.equal(tripBand({}), null, "no venue: no band");
  assert.equal(tripBand({ trip: { name: "x" } }), null);
  assert.ok(typeof PROGRAM_BANDS.trip === "function", "its own flyout from the menu");
  const cover = coverConditions({ game: { completed: false, venueDetail: { name: "EverBank Stadium" } }, trip, weather: null });
  assert.ok(cover.querySelector(".conditions__directions a.directions"), "Directions on the cover while the game is ahead");
  const after = coverConditions({ game: { completed: true, venueDetail: { name: "EverBank Stadium" } }, trip, weather: null });
  assert.equal(after?.querySelector?.(".conditions__directions") ?? null, null, "none once it is played");
};

scenarios.print = async () => {
  installWindow();
  const { printNow } = await import(moduleUrl("ui/print.js"));
  const band = document.createElement("section");
  document.body.append(band);
  let printed = 0;
  const win = { print: () => { printed += 1; }, addEventListener: () => {}, removeEventListener: () => {} };
  const done = printNow({ paper: "letter", orientation: "portrait", only: band }, document, win);
  assert.equal(printed, 1);
  assert.ok(document.body.classList.contains("print-only") && band.classList.contains("print-target"), "the band alone");
  done();
  assert.ok(!document.body.classList.contains("print-only") && !band.classList.contains("print-target"), "the page back after");
};
"""


@needs_node
@pytest.mark.parametrize("scenario", ["series", "directions", "trip", "print"])
def test_series_and_getting_there_in_a_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)
