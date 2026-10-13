"""The newspaper's pixel pictures: the topic pictures (Phase 19) and, since items 10 to 12 (mock approved 2026-10-13),
the pictures that fill their box: a helmet in a team's colors, the lead's stadium, the made-up coach, a player."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fakedom import needs_node, run_scenario

SCENARIOS = r"""
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

scenarios.fill = async () => {
  const { fillPicture, refitPictures } = await import(moduleUrl("ui/pixel-art.js"));
  // every kind: a labeled picture that waits for its box; an unknown kind draws the stadium
  for (const kind of ["helmet", "stadium", "coach", "player"]) {
    const pic = fillPicture(kind, { color: "#7b2cbf", alt: "#ffffff", flip: kind === "helmet", number: 19 }, `A pixel ${kind}`);
    assert.ok(pic.className.includes(`px-fill--${kind}`) && pic.className.includes("px-pic"), pic.className);
    assert.equal(pic.getAttribute("role"), "img");
    assert.equal(pic.getAttribute("aria-label"), `A pixel ${kind}`);
    assert.equal(typeof pic.pxDraw, "function");
    assert.equal(pic.pxDraw(), false, "no box yet (the test browser lays nothing out): nothing is drawn, nothing breaks");
  }
  assert.ok(fillPicture("nonsense").className.includes("px-fill--stadium"));
  assert.ok(fillPicture("helmet", { color: "not a color", alt: null }).getAttribute("aria-label").includes("helmet"), "a bad color still draws");
  // junk options and a junk root never throw
  fillPicture("player", null);
  fillPicture("player", { playerId: "../../etc" });
  refitPictures(null);
  refitPictures({});
  const box = document.createElement("div");
  box.append(fillPicture("coach"), fillPicture("stadium"));
  refitPictures(box);

  // a drawing surface with a size: the grid takes the box's shape and the picture is painted
  const calls = [];
  const fake = (w, h) => {
    const pic = fillPicture("helmet", { color: "#123456", alt: "#fedcba" });
    pic.getBoundingClientRect = () => ({ width: w, height: h, top: 0, left: 0, right: w, bottom: h });
    pic.getContext = () => new Proxy({}, { get: (t, k) => (k in t ? t[k] : (...args) => calls.push([k, ...args])), set: (t, k, v) => { t[k] = v; return true; } });
    return pic;
  };
  const wide = fake(300, 150);
  assert.equal(wide.pxDraw(), true);
  assert.ok(wide.width > wide.height && wide.height >= 34, `${wide.width}x${wide.height}`);
  const tall = fake(120, 240);
  tall.pxDraw();
  assert.ok(tall.height > tall.width && tall.width >= 37, `${tall.width}x${tall.height}`);
  assert.ok(calls.some(([k]) => k === "fillRect"), "it painted");
};
"""


@needs_node
@pytest.mark.parametrize("scenario", ["pictures", "fill"])
def test_paper_pictures_in_a_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)
