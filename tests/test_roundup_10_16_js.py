"""The 2026-10-16 roundup in the fake browser: the loading bar (Claude Code loads in the background, the pages hold their
refreshes and refresh once at the end), the pie the recruiting page draws, the sample station on the radio list, the
notes file's location with its Copy, and the stream check of the station guide."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fakedom import needs_node, run_scenario

SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object Object\]/;
const text = (node) => (node ? node.textContent : "");
const clean = (label, node) => {
  const t = text(node);
  assert.ok(!RAW.test(t), `${label} printed ${JSON.stringify(t.slice(0, 400))}`);
  return t;
};

const RUNNING = { running: true, label: "Coaches", detail: "step 2 of 5, East (1 of 2)", fraction: 0.3, startedAt: null, lastFinishedAt: null, run: { running: true, steps: [] } };
const IDLE = (at = null) => ({ running: false, label: null, detail: null, fraction: null, startedAt: null, lastFinishedAt: at, run: { running: false, steps: [] } });

scenarios.runBar = async () => {
  let answer = IDLE();
  route("/api/prompts/progress", () => envelope(clone(answer)));
  const bar = await import(moduleUrl("ui/run-bar.js"));
  let loaded = 0;
  document.addEventListener("kickoff:data-loaded", () => { loaded += 1; });
  const slot = document.createElement("div");
  slot.className = "page-notes";
  document.body.append(slot);
  const host = bar.installRunBar(slot);
  await advance(0);
  assert.ok(host.hidden, "nothing runs: no bar");
  assert.equal(bar.dataRunActive(), false);
  assert.equal(loaded, 0, "a page that opens after a run ended does not refresh for it");
  answer = clone(RUNNING);
  bar.watchRun();
  await advance(0);
  assert.equal(host.hidden, false);
  const t = clean("the bar", host);
  assert.ok(t.includes("Loading data with Claude Code") && t.includes("Coaches, step 2 of 5") && t.includes("30%"), t);
  assert.equal(host.querySelector('[role="progressbar"]').getAttribute("aria-valuenow"), "30");
  assert.equal(bar.dataRunActive(), true);
  const seen = [];
  const stop = bar.onRunProgress((p) => seen.push(p.running));
  await advance(5000);
  assert.deepEqual(seen, [true], "every 5 s while it runs");
  assert.equal(loaded, 0, "no refresh until all of it is in");
  answer = IDLE("2026-10-16T15:00:00Z");
  await advance(5000);
  assert.equal(loaded, 1, "one refresh when every run has ended");
  assert.equal(bar.dataRunActive(), false);
  assert.ok(text(host).includes("Data loaded") && !host.hidden);
  await advance(6000);
  assert.ok(host.hidden, "the done line goes after a few seconds");
  await advance(5 * 60000);
  assert.equal(loaded, 1, "idle checks do not refresh");
  answer = IDLE("2026-10-16T16:00:00Z"); // a short run started and ended between two idle checks
  await advance(60000);
  assert.equal(loaded, 2);
  stop();
  // no indeterminate NaN: a run with no fraction moves without a percentage
  const moving = document.createElement("div");
  moving.append(...bar.runBarView({ running: true, label: "This week's notes", detail: "a few minutes", fraction: null, startedAt: "junk" }));
  const m = clean("moving bar", moving);
  assert.ok(m.includes("This week's notes, a few minutes") && !m.includes("%"));
  assert.ok(moving.querySelector(".run-bar__track--moving") && !moving.querySelector('[aria-valuenow]'));
  const junk = document.createElement("div");
  junk.append(...bar.runBarView("junk"));
  clean("junk bar", junk);
};

scenarios.hold = async () => {
  let answer = IDLE();
  route("/api/prompts/progress", () => envelope(clone(answer)));
  route("/api/thing", () => envelope({ n: 1 }));
  const bar = await import(moduleUrl("ui/run-bar.js"));
  const { poller, clearEnvelopeCache } = await import(moduleUrl("views/common.js"));
  clearEnvelopeCache();
  const slot = document.createElement("div");
  document.body.append(slot);
  bar.installRunBar(slot);
  await advance(0);
  let draws = 0;
  const view = poller({ url: "/api/thing", refreshMs: 1000, render: (env, c) => { draws += 1; c.replaceChildren(document.createTextNode(`n ${env.data.n}`)); }, renderError: () => {}, renderLoading: () => document.createElement("p") });
  const main = document.createElement("main");
  document.body.append(main);
  view.mount(main);
  await advance(0);
  const asked = () => calls.filter((u) => u.startsWith("/api/thing")).length;
  const start = asked();
  answer = clone(RUNNING);
  bar.watchRun();
  await advance(0);
  await advance(10000);
  assert.equal(asked(), start, "a drawn page holds its refreshes while Claude Code loads");
  answer = IDLE("2026-10-16T15:00:00Z");
  await advance(5000);
  assert.equal(asked(), start + 1 + 0, "one refresh at the end...");
  await advance(3000);
  assert.ok(asked() >= start + 3, "...then its own pace again");
  view.unmount();
};

scenarios.pie = async () => {
  const { arcPath, cleanSlices, pieChart } = await import(moduleUrl("ui/pie.js"));
  assert.equal(arcPath(100, 100, 96, 0, Math.PI / 2), "M 100 100 L 100 4 A 96 96 0 0 1 196 100 Z");
  assert.ok(arcPath(100, 100, 96, 0, Math.PI * 1.5).includes(" 0 1 1 "), "past half way the arc takes the long way round");
  const kept = cleanSlices([{ key: "b", label: "Bee", value: 2 }, { key: "a", label: "Ay", value: 2 }, { label: "Zero", value: 0 }, { label: "Bad", value: "3" }, null, "x", { value: 4 }, { key: "c", label: "Sea", value: 5 }]);
  assert.deepEqual(kept.map((s) => s.key), ["c", "a", "b"], "largest first, ties by name, junk left out");
  assert.equal(pieChart({ slices: [] }), null);
  assert.equal(pieChart({ slices: "junk" }), null);
  const one = pieChart({ slices: [{ key: "x", label: "Only", short: "OO", value: 3, color: "var(--team-us)" }], unit: ["commit", "commits"] });
  assert.equal(one.querySelectorAll("circle").length, 1, "one slice is a whole circle");
  assert.equal(text(one.querySelector(".pie__info")), "Only: 3 commits, 100%");
  const many = pieChart({ slices: [{ key: "a", label: "Ay", short: "A", value: 1 }, { key: "b", label: "Bee", short: "B", value: 3 }], unit: ["commit", "commits"] });
  const chips = many.querySelectorAll(".pie__chip");
  assert.deepEqual(chips.map((c) => text(c.querySelector(".pie__name"))), ["B", "A"]);
  assert.equal(text(chips[1].querySelector(".pie__value")), "1 · 25%");
  chips[1].click();
  assert.equal(text(many.querySelector(".pie__info")), "Ay: 1 commit, 25%");
  assert.ok(many.querySelectorAll(".pie__slice")[0].classList.contains("is-dim"));
  clean("pie", many);
};

scenarios.sampleStation = async () => {
  route("/api/radio/sources", () => envelope({ sources: [{ id: "1-far", name: "Far stream", kind: "stream", url: "https://radio.example.invalid/far.mp3", team: "Far Away", origin: "sample" }], help: [{ school: "Home U", search: [{ label: "Search the web", url: "https://example.org/s" }], requestUrl: "https://example.org/r" }], note: "" }));
  const { radioStations } = await import(moduleUrl("ui/radio-stations.js"));
  const host = radioStations({});
  document.body.append(host);
  await advance(0);
  const t = clean("sample radio", host);
  assert.ok(t.includes("Far stream") && t.includes("a sample (Far Away)"), t);
  assert.ok(t.includes("Home U: no station in the app yet") && t.includes("a sample station shows how the radio works"));
  assert.ok(host.querySelector('a[href="#settings=radio"]'), "the way to the station guide");
};

scenarios.notesPath = async () => {
  const { notesPathButton } = await import(moduleUrl("ui/notes-paste.js"));
  assert.equal(notesPathButton("junk"), null);
  const where = notesPathButton(42, { file: "C:\\\\data\\\\notes\\\\42.json", fileExists: false, example: "C:\\\\data\\\\notes\\\\_example.json" });
  document.body.append(where);
  assert.ok(text(where).includes("data/notes/42.json"));
  const buttons = where.querySelectorAll("button");
  assert.equal(buttons.length, 2, "no file yet: the example's location too");
  buttons[0].click();
  await advance(0);
  const box = where.querySelector("input.notes-paste__copybox");
  assert.ok(box.value.endsWith("42.json"), "over plain HTTP the location waits in a selected box");
  clean("notes path", where);
  const there = notesPathButton(42, { file: "x/42.json", fileExists: true, example: "x/_example.json" });
  assert.equal(there.querySelectorAll("button").length, 1, "a file already there: just its location");
};

scenarios.stream = async () => {
  const { looksLikeAudio } = await import(moduleUrl("views/settings.js"));
  for (const yes of ["https://ice.example.org/live.mp3", "https://x.example.org/a.aac?x=1", "https://x.example.org/p.m3u8", "https://x.example.org/radio/stream", "https://ais-sa1.streamon.fm/7644_64k.mp3"]) assert.ok(looksLikeAudio(yes), yes);
  for (const no of ["https://www.example-station.com/listen-live-now-page", "https://www.example.org/", "", null, 5]) assert.ok(!looksLikeAudio(no), String(no));
};
"""


@needs_node
@pytest.mark.parametrize("scenario", ["runBar", "hold", "pie", "sampleStation", "notesPath", "stream"])
def test_roundup_in_a_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)
