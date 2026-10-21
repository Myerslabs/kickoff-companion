"""The Prompts phase (owner 2026-10-13) in the fake browser: the school facts band (every fact a dash when missing, junk
never printed), the Prompts page (one card per prompt with its state, Copy, Paste and Run for the host and none for a
guest, the one run's lines, the schedule), and the release note (one format, once per version, with its close)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fakedom import needs_node, run_scenario

SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object Object\]/;
const text = (node) => (node ? node.textContent : "");
const clean = (label, node) => {
  const t = text(node);
  assert.ok(!RAW.test(t), `${label} printed ${JSON.stringify(t.slice(0, 400))}`);
  return t;
};
Object.getPrototypeOf(document.body).scrollIntoView = function () {};

scenarios.facts = async () => {
  const { factRows, factsBand } = await import(moduleUrl("ui/school-facts.js"));
  const full = { founded: 1853, stadium: "The Bog", stadiumOpened: 1930, capacity: 88548, conferenceSince: 1932, allTimeRecord: "750-440-40", nationalTitles: [1996, 2006, "x"], conferenceTitles: 8, heismans: ["One, 1966", 5, null], bowlRecord: "24-23", rivalries: [{ rival: "Rival U", trophy: "The Cup", firstMeeting: 1915, record: "68-44-2" }, { trophy: "no rival" }, "junk"], headCoachRecord: "30-20", mascotOrigin: " A marsh. ", colorsOrigin: null, fightSong: "Fight!", firstSeason: 1906, mascotName: "Mud", traditions: ["The chomp", 7], nflAlumni: ["Pro One", "", null], savedAt: "2026-08-02T10:00:00Z", sources: [{ label: "Guide", url: "https://example.org/g" }, { label: "No link" }, { url: "javascript:alert(1)" }] };
  const rows = factRows(full);
  assert.equal(rows.length, 21); // freeze wave F4: the Dates row joined the fourteen; the preloaded facts (2026-10-21): first season, winningest coach, longest streak, record crowd, retired numbers, traditions
  assert.equal(rows[1].value, "The Bog, opened 1930, 88,548 seats");
  assert.equal(rows[4].value, "2: 1996, 2006");
  assert.equal(rows[6].value, "1906");
  assert.equal(rows[9].value, "Rival U (The Cup, since 1915, 68-44-2)", "a rivalry with its trophy, the first meeting and the record; one without a rival is left out");
  assert.equal(rows[11].value, "–", "no winningest coach: a dash");
  assert.equal(rows[15].value, "Mud: A marsh.", "the mascot's name, then its origin");
  assert.equal(rows[16].value, "–", "colors missing: a dash");
  assert.equal(rows[18].value, "The chomp", "a tradition that is not text is left out");
  assert.equal(rows[19].value, "Pro One");
  const empty = factRows(null);
  assert.ok(empty.every((r) => r.value === "–"), "nothing loaded: every value a dash");
  const band = factsBand(full, { id: "team-facts", school: "Home U" });
  document.body.append(band);
  const t = clean("facts band", band);
  assert.ok(t.includes("School history") && t.includes("Heisman winners") && t.includes("One, 1966") && t.includes("Sources: Guide"));
  assert.equal(band.querySelectorAll("a").length, 1, "only a real link is offered");
  const none = factsBand(null, { id: "sheet-facts", school: "Away U" });
  document.body.append(none);
  const n = clean("empty facts band", none);
  assert.ok(n.includes("Away U's history and facts are not loaded yet") && n.includes("Open Load data"));
  assert.ok(none.querySelector('a[href="#prompts"]'), "the dead end leads to the Prompts page");
  clean("junk facts", factsBand({ founded: "x", rivalries: null, dates: 5 }, { school: 7 }));
};

const PAGE = {
  commandFound: true,
  command: "claude",
  season: { season: 2026, coachesSaved: 16, coachesOf: 16, costsSaved: 0, factsSaved: 3,
    preseason: [{ school: "Home U", savedAt: "2026-08-02T10:00:00Z" }, { school: "Second U", savedAt: null }, null],
    coaches: [{ conference: "Big Pie", schools: 16, saved: 16, savedAt: "2026-08-02T10:00:00Z" }],
    costs: [{ conference: "Big Pie", schools: 16, saved: 0, savedAt: null }],
    facts: [{ conference: "Big Pie", schools: 16, saved: 3, savedAt: "2026-09-01T10:00:00Z" }, "junk"] },
  seasonRun: { commandFound: true, running: false, kind: "facts", batches: [{ key: "Big Pie", state: "failed", error: "no answer" }] },
  notesRun: { commandFound: true, running: false, error: null },
  notes: { gameId: 42, opponent: "Rival U", writtenAt: null, missing: ["the written notes", "the injury report"] },
  run: { running: true, startedAt: "2026-10-13T12:00:00Z", done: 1, of: 5, steps: [{ kind: "preseason", label: "The season load", state: "skipped", detail: "nothing missing" }, { kind: "coaches", label: "Coaches", state: "running" }, null] },
  schedule: { enabled: true, commandFound: true, running: null, next: [{ key: "n", label: "Monday's notes", at: "2026-10-19T22:00:00Z" }], recent: [{ key: "catch-up", ok: true }, { key: "x", ok: false, error: "broke" }, "junk"] },
};

scenarios.page = async () => {
  installWindow();
  document.body.dataset.role = "host";
  route("/api/prompts", () => envelope(clone(PAGE)));
  const { createPromptsView, promptCards } = await import(moduleUrl("views/prompts.js"));
  const { clearEnvelopeCache } = await import(moduleUrl("views/common.js"));
  clearEnvelopeCache();
  const main = document.createElement("main");
  document.body.append(main);
  const view = createPromptsView({});
  view.mount(main);
  await settle();
  await settle();
  const t = clean("prompts page", main);
  assert.ok(t.includes("Run them all") && t.includes("Run everything that is missing") && t.includes("Running since") && t.includes("The season load: skipped (nothing missing)") && t.includes("Coaches: running"));
  assert.equal(main.querySelectorAll(".band").length, 7, "the run, five cards, the schedule");
  assert.ok(t.includes("not loaded for Second U") && t.includes("Partly loaded"), "the season load is partly loaded");
  assert.ok(t.includes("0 of 16 teams") && t.includes("Missing"), "the costs are missing");
  assert.ok(t.includes("This week's notes, Rival U") && t.includes("missing: the written notes, the injury report"));
  assert.ok(t.includes("Big Pie: failed (no answer)"), "the facts run's batch");
  assert.ok(t.includes("Monday's notes") && t.includes("catch-up: done") && t.includes("x: failed, broke"));
  const buttons = [...main.querySelectorAll("button")].map(text);
  assert.ok(buttons.includes("Copy the prompt") && buttons.includes("Paste the answer") && buttons.includes("Run the missing with Claude Code"));
  assert.ok(main.querySelector("#prompts-run button[disabled]"), "a run under way: the buttons wait");
  view.unmount();
  // a guest: the cards and no buttons at all
  document.body.dataset.role = "guest";
  const guest = document.createElement("div");
  guest.append(...promptCards(clone(PAGE), () => {}));
  clean("guest cards", guest);
  assert.equal(guest.querySelectorAll("button").length, 0);
  document.body.dataset.role = "host";
  // no command: the words say what to do instead; junk never prints
  const junk = document.createElement("div");
  junk.append(...promptCards({ commandFound: false, season: "junk", notes: null, run: 5 }, () => {}));
  const j = clean("junk cards", junk);
  assert.ok(j.includes("This week's notes") && !j.includes("Run the missing"));
};
"""


@needs_node
@pytest.mark.parametrize("scenario", ["facts", "page"])
def test_prompts_in_a_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)


def test_the_reminders_share_one_format() -> None:
    """Owner 2026-10-13: the update banner, the restart banner and the Not loaded yet list are the same note at the top
    of the page, each with its close button; nothing floats at the bottom or slides in from the side."""
    js = Path(__file__).resolve().parents[1] / "static" / "js"
    app = (js / "app.js").read_text(encoding="utf-8")
    assert "update-banner" not in app and 'addNote({ id: "update"' in app and 'addNote({ id: "restart-needed"' in app and 'id: "release"' in app
    assert "startReleaseNote().catch" in app and 'window.localStorage.setItem(RELEASE_SEEN_KEY, data.latest)' in app
    css = (js.parent / "css" / "components.css").read_text(encoding="utf-8")
    assert ".update-banner" not in css and ".page-note__row" in css
    notes = (js / "ui" / "page-notes.js").read_text(encoding="utf-8")
    assert 'class: "btn btn--quiet icon-btn page-note__close"' in notes, "every note closes with its ×"
    shell = (js / "ui" / "shell.js").read_text(encoding="utf-8")
    assert '{ id: "prompts", label: "Load data"' in shell
    for name, needle in (("ui/matchup-card.js", 'href: "#prompts"'), ("ui/roster-costs.js", 'href: "#prompts"'), ("views/preseason.js", 'href: "#prompts"'), ("views/injuries.js", 'href: "#prompts"')):
        assert needle in (js / name).read_text(encoding="utf-8"), f"{name}: the dead end leads to the Prompts page"
