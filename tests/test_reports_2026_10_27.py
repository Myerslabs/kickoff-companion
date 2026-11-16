"""The owner's three reports of 2026-10-27 evening (1.7.2, from his iPhone):

BUG-26 (20261027-204732-b53b65): "When I'm in light mode, some of the toggles are dark blue over black text and I can't read
what is in the boxes." Every fill in the team's primary color carried the theme's text color, near black in light mode;
now the text on that fill is --on-team, white in both themes.
ENH-33 (20261027-203210-10e41a): "If I'm on the newspaper page and I select newspaper from the menu again, it should take me
to the top of the page." The menu, a tab and goTo send the page already showing to its top, and hold it there through the
browser's own scroll restoration as the menu's history entry goes back out.
ENH-34 (20261027-203605-3b1f85): Leaders vs this week's opponent, "The bigger number is already bolder so the arrow is just
confusing": the vs table keeps its middle column to the place, no bar.
ENH-35 (his follow-up the same evening: "Make the theme a per-device choice, like the text size, so the iPhone's choice
never changes the other screens"): the theme lives in each browser's storage; the server's setting is no longer read."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.fakedom import needs_node, run_scenario

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "static" / "css" / "components.css").read_text(encoding="utf-8")
TOKENS = (ROOT / "static" / "css" / "tokens.css").read_text(encoding="utf-8")


def test_text_on_the_team_fill_is_white_in_both_themes():
    assert re.search(r"--on-team:\s*#FFFFFF;", TOKENS)
    light = TOKENS.split(':root[data-theme="light"]', 1)[1].split("}", 1)[0]
    assert "--on-team" not in light, "the light theme keeps the white text on the team's fill"
    rules = [r for r in re.findall(r"[^{}]+\{[^{}]*\}", CSS) if re.search(r"background:\s*var\(--team-primary\)", r)]
    assert len(rules) >= 7
    for rule in rules:
        color = re.search(r"(?<![-\w])color:\s*([^;]+);", rule)
        assert color and color.group(1).strip() == "var(--on-team)", rule.strip()[:120]


SCENARIOS = r"""
scenarios.toTop = async () => {
  const win = installWindow({ scrollY: 1500 });
  window.location.hash = "#newspaper";
  const { goTo, toTop } = await import(moduleUrl("ui/layers.js"));
  goTo("newspaper"); // the page already showing
  await advance(20);
  assert.equal(win.scrollY, 0, "the page goes back to its top");
  win.scrollY = 1500; // the browser puts the entry's old scroll back a moment later
  win.dispatchEvent(makeEvent("scroll"));
  assert.equal(win.scrollY, 0, "a scroll the reader did not make goes back up");
  await advance(600);
  win.scrollY = 900; // the hold is over: the reader's own scroll stays
  win.dispatchEvent(makeEvent("scroll"));
  assert.equal(win.scrollY, 900);
  toTop();
  await advance(20);
  assert.equal(win.scrollY, 0);
  win.dispatchEvent(makeEvent("touchstart")); // the reader takes over at once
  win.scrollY = 400;
  win.dispatchEvent(makeEvent("scroll"));
  assert.equal(win.scrollY, 400, "a touch ends the hold");
};

scenarios.theme = async () => {
  installWindow();
  localStorage.removeItem("ui:theme");
  route("/api/settings", () => envelope({ prefs: { theme: "light", delaySeconds: 30 } })); // the server still says light
  const prefs = await import(moduleUrl("prefs.js"));
  await prefs.loadPrefs(true);
  assert.equal(document.documentElement.dataset.theme, "dark", "a device that never chose is Dark, whatever the server says");
  assert.equal(prefs.themeChoice(), "dark");
  assert.equal(prefs.setTheme("light"), "light");
  assert.equal(document.documentElement.dataset.theme, "light");
  assert.equal(JSON.parse(localStorage.getItem("ui:theme")), "light");
  await prefs.loadPrefs(true); // another device saving its settings never changes this one's theme
  assert.equal(document.documentElement.dataset.theme, "light");
  assert.equal(prefs.setTheme("neon"), "dark", "anything else is Dark");
  localStorage.setItem("ui:theme", "{not json");
  assert.equal(prefs.themeChoice(), "dark", "a damaged stored value is Dark");
};

scenarios.versus = async () => {
  await useTeam();
  const { twoTeamTable } = await import(moduleUrl("ui/two-team.js"));
  const side = (value, who) => ({ value, who, whoName: who, onWho: () => {} });
  const rows = [{ label: "1", format: "0f", higherIsBetter: true, us: side(608, "C. Nichols"), them: side(449, "M. Reed") }, { label: "2", format: "0f", higherIsBetter: true, us: side(149, "R. Nichols"), them: side(181, "R. White") }];
  const plain = twoTeamTable({ rows, usAbbr: "FLA", themAbbr: "TEX", centered: true, bar: false, labelHead: "#" });
  document.body.append(plain);
  assert.equal(plain.querySelectorAll(".tug").length, 0, "no bar under the place");
  assert.equal(plain.querySelectorAll("td.tt__mid--plain").length, 2);
  assert.ok(plain.querySelectorAll("td.lead").length === 2, "the bigger number is still the bold one");
  const withBar = twoTeamTable({ rows, usAbbr: "FLA", themAbbr: "TEX", centered: true, labelHead: "#" });
  document.body.append(withBar);
  assert.equal(withBar.querySelectorAll(".tug").length, 2, "the program's leader lines keep their bar");
  const leaders = (await import("node:fs")).readFileSync(new URL(moduleUrl("views/leaders.js")), "utf8");
  assert.ok(/centered: true,\s*bar: false,/.test(leaders), "Leaders' vs table asks for no bar");
};
"""


@needs_node
@pytest.mark.parametrize("scenario", ["toTop", "versus", "theme"])
def test_in_a_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)


def test_the_menu_and_the_tabs_send_the_page_showing_to_its_top():
    shell = (ROOT / "static" / "js" / "ui" / "shell.js").read_text(encoding="utf-8")
    app = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
    assert re.search(r"window\.location\.hash === `#\$\{page\}`\) \{\s*closeDrawer\(\);\s*toTop\(\);", shell), "the menu"
    assert re.search(r"closeLayers\(\);\s*toTop\(\);[^\n]*\n\s*show\(\{ id, arg: null \}\);", app), "a tab"
