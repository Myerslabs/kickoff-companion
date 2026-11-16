"""ENH-20 (P5, owner 2026-10-25: "Make all bands look put together, and have their data fit correctly. No huge empty
spaces"): the quieter pages redrawn from his design rules. The roster grid's equal class columns with wrapping chips (the
fit asks every cell), the Ratings scatter drawn wide in an iPad-width band (tests/test_p16_season_look_scatter.py), the
pie legend in even columns, the empty Archive's way to the Season schedule, the Preseason Magazine across the page in
columns (tests/test_preseason_js.py), the Load data cards ending level (tests/test_prompts_js.py), the Invite page's code
in a band with the PIN said once, the Status page's panels in pairs from 700 px."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.fakedom import needs_node, run_scenario

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "static" / "css" / "components.css").read_text(encoding="utf-8")
APP_CSS = (ROOT / "static" / "css" / "app.css").read_text(encoding="utf-8")
STATUS = (ROOT / "static" / "status.html").read_text(encoding="utf-8")

SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object Object\]/;
const text = (node) => (node ? node.textContent : "");

scenarios.fit = async () => {
  // a fixed table always matches its box, so the roster grid's own check steps the size down
  const { fitSize } = await import(moduleUrl("ui/sizes.js"));
  const wrap = document.createElement("div");
  const table = document.createElement("table");
  Object.defineProperty(wrap, "clientWidth", { value: 400 });
  Object.defineProperty(table, "offsetWidth", { value: 400 });
  const tried = [];
  const seen = fitSize(wrap, table, (step) => tried.push(step), ["large", "medium", "small"], () => tried.length >= 2);
  assert.equal(seen, "medium", "large fits the box but not the check; medium passes both");
  assert.deepEqual(tried, ["large", "medium"]);
  assert.equal(fitSize(wrap, table, () => {}, ["large", "small"]), "large", "no check: the box alone, as before");
};

scenarios.invite = async () => {
  const { inviteBody } = await import(moduleUrl("views/invite.js"));
  const data = { url: "http://192.168.0.5:8642/", qrPath: "/setup/qr.svg?url=http://192.168.0.5:8642/", warnings: ["A hotspot."], pinWarning: "No host PIN is set." };
  const sheet = inviteBody(data);
  assert.ok(text(sheet).includes("A hotspot.") && text(sheet).includes("No host PIN is set."), "In Game's Invite panel: both");
  const page = inviteBody(data, { big: true, pin: false });
  assert.ok(text(page).includes("A hotspot.") && !text(page).includes("No host PIN"), "the Invite page: What guests can do says it");
  assert.ok(page.querySelector(".invite__text button"), "the address and its copy beside the code");
  assert.ok(!RAW.test(text(inviteBody({ warnings: "junk", pinWarning: 4 }))));
};

scenarios.archive = async () => {
  installWindow();
  route("/api/archive", () => envelope({ games: [], count: 0, skipped: 0 }));
  const { createArchiveView } = await import(moduleUrl("views/archive.js"));
  const main = document.createElement("main");
  document.body.append(main);
  const view = createArchiveView({});
  view.mount(main);
  await settle();
  await settle();
  const t = text(main);
  assert.ok(!RAW.test(t), t);
  assert.ok(t.includes("No games yet") && t.includes("open from the Season schedule"), t);
  const go = main.querySelector('a[href="#season"]');
  assert.ok(go && text(go) === "Open the Season schedule", "the empty archive's way to every finished game");
  view.unmount();
};
"""


@needs_node
@pytest.mark.parametrize("scenario", ["fit", "invite", "archive"])
def test_the_quieter_pages_in_a_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)


def test_the_status_page_pairs_its_panels_from_the_ipad_held_upright() -> None:
    assert ".sheet--status { grid-template-columns: repeat(2, minmax(0, 1fr));" in APP_CSS
    assert re.search(r"@media \(max-width: 699px\) \{ \.sheet--status \{ grid-template-columns: minmax\(0, 1fr\)", APP_CSS), "one column on a phone only"
    order = re.findall(r'<section class="([^"]+)" aria-labelledby="h-([a-z]+)">', STATUS)
    assert [h for _cls, h in order] == ["connect", "server", "checks", "tls", "cfbd", "quota", "config", "calls", "published"], "the fact panels pair up"
    assert {h for cls, h in order if "panel-wide" in cls} == {"checks", "calls", "published"}, "the tables across the page"


def test_the_legend_and_the_magazine_lay_out_in_columns() -> None:
    assert ".pie__legend { display: grid; grid-template-columns: repeat(auto-fill, minmax(104px, 1fr));" in CSS
    assert ".preseason__blocks { columns: 2 300px;" in CSS and ".preseason__blocks > .preseason__block { break-inside: avoid;" in CSS


def test_the_api_gives_the_pin_its_own_field() -> None:
    source = (ROOT / "app" / "api" / "host.py").read_text(encoding="utf-8")
    assert '"pinWarning": pin_warning' in source and "warnings.append(\"No host PIN" not in source
