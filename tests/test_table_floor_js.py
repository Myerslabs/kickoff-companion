"""The table kit's floor (wave 2 of the one-column page, 2026-11-01): a sized table that fits nowhere stays at small and
scrolls sideways inside its wrap (never clipped at the band's edge), while a table that fits never scrolls, so its header
sticks. The owner's rule (2026-10-10): "I would rather always show the minimal table"."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fakedom import needs_node, run_scenario

SCENARIOS = r"""
scenarios.floor = async () => {
  const { statTable } = await import(moduleUrl("ui/stat-table.js"));
  const { fits } = await import(moduleUrl("ui/sizes.js"));
  const columns = [
    { key: "name", label: "Player", kind: "text" },
    { key: "yds", label: "Yards" },
    { key: "td", label: "TD", size: "medium" },
    { key: "int", label: "INT", size: "small" },
  ];
  const rows = [{ name: "A. Passer", yds: 2991, td: 17, int: 4 }, { name: "B. Passer", yds: 2682, td: 18, int: 9 }];
  const make = (room, wide) => {
    const wrap = statTable({ compact: true, sizes: true, columns, rows, caption: "floor" });
    document.body.append(wrap);
    const table = wrap.querySelector("table");
    Object.defineProperty(wrap, "clientWidth", { value: room, configurable: true });
    Object.defineProperty(table, "offsetWidth", { value: wide, configurable: true });
    return { wrap, table };
  };
  // wider than its room at every size: the floor, shown small and scrolled sideways
  const narrow = make(373, 400);
  assert.equal(fits(narrow.wrap, narrow.table), false);
  narrow.wrap.measure();
  assert.equal(narrow.wrap.dataset.size, "small", "the smallest size stays");
  assert.ok(narrow.wrap.className.includes("stat-table-wrap--scrolls"), "it scrolls sideways in its wrap instead of being clipped (wave 2, 2026-11-01)");
  assert.ok(!narrow.wrap.className.includes("stat-table-wrap--fits"), "its header does not stick: there is no box to stick in");
  // room enough: no scroll box, the header sticks
  const roomy = make(900, 400);
  assert.equal(fits(roomy.wrap, roomy.table), true);
  roomy.wrap.measure();
  assert.ok(roomy.wrap.className.includes("stat-table-wrap--fits"));
  assert.ok(!roomy.wrap.className.includes("stat-table-wrap--scrolls"), "a table that fits never scrolls");
  // the room grows later: the scroll box goes
  Object.defineProperty(narrow.wrap, "clientWidth", { value: 900, configurable: true });
  narrow.wrap.measure();
  assert.ok(narrow.wrap.className.includes("stat-table-wrap--fits") && !narrow.wrap.className.includes("stat-table-wrap--scrolls"), "measured again with room: it fits");
};
"""


@needs_node
@pytest.mark.parametrize("scenario", ["floor"])
def test_the_tables_floor_in_a_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)
