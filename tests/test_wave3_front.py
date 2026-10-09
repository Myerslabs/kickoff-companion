"""Phase 16 wave 3, the front end, in the fake browser (tests/fakedom.py) and as static checks: the grouped scores
table that patches itself, the national ticker's star on my teams (6A), the icon sprite and the glyph sweep (3B),
band heads that fold on a tap with a chevron (2B), swipe right to close, the play log's results and drive rows
(L-09), the win-probability chart on game time (5B), the quiet Updated pill and its status card (DS-12), the
sort headers' long press (DS-11), one 13px label size (4B) and the boot outline (DS-13)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.fakedom import needs_node, run_scenario

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"
CSS = (STATIC / "css" / "components.css").read_text(encoding="utf-8")

SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object Object\]/;
const text = (node) => (node ? node.textContent : "");
const clean = (label, node) => {
  const t = text(node);
  assert.ok(!RAW.test(t), `${label} printed ${JSON.stringify(t)}`);
  return t;
};
const pointer = (target, type, x, y, pointerType = "touch") => {
  const event = makeEvent(type, { bubbles: true });
  Object.assign(event, { clientX: x, clientY: y, pointerType, target });
  target.dispatchEvent(event);
  return event;
};
const GAME = (id, status, away, home, extra = {}) => ({ gameId: id, status, detail: status === "final" ? "Final" : status === "live" ? "Q3 4:12" : "7:30 PM", away: { school: away[0], abbr: away[0].slice(0, 3).toUpperCase(), points: away[1] }, home: { school: home[0], abbr: home[0].slice(0, 3).toUpperCase(), points: home[1] }, ...extra });

scenarios.scores = async () => {
  const { scoresTable, scoresSummary } = await import(moduleUrl("ui/scores.js"));
  const list = [
    GAME(1, "final", ["Diner Tech", 21], ["Swampwater Tech", 28]),
    GAME(2, "live", ["Gravel State", 7], ["Harbor A&M", 10], { away: { school: "Gravel State", rank: 9, points: 7 } }),
    GAME(3, "pre", ["Lowland", null], ["Mesa", null]),
    GAME(4, "live", ["North Bend", 3], ["South Fork", 0]),
    null, "junk", 7,
  ];
  assert.equal(scoresSummary(list), "2 live · 1 final · 1 to come");
  assert.equal(scoresSummary([]), "");
  assert.equal(scoresSummary(null), "");
  const wrap = scoresTable({ games: list });
  document.body.append(wrap);
  const groups = [...wrap.querySelectorAll("tr.scores__group")].map(text);
  assert.deepEqual(groups, ["Live (2)", "Upcoming (1)", "Final (1)"], "live first, then upcoming, then final");
  const final = wrap.querySelectorAll("tbody tr")[6];
  assert.ok(final.querySelector(".scores__team--win") && final.querySelector(".scores__team--lose"));
  assert.equal(text(final.querySelector(".scores__pts--win")), "28");
  assert.ok(wrap.querySelector(".scores__st--live") && wrap.querySelector(".scores__st--pre") && wrap.querySelector(".scores__st--final"));
  assert.ok(wrap.querySelector("a.poll-badge, .poll-badge"), "the AP rank is a poll badge");
  clean("scores", wrap);
  // update(): patched in place, only the changed points flash
  const table = wrap.querySelector("table");
  const next = clone(list.slice(0, 4));
  next[1].home.points = 17;
  wrap.update(next);
  assert.equal(wrap.querySelector("table"), table, "the same table, patched");
  const flashed = [...wrap.querySelectorAll(".is-changed")].map((n) => n.dataset.k);
  assert.deepEqual(flashed, ["pts:2:home"]);
  wrap.update([]);
  assert.equal(text(wrap), "No FBS games on this week's slate.");
  assert.equal(text(scoresTable({ games: [], emptyText: "None of your other teams play right now." })), "None of your other teams play right now.");
};

scenarios.tickerStar = async () => {
  const { ticker } = await import(moduleUrl("ui/ticker.js"));
  const games = [GAME(1, "live", ["Diner Tech", 3], ["Mesa", 0], { star: true, isMine: true }), GAME(2, "live", ["Lowland", 0], ["Swampwater Tech", 7], { star: true, isUs: true }), GAME(3, "final", ["North Bend", 1], ["South Fork", 2])];
  const node = ticker({ games, id: "t", label: "FBS scores" });
  document.body.append(node);
  const stars = node.querySelectorAll(".ticker__star");
  assert.ok(stars.length >= 1, "my team's game carries a star");
  for (const star of stars) assert.ok(star.parentNode.className.includes("ticker__game--fav"));
  assert.ok(![...node.querySelectorAll(".ticker__game--us")].some((g) => g.querySelector(".ticker__star")), "never on our own game");
  const none = ticker({ games: [], id: "t2", label: "My teams", emptyText: "None of your other teams play right now." });
  assert.ok(text(none).includes("None of your other teams play right now."));
};

scenarios.icons = async () => {
  const { icon, ICONS } = await import(moduleUrl("ui/icons.js"));
  const star = icon("star");
  assert.equal(star.tagName.toLowerCase(), "svg");
  assert.equal(star.getAttribute("class"), "icon icon--star");
  assert.equal(star.getAttribute("aria-hidden"), "true");
  assert.equal(star.childNodes[0].getAttribute("href"), "/static/icons/ui.svg#i-star");
  const named = icon("search", { label: "Search", className: "x", size: 18 });
  assert.equal(named.getAttribute("role"), "img");
  assert.equal(named.getAttribute("aria-label"), "Search");
  assert.equal(named.getAttribute("width"), "18");
  assert.equal(icon("nope"), null);
  assert.equal(text(icon("nope", { label: "Gone" })), "Gone", "an unknown icon with a label still says it");
  for (const bad of [null, undefined, 3, {}]) assert.equal(icon(bad), null);
  assert.ok(ICONS.includes("chevron-down") && ICONS.includes("stadium"));
};

scenarios.fold = async () => {
  const { band } = await import(moduleUrl("ui/states.js"));
  const { el } = await import(moduleUrl("ui/dom.js"));
  const section = band({ title: "Drives", collapsible: false, foldable: true, summary: "12 drives", tools: el("button", { type: "button" }, "Tool"), body: () => el("p", {}, "inside") });
  document.body.append(section);
  const head = section.querySelector(".band__head");
  const toggle = section.querySelector(".band__toggle");
  assert.ok(toggle.querySelector("svg.icon--chevron-down"), "a chevron, not a minus");
  assert.notEqual(section.dataset.collapsed, "true");
  head.click();
  await advance(400);
  assert.equal(section.dataset.collapsed, "true", "a tap anywhere on the head folds it");
  assert.equal(toggle.getAttribute("aria-expanded"), "false");
  head.click();
  await advance(400);
  assert.equal(section.dataset.collapsed, "false");
  // the toggle folds once, not twice (the head's own tap is not run as well)
  toggle.click();
  await advance(400);
  assert.equal(section.dataset.collapsed, "true");
  toggle.click();
  await advance(400);
  // a tap on something with its own job in the head (a tool button) does not fold
  section.querySelector(".band__head button:not(.band__toggle)")?.click();
  await advance(400);
  assert.equal(section.dataset.collapsed, "false");
  // a tap that closes an open hint card does not fold
  const pop = el("div", { class: "hint-pop" });
  document.body.append(pop);
  head.dispatchEvent(Object.assign(makeEvent("pointerdown", { bubbles: true }), { target: head }));
  pop.remove();
  head.click();
  await advance(400);
  assert.equal(section.dataset.collapsed, "false");
  // a band that does not fold ignores the tap
  const fixed = band({ title: "Fixed", collapsible: false, body: () => el("p", {}, "x") });
  document.body.append(fixed);
  fixed.querySelector(".band__head").click();
  await advance(400);
  assert.notEqual(fixed.dataset.collapsed, "true");
};

scenarios.swipe = async () => {
  const { el, swipeToClose } = await import(moduleUrl("ui/dom.js"));
  let closed = 0;
  const panel = el("aside", {}, el("p", {}, "body"), el("input", {}));
  document.body.append(panel);
  swipeToClose(panel, () => { closed += 1; });
  const p = panel.querySelector("p");
  pointer(p, "pointerdown", 10, 100);
  await advance(200);
  pointer(p, "pointerup", 120, 110);
  assert.equal(closed, 1, "a quick swipe right closes it");
  pointer(p, "pointerdown", 10, 100);
  pointer(p, "pointerup", 40, 100);
  assert.equal(closed, 1, "too short");
  pointer(p, "pointerdown", 10, 100);
  pointer(p, "pointerup", 130, 200);
  assert.equal(closed, 1, "too much drift: a scroll");
  pointer(p, "pointerdown", 10, 100);
  await advance(900);
  pointer(p, "pointerup", 130, 100);
  assert.equal(closed, 1, "too slow");
  pointer(p, "pointerdown", 10, 100, "mouse");
  pointer(p, "pointerup", 130, 100, "mouse");
  assert.equal(closed, 1, "a mouse drag selects text");
  const input = panel.querySelector("input");
  pointer(input, "pointerdown", 10, 100);
  pointer(input, "pointerup", 130, 100);
  assert.equal(closed, 1, "not from a form control");
  pointer(p, "pointerdown", 10, 100);
  pointer(p, "pointercancel", 10, 100);
  pointer(p, "pointerup", 130, 100);
  assert.equal(closed, 1, "a cancelled pointer");
  assert.equal(typeof swipeToClose(null, () => {}), "function");
};

scenarios.playLog = async () => {
  const { playLog } = await import(moduleUrl("ui/play-log.js"));
  const us = { name: "Swampwater Tech", abbr: "SWT" };
  const them = { name: "Diner Tech", abbr: "DT" };
  const play = (id, drive, offense, extra = {}) => ({ id, driveId: `d${drive}`, driveNumber: drive, period: 1, clock: { minutes: 10, seconds: id }, offense, down: 1, distance: 10, yardsToGoal: 60, yardsGained: 4, text: `Play ${id}`, success: false, ...extra });
  const plays = [
    play("6", 2, them.name, { yardsGained: -3 }),
    play("5", 2, us.name, { down: 0, yardsGained: 40, playType: "Kickoff" }), // our kickoff opens their drive
    play("4", 1, us.name, { yardsGained: 25, scoring: true, success: true, flags: ["td"] }),
    play("3", 1, us.name, { yardsGained: 8, success: true }),
    play("2", 1, us.name, { yardsGained: null, success: null }),
    { id: "1", period: 1, offense: us.name, text: "No drive on record" },
    null, "x",
  ];
  const log = playLog({ plays, us, them, freshIds: new Set(["6"]) });
  document.body.append(log);
  const heads = [...log.querySelectorAll(".play-drive")];
  assert.equal(heads.length, 2, "a header over each drive");
  assert.equal(text(heads[0].querySelector(".play-drive__team")), "DT drive 2");
  assert.equal(text(heads[0].querySelector(".play-drive__sum")), "1 play · −3 yds", "a kickoff is not a play of the drive's yards");
  assert.equal(text(heads[1].querySelector(".play-drive__sum")), "3 plays · +33 yds · Points");
  assert.equal(log.querySelectorAll(".plays li.play").length, 6);
  const rows = [...log.querySelectorAll("li.play")];
  assert.ok(rows[0].className.includes("slide-in") && !rows[1].className.includes("slide-in"), "only the fresh play slides in");
  assert.equal(text(rows[0].querySelector(".play__yds")), "−3");
  assert.ok(rows[0].querySelector(".play__yds--loss"));
  assert.equal(rows[1].querySelector(".play__yds"), null, "no yards on a kickoff");
  assert.ok(rows[2].className.includes("play--score"));
  assert.ok(rows[2].querySelector(".play__ok--yes"));
  assert.ok(rows[0].querySelector(".play__ok:not(.play__ok--yes)"), "a hollow dot for a miss");
  assert.equal(rows[4].querySelector(".play__ok"), null, "not judged: no dot");
  clean("play log", log);
  // Key plays: no drive rows
  log.setFilter("key");
  assert.equal(log.querySelectorAll(".play-drive").length, 0);
  assert.equal(log.querySelectorAll("li.play").length, 1);
  log.setFilter("all");
  assert.equal(log.querySelectorAll(".slide-in").length, 0, "a redraw after a filter change slides nothing");
  log.addPlay(play("7", 2, them.name));
  assert.equal(log.querySelectorAll(".slide-in").length, 1);
  assert.equal(text(log.querySelector(".play-drive__sum")), "2 plays · +1 yds");
  log.addPlay(null);
  assert.ok(log.querySelector(".play-tools"));
};

scenarios.wpChart = async () => {
  const { winProbabilityChart, gameSeconds, usSeries } = await import(moduleUrl("ui/wp-chart.js"));
  assert.equal(gameSeconds(1, { minutes: 15, seconds: 0 }), 0);
  assert.equal(gameSeconds(2, "7:30"), 1350);
  assert.equal(gameSeconds(4, { minutes: 0, seconds: 0 }), 3600);
  assert.equal(gameSeconds(5, null), 3750, "overtime sits in its own slot");
  for (const bad of [[null, "1:00"], [0, "1:00"], [2, "x"], [2, null], ["2", "1:00"]]) assert.equal(gameSeconds(...bad), null);
  // the scoreboard readings carry their period and clock
  const live = [{ homeWp: 0.5, period: 1, clock: { minutes: 15, seconds: 0 } }, { homeWp: 0.6, period: 1, clock: { minutes: 2, seconds: 0 } }, { homeWp: 0.7, period: 3, clock: { minutes: 10, seconds: 0 } }, { homeWp: "x" }, null];
  const chart = winProbabilityChart({ series: live, homeIsUs: true, usAbbr: "SWT" });
  assert.equal(chart.querySelectorAll(".wp__tick").length, 3, "a tick between each pair of quarters");
  assert.deepEqual([...chart.querySelectorAll(".wp__cap")].map(text), ["Q1", "Q2", "Q3", "Q4"]);
  assert.equal(chart.querySelector(".wp__area"), null, "no shading");
  assert.equal(chart.querySelector(".wp__svg").getAttribute("preserveAspectRatio"), "none");
  assert.equal(text(chart.querySelector(".wp__now")).startsWith("70"), true);
  assert.ok(chart.querySelector(".wp__plot").getAttribute("aria-label").includes("by game time"));
  clean("wp", chart);
  // the post-game model names its plays: the times come from the play log
  const post = [{ homeWp: 0.4, playId: "a" }, { homeWp: 0.45, playId: "b" }, { homeWp: 0.3, playId: "c" }];
  const plays = [{ id: "a", period: 1, clock: { minutes: 14, seconds: 0 } }, { id: "b", period: 4, clock: { minutes: 1, seconds: 0 } }, { id: "c", period: 6, clock: null }];
  const ot = winProbabilityChart({ series: post, homeIsUs: false, plays, final: true });
  assert.deepEqual([...ot.querySelectorAll(".wp__cap")].map(text), ["Q1", "Q2", "Q3", "Q4", "1OT", "2OT"]);
  assert.ok(text(ot.querySelector(".wp__now")).startsWith("70"), "away side: 1 - 0.3");
  // without times: even spacing, Kickoff and Final at the ends
  const bare = winProbabilityChart({ series: [{ homeWp: 0.4 }, { homeWp: 0.6 }], final: true });
  assert.equal(bare.querySelectorAll(".wp__tick").length, 0);
  assert.equal(text(bare.querySelector(".wp__caption")), "KickoffFinal");
  const empty = winProbabilityChart({ series: "junk" });
  assert.equal(empty.querySelector(".wp__line"), null);
  clean("empty wp", empty);
  assert.deepEqual(usSeries([{ homeWp: 0.25 }, { homeWp: 2 }], false), [0.75, 0]);
};

scenarios.statusPill = async () => {
  installWindow();
  const { statusFor, offlineStatus, agoText } = await import(moduleUrl("views/common.js"));
  const iso = (ms) => new Date(Date.now() - ms).toISOString();
  const fresh = statusFor({ meta: { fetched_at: iso(4 * 60000) }, errors: [] });
  assert.equal(fresh.kind, "quiet");
  assert.equal(fresh.label, "Updated 4 min ago");
  assert.ok(fresh.detail && fresh.updatedAt);
  assert.equal(statusFor({ meta: { fetched_at: iso(5000) } }).label, "Updated just now");
  assert.equal(statusFor({}).label, "Updated");
  assert.equal(statusFor({ meta: { stale: true, fetched_at: iso(600000) } }).kind, "stale");
  assert.ok(offlineStatus(null).detail.includes("could not reach"));
  assert.equal(agoText(7200), "2 h ago");
  assert.equal(agoText(null), null);
  const { shell } = await import(moduleUrl("ui/shell.js"));
  const page = shell({ current: "program" });
  document.body.append(page.root);
  page.setStatus(fresh);
  const pill = page.root.querySelector(".topbar__status .pill--button");
  assert.equal(pill.tagName, "BUTTON");
  assert.equal(text(pill), "Updated 4 min ago");
  // the words age with the clock between refreshes
  await advance(3 * 60000);
  assert.equal(text(page.root.querySelector(".topbar__status .pill")), "Updated 7 min ago");
  page.root.querySelector(".topbar__status .pill").click();
  const card = document.body.querySelector(".status-card");
  assert.ok(card, "the pill opens the status card");
  assert.ok(text(card).includes("came fresh"));
  assert.equal(card.querySelector("a").getAttribute("href"), "/status");
  let retried = 0;
  document.addEventListener("kickoff:retry", () => { retried += 1; });
  card.querySelector(".status-card__retry").click();
  assert.equal(retried, 1);
  await advance(1000);
  assert.equal(document.body.querySelector(".status-card"), null, "it closes after Retry");
  page.setStatus({ kind: "offline", label: "Offline" });
  page.root.querySelector(".topbar__status .pill").click();
  assert.ok(text(document.body.querySelector(".status-card")).includes("could not reach the app's server"));
  page.setStatus(null);
  clean("pill", page.root.querySelector(".topbar__status"));
};

scenarios.slowLoad = async () => {
  // A cold server (the first load after a restart) answers after the browser's 20 s: the page keeps loading and
  // asks again; it never says Offline or "Could not load" while the server is still working.
  installWindow();
  const { poller, SLOW_TRIES, FETCH_TIMEOUT_MS } = await import(moduleUrl("views/common.js"));
  const { loadingSun } = await import(moduleUrl("ui/states.js"));
  let hangs = 2;
  let asked = 0;
  const realFetch = globalThis.fetch;
  globalThis.fetch = (url, opts) => {
    asked += 1;
    if (hangs > 0) {
      hangs -= 1;
      return new Promise((resolve, reject) => opts?.signal?.addEventListener("abort", () => reject(Object.assign(new Error("aborted"), { name: "AbortError" }))));
    }
    return Promise.resolve({ ok: true, status: 200, json: async () => ({ data: { teams: ["A"] }, errors: [], meta: { fetched_at: new Date(Date.now()).toISOString(), stale: false } }) });
  };
  const statuses = [];
  const main = document.createElement("main");
  document.body.append(main);
  const make = (url) => poller({
    url,
    refreshMs: 15 * 60000,
    onStatus: (st) => statuses.push(st),
    render: (env, c) => c.replaceChildren(document.createTextNode(`drawn ${env.data.teams.join(",")}`)),
    renderError: (msg, c) => c.replaceChildren(document.createTextNode(`error ${msg}`)),
    renderLoading: () => document.createTextNode("outline"),
  });
  const page = make("/api/slow-one");
  page.mount(main);
  await settle();
  await advance(FETCH_TIMEOUT_MS + 10);
  assert.ok(!text(main).includes("error"), text(main));
  assert.ok(text(main).includes("Still gathering this page"), "the sun says the server is still working");
  assert.equal(statuses.at(-1).label, "Still loading");
  assert.notEqual(statuses.at(-1).kind, "offline");
  await advance(FETCH_TIMEOUT_MS + 10);
  assert.equal(text(main), "drawn A", "the third ask gets the page");
  assert.equal(asked, 3);
  assert.equal(statuses.at(-1).kind, "quiet");
  assert.ok(statuses.at(-1).label.startsWith("Updated"));
  page.unmount();

  // a server that never finishes: after SLOW_TRIES more rounds the page says so, as "Server slow", not Offline
  hangs = 1000;
  asked = 0;
  const stuck = make("/api/slow-two");
  main.replaceChildren();
  stuck.mount(main);
  await settle();
  for (let i = 0; i <= SLOW_TRIES; i += 1) await advance(FETCH_TIMEOUT_MS + 10);
  assert.equal(asked, SLOW_TRIES + 1);
  assert.ok(text(main).startsWith("error The server did not answer in"), text(main));
  assert.equal(statuses.at(-1).label, "Server slow");
  await advance(5 * 60000);
  assert.equal(asked, SLOW_TRIES + 1, "then it waits for its usual refresh");
  stuck.unmount();

  // an HTTP error is the server answering: "Server error", not Offline
  globalThis.fetch = () => Promise.resolve({ ok: false, status: 500, json: async () => ({ errors: [{ message: "boom" }] }) });
  const broken = make("/api/slow-three");
  main.replaceChildren();
  broken.mount(main);
  await settle();
  assert.equal(statuses.at(-1).label, "Server error");
  assert.ok(text(main).startsWith("error boom"));
  broken.unmount();

  // a network failure is still Offline
  globalThis.fetch = () => Promise.reject(new TypeError("Failed to fetch"));
  const gone = make("/api/slow-four");
  main.replaceChildren();
  gone.mount(main);
  await settle();
  assert.equal(statuses.at(-1).kind, "offline");
  gone.unmount();
  globalThis.fetch = realFetch;
  assert.ok(loadingSun);
};
"""

CASES = ["scores", "tickerStar", "icons", "fold", "swipe", "playLog", "wpChart", "statusPill", "slowLoad"]


@needs_node
@pytest.mark.parametrize("scenario", CASES)
def test_wave3_front_in_a_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)


# --- static checks ---------------------------------------------------------------------------------------------

OLD_GLYPHS = "★☆▶‖▸▾⚑⊗⌕⛈🌧🌨🌫☁⛅☀🏟◀▲▼✓✗"


def _front_files() -> list[Path]:
    return [*sorted((STATIC / "js").rglob("*.js")), *sorted((STATIC / "css").rglob("*.css")), STATIC / "index.html", STATIC / "status.html"]


def test_no_font_glyphs_left_after_the_sweep() -> None:
    """Owner pick 3B: every mark is the sprite or CSS; no font symbol or emoji a tablet may not draw."""
    found = []
    for path in _front_files():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            hits = [c for c in OLD_GLYPHS if c in line]
            if hits:
                found.append(f"{path.relative_to(ROOT)}:{number} {''.join(hits)}")
    assert not found, found


def test_the_sprite_has_every_icon_the_module_names() -> None:
    sprite = (STATIC / "icons" / "ui.svg").read_text(encoding="utf-8")
    module = (STATIC / "js" / "ui" / "icons.js").read_text(encoding="utf-8")
    names = re.findall(r'"([a-z-]+)"', module[module.index("export const ICONS") : module.index("];", module.index("export const ICONS"))])
    assert len(names) >= 20
    for name in names:
        assert f'id="i-{name}"' in sprite, name


def test_nothing_under_13px_but_the_chart_axes() -> None:
    """Owner pick 4B: one 13px label size; only a chart's own axis text may be smaller."""
    small = []
    for number, line in enumerate(CSS.splitlines(), 1):
        for match in re.finditer(r"font-size:\s*(?:calc\()?(\d+(?:\.\d+)?)px", line):  # final pass: scaled sizes count too
            if float(match.group(1)) < 13 and not line.lstrip().startswith((".wp__axis", ".scatter__axis")):
                small.append(f"{number}: {line.strip()[:80]}")
    assert not small, small
    assert re.search(r"\.eyebrow,[^{]*\{\s*font-family: var\(--font-cond\);\s*font-size: calc\(13px \* var\(--ui-scale\)\);", CSS)  # final pass: every size follows the text-size setting


def test_sort_headers_are_finger_sized_and_long_press_reads_them() -> None:
    assert re.search(r"\.stat-table th button \{[^}]*min-height: 44px;", CSS)
    hints = (STATIC / "js" / "ui" / "hints.js").read_text(encoding="utf-8")
    assert "LONG_PRESS_MS = 450" in hints and "dataset.hintSort" in hints and "event.shiftKey" in hints
    assert ".kp\"" in hints or ".kp\";" in hints or ", .kp" in hints


def test_the_wp_chart_strokes_do_not_scale_and_have_no_area() -> None:
    assert ".wp__area" not in CSS
    for cls in (".wp__line", ".wp__mid", ".wp__tick"):
        rule = re.search(re.escape(cls) + r" \{[^}]*\}", CSS)
        assert rule and "vector-effect: non-scaling-stroke" in rule.group(0), cls
    assert re.search(r"\.wp__caption \{[^}]*font-size: calc\(13px \* var\(--ui-scale\)\);", CSS)


def test_index_has_the_boot_outline() -> None:
    page = (STATIC / "index.html").read_text(encoding="utf-8")
    assert 'class="shell__main boot"' in page and page.count('class="skel skel--row"') >= 6
    assert "aria-busy=\"true\"" in page


def test_band_heads_fold_with_a_chevron() -> None:
    assert '.band__toggle::before { content: "\\2212"; }' not in CSS
    assert re.search(r'\.band\[data-collapsed="true"\] \.band__toggle \.icon \{ transform: rotate\(-90deg\); \}', CSS)
    assert ".band--foldable .band__head { cursor: pointer; }" in CSS
