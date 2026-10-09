"""Phase 17 #34, palette B, in node: charcoal surfaces for every team, the team's colors as accents only.
--team-us (what is ours) and --team-accent (what is active) always read on the panel; bad colors fall back."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fakedom import needs_node, run_scenario

SCENARIOS = r"""
scenarios.palette = async () => {
  const { teamPalette, paintTeam, contrastRatio } = await import(moduleUrl("theme.js"));
  const teams = [["#0021A5", "#FA4616"], ["#73000A", "#FFFFFF"], ["#FFCD00", "#00274C"], ["#000000", "#FFFFFF"], ["#BA0C2F", "#000000"], ["#4B2E83", "#B7A57A"]];
  const dark = teams.map(([c, a]) => teamPalette(c, a, "dark"));
  // the surfaces are the same neutral greys whatever the team
  for (const key of ["--ground", "--panel", "--band-head", "--rule", "--topbar-bg", "--fog"]) {
    assert.equal(new Set(dark.map((p) => p[key])).size, 1, `${key} is the same for every team`);
  }
  assert.equal(dark[0]["--panel"], "#1C1F26");
  for (const [i, p] of dark.entries()) {
    assert.ok(contrastRatio(p["--team-us"], p["--panel"]) >= 3.6, `${teams[i]} ours reads: ${p["--team-us"]}`);
    assert.ok(contrastRatio(p["--team-accent"], p["--panel"]) >= 3, `${teams[i]} accent reads`);
    assert.ok(contrastRatio(p["--team-primary"], "#f2f4fa") >= 4.5, `${teams[i]} fill holds white text`);
    assert.ok(p["--us-row"].startsWith("rgba("));
  }
  // a navy primary becomes a clear blue on charcoal; the orange second color stays the accent
  const fla = dark[0];
  assert.notEqual(fla["--team-us"].toLowerCase(), "#0021a5");
  assert.equal(fla["--team-accent"], "#FA4616");
  // the light theme: light neutral surfaces, ours still readable
  const light = teamPalette("#0021A5", "#FA4616", "light");
  assert.equal(light["--panel"], "#FFFFFF");
  assert.ok(contrastRatio(light["--team-us"], light["--panel"]) >= 3.6);
  // unusable colors: no palette, and painting clears back to tokens.css
  assert.equal(teamPalette("not a color", null), null);
  const set = new Map();
  const root = { style: { setProperty: (k, v) => set.set(k, v), removeProperty: (k) => set.delete(k) } };
  paintTeam({ color: "#0021A5", altColor: "#FA4616" }, "dark", root);
  assert.equal(set.get("--team-us"), fla["--team-us"]);
  assert.equal(set.get("--topbar-bg"), "#1A1D23");
  paintTeam(null, "dark", root);
  assert.equal(set.size, 0, "no identity: every painted property is cleared");
};
"""


@needs_node
@pytest.mark.parametrize("scenario", ["palette"])
def test_palette_in_node(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)
