"""The flowing page, one column (static/js/ui/flow.js; owner 2026-11-01: "every band just to be a single band ... widens
with the screen and you can scroll up and down"), in the fake browser: one column at every width, nothing placed or
stretched, the packer's old placement cleared, the wide bands marked for the whole width, a band added later marked too,
and a harmless handle for nothing."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fakedom import needs_node, run_scenario

SCENARIOS = r"""
scenarios.flow = async () => {
  const { flow, columnsFor, mountFlow, stopFlow } = await import(moduleUrl("ui/flow.js"));
  assert.deepEqual([0, 375, 699, 700, 1180, 1920, 2500, 3440, NaN].map(columnsFor), [1, 1, 1, 1, 1, 1, 1, 1, 1], "one column at every width");
  const box = (w, h) => () => ({ width: w, height: h, top: 0, left: 0, right: w, bottom: h });
  const page = document.createElement("div");
  page.classList.add("page");
  page.getBoundingClientRect = box(1920, 0);
  const make = (id, h, cls) => { const d = document.createElement("section"); d.id = id; d.classList.add("band"); if (cls) d.classList.add(cls); d.getBoundingClientRect = box(400, h); page.append(d); return d; };
  const cover = make("cover", 500, "flow-full");
  const tape = make("tape", 1000);
  const table = make("table", 300, "flow-wide");
  const stale = make("stale", 100);
  // a page drawn by the packer of before: its placement is cleared
  stale.style.gridColumn = "2 / span 1"; stale.style.gridRowStart = "41"; stale.style.gridRowEnd = "span 9"; stale.style.minHeight = "620px"; stale.classList.add("flow-hold");
  document.body.append(page);
  const f = flow(page, { wide: ["tape"] });
  assert.ok(page.className.includes("flow"));
  assert.equal(page.dataset.cols, "1", "a 1920 px screen: one column");
  assert.equal(page.style["--flow-cols"], "1");
  for (const band of [cover, tape, table, stale]) {
    assert.equal(band.style.gridColumn, "", `${band.id}: nothing placed`);
    assert.equal(band.style.gridRowStart, "");
    assert.equal(band.style.gridRowEnd, "");
    assert.equal(band.style.minHeight, "", `${band.id}: nothing stretched`);
    assert.ok(!band.className.includes("flow-hold"));
  }
  assert.ok(tape.className.includes("band--wide"), "a band in the wide list keeps the whole width");
  assert.ok(table.className.includes("band--wide"), "a band marked .flow-wide by its view too");
  assert.ok(!cover.className.includes("band--wide") && !stale.className.includes("band--wide"), "the rest cap their content at the reading width (components.css)");
  // a wrapper around one band passes the mark to the band, whose body the cap measures
  const wrap = document.createElement("div");
  wrap.classList.add("flow-wide");
  const inner = document.createElement("section");
  inner.classList.add("band");
  wrap.append(inner);
  page.append(wrap);
  f.relayout();
  assert.ok(inner.className.includes("band--wide"), "the wrapper's band is marked");
  f.stop();
  // mountFlow: the chips above the page, the flow started; stopFlow clears both
  const ui = {};
  const container = document.createElement("div");
  const page2 = document.createElement("div");
  page2.classList.add("page");
  page2.getBoundingClientRect = box(820, 0);
  const wide = document.createElement("section"); wide.id = "roster-table"; wide.classList.add("band"); page2.append(wide);
  mountFlow(ui, container, page2, { wide: ["roster-table"] });
  assert.ok(ui.flow && ui.chips, "the layout and the chips are kept");
  assert.equal(container.children.length, 2, "the chips row, then the page");
  assert.equal(page2.dataset.cols, "1");
  assert.ok(wide.className.includes("band--wide"));
  stopFlow(ui);
  assert.equal(ui.flow, null);
  assert.equal(ui.chips, null);
  mountFlow(ui, container, page2, { chips: false });
  assert.equal(container.children.length, 1, "no chips: the page alone");
  stopFlow(ui);
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
