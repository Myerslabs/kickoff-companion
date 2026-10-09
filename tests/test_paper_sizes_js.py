"""Phase 19: the newspaper's story sizes (steady, mixed, never two features in a row) and its new pictures."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fakedom import needs_node, run_scenario

SCENARIOS = r"""
scenarios.sizes = async () => {
  const { storySizes } = await import(moduleUrl("views/newspaper.js"));
  const items = Array.from({ length: 60 }, (_, i) => ({ title: `Story number ${i} about the week` }));
  const sizes = storySizes(items);
  assert.equal(sizes.length, 60);
  assert.deepEqual(storySizes(items), sizes, "the same stories are always the same sizes");
  assert.ok(["s", "m", "l"].every((s) => sizes.includes(s)), "a real mix: " + sizes.join(""));
  assert.notEqual(sizes[0], "l", "the first story after the lead is never a feature");
  for (let i = 1; i < sizes.length; i += 1) assert.ok(!(sizes[i] === "l" && sizes[i - 1] === "l"), "no two features in a row");
  const small = sizes.filter((s) => s === "s").length;
  assert.ok(small > sizes.length / 3, "most stories stay small");
  assert.deepEqual(storySizes(null), []);
  assert.deepEqual(storySizes([null, {}, { title: 5 }]).length, 3, "damaged rows still get a size");
};

scenarios.pictures = async () => {
  const { TOPICS, pixelPicture, pixelBanner } = await import(moduleUrl("ui/pixel-art.js"));
  for (const topic of ["practice", "trophy", "rankings", "stadium", "scoreboard"]) assert.ok(TOPICS.includes(topic), topic);
  for (const topic of TOPICS) {
    const pic = pixelPicture({ topic, seed: 7, label: topic });
    assert.equal(pic.getAttribute("role"), "img");
  }
  assert.equal(pixelPicture({ topic: "nonsense", seed: 1 }).getAttribute("role"), "img", "an unknown topic still draws");
  const banner = pixelBanner({ seed: 3 });
  assert.ok(banner.className.includes("px-pic--banner") && banner.getAttribute("aria-label") === "A pixel stadium skyline");
};
"""


@needs_node
@pytest.mark.parametrize("scenario", ["sizes", "pictures"])
def test_paper_sizes_in_a_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)
