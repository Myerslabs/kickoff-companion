"""Phase 19 in the fake browser: spoiler mode (hide, tap one to show, show all, off again) and the color-blind switch."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fakedom import needs_node, run_scenario

SCENARIOS = r"""
const text = (node) => (node ? node.textContent : "");

function fakeStorage() {
  const data = new Map();
  Object.defineProperty(globalThis, "window", { configurable: true, value: { localStorage: { getItem: (k) => (data.has(k) ? data.get(k) : null), setItem: (k, v) => data.set(k, String(v)) }, location: { hash: "" } } });
  return data;
}

scenarios.spoiler = async () => {
  const data = fakeStorage();
  const { installSpoiler, setSpoiler, spoilerOn, SPOILER_SELECTORS } = await import(moduleUrl("ui/spoiler.js"));
  installSpoiler();
  assert.equal(spoilerOn(), false);
  assert.ok(!document.body.classList.contains("spoiler-on"));
  assert.ok(SPOILER_SELECTORS.includes(".cover__score") && SPOILER_SELECTORS.includes(".sched__res") && SPOILER_SELECTORS.includes(".ticker__game"));
  setSpoiler(true);
  assert.equal(spoilerOn(), true);
  assert.ok(document.body.classList.contains("spoiler-on"));
  assert.equal(data.get("kickoff.spoiler"), "on", "kept in this browser");
  const bar = document.body.querySelector(".spoiler-bar");
  assert.ok(bar && text(bar).includes("scores are hidden"));
  // Show all, then hide again
  const button = bar.querySelector("button");
  assert.equal(text(button), "Show all");
  button.click();
  assert.ok(document.body.classList.contains("spoiler-all") && text(button) === "Hide again");
  button.click();
  assert.ok(!document.body.classList.contains("spoiler-all"));
  // off removes the bar and the class
  setSpoiler(false);
  assert.ok(!document.body.classList.contains("spoiler-on") && !document.body.querySelector(".spoiler-bar"));
  assert.equal(data.get("kickoff.spoiler"), "off");
};

scenarios.cvd = async () => {
  const data = fakeStorage();
  const { installCvd, setCvd, cvdOn } = await import(moduleUrl("ui/cvd.js"));
  installCvd();
  assert.equal(cvdOn(), false);
  setCvd(true);
  assert.ok(document.body.classList.contains("cvd-safe") && cvdOn());
  assert.equal(data.get("kickoff.cvd"), "on");
  data.set("kickoff.cvd", "on");
  document.body.classList.remove("cvd-safe");
  installCvd();
  assert.ok(document.body.classList.contains("cvd-safe"), "a saved choice is applied at start");
  setCvd(false);
  assert.ok(!document.body.classList.contains("cvd-safe"));
};
"""


@needs_node
@pytest.mark.parametrize("scenario", ["spoiler", "cvd"])
def test_phase19_looks_in_a_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)
