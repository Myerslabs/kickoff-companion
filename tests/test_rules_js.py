"""The rules wave (Design rules, owner 2026-10-21): two tables side by side end on one line, a stat number links to its list
like its chip, a term's tap opens the card where the question mark has no room, every open issue is an item of one note, and
our team's name leads to the Season page."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.fakedom import needs_node, run_scenario

JS = Path(__file__).resolve().parents[1] / "static" / "js"

SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object Object\]/;
const text = (node) => (node ? node.textContent : "");

scenarios.matched = async () => {
  const { matchRows, statTable, twoCol } = await import(moduleUrl("ui/stat-table.js"));
  const columns = [{ key: "name", label: "Player", kind: "text" }, { key: "yds", label: "Yards" }];
  const long = statTable({ compact: true, columns, rows: [{ name: "A", yds: 1 }, { name: "B", yds: 2 }, { name: "C", yds: 3 }], caption: "long" });
  const short = statTable({ compact: true, columns, rows: [{ name: "D", yds: 4 }], caption: "short" });
  const pair = twoCol(long, short, null);
  document.body.append(pair);
  assert.equal(pair.className, "twocol");
  assert.equal(pair.children.length, 2, "a null part is left out");
  const rows = (table) => table.querySelectorAll("tbody tr");
  assert.equal(rows(long).length, 3);
  assert.equal(rows(short).length, 3, "the shorter table is padded to the longer one's length");
  const pads = rows(short).filter((tr) => tr.className.includes("is-pad"));
  assert.equal(pads.length, 2);
  assert.ok(pads.every((tr) => tr.getAttribute("aria-hidden") === "true" && tr.querySelectorAll("td").length === 2), "a pad row has one blank cell per column and is not read out");
  assert.ok(!RAW.test(text(pair)));
  // run again: the pad is replaced, never doubled; a pair with one table, or none, is left alone
  matchRows(pair);
  assert.equal(rows(short).length, 3);
  const lone = twoCol(statTable({ compact: true, columns, rows: [{ name: "E", yds: 5 }] }), document.createElement("div"));
  assert.equal(lone.querySelectorAll("tr.is-pad").length, 0);
  assert.equal(matchRows(null), null);
  assert.ok(matchRows(document.createElement("div")));
};

scenarios.links = async () => {
  const { twoTeamTable } = await import(moduleUrl("ui/two-team.js"));
  const { statTable } = await import(moduleUrl("ui/stat-table.js"));
  const rows = [
    { label: "Points per game", format: "1f", metric: "profile:ppg", us: { value: 31.2, rank: 8, of: 134 }, them: { value: 24.1, rank: 40, of: 134 } },
    { label: "Turnovers", format: "0f", us: { value: 3 }, them: { value: null } },
  ];
  const table = twoTeamTable({ rows, usAbbr: "SWT", themAbbr: "OPP", usTeam: "Swampwater Tech", themTeam: "Diner Tech", tug: true, caption: "links" });
  document.body.append(table);
  const cells = table.querySelectorAll("td.tt__cell");
  const linked = cells.filter((td) => td.className.includes("tt__cell--link"));
  assert.equal(linked.length, 2, "a value with a list behind it links, on both sides");
  const a = linked[0].querySelector("a.tt__val-link");
  assert.ok(a && a.getAttribute("href") === "#national=profile%3Appg?team=Swampwater%20Tech", "our number opens the list on our row");
  assert.ok(a.querySelector(".tt__val") && text(a).includes("31.2"), "the number itself is the link's words");
  assert.ok(cells.slice(2).every((td) => !td.querySelector("a")), "a row with no list, or no value, stays plain");
  // the same offer the chip makes, so the page's sheet can take it
  let offered = null;
  document.addEventListener("kickoff:rank-link", (event) => { offered = event.detail; event.preventDefault(); }, { once: true });
  a.click();
  assert.deepEqual([offered.href, offered.rank, offered.of], ["#national=profile%3Appg?team=Swampwater%20Tech", 8, 134]);
  // the stat table: a value cell with a linked chip links its number too
  const st = statTable({ compact: true, columns: [{ key: "team", label: "Team", kind: "text" }, { key: "ppg", label: "Points per game", format: "1f", rank: { key: "rank", of: 134, link: (row) => (row.rank ? `#national=profile%3Appg?team=${encodeURIComponent(row.team)}` : null) } }], rows: [{ team: "A", ppg: 30.5, rank: 3 }, { team: "B", ppg: 20.5, rank: null }], caption: "st" });
  document.body.append(st);
  const tds = st.querySelectorAll("tbody tr").map((tr) => tr.querySelectorAll("td")[1]);
  assert.ok(tds[0].querySelector("a.st__val-link") && text(tds[0].querySelector("a.st__val-link")) === "30.5" && tds[0].querySelector("a.rank-chip--link"), "the number and its chip both open the list");
  assert.ok(!tds[1].querySelector("a"), "no rank, no list: plain");
  assert.ok(!RAW.test(text(st)));
};

scenarios.notes = async () => {
  window.location.hash = "#program";
  const { addNote, noteShowing, removeNote } = await import(moduleUrl("ui/page-notes.js"));
  const slot = document.createElement("div");
  slot.className = "page-notes";
  slot.setAttribute("hidden", "");
  document.body.append(slot);
  let closedA = 0;
  let closedB = 0;
  const a = addNote({ id: "a", title: "Not loaded yet", body: "Open Load data.", onDismiss: () => { closedA += 1; } });
  const b = addNote({ id: "b", title: "A new version of the app is on the server", body: "Reload.", onDismiss: () => { closedB += 1; } });
  const c = addNote({ id: "c", title: "Elsewhere", body: "x", when: (route) => route === "season" });
  assert.equal(slot.querySelectorAll(".page-note").length, 1, "one note for every open issue (Design rules, owner 2026-10-21)");
  assert.equal(slot.querySelectorAll(".page-note__close").length, 1, "one close button");
  assert.equal(slot.querySelectorAll(".page-note__item").length, 3);
  assert.equal(text(slot.querySelector(".page-note__title")), "To do (2)", "the count of what shows here");
  assert.ok(noteShowing("a") && noteShowing("b") && !noteShowing("c"), "an item shows on the routes it names");
  assert.ok(c.hasAttribute("hidden") && !a.hasAttribute("hidden"));
  assert.ok(text(a).includes("Not loaded yet") && text(a).includes("Open Load data."), "an item: its title and how to put it right");
  slot.querySelector(".page-note__close").click();
  assert.deepEqual([closedA, closedB], [1, 1], "the one close button dismisses every item on screen, each telling its owner");
  assert.ok(!noteShowing("a") && !noteShowing("b"));
  assert.ok(slot.hasAttribute("hidden") && slot.querySelector(".page-note") && slot.querySelector(".page-note").hasAttribute("hidden"), "an item that waits for another page keeps the note, hidden");
  assert.ok(removeNote("c"));
  assert.equal(slot.querySelector(".page-note"), null, "the last item gone, the note goes");
  const again = addNote({ id: "d", title: "Again", body: "y" });
  assert.ok(again && slot.querySelector(".page-note") && text(slot.querySelector(".page-note__title")) === "To do");
  assert.ok(!RAW.test(text(slot)));
};

"""


@needs_node
@pytest.mark.parametrize("scenario", ["matched", "links", "notes"])
def test_rules_in_a_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)


def test_our_team_name_leads_to_the_season_page_and_the_screens_are_set() -> None:
    app = (JS / "app.js").read_text(encoding="utf-8")
    assert 'event.detail === usSchool()) window.location.hash = "season"' in app, "ours to the Season page, others to the flyout"
    flow = (JS / "ui" / "flow.js").read_text(encoding="utf-8")
    assert "const BREAKS = [[2500, 4], [1700, 3], [700, 2]];" in flow
    from tools import page_check

    assert page_check.DEFAULT_SIZE == (820, 1180) and page_check.ANCHOR_SIZES[0] == (820, 1180), "the iPad held upright is the anchor"
    dom = (JS / "ui" / "dom.js").read_text(encoding="utf-8")
    assert re.search(r'case "pct": return fmtPct\(value, 0\)', dom), "whole-number rates in tables"


def test_a_term_at_small_wears_a_dotted_underline_and_its_tap_opens_the_card() -> None:
    hints = (JS / "ui" / "hints.js").read_text(encoding="utf-8")
    assert "const markHidden = !mark || typeof mark.getClientRects !== \"function\" || mark.getClientRects().length === 0;" in hints
    assert "const href = markHidden ? null : listFor(byId.get(target.dataset.hint));" in hints, "no room for the mark: the tap opens the card, not the list"
    css = (JS.parent / "css" / "components.css").read_text(encoding="utf-8")
    assert '.tt-wrap[data-size="small"] [data-hint], .stat-table-wrap[data-size="small"] [data-hint] { text-decoration: underline dotted;' in css
