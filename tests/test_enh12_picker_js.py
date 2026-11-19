"""The team picker on the welcome page, which Settings' "Change team" opens. ENH-12 (owner 2026-10-23) made it one picker;
batch 3 (owner 2026-11-19: "I want to take out all the secondary teams. The initial idea was to have them so they warm
loaded, but now we do that a different way. Let's just have one team listed, and a change team for the switch.") makes it
pick exactly one school: no more primary teams, no order, no secondary teams and no ticker step. Picking another school
replaces the first; the setup saves the one team and nothing else."""

from __future__ import annotations

import json
import re
from pathlib import Path

from tests.fakedom import PROJECT_ROOT, needs_node, run_scenario

STATIC = PROJECT_ROOT / "static"
WELCOME = (STATIC / "welcome.html").read_text(encoding="utf-8")
WELCOME_JS = (STATIC / "js" / "welcome.js").read_text(encoding="utf-8")

SCENARIOS = r"""
const text = (node) => (node ? node.textContent : "");
const TEAMS = ["Florida", "Georgia", "Miami", "Florida State", "Texas", "Alabama"].map((school, i) => ({ school, mascot: `M${i}`, conference: "SEC", color: "#112233" }));

async function welcome(info) {
  document.body.replaceChildren();
  document.getElementById = (id) => document.querySelector(`#${id}`);
  for (const id of FIXTURE.welcomeIds) {
    const tag = id.endsWith("-input") || id.endsWith("-search") ? "input" : ["finish", "key-show", "key-check", "import-go"].includes(id) ? "button" : "div";
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
  route("/api/welcome", () => envelope(info));
  route("/api/welcome/teams", () => envelope({ teams: TEAMS }));
  route("/api/welcome/finish", () => envelope({ restarting: false }));
  route("/api/health", () => envelope({ server: { started_at: "2026-10-27T12:00:00Z" } }));
  await import(moduleUrl("welcome.js") + `?${Math.random()}`);
  await advance(50);
  return posted;
}

const picked = () => document.querySelectorAll("#team-picked .welcome__pick").map((row) => text(row.querySelector(".welcome__pick-name")).split(" M")[0]);
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

scenarios.firstSetup = async () => {
  const posted = await welcome({ setupNeeded: true, keyConfigured: true });
  assert.deepEqual(picked(), [], "nothing picked yet");
  assert.ok(document.querySelectorAll("#team-list .welcome__item").length > 0, "with no team yet the whole list shows");
  assert.equal(document.querySelector("#finish").disabled, true, "a team first");
  pick("Georgia");
  assert.deepEqual(picked(), ["Georgia"]);
  assert.ok(text(document.querySelector("#team-picked")).includes("Your team"), "the one team, said so");
  assert.equal(document.querySelectorAll("#team-list .welcome__item").length, 0, "once picked, only what is typed shows");
  assert.equal(document.querySelector("#finish").disabled, false);
  pick("Florida");
  assert.deepEqual(picked(), ["Florida"], "a second pick replaces the first: one team");
  assert.equal(document.querySelector("#team-search").disabled, false, "another school can always be picked instead");
  document.querySelectorAll("#team-picked button").find((b) => b.getAttribute("aria-label") === "Remove Florida").click();
  assert.deepEqual(picked(), [], "removed");
  assert.equal(document.querySelector("#finish").disabled, true);
  pick("Florida");
  document.querySelector("#finish").click();
  await advance(50);
  const saved = posted.find(([url]) => url === "/api/welcome/finish");
  assert.ok(saved, "the setup was saved");
  assert.deepEqual(saved[1], { team: "Florida" }, "the one team and nothing else");
};

scenarios.setUp = async () => {
  // a server from before batch 3 may still answer with the old picks: the page ignores them
  await welcome({ setupNeeded: false, keyConfigured: true, team: "Florida", primaryTeams: ["Georgia", "Miami"], liked: { teams: ["Texas"] }, tickerMode: "mine" });
  assert.deepEqual(picked(), ["Florida"], "the saved team alone");
  assert.ok(!/undefined|null|NaN/.test(text(document.body)));
  assert.ok(text(document.querySelector("#intro")).startsWith("Change your team or the key"));
  pick("Texas");
  assert.deepEqual(picked(), ["Texas"]);
};
"""


def _fixture(tmp_path: Path) -> str:
    ids = sorted(set(re.findall(r'id="([\w-]+)"', WELCOME)))
    path = tmp_path / "fixture.json"
    path.write_text(json.dumps({"welcomeIds": ids}), encoding="utf-8")
    return str(path)


@needs_node
def test_one_team_first_setup(tmp_path):
    run_scenario(tmp_path, SCENARIOS, "firstSetup", _fixture(tmp_path))


@needs_node
def test_one_team_once_set_up(tmp_path):
    run_scenario(tmp_path, SCENARIOS, "setUp", _fixture(tmp_path))


def test_the_welcome_page_has_two_steps_and_one_team():
    assert WELCOME.count("Step 1. Your CFBD key") == 1 and WELCOME.count("Step 2. Your team") == 1
    assert "Step 3" not in WELCOME and "Step 4" not in WELCOME, "the secondary teams and the ticker steps are gone"
    ids = set(re.findall(r'id="([\w-]+)"', WELCOME))
    assert "team-picked" in ids and "team-search" in ids and "team-list" in ids
    gone = sorted(i for i in ids if i.startswith(("liked-", "ticker-")) or i in ("team-order", "liked-panel", "ticker-panel", "h-liked", "h-ticker"))
    assert gone == [], gone
    for words in ("primary teams", "Primary teams", "Secondary teams", "My Teams order", "up to 5", "My teams"):
        assert words not in WELCOME, words


def test_the_welcome_script_sends_one_team():
    for name in ("primaryTeams", "tickerMode", "likedSearch", "MAX_PRIMARIES", "ticker-mine", "liked-"):
        assert name not in WELCOME_JS, name
    assert "payload = { team: state.team }" in WELCOME_JS
