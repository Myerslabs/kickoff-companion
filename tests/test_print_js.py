"""Phase 19: the print sheet (paper and orientation) and what printing does to the page."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fakedom import STATIC_JS, needs_node, run_scenario

SCENARIOS = r"""
const text = (node) => (node ? node.textContent : "");

scenarios.rule = async () => {
  const { pageRule, PAPERS } = await import(moduleUrl("ui/print.js"));
  assert.deepEqual(PAPERS.map((p) => p[0]), ["letter", "a4", "legal"]);
  assert.equal(pageRule("a4", "landscape"), "@page { size: A4 landscape; margin: 12mm; }");
  assert.equal(pageRule("letter", "portrait"), "@page { size: letter portrait; margin: 12mm; }");
  assert.equal(pageRule("nonsense", "sideways"), "@page { size: letter portrait; margin: 12mm; }", "a bad choice falls back, never prints garbage");
};

scenarios.print = async () => {
  const { printNow } = await import(moduleUrl("ui/print.js"));
  const listeners = [];
  let printed = 0;
  const win = { print: () => { printed += 1; }, addEventListener: (name, fn) => listeners.push([name, fn]), removeEventListener() {} };
  document.documentElement.dataset.theme = "dark";
  const done = printNow({ paper: "a4", orientation: "landscape" }, document, win);
  assert.equal(printed, 1);
  assert.equal(document.documentElement.dataset.theme, "light", "ink on white while printing");
  assert.ok(document.body.classList.contains("printing"));
  assert.equal((document.head || document.body).querySelector("#print-page").textContent, "@page { size: A4 landscape; margin: 12mm; }");
  assert.ok(listeners.some(([name]) => name === "afterprint"));
  done();
  assert.equal(document.documentElement.dataset.theme, "dark", "the screen's theme comes back");
  assert.equal((document.head || document.body).querySelector("#print-page"), null);
  assert.ok(!document.body.classList.contains("printing"));
};
"""


@needs_node
@pytest.mark.parametrize("scenario", ["rule", "print"])
def test_print_in_a_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)


def test_the_print_rules_hide_controls_and_open_folded_sections() -> None:
    css = (STATIC_JS.parent / "css" / "components.css").read_text(encoding="utf-8")
    block = css[css.index("@media print {"):]
    block = block[: block.index("\n}")]
    for needle in (".topbar", ".tabs", "button", ".band[data-collapsed=\"true\"] .band__body", "display: block !important", ".flow > *"):
        assert needle in block, needle
