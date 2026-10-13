"""No scroll box inside a page (owner 2026-10-10, his phone): nothing on a page scrolls up and down inside itself. On a
touch screen a box that scrolls inside the page keeps the finger once its own end is reached, so the page under the
pinned section chips and the Leaders bar would not move. Tables and lists show whole; their bands fold instead.

Static checks over the stylesheets and the scripts: every rule that lets an element scroll either belongs to one of the
reader's own layers (a side sheet, the menu, the player card, an open drop-down) or scrolls sideways only, with its
up-and-down overflow hidden; no table or play list is built with a height. The page check's --scroll rule
(tools/page_check.py) measures the same thing in a real browser at every anchor screen and on a phone."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.fakedom import needs_node, run_scenario

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"
SHEETS = [STATIC / "css" / "components.css", STATIC / "css" / "app.css"]

# The reader's own layers: each is fixed over the page (or drops down over it) and scrolls on its own. The status card
# (item 6: it lists what is not loaded yet) hangs from the top bar the same way.
LAYERS = (".drawer__panel", ".player-card", ".side-sheet__body", ".jump__panel", ".status-card")
SCROLLS = re.compile(r"\boverflow(-y)?\s*:\s*(auto|scroll|overlay)\b")
SIDEWAYS = re.compile(r"\boverflow-x\s*:\s*(auto|scroll|overlay)\b")
HIDES_Y = re.compile(r"\boverflow-y\s*:\s*(hidden|clip)\b")


def rules(css: str) -> list[tuple[str, str]]:
    """Every innermost `selector { declarations }` block, with comments dropped (at-rule wrappers are skipped)."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    return [(sel.strip(), body) for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css)]


def test_the_rules_parse() -> None:
    found = [sel for sheet in SHEETS for sel, _ in rules(sheet.read_text(encoding="utf-8"))]
    assert len(found) > 500
    assert any(".side-sheet__body" in sel for sel in found)


@pytest.mark.parametrize("sheet", SHEETS, ids=lambda p: p.name)
def test_nothing_on_a_page_scrolls_up_and_down(sheet: Path) -> None:
    broken = []
    for selector, body in rules(sheet.read_text(encoding="utf-8")):
        if selector.startswith("@") or all(any(layer in part for layer in LAYERS) for part in selector.split(",")):
            continue
        if SCROLLS.search(body) and not HIDES_Y.search(body):
            broken.append(f"{selector}: scrolls up and down")
        elif SIDEWAYS.search(body) and not HIDES_Y.search(body):
            broken.append(f"{selector}: overflow-x alone lets it scroll up and down too (add overflow-y: hidden)")
        if re.search(r"\bmax-height\s*:", body) and (SCROLLS.search(body) or SIDEWAYS.search(body)):
            broken.append(f"{selector}: a scroll box with a height")
    assert not broken, "\n".join(broken)


def test_no_table_or_play_list_is_built_with_a_height() -> None:
    scripts = [p for p in (STATIC / "js").rglob("*.js") if p.name != "debug-live.js"]  # the replay debug page is a test tool
    hits = [f"{p.relative_to(ROOT)}:{n}" for p in scripts for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1) if re.search(r"\bmaxHeight\s*:|--table-max|--plays-max", line)]
    assert not hits, "a boxed table or play list:\n" + "\n".join(hits)
    css = "\n".join(sheet.read_text(encoding="utf-8") for sheet in SHEETS)
    for word in ("--table-max", "--plays-max", "stat-table-wrap--box"):
        assert word not in css, word


SCENARIOS = r"""
scenarios.tables = async () => {
  const { statTable } = await import(moduleUrl("ui/stat-table.js"));
  const rows = Array.from({ length: 60 }, (_, i) => ({ a: i }));
  const wrap = statTable({ columns: [{ key: "a", label: "A" }], rows, maxHeight: 400 }); // an old caller's height is ignored
  assert.ok(!wrap.className.includes("--box"), wrap.className);
  assert.equal(wrap.style["--table-max"], undefined);
  assert.equal(wrap.querySelectorAll("tbody tr").length, 60, "every row on the page");
};

scenarios.fold = async () => {
  // folding a long band from its pinned head keeps the head where it was on screen (the reader is not thrown down the page)
  installWindow();
  const { band } = await import(moduleUrl("ui/states.js"));
  const section = band({ id: "fold-test", title: "Long", collapsible: false, foldable: true, body: () => "rows" });
  document.body.append(section);
  const head = [...section.children].find((n) => n.className.includes("band__head"));
  section.getBoundingClientRect = () => ({ top: -3000, height: 3200 }); // scrolled 3,000 px into the band
  head.getBoundingClientRect = () => ({ top: 100, height: 45 }); // its head pinned 100 px down the screen
  window.scrollY = 5000;
  section.setCollapsed(true, { animate: true });
  assert.equal(section.dataset.collapsed, "true");
  assert.equal(window.scrollY, 1900, "the folded head stays 100 px down the screen");
  // a band whose top is on screen folds where it is
  section.setCollapsed(false);
  section.getBoundingClientRect = () => ({ top: 300, height: 600 });
  head.getBoundingClientRect = () => ({ top: 300, height: 45 });
  window.scrollY = 800;
  section.setCollapsed(true);
  assert.equal(window.scrollY, 800);
};

scenarios.plays = async () => {
  const { playLog } = await import(moduleUrl("ui/play-log.js"));
  const plays = Array.from({ length: 30 }, (_, i) => ({ id: String(i), offense: "Us", period: 1, text: `Rush for ${i}` }));
  const log = playLog({ plays, us: { name: "Us", abbr: "US" }, them: { name: "Them", abbr: "TH" }, maxHeight: 440 });
  const list = log.querySelector(".plays");
  assert.ok(list);
  assert.equal(list.style["--plays-max"], undefined);
};
"""


@needs_node
@pytest.mark.parametrize("name", ["tables", "plays", "fold"])
def test_scroll_boxes_js(tmp_path: Path, name: str) -> None:
    run_scenario(tmp_path, SCENARIOS, name)
