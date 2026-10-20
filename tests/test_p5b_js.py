"""Public release Phase 5b in the fake browser (tests/fakedom.py): the menu's My teams group with one tap to
each primary team, the opponents and My teams switches on a ranked list (their URLs and titles), the My teams
page over a damaged payload (no undefined, null or NaN; dashes for missing games), and the radio help block
(only https links, the request button). Tables wave 3: the My Teams table sizes itself by its own box, every data point in its
own column (the role, why, the last game's result and opponent, the next game and its kickoff), the AP rank as the poll's
badge."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fakedom import STATIC_JS, needs_node, run_scenario

SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object Object\]/;
const text = (node) => (node ? node.textContent : "");
const clean = (label, node) => {
  const t = text(node);
  assert.ok(!RAW.test(t), `${label} printed ${JSON.stringify(t.slice(0, 400))}`);
  return t;
};

scenarios.menu = async () => {
  // owner 2026-10-10: the menu in his order and words
  const { MENU } = await import(moduleUrl("ui/shell.js"));
  const plain = MENU;
  assert.deepEqual(MENU.map((g) => g.group), ["Views", "My Teams", "National", "App"]);
  assert.deepEqual(MENU[0].items.map((i) => i.label), ["Newspaper", "Pre-Game Program", "In Game", "Season", "Top 25", "Preseason Magazine", "Archive", "Season in review"]);
  assert.deepEqual(MENU[1].items.map((i) => i.id), ["myteams", "injuries", "prompts", "roster", "recruiting"]); // the Prompts phase: Prompts after the Injury Report
  assert.deepEqual(MENU[2].items.map((i) => i.id), ["leaders", "ratings"]);
  assert.deepEqual(MENU[3].items.map((i) => i.id), ["invite", "setup", "status", "glossary", "settings"]);
  assert.ok(!MENU.flatMap((g) => g.items).some((i) => ["board", "demo", "radio"].includes(i.id)), "the board is a button on In Game; the demo and the radio are on the Setup page (wave F5: the Archive and the Season in review joined Views)");
  // the tabs: the views in the same order, Top 25 after Season since 2026-10-13 (the magazine only in the menu); the Pre-Game Program stays home
  const { shell, VIEWS } = await import(moduleUrl("ui/shell.js"));
  assert.deepEqual(VIEWS.map((v) => v.id), ["newspaper", "program", "live", "season", "top25"]);
  installWindow();
  const page = shell({ menu: plain });
  document.body.append(page.root);
  const tab = page.root.querySelector('.tab[data-view="live"]');
  const flag = page.root.querySelector(".live-flag");
  assert.equal(page.root.querySelector('.tab[aria-current="page"]').dataset.view, "program");
  assert.ok(flag.hasAttribute("hidden") && !tab.className.includes("tab--live"));
  page.setLive(true);
  assert.ok(!flag.hasAttribute("hidden") && tab.className.includes("tab--live"));
  assert.ok(text(page.root.querySelector(".drawer")).includes("our game is live"));
  page.setLive("yes");
  assert.ok(flag.hasAttribute("hidden") && !tab.className.includes("tab--live"), "only true turns it on");
  assert.ok(!text(page.root.querySelector(".drawer")).includes("our game is live"));
  clean("shell", page.root);
};

scenarios.scopes = async () => {
  installWindow();
  const { nationalApiUrl, listTitle, nationalListBody } = await import(moduleUrl("ui/national-sheet.js"));
  const { nationalHref, nationalRoute, parseRoute } = await import(moduleUrl("ui/national-link.js"));
  assert.equal(nationalApiUrl({ metric: "rating:sp", scope: "opponents" }), "/api/national/rating%3Asp?scope=opponents");
  assert.equal(nationalApiUrl({ metric: "rating:sp", scope: "mine" }), "/api/national/rating%3Asp?scope=mine");
  assert.equal(nationalApiUrl({ metric: "rating:sp", scope: "everything" }), "/api/national/rating%3Asp");
  assert.equal(nationalHref("rating:sp", { scope: "mine", team: "Diner Tech" }), "#national=rating%3Asp?team=Diner%20Tech&scope=mine");
  assert.equal(nationalRoute(parseRoute("#national=rating%3Asp?scope=opponents")).scope, "opponents");
  assert.equal(nationalRoute(parseRoute("#national=rating%3Asp?scope=bogus")).scope, "national");
  assert.equal(listTitle({ label: "SP+ overall", scope: "opponents", us: { team: "Swampwater Tech" } }), "SP+ overall, Swampwater Tech and its opponents");
  assert.equal(listTitle({ label: "SP+ overall", scope: "mine" }), "SP+ overall, my teams");
  const data = {
    metric: "rating:sp", family: "rating", key: "sp", label: "SP+ overall", format: "1f", higherIsBetter: true, season: 2026, year: 2026, years: [2026],
    scope: "mine", scopes: ["national", "conference", "opponents", "mine"], unit: "team", population: "My teams, ranked nationally (FBS teams)", rankSource: "cfbd", of: 136,
    rows: [{ rank: 3, team: "Swampwater Tech", conference: "Biscuit Belt", value: 20.1, isUs: true }, { rank: 40, team: "Cactus Gulch", conference: null, value: null }, null],
    beyond: [], us: { team: "Swampwater Tech", rank: 3, value: 20.1, of: 136 }, focus: null, parts: {},
  };
  const picked = [];
  const body = nationalListBody({ data, errors: [], meta: { source: "live", stale: false } }, { onScope: (s) => picked.push(s) });
  document.body.append(body);
  const seg = body.querySelector(".nat-seg");
  assert.equal(text(seg), "All FBSBiscuit BeltOpponentsMy teams");
  const pressed = seg.querySelectorAll("button").filter((b) => b.getAttribute("aria-pressed") === "true");
  assert.equal(text(pressed[0]), "My teams");
  seg.querySelectorAll("button")[2].click();
  assert.deepEqual(picked, ["opponents"]);
  clean("mine list", body);
  const free = nationalListBody({ data: { ...data, scope: "national", scopes: ["national", "opponents"] }, errors: [], meta: {} }, { onScope: () => {} });
  assert.equal(text(free.querySelector(".nat-seg")), "All FBSOpponents", "a free key: no My teams switch");
};

scenarios.myteams = async () => {
  installWindow();
  const { createMyTeamsView, resultText, opponentText, kickoffText, shapeRows } = await import(moduleUrl("views/myteams.js"));
  assert.equal(resultText({ opponent: "Diner Tech", homeAway: "away", result: "W", usPoints: 31, themPoints: 14 }), "W 31-14");
  assert.equal(resultText({ opponent: "Diner Tech", result: "L" }), "L", "the result alone without a score");
  assert.equal(resultText({ opponent: "Diner Tech" }), "–");
  assert.equal(resultText(null), "–");
  assert.equal(opponentText({ opponent: "Diner Tech", homeAway: "away", opponentAbbr: "DT" }), "at Diner Tech");
  assert.equal(opponentText({ opponent: "Diner Tech", homeAway: "away", opponentAbbr: "DT" }, { short: true }), "at DT");
  assert.equal(opponentText({ opponent: "Lake Effect", homeAway: "neutral", opponentAbbr: " " }, { short: true }), "vs Lake Effect", "no abbreviation: the school");
  assert.equal(opponentText({ opponent: null }), "–");
  assert.equal(kickoffText({ opponent: "Lake Effect", date: "junk" }), "–");
  assert.equal(kickoffText({ opponent: null, date: "2026-10-10T19:30:00Z" }), "–");
  assert.ok(/^[A-Z][a-z]{2} \d{1,2}$/.test(kickoffText({ opponent: "Lake Effect", date: "2026-10-10T19:30:00Z" })), kickoffText({ opponent: "Lake Effect", date: "2026-10-10T19:30:00Z" }));
  assert.equal(shapeRows([null, "junk", { school: "" }, { school: "X", why: [null, "Gravy Ten"], sp: { rank: "1" } }]).length, 1);
  route("/api/myteams", () => envelope({
    season: 2026, pollWeek: 5, plansUrl: "javascript:alert(1)",
    teamSet: { home: "Swampwater Tech", primaries: ["Swampwater Tech", "Diner Tech"], extraPrimaries: ["Diner Tech"], secondary: ["Cactus Gulch"], allowed: true, locked: {} },
    rows: [
      { school: "Swampwater Tech", abbreviation: "SWT", role: "home", why: ["Home team"], record: { wins: 3, losses: 1, ties: 0 }, conferenceRecord: { wins: 1, losses: 0 }, apRank: 12, sp: { value: 20.1, rank: 3, of: 136 }, elo: { value: null, rank: null, of: null }, fpi: {}, last: { opponent: "Silver Dollar", opponentAbbr: "SD", homeAway: "away", result: "W", usPoints: 30, themPoints: 3 }, next: { opponent: "Diner Tech", opponentAbbr: "DT", homeAway: "home", date: "2026-10-10T19:30:00Z" } },
      { school: "Diner Tech", role: "primary", why: ["Primary team"], record: null, apRank: null, sp: null, elo: "junk", fpi: { rank: NaN }, last: null, next: null },
      { school: "Cactus Gulch", abbreviation: "CG", role: "secondary", why: ["Liked school", "Gravy Ten"], record: { wins: "two" }, sp: { rank: 50, of: 136 }, last: { opponent: "Lake Effect", homeAway: "home", result: "L", usPoints: 10, themPoints: 17 } },
      null, "junk",
    ],
    note: null, parts: { teams: { status: "ok" }, records: { status: "ok" }, rankings: { status: "ok" } },
  }));
  const host = document.createElement("main");
  document.body.append(host);
  const view = createMyTeamsView({ onStatus: () => {} });
  view.mount(host);
  await advance(50);
  const all = clean("my teams", host);
  assert.ok(all.includes("Home team") && all.includes("Primary") && all.includes("Secondary"), all.slice(0, 300));
  assert.ok(all.includes("2 primary, 1 secondary"), "the summary counts each kind");
  assert.ok(all.includes("Liked school, Gravy Ten"), "why a secondary team is on the list");
  const links = host.querySelectorAll("a.rank-chip--link").map((a) => a.getAttribute("href"));
  assert.ok(links.includes("#national=rating%3Asp?team=Swampwater%20Tech&scope=mine"), links.join(" "));
  assert.equal(host.querySelectorAll("a").filter((a) => String(a.getAttribute("href")).startsWith("javascript:")).length, 0, "a bad plans link is never drawn");
  // wave 3: sized by its own box (large until the page measures it), every data point in its own column
  const wrap = host.querySelector("#myteams .stat-table-wrap");
  assert.equal(wrap.dataset.size, "large");
  assert.ok(host.querySelector(".page.myteams-page"), "the page may run wider than the others: the large needs about 1,420 px");
  const heads = wrap.querySelectorAll("thead th");
  assert.deepEqual(heads.map((th) => th.dataset.term), ["Team", "Role", "Why", "Record", "Conf record", "AP rank", "SP+ rank", "Elo rank", "FPI rank", "Last game", "Last opponent", "Next game", "Kickoff"]);
  const marks = heads.map((th) => (th.className.includes("st__min-large") ? "L" : th.className.includes("st__min-medium") ? "M" : ""));
  assert.deepEqual(marks, ["", "M", "L", "", "M", "M", "M", "L", "L", "", "", "", "M"], "medium drops Why, Elo and FPI; small keeps the team, record, last and next");
  const words = (th, which) => { const t = th.querySelector(`.sz-t--${which}`); return t ? t.textContent : th.textContent; };
  assert.deepEqual([4, 5, 6, 9, 10, 11, 12].map((i) => words(heads[i], "mid")), ["Conf", "AP", "SP+", "Last", "Opponent", "Next", "Date"]);
  assert.equal(words(heads[10], "short"), "Opp");
  assert.ok(heads.every((th) => th.querySelector("button")), "the teams sort");
  assert.equal(heads.filter((th) => th.className.includes("stick")).length, 0, "a sized table never scrolls sideways, so nothing sticks");
  const cells = (i) => wrap.querySelectorAll("tbody tr")[i].querySelectorAll("td");
  const us = cells(0);
  assert.ok(wrap.querySelectorAll("tbody tr")[0].className.includes("is-us"));
  assert.equal(us[0].querySelector(".sz-t--long button.team-link").dataset.team, "Swampwater Tech");
  assert.equal(us[0].querySelector(".sz-t--short button.team-link").textContent, "SWT", "the abbreviation at small, still its link");
  assert.equal(text(us[1]), "Home team");
  assert.equal(text(us[2]), "–", "the home team needs no why");
  assert.deepEqual([text(us[3]), text(us[4])], ["3-1", "1-0"]);
  const badge = us[5].querySelector("a.poll-badge--link");
  assert.ok(badge, "the AP rank is the poll's badge, a link to the poll");
  assert.equal(badge.getAttribute("href"), "#national=poll%3AAP?team=Swampwater%20Tech");
  assert.equal(us[9].textContent, "W 30-3");
  assert.equal(words(us[10], "long"), "at Silver Dollar");
  assert.equal(words(us[10], "short"), "at SD", "a phone: at or vs and the abbreviation");
  assert.equal(words(us[11], "long"), "vs Diner Tech");
  assert.equal(words(us[11], "short"), "vs DT");
  assert.ok(/^[A-Z][a-z]{2} \d{1,2}$/.test(text(us[12])), text(us[12]));
  const primary = cells(1);
  assert.equal(text(primary[5]), "NR", "unranked in a loaded poll reads NR");
  assert.deepEqual([text(primary[9]), text(primary[10]), text(primary[11]), text(primary[12])], ["–", "–", "–", "–"], "no games: dashes");
  assert.equal(primary[0].querySelector(".sz-t--short button.team-link").textContent, "Diner Tech", "no abbreviation: the school, still a link");
  // the result sorts by its margin, the kickoff by the day, the role home team first
  heads[9].querySelector("button").click();
  assert.deepEqual(wrap.querySelectorAll("tbody tr").map((tr) => tr.querySelectorAll("td")[0].querySelector("button").dataset.team), ["Swampwater Tech", "Cactus Gulch", "Diner Tech"], "the biggest win first, no game last");
  heads[1].querySelector("button").click();
  assert.equal(wrap.querySelectorAll("tbody tr")[0].querySelectorAll("td")[0].querySelector("button").dataset.team, "Swampwater Tech", "the home team first on the first tap");
  view.unmount();
  // the poll not loaded: an unranked team is a dash, never NR
  route("/api/myteams", () => envelope({ season: 2026, pollWeek: null, teamSet: { allowed: false }, rows: [{ school: "Swampwater Tech", role: "home", apRank: null }], note: "Add more with a Tier 2 key.", parts: {} }));
  const { clearEnvelopeCache } = await import(moduleUrl("views/common.js"));
  clearEnvelopeCache();
  const again = document.createElement("main");
  document.body.append(again);
  const view2 = createMyTeamsView({ onStatus: () => {} });
  view2.mount(again);
  await advance(50);
  clean("my teams, no poll", again);
  assert.equal(text(again.querySelectorAll("#myteams tbody tr")[0].querySelectorAll("td")[5]), "–");
  view2.unmount();
};

scenarios.radioHelp = async () => {
  const { cleanHelp, radioHelpBlock } = await import(moduleUrl("radio.js"));
  const help = cleanHelp([
    { school: "Diner Tech", search: [{ label: "Search the web", url: "https://www.google.com/search?q=x" }, { label: "Bad", url: "javascript:alert(1)" }, { label: "Plain", url: "http://x" }], requestUrl: "https://github.com/Myerslabs/kickoff-companion/issues/new?template=radio-station.yml" },
    { school: "", search: [] },
    { school: "No Links", search: "junk", requestUrl: "ftp://x" },
    null,
  ]);
  assert.equal(help.length, 2);
  assert.equal(help[0].search.length, 1, "only https search links survive");
  assert.equal(help[1].requestUrl, null);
  assert.equal(radioHelpBlock([]), null, "nothing to help with: no block");
  const block = radioHelpBlock(help);
  document.body.append(block);
  const t = clean("radio help", block);
  assert.ok(t.includes("Diner Tech: no station in the app yet."));
  const request = block.querySelectorAll("a").find((a) => text(a) === "Request your team's radio");
  assert.ok(request && request.getAttribute("target") === "_blank" && request.getAttribute("rel") === "noopener");
  assert.ok(block.querySelector('a[href="#settings=radio"]'), "it points at Settings' station guide to add a station");
};
"""

NAMES = ["menu", "scopes", "myteams", "radioHelp"]


@needs_node
@pytest.mark.parametrize("scenario", NAMES)
def test_phase5b_in_a_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)


def test_app_registers_the_my_teams_view_and_warms_the_primaries() -> None:
    app = (STATIC_JS / "app.js").read_text(encoding="utf-8")
    assert 'myteams: (opts) => createMyTeamsView(opts)' in app
    assert "menu: MENU," in app, "owner 2026-10-10: the other primary teams are reached from the My Teams page, not the menu"
    assert '"/api/myteams/warm", { method: "POST" }' in app
