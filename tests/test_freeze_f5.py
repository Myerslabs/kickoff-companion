"""Freeze wave F5 (2026-10-20): In Game on one screen, the big screen as its mirror, your notes inside the program notes,
the menu entries.

- The stage kit (ui/stage.js): the win probability for us, the last play's words, the last-plays list, the drive lines.
- The shot chart's "both" view: the passes over the line of scrimmage, the runs under it, no switch.
- The notes carry "Note from <name>", the name from Settings; the Prefs model keeps it.
- The menu lists the Archive, the Season in review and the server status; the board's zoom fits the stage to the screen."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.prefs import Prefs
from tests.fakedom import needs_node, run_scenario


def test_prefs_keep_the_host_name():
    assert Prefs().hostName == ""
    assert Prefs(hostName="Pat").hostName == "Pat"
    with pytest.raises(ValueError):
        Prefs(hostName="x" * 41)


def test_page_notes_never_on_in_game():
    """Owner 2026-10-20: In Game fits one screen; a note at its top would push the rest off. The board never had one."""
    src = (Path(__file__).resolve().parents[1] / "static" / "js" / "ui" / "page-notes.js").read_text(encoding="utf-8")
    assert 'route !== "board" && route !== "live"' in src


SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object Object\]/;
const text = (node) => (node ? node.textContent : "");
const us = { name: "Swampwater Tech", abbr: "SWT" };
const them = { name: "Silver Dollar", abbr: "SLV" };
const play = (over) => ({ id: 1, period: 1, clock: { minutes: 2, seconds: 8 }, offense: "Silver Dollar", down: 1, distance: 10, yardsToGoal: 29, playType: "Passing Touchdown", yardsGained: 29, success: true, ppa: 3.43, scoring: true, text: "the long text", ...over });

scenarios.stageKit = async () => {
  const { wpSummary, lastPlayWords, playWords, lastPlaysList, driveLines, scoreCell, stripExtras } = await import(moduleUrl("ui/stage.js"));
  // the words for a play type
  assert.equal(playWords({ playType: "Passing Touchdown" }), "TD pass");
  assert.equal(playWords({ playType: "Rushing Touchdown" }), "TD run");
  assert.equal(playWords({ playType: "Pass Incompletion" }), "Incomplete pass");
  assert.equal(playWords({ playType: "Pass Reception" }), "Pass complete");
  assert.equal(playWords({ playType: "Rush" }), "Run");
  assert.equal(playWords({ playType: "Interception Return Touchdown" }), "Pick six");
  assert.equal(playWords({ playType: "Field Goal Good" }), "Field goal good");
  assert.equal(playWords({ playType: "Something New" }), "Something New", "an unknown type keeps its name");
  assert.equal(playWords(null), "Play");
  // the strip's last play line
  assert.equal(lastPlayWords(play(), { abbr: (school) => (school === "Silver Dollar" ? "SLV" : "SWT") }), "TD pass, +29 yds, SLV · +3.4 PPA · Q1 2:08");
  assert.equal(lastPlayWords(play({ down: 0, playType: "Kickoff", yardsGained: 0, ppa: null }), { abbr: () => "SLV" }), "Kickoff, SLV · Q1 2:08", "no yards or value on a kickoff");
  assert.equal(lastPlayWords(null), null);
  assert.equal(lastPlayWords("junk"), null);
  // our win probability: the latest reading, else the series' last point, flipped for the away side
  assert.deepEqual(wpSummary({ liveWinProbability: { homeWp: 0.361, series: [] } }, { usHome: false, pregame: 0.69 }), { pct: 0.639, kickoff: 0.69 });
  assert.deepEqual(wpSummary({ liveWinProbability: { series: [{ homeWp: 0.2 }, { homeWp: 0.75 }] } }, { usHome: true }), { pct: 0.75, kickoff: null });
  assert.deepEqual(wpSummary({ liveWinProbability: { homeWp: 7 } }, { usHome: true, pregame: 2 }), { pct: null, kickoff: null }, "out of range is unknown");
  assert.deepEqual(wpSummary(null, {}), { pct: null, kickoff: null });
  // the strip's extras
  const extras = stripExtras({ wp: { pct: 0.639, kickoff: 0.69 }, lastPlay: "TD pass, +29 yds, SLV", usAbbr: "SWT" });
  document.body.append(extras);
  assert.equal(text(extras.querySelector(".strip__wp-pct")), "64%");
  assert.ok(text(extras.querySelector(".strip__wp")).includes("SWT to win") && text(extras.querySelector(".strip__wp-kick")).includes("69% at kickoff"), text(extras));
  assert.equal(text(extras.querySelector(".strip__last-words")), "TD pass, +29 yds, SLV");
  assert.equal(stripExtras({ wp: {}, lastPlay: null }), null, "nothing known: nothing drawn");
  assert.ok(text(stripExtras({ wp: { pct: null, kickoff: 0.69 }, usAbbr: "SWT" })).includes("69%"), "before kickoff the pregame number");
  // the last five plays, newest first, nothing raw
  const plays = [play({ id: 9 }), play({ id: 8, offense: "Swampwater Tech", playType: "Rush", yardsGained: -3, success: false, ppa: -0.7, scoring: false, yardsToGoal: 75 }), play({ id: 7 }), play({ id: 6 }), play({ id: 5 }), play({ id: 4 }), play({ id: 3 }), "junk", null];
  const list = lastPlaysList({ plays, us, them, limit: 5 });
  document.body.append(list);
  assert.equal(list.querySelectorAll(".stage-play").length, 5);
  assert.ok(!RAW.test(text(list)), text(list));
  const second = list.querySelectorAll(".stage-play")[1];
  assert.ok(second.className.includes("stage-play--us") && text(second).includes("Run, −3 yds") && text(second).includes("1st & 10 at SWT 25"), text(second));
  assert.ok(list.querySelectorAll(".stage-play")[0].className.includes("stage-play--score"), "a scoring play is marked");
  assert.ok(text(lastPlaysList({ plays: [] })).includes("Plays appear after kickoff"));
  // the drive lines and the score cell
  assert.deepEqual(driveLines({ "Swampwater Tech": { drives: 4, pointsPerDrive: 3, opportunities: 2, threeAndOuts: 0 }, "Silver Dollar": { drives: 4, pointsPerDrive: 4.5 } }, "Swampwater Tech", "Silver Dollar"), [
    { label: "Drives", us: "4", them: "4" }, { label: "Points per drive", us: "3.0", them: "4.5" }, { label: "Scoring chances", us: "2", them: "–" }, { label: "Three and outs", us: "0", them: "–" },
  ]);
  const cell = scoreCell({ s: { homeLineScores: [21], awayLineScores: [14], homeScore: 21, awayScore: 14, driveSummary: {} }, us, them, usHome: false });
  document.body.append(cell);
  assert.ok(cell.querySelector(".qline") && cell.querySelectorAll(".stage-drives__row").length === 4 && !RAW.test(text(cell)), text(cell));
};

scenarios.shotChartBoth = async () => {
  const { shotChart } = await import(moduleUrl("ui/shot-chart.js"));
  const chart = { passes: { "deep-left": { attempts: 3, completions: 2, successRate: 0.667, yardsPerAttempt: 15.7 } }, runs: { left: { attempts: 5, successRate: 0.8, yardsPerAttempt: 6.6 }, middle: { attempts: 1, successRate: 0 } }, sacks: 1 };
  const node = shotChart({ chart, view: "both", team: "Swampwater Tech", fixed: true });
  document.body.append(node);
  assert.ok(node.querySelector(".shot-field--both"), "one field");
  assert.equal(node.querySelectorAll(".shot-row").length, 3, "deep, short, then the runs");
  assert.ok(node.querySelector(".shot-row--runs") && node.querySelector(".shot-field__los"), "the runs under the line of scrimmage");
  assert.equal(node.querySelector(".shot-chart__seg"), null, "no Passes and Runs switch");
  assert.equal(node.querySelector(".note"), null, "no note: the band's summary carries the counts");
  const { shotCounts } = await import(moduleUrl("ui/shot-chart.js"));
  assert.equal(shotCounts(chart), "3 passes, 6 runs, 1 sack");
  assert.equal(shotCounts(null), "0 passes, 0 runs");
  assert.ok(!RAW.test(text(node)) && !text(node).includes("Success is CFBD"), text(node));
  assert.ok(!RAW.test(text(shotChart({ chart: "junk", view: "both" }))), "a damaged chart draws dashes");
};

scenarios.notesAndMenu = async () => {
  const { noteAuthor } = await import(moduleUrl("ui/game-notes.js"));
  assert.equal(noteAuthor("  Pat "), "Pat");
  assert.equal(noteAuthor(""), "the host", "no name set: the host");
  const { MENU } = await import(moduleUrl("ui/shell.js"));
  const views = MENU.find((g) => g.group === "Views").items.map((i) => i.label);
  assert.deepEqual(views.slice(-3), ["Preseason Magazine", "Archive", "Season in review"], "the Archive and the Season in review after the Magazine");
  const app = MENU.find((g) => g.group === "App").items;
  const status = app.find((i) => i.label === "Server status");
  assert.ok(status && status.href === "/status" && status.external === true, "the server's page, in a new tab");
  const { boardZoom } = await import(moduleUrl("views/board.js"));
  assert.equal(boardZoom(1180, 820), 1);
  assert.equal(boardZoom(1920, 1080), 1.32, "a 1080p set shows the stage a third bigger");
  assert.equal(boardZoom(3840, 2160), 2.63);
  assert.equal(boardZoom(844, 390), 1, "a phone cast sideways draws the essentials at their own size");
  assert.equal(boardZoom(1920), 1, "no height: the old answer");
};
"""


@needs_node
def test_the_stage_kit(tmp_path: Path) -> None:
    run_scenario(tmp_path, SCENARIOS, "stageKit")


@needs_node
def test_the_shot_chart_draws_both(tmp_path: Path) -> None:
    run_scenario(tmp_path, SCENARIOS, "shotChartBoth")


@needs_node
def test_the_notes_author_the_menu_and_the_zoom(tmp_path: Path) -> None:
    run_scenario(tmp_path, SCENARIOS, "notesAndMenu")
