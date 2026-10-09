"""Open every page of the app with real data in headless Edge and fail if any shows the words
undefined, null, NaN, Infinity or [object Object] (Phase 15, the design rule "a missing value renders
as a dash").

    .\\.venv\\Scripts\\python tools\\page_check.py            start the simulator, check every page, stop
    .\\.venv\\Scripts\\python tools\\page_check.py --url http://127.0.0.1:8650   check a server already running
    .\\.venv\\Scripts\\python tools\\page_check.py --size 820x1180    the same pages on a portrait tablet
    .\\.venv\\Scripts\\python tools\\page_check.py --group F NV       only some streams' routes
    .\\.venv\\Scripts\\python tools\\page_check.py --labels         also list every label with no glossary entry

The simulator (tools/live_sim.py) is the real app against the made-up league (app/demo), so this costs
no CFBD calls. Routes name the league's teams and games through placeholders ({US} the demo team,
{OPP} the opponent in the game under way, {LIVE} that game, {OTHER} a finished game of two other teams, {LAST} and {NEXT} the demo team's games
before and after it, {S} the season), filled in from the league before the pages load. Edge (headless, driven over its DevTools protocol) loads each page, waits
for its loading skeletons to go, and reads the text a reader would see; each hit is printed with its
surroundings.
--interact (Phase 18.5) also clicks through the menu, search, the tabs and a rank-chip sheet in the same browser, and fails on any
script error the page throws while it does.
Exit status 0 when every page is clean, 1 when any is not, 2 when Edge or the server is missing.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Phase 16: one group per stream. Each stream adds its routes to its own group only (hotspot rule), so
# parallel branches never edit the same lines. ROUTES is every group, in this order, without repeats.
ROUTE_GROUPS: dict[str, list[str]] = {
    # --- F: every page as it stood before Phase 16, plus a flyout team page ---
    "F": [
        "season", "newspaper", "program", "live", "leaders", "roster", "recruiting", "ratings",
        "archive", "glossary", "settings", "team={US}", "team={OPP}",
    ],
    # --- NV: national lists (national=<metric>?team=&year=&scope=), search, glossary ---
    "NV": [
        "national=profile:ypp", "national=profile:ypp_d?team={OPP}&scope=conference", "national=advanced:defense_explosiveness",
        "national=board:passing:YDS", "national=poll:AP", "national=rating:sp", "national=class:{S}",
        "national=recruit:{S}", "national=returning:percentPPA", "national=bluechip:ratio?scope=conference",
        "national=profile:ypp?year={S-1}&team={OPP}", "national=nope:nothing",
    ],
    # --- SEASON: Season, team pages, Ratings ---
    "SEASON": ["season", "season=polls:Coaches", "team={US}", "team={OPP}", "ratings", "ratings=sp", "ratings=elo?team={OPP}", "preseason"],
    # --- PROGRAM: Game program (the simulator's game under way, a finished one, an upcoming one) ---
    "PROGRAM": ["program", "program={LIVE}", "program={LAST}", "program={NEXT}", "box={LAST}", "box={OTHER}", "season?band=standings", "team={OPP}?band=standings"],
    # --- PEOPLE: Leaders, Roster, Recruiting, the player card ---
    "PEOPLE": [
        "leaders", "leaders=passing:YDS:national", "leaders=defensive:TOT:conference", "leaders=ppa:all:opponent",
        "leaders=usage:overall:national", "roster", "recruiting", "recruiting=national", "recruiting={S+1}:where",
    ],
    # --- PROFILES: configure, profiles ---
    "PROFILES": [],
    # --- SCORES: Newspaper, ticker ---
    "SCORES": [],
    # --- LIVE: Live sheet, Archive ---
    "LIVE": [],
    # --- DS: shell ---
    "DS": [],
    # --- public release Phase 5b: My teams, the opponents and My teams lists ---
    # --- Phase 18.6: Invite friends and the game-day board ---
    "FRIENDS": ["invite", "board", "review"],
    "MYTEAMS": ["myteams", "national=rating:sp?scope=opponents", "national=profile:ypp?scope=mine", "national=board:passing:YDS?scope=opponents"],
}
ROUTES = list(dict.fromkeys(route for group in ROUTE_GROUPS.values() for route in group))
DEFAULT_SIZE = (1180, 820)
# Phase 19 (owner 2026-10-08): the app is arranged and tested around two screens, a tablet and a full-screen monitor.
ANCHOR_SIZES = [(1180, 820), (820, 1180), (1920, 1080)]  # an iPad (Air or plain) both ways, and a 1080p screen: what a bar's television is
ANCHOR_NAMES = {(1180, 820): "iPad, landscape", (820, 1180): "iPad, portrait", (1920, 1080): "1080p screen"}
BAD = re.compile(r"\b(undefined|null|NaN|Infinity)\b|\[object Object\]")
# Any Chromium browser with the DevTools protocol works: Edge on Windows, Chrome or Chromium elsewhere.
EDGE_PATHS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
]
BROWSER_COMMANDS = ("msedge", "microsoft-edge", "microsoft-edge-stable", "google-chrome", "google-chrome-stable", "chrome", "chromium", "chromium-browser")
# Text the app shows on purpose that contains one of the words (none today); matched against the hit's context.
ALLOWED: list[re.Pattern[str]] = []

# Phase 17 #20 (--labels): every label cell the stat hints look at (static/js/ui/hints.js LABELS) that has no
# glossary entry, so no stat, rule or term is left without an explanation. Cells naming a team or a player
# (a team link, a logo, a player button) are not terms. Also opens player cards and reads each of their tabs.
LABEL_SELECTOR = "td.txt:first-child, th[scope=row], thead th, .sit__label, .success__source, .verdict, .hint-term"
# A row label is a term only in a table of stats: one whose first column is headed by one of these (or a
# two-team table); the first cell of a roster, a recruit list or a standings row names a person or a team.
STAT_HEADS = ["statistic", "stat", "metric", "measure", "split", "situation", "matchup", "part", "rating", "this season", "last season", "category", "rate"]
# Headers and labels a new fan already understands: names of things, places, dates and the table's own furniture.
PLAIN_LABELS = {
    "#", "±", "away", "change", "choice", "class", "coach", "conference", "date", "game", "high school", "hired", "home",
    "hometown", "ht", "wt", "last game", "last three", "last 5", "matchup", "measure", "metric", "next", "no", "no.", "note",
    "opp", "opponent", "overall", "player", "pos", "rank", "rating", "record", "recruit", "result", "season", "score",
    "score or date", "site", "situation", "slot", "split", "starter", "stat", "state", "statistic", "status", "team",
    "this season", "total", "transfer from", "value", "week", "wk", "winner", "year", "commits", "offense", "defense",
    "special", "passing", "rushing", "receiving", "kicking", "punting", "kick returns", "punt returns", "interceptions",
    "pass", "run", "rush", "rec", "def", "off", "by quarter", "per quarter", "line", "part", "percentile", "drives",
    "plays", "tackles", "solo", "stars", "share", "avg", "avg rating", "pct", "margin", "pts", "long", "att", "car", "yds",
    "both teams", "attempts", "career", "last season", "players", "all", "position", "unit", "then, in order",
}
UNEXPLAINED_JS = r"""
(() => {
  const statHeads = new Set(STAT_HEADS);
  const out = new Set();
  const statTable = (n) => {
    const table = n.closest('table');
    if (!table) return true; // a situation label or a verdict, not a table row
    if (table.closest('.tt, .two-team, .prof, .grade-parts')) return true;
    const first = table.querySelector('thead th');
    return Boolean(first) && statHeads.has(first.textContent.replace(/\s+/g, ' ').trim().toLowerCase());
  };
  for (const n of document.querySelectorAll(SELECTOR)) {
    if (n.closest('.hint-pop, .gloss, .search, .sg__frame')) continue;
    if (n.dataset.hint) continue;
    const head = n.matches('thead th');
    if (head && (n.matches('.us, .them, [class*=team]') || n.closest('.tt__them'))) continue; // a team's abbreviation
    if (!head && !statTable(n)) continue;
    const sort = n.tagName === 'TH' ? n.querySelector('button') : null;
    if (sort && (sort.title || '').includes(':')) continue;
    if (n.querySelector('.team-link, a[href^="#team"], .team-logo, img') || (n.tagName === 'TD' && n.querySelector('button'))) continue;
    const own = [...n.childNodes].filter((c) => c.nodeType === 3).map((c) => c.textContent).join('').trim() || n.textContent.trim();
    const words = own.replace(/\s+/g, ' ');
    if (words && /[A-Za-z]/.test(words)) out.add(words);
  }
  return [...out];
})()
""".replace("SELECTOR", json.dumps(LABEL_SELECTOR)).replace("STAT_HEADS", json.dumps(STAT_HEADS))
# Phase 19 (owner 2026-10-08, after a wide "Leaders side by side" band put each label a hand's width from its value): find rows,
# table rows and grids whose content is split apart by a large empty gap, so a label and its value never sit far from each other.
# A band's head (title left, summary right), a face-off (team left, team right), a table's header row, the roster grid's empty
# class cells and a Settings row (name left, switch right) are split on purpose and skipped.
# Run on every page at every anchor size with --layout. A row counts when it is wider than 700 px and two of its children's
# text sits on one line with more than STRETCH_GAP px of nothing between them.
STRETCH_GAP = 300
STRETCH_JS = r"""
(() => {
  const GAP = STRETCH_GAP;
  const found = new Map();
  const visible = (el) => { const s = getComputedStyle(el); return s.display !== 'none' && s.visibility !== 'hidden' && el.getClientRects().length > 0; };
  const textBox = (el) => {
    const range = document.createRange();
    range.selectNodeContents(el);
    const boxes = [...range.getClientRects()].filter((b) => b.width > 0 && b.height > 0);
    if (!boxes.length || !(el.textContent || '').trim()) return null;
    return { l: Math.min(...boxes.map((b) => b.left)), r: Math.max(...boxes.map((b) => b.right)), t: Math.min(...boxes.map((b) => b.top)), b: Math.max(...boxes.map((b) => b.bottom)) };
  };
  const name = (el) => (el.tagName || '').toLowerCase() + (typeof el.className === 'string' && el.className.trim() ? '.' + el.className.trim().split(/\s+/).slice(0, 2).join('.') : '');
  const where = (el) => { const band = el.closest('[id]'); return band ? '#' + band.id : 'page'; };
  if (document.body.classList.contains('board-mode')) return []; // the board is drawn at a zoom: its gaps are the zoom's
  const BY_DESIGN = /(__head|faceoff|__ends|kicker-row|team-head|mast__line|wp__caption|game-card|leaders__head|rgrid|^setting$)/;
  for (const el of document.querySelectorAll('main *')) {
    if (BY_DESIGN.test(typeof el.className === 'string' ? el.className : '') || el.closest('.band__head, thead, .rgrid')) continue;
    const display = getComputedStyle(el).display;
    if (!(display.includes('flex') || display.includes('grid') || display === 'table-row')) continue;
    const box = el.getBoundingClientRect();
    if (box.width < 700 || !visible(el)) continue;
    const parts = [...el.children].filter(visible).map((child) => ({ child, box: textBox(child) })).filter((p) => p.box).sort((a, b) => a.box.l - b.box.l);
    for (let i = 0; i + 1 < parts.length; i += 1) {
      const a = parts[i].box;
      const b = parts[i + 1].box;
      const sameLine = Math.abs(a.t - b.t) < 14 || (a.t < b.b && b.t < a.b);
      const gap = b.l - a.r;
      if (!sameLine || gap <= GAP) continue;
      const key = where(el) + ' ' + name(el);
      const entry = found.get(key) || { where: where(el), element: name(el), gap: 0, width: Math.round(box.width), sample: [] };
      entry.gap = Math.max(entry.gap, Math.round(gap));
      if (entry.sample.length < 2) entry.sample.push((parts[i].child.textContent || '').trim().slice(0, 24) + ' ... ' + (parts[i + 1].child.textContent || '').trim().slice(0, 24));
      found.set(key, entry);
    }
  }
  return [...found.values()].sort((x, y) => y.gap - x.gap);
})()
""".replace("STRETCH_GAP", str(STRETCH_GAP))


# Phase 19: the written rules, measured. Text under 13 px (the floor since wave 3; chart axes and small print inside a drawing
# are exempt) and, on a touch screen, anything you press that is under 44 px tall or wide (docs/03-DESIGN.md, "Touch and
# accessibility"). Run with --rules; the touch rule is only checked at tablet widths.
RULES_JS = r"""
(() => {
  const found = new Map();
  const visible = (el) => { const s = getComputedStyle(el); return s.display !== 'none' && s.visibility !== 'hidden' && el.getClientRects().length > 0; };
  const label = (el) => (el.tagName || '').toLowerCase() + (typeof el.className === 'string' && el.className.trim() ? '.' + el.className.trim().split(/\s+/).slice(0, 2).join('.') : '');
  const note = (key, value) => { const e = found.get(key) || { rule: value.rule, element: value.element, count: 0, sample: value.sample, size: value.size }; e.count += 1; found.set(key, e); };
  const small = document.createTreeWalker(document.querySelector('main') || document.body, NodeFilter.SHOW_TEXT);
  while (small.nextNode()) {
    const node = small.currentNode;
    const el = node.parentElement;
    if (!el || !node.textContent.trim() || el.closest('svg, canvas, .wp__plot, .spark, .px-pic, .team-logo, script, style') || !visible(el)) continue;
    const size = parseFloat(getComputedStyle(el).fontSize);
    if (size < 12.99) note('text ' + label(el), { rule: 'text under 13 px', element: label(el), sample: node.textContent.trim().slice(0, 30), size: Math.round(size * 10) / 10 });
  }
  if (window.innerWidth <= 1300) {
    for (const el of document.querySelectorAll('main button, main a[href], main select, main input, main [role="button"], .topbar button, .topbar a, .tabs a')) {
      if (!visible(el)) continue;
      const box = el.getBoundingClientRect();
      if (box.width < 1 || box.height < 1 || el.closest('.hint, .glossary-tip, .tt__cell--link')) continue; // a two-team table's linked cell is the whole cell
      const slop = getComputedStyle(el, '::after');
      const grows = slop.position === 'absolute' && slop.content !== 'none';
      const px = (v) => { const n = parseFloat(v); return Number.isFinite(n) ? n : 0; };
      const width = grows ? box.width - px(slop.left) - px(slop.right) : box.width;
      const height = grows ? box.height - px(slop.top) - px(slop.bottom) : box.height;
      const inText = el.tagName === 'A' && getComputedStyle(el).display === 'inline' && el.closest('p, li, small, .note, td, th, span');
      if (inText) continue; // a link inside a sentence or a cell is read, not aimed at
      if (height < (el.closest('tr') ? 37.5 : 43.5) || (width < 43.5 && el.tagName !== 'TH' && !el.closest('th') && (el.textContent || '').trim().length < 3)) note('tap ' + label(el), { rule: 'press target under 44 px', element: label(el), sample: (el.textContent || el.getAttribute('aria-label') || '').trim().slice(0, 30), size: Math.round(width) + 'x' + Math.round(height) });
    }
  }
  return [...found.values()].sort((a, b) => b.count - a.count);
})()
""".replace("\\\\s", "\\s")


PLAYER_TABS_JS = r"""
(async () => {
  const seen = [];
  const pause = (ms) => new Promise((r) => setTimeout(r, ms));
  const leaders = await fetch('/api/season/leaders').then((r) => r.json()).catch(() => null);
  const boards = leaders && leaders.data && Array.isArray(leaders.data.boards) ? leaders.data.boards : [];
  const ids = [];
  for (const b of boards) for (const row of (b.team || []).slice(0, 1)) if (row && row.playerId && !ids.includes(row.playerId)) ids.push(row.playerId);
  const { openPlayer } = await import('/static/js/views/player.js');
  for (const id of ids.slice(0, 4)) {
    openPlayer(id);
    await pause(2500);
    for (const tab of [...document.querySelectorAll('.player-card__tabs [role=tab]')]) {
      tab.click();
      await pause(400);
      seen.push(...(UNEXPLAINED));
    }
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    await pause(300);
  }
  return [...new Set(seen)];
})()
""".replace("UNEXPLAINED", UNEXPLAINED_JS.strip())


def find_edge() -> str | None:
    for path in EDGE_PATHS:
        if os.path.exists(path):
            return path
    return next((found for found in (shutil.which(name) for name in BROWSER_COMMANDS) if found), None)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_for(url: str, seconds: float = 90) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{url}/api/health", timeout=3) as response:
                if response.status == 200:
                    return True
        except OSError:
            time.sleep(0.5)
    return False


class Edge:
    """Headless Edge driven over its DevTools protocol (websockets ships with uvicorn[standard]).
    Each page is loaded, given time for its fetches (until no loading skeleton is left, or the
    budget runs out), and its visible text read with document.body.innerText. Unlike --dump-dom this
    also works on the Live sheet, whose event stream never goes quiet."""

    def __init__(self, path: str, profile: str, size: tuple[int, int] = DEFAULT_SIZE) -> None:
        self.port = free_port()
        self.size = size
        self.proc = subprocess.Popen([path, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check", f"--user-data-dir={profile}", f"--remote-debugging-port={self.port}", f"--window-size={size[0]},{size[1]}", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.ws = None
        self.next_id = 0
        self.errors: list[str] = []
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/json/list", timeout=3) as response:
                    targets = json.loads(response.read())
                page = next((t for t in targets if t.get("type") == "page"), None)
                if page:
                    from websockets.sync.client import connect

                    self._conn = connect(page["webSocketDebuggerUrl"], max_size=None)
                    self.ws = self._conn.__enter__()
                    # --window-size sets the outer window; this sets the viewport the page lays out in
                    self.call("Emulation.setDeviceMetricsOverride", width=size[0], height=size[1], deviceScaleFactor=1, mobile=False)
                    self.call("Runtime.enable")
                    return
            except OSError:
                pass
            time.sleep(0.3)
        raise RuntimeError("Edge's debugging port did not answer")

    def call(self, method: str, **params: object) -> dict:
        self.next_id += 1
        mine = self.next_id
        self.ws.send(json.dumps({"id": mine, "method": method, "params": params}))
        while True:
            message = json.loads(self.ws.recv(timeout=60))
            if message.get("method") == "Runtime.exceptionThrown":  # a script error on the page (Phase 18.5: --interact fails on any)
                detail = (message.get("params") or {}).get("exceptionDetails") or {}
                self.errors.append(str((detail.get("exception") or {}).get("description") or detail.get("text") or "script error")[:300])
            if message.get("id") == mine:
                return message.get("result") or {}

    def text_of(self, url: str, budget_ms: int) -> str:
        self.call("Page.navigate", url="about:blank")
        self.call("Page.navigate", url=url)
        deadline = time.monotonic() + budget_ms / 1000
        time.sleep(1.5)
        while time.monotonic() < deadline:
            busy = self.call("Runtime.evaluate", expression="document.readyState !== 'complete' || !!document.querySelector('.skel')", returnByValue=True)
            if not busy.get("result", {}).get("value"):
                break
            time.sleep(0.5)
        time.sleep(1.0)  # one more beat for the last redraw
        result = self.call("Runtime.evaluate", expression="document.body ? document.body.innerText : ''", returnByValue=True)
        return str(result.get("result", {}).get("value") or "")

    def run(self, expression: str) -> object:
        """Evaluate an async expression in the page and give back its JSON value (None when it threw)."""
        result = self.call("Runtime.evaluate", expression=expression, returnByValue=True, awaitPromise=True)
        if result.get("exceptionDetails"):
            return None
        return result.get("result", {}).get("value")

    def rule_breaks(self) -> list[dict]:
        value = self.run(RULES_JS)
        return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []

    def stretched(self) -> list[dict]:
        """Rows with a large empty gap inside them on the page now loaded (--layout)."""
        value = self.run(STRETCH_JS)
        return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []

    def labels(self, expression: str) -> list[str]:
        """The page's unexplained labels (run after text_of has loaded the page)."""
        result = self.call("Runtime.evaluate", expression=expression, returnByValue=True, awaitPromise=True)
        value = result.get("result", {}).get("value")
        return [str(v) for v in value] if isinstance(value, list) else []

    def close(self) -> None:
        try:
            if self.ws is not None:
                self._conn.__exit__(None, None, None)
        finally:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()


# Phase 18.5: real interaction. Each flow is an async expression evaluated in the page; it gives back "" when it worked
# or a sentence saying what did not. A script error thrown anywhere while the flows run fails the check too.
WAIT_JS = "const wait = (ms) => new Promise((r) => setTimeout(r, ms)); const until = async (fn, ms = 4000) => { const end = Date.now() + ms; while (Date.now() < end) { const v = fn(); if (v) return v; await wait(100); } return null; };"
ESCAPE_JS = "document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));"
FLOWS: list[tuple[str, str]] = [
    ("menu opens and closes", """(async () => {""" + WAIT_JS + """
      document.querySelector('.menu-button').click();
      const drawer = await until(() => document.querySelector('.drawer[aria-label="Menu"]') && document.querySelector('.drawer__item'));
      if (!drawer) return 'the menu did not open';
      const items = document.querySelectorAll('.drawer__item').length;
      if (items < 5) return 'the menu lists only ' + items + ' items';
      document.querySelector('[aria-label="Close menu"]').click();
      await wait(500);
      return '';
    })()"""),
    ("search finds a team", """(async () => {""" + WAIT_JS + """
      document.querySelector('.search-button').click();
      const box = await until(() => document.querySelector('.sheet-layer input'));
      if (!box) return 'the search did not open';
      box.value = 'a'; box.dispatchEvent(new Event('input', { bubbles: true }));
      const row = await until(() => document.querySelector('.sheet-layer .search__row, .sheet-layer .search li, .sheet-layer [role="option"], .sheet-layer button[data-team]'), 6000);
      """ + ESCAPE_JS + """
      await wait(400);
      return row ? '' : 'the search found nothing for "a"';
    })()"""),
    ("every tab opens a page", """(async () => {""" + WAIT_JS + """
      const tabs = [...document.querySelectorAll('.tabs a, .tabs button')];
      if (tabs.length < 3) return 'only ' + tabs.length + ' tabs';
      for (const tab of tabs) {
        tab.click(); await wait(1200);
        const text = document.querySelector('main')?.innerText || '';
        if (text.trim().length < 80) return 'the "' + tab.textContent.trim() + '" tab drew almost nothing';
      }
      return '';
    })()"""),
    ("a rank chip opens its list", """(async () => {""" + WAIT_JS + """
      location.hash = 'season'; await wait(2500);
      const chip = document.querySelector('main a[href^="#national"]');
      if (!chip) return 'no rank chip with a list on the Season page';
      chip.click();
      const sheet = await until(() => document.querySelector('.sheet-layer .nat-sheet, .sheet-layer .national'), 6000);
      """ + ESCAPE_JS + """
      await wait(400);
      return sheet ? '' : 'the list did not open';
    })()"""),
]


def run_flows(edge: Edge, base: str, budget_ms: int) -> int:
    """Load the Game program, run each flow in turn, and say what failed. Returns the number of failures."""
    edge.text_of(f"{base}/#program", budget_ms)
    failures = 0
    for name, body in FLOWS:
        before = len(edge.errors)
        said = edge.run(body)
        problems = [str(said)] if said else (["the flow could not run"] if said is None else [])
        problems += [f"script error: {e}" for e in edge.errors[before:]]
        if problems:
            failures += 1
            print(f"FAIL interaction: {name}")
            for problem in problems:
                print(f"       {problem}")
        else:
            print(f"  ok interaction: {name}")
    return failures


def check_page(edge: Edge, url: str, budget_ms: int) -> tuple[list[str], int]:
    text = re.sub(r"\s+", " ", edge.text_of(url, budget_ms))
    hits = []
    for match in BAD.finditer(text):
        context = text[max(0, match.start() - 60): match.end() + 60].strip()
        if any(p.search(context) for p in ALLOWED):
            continue
        hits.append(context)
    return hits, len(text)


def parse_size(value: str) -> tuple[int, int]:
    """'820x1180' -> (820, 1180); argparse reports anything else."""
    match = re.fullmatch(r"\s*(\d{3,4})\s*[xX]\s*(\d{3,4})\s*", value or "")
    if not match:
        raise argparse.ArgumentTypeError(f"size must look like 1180x820, not {value!r}")
    return int(match.group(1)), int(match.group(2))


def league_values() -> dict[str, str]:
    """The placeholders' values: the simulator's league, at the game it opens on."""
    from urllib.parse import quote

    sys.path.insert(0, str(ROOT))
    from app.demo import names as N
    from app.demo.run import CACHE_DIR, demo_season, next_game
    from app.demo.upstream import load_world

    world = load_world(season=demo_season(), seed=2026, cache_dir=CACHE_DIR)
    league = world.league
    us = league.team(N.OUR_SCHOOL)
    live = next_game(world)
    ours = sorted((r for r in world.seasons[world.season].records if us.id in (r.slot.home, r.slot.away) and r.slot.season_type == "regular"),
                  key=lambda r: r.slot.start)
    before = [r for r in ours if r.slot.start < live.slot.start]
    after = [r for r in ours if r.slot.start > live.slot.start]
    opp = league.by_id[live.slot.away if live.slot.home == us.id else live.slot.home]
    others = [r for r in world.seasons[world.season].records if us.id not in (r.slot.home, r.slot.away) and r.slot.start < live.slot.start]
    season = world.season
    return {"US": quote(us.school), "OPP": quote(opp.school), "LIVE": str(live.id), "LAST": str((before or ours)[-1].id),
            "NEXT": str((after or ours)[0].id), "OTHER": str(others[0].id if others else live.id), "S": str(season), "S-1": str(season - 1), "S+1": str(season + 1)}


def league_names() -> set[str]:
    """Every team's school and abbreviation and every conference's name and short name in the simulator's
    league, lower case: a column headed by a team or a conference is not a term (--labels)."""
    sys.path.insert(0, str(ROOT))
    from app.demo.run import CACHE_DIR, demo_season
    from app.demo.upstream import load_world

    league = load_world(season=demo_season(), seed=2026, cache_dir=CACHE_DIR).league
    return {name.lower() for t in league.teams for name in (t.school, t.abbr, t.conference, t.conf_short) if name}


def fill(route: str, values: dict[str, str]) -> str:
    for key, value in values.items():
        route = route.replace("{" + key + "}", value)
    return route


def routes_for(groups: list[str] | None, routes: list[str] | None) -> list[str]:
    """The routes to check: --routes as given, else the chosen groups, else every group."""
    if routes:
        return routes
    if groups:
        unknown = [g for g in groups if g not in ROUTE_GROUPS]
        if unknown:
            raise SystemExit(f"unknown group(s) {', '.join(unknown)}; known: {', '.join(ROUTE_GROUPS)}")
        return list(dict.fromkeys(route for g in groups for route in ROUTE_GROUPS[g]))
    return ROUTES


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--url", help="check a server that is already running instead of starting the simulator")
    parser.add_argument("--budget", type=int, default=15000, help="milliseconds Edge lets each page run (default 15000)")
    parser.add_argument("--routes", nargs="*", default=None, help="routes to check (default: every group)")
    parser.add_argument("--group", nargs="*", default=None, help=f"only these streams' routes ({', '.join(ROUTE_GROUPS)})")
    parser.add_argument("--size", type=parse_size, default=DEFAULT_SIZE, help="viewport as WIDTHxHEIGHT (default 1180x820; the portrait tablet is 820x1180)")
    parser.add_argument("--anchors", action="store_true", help="run everything at the anchor screens: an iPad at 1180x820 and 820x1180, and a 1080p screen at 1920x1080 (Phase 19)")
    parser.add_argument("--layout", action="store_true", help="also fail on any row whose content is split apart by a large empty gap: a label far from its value (Phase 19)")
    parser.add_argument("--rules", action="store_true", help="also report text under 13 px and (at tablet widths) press targets under 44 px (Phase 19)")
    parser.add_argument("--interact", action="store_true", help="also click through the menu, search, the tabs and a rank-chip sheet (Phase 18.5)")
    parser.add_argument("--labels", action="store_true", help="also list every label with no glossary entry, and fail on any (Phase 17 #20)")
    args = parser.parse_args(argv)
    if args.anchors:
        rest = [a for a in (argv if argv is not None else sys.argv[1:]) if a != "--anchors"]
        worst = 0
        for width, height in ANCHOR_SIZES:
            print(f"== {ANCHOR_NAMES[(width, height)]} ==")
            worst = max(worst, main([*rest, "--size", f"{width}x{height}"]))
        return worst
    args.routes = routes_for(args.group, args.routes)
    if any("{" in route for route in args.routes):
        values = league_values()
        args.routes = [fill(route, values) for route in args.routes]

    edge = find_edge()
    if edge is None:
        print("No Edge, Chrome or Chromium found; install one or add its path to EDGE_PATHS.", file=sys.stderr)
        return 2
    sim = None
    base = args.url.rstrip("/") if args.url else None
    if base is None:
        port = free_port()
        base = f"http://127.0.0.1:{port}"
        sim = subprocess.Popen([sys.executable, str(ROOT / "tools" / "live_sim.py"), "--port", str(port), "--speed", "4", "--start", "75", "--no-browser"], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        if not wait_for(base):
            print(f"No server answered at {base}.", file=sys.stderr)
            return 2
        failures = 0
        with tempfile.TemporaryDirectory(prefix="kickoff-page-check-", ignore_cleanup_errors=True) as profile:
            browser = Edge(edge, profile, args.size)
            print(f"Viewport {args.size[0]}x{args.size[1]}, {len(args.routes)} route(s).")
            unexplained: dict[str, list[str]] = {}
            stretches: list[tuple[str, dict]] = []
            breaks: list[tuple[str, dict]] = []
            try:
                results = []
                for route in args.routes:
                    results.append((route, *check_page(browser, f"{base}/#{route}", args.budget)))
                    if args.rules:
                        for row in browser.rule_breaks():
                            breaks.append((route, row))
                    if args.layout:
                        for row in browser.stretched():
                            stretches.append((route, row))
                    if args.labels:
                        for label in browser.labels(UNEXPLAINED_JS):
                            unexplained.setdefault(label, []).append(route)
                if args.labels:
                    browser.text_of(f"{base}/#roster", args.budget)
                    for label in browser.labels(PLAYER_TABS_JS):
                        unexplained.setdefault(label, []).append("player card")
                if args.interact:
                    failures += run_flows(browser, base, args.budget)
                names = league_names() if args.labels and args.url is None else set()
                unexplained = {k: v for k, v in unexplained.items() if k.strip().rstrip(":.").lower() not in PLAIN_LABELS | names}
            finally:
                browser.close()
            for route, hits, size in results:
                if size < 120:  # the shell alone is about 100 characters; an empty-state page is more
                    print(f"  ?  #{route}: the page came back nearly empty ({size} characters)")
                    failures += 1
                elif hits:
                    failures += 1
                    print(f"FAIL #{route}: {len(hits)} hit(s)")
                    for hit in hits[:5]:
                        print(f"       ...{hit}...")
                else:
                    print(f"  ok #{route} ({size:,} characters of text)")
        if args.rules:
            merged: dict[str, dict] = {}
            for route, row in breaks:
                key = f"{row['rule']}|{row['element']}"
                entry = merged.setdefault(key, {**row, "count": 0, "routes": []})
                entry["count"] += row["count"]
                if route not in entry["routes"]:
                    entry["routes"].append(route)
            if merged:
                failures += 1
                print(f"{len(merged)} rule break(s):")
                for entry in sorted(merged.values(), key=lambda e: -e["count"]):
                    print(f"       {entry['rule']}: {entry['element']} x{entry['count']} ({entry['size']}, e.g. {entry['sample']!r}) on #{', #'.join(entry['routes'][:4])}")
            else:
                print("No rule breaks.")
        if args.layout:
            if stretches:
                failures += 1
                print(f"{len(stretches)} stretched row(s): content split apart by more than {STRETCH_GAP} px of empty space:")
                for route, row in stretches:
                    print(f"       #{route}  {row['where']} {row['element']}  gap {row['gap']} px in {row['width']} px  e.g. {row['sample'][0] if row['sample'] else ''}")
            else:
                print("No stretched rows.")
        if args.labels:
            if unexplained:
                failures += 1
                print(f"{len(unexplained)} label(s) with no glossary entry (add an entry or an alias in static/js/glossary-data.js):")
                for label, where in sorted(unexplained.items(), key=lambda kv: kv[0].lower()):
                    print(f"       {label!r}  on #{', #'.join(dict.fromkeys(where))}")
            else:
                print("Every label has a glossary entry.")
        print("Every page is clean." if failures == 0 else f"{failures} page(s) need a look.")
        return 0 if failures == 0 else 1
    finally:
        if sim is not None:
            sim.terminate()
            try:
                sim.wait(timeout=15)
            except subprocess.TimeoutExpired:
                sim.kill()


if __name__ == "__main__":
    raise SystemExit(main())
