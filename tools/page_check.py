"""Open every page of the app with real data in headless Edge and fail if any shows the words
undefined, null, NaN, Infinity or an object printed as text, [object Object] or [object HTMLElement] (Phase 15, the
design rule "a missing value renders as a dash").

    .\\.venv\\Scripts\\python tools\\page_check.py            start the simulator, check every page, stop
    .\\.venv\\Scripts\\python tools\\page_check.py --url http://127.0.0.1:8650   check a server already running
    .\\.venv\\Scripts\\python tools\\page_check.py --size 820x1180    the same pages on a portrait tablet
    .\\.venv\\Scripts\\python tools\\page_check.py --group F NV       only some streams' routes
    .\\.venv\\Scripts\\python tools\\page_check.py --labels         also list every label with no glossary entry

The simulator (tools/live_sim.py) is the real app against the made-up league (app/demo), so this costs
no CFBD calls. Routes name the league's teams and games through placeholders ({US} the demo team,
{OPP} the opponent in the game under way, {LIVE} that game, {OTHER} a finished game of two other teams, {LAST} and {NEXT} the demo team's games
before and after it, {S} the season), filled in from the league before the pages load ({ARCHIVED}, a game the server's
archive holds, once the server answers). Edge (headless, driven over its DevTools protocol) loads each page, waits
for its loading skeletons to go, and reads the text a reader would see; each hit is printed with its
surroundings.
--interact (Phase 18.5) also clicks through the menu, search, the tabs and a rank-chip sheet in the same browser, and fails on any
script error the page throws while it does. Since item 6 (owner 2026-10-11) --interact also runs:
    the Menu over a sheet: on every page with a trigger (another team's name, a rank chip, a player row) it opens one sheet, at
        700 px and wider (the iPad both ways, the big screen; a phone keeps full-screen sheets), and fails unless the thing under
        a tap at the Menu button's centre is the Menu, the sheet starts under the top bar, and a tap on the Menu closes the
        sheet and opens the menu; a sheet already open before one was asked for (one that opened by itself) fails too;
    the board's way out: #board, from In Game and opened straight at it, fails unless its "Leave big screen" chip hides at
        rest, shows (44 px, on screen, nothing over it, the pointer back) after a mouse move, and leads back to #live;
    a file that does not arrive: one of the app's script files fails (DevTools' Fetch), and the check fails unless the loading
        screen says so beside a Reload within 12 s, and unless the app starts once the file arrives again.
--layout (Phase 19) fails on a row whose content is split apart by a large empty gap.
--rules (Phase 19) reports text under 13 px and, at tablet widths, press targets under 44 px; since item 6 it also fails on a
player's name on two lines (a name never wraps: it shortens), and with --anchors the phone is held to the names too.
--scroll (owner 2026-10-10) fails on anything on a page that scrolls up and down inside itself.
--anchors (the tablet lock, owner 2026-10-13) runs the whole check at the screens the app is made for and no other: an iPad both
ways (1180x820, 820x1180), then a phone (390x844: the words, the scroll rule and a name on one line, never the press targets or
the sheets), then the board alone on a 1080p screen (1920x1080, --board: its words, and with --interact its way out). Any other
page in a wider browser is the iPad's layout with wider columns (ui/flow.js), so nothing else runs wide.
--labels (Phase 17 #20) lists every label with no glossary entry.
The routes include the ones the item 6 menu sweep found missing: an archived game (#archive=<id>: the first game the server's
archive holds, else a finished game the archive does not hold, its designed "not watched" page), one glossary entry, #radio and
an address that is no page.
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
        "archive", "glossary", "settings", "team={US}", "team={OPP}", "setup", "prompts",
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
    "PROGRAM": ["program", "program={LIVE}", "program={LAST}", "program={NEXT}", "box={LAST}", "box={OTHER}", "season?band=standings", "team={OPP}?band=standings"],  # program={LAST}: the results band (wave B)
    # --- PEOPLE: Leaders, Roster, Recruiting, the player card ---
    "PEOPLE": [
        "leaders", "leaders=passing:YDS:national", "leaders=defensive:TOT:conference", "leaders=ppa:all:opponent",
        "leaders=usage:overall:national", "roster", "recruiting", "recruiting=national", "recruiting={S+1}:where",
    ],
    # --- PROFILES: configure, profiles ---
    "PROFILES": [],
    # --- SCORES: Newspaper, ticker; items 10-12: the Top 25 page and an earlier week's edition of the paper ---
    "SCORES": ["top25", "newspaper=week-7", "newspaper=week-1"],
    # --- LIVE: Live sheet, Archive ---
    # item 6: an archived game ({ARCHIVED}: filled from the server's /api/archive once it answers, else {LAST})
    "LIVE": ["archive={ARCHIVED}"],
    # --- DS: shell ---
    # item 6: the routes the menu sweep found missing: one glossary entry, the radio (the Pre-Game Program's radio band), an
    # address that is no page (the router sends it to the Pre-Game Program)
    "DS": ["glossary=success-rate", "radio", "no-such-page"],
    # --- public release Phase 5b: My teams, the opponents and My teams lists ---
    # --- Phase 18.6: Invite friends and the game-day board ---
    "FRIENDS": ["invite", "board", "review"],
    "MYTEAMS": ["myteams", "injuries", "national=rating:sp?scope=opponents", "national=profile:ypp?scope=mine", "national=board:passing:YDS?scope=opponents"],
}
ROUTES = list(dict.fromkeys(route for group in ROUTE_GROUPS.values() for route in group))
DEFAULT_SIZE = (1180, 820)
# Phase 19 (owner 2026-10-08): the app is arranged and tested around two screens, a tablet and a full-screen monitor.
# The screens (owner 2026-10-13, the tablet lock): an iPad both ways and a phone for every page; the big screen for the board
# only, since any other page in a wider browser is the iPad's layout with wider columns (ui/flow.js).
ANCHOR_SIZES = [(1180, 820), (820, 1180)]  # an iPad (Air or plain) both ways
PHONE_SIZE = (390, 844)  # an iPhone held upright
BIG_SCREEN = (1920, 1080)  # a 1080p screen: the board's own layout
ANCHOR_NAMES = {(1180, 820): "iPad, landscape", (820, 1180): "iPad, portrait", BIG_SCREEN: "1080p screen, the board", PHONE_SIZE: "phone"}
BAD = re.compile(r"\b(undefined|null|NaN|Infinity)\b|\[object \w+\]")  # any object printed as text ([object HTMLElement] too, 2026-10-10)
BROKEN = re.compile(r"The page could not be drawn \(([^)]{0,200})\)")  # the app's own error band: a render that threw (wave F4, 2026-10-20: a missing import got past the sweep)
# The old names (owner 2026-10-10: Pre-Game Program, In Game, Preseason Magazine, First time setup), never on a page again.
OLD_NAMES = re.compile(r"(?<![-\w])(Game program|Live sheet|live sheet|Preseason page|Device setup)(?![-\w])")
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
LABEL_SELECTOR = "td.txt:first-child, th[scope=row], thead th, .success__source, .verdict, .hint-term"
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
    # tables wave 3 (owner 2026-10-10): the heads the other pages' tables gain (My Teams, the review, the grade, the series)
    "role", "why", "kickoff", "fact", "weight", "venue", "conf record", "last opponent", "next game", "next update",
    # wave 3, the last step: the penalty sheet's heads
    "fouled by", "penalty", "rulebook",
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
    const long = n.querySelector('.sz-t--long, .tt__t--long'); // a sized table's head holds its three forms; the long one is the term (2026-10-10)
    const own = long ? long.textContent.trim() : [...n.childNodes].filter((c) => c.nodeType === 3).map((c) => c.textContent).join('').trim() || n.textContent.trim();
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
  // a drawn thing (the tug-of-war bar, the percentile ladder, the win-probability bar, a drive's bar on the field) is content, not a gap (tables 2026-10-10:
  // a two-team table fills its band and its bar takes the room)
  const DRAWN = '.tug, .ladder, .tt__pct, .wp__bar, .field'; // .field: item 6, an archived game's drives (its own route since then)
  const textBox = (el) => {
    const range = document.createRange();
    range.selectNodeContents(el);
    const boxes = [...range.getClientRects()].filter((b) => b.width > 0 && b.height > 0);
    const drawn = typeof el.matches === 'function' && el.matches(DRAWN) ? el : typeof el.querySelector === 'function' ? el.querySelector(DRAWN) : null;
    if (drawn) { const d = drawn.getBoundingClientRect(); if (d.width > 0 && d.height > 0) boxes.push(d); }
    if (!boxes.length || (!drawn && !(el.textContent || '').trim())) return null;
    return { l: Math.min(...boxes.map((b) => b.left)), r: Math.max(...boxes.map((b) => b.right)), t: Math.min(...boxes.map((b) => b.top)), b: Math.max(...boxes.map((b) => b.bottom)) };
  };
  const name = (el) => (el.tagName || '').toLowerCase() + (typeof el.className === 'string' && el.className.trim() ? '.' + el.className.trim().split(/\s+/).slice(0, 2).join('.') : '');
  const where = (el) => { const band = el.closest('[id]'); return band ? '#' + band.id : 'page'; };
  if (document.body.classList.contains('board-mode')) return []; // the board is drawn at a zoom: its gaps are the zoom's
  const BY_DESIGN = /(__head|faceoff|__ends|kicker-row|team-head|mast__line|wp__caption|game-card|leaders__head|rgrid|tt__group|^setting$|play-drive)/; // tt__group: each team's scheme under its own columns, the bar's column empty between them on purpose; play-drive: a drive's head over its plays (the team and drive left, its plays and yards right), a band head's pattern
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
  // the page and the notes above it (item 6, step C: "Not loaded yet", a guest's welcome)
  for (const root of [document.querySelector('.page-notes'), document.querySelector('main') || document.body]) {
    if (!root) continue;
    const small = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    while (small.nextNode()) {
      const node = small.currentNode;
      const el = node.parentElement;
      if (!el || !node.textContent.trim() || el.closest('svg, canvas, .wp__plot, .spark, .px-pic, .team-logo, script, style') || !visible(el)) continue;
      const size = parseFloat(getComputedStyle(el).fontSize);
      if (size < 12.99) note('text ' + label(el), { rule: 'text under 13 px', element: label(el), sample: node.textContent.trim().slice(0, 30), size: Math.round(size * 10) / 10 });
    }
  }
  if (window.innerWidth <= 1300) {
    for (const el of document.querySelectorAll('main button, main a[href], main select, main input, main [role="button"], .topbar button, .topbar a, .tabs a, .page-notes button, .page-notes a[href]')) {
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


# 2026-10-10 (owner, his phone: a Leaders table scrolled up and down inside itself under the pinned chips; once his finger
# reached its bottom the touch stayed in the box and the page would not move): nothing on a page scrolls up and down inside
# itself. A table shows whole and its band folds instead. Any element on the page whose overflow lets it scroll up and down
# and whose content is taller than its box is a break, by even one pixel: a sideways strip whose press areas poke a pixel past
# its last row rubber-bands under a finger and keeps the touch. The reader's own layers (a side sheet, the menu, the player
# card, the search, an open drop-down, the status card) scroll on their own and are skipped. Run with --scroll; the phone too.
OVERLAYS = ".sheet-layer, .sheet-layer-closing, .drawer, .card-layer, .card-layer-closing, .search, dialog, .jump__panel, .status-card, .hint-pop"
SCROLL_JS = r"""
(() => {
  const found = new Map();
  const visible = (el) => { const s = getComputedStyle(el); return s.display !== 'none' && s.visibility !== 'hidden' && el.getClientRects().length > 0; };
  const label = (el) => (el.tagName || '').toLowerCase() + (typeof el.className === 'string' && el.className.trim() ? '.' + el.className.trim().split(/\s+/).slice(0, 2).join('.') : '');
  const where = (el) => { const band = el.closest('[id]'); return band ? '#' + band.id : 'page'; };
  for (const el of document.querySelectorAll('body *')) {
    if (el.closest('OVERLAYS') || !visible(el)) continue;
    const s = getComputedStyle(el);
    if (!/(auto|scroll|overlay)/.test(s.overflowY)) continue;
    const over = el.scrollHeight - el.clientHeight;
    if (over < 1) continue;
    const key = where(el) + ' ' + label(el);
    const entry = found.get(key) || { where: where(el), element: label(el), count: 0, over: 0, box: Math.round(el.clientHeight) };
    entry.count += 1;
    entry.over = Math.max(entry.over, Math.round(over));
    found.set(key, entry);
  }
  return [...found.values()].sort((a, b) => b.over - a.over);
})()
""".replace("OVERLAYS", OVERLAYS)


# Item 6 (owner 2026-10-11, "One line only, reduce the name"): a player's name never wraps onto a second line; a table steps
# down through "K. Crawford", the surname and "Brackwater-M." instead, and only last cuts it with "…" (docs/03-DESIGN.md, "The
# menu, the big screen and player names"). Every name is drawn by ui/dom.js personName as a .pn with its four forms, one shown;
# a name counts the lines its shown words sit on (the screen reader's copy left out). Run with --rules, on the page and (with
# --interact) inside the sheet the Menu check opens; with --anchors the phone too.
NAMES_JS = r"""
(() => {
  const visible = (el) => { const s = getComputedStyle(el); const b = el.getBoundingClientRect(); return s.display !== 'none' && s.visibility !== 'hidden' && b.width > 0 && b.height > 0; };
  const label = (el) => (el.tagName || '').toLowerCase() + (typeof el.className === 'string' && el.className.trim() ? '.' + el.className.trim().split(/\s+/).slice(0, 2).join('.') : '');
  const where = (el) => { const band = el.closest('[id]'); const layer = el.closest('[data-modal]'); return (layer ? 'sheet ' : '') + (band ? '#' + band.id : 'page'); };
  const lineCount = (pn) => {
    const rows = [];
    const walker = document.createTreeWalker(pn, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
      const node = walker.currentNode;
      const parent = node.parentElement;
      if (!parent || !node.textContent.trim() || parent.closest('.sr-only') || !visible(parent)) continue;
      const range = document.createRange();
      range.selectNodeContents(node);
      for (const box of range.getClientRects()) {
        if (box.width < 0.5 || box.height < 0.5) continue;
        const middle = (box.top + box.bottom) / 2;
        if (!rows.some((row) => middle > row.top && middle < row.bottom)) rows.push({ top: box.top, bottom: box.bottom });
      }
    }
    return rows.length;
  };
  const shown = (pn) => ([...pn.querySelectorAll('.pn__f')].filter(visible).map((f) => f.textContent).join('') || pn.textContent || '').replace(/\u00a0/g, ' ').trim();
  const found = new Map();
  for (const root of document.querySelectorAll(ROOTS)) {
    for (const pn of root.querySelectorAll('.pn')) {
      if (!visible(pn)) continue;
      const lines = lineCount(pn);
      if (lines < 2) continue;
      const box = pn.closest('table, .tt, [class*="card"], li, p') || pn.parentElement || pn;
      const key = where(pn) + ' ' + label(box);
      const entry = found.get(key) || { where: where(pn), element: label(box), count: 0, lines: 0, sample: shown(pn).slice(0, 40) };
      entry.count += 1;
      entry.lines = Math.max(entry.lines, lines);
      found.set(key, entry);
    }
  }
  return [...found.values()].sort((a, b) => b.count - a.count);
})()
"""
OPEN_LAYERS = ".sheet-layer[data-modal], .card-layer[data-modal]"  # a side sheet or the player card, open (a closing one drops data-modal)
PAGE_NAMES_JS = NAMES_JS.replace("ROOTS", json.dumps("body"))
LAYER_NAMES_JS = NAMES_JS.replace("ROOTS", json.dumps(OPEN_LAYERS))


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
        # item 6 (--interact, a file that does not arrive): while the Fetch domain pauses requests, any whose address holds
        # one of these parts is failed as a dropped connection, any other let through; each failed address is kept
        self.failing: tuple[str, ...] = ()
        self.failed: list[str] = []
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
            if message.get("method") == "Fetch.requestPaused":
                self.answer_paused(message.get("params") or {})
            if message.get("id") == mine:
                return message.get("result") or {}

    def answer_paused(self, params: dict) -> None:
        """A request the Fetch domain paused: fail it when its address holds one of self.failing, else let it through. Sent
        without waiting; the answer to it is read and passed over by call()."""
        request_id = params.get("requestId")
        if not isinstance(request_id, str) or not request_id:
            return
        url = str((params.get("request") or {}).get("url") or "")
        self.next_id += 1
        if any(part and part in url for part in self.failing):
            self.failed.append(url)
            message = {"id": self.next_id, "method": "Fetch.failRequest", "params": {"requestId": request_id, "errorReason": "ConnectionReset"}}
        else:
            message = {"id": self.next_id, "method": "Fetch.continueRequest", "params": {"requestId": request_id}}
        self.ws.send(json.dumps(message))

    def move(self, x: float, y: float) -> None:
        """A real mouse move to a point of the viewport (CSS pixels)."""
        self.call("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y, button="none")

    def tap(self, x: float, y: float) -> None:
        """A real click at a point of the viewport: the pointer moves there, presses and lets go (hit-testing applies)."""
        self.move(x, y)
        self.call("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y, button="left", clickCount=1)
        self.call("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y, button="left", clickCount=1)

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

    def scroll_boxes(self) -> list[dict]:
        """Elements on the page now loaded that scroll up and down inside themselves (--scroll)."""
        value = self.run(SCROLL_JS)
        return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []

    def wrapped_names(self, expression: str = PAGE_NAMES_JS) -> list[dict]:
        """Players' names on two lines or more, on the page now loaded or (LAYER_NAMES_JS) in its open sheet (--rules)."""
        value = self.run(expression)
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


# Item 6, step I (owner 2026-10-11): checks that keep the menu fixed. Each runs with --interact.
#
# The Menu over a sheet (step B): on the iPad and the big screen every side sheet and the player card start under the top bar,
# so the Menu stays the thing under a tap at its spot. One sheet per page, from the first trigger the page has, the kind used
# least so far first (so a run opens all three): another team's name (its flyout; our own leads to our page), a rank chip
# (its national list), a player row (the card).
SHEET_MIN_WIDTH = 700  # below it a phone keeps full-screen sheets (owner answer 2)
SHEET_KINDS = ("team", "chip", "player")
SHEET_SKIP = ("board",)  # the board hides the top bar on purpose; its own check is the way out
OPEN_SHEET_JS = (r"""(async () => {""" + WAIT_JS + r"""
  const visible = (el) => { const s = getComputedStyle(el); const b = el.getBoundingClientRect(); return s.display !== 'none' && s.visibility !== 'hidden' && b.width > 0 && b.height > 0; };
  const layer = () => document.querySelector(OPEN_LAYERS);
  const already = layer();
  if (already) return { kind: null, problem: 'a sheet opened by itself: ' + (already.getAttribute('aria-label') || already.className) };
  let isUs = () => false;
  try { const id = await import('/static/js/identity.js'); if (typeof id.isUs === 'function') isUs = id.isUs; } catch (e) { /* every team name is tried */ }
  const triggers = {
    team: () => [...document.querySelectorAll('main button.team-link[data-team]')].filter((b) => !isUs(b.dataset.team)),
    chip: () => [...document.querySelectorAll('main a[href^="#national"]')],
    player: () => [...document.querySelectorAll('main tr[role="button"], main button')].filter((b) => b.querySelector('.pn')),
  };
  for (const kind of ORDER) {
    for (const trigger of triggers[kind]().filter(visible).slice(0, 3)) {
      const before = location.hash;
      trigger.scrollIntoView({ block: 'center' });
      await wait(150);
      trigger.click();
      const open = await until(layer, 3000);
      if (open) {
        await wait(450); // the slide in
        const pn = trigger.querySelector('.pn');
        const words = ((pn && pn.getAttribute('title')) || trigger.getAttribute('aria-label') || trigger.innerText || '').replace(/\s+/g, ' ').trim();
        return { kind, what: words.slice(0, 40), sheet: open.getAttribute('aria-label') || (open.querySelector('.player-card') ? 'player card' : 'sheet') };
      }
      if (location.hash !== before) return { kind: null, left: location.hash }; // the trigger led to a page, not a sheet
    }
  }
  return { kind: null };
})()""").replace("OPEN_LAYERS", json.dumps(OPEN_LAYERS))
MENU_SPOT_JS = r"""(() => {
  const label = (el) => !el ? 'nothing' : (el.tagName || '').toLowerCase() + (typeof el.className === 'string' && el.className.trim() ? '.' + el.className.trim().split(/\s+/).slice(0, 2).join('.') : '');
  const layer = document.querySelector(OPEN_LAYERS);
  const menu = document.querySelector('.topbar .menu-button');
  if (!layer) return { problem: 'the sheet closed by itself' };
  if (!menu) return { problem: 'no Menu button in the top bar' };
  const r = menu.getBoundingClientRect();
  const x = r.left + r.width / 2;
  const y = r.top + r.height / 2;
  if (r.width < 1 || r.height < 1 || x < 0 || y < 0 || x > innerWidth || y > innerHeight) return { x, y, problem: 'the Menu is off the screen (its centre at ' + Math.round(x) + ', ' + Math.round(y) + ')' };
  const hit = document.elementFromPoint(x, y);
  if (!hit || !(hit === menu || menu.contains(hit))) {
    const over = hit ? hit.closest('[data-modal]') : null;
    return { x, y, problem: 'the Menu is covered by ' + label(hit) + (over ? ' in ' + label(over) + (over.getAttribute('aria-label') ? ' "' + over.getAttribute('aria-label') + '"' : '') : '') };
  }
  const panel = layer.querySelector(':scope > .side-sheet, :scope > .player-card');
  const bar = document.querySelector('.topbar').getBoundingClientRect();
  if (panel && panel.getBoundingClientRect().top < bar.bottom - 1) return { x, y, problem: 'the sheet starts at ' + Math.round(panel.getBoundingClientRect().top) + ' px, over the top bar (its bottom edge at ' + Math.round(bar.bottom) + ' px)' };
  return { x, y, problem: '' };
})()""".replace("OPEN_LAYERS", json.dumps(OPEN_LAYERS))
AFTER_MENU_JS = (r"""(async () => {""" + WAIT_JS + r"""
  const drawer = await until(() => document.querySelector('.drawer[open]'), 2500);
  if (!drawer) return 'a tap on the Menu did not open the menu';
  if (document.querySelector(OPEN_LAYERS)) return 'a tap on the Menu opened the menu but left the sheet open';
  """ + ESCAPE_JS + r"""
  const shut = await until(() => !document.querySelector('.drawer[open]'), 2500);
  return shut ? '' : 'Escape did not close the menu';
})()""").replace("OPEN_LAYERS", json.dumps(OPEN_LAYERS))
# the open sheet's own loading skeletons gone (a team's flyout fetches its page), before its names are read
LAYER_SETTLED_JS = (r"""(async () => {""" + WAIT_JS + r"""
  await until(() => !document.querySelector(SKELETONS), 4000);
  return true;
})()""").replace("SKELETONS", json.dumps(", ".join(f"{layer} .skel" for layer in OPEN_LAYERS.split(", "))))


def sheet_order(used: dict[str, int]) -> list[str]:
    """The trigger kinds to try on the next page: the one opened least so far first, ties in SHEET_KINDS order."""
    return sorted(SHEET_KINDS, key=lambda kind: (used.get(kind, 0), SHEET_KINDS.index(kind)))


def check_sheet(edge: Edge, used: dict[str, int], names: bool) -> dict:
    """On the page now loaded: open one sheet, check the Menu's spot, tap the Menu, close the menu. Gives back
    {"kind", "what", "sheet", "problems", "names"}; kind None when the page has no trigger (not a failure)."""
    before = len(edge.errors)
    opened = edge.run(OPEN_SHEET_JS.replace("ORDER", json.dumps(sheet_order(used))))
    result: dict = {"kind": None, "what": "", "sheet": "", "problems": [], "names": []}
    if not isinstance(opened, dict):
        result["problems"].append("the sheet check could not run")
    elif opened.get("problem"):
        result["problems"].append(str(opened["problem"]))
    elif opened.get("kind") in SHEET_KINDS:
        kind = str(opened["kind"])
        used[kind] = used.get(kind, 0) + 1
        result.update(kind=kind, what=str(opened.get("what") or ""), sheet=str(opened.get("sheet") or ""))
        if names:
            edge.run(LAYER_SETTLED_JS)
            result["names"] = edge.wrapped_names(LAYER_NAMES_JS)
        spot = edge.run(MENU_SPOT_JS)
        if not isinstance(spot, dict):
            result["problems"].append("the Menu's spot could not be read")
        elif spot.get("problem"):
            result["problems"].append(str(spot["problem"]))
        else:
            edge.tap(float(spot["x"]), float(spot["y"]))
            said = edge.run(AFTER_MENU_JS)
            if said is None or said:
                result["problems"].append(str(said) if said else "the menu check could not run")
    result["problems"] += [f"script error: {e}" for e in edge.errors[before:]]
    return result


def report_sheets(results: list[tuple[str, dict]], width: int) -> int:
    """Print the Menu-over-a-sheet check's verdict; 1 when any page failed it."""
    name = "the Menu over a sheet"
    if width < SHEET_MIN_WIDTH:
        print(f"  -- interaction: {name}: not checked below {SHEET_MIN_WIDTH} px (a phone keeps full-screen sheets)")
        return 0
    bad = [(route, r) for route, r in results if r["problems"]]
    opened = [r for _route, r in results if r["kind"]]
    kinds = ", ".join(f"{sum(1 for r in opened if r['kind'] == k)} {k}" for k in SHEET_KINDS)
    if bad:
        print(f"FAIL interaction: {name} ({len(bad)} of {len(results)} page(s))")
        for route, r in bad:
            opener = f" ({r['kind']} {r['what']!r}, {r['sheet']!r})" if r["kind"] else ""
            for problem in r["problems"]:
                print(f"       #{route}{opener}: {problem}")
        return 1
    print(f"  ok interaction: {name} ({len(opened)} sheet(s) on {len(results)} page(s): {kinds}; {len(results) - len(opened)} page(s) with no trigger)")
    return 0


# The board's way out (step A): a "Leave big screen" chip, hidden at rest, shown by a mouse move, a key or a tap, back to In
# Game. Checked from In Game (the Big screen button's way in) and opened straight at the board (the kiosk, a bookmark, a
# cast tab), with real mouse events: a move to wake it, then a press on its centre once the reveal guard has passed.
BOARD_REVEAL_S = 0.5  # board.js REVEAL_MS is 400: a press sooner only reveals the chip
BOARD_REST_JS = r"""(async () => {""" + WAIT_JS + r"""
  const chip = await until(() => document.body.classList.contains('board-mode') && document.querySelector('.board-exit__leave'), 8000);
  if (!chip) return 'the board has no "Leave big screen" chip';
  const rests = await until(() => Number(getComputedStyle(chip).opacity) < 0.05, 8000);
  return rests ? '' : 'the chip never hides, so the TV is never clean';
})()"""
BOARD_SHOWN_JS = r"""(async () => {""" + WAIT_JS + r"""
  const label = (el) => !el ? 'nothing' : (el.tagName || '').toLowerCase() + (typeof el.className === 'string' && el.className.trim() ? '.' + el.className.trim().split(/\s+/).slice(0, 2).join('.') : '');
  const chip = document.querySelector('.board-exit__leave');
  if (!chip) return { problem: 'the chip is gone' };
  const shown = await until(() => Number(getComputedStyle(chip).opacity) > 0.95, 2000);
  const r = chip.getBoundingClientRect();
  const x = r.left + r.width / 2;
  const y = r.top + r.height / 2;
  const hit = document.elementFromPoint(x, y);
  const cursor = getComputedStyle(document.querySelector('.shell__main') || document.body).cursor;
  const problems = [];
  if (!shown) problems.push('a mouse move did not show the chip');
  if (r.width < 43.5 || r.height < 43.5) problems.push('the chip is ' + Math.round(r.width) + 'x' + Math.round(r.height) + ', under 44 px');
  if (r.left < 0 || r.top < 0 || r.right > innerWidth || r.bottom > innerHeight) problems.push('the chip is off the screen');
  else if (!hit || !(hit === chip || chip.contains(hit))) problems.push('the chip is covered by ' + label(hit));
  if (cursor === 'none') problems.push('the mouse pointer stays hidden after a move');
  return { x, y, size: Math.round(r.width) + 'x' + Math.round(r.height), words: (chip.innerText || '').replace(/\s+/g, ' ').trim(), problem: problems.join('; ') };
})()"""
BOARD_LEFT_JS = r"""(async () => {""" + WAIT_JS + r"""
  const shown = (el) => Boolean(el) && getComputedStyle(el).display !== 'none' && el.getBoundingClientRect().width > 0;
  const back = await until(() => location.hash === '#live' && !document.body.classList.contains('board-mode') && shown(document.querySelector('.topbar .menu-button')), 5000);
  if (back) return '';
  return 'the chip did not lead back to In Game (the address is ' + (location.hash || 'without a page') + (document.body.classList.contains('board-mode') ? ', still the board' : '') + ')';
})()"""


def check_board(edge: Edge, base: str, budget_ms: int) -> tuple[list[str], str]:
    """The board's way out, both ways in. Gives back (problems, what the chip read and measured)."""
    problems: list[str] = []
    seen = ""
    before = len(edge.errors)
    for way in ("from In Game", "opened straight at #board"):
        if way == "from In Game":
            edge.text_of(f"{base}/#live", budget_ms)
            edge.run("(() => { location.hash = 'board'; return true; })()")
        else:
            edge.text_of(f"{base}/#board", budget_ms)
        said = edge.run(BOARD_REST_JS)
        if said is None or said:
            problems.append(f"{way}: {said or 'the board check could not run'}")
            continue
        width, height = edge.size
        edge.move(width / 2, height / 2)
        edge.move(width / 2 + 24, height / 2 + 12)
        chip = edge.run(BOARD_SHOWN_JS)
        if not isinstance(chip, dict) or chip.get("problem"):
            problems.append(f"{way}: {chip.get('problem') if isinstance(chip, dict) else 'the chip could not be read'}")
            continue
        seen = f"{chip.get('words')!r}, {chip.get('size')}"
        time.sleep(BOARD_REVEAL_S)
        edge.tap(float(chip["x"]), float(chip["y"]))
        left = edge.run(BOARD_LEFT_JS)
        if left is None or left:
            problems.append(f"{way}: {left or 'the way back could not be read'}")
    problems += [f"script error: {e}" for e in edge.errors[before:]]
    return problems, seen


# A file that does not arrive (step E): the loading screen carries Reload from the first frame and, when a file fails or the
# app has not drawn its Menu in 10 s, says it could not load. One of the app's script files is failed as a dropped connection
# (every page imports it), the cache is off so the browser asks for it, and within BOOT_LIMIT_S the page must say so beside a
# Reload that is 44 px tall with nothing over it. Then the file arrives again and the app must start.
BOOT_FILE = "static/js/ui/dom.js"
BOOT_LIMIT_S = 12.0
BOOT_JS = r"""(() => {
  const visible = (el) => { if (!el) return false; const s = getComputedStyle(el); const b = el.getBoundingClientRect(); return s.display !== 'none' && s.visibility !== 'hidden' && b.width > 0 && b.height > 0; };
  const drawn = Boolean(document.querySelector('#app .menu-button'));
  const failed = document.getElementById('boot-failed');
  const said = Boolean(failed && !failed.hidden && visible(failed));
  const pill = ((document.getElementById('boot-pill') || {}).textContent || '').replace(/\s+/g, ' ').trim();
  let reload = null;
  for (const b of document.querySelectorAll('button, a[href]')) {
    if (!/\breload\b/i.test(b.textContent || '') || !visible(b)) continue;
    const r = b.getBoundingClientRect();
    const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    if (!hit || !(hit === b || b.contains(hit))) continue;
    reload = { size: Math.round(r.width) + 'x' + Math.round(r.height), tall: r.height >= 43.5, where: b.closest('header') ? 'the top bar' : 'the page' };
    if (reload.tall) break;
  }
  return { drawn, said, pill, reload, ok: !drawn && said && Boolean(reload) && reload.tall };
})()"""


def check_boot(edge: Edge, base: str, budget_ms: int) -> tuple[list[str], str]:
    """Fail BOOT_FILE while #program loads; the loading screen must say so beside a Reload. Gives back (problems, what it saw)."""
    problems: list[str] = []
    seen = ""
    before = len(edge.errors)
    edge.failing, edge.failed = (f"/{BOOT_FILE}",), []
    last: object = None
    took: float | None = None
    try:
        edge.call("Network.enable")
        edge.call("Network.setCacheDisabled", cacheDisabled=True)
        edge.call("Fetch.enable", patterns=[{"urlPattern": f"*/{BOOT_FILE}*", "requestStage": "Request"}])
        edge.call("Page.navigate", url="about:blank")
        start = time.monotonic()
        edge.call("Page.navigate", url=f"{base}/#program")
        while time.monotonic() - start < BOOT_LIMIT_S:
            state = edge.run(BOOT_JS)
            if isinstance(state, dict):
                last = state
                if state.get("ok"):
                    took = time.monotonic() - start
                    break
            time.sleep(0.25)
    finally:
        edge.failing = ()
        edge.call("Fetch.disable")
        edge.call("Network.setCacheDisabled", cacheDisabled=False)
        edge.call("Network.disable")
        del edge.errors[before:]  # the failed file's own errors are the point of the check
    state = last if isinstance(last, dict) else {}
    if took is not None:
        reload = state.get("reload") or {}
        seen = f"{BOOT_FILE} failed: {state.get('pill')!r} and Reload ({reload.get('size')}, in {reload.get('where')}) at {took:.1f} s"
    elif not edge.failed:
        problems.append(f"{BOOT_FILE} was never asked for, so it could not be failed (the check needs the cache off)")
    elif state.get("drawn"):
        problems.append(f"the app started although {BOOT_FILE} failed")
    else:
        reload = state.get("reload")
        problems.append(f"no Reload within {BOOT_LIMIT_S:.0f} s of {BOOT_FILE} failing: " + ("the page never said it could not load" if not state.get("said") else f"its Reload is {reload['size']}, under 44 px" if reload else "no Reload on screen with nothing over it") + f" (the pill reads {state.get('pill')!r})")
    edge.text_of(f"{base}/#program", budget_ms)  # the file arrives again: the app starts (the page's own retry is spent)
    if not edge.run("Boolean(document.querySelector('.topbar .menu-button'))"):
        problems.append(f"once {BOOT_FILE} arrived again the app did not start")
    problems += [f"script error: {e}" for e in edge.errors[before:]]
    return problems, seen


def report(name: str, problems: list[str], seen: str) -> int:
    """Print one item 6 interaction check's verdict in the flows' style; 1 when it failed."""
    if problems:
        print(f"FAIL interaction: {name}")
        for problem in problems:
            print(f"       {problem}")
        return 1
    print(f"  ok interaction: {name}" + (f" ({seen})" if seen else ""))
    return 0


def archived_game(payload: object) -> str | None:
    """The first game id in an /api/archive answer ({"data": {"games": [{"gameId": ...}]}}), as text; None when it holds none
    or the answer is not that shape."""
    data = payload.get("data") if isinstance(payload, dict) else None
    games = data.get("games") if isinstance(data, dict) else None
    for game in games if isinstance(games, list) else []:
        game_id = game.get("gameId") if isinstance(game, dict) else None
        if isinstance(game_id, int) and not isinstance(game_id, bool) and game_id > 0:
            return str(game_id)
        if isinstance(game_id, str) and game_id.isdigit():
            return game_id
    return None


def archive_route_value(base: str, fallback: str) -> str:
    """{ARCHIVED}: a game the server's archive holds, else the fallback (a finished game: the archive's "not watched" page)."""
    try:
        with urllib.request.urlopen(f"{base}/api/archive", timeout=10) as response:
            found = archived_game(json.loads(response.read()))
    except (OSError, ValueError) as error:
        print(f"  -- the archive did not answer ({error}); #archive= shows a finished game it does not hold")
        return fallback
    return found or fallback


def check_page(edge: Edge, url: str, budget_ms: int) -> tuple[list[str], int]:
    text = re.sub(r"\s+", " ", edge.text_of(url, budget_ms))
    hits = []
    for match in BAD.finditer(text):
        context = text[max(0, match.start() - 60): match.end() + 60].strip()
        if any(p.search(context) for p in ALLOWED):
            continue
        hits.append(context)
    for match in OLD_NAMES.finditer(text):
        hits.append("old name: " + text[max(0, match.start() - 60): match.end() + 60].strip())
    for match in BROKEN.finditer(text):
        hits.append("the page could not be drawn: " + (match.group(1).strip() or "no reason given"))
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
    league, lower case: a column headed by a team or a conference is not a term (--labels). The short names include the
    server's own (app/services/identity.py conference_short, the initials of a made-up conference: a standings head reads
    "PA" where the league says "PAC")."""
    sys.path.insert(0, str(ROOT))
    from app.demo.run import CACHE_DIR, demo_season
    from app.demo.upstream import load_world
    from app.services.identity import conference_short

    league = load_world(season=demo_season(), seed=2026, cache_dir=CACHE_DIR).league
    return {name.lower() for t in league.teams for name in (t.school, t.abbr, t.conference, t.conf_short, conference_short(t.conference)) if name}


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


def printable(stream: object) -> None:
    """A page's own words reach the report (a sample of a stretched row, a name): a character the output's code page lacks
    (Windows writes a redirected report in cp1252, which has no U+2212 minus) prints as "?" instead of stopping the check."""
    reconfigure = getattr(stream, "reconfigure", None)
    if callable(reconfigure):
        try:
            reconfigure(errors="replace")
        except (ValueError, OSError):
            pass  # a stream that cannot change keeps its own handling


def main(argv: list[str] | None = None, *, names: bool | None = None) -> int:
    """Run the check. names: hold the page to the player-name rule (default: with --rules; the anchors' phone run passes it)."""
    printable(sys.stdout)
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--url", help="check a server that is already running instead of starting the simulator")
    parser.add_argument("--budget", type=int, default=15000, help="milliseconds Edge lets each page run (default 15000)")
    parser.add_argument("--routes", nargs="*", default=None, help="routes to check (default: every group)")
    parser.add_argument("--group", nargs="*", default=None, help=f"only these streams' routes ({', '.join(ROUTE_GROUPS)})")
    parser.add_argument("--size", type=parse_size, default=DEFAULT_SIZE, help="viewport as WIDTHxHEIGHT (default 1180x820; the portrait tablet is 820x1180)")
    parser.add_argument("--anchors", action="store_true", help="run everything at the screens: an iPad at 1180x820 and 820x1180, a phone at 390x844 (the words, the scroll rule and the names), and the board alone on a 1080p screen at 1920x1080 (the tablet lock, 2026-10-13)")
    parser.add_argument("--board", action="store_true", help="the board only (#board), as --anchors runs it on the big screen; with --interact its way out is the one interaction")
    parser.add_argument("--layout", action="store_true", help="also fail on any row whose content is split apart by a large empty gap: a label far from its value (Phase 19)")
    parser.add_argument("--rules", action="store_true", help="also report text under 13 px and (at tablet widths) press targets under 44 px (Phase 19), and fail on a player's name on two lines (item 6; with --anchors the phone too)")
    parser.add_argument("--interact", action="store_true", help="also click through the menu, search, the tabs and a rank-chip sheet (Phase 18.5); and (item 6) open a sheet on every page and check the Menu over it, the board's way out, and a file that does not arrive")
    parser.add_argument("--labels", action="store_true", help="also list every label with no glossary entry, and fail on any (Phase 17 #20)")
    parser.add_argument("--scroll", action="store_true", help="also fail on anything on a page that scrolls up and down inside itself; with --anchors the phone runs too (owner 2026-10-10)")
    args = parser.parse_args(argv)
    if args.anchors:
        rest = [a for a in (argv if argv is not None else sys.argv[1:]) if a != "--anchors"]
        worst = 0
        for width, height in ANCHOR_SIZES:
            print(f"== {ANCHOR_NAMES[(width, height)]} ==")
            worst = max(worst, main([*rest, "--size", f"{width}x{height}"]))
        # the phone: the words, the scroll rule and a name on one line (item 6); the press targets and the sheets are the tablet's
        print(f"== {ANCHOR_NAMES[PHONE_SIZE]} ==")
        phone = [a for a in rest if a not in ("--layout", "--rules", "--interact", "--labels")]
        worst = max(worst, main([*phone, "--size", f"{PHONE_SIZE[0]}x{PHONE_SIZE[1]}"], names=args.rules))
        # the big screen: the board only, its words and (with --interact) its way out
        print(f"== {ANCHOR_NAMES[BIG_SCREEN]} ==")
        big = [a for a in rest if a not in ("--layout", "--labels", "--scroll")]
        worst = max(worst, main([*big, "--board", "--size", f"{BIG_SCREEN[0]}x{BIG_SCREEN[1]}"]))
        return worst
    check_names = args.rules if names is None else names
    if args.board:
        args.routes, args.group = ["board"], None
    args.routes = routes_for(args.group, args.routes)
    values: dict[str, str] = {}
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
        if any("{ARCHIVED}" in route for route in args.routes):  # item 6: a game the server's archive holds, once it answers
            archived = archive_route_value(base, values.get("LAST", ""))
            args.routes = [fill(route, {"ARCHIVED": archived}) for route in args.routes]
        failures = 0
        with tempfile.TemporaryDirectory(prefix="kickoff-page-check-", ignore_cleanup_errors=True) as profile:
            browser = Edge(edge, profile, args.size)
            print(f"Viewport {args.size[0]}x{args.size[1]}, {len(args.routes)} route(s).")
            unexplained: dict[str, list[str]] = {}
            stretches: list[tuple[str, dict]] = []
            breaks: list[tuple[str, dict]] = []
            boxes: list[tuple[str, dict]] = []
            wraps: list[tuple[str, dict]] = []
            sheets: list[tuple[str, dict]] = []
            used: dict[str, int] = {}  # the sheet check's trigger kinds opened so far
            menu_spot = args.interact and args.size[0] >= SHEET_MIN_WIDTH
            try:
                results = []
                for route in args.routes:
                    results.append((route, *check_page(browser, f"{base}/#{route}", args.budget)))
                    if args.scroll:
                        for row in browser.scroll_boxes():
                            boxes.append((route, row))
                    if args.rules:
                        for row in browser.rule_breaks():
                            breaks.append((route, row))
                    if args.layout:
                        for row in browser.stretched():
                            stretches.append((route, row))
                    if args.labels:
                        for label in browser.labels(UNEXPLAINED_JS):
                            unexplained.setdefault(label, []).append(route)
                    if check_names:
                        for row in browser.wrapped_names():
                            wraps.append((route, row))
                    if menu_spot and route.split("?")[0].split("=")[0] not in SHEET_SKIP:  # last: it opens a sheet and the menu
                        sheet = check_sheet(browser, used, check_names)
                        sheets.append((route, sheet))
                        for row in sheet["names"]:
                            wraps.append((f"{route} ({sheet['sheet']})", row))
                if args.labels:
                    browser.text_of(f"{base}/#roster", args.budget)
                    for label in browser.labels(PLAYER_TABS_JS):
                        unexplained.setdefault(label, []).append("player card")
                if args.interact and args.board:  # the big screen: the board's way out is its one interaction
                    failures += report("the board's way out", *check_board(browser, base, args.budget))
                elif args.interact:
                    failures += run_flows(browser, base, args.budget)
                    failures += report_sheets(sheets, args.size[0])
                    failures += report("the board's way out", *check_board(browser, base, args.budget))
                    failures += report("a file that does not arrive", *check_boot(browser, base, args.budget))
                team_names = league_names() if args.labels and args.url is None else set()
                unexplained = {k: v for k, v in unexplained.items() if k.strip().rstrip(":.").lower() not in PLAIN_LABELS | team_names}
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
        if args.scroll:
            if boxes:
                failures += 1
                print(f"{len(boxes)} scroll box(es): something on the page scrolls up and down inside itself (show it whole; fold its band):")
                for route, row in boxes:
                    print(f"       #{route}  {row['where']} {row['element']} x{row['count']}  {row['over']} px more than its {row['box']} px box")
            else:
                print("No scroll boxes.")
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
        if check_names:
            if wraps:
                failures += 1
                print(f"{len(wraps)} player name(s) on two lines (a name never wraps: its table shortens it, docs/03-DESIGN.md):")
                for route, row in wraps:
                    print(f"       #{route}  {row['where']} {row['element']} x{row['count']}  {row['sample']!r} on {row['lines']} lines")
            else:
                print("No player name on two lines.")
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
