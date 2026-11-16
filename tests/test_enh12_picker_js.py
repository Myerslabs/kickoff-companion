"""ENH-12 (owner 2026-10-23: "In the setup, step 2 is pick primary team, but step 3 is also pick primary team. Use the step 3
as the only step and use the multi-select there", the pick order as the My Teams order): one picker on the welcome page, which
Settings' "Change my teams" opens. The first team picked is the home team, up to four more follow, Move up reorders them (up
to #1 makes a team the home team), and the setup saves the home team and the rest in that order."""

from __future__ import annotations

import json
import re
from pathlib import Path

from tests.fakedom import PROJECT_ROOT, needs_node, run_scenario

STATIC = PROJECT_ROOT / "static"
WELCOME = (STATIC / "welcome.html").read_text(encoding="utf-8")

SCENARIOS = r"""
const text = (node) => (node ? node.textContent : "");
const TEAMS = ["Florida", "Georgia", "Miami", "Florida State", "Texas", "Alabama"].map((school, i) => ({ school, mascot: `M${i}`, conference: "SEC", color: "#112233" }));

async function welcome(info) {
  document.body.replaceChildren();
  document.getElementById = (id) => document.querySelector(`#${id}`);
  for (const id of FIXTURE.welcomeIds) {
    const tag = id.endsWith("-input") || id.endsWith("-search") || id.startsWith("ticker-") ? "input" : ["finish", "key-show", "key-check", "import-go"].includes(id) ? "button" : id === "team-order" ? "ol" : "div";
    const node = document.createElement(tag);
    node.setAttribute("id", id);
    document.body.append(node);
  }
  const posted = [];
  const plain = globalThis.fetch;
  globalThis.fetch = async (url, init) => {
    if (init && typeof init.body === "string") posted.push([String(url), JSON.parse(init.body)]);
    return plain(url, init);
  };
  route("/api/welcome", () => envelope({ plan: { likedAllowed: true }, ...info })); // a Tier 2 key: the picker takes five (2.0: one below Tier 2)
  route("/api/welcome/teams", () => envelope({ teams: TEAMS, conferences: ["SEC"], states: ["FL"] }));
  route("/api/welcome/finish", () => envelope({ restarting: false }));
  route("/api/health", () => envelope({ server: { started_at: "2026-10-27T12:00:00Z" } }));
  await import(moduleUrl("welcome.js") + `?${Math.random()}`);
  await advance(50);
  return posted;
}

const order = () => document.querySelectorAll("#team-order li").map((li) => text(li.querySelector(".welcome__pick-name")).split(" M")[0]);
const search = (value) => {
  const box = document.querySelector("#team-search");
  box.value = value;
  box.dispatchEvent(makeEvent("input", { bubbles: true }));
};
const pick = (school) => {
  search(school);
  const item = document.querySelectorAll("#team-list .welcome__item").find((b) => text(b).startsWith(`${school} `));
  assert.ok(item, `${school} is offered`);
  item.click();
};
const button = (label) => document.querySelectorAll("#team-order button").find((b) => b.getAttribute("aria-label") === label);

scenarios.firstSetup = async () => {
  const posted = await welcome({ setupNeeded: true, keyConfigured: true, primaryTeams: [] });
  assert.deepEqual(order(), [], "nothing picked yet");
  assert.ok(document.querySelectorAll("#team-list .welcome__item").length > 0, "with no team yet the whole list shows");
  assert.equal(document.querySelector("#finish").disabled, true, "a home team first");
  pick("Florida");
  assert.deepEqual(order(), ["Florida"]);
  assert.ok(text(document.querySelector("#team-order li")).includes("Home team"), "#1 is the home team, said so");
  assert.equal(document.querySelectorAll("#team-list .welcome__item").length, 0, "after the first, only what is typed shows");
  assert.equal(document.querySelector("#finish").disabled, false);
  for (const school of ["Georgia", "Miami", "Florida State", "Texas"]) pick(school);
  assert.deepEqual(order(), ["Florida", "Georgia", "Miami", "Florida State", "Texas"], "the pick order");
  assert.equal(document.querySelector("#team-search").disabled, true, "five is the most");
  search("Ala");
  assert.equal(document.querySelectorAll("#team-list .welcome__item").length, 0);
  // Move up reorders; up to #1 makes the home team
  button("Move Miami up to #2").click();
  assert.deepEqual(order(), ["Florida", "Miami", "Georgia", "Florida State", "Texas"]);
  button("Move Miami up to #1").click();
  assert.deepEqual(order(), ["Miami", "Florida", "Georgia", "Florida State", "Texas"]);
  assert.ok(text(document.querySelector("#team-order li")).includes("Home team") && !button("Move Miami up to #0"), "no Move up on #1");
  button("Remove Miami").click();
  assert.deepEqual(order(), ["Florida", "Georgia", "Florida State", "Texas"], "removing #1 makes #2 the home team");
  assert.equal(document.querySelector("#team-search").disabled, false);
  document.querySelector("#finish").click();
  await advance(50);
  const saved = posted.find(([url]) => url === "/api/welcome/finish");
  assert.ok(saved, "the setup was saved");
  assert.equal(saved[1].team, "Florida");
  assert.deepEqual(saved[1].primaryTeams, ["Georgia", "Florida State", "Texas"], "the rest in the picked order");
};

scenarios.setUp = async () => {
  await welcome({ setupNeeded: false, keyConfigured: true, team: "Florida", primaryTeams: ["Georgia", "Miami"], liked: { teams: ["Miami", "Texas"] } });
  assert.deepEqual(order(), ["Florida", "Georgia", "Miami"], "the saved teams in the My Teams order");
  assert.ok(!/undefined|null|NaN/.test(text(document.querySelector("#team-order"))));
  pick("Texas");
  assert.deepEqual(order(), ["Florida", "Georgia", "Miami", "Texas"]);
  assert.ok(!text(document.querySelector("#liked-chips")).includes("Texas"), "a team is primary or secondary, not both");
};
"""


def _fixture(tmp_path: Path) -> str:
    ids = sorted(set(re.findall(r'id="([\w-]+)"', WELCOME)))
    path = tmp_path / "fixture.json"
    path.write_text(json.dumps({"welcomeIds": ids}), encoding="utf-8")
    return str(path)


@needs_node
def test_one_picker_first_setup(tmp_path):
    run_scenario(tmp_path, SCENARIOS, "firstSetup", _fixture(tmp_path))


@needs_node
def test_one_picker_once_set_up(tmp_path):
    run_scenario(tmp_path, SCENARIOS, "setUp", _fixture(tmp_path))


def test_the_welcome_page_has_one_primary_step():
    assert WELCOME.count("Step 2. Your primary teams") == 1 and 'id="team-order"' in WELCOME
    assert "primary-search" not in WELCOME and "More primary teams" not in WELCOME, "the old step 3 is gone"
    assert "Step 3. Secondary teams" in WELCOME and "Step 4. The score ticker" in WELCOME and "Step 5" not in WELCOME
