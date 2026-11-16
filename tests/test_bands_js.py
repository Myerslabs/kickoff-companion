"""Every band its own flyout and page (owner 2026-10-28: "I want to make sure that each band has its own flyout, and page as
well as grouped together somewhere"; "Page opens its list"): the catalog of every page's bands, the holder that shows one band
of a page by itself, the band's own page (#band=<page>:<band>), the flyout's Own page, and where a band is reached from:
since ENH-46 (owner 2026-11-10: "I dont think we need a menu item for things on that page") its own head and Search, never a
row of the menu outside New."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.fakedom import needs_node, run_scenario

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "static" / "js"

SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object \w+\]/;
const text = (node) => (node ? node.textContent : "");

scenarios.catalog = async () => {
  const cat = await import(moduleUrl("ui/band-catalog.js"));
  assert.deepEqual(cat.parseBandArg("season:season-polls"), { route: "season", page: "season", id: "season-polls" });
  assert.deepEqual(cat.parseBandArg("leaders=passing:YDS:national:leaders-grades"), { route: "leaders=passing:YDS:national", page: "leaders", id: "leaders-grades" }, "split at the last colon");
  for (const bad of [null, "", "season", ":x", "season:", "season:1bad", "sea son:x", "season:a b"]) assert.equal(cat.parseBandArg(bad), null, String(bad));
  assert.equal(cat.bandHref("season", "season-polls"), "#band=season:season-polls");
  assert.equal(cat.bandHref("stats-passing", "stats-teams"), "#band=stats=passing:stats-teams?view=teams", "the page's own address and query");
  assert.equal(cat.bandHref("archive", "archive-wp"), "#band=archive=latest:archive-wp", "the last game watched");
  assert.equal(cat.catalogPage(cat.parseBandArg("stats=rushing:stats-players")), "stats-rushing");
  // the owner's test (2026-10-28): the playoff band, drawn only while the team is ranked, is listed first, as the page has it
  assert.equal(cat.bandsOf("season")[0].id, "season-playoff");
  assert.equal(cat.bandHref("season", "roster-table"), "#band=season:roster-table", "the roster's bands are My Team's (wave 3, 2026-11-01)");
  assert.equal(cat.bandsOf("team").length, 0, "the team page's entry went: #team=<school> is My Team's page");
  assert.ok(cat.bandsOf("season").some((b) => b.id === "blame-wheel") && cat.bandsOf("blame").length === 0, "the Circle of Blame's bands are My Team's");
  assert.ok(["archive-box", "archive-notes", "archive-availability"].every((id) => cat.findBand("archive", id)) && !cat.findBand("archive", "archive-mynotes"), "the archived game's every band (My notes dropped, wave 3 2026-11-01)");
  assert.equal(cat.catalogPage(cat.parseBandArg("nope:x")), null);
  // Own page from any entry that opens wide
  assert.equal(cat.ownHref({ flyout: "program:matchup" }), "#band=program:program-matchup");
  assert.equal(cat.ownHref({ flyout: "program:matchup" }, { route: "program=401" }), "#band=program=401:program-matchup", "the program on screen");
  assert.equal(cat.ownHref({ flyout: "program:matchupLast" }), "#band=program:program-matchup-last?view=last", "a box's other view: its own page, the box opened on that view");
  assert.equal(cat.ownHref({ flyout: "band:roster:roster-costs" }), "#band=roster:roster-costs");
  assert.equal(cat.ownHref({ live: "drives" }), "#band=live:drives");
  assert.equal(cat.ownHref({ flyout: "radio" }), null, "the station list has no page of its own");
  assert.equal(cat.ownHref({ flyout: "program:nothing" }), null);
  // a page's list: the whole page first, then each band, each kind opening its own way
  const list = cat.pageList("season");
  assert.equal(list[0].label, "The whole page");
  assert.equal(list[0].searchLabel, "My Team");
  assert.equal(list[0].page, "season");
  assert.ok(list.slice(1).every((e) => e.flyout && e.flyout.startsWith("band:season:")), "the Season's bands open by themselves");
  assert.deepEqual(list.slice(1).map((e) => e.id.split(":")[1]), cat.bandsOf("season").map((b) => b.id), "in the page's order");
  const program = cat.pageList("program");
  assert.equal(program.find((e) => e.id === "program:program-matchup").flyout, "program:matchup", "the program's own builders where it has them");
  assert.equal(program.find((e) => e.id === "program:program-schools").flyout, "program:schools", "The two schools and the series has its own builder since the line's Wave 2");
  assert.equal(program.find((e) => e.id === "program:program-scout").flyout, "band:program:program-scout", "a band with no builder is drawn by its page in the flyout");
  assert.equal(cat.pageList("live").find((e) => e.id === "live:chart").live, "chart", "In Game's panels open over In Game");
  assert.ok(cat.pageList("archive").some((e) => e.heading === "The last game watched"), "headings kept");
  assert.deepEqual(cat.pageList("nope"), []);
  // every page's band ids are its own, once
  for (const [page, meta] of Object.entries(cat.BAND_PAGES)) {
    const ids = cat.bandsOf(page).map((b) => b.id);
    assert.equal(new Set(ids).size, ids.length, `${page}: an id twice`);
    assert.ok(ids.every((id) => /^[A-Za-z][\w-]*$/.test(id)), page);
    assert.ok(meta.label && meta.hint && meta.route, page);
  }
};

function fakePage(drawn) {
  // a page view the way the app's are: it draws its page into the holder, a band folded, chips over the page, and redraws
  let host = null;
  const make = (ids) => {
    const page = document.createElement("div");
    page.className = "page flow";
    for (const id of ids) {
      const s = document.createElement("section");
      s.className = "band band--foldable";
      s.setAttribute("id", id);
      s.setAttribute("data-collapsed", id === "b-two" ? "true" : "false");
      const head = document.createElement("div");
      head.className = "band__head";
      const h = document.createElement("h2");
      h.className = "band__title";
      h.textContent = id;
      head.append(h);
      s.append(head);
      page.append(s);
    }
    const chips = document.createElement("nav");
    chips.className = "section-chips";
    return [chips, page];
  };
  return {
    mounted: 0,
    unmounted: 0,
    mount(node) {
      host = node;
      this.mounted += 1;
      node.replaceChildren(...make(drawn.ids));
    },
    redraw(ids) {
      if (host) host.replaceChildren(...make(ids));
    },
    refresh() {
      return "refreshed";
    },
    unmount() {
      this.unmounted += 1;
    },
  };
}

scenarios.solo = async () => {
  installWindow();
  const { soloMount, bandNode } = await import(moduleUrl("ui/solo.js"));
  const box = document.createElement("div");
  document.body.append(box);
  const drawn = { ids: ["b-one", "b-two", "b-three"] };
  const view = fakePage(drawn);
  const solo = soloMount({ view, container: box, band: { id: "b-two" }, label: "Two", pageHref: "#season" });
  await settle();
  await advance(300);
  const holder = box.querySelector(".solo");
  assert.equal(holder.getAttribute("data-solo"), "shown");
  const two = holder.querySelector("#b-two");
  assert.ok(two.className.includes("solo-target"), "the band, marked");
  assert.equal(two.getAttribute("data-collapsed"), "false", "always unfolded");
  assert.ok(holder.querySelector("#b-one").className.includes("solo-off") && holder.querySelector("#b-three").className.includes("solo-off"), "the bands beside it step aside");
  assert.ok(holder.querySelector(".section-chips").className.includes("solo-off"), "and the chips over the page");
  assert.ok(holder.querySelector(".page").className.includes("solo-chain"), "the page above it holds it across the width");
  // a redraw draws new elements: they are marked again
  view.redraw(["b-zero", "b-two"]);
  await settle();
  await advance(300);
  assert.ok(holder.querySelector("#b-zero").className.includes("solo-off") && holder.querySelector("#b-two").className.includes("solo-target"), "marked again after a redraw");
  assert.equal(solo.refresh(), "refreshed", "Pull to refresh reaches the page's view");
  // another band of the same page: no remount
  solo.setBand({ id: "b-zero" }, "Zero");
  assert.ok(holder.querySelector("#b-zero").className.includes("solo-target") && holder.querySelector("#b-two").className.includes("solo-off"));
  assert.equal(view.mounted, 1);
  // a band the page does not draw: missing once the page has settled, with the way to the whole page
  solo.setBand({ id: "b-nine" }, "Nine");
  await advance(9000);
  assert.equal(holder.getAttribute("data-solo"), "missing");
  const status = box.querySelector(".solo__status");
  assert.ok(text(status).includes("Nothing to show in Nine right now") && status.querySelector('a[href="#season"]'), text(status));
  assert.ok(!RAW.test(text(box)));
  // it comes once the page draws it
  view.redraw(["b-nine"]);
  await settle();
  await advance(300);
  assert.equal(holder.getAttribute("data-solo"), "shown");
  assert.equal(text(box.querySelector(".solo__status")), "");
  solo.unmount();
  assert.equal(view.unmounted, 1, "the page's view goes with it");
  // a selector band: the first match
  assert.equal(bandNode(holder, { select: "section.band:not(#b-one)" }).getAttribute("id"), "b-nine");
  assert.equal(bandNode(holder, { id: "bad id" }), null, "an id that is not one is never put in a selector");
  assert.equal(bandNode(null, { id: "x" }), null);
  // a page still loading waits: no missing line while it shows its loading state
  const slow = { mount(node) { const busy = document.createElement("div"); busy.setAttribute("aria-busy", "true"); node.replaceChildren(busy); }, unmount() {} };
  const box2 = document.createElement("div");
  document.body.append(box2);
  const waiting = soloMount({ view: slow, container: box2, band: { id: "x" }, label: "X" });
  await advance(9000);
  assert.equal(box2.querySelector(".solo").getAttribute("data-solo"), "waiting", "still loading: it waits");
  waiting.unmount();
};

scenarios.page = async () => {
  installWindow();
  const { registerPages, createBandView, bandTarget, pageView } = await import(moduleUrl("views/band.js"));
  const drawn = { ids: ["season-schedule", "season-ratings"] };
  const made = [];
  registerPages({
    season: (opts, arg, focus, params) => {
      made.push({ arg, params });
      return fakePage(drawn);
    },
    band: () => null,
  });
  const t = bandTarget("season:season-ratings", {});
  assert.equal(t.label, "Ratings");
  assert.equal(t.pageLabel, "My Team");
  assert.equal(t.address, "season");
  assert.deepEqual(bandTarget("stats=passing:stats-teams", { view: "teams" }).address, "stats=passing?view=teams");
  assert.deepEqual(bandTarget("preseason:preseason-home", {}).which.select.startsWith("section.band"), true, "a band named by a selector");
  assert.equal(bandTarget("nope", {}), null);
  assert.equal(pageView("band=season:x"), null, "a band page is never a band's page");
  const main = document.createElement("main");
  document.body.append(main);
  const statuses = [];
  const view = createBandView({ onStatus: (s) => statuses.push(s), arg: "season:season-ratings", params: {} });
  view.mount(main);
  await settle();
  await advance(300);
  assert.equal(text(main.querySelector(".band-page__title")), "Ratings", "the band's name heads its page");
  assert.equal(main.querySelector(".back-row a").getAttribute("href"), "#season", "Back falls back to the whole page");
  assert.equal(main.querySelector(".band-page__whole").getAttribute("href"), "#season");
  assert.ok(main.querySelector("#season-ratings").className.includes("solo-target"));
  assert.ok(main.querySelector("#season-schedule").className.includes("solo-off"));
  assert.deepEqual(made[0], { arg: null, params: {} });
  view.unmount();
  // an address that names no table says so
  const lost = createBandView({ onStatus: (s) => statuses.push(s), arg: "nonsense" });
  lost.mount(main);
  assert.ok(text(main).includes("This address names no table"));
  assert.equal(statuses[statuses.length - 1].label, "No such table");
  assert.ok(!RAW.test(text(main)));
};

scenarios.own = async () => {
  installWindow();
  const { openWide, ownButton } = await import(moduleUrl("ui/flyout.js"));
  assert.equal(ownButton(null), null);
  assert.equal(ownButton({ href: "javascript:alert(1)" }), null, "only an address of the app");
  const handle = openWide({ title: "Polls", subtitle: "Season", own: { href: "#band=season:season-polls" }, body: document.createElement("div") });
  const layer = document.body.querySelector(".sheet-layer");
  const own = layer.querySelector(".side-sheet__head .flyout-own");
  assert.equal(own.getAttribute("href"), "#band=season:season-polls", "Own page in the flyout's head");
  assert.ok(text(own).includes("Own page"));
  handle.setOwn({ href: "#band=season:season-ratings" });
  assert.equal(layer.querySelector(".flyout-own").getAttribute("href"), "#band=season:season-ratings", "it follows previous and next");
  handle.setOwn(null);
  assert.equal(layer.querySelector(".flyout-own"), null);
  handle.close();
};

scenarios.menu = async () => {
  // ENH-46 (owner 2026-11-10: "I dont think we need a menu item for things on that page"): every band of the catalog still
  // opens wide by itself, once a page, from Search and its own head; none is a row of the menu outside New, his testing
  // list; every listed page is one row that opens the page
  const { MENU, allEntries, findPath } = await import(moduleUrl("ui/menu-tree.js"));
  const cat = await import(moduleUrl("ui/band-catalog.js"));
  const found = cat.allBands();
  const rows = allEntries(MENU).map((x) => x.entry).filter((e) => !String(e.id).startsWith("new:")); // New keeps a row for a band he is testing
  const opens = (list, page, band) => list.filter((e) => (page === "program" && band.key ? e.flyout === `program:${band.key}` : page === "live" ? e.live === (band.panel || band.id) : e.flyout === `band:${page}:${band.id}`));
  const missing = [];
  const listed = [];
  for (const page of Object.keys(cat.BAND_PAGES)) {
    for (const band of cat.bandsOf(page)) {
      const hits = opens(found.filter((b) => b.page === page).map((b) => b.entry), page, band);
      if (hits.length !== 1) missing.push(`${page}:${band.id} (${hits.length})`);
      if (opens(rows, page, band).length) listed.push(`${page}:${band.id}`);
    }
  }
  assert.deepEqual(missing, [], "every band once in what Search finds");
  assert.deepEqual(listed, [], "no band is a row of the menu");
  for (const page of ["season", "roster", "recruiting", "preseason", "archive", "leaders", "stats-passing", "ratings", "newspaper", "top25", "conference", "program", "live"]) {
    const address = cat.BAND_PAGES[page].route;
    const path = findPath(MENU, (e) => e.page === address && !e.icon);
    assert.ok(path && path.length === 2, `${page}: one row of its group opens the page (${path})`);
    assert.ok(!findPath(MENU, (e) => e.id === `${page}:page` && e.label === "The whole page"), `${page}: no list for The whole page to top`);
  }
};
"""


@needs_node
@pytest.mark.parametrize("scenario", ["catalog", "solo", "page", "own", "menu"])
def test_bands_in_a_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)


def test_the_router_builds_the_band_page_and_in_game_draws_one_panel() -> None:
    app = (JS / "app.js").read_text(encoding="utf-8")
    assert "band: (opts, arg, focus, params) => createBandView({ ...opts, arg, params })" in app
    assert "registerPages(BUILT);" in app
    assert 'const shown = route.id === "band" ? bandPage(route) : route;' in app, "a band's page belongs to its page's tab"
    live = (JS / "views" / "live.js").read_text(encoding="utf-8")
    assert "export function createLiveView({ onStatus, board = false, panel = null } = {}) {" in live
    assert "if (panel) {" in live and "drawPanel(view);" in live, "the panel mode draws the one panel"
    assert re.search(r'\{ id: "score", label: "Score by quarter"', live) and re.search(r'\{ id: "chart", label: "Shot chart"', live), "the stage's two as panels"


def test_the_rows_that_were_one_band_went_and_the_lists_they_need() -> None:
    """The owner's test (2026-10-28): National's AP poll opened the Season page, not its own, so a row that was one band of a
    page opened that band's own page. ENH-46 (owner 2026-11-10: no menu item for a thing on a page): those six rows went with
    the lists of bands; the bands' own pages still open (tools/page_check.py keeps their addresses). National recruiting opens
    this season's class list by name; the team page opens on a tab."""
    from app.services.national import resolve

    tree = (JS / "ui" / "menu-tree.js").read_text(encoding="utf-8")
    for page in ("band=newspaper:np-polls?poll=AP", "band=newspaper:np-polls?poll=Coaches", "band=ratings=sp:ratings-sp", "band=ratings=elo:ratings-side", "band=leaders=usage:overall:national:leaders-usage-overall", "band=leaders=ppa:all:national:leaders-ppa-all"):
        assert f'page: "{page}"' not in tree, f"{page}: one band of a page is no row of the menu"
    assert "pageList(" not in tree, "no page's row opens a list of its bands"
    assert 'page: "national=class:current"' in tree
    assert 'page: "season=polls:AP"' not in tree
    check = (ROOT / "tools" / "page_check.py").read_text(encoding="utf-8")
    for address in ("band=newspaper:np-polls?poll=AP", "band=ratings=sp:ratings-sp", "band=ratings=elo:ratings-side", "band=leaders=usage:overall:national:leaders-usage-overall"):
        assert address in check, f"{address}: the band's own page is still checked"
    current = resolve("class:current", 2026)
    assert current is not None and current.key == "class:2026", "this season's class"
    assert resolve("class:soon", 2026) is None and resolve("class:2031", 2026) is None
    team = (JS / "views" / "team.js").read_text(encoding="utf-8")
    assert "export function teamExtraBands(data, state)" in team and "TABS" not in team, "wave 3 (2026-11-01): the team page is My Team's page, its bands builders for it; no tabs"
    season = (JS / "views" / "season.js").read_text(encoding="utf-8")
    assert 'TAB_FOCUS = { schedule: "#season-schedule", roster: "#roster-table", coaches: "#team-staff", history: "#team-facts" }' in season, "the old team page's ?tab= lands on the band"


def test_every_catalog_band_is_drawn_by_its_page() -> None:
    """A renamed band would leave its flyout pointing at nothing: each fixed id of the catalog is in its page's code."""
    sources = {
        "season": ["views/season.js", "ui/numbers-band.js"],
        "roster": ["views/roster.js"],
        "recruiting": ["views/recruiting.js"],
        "archive": ["views/archive.js"],
        "team": ["views/team.js", "ui/numbers-band.js"],
        "program": ["views/program.js", "ui/strengths.js", "ui/race.js", "ui/writing-band.js", "ui/offday.js", "ui/two-schools.js"],
        "newspaper": ["views/newspaper.js", "ui/writing-band.js"],
        "ratings": ["views/ratings.js"],
        "preseason": ["views/preseason.js"],
        "stats": ["views/stats.js"],
    }
    catalog = (JS / "ui" / "band-catalog.js").read_text(encoding="utf-8")
    ids = re.findall(r'\{ id: "([a-z][\w-]*)"', catalog)
    missing = []
    for band_id in ids:
        page = band_id.split("-")[0]
        if page not in sources or band_id in {"preseason-home", "np-weeks", "team-offense", "team-defense", "program-matchup-last", "program-week-ppa", "program-box-advanced", "season-advanced", "season-numbers-ours"}:  # named by a selector (a box's other views open the box on that view); the team page's summary prefix
            continue
        code = "".join((JS / f).read_text(encoding="utf-8") for f in sources[page] if (JS / f).exists())
        dynamic = band_id.rsplit("-", 1)[0] + "-$" in code or f"{band_id.split('-')[0]}-${{" in code
        if f'"{band_id}"' not in code and f"`{band_id}`" not in code and not dynamic:
            missing.append(band_id)
    assert not missing, f"catalog ids no page draws: {missing}"
