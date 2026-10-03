"""Public release Phase 4b: keeping the screen on without HTTPS (static/js/awake.js). The browser's own
wake lock is used when the page has one; over plain HTTP a muted looping video stands in, behind the same
request()/sentinel shape, started on the first tap when the browser will not play it before one."""

from __future__ import annotations

import pytest

from tests.fakedom import needs_node, run_scenario

SCENARIOS = r"""
scenarios.native = async () => {
  const { screenLock } = await import(moduleUrl("awake.js"));
  assert.equal(screenLock(), navigator.wakeLock, "a secure page uses the browser's own wake lock");
};

scenarios.fallback = async () => {
  navigator.wakeLock = undefined; // a phone on http://kickoff.local:8642
  const { screenLock, fallbackState } = await import(moduleUrl("awake.js"));
  const api = screenLock();
  assert.ok(api && api.fallback, "the video stands in");
  await assert.rejects(api.request("system"));
  const first = await api.request("screen");
  assert.equal(first.released, false);
  const video = document.body.querySelector("video");
  assert.ok(video, "a hidden video joins the page");
  assert.ok(video.muted && video.loop && video.playsInline, "muted, looping, inline");
  assert.deepEqual(video.querySelectorAll("source").map((s) => s.getAttribute("src")), ["/static/media/awake.mp4", "/static/media/awake.webm"]);
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(fallbackState(), { holders: 1, hasVideo: true, waitingForTap: true }, "no playback before a tap: it waits for one");
  let plays = 0;
  let pauses = 0;
  video.play = () => { plays += 1; video.paused = false; return Promise.resolve(); };
  video.pause = () => { pauses += 1; video.paused = true; };
  document.dispatchEvent(makeEvent("pointerdown", { bubbles: true }));
  assert.equal(plays, 1, "the first tap starts it");
  assert.equal(fallbackState().waitingForTap, false);
  document.dispatchEvent(makeEvent("pointerdown", { bubbles: true }));
  assert.equal(plays, 1, "later taps do nothing more");
  const second = await api.request("screen");
  assert.equal(fallbackState().holders, 2);
  assert.equal(plays, 1, "a second holder shares the playing video");
  let released = 0;
  first.addEventListener("release", () => { released += 1; });
  await first.release();
  await first.release();
  assert.equal(released, 1, "release fires once");
  assert.equal(pauses, 0, "another holder still wants the screen on");
  await second.release();
  assert.equal(fallbackState().holders, 0);
  assert.equal(pauses, 1, "the last holder lets go: the video stops");
  const third = await api.request("screen");
  assert.equal(plays, 2, "after a tap has happened, a new request plays at once");
  await third.release();
};
"""


@needs_node
@pytest.mark.parametrize("scenario", ["native", "fallback"])
def test_keep_awake(tmp_path, scenario):
    run_scenario(tmp_path, SCENARIOS, scenario)
