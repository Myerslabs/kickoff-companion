"""FEAT-5 on the page: another team's Roster, Recruiting and program carry `?team=`, say whose page it is with the way back
to ours, and every team's sheet and page lead to its own Season, Roster, Recruiting and next game's program."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fakedom import needs_node, run_scenario

SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object Object\]/;
const text = (node) => (node ? node.textContent : "");
const flush = async () => { for (let i = 0; i < 8; i += 1) await new Promise((resolve) => setImmediate(resolve)); };

scenarios.other = async () => {
  await useTeam();
  const { otherTeam, otherTeamHead, teamLinks, withTeam } = await import(moduleUrl("ui/other-team.js"));
  const { gameHref } = await import(moduleUrl("ui/schedule.js"));
  assert.equal(otherTeam({ team: " Texas " }), "Texas");
  assert.equal(otherTeam({ team: "Florida" }), null, "our own team is the plain page");
  assert.equal(otherTeam(null), null);
  assert.equal(otherTeam({ team: 5 }), null);
  assert.equal(withTeam("/api/roster", "Texas A&M"), "/api/roster?team=Texas%20A%26M");
  assert.equal(withTeam("/api/x?y=1", "Texas"), "/api/x?y=1&team=Texas");
  assert.equal(withTeam("/api/roster", null), "/api/roster");
  assert.equal(gameHref({ gameId: 401 }, "Texas"), "#program=401?team=Texas");
  assert.equal(gameHref({ gameId: 401 }), "#program=401");
  const head = otherTeamHead({ school: "Texas", conference: "SEC" }, "roster", "#roster");
  assert.ok(text(head).includes("Texas roster") && text(head).includes("SEC") && !RAW.test(text(head)), text(head));
  assert.equal(head.querySelector("a.other-team__back").getAttribute("href"), "#roster");
  assert.ok(text(head.querySelector("a.other-team__back")).includes("roster"));
  assert.equal(otherTeamHead({}, "roster", "#roster"), null, "no school: no head");
  const links = teamLinks("Texas", [{ gameId: 1, completed: true }, null, { gameId: 2, completed: false }]);
  assert.deepEqual(links.querySelectorAll("a").map((a) => a.getAttribute("href")), ["#season?team=Texas", "#roster?team=Texas", "#recruiting?team=Texas", "#program=2?team=Texas"]);
  const ours = teamLinks("Florida", []);
  assert.deepEqual(ours.querySelectorAll("a").map((a) => a.getAttribute("href")), ["#season", "#roster", "#recruiting"], "ours are the plain pages; no next game, no program link");
  assert.equal(teamLinks(null, []), null);
};

scenarios.numbers = async () => {
  // FEAT-8: the app's own numbers, offense left, the measure in the middle, defense right, whole percents
  installWindow();
  await useTeam();
  const { numbersBand } = await import(moduleUrl("ui/numbers-band.js"));
  const side = (rate, rank) => ({ snaps: 400, successRate: rate, explosiveRate: 0.081, havocRate: 0.12, passRate: 0.5, redZone: { trips: 20, touchdowns: 12, fieldGoals: 5, tdRate: 0.6, pointsPerTrip: 4.95 }, ranks: { successRate: rank, explosiveRate: 10, havocRate: 30, "redZone.tdRate": 7, "redZone.pointsPerTrip": 9 },
    downs: [{ key: "first", label: "1st down", made: 90, of: 200, rate: 0.45 }, { key: "third_long", label: "3rd/4th and long (8+)", made: 4, of: 0, rate: null }, null] });
  route("/api/numbers/Texas", () => envelope({ season: 2026, games: 30, rankOf: { "offense.successRate": 120 }, team: { school: "Texas", games: 6, offense: side(0.456, 12), defense: side(0.39, 4) } }));
  route("/api/numbers/Nowhere", () => envelope({ season: 2026, games: 30, team: null }));
  const host = numbersBand("Texas");
  document.body.append(host);
  await flush();
  const t = text(host);
  assert.ok(!RAW.test(t), t.slice(0, 400));
  assert.ok(t.includes("6 games, every play") && t.includes("46%") && t.includes("39%") && t.includes("Success rate"), t.slice(0, 500));
  assert.ok(t.includes("45% (90/200)") && !t.includes("(4/0)"), "a down with no snaps is a dash");
  assert.ok(host.querySelector(".rank-chip"), "the national ranks as chips");
  const empty = numbersBand("Nowhere");
  document.body.append(empty);
  await flush();
  assert.ok(text(empty).includes("after its first game is read"), text(empty));
  route("/api/numbers/Broken", () => { throw new Error("down"); });
  const broken = numbersBand("Broken");
  document.body.append(broken);
  await flush();
  assert.ok(!RAW.test(text(broken)) && broken.querySelector(".band"), text(broken));
  assert.equal(numbersBand(null), null);
};

scenarios.follow = async () => {
  // FEAT-1: Watch it live on another team's game on its day, and the line on In Game with the way back to ours
  installWindow();
  await useTeam();
  const { followButton, followingLine, watchable } = await import(moduleUrl("ui/follow.js"));
  const now = Date.parse("2026-10-24T20:00:00Z");
  const soon = { gameId: 401, kickoff: "2026-10-24T23:30:00Z", completed: false };
  assert.ok(watchable(soon, now) && !watchable({ ...soon, completed: true }, now) && watchable({ ...soon, kickoff: "2026-10-31T23:30:00Z" }, now) && !watchable({ ...soon, kickoff: "2026-11-03T23:30:00Z" }, now) && !watchable({ ...soon, kickoff: "x" }, now), "any game of the week (2026-11-02), not one nine days out");
  assert.ok(followButton(soon, "Texas", now), "on its day");
  assert.ok(followButton({ ...soon, kickoff: "2026-10-31T23:30:00Z" }, "Texas", now), "a week away: the pregame screen until plays arrive (2026-11-02)");
  assert.equal(followButton({ ...soon, kickoff: "2026-11-03T23:30:00Z" }, "Texas", now), null, "nine days out: not this week's");
  assert.equal(followButton({ gameId: "x", kickoff: soon.kickoff }, "Texas", now), null);
  let sent = null;
  route("/api/live/follow", (req) => { sent = req; return envelope({ followed: { gameId: 401, team: "Texas" } }); });
  const button = followButton(soon, "Texas", now);
  document.body.append(button);
  button.querySelector("button").click();
  for (let i = 0; i < 8; i += 1) await new Promise((resolve) => setImmediate(resolve));
  assert.ok(sent, "the follow was asked for");
  assert.equal(window.location.hash.replace(/^#/, ""), "live", "and In Game opens");
  assert.equal(followingLine({ team: "Florida", home: "Florida", away: "Texas" }), null, "our own game: no line");
  assert.equal(followingLine(null), null);
  const line = followingLine({ team: "Texas", home: "Oklahoma", away: "Texas" });
  assert.ok(text(line).includes("Watching Texas at Oklahoma, from Texas's side.") && text(line).includes("Back to Florida's game"), text(line));
  assert.ok(!RAW.test(text(followingLine({ team: "Texas", home: null, away: 5 }))), "missing names: still words");
};
"""


@needs_node
@pytest.mark.parametrize("scenario", ["other", "numbers", "follow"])
def test_another_teams_pages_in_a_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)
