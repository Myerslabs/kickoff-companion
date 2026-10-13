"""Item 6, step I (owner 2026-10-11): the page check keeps the menu fixed. tools/page_check.py learns, under its existing flags:
with --interact, the Menu over a sheet (one sheet per page at 700 px and wider: the thing under a tap at the Menu's centre is
the Menu, the sheet starts under the top bar, a Menu tap closes it and opens the menu, and a sheet that opened by itself
fails), the board's way out (a mouse move shows the chip, which leads back to #live) and a file that does not arrive (the
loading screen says so beside a Reload within 12 s); with --rules, a player's name on two lines (the anchors' phone too); and
the routes the menu sweep found missing (an archived game, a glossary entry, #radio, an address that is no page).

The checks themselves run in headless Edge (tools/page_check.py); these tests hold their rules, their wiring and their
Python side with a scripted stand-in for the browser, and run the name rule's script in Node over a small fake page. Nothing
here starts a server or touches the network."""

from __future__ import annotations

import io
import json
import re
import subprocess
from pathlib import Path

import pytest

from tests.fakedom import NODE, needs_node
from tools import page_check as pc

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "static" / "js"


class FakeEdge:
    """A stand-in for page_check.Edge: scripted answers to run() by the script's own words, every call kept."""

    def __init__(self, answers: list[tuple[str, object]], size: tuple[int, int] = (1180, 820)) -> None:
        self.answers = answers  # (a phrase in the script, the answer or a list of answers given in turn)
        self.size = size
        self.errors: list[str] = []
        self.failing: tuple[str, ...] = ()
        self.failed: list[str] = []
        self.ran: list[str] = []
        self.loaded: list[str] = []
        self.moves: list[tuple[float, float]] = []
        self.taps: list[tuple[float, float]] = []
        self.calls: list[tuple[str, dict]] = []

    def run(self, expression: str) -> object:
        self.ran.append(expression)
        for phrase, answer in self.answers:
            if phrase in expression:
                if isinstance(answer, list):
                    return answer.pop(0) if len(answer) > 1 else answer[0]
                return answer
        raise AssertionError("no scripted answer for: " + expression[:120])

    def text_of(self, url: str, budget_ms: int) -> str:
        self.loaded.append(url)
        return "text"

    def move(self, x: float, y: float) -> None:
        self.moves.append((x, y))

    def tap(self, x: float, y: float) -> None:
        self.taps.append((x, y))

    def call(self, method: str, **params: object) -> dict:
        self.calls.append((method, params))
        if method == "Page.navigate" and "#program" in str(params.get("url")) and self.failing:
            self.failed.append(str(params["url"]).split("#")[0] + pc.BOOT_FILE)
        return {}

    def wrapped_names(self, expression: str = pc.PAGE_NAMES_JS) -> list[dict]:
        value = self.run(expression)
        return value if isinstance(value, list) else []


# --- the routes the sweep found missing --------------------------------------------------------------------------------------


def test_the_routes_the_menu_sweep_found_missing():
    assert pc.ROUTE_GROUPS["LIVE"] == ["archive={ARCHIVED}"]
    assert pc.ROUTE_GROUPS["DS"] == ["glossary=success-rate", "radio", "no-such-page"]
    for route in ("archive={ARCHIVED}", "glossary=success-rate", "radio", "no-such-page"):
        assert route in pc.ROUTES
    glossary = (JS / "glossary-data.js").read_text(encoding="utf-8")
    assert 'id: "success-rate",' in glossary, "the glossary route names a real entry"
    app = (JS / "app.js").read_text(encoding="utf-8")
    assert 'const VALID = new Set([...Object.keys(BUILT), ...Object.keys(LATER), "radio"]);' in app, "#radio is a route of its own"
    assert not re.search(r"^\s+\"?no-such-page\"?:", app, flags=re.M), "the unknown address is no page the router knows"


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"data": {"games": [{"gameId": 401}, {"gameId": 402}]}}, "401"),
        ({"data": {"games": [{"gameId": "526002084"}]}}, "526002084"),
        ({"data": {"games": [None, {"gameId": True}, {"gameId": -3}, {"gameId": "12a"}, {"gameId": 0}, {"gameId": 77}]}}, "77"),
        ({"data": {"games": []}}, None),
        ({"data": {"games": "nope"}}, None),
        ({"data": None}, None),
        ({"data": []}, None),
        ([], None),
        (None, None),
        ("text", None),
    ],
)
def test_the_archived_game_comes_from_the_archive_answer(payload, expected):
    assert pc.archived_game(payload) == expected


def test_an_archive_that_does_not_answer_falls_back(monkeypatch, capsys):
    def refused(url, timeout=None):
        raise OSError("connection refused")

    monkeypatch.setattr(pc.urllib.request, "urlopen", refused)
    assert pc.archive_route_value("http://127.0.0.1:1", "526002084") == "526002084"
    assert "the archive did not answer" in capsys.readouterr().out

    class Answer(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    seen = []
    monkeypatch.setattr(pc.urllib.request, "urlopen", lambda url, timeout=None: seen.append(url) or Answer(json.dumps({"data": {"games": [{"gameId": 9}]}}).encode()))
    assert pc.archive_route_value("http://host:1", "5") == "9" and seen == ["http://host:1/api/archive"]
    monkeypatch.setattr(pc.urllib.request, "urlopen", lambda url, timeout=None: Answer(b"not json"))
    assert pc.archive_route_value("http://host:1", "5") == "5", "a damaged answer is a fallback, not a crash"
    monkeypatch.setattr(pc.urllib.request, "urlopen", lambda url, timeout=None: Answer(json.dumps({"data": {"games": []}}).encode()))
    assert pc.archive_route_value("http://host:1", "5") == "5", "an empty archive: the finished game it does not hold"


def test_an_archived_games_drives_are_no_stretched_rows():
    """With a game in the archive the route reaches the drives and the play log: a drive's bar on the field is a drawing
    (content, not a gap), and a drive's head over its plays is a band head's pattern (split on purpose)."""
    assert "const DRAWN = '.tug, .ladder, .tt__pct, .wp__bar, .field';" in pc.STRETCH_JS
    assert "|play-drive)/;" in pc.STRETCH_JS
    css = (ROOT / "static" / "css" / "components.css").read_text(encoding="utf-8")
    assert ".drive { display: grid; grid-template-columns: 40px minmax(0, 1fr) auto;" in css, "the bar takes the middle of the row"
    assert ".play-drive { display: flex; justify-content: space-between;" in css


def test_the_archived_route_is_filled_once_the_server_answers():
    source = (ROOT / "tools" / "page_check.py").read_text(encoding="utf-8")
    main = source[source.index("def main("):]
    assert main.index("if not wait_for(base):") < main.index('if any("{ARCHIVED}" in route for route in args.routes):')
    assert 'archived = archive_route_value(base, values.get("LAST", ""))' in main
    assert pc.fill("archive={ARCHIVED}", {"US": "x"}) == "archive={ARCHIVED}", "the league's values leave it for later"


# --- the Menu over a sheet ---------------------------------------------------------------------------------------------------


def test_the_menu_over_a_sheet_rules():
    assert pc.SHEET_MIN_WIDTH == 700, "the iPad both ways and the big screen; a phone keeps full-screen sheets (owner answer 2)"
    assert pc.SHEET_KINDS == ("team", "chip", "player") and pc.SHEET_SKIP == ("board",)
    assert pc.OPEN_LAYERS == ".sheet-layer[data-modal], .card-layer[data-modal]"
    opener = pc.OPEN_SHEET_JS
    assert "main button.team-link[data-team]" in opener and "!isUs(b.dataset.team)" in opener, "another team's flyout, not our page"
    assert "main a[href^=\"#national\"]" in opener, "a rank chip's national list"
    assert "main tr[role=\"button\"], main button" in opener and "b.querySelector('.pn')" in opener, "a player row opens the card"
    assert "a sheet opened by itself" in opener, "nothing opens by itself (owner answer 3)"
    assert "for (const kind of ORDER)" in opener and "OPEN_LAYERS" not in opener
    spot = pc.MENU_SPOT_JS
    assert "document.elementFromPoint(x, y)" in spot and "hit === menu || menu.contains(hit)" in spot
    assert "'.topbar .menu-button'" in spot and "r.left + r.width / 2" in spot and "r.top + r.height / 2" in spot
    assert "panel.getBoundingClientRect().top < bar.bottom - 1" in spot, "the sheet starts under the top bar"
    after = pc.AFTER_MENU_JS
    assert ".drawer[open]" in after and "left the sheet open" in after and "Escape did not close the menu" in after
    assert "OPEN_LAYERS" not in after and json.dumps(pc.OPEN_LAYERS) in after


def test_the_sheet_kinds_take_turns():
    assert pc.sheet_order({}) == ["team", "chip", "player"]
    assert pc.sheet_order({"team": 1}) == ["chip", "player", "team"]
    assert pc.sheet_order({"team": 2, "chip": 1, "player": 1}) == ["chip", "player", "team"]
    assert pc.sheet_order({"team": 1, "chip": 1, "player": 1}) == ["team", "chip", "player"]


def test_the_sheet_check_taps_the_menu_where_it_is():
    edge = FakeEdge([
        ("a sheet opened by itself", {"kind": "chip", "what": "SP+ #5", "sheet": "SP+ overall"}),
        ("hit === menu || menu.contains(hit)", {"x": 1128.5, "y": 28, "problem": ""}),
        ("Escape did not close the menu", ""),
    ])
    used = {"team": 1}
    result = pc.check_sheet(edge, used, names=False)
    assert result == {"kind": "chip", "what": "SP+ #5", "sheet": "SP+ overall", "problems": [], "names": []}
    assert used == {"team": 1, "chip": 1}
    assert edge.taps == [(1128.5, 28.0)], "a real tap at the Menu's centre"
    assert '["chip", "player", "team"]' in edge.ran[0], "the kind opened least so far is tried first"
    assert len(edge.ran) == 3, "no names read without --rules"


def test_the_sheet_check_says_what_covers_the_menu():
    edge = FakeEdge([
        ("a sheet opened by itself", {"kind": "team", "what": "Red Clay", "sheet": "Red Clay"}),
        ("hit === menu || menu.contains(hit)", {"x": 10, "y": 10, "problem": 'the Menu is covered by button.side-sheet__close in div.sheet-layer "Red Clay"'}),
    ])
    result = pc.check_sheet(edge, {}, names=False)
    assert result["problems"] == ['the Menu is covered by button.side-sheet__close in div.sheet-layer "Red Clay"']
    assert edge.taps == [], "no tap where the Menu is not"


def test_the_sheet_check_reads_the_sheets_names_with_rules():
    edge = FakeEdge([
        ("a sheet opened by itself", {"kind": "team", "what": "Red Clay", "sheet": "Red Clay"}),
        ("!document.querySelector(\".sheet-layer[data-modal] .skel, .card-layer[data-modal] .skel\")", True),
        ("createTreeWalker", [[{"where": "sheet #team-roster", "element": "table.stat-table", "count": 1, "lines": 2, "sample": "Brackwater-Fennimore"}]]),  # one answer, a list
        ("hit === menu || menu.contains(hit)", {"x": 1, "y": 1, "problem": ""}),
        ("Escape did not close the menu", "a tap on the Menu did not open the menu"),
    ])
    result = pc.check_sheet(edge, {}, names=True)
    assert result["names"][0]["sample"] == "Brackwater-Fennimore"
    assert json.dumps(pc.OPEN_LAYERS) in pc.LAYER_NAMES_JS and edge.ran[2] == pc.LAYER_NAMES_JS
    assert result["problems"] == ["a tap on the Menu did not open the menu"]


@pytest.mark.parametrize(
    ("opened", "problem"),
    [
        ({"kind": None, "problem": "a sheet opened by itself: Not loaded yet"}, "a sheet opened by itself: Not loaded yet"),
        (None, "the sheet check could not run"),
    ],
)
def test_the_sheet_check_fails_without_a_menu_tap(opened, problem):
    edge = FakeEdge([("a sheet opened by itself", opened)])
    edge.errors.append("TypeError: boom")
    result = pc.check_sheet(edge, {}, names=False)
    assert result["problems"] == [problem] and edge.taps == []


def test_a_page_with_no_trigger_is_no_failure(capsys):
    edge = FakeEdge([("a sheet opened by itself", {"kind": None, "left": "#team=Swampwater%20Tech"})])
    result = pc.check_sheet(edge, {}, names=False)
    assert result["kind"] is None and result["problems"] == []
    assert pc.report_sheets([("setup", result), ("season", {**result, "kind": "team", "what": "Red Clay", "sheet": "Red Clay"})], 1180) == 0
    out = capsys.readouterr().out
    assert "  ok interaction: the Menu over a sheet (1 sheet(s) on 2 page(s): 1 team, 0 chip, 0 player; 1 page(s) with no trigger)" in out


def test_the_sheet_report(capsys):
    assert pc.report_sheets([], 390) == 0
    assert "not checked below 700 px (a phone keeps full-screen sheets)" in capsys.readouterr().out
    bad = {"kind": "player", "what": "Keegan Crawford", "sheet": "player card", "problems": ["the Menu is off the screen (its centre at 1200, 28)"], "names": []}
    assert pc.report_sheets([("leaders", bad)], 820) == 1
    out = capsys.readouterr().out
    assert "FAIL interaction: the Menu over a sheet (1 of 1 page(s))" in out
    assert "#leaders (player 'Keegan Crawford', 'player card'): the Menu is off the screen" in out


# --- the board's way out -----------------------------------------------------------------------------------------------------


def test_the_board_check_rules():
    reveal = re.search(r"export const REVEAL_MS = (\d+);", (JS / "views" / "board.js").read_text(encoding="utf-8"))
    assert reveal and pc.BOARD_REVEAL_S * 1000 > int(reveal.group(1)), "the press comes after the reveal guard"
    rest = pc.BOARD_REST_JS
    assert ".board-exit__leave" in rest and "board-mode" in rest and "opacity) < 0.05" in rest and "never hides" in rest
    shown = pc.BOARD_SHOWN_JS
    assert "opacity) > 0.95" in shown and "r.width < 43.5 || r.height < 43.5" in shown and "document.elementFromPoint(x, y)" in shown
    assert "cursor === 'none'" in shown and "off the screen" in shown
    left = pc.BOARD_LEFT_JS
    assert "location.hash === '#live'" in left and "!document.body.classList.contains('board-mode')" in left and ".topbar .menu-button" in left
    board = (JS / "views" / "board.js").read_text(encoding="utf-8")
    assert 'class: "btn board-exit__leave"' in board, "the check finds the chip by its class"


def test_the_board_check_goes_in_both_ways_and_leaves_by_the_chip():
    edge = FakeEdge([
        ("location.hash = 'board'", True),
        ("never hides", ""),
        ("mouse pointer stays hidden", {"x": 96, "y": 1040, "size": "156x44", "words": "Leave big screen", "problem": ""}),
        ("the chip did not lead back to In Game", ""),
    ], size=(1920, 1080))
    problems, seen = pc.check_board(edge, "http://h:1", 15000)
    assert problems == [] and seen == "'Leave big screen', 156x44"
    assert edge.loaded == ["http://h:1/#live", "http://h:1/#board"], "from In Game, then opened straight at the board"
    assert len(edge.moves) == 4 and edge.moves[0] == (960, 540), "a real mouse move wakes it, each way"
    assert edge.taps == [(96.0, 1040.0), (96.0, 1040.0)]


def test_the_board_check_names_the_way_that_failed():
    edge = FakeEdge([
        ("location.hash = 'board'", True),
        ("never hides", ["", 'the board has no "Leave big screen" chip']),
        ("mouse pointer stays hidden", {"x": 1, "y": 1, "problem": "a mouse move did not show the chip"}),
    ])
    problems, seen = pc.check_board(edge, "http://h:1", 15000)
    assert problems == ["from In Game: a mouse move did not show the chip", 'opened straight at #board: the board has no "Leave big screen" chip']
    assert seen == "" and edge.taps == []


# --- a file that does not arrive ---------------------------------------------------------------------------------------------


def test_the_failed_file_check_rules():
    assert pc.BOOT_LIMIT_S == 12.0 and pc.BOOT_FILE == "static/js/ui/dom.js"
    assert (ROOT / pc.BOOT_FILE).is_file(), "a file every page imports"
    boot = pc.BOOT_JS
    assert "document.getElementById('boot-failed')" in boot and "document.getElementById('boot-pill')" in boot
    assert r"/\breload\b/i" in boot and "document.elementFromPoint(" in boot and "r.height >= 43.5" in boot
    assert "ok: !drawn && said && Boolean(reload) && reload.tall" in boot
    index = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    assert 'id="boot-failed"' in index and 'id="boot-pill"' in index and '<button class="btn boot-reload" type="button"' in index and ">Reload</button>" in index


def test_the_failed_file_check_turns_the_failure_off_again():
    edge = FakeEdge([
        ("reload.tall", [{"drawn": False, "said": False, "pill": "Loading", "reload": None, "ok": False}, {"drawn": False, "said": True, "pill": "Could not load", "reload": {"size": "82x44", "tall": True, "where": "the top bar"}, "ok": True}]),
        ("Boolean(document.querySelector('.topbar .menu-button'))", True),
    ])
    edge.errors.append("earlier error")
    problems, seen = pc.check_boot(edge, "http://h:1", 15000)
    assert problems == [] and seen.startswith("static/js/ui/dom.js failed: 'Could not load' and Reload (82x44, in the top bar) at ")
    methods = [m for m, _p in edge.calls]
    assert methods[:3] == ["Network.enable", "Network.setCacheDisabled", "Fetch.enable"]
    assert methods[-3:] == ["Fetch.disable", "Network.setCacheDisabled", "Network.disable"]
    assert dict(edge.calls[2][1]) == {"patterns": [{"urlPattern": "*/static/js/ui/dom.js*", "requestStage": "Request"}]}
    assert edge.calls[-2][1] == {"cacheDisabled": False} and edge.failing == ()
    assert edge.loaded == ["http://h:1/#program"], "then the file arrives again and the app must start"
    assert edge.errors == ["earlier error"], "the failed file's own errors are the point, not a failure"


def test_the_failed_file_check_says_what_went_wrong(monkeypatch):
    monkeypatch.setattr(pc, "BOOT_LIMIT_S", 0.3)
    monkeypatch.setattr(pc.time, "sleep", lambda s: None)
    edge = FakeEdge([
        ("reload.tall", {"drawn": False, "said": True, "pill": "Could not load", "reload": None, "ok": False}),
        ("Boolean(document.querySelector('.topbar .menu-button'))", False),
    ])
    problems, _seen = pc.check_boot(edge, "http://h:1", 15000)
    assert problems[0] == "no Reload within 0 s of static/js/ui/dom.js failing: no Reload on screen with nothing over it (the pill reads 'Could not load')"
    assert problems[1] == "once static/js/ui/dom.js arrived again the app did not start"
    short = FakeEdge([
        ("reload.tall", {"drawn": False, "said": True, "pill": "Could not load", "reload": {"size": "82x30", "tall": False, "where": "the page"}, "ok": False}),
        ("Boolean(document.querySelector('.topbar .menu-button'))", True),
    ])
    assert pc.check_boot(short, "http://h:1", 15000)[0] == ["no Reload within 0 s of static/js/ui/dom.js failing: its Reload is 82x30, under 44 px (the pill reads 'Could not load')"]
    started = FakeEdge([
        ("reload.tall", {"drawn": True, "said": False, "pill": "", "reload": None, "ok": False}),
        ("Boolean(document.querySelector('.topbar .menu-button'))", True),
    ])
    assert pc.check_boot(started, "http://h:1", 15000)[0] == ["the app started although static/js/ui/dom.js failed"]
    never = FakeEdge([("reload.tall", {"drawn": True, "ok": False}), ("Boolean(document.querySelector('.topbar .menu-button'))", True)])
    never.call = lambda method, **params: {}  # the page never asked for the file
    assert pc.check_boot(never, "http://h:1", 15000)[0] == ["static/js/ui/dom.js was never asked for, so it could not be failed (the check needs the cache off)"]


class FakeSocket:
    def __init__(self, incoming: list[dict]) -> None:
        self.incoming = [json.dumps(m) for m in incoming]
        self.sent: list[dict] = []

    def send(self, text: str) -> None:
        self.sent.append(json.loads(text))

    def recv(self, timeout: float | None = None) -> str:
        return self.incoming.pop(0)


def test_edge_fails_the_paused_file_and_lets_the_rest_through():
    edge = object.__new__(pc.Edge)
    edge.next_id = 0
    edge.errors = []
    edge.failing = ("/static/js/ui/dom.js",)
    edge.failed = []
    paused = lambda rid, url: {"method": "Fetch.requestPaused", "params": {"requestId": rid, "request": {"url": url}}}  # noqa: E731
    edge.ws = FakeSocket([
        paused("r1", "http://h:1/static/js/ui/dom.js"),
        paused("r2", "http://h:1/static/js/app.js"),
        {"method": "Fetch.requestPaused", "params": {"requestId": None}},
        {"id": 2, "result": {}},  # the answer to failRequest, passed over
        {"id": 1, "result": {"result": {"value": 7}}},
    ])
    assert edge.call("Runtime.evaluate", expression="7") == {"result": {"value": 7}}
    sent = edge.ws.sent
    assert sent[0]["method"] == "Runtime.evaluate"
    assert sent[1] == {"id": 2, "method": "Fetch.failRequest", "params": {"requestId": "r1", "errorReason": "ConnectionReset"}}
    assert sent[2] == {"id": 3, "method": "Fetch.continueRequest", "params": {"requestId": "r2"}}
    assert len(sent) == 3, "a paused request with no id is left alone"
    assert edge.failed == ["http://h:1/static/js/ui/dom.js"]


def test_edge_presses_with_real_mouse_events():
    edge = object.__new__(pc.Edge)
    seen = []
    edge.call = lambda method, **params: seen.append((method, params)) or {}
    edge.tap(10.5, 20)
    assert [p["type"] for _m, p in seen] == ["mouseMoved", "mousePressed", "mouseReleased"]
    assert all(m == "Input.dispatchMouseEvent" and p["x"] == 10.5 and p["y"] == 20 for m, p in seen)
    assert seen[1][1]["button"] == "left" and seen[1][1]["clickCount"] == 1


# --- a player's name on one line ---------------------------------------------------------------------------------------------


NAMES_PAGE_JS = r"""
import { readFileSync } from "node:fs";
const SOURCE = readFileSync(process.argv[2], "utf8");
class Text { constructor(text, rects) { this.nodeType = 3; this.textContent = text; this.rects = rects; this.parentElement = null; } }
class Element {
  constructor(tag, { cls = "", id = "", modal = false, display = "inline", rect = { width: 80, height: 18 } } = {}, kids = []) {
    this.tagName = tag.toUpperCase(); this.className = cls; this.id = id; this.modal = modal; this.display = display; this.rect = rect;
    this.children = []; this.nodes = []; this.parentElement = null;
    for (const kid of kids) { kid.parentElement = this; this.nodes.push(kid); if (kid instanceof Element) this.children.push(kid); }
  }
  get textContent() { return this.nodes.map((n) => n.textContent).join(""); }
  getBoundingClientRect() { return this.rect; }
  getAttribute(name) { return name === "title" ? null : null; }
  matches(selector) {
    return selector.split(",").map((s) => s.trim()).some((s) => {
      if (s.startsWith(".")) return this.className.split(/\s+/).includes(s.slice(1));
      if (s === "[id]") return Boolean(this.id);
      if (s === "[data-modal]") return this.modal;
      if (s === '[class*="card"]') return this.className.includes("card");
      return this.tagName.toLowerCase() === s;
    });
  }
  closest(selector) { for (let el = this; el; el = el.parentElement) if (el.matches(selector)) return el; return null; }
  *walk() { for (const kid of this.children) { yield kid; yield* kid.walk(); } }
  querySelectorAll(selector) { return [...this.walk()].filter((el) => el.matches(selector)); }
}
const text = (words, lines = 1) => new Text(words, Array.from({ length: lines }, (_, i) => ({ top: 100 + i * 20, bottom: 118 + i * 20, width: 40, height: 18 })));
// a drawn name: the screen reader's copy (on three lines: never counted), the forms (the ones not shown on two lines: never counted)
const pn = (forms, shown, lines = 1, extra = {}) => new Element("span", { cls: "pn", ...extra }, [
  new Element("span", { cls: "sr-only" }, [text(forms.full, 3)]),
  ...Object.entries(forms).map(([k, words]) => new Element("span", { cls: `pn__f pn__f--${k}`, display: k === shown ? "inline" : "none" }, [text(words, k === shown ? lines : 2)])),
]);
const one = pn({ full: "Keegan Crawford", initial: "K.\u00a0Crawford" }, "initial");
const two = pn({ full: "Wexley Brackwater-Fennimore", initial: "W.\u00a0Brackwater-Fennimore" }, "initial", 2);
const hidden = pn({ full: "Hidden Player", initial: "H.\u00a0Player" }, "initial", 2, { display: "none" });
const plain = new Element("span", { cls: "pn" }, [text("Pemberly", 2)]);
const table = new Element("table", { cls: "stat-table stat-table--compact" }, [new Element("td", {}, [one]), new Element("td", {}, [two]), new Element("td", {}, [hidden])]);
const card = new Element("div", { cls: "leader-card" }, [plain]);
const body = new Element("body", {}, [new Element("section", { id: "leaders-passing" }, [table]), new Element("div", { modal: true }, [card])]);
globalThis.NodeFilter = { SHOW_TEXT: 4 };
globalThis.getComputedStyle = (el) => ({ display: el.display, visibility: "visible" });
globalThis.document = {
  querySelectorAll: (selector) => (selector === "body" ? [body] : body.querySelectorAll(selector)),
  createTreeWalker(root) {
    const texts = [];
    const visit = (el) => { for (const n of el.nodes) { if (n instanceof Text) { n.parentElement = el; texts.push(n); } else visit(n); } };
    visit(root);
    let at = -1;
    return { get currentNode() { return texts[at]; }, nextNode() { at += 1; return at < texts.length; } };
  },
  createRange() { let node = null; return { selectNodeContents(n) { node = n; }, getClientRects() { return node.rects; } }; },
};
const found = eval(SOURCE);
console.log(JSON.stringify(found));
"""


@needs_node
def test_the_name_rule_counts_the_lines_a_shown_name_takes(tmp_path):
    script = tmp_path / "names.mjs"
    script.write_text(NAMES_PAGE_JS, encoding="utf-8")
    source = tmp_path / "names.js"
    source.write_text(pc.PAGE_NAMES_JS, encoding="utf-8")
    result = subprocess.run([NODE, str(script), str(source)], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert result.returncode == 0, result.stderr
    found = json.loads(result.stdout)
    assert found == [
        {"where": "#leaders-passing", "element": "table.stat-table.stat-table--compact", "count": 1, "lines": 2, "sample": "W. Brackwater-Fennimore"},
        {"where": "sheet page", "element": "div.leader-card", "count": 1, "lines": 2, "sample": "Pemberly"},
    ], "the one-line name, the screen reader's copy, the forms not shown and a hidden name never count"


def test_the_name_rule_reads_every_drawn_name():
    names = pc.NAMES_JS
    assert "root.querySelectorAll('.pn')" in names and "parent.closest('.sr-only')" in names and "range.getClientRects()" in names
    assert "if (lines < 2) continue;" in names
    assert pc.PAGE_NAMES_JS == names.replace("ROOTS", '"body"') and pc.LAYER_NAMES_JS == names.replace("ROOTS", json.dumps(pc.OPEN_LAYERS))
    css = (ROOT / "static" / "css" / "components.css").read_text(encoding="utf-8")
    assert ".pn { white-space: nowrap; }" in css, "the rule the check holds the pages to"


def test_main_runs_the_new_checks_under_the_old_flags():
    source = (ROOT / "tools" / "page_check.py").read_text(encoding="utf-8")
    main = source[source.index("def main("):]
    assert "check_names = args.rules if names is None else names" in main
    assert "for row in browser.wrapped_names():" in main and 'print("No player name on two lines.")' in main
    assert "menu_spot = args.interact and args.size[0] >= SHEET_MIN_WIDTH" in main
    assert "sheet = check_sheet(browser, used, check_names)" in main and "not in SHEET_SKIP" in main
    flows = main[main.index("if args.interact:\n                    failures += run_flows"):]
    assert "failures += report_sheets(sheets, args.size[0])" in flows
    assert "failures += report(\"the board's way out\", *check_board(browser, base, args.budget))" in flows
    assert 'failures += report("a file that does not arrive", *check_boot(browser, base, args.budget))' in flows
    doc = pc.__doc__
    for words in ("Since item 6 (owner 2026-10-11) --interact also runs:", "the Menu over a sheet:", "the board's way out:", "a file that does not arrive:", "player's name on two lines", "the phone is held to the names too", "#archive=<id>"):
        assert words in doc, words


def test_the_anchors_hold_the_phone_to_the_names(monkeypatch, capsys):
    real = pc.main
    calls = []
    monkeypatch.setattr(pc, "main", lambda argv, names=None: calls.append((argv, names)) or 0)
    # the tablet lock (owner 2026-10-13): the iPad both ways, the phone, then the board alone on the big screen
    assert real(["--anchors", "--rules", "--scroll", "--interact"]) == 0
    assert [a[-1] for a, _n in calls] == ["1180x820", "820x1180", "390x844", "1920x1080"]
    assert all("--rules" in a and "--interact" in a and n is None for a, n in calls[:2])
    phone, names = calls[2]
    assert "--rules" not in phone and "--interact" not in phone and "--scroll" in phone and names is True
    big, big_names = calls[3]
    assert "--board" in big and "--rules" in big and "--interact" in big and "--scroll" not in big and "--layout" not in big and big_names is None
    calls.clear()
    real(["--anchors", "--rules"])
    assert len(calls) == 4 and calls[2][1] is True and "--scroll" not in calls[2][0], "--rules takes the phone for the names"
    calls.clear()
    real(["--anchors", "--layout"])
    assert len(calls) == 4 and "--layout" not in calls[3][0], "the phone and the board always run; the board skips --layout"
    calls.clear()
    real(["--anchors", "--scroll"])
    assert calls[2][1] is False, "--scroll alone: the phone's scroll rule only"
    out = capsys.readouterr().out
    assert "== phone ==" in out and "== 1080p screen, the board ==" in out


def test_the_report_survives_a_character_the_code_page_lacks():
    """A stretched row's sample is the page's own words; a redirected report on Windows is cp1252, which has no minus sign
    (U+2212): the report prints "?" instead of stopping the check with a UnicodeEncodeError."""
    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding="cp1252")
    pc.printable(stream)
    stream.write("gap 637 px  e.g. SWT \u2212 BLUE")
    stream.flush()
    assert raw.getvalue() == b"gap 637 px  e.g. SWT ? BLUE"
    pc.printable(object())  # no reconfigure: left alone
    source = (ROOT / "tools" / "page_check.py").read_text(encoding="utf-8")
    assert source[source.index("def main("):].split("\n")[2].strip() == "printable(sys.stdout)"
