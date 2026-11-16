"""FEAT-18 the Circle of Blame's page (the owner's board of 2026-10-30,
"Build as drawn") in a fake browser: the wheel, an arc a slice with the biggest selected, the list beside it, the kinds'
legend, the verdict; the case of the selected slice with who a named coach is, its evidence and a headline's link; What
moved; the season strip newest on top, a tap loading that week; the headlines folded; Regenerate for the host following
its run; the states with no report; and its place in the band catalog and the menu's New."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fakedom import needs_node, run_scenario

SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object \w+\]/;
const text = (node) => (node ? node.textContent : "");
const ev = (n) => Array.from({ length: n }, (_, i) => ({ metric: `Metric ${i}`, value: String(10 + i), context: "ranks 100th of 138" }));
const slice = (name, kind, share, trend = "flat", evidence = ev(2)) => ({ name, kind, share_pct: share, case: `The case against ${name}.`, evidence, trend });
const WEEK7 = {
  season: 2026, key: "week-7", week: 7, label: "Week 7", opponent: "Texas", home: false, neutral: false, score: { us: 27, them: 24 },
  people: { "Brad White": "defensive coordinator", "Aaron Philo": "QB" },
  generatedAt: "2026-10-19T06:41:00-04:00", modelUsed: "claude-opus-5-5", attempts: 1, status: "published",
  report: {
    schema_version: "1", season: 2026, week: 7, after_result: "win", verdict: "The pass defense is the liability.",
    slices: [
      slice("Offensive line", "unit", 24, "up"),
      slice("Brad White", "coach", 32, "down", [...ev(1), { metric: "Headline", value: "Gators secondary torched again", context: "ESPN, Oct 20" }]),
      slice("Passing-down offense", "scheme", 18),
      slice("Penalties", "other", 14, "new"),
      slice("The early schedule", "schedule", 12),
    ],
    movement: "The defense rose; the line fell.", limitations: ["No coverage grades."], confidence: "medium",
  },
  headlines: [{ title: "Gators secondary torched again", source: "ESPN", publishedAt: "2026-10-20T12:00:00Z", url: "https://espn.example/1" }, { title: "No link here", source: "Blog", publishedAt: null, url: null }],
};
const WEEK6 = { ...WEEK7, key: "week-6", week: 6, label: "Week 6", opponent: "South Carolina", home: true, score: { us: 19, them: 38 }, report: { ...WEEK7.report, week: 6, after_result: "loss", verdict: "Week six's verdict.", slices: WEEK7.report.slices.map((s, i) => ({ ...s, share_pct: [20, 40, 16, 14, 10][i] })) } };
const strip = (w) => ({ key: w.key, week: w.week, label: w.label, result: w.report.after_result, opponent: w.opponent, score: w.score, home: w.home, neutral: w.neutral, top: { name: "Brad White", kind: "coach", share: w.report.slices[1].share_pct }, slices: w.report.slices.map((s) => ({ name: s.name, kind: s.kind, share: s.share_pct })) });
const NOW = { available: true, season: 2026, ourTeam: "Florida", latest: WEEK7, weeks: [], history: [strip(WEEK6), strip(WEEK7)], runs: { last: { status: "ok" }, running: false }, lastFailure: null, canRegenerate: true };

async function mountPage(data = NOW) {
  installWindow();
  await useTeam();
  route("/api/blame/now", envelope(data));
  route("/api/blame/2026/week-6", envelope(WEEK6));
  const { createBlameView } = await import(moduleUrl("views/blame.js"));
  const container = document.createElement("main");
  document.body.append(container);
  const view = createBlameView({ onStatus: () => {} });
  view.mount(container);
  await settle();
  return { view, container };
}

scenarios.pure = async () => {
  const m = await import(moduleUrl("views/blame.js"));
  assert.equal(m.KINDS.length, 10);
  assert.equal(new Set(m.KINDS.map((k) => k.color)).size, 10, "ten colors told apart");
  const arcs = m.arcPaths([50, 25, 25]);
  assert.equal(arcs.length, 3);
  assert.ok(arcs.every((a) => a.d.startsWith("M") && a.d.endsWith("Z")));
  assert.ok(arcs[0].d.includes(" 0 0 1 "), "half the wheel is not a large arc after the gaps");
  assert.equal(m.arcPaths([0, 100]).length, 2);
  assert.equal(m.resultWords({ result: "win", score: { us: 27, them: 24 }, opponent: "Texas", home: false }), "W 27-24 at Texas");
  assert.equal(m.resultWords({ result: "loss", score: { us: 19, them: 38 }, opponent: "South Carolina", home: true }), "L 19-38 vs South Carolina");
  assert.equal(m.resultWords({}), "–");
  assert.equal(m.trendWords("up"), "up");
  assert.equal(m.trendWords("sideways"), "–");
};

scenarios.page = async () => {
  const { view, container } = await mountPage();
  const words = text(container);
  assert.ok(!RAW.test(words), words.match(/.{0,40}(undefined|null|NaN|Infinity|object).{0,40}/)?.[0]);
  assert.deepEqual(container.querySelectorAll("section.band").map((s) => s.getAttribute("id")), ["blame-wheel", "blame-case", "blame-moved", "blame-season"], "the four bands stacked; Headlines considered dropped (his inventory, 2026-11-01)");
  assert.ok(container.querySelector(".blame--embedded") && !container.querySelector(".page"), "embedded: a host on My Team, no page of its own");
  assert.ok(text(container.querySelector("#blame-wheel .band__summary")).includes("Week 7 · W 27-24 at Texas"));
  assert.equal(container.querySelectorAll(".blame-wheel__arc").length, 5);
  assert.ok(container.querySelectorAll(".blame-wheel__arc")[1].classList.contains("is-selected"), "the biggest slice is selected first");
  assert.equal(container.querySelectorAll(".blame-legend__item").length, 10);
  assert.equal(text(container.querySelector(".blame-verdict")), "The pass defense is the liability.");
  assert.ok(text(container.querySelector(".blame-meta")).includes("by claude-opus-5-5") && text(container.querySelector(".blame-meta")).includes("confidence medium"));
  assert.equal(text(container.querySelector("#blame-case .band__title")), "Brad White");
  assert.ok(text(container.querySelector("#blame-case .blame-kind")) === "Coach · defensive coordinator");
  assert.ok(text(container.querySelector("#blame-case")).includes("32%") && text(container.querySelector("#blame-case")).includes("down"));
  const link = container.querySelector(".blame-evidence a");
  assert.ok(link && link.getAttribute("href") === "https://espn.example/1", "a headline's evidence links to its story");
  assert.equal(container.querySelectorAll(".blame-evidence tbody tr").length, 2);
  assert.ok(text(container.querySelector("#blame-moved")).includes("The defense rose") && text(container.querySelector(".blame-limits")).includes("No coverage grades."));
  const rows = container.querySelectorAll(".blame-season__row");
  assert.deepEqual(rows.map((r) => text(r.querySelector(".blame-season__week"))), ["Wk 7", "Wk 6"], "newest on top");
  assert.ok(rows[0].classList.contains("is-current") && text(rows[1]).includes("L 19-38 vs South Carolina"));
  // owner 2026-11-15 (his iPhone: never cut): the separator is its own span, so a phone puts the unit on a line of its own
  assert.ok(rows.every((r) => !r.querySelector(".blame-season__what b") || text(r.querySelector(".blame-season__sep")) === " · "), "the separator before the unit is a span the phone hides");
  assert.equal(container.querySelectorAll(".blame-season__bar span").length, 10);
  assert.equal(container.querySelector("#blame-headlines"), null, "no Headlines considered band");
  // a tap on another slice: the case follows
  container.querySelectorAll(".blame-list__row")[0].click();
  assert.equal(text(container.querySelector("#blame-case .band__title")), "Offensive line");
  assert.ok(text(container.querySelector("#blame-case .blame-kind")) === "Unit", "a unit names no person");
  assert.ok(container.querySelectorAll(".blame-wheel__arc")[0].classList.contains("is-selected"));
  // a tap on the wheel too
  container.querySelectorAll(".blame-wheel__arc")[2].dispatchEvent(makeEvent("click", { bubbles: true }));
  assert.equal(text(container.querySelector("#blame-case .band__title")), "Passing-down offense");
  // a week from the strip
  container.querySelectorAll(".blame-season__row")[1].click();
  await settle();
  assert.ok(text(container.querySelector("#blame-wheel .band__summary")).includes("Week 6 · L 19-38 vs South Carolina"));
  assert.equal(text(container.querySelector("#blame-case .band__title")), "Brad White", "that week's biggest slice");
  assert.ok(container.querySelectorAll(".blame-season__row")[1].classList.contains("is-current"));
  const back = [...container.querySelectorAll("button")].find((b) => text(b) === "Back to the latest week");
  assert.ok(back);
  back.click();
  assert.ok(text(container.querySelector("#blame-wheel .band__summary")).includes("Week 7"));
  view.unmount();
};

scenarios.regenerate = async () => {
  const { view, container } = await mountPage();
  route("/api/blame/2026/week-7/regenerate", { status: 200, body: { data: { run: { id: "circle_of_blame-1", status: "running" } }, errors: [] } });
  let asked = 0;
  route("/api/jobs/runs/circle_of_blame-1", () => {
    asked += 1;
    return envelope({ id: "circle_of_blame-1", status: asked > 1 ? "ok" : "running", message: "written" });
  });
  const button = container.querySelector(".blame-regen");
  assert.ok(button && text(button) === "Regenerate");
  button.click();
  await settle();
  assert.ok(text(container).includes("Claude Code is writing the report now"), "the run is said");
  assert.equal(text(container.querySelector(".blame-regen")), "Writing…");
  const before = callsTo("/api/blame/now");
  await advance(10000);
  await advance(10000);
  assert.ok(callsTo("/api/blame/now") > before, "the page reads the new report once the run is done");
  assert.ok(!text(container).includes("Claude Code is writing the report now"));
  view.unmount();
};

scenarios.states = async () => {
  const never = await mountPage({ available: false, season: 2026, message: "No Circle of Blame yet: Claude Code isn't on this computer.", failed: false, runs: {}, canRegenerate: true });
  assert.ok(text(never.container).includes("isn't on this computer") && !never.container.querySelector(".blame-wheel__svg"), "words, never an empty wheel");
  assert.ok(never.container.querySelector(".blame-regen"), "the host can write the first one");
  never.view.unmount();
  const guest = await mountPage({ ...NOW, canRegenerate: false });
  assert.ok(!guest.container.querySelector(".blame-regen"), "a guest has no Regenerate");
  guest.view.unmount();
  const failed = await mountPage({ available: false, season: 2026, message: "The Circle of Blame for 2026 is unavailable since 2026-11-01: Claude's report failed the checks twice", failed: true, runs: {}, canRegenerate: false });
  assert.ok(failed.container.querySelector(".note--error") && text(failed.container).includes("unavailable since"));
  failed.view.unmount();
  const later = await mountPage({ ...NOW, lastFailure: { at: "2026-10-26T06:30:00-04:00", attempts: 2 }, runs: { last: { status: "failed", message: "No report for week 8 after 2 tries" }, running: false } });
  assert.ok(text(later.container).includes("The last run failed: No report for week 8 after 2 tries"), "a failure after a good report keeps the report, said");
  later.view.unmount();
  const empty = await mountPage({ ...NOW, latest: { ...WEEK7, report: { ...WEEK7.report, slices: [] } } });
  assert.ok(text(empty.container).includes("without its slices"));
  assert.ok(!RAW.test(text(empty.container)));
  empty.view.unmount();
};

scenarios.placed = async () => {
  const cat = await import(moduleUrl("ui/band-catalog.js"));
  assert.deepEqual(cat.bandsOf("blame"), [], "the page's catalog entry went (wave 3, 2026-11-01)");
  assert.deepEqual(cat.bandsOf("season").filter((b) => b.id.startsWith("blame-")).map((b) => b.id), ["blame-wheel", "blame-case", "blame-moved", "blame-season"], "the four bands are My Team's");
  const { MENU } = await import(moduleUrl("ui/menu-tree.js"));
  assert.equal(MENU.groups.find((g) => g.id === "new").items.find((e) => e.id === "blame"), undefined, "no row of its own in New");
  const app = (await import("node:fs")).readFileSync(new URL(moduleUrl("app.js")), "utf8");
  assert.ok(app.includes('blame: (opts) => createSeasonView({ ...opts, params: { band: "blame" } })'), "the old address lands on the wheel");
};
"""


@needs_node
@pytest.mark.parametrize("scenario", ["pure", "page", "regenerate", "states", "placed"])
def test_the_page_in_a_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)
