"""Phase 17 #37 in the fake browser: a regular-season week with no game between a team's first and last regular-season
weeks shows as a Bye row in its place, dated from the game before it; the postseason, week-0 starts, odd gaps and
damaged rows add none."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fakedom import needs_node, run_scenario

SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object Object\]/;
const text = (node) => (node ? node.textContent : "");

scenarios.byes = async () => {
  const { scheduleList, withByes } = await import(moduleUrl("ui/schedule.js"));
  const game = (gameId, week, date, extra = {}) => ({ gameId, week, date, opponent: { school: `Opp ${gameId}` }, homeAway: "home", ...extra });
  const games = [
    game(1, 1, "2026-09-05T23:00:00Z"), game(2, 2, "2026-09-12T23:00:00Z"), game(3, 4, "2026-09-26T23:00:00Z"),
    game(4, 5, null), game(5, 7, "2026-10-17T23:00:00Z"),
    game(6, 1, "2026-12-20T23:00:00Z", { postseason: "Bowl game" }), null, "junk",
  ];
  const rows = withByes(games);
  assert.deepEqual(rows.filter((r) => r && r.bye).map((r) => r.week), [3, 6]);
  assert.equal(rows.find((r) => r.bye && r.week === 3).date.slice(0, 10), "2026-09-19", "the Saturday a week after the game before");
  assert.equal(rows.find((r) => r.bye && r.week === 6).date, null, "no date before it: no date");
  assert.deepEqual(withByes([game(1, 0, null), game(2, 1, null)]).filter((r) => r.bye), [], "a week-0 start is not a bye");
  assert.deepEqual(withByes([game(1, 1, null), game(2, 9, null)]).filter((r) => r.bye), [], "a gap that long is missing data, not byes");
  assert.deepEqual(withByes([game(1, "x", null), game(2, NaN, null)]).filter((r) => r.bye), []);
  const list = scheduleList({ games, onSelect: () => {} });
  document.body.append(list);
  const t = text(list);
  assert.ok(!RAW.test(t), t);
  const items = list.querySelectorAll("li");
  assert.deepEqual(items.map((li) => text(li.querySelector(".sched__wk"))).slice(0, 7), ["wk 1", "wk 2", "wk 3", "wk 4", "wk 5", "wk 6", "wk 7"]);
  const bye = list.querySelector(".sched__game--bye");
  assert.ok(text(bye).includes("Bye") && text(bye).includes("No game this week"));
  assert.equal(bye.getAttribute("role"), null, "a bye promises no tap");
};
"""


@needs_node
@pytest.mark.parametrize("scenario", ["byes"])
def test_bye_weeks_in_a_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)
