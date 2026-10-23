"""Phase 17 #7, #10, #28 in the fake browser: the flowing page (static/js/ui/flow.js). Column count by width,
full and wide bands, row spans from each band's height, a plain stack on one column, and observers that stop. The flush
rows (the layout pass, owner 2026-10-22): a row's bands end on one line, a stack on one side ends level with the band
beside it, and a row short of bands gives its last band the columns left over."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fakedom import needs_node, run_scenario

SCENARIOS = r"""
scenarios.flow = async () => {
  const { flow, columnsFor } = await import(moduleUrl("ui/flow.js"));
  // the tablet lock (owner 2026-10-13): a browser wider than the iPad keeps its two columns, never a third or a fourth
  assert.deepEqual([0, 375, 699, 700, 1099, 1100, 1180, 1599, 1600, 3440, NaN].map(columnsFor), [1, 1, 1, 2, 2, 2, 2, 2, 2, 4, 1]);
  assert.deepEqual([1699, 1700, 1920, 2499, 2500].map(columnsFor), [2, 3, 3, 3, 4], "a 1080p screen gets three columns, an ultrawide four (Design rules, owner 2026-10-21)");
  const box = (w, h) => () => ({ width: w, height: h, top: 0, left: 0, right: w, bottom: h });
  const page = document.createElement("div");
  page.classList.add("page");
  page.getBoundingClientRect = box(1180, 0); // the iPad sideways: two columns (a 1920 px screen gets three since the Design rules of 2026-10-21, tested above)
  const make = (id, h, cls) => { const d = document.createElement("section"); d.id = id; if (cls) d.classList.add(cls); d.getBoundingClientRect = box(400, h); page.append(d); return d; };
  const cover = make("cover", 500, "flow-full");
  const weather = make("weather", 120);
  const tape = make("tape", 1000);
  const small = make("small", 46);
  document.body.append(page);
  const f = flow(page, { full: ["weather"], wide: ["tape"] });
  assert.ok(page.className.includes("flow"));
  assert.equal(page.dataset.cols, "2", "the iPad sideways: two columns");
  assert.equal(page.style["--flow-cols"], "2");
  // the order rule (owner 2026-10-13): each band placed below everything listed before it, no holes
  assert.equal(cover.style.gridColumn, "1 / span 2"); assert.equal(cover.style.gridRowStart, "1");
  assert.equal(weather.style.gridColumn, "1 / span 2"); assert.equal(weather.style.gridRowStart, "129", "500 px plus the gap over 4 px rows, under the cover");
  assert.equal(tape.style.gridColumn, "1 / span 2"); assert.equal(tape.style.gridRowStart, "162");
  assert.equal(small.style.gridRowStart, "415", "under the wide band, never beside it");
  assert.equal(small.style.gridColumn, "1 / span 2", "alone in the last row: it takes the column left over, no hole beside it");
  assert.equal(small.style.gridRowEnd, "span 15", "46 px plus the 12 px gap over 4 px rows");
  assert.equal(small.style.minHeight, "", "nothing beside it to end level with");
  assert.equal(tape.style.gridRowEnd, "span 253");
  // a tall band in one column, two short ones after it: the first short one sits beside it, the second under the first
  const tall = make("tall", 800);
  const a = make("a", 100);
  const b = make("b", 100);
  f.relayout();
  assert.equal(tall.style.gridColumn, "2 / span 1"); assert.equal(tall.style.gridRowStart, "415", "the second column had more room");
  assert.equal(a.style.gridColumn, "1 / span 1"); assert.equal(a.style.gridRowStart, "430", "beside the tall band, under small");
  assert.equal(b.style.gridColumn, "1 / span 1"); assert.equal(b.style.gridRowStart, "458", "under a; the tall band's column is further down");
  assert.equal(small.style.gridColumn, "1 / span 1", "a band beside it now: one column again");
  // flush (2026-10-22): the stack's last band reaches the tall band's bottom, the gap kept under it
  assert.equal(b.style.gridRowEnd, "span 160", "from row 458 to the tall band's last row at 618");
  assert.equal(b.style.minHeight, "628px", "down to the tall band's bottom to the pixel: 800 px less the 172 px a and small take above it");
  assert.equal(tall.style.minHeight, "", "the tallest band sets the line and keeps its own height, so its shrinking is noticed");
  assert.equal(a.style.minHeight, "", "only the last band of a stack stretches");
  // a tablet: two columns, and a wide band spans both (a big two-team table is cramped in one tablet column)
  page.getBoundingClientRect = box(820, 0);
  f.relayout();
  assert.equal(page.dataset.cols, "2");
  assert.equal(tape.style.gridColumn, "1 / span 2");
  // a phone: one column is a plain stack, no row spans
  page.getBoundingClientRect = box(375, 0);
  f.relayout();
  assert.equal(page.dataset.cols, "1");
  assert.equal(small.style.gridRowEnd, "");
  assert.equal(small.style.gridRowStart, "");
  assert.equal(b.style.minHeight, "", "a plain stack stretches nothing");
  assert.equal(cover.style.gridColumn, "1 / -1");
  f.stop();
  // three columns: a row fills left to right, a band that would not fit beside the tallest opens the next row, a wrapper
  // around one band passes the stretch to it, and a band drawn nowhere (display: none) takes no place
  const wide = document.createElement("div");
  wide.getBoundingClientRect = box(1920, 0);
  const add = (id, h, wrap) => {
    const d = document.createElement("section");
    d.id = id;
    d.classList.add("band");
    d.getBoundingClientRect = box(400, h);
    if (!wrap) { wide.append(d); return d; }
    const w = document.createElement("div");
    w.append(d);
    w.getBoundingClientRect = box(400, h);
    wide.append(w);
    return w;
  };
  const one = add("one", 400);
  const two = add("two", 100, true);
  const hidden = add("hidden", 0);
  const three = add("three", 200);
  const four = add("four", 500);
  document.body.append(wide);
  const g = flow(wide);
  assert.equal(wide.dataset.cols, "3");
  assert.deepEqual([one, two, three].map((n) => n.style.gridColumn), ["1 / span 1", "2 / span 1", "3 / span 1"], "one a column, left to right");
  assert.deepEqual([one, two, three].map((n) => n.style.gridRowStart), ["1", "1", "1"]);
  assert.equal(hidden.style.gridRowStart, "", "nothing drawn: no place");
  assert.equal(two.style.minHeight, "400px", "level with the tallest band of its row, to the pixel");
  assert.equal(three.style.minHeight, "400px");
  assert.equal(one.style.minHeight, "", "the tallest keeps its own height");
  assert.ok(two.className.includes("flow-hold"), "the wrapper hands the room to its band");
  assert.equal(four.style.gridRowStart, String(1 + Math.ceil((400 + 12) / 4)), "500 px does not fit beside the 400 px band: the next row");
  assert.equal(four.style.gridColumn, "1 / span 3", "alone in its row: every column");
  g.stop();
  // nothing to lay out: no crash, a harmless handle
  const none = flow(null);
  none.relayout();
  none.stop();
};
"""


@needs_node
@pytest.mark.parametrize("scenario", ["flow"])
def test_flow_in_a_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)
