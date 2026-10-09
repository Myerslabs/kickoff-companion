"""Phase 17 #7, #10, #28 in the fake browser: the flowing page (static/js/ui/flow.js). Column count by width,
full and wide bands, row spans from each band's height, a plain stack on one column, and observers that stop."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fakedom import needs_node, run_scenario

SCENARIOS = r"""
scenarios.flow = async () => {
  const { flow, columnsFor } = await import(moduleUrl("ui/flow.js"));
  assert.deepEqual([0, 375, 699, 700, 1099, 1100, 1599, 1600, 3440, NaN].map(columnsFor), [1, 1, 1, 2, 2, 3, 3, 4, 4, 1]);
  const box = (w, h) => () => ({ width: w, height: h, top: 0, left: 0, right: w, bottom: h });
  const page = document.createElement("div");
  page.classList.add("page");
  page.getBoundingClientRect = box(1920, 0);
  const make = (id, h, cls) => { const d = document.createElement("section"); d.id = id; if (cls) d.classList.add(cls); d.getBoundingClientRect = box(400, h); page.append(d); return d; };
  const cover = make("cover", 500, "flow-full");
  const weather = make("weather", 120);
  const tape = make("tape", 1000);
  const small = make("small", 46);
  document.body.append(page);
  const f = flow(page, { full: ["weather"], wide: ["tape"] });
  assert.ok(page.className.includes("flow"));
  assert.equal(page.dataset.cols, "4");
  assert.equal(page.style["--flow-cols"], "4");
  assert.equal(cover.style.gridColumn, "1 / -1");
  assert.equal(weather.style.gridColumn, "1 / -1");
  assert.equal(tape.style.gridColumn, "span 2");
  assert.equal(small.style.gridColumn, "");
  assert.equal(small.style.gridRowEnd, "span 15", "46 px plus the 12 px gap over 4 px rows");
  assert.equal(tape.style.gridRowEnd, "span 253");
  // a tablet: two columns, and a wide band spans both (a big two-team table is cramped in one tablet column)
  page.getBoundingClientRect = box(820, 0);
  f.relayout();
  assert.equal(page.dataset.cols, "2");
  assert.equal(tape.style.gridColumn, "span 2");
  // a phone: one column is a plain stack, no row spans
  page.getBoundingClientRect = box(375, 0);
  f.relayout();
  assert.equal(page.dataset.cols, "1");
  assert.equal(small.style.gridRowEnd, "");
  f.stop();
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
