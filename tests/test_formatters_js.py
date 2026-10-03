"""Phase 15: the front end's formatters under Node (node:test style asserts). Every formatter is fed the
values a damaged payload can carry (null, undefined, NaN, Infinity, strings, objects) and must answer
with a number or the dash, never the words undefined, null or NaN on the page."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "static" / "js"

SCRIPT = r"""import assert from "node:assert/strict";
const dom = await import(process.argv[2]);
const weeks = await import(process.argv[3]);
const table = await import(process.argv[4]);
const { DASH } = dom;
const BAD = [null, undefined, NaN, Infinity, -Infinity, "", "abc", {}, [], true];
// Phase 16: "[object Object]" outside the word boundaries (\b never matched before a "[", so it slipped by)
const words = /\b(undefined|null|NaN|Infinity)\b|\[object \w+\]/;
const clean = (label, out) => {
  assert.equal(typeof out, "string", `${label} returned ${typeof out}`);
  assert.ok(!words.test(out), `${label} printed ${JSON.stringify(out)}`);
};

// every formatter, every bad value
for (const bad of BAD) {
  const tag = JSON.stringify(bad) ?? String(bad);
  clean(`text(${tag})`, dom.text(bad));
  clean(`fmtNum(${tag})`, dom.fmtNum(bad, 1));
  clean(`fmtSigned(${tag})`, dom.fmtSigned(bad, 2));
  clean(`fmtPct(${tag})`, dom.fmtPct(bad));
  for (const f of ["pct", "1f", "0f", "2f", "+2f", "+0f", "rank", "unknown", undefined]) clean(`fmtStat(${tag}, ${f})`, dom.fmtStat(bad, f));
  clean(`fmtDate(${tag})`, dom.fmtDate(bad));
  clean(`fmtTime(${tag})`, dom.fmtTime(bad));
  clean(`fmtDateTime(${tag})`, dom.fmtDateTime(bad));
  clean(`fmtClock(${tag})`, dom.fmtClock(bad));
  clean(`ageText(${tag})`, dom.ageText(bad));
  clean(`ordinal(${tag})`, dom.ordinal(bad));
  clean(`period(${tag})`, dom.period(bad));
  clean(`fmtDuration(${tag})`, dom.fmtDuration(bad));
  clean(`weekShort(${tag})`, weeks.weekShort(bad));
  clean(`weekLong(${tag})`, weeks.weekLong(bad));
  clean(`weekShort({week: ${tag}})`, weeks.weekShort({ week: bad }));
  clean(`situationText(${tag})`, dom.situationText({ down: bad, distance: bad, yardsToGoal: bad, offenseAbbr: bad, defenseAbbr: bad }));
}

// good values format as expected
assert.equal(dom.fmtNum(59, 0), "59");
assert.equal(dom.fmtNum(8.04, 1), "8.0");
assert.equal(dom.fmtPct(0.74), "74%");
assert.equal(dom.fmtStat(0.46, "pct"), "46%");
assert.equal(dom.fmtStat(0.241, "+2f"), "+0.24");
assert.equal(dom.fmtStat(-6, "+0f"), "−6"); // a true minus sign, by design
assert.equal(dom.text(0), "0");
assert.equal(dom.fmtNum(null), DASH);

// bowl and playoff weeks (Phase 15)
assert.equal(weeks.weekShort({ week: 3 }), "wk 3");
assert.equal(weeks.weekShort({ week: 1, postseason: "Rose Bowl", playoffRound: "Quarterfinal" }), "CFP QF");
assert.equal(weeks.weekShort({ week: 1, postseason: "Mudpuppy Bowl" }), "Bowl");
assert.equal(weeks.weekShort({ week: 1, playoffRound: "National Championship", postseason: "x" }), "Title");
assert.equal(weeks.weekLong({ week: 1, postseason: "Vrbo Fiesta Bowl" }), "Vrbo Fiesta Bowl");
assert.equal(weeks.weekLong({ week: 7 }), "Week 7");
assert.equal(weeks.weekCell({ week: 7 }), 7);
assert.equal(weeks.weekCell({ week: 1, seasonType: "postseason" }), "Bowl");

// the table sorter reads text cells by meaning and puts dashes last
const values = ["3 of 8", "#12", "+0.24", "43%", DASH, "10-16"].map((v) => table.sortValue(v));
assert.equal(values[4], null);
assert.ok(values.slice(0, 4).every((v) => Array.isArray(v) && v.every(Number.isFinite)), JSON.stringify(values));
assert.deepEqual(values[0], [3 / 8, 8]);

// Phase 16: recruiting ratings and stars as formats (LRP-13); every bad value is a dash
for (const bad of [...BAD, "0.93", "4", -1, 0]) {
  const tag = JSON.stringify(bad) ?? String(bad);
  clean(`fmtStat(${tag}, rating100)`, dom.fmtStat(bad, "rating100"));
  clean(`fmtStat(${tag}, stars)`, dom.fmtStat(bad, "stars"));
  assert.equal(dom.fmtStat(bad, "rating100"), DASH, `rating100 of ${tag}`);
  assert.equal(dom.fmtStat(bad, "stars"), DASH, `stars of ${tag}`);
}
assert.equal(dom.fmtStat(0.9379, "rating100"), "94");
assert.equal(dom.fmtStat(88, "rating100"), "88");
assert.equal(dom.fmtStat(250, "rating100"), DASH);
assert.equal(dom.fmtStat(4, "stars"), "4★");
assert.equal(dom.fmtStat(3.6, "stars"), "4★");
assert.equal(dom.fmtStat(6, "stars"), DASH);
assert.equal(dom.ratingTier(dom.rating100(0.9379)), "top");
assert.equal(dom.ratingTier(dom.rating100(0.85)), "good");
assert.equal(dom.ratingTier(dom.rating100(0.79)), "fair");
assert.equal(dom.ratingTier(null), "");

// Phase 16: routes and list links (DOM-free national-link.js)
const nl = await import(process.argv[5]);
const round = (metric, opts) => {
  const href = nl.nationalHref(metric, opts);
  assert.ok(href && href.startsWith("#national="), `${metric} gave ${href}`);
  const route = nl.parseRoute(href);
  assert.ok(route, `${href} did not parse`);
  assert.equal(route.id, "national");
  assert.equal(route.arg, metric);
  return { href, route, read: nl.nationalRoute(route) };
};
for (const team of ["Texas A&M", "Miami (OH)", "Hawai'i", "Diner Tech", "San José State", "William & Mary?"]) {
  const { href, route, read } = round("profile:ypp_d", { team, scope: "conference" });
  assert.equal(route.params.team, team, `team ${team} through ${href}`);
  assert.equal(read.team, team);
  assert.equal(read.scope, "conference");
  assert.ok(!/[ &]/.test(href.split("?")[1].replace(/&(year|scope)=/g, "")), `the team in ${href} is encoded`);
}
{
  const { href, route, read } = round("board:passing:YDS", { team: "Swampwater Tech", year: 2025 });
  assert.equal(href, "#national=board%3Apassing%3AYDS?team=Swampwater%20Tech&year=2025");
  assert.equal(route.params.year, "2025");
  assert.deepEqual(read, { metric: "board:passing:YDS", team: "Swampwater Tech", year: 2025, scope: "national" });
  assert.equal(route.key, "national=board:passing:YDS?team=Swampwater%20Tech&year=2025");
}
assert.equal(round("advanced:defense_explosiveness").href, "#national=advanced%3Adefense_explosiveness");
// the same list with the query in another order is the same page; another team is another page
const k1 = nl.parseRoute("#national=rating%3Asp?year=2025&team=Swampwater Tech").key;
assert.equal(nl.parseRoute("#national=rating%3Asp?team=Swampwater Tech&year=2025").key, k1);
assert.notEqual(nl.parseRoute("#national=rating%3Asp?team=Silver Dollar&year=2025").key, k1);
assert.equal(nl.parseRoute("national=rating%3Asp?team=Diner+Tech").params.team, "Diner Tech");
// unknown ids, bad encoding and bad metrics are refused, never thrown
for (const bad of ["#bogus=1", "#", "", "#national=%E0%A4%A", "#=x", null, undefined, 42, {}]) assert.equal(nl.parseRoute(bad), null, String(bad));
for (const bad of [null, undefined, "", "ypp", "profile:", "Profile:ypp", "profile:ypp d", "profile:" + "x".repeat(60), 7, {}]) assert.equal(nl.nationalHref(bad), null, String(bad));
assert.equal(nl.nationalHref("profile:ypp", { team: "x".repeat(81), year: "20x5", scope: "sec" }), "#national=profile%3Aypp");
assert.equal(nl.nationalRoute(nl.parseRoute("#national=profile%3Aypp?scope=sec&year=12")).scope, "national");
assert.equal(nl.nationalRoute(nl.parseRoute("#national=not%20a%20metric")).metric, null);
assert.equal(nl.nationalRoute(null).metric, null);
// existing routes read as before
assert.deepEqual([nl.parseRoute("#team=Diner%20Tech").arg, nl.parseRoute("#team=Diner%20Tech").query], ["Diner Tech", ""]);
assert.equal(nl.parseRoute("#program=526001015").arg, "526001015");
assert.equal(nl.parseRoute("season").arg, null);
assert.equal(nl.parseRoute("#season").key, "season=");
assert.equal(nl.parseRoute("#live", new Set(["season"])), null, "a router's own list of ids wins");
// polls: the short names, the list, the Season band
assert.equal(nl.pollName("AP Top 25"), "AP");
assert.equal(nl.pollName("Coaches Poll"), "Coaches");
assert.equal(nl.pollName("Playoff Committee Rankings"), "CFP");
assert.equal(nl.pollName(null), null);
assert.equal(nl.pollHref("AP Top 25", { team: "Swampwater Tech" }), "#national=poll%3AAP?team=Swampwater%20Tech");
assert.equal(nl.pollHref("junk"), null);
assert.equal(nl.pollsPageHref("Coaches Poll"), "#season=polls%3ACoaches");
assert.equal(nl.parseRoute(nl.pollsPageHref("CFP")).arg, "polls:CFP");
assert.equal(nl.pollsPageHref(undefined), "#season");
// the statTable link hook: a row without a metric gets no link
const link = nl.metricLink({ team: "Swampwater Tech" });
assert.equal(link({ metric: "advanced:defense_explosiveness" }), "#national=advanced%3Adefense_explosiveness?team=Swampwater%20Tech");
assert.equal(link({ label: "Explosiveness allowed" }), null);
assert.equal(link(null), null);
assert.equal(nl.metricLink({ team: (row) => row.team, scope: "conference" })({ metric: "profile:ppg", team: "Silver Dollar" }), "#national=profile%3Appg?team=Silver%20Dollar&scope=conference");
assert.ok(nl.isListHref("#national=x%3Ay") && !nl.isListHref("#season") && !nl.isListHref(null));
console.log("ok");
"""


def test_formatters_never_print_undefined_null_or_nan(tmp_path):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    script = tmp_path / "formatters.mjs"
    script.write_text(SCRIPT, encoding="utf-8")
    result = subprocess.run(
        [node, str(script), (JS / "ui" / "dom.js").as_uri(), (JS / "ui" / "weeks.js").as_uri(), (JS / "ui" / "stat-table.js").as_uri(), (JS / "ui" / "national-link.js").as_uri()],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
    )
    assert result.returncode == 0, result.stderr[-3000:]
    assert result.stdout.strip().endswith("ok")
