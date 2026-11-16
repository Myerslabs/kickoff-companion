"""The notes laid out in the fake browser (Wave 5; owner 2026-11-15, "Build as drawn"): the keys, the numbers strip and the
matchup to watch draw from the program's resolved layout under the byline and over the sections; a piece the server left out
is not drawn, nothing at all draws the band as before, and damaged input never prints a raw value."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fakedom import needs_node, run_scenario

SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object Object\]/;
const text = (node) => (node ? node.textContent : "");

const LAYOUT = {
  conference: "SEC",
  keys: [
    { line: "Keep Philo upright.", text: "Kentucky's front faces a line that may start Caden Jones at right tackle." },
    { line: "Take the ball away.", text: null },
    { line: "Hold up without Thornton.", text: "The backups face Kenny Minchey." },
  ],
  numbers: [
    { team: "them", school: "Kentucky", metric: "profile:to_lost_pg", label: "Turnovers lost per game", value: 2.0, format: "1f", rank: 129, of: 138, conferenceRank: 15, conferenceOf: 16 },
    { team: "us", school: "Florida", metric: "profile:takeaways_pg", label: "Takeaways per game", value: 1.778, format: "1f", rank: 7, of: 138, conferenceRank: 1, conferenceOf: 16 },
    { team: "them", school: "Kentucky", metric: "profile:third", label: "Third down", value: 0.349, format: "pct", rank: 111, of: 138, conferenceRank: 16, conferenceOf: 16 },
    { team: "us", school: "Florida", metric: "profile:tfl_pg", label: "Tackles for loss per game", value: 6.889, format: "1f", rank: 13, of: 138, conferenceRank: null },
  ],
  watch: { line: "Florida's right side against Kentucky's front.", text: "Caden Jones may start at right tackle." },
  dropped: [],
};

scenarios.drawn = async () => {
  installWindow();
  const { notesLayout, figureText } = await import(moduleUrl("ui/notes-layout.js"));
  const root = notesLayout(LAYOUT, { year: 2026 });
  document.body.append(root);
  const t = text(root);
  assert.ok(!RAW.test(t), t);
  assert.ok(root.className.includes("nl--two"), "the keys and a side column");
  const keys = root.querySelectorAll(".nl-keys__item");
  assert.equal(keys.length, 3);
  assert.equal(text(keys[0].querySelector(".nl-keys__n")), "1");
  assert.equal(text(keys[0].querySelector(".nl-keys__line")), "Keep Philo upright.");
  assert.equal(text(keys[1].querySelector(".nl-keys__text")), "Take the ball away.", "a key without a sentence is its line alone");
  const cells = root.querySelectorAll(".nl-cell");
  assert.equal(cells.length, 4);
  assert.equal(text(cells[0].querySelector(".nl-cell__team")), "KENTUCKY");
  assert.ok(cells[0].querySelector(".nl-cell__team--them") && cells[1].querySelector(".nl-cell__team--us"));
  assert.equal(text(cells[0].querySelector(".nl-cell__value")), "2.0");
  assert.equal(text(cells[2].querySelector(".nl-cell__value")), "34.9%", "a rate to one decimal, as the notes write it");
  assert.ok(text(cells[0].querySelector(".rank-chip")).includes("129") && cells[0].querySelector(".rank-chip--bottom"));
  assert.ok(cells[1].querySelector(".rank-chip--top"));
  assert.equal(cells[0].querySelector(".rank-chip").getAttribute("href"), "#national=profile%3Ato_lost_pg?team=Kentucky&year=2026");
  assert.equal(text(cells[0].querySelector(".nl-cell__conf")), "SEC 15th");
  assert.equal(cells[3].querySelector(".nl-cell__conf"), null, "no conference rank, no line for it");
  assert.ok(text(root.querySelector(".nl-strip__foot")).includes("138 FBS teams"));
  assert.equal(text(root.querySelector(".nl-watch .nl-head")), "The matchup to watch");
  assert.ok(text(root.querySelector(".nl-watch__text")).startsWith("Florida's right side against Kentucky's front. Caden Jones"));
  assert.equal(figureText(null, "1f"), "–");
  assert.equal(figureText(0.5, "pct"), "50.0%");
};

scenarios.pieces = async () => {
  installWindow();
  const { notesLayout } = await import(moduleUrl("ui/notes-layout.js"));
  const keysOnly = notesLayout({ ...LAYOUT, numbers: [], watch: null });
  assert.ok(keysOnly.querySelector(".nl-keys") && !keysOnly.querySelector(".nl-strip") && !keysOnly.querySelector(".nl-watch"));
  assert.ok(!keysOnly.className.includes("nl--two"), "one piece, one column");
  const twoNumbers = notesLayout({ keys: [], numbers: LAYOUT.numbers.slice(0, 2), watch: LAYOUT.watch });
  assert.ok(!twoNumbers.querySelector(".nl-strip") && twoNumbers.querySelector(".nl-watch"), "two figures are not a strip");
  for (const bad of [null, undefined, "layout", 7, [], {}, { keys: "x", numbers: { a: 1 }, watch: [] }, { keys: [null, 5, { line: "" }], numbers: [{ value: "NaN" }], watch: { text: "no line" } }]) {
    assert.equal(notesLayout(bad), null, `nothing to draw from ${JSON.stringify(bad)}`);
  }
  const damaged = notesLayout({
    keys: [{ line: "One.", text: 5 }, { line: "Two." }, { line: "Three.", text: "Words." }],
    numbers: [{ team: "us", metric: "profile:a", value: 1, label: null, rank: "x" }, { team: "them", metric: "profile:b", value: 2 }, { team: 3, metric: "profile:c", value: 3, school: null, format: "weird" }],
    watch: { line: "Watch.", text: null },
  });
  document.body.append(damaged);
  assert.ok(!RAW.test(text(damaged)), text(damaged));
  assert.equal(damaged.querySelectorAll(".nl-cell").length, 3);
};

scenarios.band = async () => {
  installWindow();
  const { editorial } = await import(moduleUrl("ui/editorial.js"));
  const { notesLayout } = await import(moduleUrl("ui/notes-layout.js"));
  const root = editorial({ byline: { author: "Claude", writtenAt: "2026-11-14T18:00:00Z" }, sections: [{ heading: "Key matchups", paragraphs: ["Words here."] }], top: notesLayout(LAYOUT) });
  const kids = [...root.children].map((c) => c.className);
  assert.deepEqual(kids.slice(0, 3), ["editorial__byline", "nl nl--two", "editorial__grid"], "the layout under the byline, over the sections");
  const plain = editorial({ byline: { author: "Claude" }, sections: [{ heading: "H", paragraphs: ["P."] }], top: "not a node" });
  assert.equal(plain.querySelector(".nl"), null);
  assert.ok(plain.querySelector(".editorial__grid"), "the band as before");
};
"""


@needs_node
@pytest.mark.parametrize("scenario", ["drawn", "pieces", "band"])
def test_the_notes_layout_in_the_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)
