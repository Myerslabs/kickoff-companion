"""ENH-17, a rank chip opens a chart (the owner's board of 2026-10-30, "Build it as drawn"): every team list a chip opens
carries the whole field above it, a dot a team placed by its value with better to the right, us and this week's opponent
marked with the value and rank, the quarters and the median, the scale; a tap on a dot centers that team's row."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fakedom import needs_node, run_scenario

SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object \w+\]/;
const text = (node) => (node ? node.textContent : "");
const num = (node, name) => Number(node.getAttribute(name));

function field(n, { higher = true } = {}) {
  const rows = [];
  for (let i = 0; i < n; i += 1) rows.push({ rank: i + 1, team: `Team ${i + 1}`, abbreviation: `T${i + 1}`, conference: "X", value: higher ? 30 - i * 0.4 : 10 + i * 0.4 });
  rows[37] = { ...rows[37], team: "Florida", abbreviation: "FLA", isUs: true };
  rows[1] = { ...rows[1], team: "Georgia", abbreviation: "UGA", isNext: true };
  return { metric: "rating:sp", family: "rating", label: "SP+", format: "1f", higherIsBetter: higher, unit: "team", scope: "national", of: n, rows, beyond: [], us: { team: "Florida", rank: 38 }, parts: {} };
}

scenarios.chart = async () => {
  installWindow();
  const { fieldChart, swarm, niceTicks } = await import(moduleUrl("ui/field-chart.js"));
  const { barScale } = await import(moduleUrl("ui/national-bars.js"));
  // the swarm: the same x three times stacks at 0, one step down, one step up; dots apart stay on the line
  const ys = swarm([100, 100, 100, 300], { r: 3, gap: 1 });
  assert.deepEqual(ys, [0, 7, -7, 0]);
  assert.deepEqual(swarm([5, null, 5], { r: 3, gap: 1 }), [0, 0, 7], "a missing x is left on the line, out of the way");
  // the scale's round values
  assert.deepEqual(niceTicks(-28, 28), [-20, -10, 0, 10, 20]);
  assert.deepEqual(niceTicks(0, 1, 5), [0, 0.2, 0.4, 0.6, 0.8, 1]);
  assert.deepEqual(niceTicks(5, 5), []);
  assert.deepEqual(niceTicks(null, 3), []);
  // the chart on a team list of 138
  const data = field(138);
  const scale = barScale(data.rows.map((r) => r.value), { higher: true });
  const block = fieldChart(data, scale);
  const svg = block.querySelector("svg");
  assert.ok(svg, "drawn");
  assert.equal(svg.querySelectorAll("circle").length, 138, "every team one dot");
  const us = svg.querySelector(".fc__dot--us");
  const them = svg.querySelector(".fc__dot--next");
  assert.ok(us && them, "us and this week's opponent marked");
  assert.ok(num(us, "r") > num(svg.querySelector(".fc__dot:not(.fc__dot--us):not(.fc__dot--next)") || svg.querySelectorAll(".fc__dot")[0], "r"), "larger");
  const labels = svg.querySelectorAll(".fc__label").map((t) => t.textContent);
  assert.ok(labels.includes("FLA 15.2 · 38th") && labels.includes("UGA 29.6 · 2nd"), labels.join(" | "));
  assert.ok(num(them, "cx") > num(us, "cx"), "better to the right");
  assert.ok(svg.querySelector(".fc__zone--top") && svg.querySelector(".fc__zone--low"), "the quarters");
  assert.ok(svg.querySelector(".fc__median"), "the median");
  assert.ok(text(svg).includes("worse") && text(svg).includes("better"), "the scale's ends");
  assert.ok(block.querySelector(".fc__chart").getAttribute("aria-label").includes("Florida 15.2, 38th"));
  assert.ok(!RAW.test(text(block)), text(block));
  // less is better: the lowest value sits on the right
  const low = field(40, { higher: false });
  const lowSvg = fieldChart(low, barScale(low.rows.map((r) => r.value), { higher: false })).querySelector("svg");
  const dots = lowSvg.querySelectorAll("circle");
  const cxOf = (team) => num(dots.find((c) => (c.querySelector("title")?.textContent || "").startsWith(team + " ")), "cx");
  assert.ok(cxOf("Team 1") > cxOf("Team 40"), "the best, lowest value, on the right");
  // nothing to draw
  assert.equal(fieldChart({ ...data, unit: "player" }, scale), null, "no chart on a player list");
  assert.equal(fieldChart({ ...data, family: "poll" }, scale), null, "nor on a poll");
  assert.equal(fieldChart({ ...data, rows: data.rows.slice(0, 2) }, scale), null, "fewer than three values");
  assert.equal(fieldChart(data, null), null);
  assert.equal(fieldChart({ rows: "junk" }, scale), null);
  const few = field(6);
  assert.equal(fieldChart(few, barScale(few.rows.map((r) => r.value))).querySelector(".fc__zone--top"), null, "no quarters on a short list");
  // a tap on a dot picks the nearest team within reach
  let picked = null;
  const tapped = fieldChart(data, scale, { onPick: (team) => { picked = team; } });
  const chart = tapped.querySelector(".fc__chart");
  const drawn = chart.querySelector("svg");
  drawn.getBoundingClientRect = () => ({ left: 0, top: 0, width: Number(drawn.getAttribute("width")), height: Number(drawn.getAttribute("height")) });
  const target = drawn.querySelector(".fc__dot--next");
  chart.dispatchEvent({ type: "click", bubbles: true, clientX: num(target, "cx") + 2, clientY: num(target, "cy") });
  assert.equal(picked, "Georgia");
  picked = null;
  chart.dispatchEvent({ type: "click", bubbles: true, clientX: 2, clientY: 2 });
  assert.equal(picked, null, "a tap far from every dot picks nothing");
};

scenarios.list = async () => {
  installWindow();
  const { nationalListBody, centerRow } = await import(moduleUrl("ui/national-sheet.js"));
  const data = field(20);
  const body = nationalListBody({ data });
  document.body.append(body);
  assert.ok(body.querySelector(".fc svg"), "the field above the list");
  const kids = body.children;
  const at = kids.indexOf(body.querySelector(".fc"));
  assert.ok(at > 0 && kids[at + 1].querySelector("table"), "right above the table");
  const row = centerRow(body, { team: "Team 7" });
  assert.ok(row && row.className.includes("nat-arrived") && text(row).includes("Team 7"), "a dot's team: its row centered and flashed");
  assert.equal(centerRow(body, { team: "Nobody" }), null, "an unknown team moves nothing");
};
"""


@needs_node
@pytest.mark.parametrize("scenario", ["chart", "list"])
def test_the_field_chart_in_a_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)
