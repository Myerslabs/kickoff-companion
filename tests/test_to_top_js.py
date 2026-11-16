"""The Top button (owner 2026-11-15: "there needs to be an action to throw you back to the top of the page, as some pages are a
little long"; his pick, a floating button at the bottom right): one on the page, down until a screen of scrolling, up until back
above half a screen (no blink on a small scroll back), a tap to the page's top (straight there when the reader asked for less
motion), never over the game-day board or a sheet or the card, and quiet on a page with no window to listen to."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fakedom import needs_node, run_scenario

ROOT = Path(__file__).resolve().parents[1]

SCENARIOS = r"""
const down = (button) => button.hasAttribute("hidden");

scenarios.showAndGo = async () => {
  const win = installWindow({ scrollY: 0 });
  win.innerHeight = 1000;
  win.matchMedia = (q) => ({ matches: false, media: q });
  const asked = [];
  const scrollTo = win.scrollTo;
  win.scrollTo = (x, y) => { asked.push(x); scrollTo(x, y); };
  const { installToTop } = await import(moduleUrl("ui/to-top.js"));
  const button = installToTop();
  assert.ok(button && button.parentNode === document.body, "on the page");
  assert.equal(installToTop(), button, "a second call hands back the same button");
  assert.equal(document.body.querySelectorAll(".to-top").length, 1, "once");
  assert.equal(button.getAttribute("type"), "button");
  assert.equal(button.getAttribute("aria-label"), "Back to the top of the page");
  assert.ok(button.textContent.includes("Top"));
  assert.ok(down(button), "down at the top of the page");
  const scroll = (y) => { win.scrollY = y; win.dispatchEvent(makeEvent("scroll")); };
  scroll(800);
  assert.ok(down(button), "not before a screen down");
  scroll(1000);
  assert.ok(!down(button), "up from one screen down");
  scroll(600);
  assert.ok(!down(button), "a small scroll back keeps it, so it never blinks");
  scroll(400);
  assert.ok(down(button), "gone above half a screen");
  scroll(5000);
  button.click();
  assert.equal(win.scrollY, 0, "a tap takes the page to its top");
  assert.deepEqual(asked[asked.length - 1], { top: 0, behavior: "smooth" });
  win.dispatchEvent(makeEvent("scroll"));
  assert.ok(down(button), "and goes away there");
  // less motion asked for: straight there
  win.matchMedia = (q) => ({ matches: /reduce/.test(q), media: q });
  scroll(5000);
  button.click();
  assert.deepEqual(asked[asked.length - 1], { top: 0, behavior: "auto" });
  // an older browser that takes only the two numbers
  win.scrollTo = (x, y) => {
    if (typeof x === "object") throw new TypeError("no options");
    scrollTo(x, y);
  };
  scroll(5000);
  button.click();
  assert.equal(win.scrollY, 0);
  win.scrollTo = scrollTo;
  // a taller window: the same scroll is less than a screen
  scroll(1500);
  assert.ok(!down(button));
  win.innerHeight = 4000;
  win.dispatchEvent(makeEvent("resize"));
  assert.ok(down(button), "a resize looks again");
  win.innerHeight = 1000;
  // a new page starts at its top
  scroll(3000);
  win.scrollY = 0;
  win.dispatchEvent(makeEvent("hashchange"));
  assert.ok(down(button), "a route change looks again");
  console.log("ok showAndGo");
};

scenarios.covered = async () => {
  const win = installWindow({ scrollY: 0 });
  win.innerHeight = 1000;
  const { installToTop } = await import(moduleUrl("ui/to-top.js"));
  const button = installToTop();
  const scroll = (y) => { win.scrollY = y; win.dispatchEvent(makeEvent("scroll")); };
  scroll(3000);
  assert.ok(!down(button));
  // the game-day board
  document.body.classList.add("board-mode");
  scroll(3001);
  assert.ok(down(button), "never on the board");
  document.body.classList.remove("board-mode");
  scroll(3002);
  assert.ok(!down(button));
  // a side sheet or the player card lies on the page where the reader is: the page's top would leave it behind
  for (const cls of ["sheet-layer", "card-layer"]) {
    const layer = document.createElement("div");
    layer.className = cls;
    document.body.append(layer);
    scroll(3003);
    assert.ok(down(button), `not while a ${cls} is open`);
    layer.remove();
    scroll(3004);
    assert.ok(!down(button), `back once the ${cls} closes`);
  }
  console.log("ok covered");
};

scenarios.junk = async () => {
  const { installToTop, shouldShow } = await import(moduleUrl("ui/to-top.js"));
  // the bare window of the plain scenarios has no listeners: nothing to put on the page
  assert.equal(installToTop(), null);
  assert.equal(document.body.querySelectorAll(".to-top").length, 0);
  for (const bad of [NaN, Infinity, -Infinity, "x", null, undefined, {}, []]) {
    assert.equal(shouldShow(bad, 1000, false), false, `scroll ${String(bad)}`);
    assert.equal(shouldShow(bad, 1000, true), false);
    assert.equal(shouldShow(5000, bad, false), false, `height ${String(bad)}`);
  }
  assert.equal(shouldShow(5000, 0, false), false, "no height, no button");
  assert.equal(shouldShow(5000, -10, true), false);
  assert.equal(shouldShow(1000, 1000, false), true);
  assert.equal(shouldShow(999, 1000, false), false);
  assert.equal(shouldShow(500, 1000, true), true);
  assert.equal(shouldShow(499, 1000, true), false);
  // a page with junk for its scroll never shows it
  const win = installWindow({ scrollY: 0 });
  win.innerHeight = "tall";
  const button = installToTop();
  win.scrollY = 99999;
  win.dispatchEvent(makeEvent("scroll"));
  assert.ok(down(button));
  console.log("ok junk");
};
"""


@needs_node
@pytest.mark.parametrize("scenario", ["showAndGo", "covered", "junk"])
def test_to_top(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)


def test_to_top_is_on_the_page_and_styled() -> None:
    app = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
    assert 'import { installToTop } from "./ui/to-top.js";' in app
    assert "  installToTop();" in app
    css = (ROOT / "static" / "css" / "components.css").read_text(encoding="utf-8")
    rule = css[css.index(".to-top {") :].split("}")[0]
    assert "position: fixed" in rule and "var(--dock-h, 0px)" in rule and "safe-area-inset-bottom" in rule, "above the radio dock and the home bar"
    assert "min-height: var(--tap)" in rule, "a full tap target"
    assert ".to-top[hidden] { display: none; }" in css, "hidden means gone, whatever the rule's display"
    assert "body.board-mode .to-top { display: none; }" in css
    printing = css[css.index("@media print {\n  .to-top") :].split("}")[0]
    assert "display: none" in printing
