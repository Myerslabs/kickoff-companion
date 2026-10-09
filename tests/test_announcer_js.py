"""Phase 17 #15 in the fake browser: the announcer sits before every band summary with a number in it (the stat
blurbs), never before one without; he talks once when the blurb first scrolls into view, stays quiet for the same
blurb drawn again, and the Announcer setting hides him."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fakedom import needs_node, run_scenario

SCENARIOS = r"""
scenarios.blurbs = async () => {
  const seen = [];
  globalThis.IntersectionObserver = class {
    constructor(fn) { this.fn = fn; }
    observe(target) { seen.push({ target, fire: () => this.fn([{ isIntersecting: true, target }]) }); }
    unobserve() {}
  };
  const { announcer, applyAnnouncer, isBlurb, TALK_MS } = await import(moduleUrl("ui/announcer.js"));
  const { band } = await import(moduleUrl("ui/states.js"));
  assert.deepEqual([isBlurb("SWT better in 14 of 24"), isBlurb("tap a game"), isBlurb(null), isBlurb(12)], [true, false, false, false]);
  const withStat = band({ id: "b1", title: "Tale", summary: "SWT better in 14 of 24", body: () => document.createElement("div") });
  const plain = band({ id: "b2", title: "Picker", summary: "tap a game", body: () => document.createElement("div") });
  document.body.append(withStat, plain);
  assert.equal(withStat.querySelectorAll(".announcer").length, 1);
  assert.equal(plain.querySelectorAll(".announcer").length, 0);
  assert.ok(withStat.querySelector(".band__summary").textContent.includes("SWT better in 14 of 24"), "the blurb is still read");
  // he talks when the blurb shows, then stops
  const svg = withStat.querySelector(".announcer");
  seen.find((s) => s.target === svg).fire();
  assert.ok(svg.className.includes("announcer--talking") || svg.getAttribute("class").includes("announcer--talking"));
  await advance(TALK_MS + 10);
  assert.ok(!svg.getAttribute("class").includes("announcer--talking"));
  // the same blurb drawn again (a refresh) stays quiet; a new one is called
  const again = announcer("b1|SWT better in 14 of 24");
  seen.find((s) => s.target === again).fire();
  assert.ok(!again.getAttribute("class").includes("talking"));
  const fresh = announcer("b1|SWT better in 15 of 24");
  seen.find((s) => s.target === fresh).fire();
  assert.ok(fresh.getAttribute("class").includes("talking"));
  applyAnnouncer(false);
  assert.ok(document.documentElement.classList.contains("announcer-off"));
  applyAnnouncer(true);
  assert.ok(!document.documentElement.classList.contains("announcer-off"));
};

scenarios.noObserver = async () => {
  delete globalThis.IntersectionObserver;
  const { band } = await import(moduleUrl("ui/states.js"));
  const b = band({ id: "b3", title: "X", summary: "3 of 4", body: () => document.createElement("div") });
  assert.equal(b.querySelectorAll(".announcer").length, 1, "drawn still, just never animated");
};
"""


@needs_node
@pytest.mark.parametrize("scenario", ["blurbs", "noObserver"])
def test_announcer_in_a_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)
