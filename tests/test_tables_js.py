"""Table sizes (owner 2026-10-10; the matchup band as the test bed) in the fake browser: the two-team table draws
every data point in its own column with three head forms, group rows carry each team's scheme under its own columns
(or the way to the notes), applySize sets the spans for large, medium and small and drops a table that fits nowhere;
the matchup card's hero is one name line and one chip line (no Team page chip, the last five link to box scores,
the conference tag alone); the stat table's opt-in sizes; and every label has its three forms. Wave 2: the shared pieces
(the lean, Team stats, the box score, the graded table) and the Pre-Game Program's tables (the tendencies, play value,
common opponents on the two-team kit, the advanced box score, a row that names a team) and In Game's (the quarter splits,
the tendencies, the fourth-down choice, the recruits, the drive summary and each team's play value on the kit, the
Situation panel as Team stats, the scores sized in place, the penalty sheet's calls). Wave 3: the kit's shared pieces (a sub
with a head as its own column, a list's own order as a chip that turns plain at small, a drawn cell's own small form, empty
rank cells on group rows, a column that keeps a plain head, ISO dates that sort by day) and the two-team kit's player column;
the Season page's tables (the standings, the stat profile, the advanced table, the resume, this season and last, the road
ahead) on the kit, each data point in its own column. Step 4: the availability table (the team and the position in columns
of their own, the team kept at small as its abbreviation in a two-team report, the status colored through a sort and
shortened at small)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fakedom import needs_node, run_scenario

SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object Object\]/;
const text = (node) => (node ? node.textContent : "");
const cls = (node) => (node ? node.className : "");
const form = (cell, which) => { const t = cell.querySelector(`.tt__t--${which}`); return t ? t.textContent : text(cell); };
const form2 = (cell, which) => { const t = cell.querySelector(`.sz-t--${which}`); return t ? t.textContent : text(cell); }; // a sized stat table's words

function rows() {
  return [
    { label: "Points per game", side: "offense", format: "1f", higherIsBetter: true, metric: "profile:ppg", us: { value: 46.2, rank: 5, of: 136, conf: { rank: 1, of: 16, conference: "Big Pie", href: "#national=profile%3Appg?team=Swampwater%20Tech&scope=conference" } }, them: { value: 37.6, rank: 26, of: 136, conf: { rank: 6, of: 16, conference: "Big Pie" } } },
    { label: "Pass yards per game", side: "offense", format: "0f", higherIsBetter: true, metric: "profile:pass_ypg", us: { value: 275, rank: 29, of: 136 }, them: { value: 235, rank: 65, of: 136 } },
    { label: "Points allowed per game", side: "defense", format: "1f", higherIsBetter: false, metric: "profile:opp_ppg", us: { value: 27.2, rank: 103, of: 136 }, them: { value: 26.8, rank: 100, of: 136 } },
  ];
}

scenarios.forms = async () => {
  const { labelForms, knownLabels, SIZES, DROPPED } = await import(moduleUrl("ui/sizes.js"));
  assert.deepEqual(SIZES, ["large", "medium", "small"]);
  assert.equal(DROPPED, "none");
  assert.deepEqual(labelForms("Points per game"), { long: "Points per game", mid: "Points per game", short: "PPG" });
  assert.deepEqual(labelForms("Pass yards allowed per game"), { long: "Pass yards allowed per game", mid: "Pass yds allowed", short: "Pass" });
  assert.deepEqual(labelForms("Something new"), { long: "Something new", mid: "Something new", short: "Something new" }, "an unknown label keeps its words");
  assert.deepEqual(labelForms(null), { long: "", mid: "", short: "" });
  for (const label of knownLabels()) {
    const f = labelForms(label);
    assert.ok(f.short.length <= 13, `${label}: the short form is a phone's word (${f.short})`);
    assert.ok(f.mid.length <= 24, `${label}: the middle form is one line (${f.mid})`);
    assert.ok(f.short.trim() && f.mid.trim(), label);
  }
  // wave 3, step 5: the shorter forms are guarded like the long one (a damaged week or label once printed "[object Object]"
  // at medium and small in a sized table's first column)
  const { sizedText, statTable } = await import(moduleUrl("ui/stat-table.js"));
  const words = (parts) => parts.map((p) => (typeof p === "string" ? p : p.textContent));
  assert.deepEqual(words(sizedText("[object Object]", "[object Object]", "[object Object]")), ["–"]);
  assert.deepEqual(words(sizedText("Year", "[object Object]", " Yr ")), ["Year", "–", "Yr"]);
  const wrap = statTable({ sizes: true, columns: [{ key: "wk", label: "Wk", kind: "text" }, { key: "n", label: "N" }], rows: [{ wk: "[object Object]", n: 1 }] });
  assert.ok(!RAW.test(text(wrap)), text(wrap));
};

scenarios.twoteam = async () => {
  const { twoTeamTable, applySize } = await import(moduleUrl("ui/two-team.js"));
  let asked = 0;
  const groups = [
    { title: "Offense", rows: rows().filter((r) => r.side === "offense"), us: "Spread option", them: null, missing: { label: "Get this week's notes", onClick: () => { asked += 1; } } },
    { title: "Defense", rows: rows().filter((r) => r.side === "defense"), us: "3-4", them: "4-2-5" },
  ];
  const wrap = twoTeamTable({ groups, usAbbr: "SWT", themAbbr: "DT", usTeam: "Swampwater Tech", themTeam: "Diner Tech", usName: "Swampwater Tech Mudcats", themName: "Diner Tech Waffles", tug: true, labelHead: "This season" });
  document.body.append(wrap);
  assert.ok(!RAW.test(text(wrap)), text(wrap));
  assert.equal(wrap.dataset.size, "large", "drawn large until it measures itself");
  // the large head: each team over its three columns, the rank heads under it; the one-row head for medium and small
  const headA = [...wrap.querySelectorAll("tr.tt__head--a th")];
  assert.deepEqual(headA.map((th) => form(th, "long")), ["This season", "Swampwater Tech Mudcats", "Edge", "Diner Tech Waffles"]);
  assert.deepEqual(headA.map((th) => th.getAttribute("colspan")), [null, "3", null, "3"]);
  assert.deepEqual([...wrap.querySelectorAll("tr.tt__head--b th")].map(text), ["FBS rank", "Big Pie rank", "", "", "Big Pie rank", "FBS rank"]);
  const one = [...wrap.querySelectorAll("tr.tt__head--one th")];
  assert.deepEqual(one.map((th) => form(th, "mid")), ["This season", "FBS", "Swampwater Tech", "Edge", "Diner Tech", "FBS"]);
  assert.deepEqual(one.map((th) => form(th, "short")), ["Season", "FBS", "SWT", "Edge", "DT", "FBS"]);
  assert.equal(one[1].dataset.term, "FBS rank", "the hint reads the long head");
  // every data point its own column, mirrored outward from the bar
  const first = wrap.querySelectorAll("tbody tr:not(.tt__group)")[0];
  assert.deepEqual([...first.childNodes].map((td) => cls(td).split(" ")[0]), ["txt", "tt__rank", "tt__rank", "num", "tt__tug", "num", "tt__rank", "tt__rank"]);
  assert.ok(cls(first.childNodes[1]).includes("tt__rank--natl") && cls(first.childNodes[2]).includes("tt__rank--conf"), "ours: national outside, conference next in");
  assert.ok(cls(first.childNodes[6]).includes("tt__rank--conf") && cls(first.childNodes[7]).includes("tt__rank--natl"), "theirs mirrored");
  assert.ok(cls(first.childNodes[2]).includes("tt__min-large") && cls(first.childNodes[1]).includes("tt__min-medium"), "the conference chip needs large, the national chip medium");
  assert.equal(first.childNodes[2].querySelector("a.rank-chip--link").getAttribute("href"), "#national=profile%3Appg?team=Swampwater%20Tech&scope=conference");
  assert.ok(first.childNodes[6].querySelector(".rank-chip:not(.rank-chip--link)"), "a conference rank with no list is a plain chip");
  assert.equal(form(first.childNodes[0], "short"), "PPG");
  assert.equal(first.childNodes[0].dataset.term, "Points per game");
  assert.ok(cls(first.childNodes[3]).includes("lead") && cls(first.childNodes[5]).includes("trail"));
  // group rows: the title, each team's scheme under its own columns, the way to the notes where one is missing
  const grp = wrap.querySelectorAll("tr.tt__group");
  assert.equal(grp.length, 2);
  assert.ok(cls(grp[0]).includes("tt__group--sided"));
  assert.equal(form(grp[0].querySelector("th"), "short"), "Off");
  assert.equal(form(grp[1].querySelector("th"), "short"), "Def (allowed)");
  assert.equal(text(grp[0].querySelector("td.tt__scheme.tt__us")), "Spread option");
  const get = grp[0].querySelector("td.tt__scheme.tt__them button.tt__get");
  assert.ok(get && text(get) === "Get this week's notes", "the missing scheme is the way to the notes, never a blank");
  get.click();
  assert.equal(asked, 1);
  assert.equal(text(grp[1].querySelector("td.tt__scheme.tt__them")), "4-2-5");
  assert.deepEqual([grp[0].querySelector("th").getAttribute("colspan"), grp[0].querySelector("td.tt__us").getAttribute("colspan"), grp[0].querySelector("td.tt__them").getAttribute("colspan")], ["1", "3", "3"], "large: the scheme spans the three columns");
  // medium: the conference columns gone, the scheme spans two; the abbreviation step keeps medium with short names
  applySize(wrap, "medium");
  assert.equal(wrap.dataset.size, "medium");
  assert.deepEqual([grp[0].querySelector("td.tt__us").getAttribute("colspan"), grp[0].querySelector("td.tt__them").getAttribute("colspan")], ["2", "2"]);
  assert.ok(!wrap.dataset.names);
  applySize(wrap, "medium:abbr");
  assert.equal(wrap.dataset.size, "medium");
  assert.equal(wrap.dataset.names, "short");
  // small: no chips, the title spans the four columns and the schemes hide
  applySize(wrap, "small");
  assert.equal(wrap.dataset.size, "small");
  assert.ok(!wrap.dataset.names);
  assert.equal(grp[0].querySelector("th").getAttribute("colspan"), "4");
  assert.ok(grp[0].querySelector("td.tt__us").hidden === true && grp[0].querySelector("td.tt__them").hidden === true && grp[0].querySelector("td.tt__scheme-gap").hidden === true);
  // dropped: the table hidden, a note in its place; back to large and the note goes
  applySize(wrap, "none");
  assert.equal(wrap.dataset.size, "none");
  assert.ok(wrap.querySelector("table").hidden === true && wrap.querySelector(".size-note") && cls(wrap).includes("stat-table-wrap--dropped"));
  assert.ok(text(wrap.querySelector(".size-note")).includes("wider screen"));
  applySize(wrap, "large");
  assert.ok(wrap.querySelector("table").hidden === false && !wrap.querySelector(".size-note") && !cls(wrap).includes("stat-table-wrap--dropped"));
  assert.equal(grp[0].querySelector("td.tt__us").hidden, false);
  // a plain group (no schemes) is one cell across the width at every size
  const plain = twoTeamTable({ groups: [{ title: "Per game", rows: rows().slice(0, 2) }], usAbbr: "SWT", themAbbr: "DT", tug: true });
  const th = plain.querySelector("tr.tt__group th");
  assert.equal(text(th), "Per game");
  assert.equal(th.getAttribute("colspan"), "8");
  applySize(plain, "small");
  assert.equal(th.getAttribute("colspan"), "4");
  // no conference ranks anywhere: no conference columns at all; no national ranks: none of those either
  const bare = twoTeamTable({ rows: [{ label: "Yards per play", us: { value: 6.1 }, them: { value: 5.2 } }], usAbbr: "SWT", themAbbr: "DT", tug: true });
  assert.equal(bare.querySelectorAll("tbody tr")[0].childNodes.length, 4, "label, value, bar, value");
  assert.equal(bare.querySelectorAll("tr.tt__head--b th").length, 2, "only the blank heads under the teams");
  assert.ok(typeof bare.measure === "function");
  // junk never throws and never prints raw words
  for (const junk of [null, undefined, "x", 3, [null, "a", { us: "x", them: 5 }]]) {
    const w = twoTeamTable({ rows: junk, groups: junk === 3 ? [null, { rows: "x", us: 7, missing: "no" }] : undefined, tug: true });
    assert.ok(!RAW.test(text(w)), text(w));
    applySize(w, "small");
    applySize(w, "none");
  }
};

scenarios.centered = async () => {
  const { twoTeamTable, applySize } = await import(moduleUrl("ui/two-team.js"));
  const groups = [{ title: "Offense", rows: rows().filter((r) => r.side === "offense"), us: "Spread option", them: "Pro-style" }];
  const wrap = twoTeamTable({ groups, usAbbr: "SWT", themAbbr: "DT", usTeam: "Swampwater Tech", themTeam: "Diner Tech", centered: true, labelHead: "Season" });
  document.body.append(wrap);
  assert.ok(!RAW.test(text(wrap)), text(wrap));
  assert.ok(wrap.querySelector("table").className.includes("tt--centered") && wrap.querySelector("table").className.includes("tt--tug"), "centered implies the bar");
  const headA = [...wrap.querySelectorAll("tr.tt__head--a th")];
  assert.deepEqual(headA.map((th) => form(th, "long")), ["Swampwater Tech", "Season", "Diner Tech"]);
  assert.deepEqual(headA.map((th) => th.getAttribute("colspan")), ["3", null, "3"]);
  assert.equal(headA[1].getAttribute("rowspan"), "2");
  assert.deepEqual([...wrap.querySelectorAll("tr.tt__head--b th")].map(text), ["FBS rank", "Big Pie rank", "", "", "Big Pie rank", "FBS rank"]);
  assert.deepEqual([...wrap.querySelectorAll("tr.tt__head--one th")].map((th) => form(th, "short")), ["FBS", "SWT", "Season", "DT", "FBS"]);
  const first = wrap.querySelectorAll("tbody tr:not(.tt__group)")[0];
  assert.deepEqual([...first.childNodes].map((td) => cls(td).split(" ")[0]), ["tt__rank", "tt__rank", "num", "tt__tug", "num", "tt__rank", "tt__rank"], "mirrored around the middle");
  const mid = first.childNodes[3];
  assert.ok(cls(mid).includes("tt__mid") && mid.querySelector(".tug") && mid.dataset.term === "Points per game");
  assert.equal(form(mid.querySelector(".tt__mid-words"), "short"), "PPG");
  assert.ok(cls(first.childNodes[2]).includes("lead") && cls(first.childNodes[4]).includes("trail"));
  // the group row: the schemes each side of the centered title
  const grp = wrap.querySelector("tr.tt__group");
  assert.deepEqual([...grp.children].map((c) => c.tagName + "." + cls(c).split(" ")[0]), ["TD.tt__scheme", "TH.tt__group-title", "TD.tt__scheme"]);
  assert.deepEqual([grp.children[0].getAttribute("colspan"), grp.children[2].getAttribute("colspan")], ["3", "3"]);
  applySize(wrap, "medium");
  assert.deepEqual([grp.children[0].getAttribute("colspan"), grp.children[2].getAttribute("colspan")], ["2", "2"]);
  applySize(wrap, "small");
  assert.equal(grp.querySelector("th").getAttribute("colspan"), "3", "small: value, the middle, value");
  assert.ok(grp.children[0].hidden === true && grp.children[2].hidden === true);
  applySize(wrap, "large");
  assert.equal(grp.querySelector("th").getAttribute("colspan"), "1");
};

scenarios.card = async () => {
  const { matchupCard, recordLine, fullName, lastFive } = await import(moduleUrl("ui/matchup-card.js"));
  assert.equal(recordLine({ record: { wins: 2, losses: 3 }, conferenceRecord: { wins: 0, losses: 3 } }), "2-3 (0-3)");
  assert.equal(recordLine({ record: { wins: 2, losses: 3, ties: 1 } }), "2-3-1");
  assert.equal(recordLine({ record: { wins: "2" } }), null);
  assert.equal(fullName({ school: "Diner Tech", mascot: "Waffles" }), "Diner Tech Waffles");
  assert.equal(fullName({ school: "Waffle State", mascot: "Waffle" }), "Waffle State", "a mascot already in the name is not repeated");
  assert.equal(fullName({}), null);
  assert.equal(lastFive([]), null);
  assert.equal(lastFive("junk"), null);
  const played = [1, 2, 3, 4, 5, 6].map((n) => ({ gameId: 100 + n, result: n % 2 ? "W" : "L", points: 20 + n, opponentPoints: 17, opponent: `Team ${n}`, homeAway: n % 3 ? "home" : "away" }));
  played.push({ result: "Q" }, null, { result: "T", points: null });
  const five = lastFive(played);
  const links = [...five.querySelectorAll("a.form-guide__game--link")];
  assert.equal(links.length + five.querySelectorAll("span.form-guide__game").length, 5, "the last five only");
  assert.equal(links[0].getAttribute("href"), "#box=103", "newest last: the five newest keep their order (the tie with no id is a plain square)");
  assert.ok(links[0].getAttribute("title").includes("Won 23-17 at Team 3") && links[0].getAttribute("title").includes("box score"));
  assert.ok(!RAW.test(text(five)));
  let asked = 0;
  const card = matchupCard({
    us: { abbreviation: "SWT", school: "Swampwater Tech", mascot: "Mudcats" },
    them: { school: "Diner Tech", mascot: "Waffles", abbreviation: "DT", apRank: 14, record: { wins: 2, losses: 3 }, conferenceRecord: { wins: 0, losses: 3 }, form: played },
    teamTags: [{ label: "SP+ #48", href: "#national=rating%3Asp?team=Diner%20Tech", rank: 48, of: 136, name: "SP+" }],
    tags: [{ label: "Big Pie" }],
    schemes: { offense: "Spread option", defense: "3-4", opponent: { offense: "Pro-style" } },
    onNotes: () => { asked += 1; },
    rows: rows(),
  });
  document.body.append(card);
  assert.ok(!RAW.test(text(card)), text(card));
  assert.equal(card.dataset.size, "large");
  assert.ok(!card.querySelector(".team-page-chip") && !text(card).includes("Team page"), "no Team page chip");
  const name = card.querySelector(".mcard__name");
  assert.ok(name.querySelector("button.team-link") && name.querySelector("button.team-link").dataset.team === "Diner Tech", "the name is the way to the team page");
  assert.equal(text(name.querySelector(".mcard__mascot")), "Waffles");
  assert.equal(text(name.querySelector(".mcard__rec")), "2-3 (0-3)");
  assert.ok(name.querySelector(".poll-badge"), "the AP badge stays before the name");
  assert.ok(!text(card).includes("in conference"), "the conference record lives in the brackets");
  const chips = card.querySelector(".mcard__chips");
  assert.ok(chips.querySelector("a.list-link") && text(chips).includes("SP+ #48"));
  assert.ok(chips.querySelector(".mcard__last5 a[href=\"#box=103\"]"), "the last five on the chip line, each a box score");
  assert.ok([...chips.querySelectorAll(".tag")].some((t) => text(t) === "Big Pie"), "the game's tag after the team's chips");
  assert.ok(!card.querySelector(".mcard__tags"));
  // the table: the mascots in the large heads, each scheme under its team, the way to the notes for the one missing
  const table = card.querySelector(".mcard__table");
  assert.ok(table && table.dataset.size === "large");
  assert.deepEqual([...table.querySelectorAll("tr.tt__head--a th.tt__team")].map((th) => form(th, "long")), ["Swampwater Tech Mudcats", "Diner Tech Waffles"]);
  const grp = table.querySelectorAll("tr.tt__group");
  assert.equal(grp.length, 2);
  assert.equal(text(grp[0].querySelector("td.tt__us")), "Spread option");
  assert.equal(text(grp[0].querySelector("td.tt__them")), "Pro-style");
  assert.equal(text(grp[1].querySelector("td.tt__us")), "3-4");
  const get = grp[1].querySelector("td.tt__them button.tt__get");
  assert.ok(get, "the opponent's defense is not in the notes: the way there");
  get.click();
  assert.equal(asked, 1);
  // no notes at all, no handler: a plain word, never a blank or a raw value
  const none = matchupCard({ us: { school: "Swampwater Tech" }, them: { school: "Diner Tech" }, rows: rows() });
  assert.ok(!RAW.test(text(none)));
  assert.ok([...none.querySelectorAll("td.tt__scheme")].every((td) => text(td) === "Get this week's notes" && td.querySelector('a[href="#prompts"]')), "never a dead end: the way to the prompts (2026-10-13)");
  assert.ok(!none.querySelector(".mcard__chips"), "nothing to say: no chip line");
  // junk never throws
  for (const junk of [null, "x", { form: "x", record: "y", mascot: 3, school: null }]) assert.ok(!RAW.test(text(matchupCard({ them: junk, rows: junk, schemes: junk, teamTags: junk, tags: junk }))));
};

scenarios.stat = async () => {
  const { statTable, applyStatSize } = await import(moduleUrl("ui/stat-table.js"));
  const columns = [
    { key: "label", label: "Statistic", kind: "text", sortable: false },
    { key: "a", label: "Points per game", labelMid: "Pts/game", labelShort: "PPG", format: "1f" },
    { key: "b", label: "Conference rank", labelShort: "Conf", kind: "rank", of: 16, size: "large" },
    { key: "c", label: "FBS rank", kind: "rank", of: 136, size: "medium" },
  ];
  const list = [{ label: "Points per game", a: 31.5, b: 3, c: 20 }, { label: "Yards per play", a: 6.2, b: 1, c: 4 }];
  const wrap = statTable({ compact: true, sizes: true, columns, rows: list, sortable: false });
  document.body.append(wrap);
  assert.ok(!RAW.test(text(wrap)), text(wrap));
  assert.equal(wrap.dataset.size, "large");
  const heads = [...wrap.querySelectorAll("thead th")];
  assert.equal(heads[1].querySelector(".sz-t--short").textContent, "PPG");
  assert.equal(heads[1].querySelector(".sz-t--mid").textContent, "Pts/game");
  assert.equal(heads[1].dataset.term, "Points per game");
  assert.ok(cls(heads[2]).includes("st__min-large") && cls(heads[3]).includes("st__min-medium") && !cls(heads[1]).includes("st__min"));
  assert.equal(heads[0].querySelector(".sz-t"), null, "one word in every form: plain text");
  const cells = wrap.querySelectorAll("tbody tr")[0].querySelectorAll("td");
  assert.equal(cells[0].dataset.term, "Points per game");
  assert.equal(cells[0].querySelector(".sz-t--short").textContent, "PPG");
  assert.ok(cls(cells[2]).includes("st__min-large") && cls(cells[3]).includes("st__min-medium"));
  assert.ok(cells[2].querySelector(".rank-chip") && text(cells[2]).includes("3"));
  applyStatSize(wrap, "medium");
  assert.equal(wrap.dataset.size, "medium");
  applyStatSize(wrap, "none");
  assert.ok(wrap.querySelector("table").hidden === true && wrap.querySelector(".size-note") && cls(wrap).includes("stat-table-wrap--dropped"));
  applyStatSize(wrap, "small");
  assert.ok(wrap.querySelector("table").hidden === false && !wrap.querySelector(".size-note"));
  assert.ok(typeof wrap.measure === "function");
  // a table without sizes is untouched: no size attribute, no forms
  const plain = statTable({ columns, rows: list, sortable: false });
  assert.ok(!plain.dataset.size && !plain.querySelector(".sz-t") && !plain.querySelector("[data-term]"));
  // a team column with a short form: the abbreviation at small, inside the team link; a prose column wraps
  const series = statTable({ sizes: true, sortable: false, columns: [{ key: "year", label: "Year", kind: "text" }, { key: "away", label: "Away", kind: "text", team: true, shortKey: "awayAbbr" }, { key: "note", label: "Note", kind: "text", shortKey: "noteShort" }, { key: "depth", label: "Then, in order", labelMid: "Then", kind: "text", size: "large", wrap: true }], rows: [{ year: "2025", away: "Swampwater Tech", awayAbbr: "SWT", note: "a long note", noteShort: "note", depth: "A, B, C" }, { year: "2024", away: "Diner Tech", awayAbbr: "", note: null, depth: null }] });
  const r0 = series.querySelectorAll("tbody tr")[0].querySelectorAll("td");
  assert.ok(r0[1].querySelector("button.team-link .sz-t--short") && r0[1].querySelector("button.team-link .sz-t--short").textContent === "SWT" && r0[1].querySelector(".sz-t--long").textContent === "Swampwater Tech");
  assert.equal(r0[2].querySelector(".sz-t--short").textContent, "note");
  assert.ok(cls(r0[3]).includes("st__wrap") && cls(r0[3]).includes("st__min-large"));
  const r1 = series.querySelectorAll("tbody tr")[1].querySelectorAll("td");
  assert.ok(r1[1].querySelector("button.team-link") && !r1[1].querySelector(".sz-t"), "no short form: the name alone");
  assert.equal(text(r1[2]), "–");
  assert.ok(!RAW.test(text(series)), text(series));
};

scenarios.tape = async () => {
  const { tapeTable, tapePairs } = await import(moduleUrl("ui/tape.js"));
  const edges = [
    { label: "Passing: SWT offense vs DT defense", side: "offense", usRank: 5, themRank: 100, of: 136, edge: 95, usValue: 298, themValue: 250, format: "0f", usKey: "pass_ypg", themKey: "pass_ypg_d" },
    { label: "Rushing: SWT offense vs DT defense", side: "offense", usRank: 40, themRank: 30, of: 136, edge: -10, usValue: 150, themValue: 120, format: "0f" },
    { label: "Third down: SWT offense vs DT defense", side: "offense", usRank: 20, themRank: 25, of: 136, edge: 5, usValue: 0.45, themValue: 0.4, format: "pct" },
    { label: "Scoring: SWT offense vs DT defense", side: "offense", usRank: 10, themRank: 12, of: 136, edge: 2, usValue: 35, themValue: 20, format: "1f" },
    { label: "Passing: DT offense vs SWT defense", side: "defense", usRank: 50, themRank: 20, of: 136, edge: -30, usValue: 240, themValue: 280, format: "0f" },
    "junk",
    null,
  ];
  const pair = tapeTable(edges, { usAbbr: "SWT", themAbbr: "DT", usTeam: "Swampwater Tech", themTeam: "Diner Tech" });
  document.body.append(pair);
  assert.ok(!RAW.test(text(pair)), text(pair));
  assert.ok(pair.className.includes("tt-pair"));
  const tables = [...pair.querySelectorAll(".tt-wrap")];
  assert.equal(tables.length, 2, "the offense matchup, then the defense matchup");
  const headsOf = (w) => [...w.querySelectorAll("tr.tt__head--a th.tt__team")].map((th) => form(th, "long"));
  assert.deepEqual(headsOf(tables[0]), ["Swampwater Tech offense", "Diner Tech defense"]);
  assert.deepEqual(headsOf(tables[1]), ["Swampwater Tech defense", "Diner Tech offense"], "our unit first in both");
  const one = [...tables[0].querySelectorAll("tr.tt__head--one th")];
  assert.deepEqual(one.map((th) => form(th, "mid")), ["Statistic", "FBS", "SWT offense", "Edge", "DT defense", "FBS"]);
  assert.deepEqual(one.map((th) => form(th, "short")), ["Stat", "FBS", "SWT off", "Edge", "DT def", "FBS"]);
  const rows0 = [...tables[0].querySelectorAll("tbody tr")];
  assert.equal(rows0.length, 4);
  assert.deepEqual(rows0.map((r) => form(r.querySelector("td.tt__label"), "long")), ["Passing", "Rushing", "Third down", "Scoring"]);
  assert.ok(!rows0[0].querySelector("td.tt__label small"), "no matchup words under the label: the heads say it");
  assert.deepEqual(rows0.map((r) => (r.querySelector(".tt__tag") ? text(r.querySelector(".tt__tag")) : "")), ["top 3", "top 3", "top 3", ""], "the three biggest edges tagged under their bars");
  assert.ok(rows0[0].querySelector(".tug__bar--us") && rows0[1].querySelector(".tug__bar--them"));
  assert.equal(rows0[0].querySelector("td.tt__rank--natl a.rank-chip--link").getAttribute("href"), "#national=profile%3Apass_ypg?team=Swampwater%20Tech");
  assert.equal(tables[1].querySelectorAll("tbody tr").length, 1);
  assert.ok(tables[1].querySelector("tbody tr .tug__bar--them"), "their offense has the edge on the defense table");
  assert.equal(tapePairs(edges, { usAbbr: "SWT", themAbbr: "DT" }).length, 4);
  for (const junk of [null, "x", [], [null, 3]]) assert.ok(!RAW.test(text(tapeTable(junk, { usAbbr: "SWT" }))));
};

scenarios.matchups = async () => {
  const { pairSlots, lineupBlock } = await import(moduleUrl("ui/lineups_combined.js"));
  const { playerNames } = await import(moduleUrl("ui/dom.js")); // item 6: one helper for every table of players
  assert.equal(playerNames("Gabriel Brownlow-Dindy").last, "Brownlow-Dindy");
  assert.equal(playerNames("Eric Singleton Jr.").last, "Singleton");
  assert.equal(playerNames("Cher").last, "Cher");
  assert.equal(playerNames(null).last, "–");
  const slot = (name, unit, players) => ({ slot: name, unit, players: players.map((p, i) => (typeof p === "string" ? { name: p, number: 10 + i, classYear: i ? "FR" : "SR", playerId: `${name}-${i}` } : p)) });
  const offense = [slot("WR-X", "offense", ["Dallas Wilson", "Micah Jr."]), slot("LT", "offense", ["Bryce Lovett", "Eagan Stock"]), slot("C", "offense", ["Harrison Moore"]), slot("WR-SL", "offense", ["Vernell Brown III"]), slot("RB", "offense", ["Jadan Baugh"]), slot("QB", "offense", ["DJ Lagway"]), slot("TE", "offense", ["Hayden Hansen"]), slot("RT", "offense", ["Austin Barber"]), slot("LG", "offense", ["Knijeah Harris"])];
  const defense = [slot("LDE", "defense", ["Caleb Herring"]), slot("LDT", "defense", ["Kelby Collins"]), slot("RDT", "defense", ["Tomiwa Durojaiye"]), slot("RDE", "defense", ["Anthony Addison"]), slot("WLB", "defense", ["Justin Okoronkwo"]), slot("MLB", "defense", ["Fred Johnson"]), slot("LCB", "defense", ["Brandon Cisse"]), slot("SS", "defense", ["Jalon Kilgore"]), slot("FS", "defense", ["Nick Emmanwori"]), slot("RCB", "defense", ["Judge Collier"]), slot("NB", "defense", ["Shadarius Toodle"])];
  const pairs = pairSlots(offense, defense);
  const said = pairs.map((p) => `${p.off ? p.off.slot : "–"}:${p.def ? p.def.slot : "–"}`);
  assert.deepEqual(said, ["WR-X:RCB", "LT:RDE", "C:LDT", "WR-SL:NB", "RB:MLB", "QB:FS", "TE:SS", "RT:LDE", "LG:RDT", "–:WLB", "–:LCB"], said.join(" ")); // the center takes the first free tackle, the guard the one on his side
  // a 3-4 chart: the edge is the JACK, the nose the NT; a slot with no match keeps a dash on that side
  const three4 = [slot("DE", "defense", ["A"]), slot("NT", "defense", ["B"]), slot("DT", "defense", ["C"]), slot("JACK", "defense", ["D"]), slot("CB", "defense", ["E"])];
  assert.deepEqual(pairSlots([slot("LT", "offense", ["t"]), slot("C", "offense", ["c"]), slot("RT", "offense", ["r"]), slot("WR-Z", "offense", ["z"]), slot("WR-X", "offense", ["x"])], three4).map((p) => `${p.off ? p.off.slot : "–"}:${p.def ? p.def.slot : "–"}`), ["LT:JACK", "C:NT", "RT:DE", "WR-Z:CB", "WR-X:–", "–:DT"]);
  assert.deepEqual(pairSlots(null, "x"), []);
  // the block: one table per pairing, our side first, the starter's cell with his class (the men behind him are not drawn since the mock of 2026-10-20), the surname at small
  let opened = null;
  const block = lineupBlock({
    lineups: { us: { team: "Swampwater Tech", slots: [...offense, ...defense, slot("PK", "special teams", ["Kicker One"])] }, them: { team: "Diner Tech", slots: [...defense, slot("QB", "offense", ["Their QB"]), slot("PK", "special teams", ["Kicker Two"]), slot("P", "special teams", ["Punter"])] } },
    us: { school: "Swampwater Tech", abbreviation: "SWT" },
    them: { school: "Diner Tech", abbreviation: "DT" },
    availability: [{ name: "Bryce Lovett", status: "Questionable", note: "ankle" }],
    onPlayer: (side) => { opened = side; },
  });
  document.body.append(block);
  assert.ok(!RAW.test(text(block)), text(block));
  const heads = [...block.querySelectorAll(".lu-head")].map(text);
  assert.deepEqual(heads, ["Swampwater Tech offense vs Diner Tech defense", "Swampwater Tech defense vs Diner Tech offense", "Swampwater Tech special teams vs Diner Tech special teams"]);
  const tables = [...block.querySelectorAll(".lineups__matchup .stat-table-wrap")];
  assert.equal(tables.length, 3);
  assert.ok(tables.every((w) => w.dataset.size === "large"));
  const first = tables[0].querySelectorAll("tbody tr")[1];
  const cells = first.querySelectorAll("td");
  assert.equal(text(cells[0]), "LT");
  assert.ok(cls(cells[1]).includes("st__min-large") && text(cells[1]) === "10", "the number at large only");
  assert.ok(cells[2].querySelector(".sz-t--long .lu-who button.lu-name") && pnText(cells[2].querySelector(".lu-name")) === "Bryce Lovett");
  assert.ok(text(cells[2]).includes("SR") && text(cells[2]).includes("Questionable") && !text(cells[2]).includes("then "), "his class and status; the man behind him is not drawn (the mock, owner 2026-10-20)");
  assert.ok(cells[2].querySelector(".sz-t--short button.lu-name"), "item 6: the starter keeps his tap at small");
  assert.deepEqual(["full", "initial", "last"].map((f) => pnText(cells[2].querySelector(".sz-t--short"), f)), ["Bryce Lovett", "B. Lovett", "Lovett"], "his name steps down with the table");
  assert.ok(cls(cells[3]).includes("st__min-large") && cls(cells[3]).includes("st__wrap"));
  assert.equal(text(cells[4]), "⟷");
  assert.equal(text(cells[5]), "RDE");
  assert.ok(text(cells[7]).includes("Anthony Addison") && pnText(cells[7].querySelector(".sz-t--short"), "last") === "Addison");
  cells[2].querySelector(".lu-name").click();
  assert.ok(opened && opened.playerId === "LT-0" && opened.name === "Bryce Lovett" && opened.slot === "LT" && opened.isUs === true, "a tap hands the starter to the player card");
  const unmatched = [...tables[0].querySelectorAll("tbody tr")].find((r) => text(r.querySelectorAll("td")[0]) === "–");
  assert.ok(unmatched && [...unmatched.querySelectorAll("td")[2].querySelectorAll(".sz-t")].every((t) => text(t) === "–") && text(unmatched.querySelectorAll("td")[5]) === "WLB", "a defender nobody faces keeps his row with a dash beside him (at every size)");
  // the second table: our defense on the left, their offense on the right
  const second = tables[1].querySelectorAll("tbody tr");
  const qbRow = [...second].find((r) => text(r.querySelectorAll("td")[5]) === "QB");
  assert.ok(qbRow && text(qbRow.querySelectorAll("td")[0]) === "FS", "their quarterback faces our free safety, our side first");
  // the specialists slot for slot
  const third = [...tables[2].querySelectorAll("tbody tr")].map((r) => [text(r.querySelectorAll("td")[0]), text(r.querySelectorAll("td")[5])]);
  assert.deepEqual(third, [["PK", "PK"], ["–", "P"]]);
  // junk never throws
  for (const junk of [null, {}, { us: "x", them: 3 }, { us: { slots: [null, { slot: 7, players: "x" }] } }]) assert.ok(!RAW.test(text(lineupBlock({ lineups: junk, us: null, them: "x" }))));
};

// --- wave 2 (owner 2026-10-10): the shared pieces the Pre-Game Program and In Game build on -------------------------

scenarios.lean = async () => {
  const { twoTeamTable, tugShare, valueShare, PPA_SCALE } = await import(moduleUrl("ui/two-team.js"));
  // a bar with no national ranks leans by the values' own share: how far ahead, never a fixed amount
  assert.equal(valueShare({ us: { value: 35 }, them: { value: 14 } }).toFixed(3), "0.429");
  assert.equal(valueShare({ us: { value: 14 }, them: { value: 0 } }), 1, "a shutout leans all the way");
  assert.equal(valueShare({ us: { value: 0.2 }, them: { value: -0.1 } }), 1, "one side gaining, the other losing: all the way");
  assert.equal(valueShare({ us: { value: -0.1 }, them: { value: -0.3 } }).toFixed(3), "0.500");
  for (const none of [{ us: { value: 0 }, them: { value: 0 } }, { us: { value: 3 }, them: {} }, { us: { value: "3" }, them: { value: 1 } }, null, "x"]) assert.equal(valueShare(none), null);
  // a measure either side of zero (PPA) names its scale: +0.05 against -0.02 is a small lean, not all the way
  assert.equal(PPA_SCALE, 0.5);
  assert.equal(valueShare({ scale: PPA_SCALE, us: { value: 0.05 }, them: { value: -0.02 } }).toFixed(2), "0.14");
  assert.equal(valueShare({ scale: PPA_SCALE, us: { value: 0.45 }, them: { value: -0.15 } }), 1, "a blowout's PPA leans all the way");
  assert.equal(valueShare({ scale: 0, us: { value: 35 }, them: { value: 14 } }).toFixed(3), "0.429", "no usable scale: the share");
  assert.equal(tugShare({ scale: PPA_SCALE, us: { value: 0.11 }, them: { value: 0.1 } }), 0.12);
  assert.equal(tugShare({ us: { value: 35 }, them: { value: 14 } }).toFixed(3), "0.429");
  assert.equal(tugShare({ us: { value: 450 }, them: { value: 440 } }), 0.12, "a near tie still shows its leader");
  assert.equal(tugShare({ us: { value: 35, rank: 10, of: 136 }, them: { value: 14, rank: 44, of: 136 } }), 0.5, "national ranks still decide when the row has them");
  assert.equal(tugShare({ edge: 136, us: { of: 136 } }), 1);
  assert.equal(tugShare({ leads: "us", us: { text: "A" }, them: { text: "B" } }), 0.12, "nothing to measure: the least lean, never a made-up margin");
  // wave 2 review: the Pre-Game Program's season PPA pairs (leads given, values either side of zero) lean on the PPA scale
  const pair = { leads: "us", scale: PPA_SCALE, format: "+2f", us: { value: 0.05 }, them: { value: -0.02 } };
  assert.equal(tugShare(pair).toFixed(2), "0.14", "+0.05 against -0.02 is a small lean, not the whole bar");
  const pairTable = twoTeamTable({ rows: [pair], usAbbr: "SWT", themAbbr: "DT", tug: true });
  assert.equal(pairTable.querySelector(".tug__bar--us").style.width, "7%");
  // the bar's width and its words follow the values; an optional key puts the flash keys on the value cells
  const wrap = twoTeamTable({
    rows: [
      { label: "Points", key: "ts:Points", higherIsBetter: true, us: { value: 21 }, them: { value: 28 } },
      { label: "Turnovers", higherIsBetter: false, us: { value: 0 }, them: { value: 2 } },
      { label: "Pass yards per game", higherIsBetter: true, us: { value: 275, rank: 29, of: 136 }, them: { value: 235, rank: 65, of: 136 } },
      { label: "Plays", key: "  ", us: { value: 60 }, them: { value: 70 } },
    ],
    usAbbr: "SWT",
    themAbbr: "DT",
    tug: true,
  });
  document.body.append(wrap);
  assert.ok(!RAW.test(text(wrap)), text(wrap));
  const [points, turnovers, ranked, plays] = wrap.querySelectorAll("tbody tr");
  assert.deepEqual([...points.querySelectorAll("td.num")].map((td) => td.dataset.k), ["ts:Points:us", "ts:Points:them"]);
  assert.ok([...turnovers.querySelectorAll("td.num"), ...plays.querySelectorAll("td.num")].every((td) => !td.dataset.k), "no key, no flash key (a blank key is none)");
  assert.equal(points.querySelector(".tug__bar--them").style.width, "7%", "28 to 21: 7 of 49, a seventh of the half");
  assert.equal(points.querySelector(".tug").getAttribute("aria-label"), "DT has the edge, 28 to 21");
  assert.equal(turnovers.querySelector(".tug__bar--us").style.width, "50%", "lower is better: none to two leans all the way");
  assert.equal(turnovers.querySelector(".tug").getAttribute("aria-label"), "SWT has the edge, 0 to 2");
  assert.equal(ranked.querySelector(".tug__bar--us").style.width, "26%", "36 ranks over half of 136");
  assert.equal(ranked.querySelector(".tug").getAttribute("aria-label"), "SWT has the edge, 36 national ranks apart");
  assert.ok(!plays.querySelector(".tug__bar") && plays.querySelector(".tug").getAttribute("aria-label") === "No edge to show", "a neutral row: no lean");
};

scenarios.teamstats = async () => {
  const { teamStatsTable, teamStatRows, feedEfficiencyTable, feedStatRows, FEED_ROWS, quarterLine } = await import(moduleUrl("ui/team-stats.js"));
  const { applySize } = await import(moduleUrl("ui/two-team.js"));
  const usBox = { points: 35, totalYards: 450, yardsPerPlay: 6.4, plays: 70, drives: 12, successRate: 0.481, turnovers: 0, penalties: { count: 6, yards: 45 }, thirdDown: { made: 5, of: 12 }, possessionTime: "31:10", raw: { passesIntercepted: "1", completionAttempts: "20/30" } };
  const themBox = { points: 14, totalYards: 300, yardsPerPlay: 5.0, plays: 60, drives: 12, successRate: 0.392, turnovers: 2, penalties: { count: 4 }, thirdDown: { made: 3, of: 11 }, possessionTime: "28:50", raw: { passesIntercepted: 2 } };
  const wrap = teamStatsTable({ us: { abbr: "SWT", box: usBox, school: "Swampwater Tech", name: "Swampwater Tech Mudcats" }, them: { abbr: "DT", box: themBox, school: "Diner Tech" } });
  document.body.append(wrap);
  assert.ok(!RAW.test(text(wrap)), text(wrap));
  assert.ok(cls(wrap).includes("tt-wrap") && wrap.dataset.size === "large", "the shared kit (rule 9), drawn large until it measures itself");
  assert.ok(wrap.querySelector("table").className.includes("tt--tug"), "with the tug bar");
  assert.equal(wrap.querySelector("caption").textContent, "Team stats");
  // the heads: the school and mascot at large, the school at medium, the abbreviation at small
  assert.deepEqual([...wrap.querySelectorAll("tr.tt__head--a th")].map((th) => form(th, "long")), ["Statistic", "Swampwater Tech Mudcats", "Edge", "Diner Tech"]);
  const one = [...wrap.querySelectorAll("tr.tt__head--one th")];
  assert.deepEqual(one.map((th) => form(th, "mid")), ["Statistic", "Swampwater Tech", "Edge", "Diner Tech"]);
  assert.deepEqual(one.map((th) => form(th, "short")), ["Stat", "SWT", "Edge", "DT"]);
  // every row, its parent or sub class, its flash keys, the leader in chalk and the bar leaning by the real margin
  const body = [...wrap.querySelectorAll("tbody tr")];
  assert.equal(body.length, teamStatRows({}, {}).length);
  const row = (label) => body.find((tr) => form(tr.querySelector("td.tt__label"), "long") === label);
  const cells = (label) => [...row(label).querySelectorAll("td")];
  assert.ok(cls(row("Points")).includes("is-parent") && cls(row("Yards per play")).includes("is-sub"));
  assert.deepEqual(cells("Points").map((td) => cls(td).split(" ")[0]), ["txt", "num", "tt__tug", "num"], "label, value, bar, value: no rank columns without ranks");
  assert.deepEqual([cells("Points")[1].dataset.k, cells("Points")[3].dataset.k], ["ts:Points:us", "ts:Points:them"], "L-03: the per-play flash keys as before");
  assert.ok(cls(cells("Points")[1]).includes("lead") && cls(cells("Points")[3]).includes("trail"));
  assert.equal(cells("Points")[2].querySelector(".tug__bar--us").style.width, "21%", "35 to 14");
  assert.equal(cells("Turnovers")[2].querySelector(".tug__bar--us").style.width, "50%");
  assert.ok(cls(cells("Interceptions thrown")[1]).includes("lead"), "1 thrown to 2: fewer is better");
  assert.ok(!cells("Plays")[2].querySelector(".tug__bar") && !cls(cells("Plays")[1]).includes("lead"), "plays: nobody leads");
  assert.deepEqual([text(cells("Penalties")[1]), text(cells("Penalties")[3])], ["6-45", "4"], "the count alone before the yards post");
  assert.deepEqual([text(cells("Third down")[1]), text(cells("Success rate")[1]), text(cells("Comp-Att")[1]), text(cells("Comp-Att")[3])], ["5-12", "48.1%", "20/30", "–"]);
  // the stat names in three forms; the hint keeps the long one
  assert.equal(form(cells("Interceptions thrown")[0], "short"), "Ints");
  assert.equal(form(cells("Time of possession")[0], "short"), "Possession");
  assert.equal(form(cells("20+ yard plays")[0], "mid"), "20+ yd plays");
  assert.equal(cells("Yards per attempt")[0].dataset.term, "Yards per attempt");
  applySize(wrap, "small");
  assert.equal(wrap.dataset.size, "small");
  // a subset under its own head (the Situation panel), and the final box's rows: no school given, the abbreviation everywhere
  const sit = teamStatsTable({ us: { abbr: "SWT", box: usBox }, them: { abbr: "DT", box: themBox }, rows: teamStatRows(usBox, themBox).filter((r) => ["Third down", "Turnovers"].includes(r.label)), labelHead: "Situation" });
  assert.equal(sit.querySelectorAll("tbody tr").length, 2);
  assert.deepEqual([...sit.querySelectorAll("tr.tt__head--a th")].map((th) => form(th, "long")), ["Situation", "SWT", "Edge", "DT"]);
  // junk never throws and never prints a raw word
  for (const junk of [null, "x", 3, [null, "a", { label: null, us: 5, usValue: "7", higherIsBetter: "yes" }]]) {
    const w = teamStatsTable({ us: junk, them: junk, rows: Array.isArray(junk) ? junk : undefined });
    assert.ok(!RAW.test(text(w)), text(w));
  }
  assert.ok(!RAW.test(text(teamStatsTable())));

  // the live feed's efficiency rows: one builder for In Game and the Archive, raw values so the leader shows
  const feed = { "Swampwater Tech": { standardDownSuccessRate: 0.52, epaPerPlay: 0.21, averageStartYardLine: 30, deserveToWin: 0.8 }, "Diner Tech": { standardDownSuccessRate: 0.41, epaPerPlay: -0.05, averageStartYardLine: 25, deserveToWin: 0.2, explosiveness: "x" } };
  const ft = feedEfficiencyTable({ feed, us: { team: "Swampwater Tech", abbr: "SWT", school: "Swampwater Tech" }, them: { team: "Diner Tech", abbr: "DT" } });
  document.body.append(ft);
  assert.ok(!RAW.test(text(ft)), text(ft));
  assert.ok(cls(ft).includes("tt-wrap") && ft.querySelector("table").className.includes("tt--tug"));
  const feedRows = [...ft.querySelectorAll("tbody tr")];
  assert.deepEqual(feedRows.map((tr) => form(tr.querySelector("td.tt__label"), "long")), ["Standard downs", "PPA per play", "Average start, yards to goal", "Deserve to win"], "rows neither side has are dropped");
  assert.deepEqual(feedRows.map((tr) => form(tr.querySelector("td.tt__label"), "short")), ["Std downs", "PPA", "Avg start", "Deserve win"]);
  assert.deepEqual(feedRows.map((tr) => text(tr.querySelectorAll("td.num")[0])), ["52.0%", "+0.21", "30", "80.0%"], "a rate shows one decimal, PPA its sign");
  assert.ok([0, 1, 3].every((i) => cls(feedRows[i].querySelectorAll("td.num")[0]).includes("lead")), "higher is better on the feed's rates and values");
  // wave 2 review: the feed's start is yards to the goal (CFBD's drives' mean startYardsToGoal), so the side with fewer leads
  assert.ok(cls(feedRows[2].querySelectorAll("td.num")[1]).includes("lead") && !cls(feedRows[2].querySelectorAll("td.num")[0]).includes("lead"), "25 yards to go beats 30");
  assert.ok(feedRows[2].querySelector(".tug__bar--them") && !feedRows[2].querySelector(".tug__bar--us"), "the start's bar leans to the side with fewer yards to go");
  assert.equal(feedRows[1].querySelector(".tug__bar--us").style.width, "26%", "PPA leans by its gap on the PPA scale: +0.21 to -0.05 is 0.26 of 0.5");
  assert.ok(feedStatRows({ epaPerPlay: 0.1 }, {}).every((r) => r.scale === 0.5) && feedStatRows({ explosiveness: 1.2 }, {}).every((r) => r.scale === undefined), "only the signed rows carry the scale");
  assert.equal(feedRows[2].querySelector(".tug__bar--them").style.width, "6%", "30 to 25 is a small lean, never a fixed one");
  assert.ok(!ft.querySelector("[data-k]"), "the feed rows keep their old behavior: no flash keys");
  assert.equal(ft.querySelector("caption").textContent, "Efficiency, from the live feed");
  assert.equal(feedEfficiencyTable({ feed: { A: {}, B: {} }, us: { team: "A" }, them: { team: "B" } }), null, "nothing in the feed: no table");
  for (const junk of [undefined, null, 3, "x", { feed: [1] }, { feed, us: { team: 5 }, them: null }]) assert.equal(feedEfficiencyTable(junk), null);
  assert.equal(feedStatRows(null, { epaPerPlay: 0.1 }).length, 1);
  assert.equal(FEED_ROWS.length, 11);

  // the quarter line keeps its scoreboard and its flash keys
  const q = quarterLine({ us: { abbr: "SWT", scores: [7, 14, 0, 14] }, them: { abbr: "DT", scores: [0, 7, 7, 0, 3] } });
  assert.deepEqual([...q.querySelectorAll(".qline__head")].map(text), ["", "Q1", "Q2", "Q3", "Q4", "OT", "T"]);
  assert.equal(text(q.querySelector('[data-k="q:us:t"]')), "35");
  assert.equal(text(q.querySelector('[data-k="q:them:4"]')), "3");
  assert.equal(text(q.querySelector('[data-k="q:us:4"]')), "–");
};

scenarios.box = async () => {
  const { BOX_COLUMNS, boxRows, boxTables } = await import(moduleUrl("ui/box-columns.js"));
  const { applyStatSize } = await import(moduleUrl("ui/stat-table.js"));
  // the sizes are declared once: every category's player column is a person column (item 6), no dead column flags
  for (const [name, columns] of Object.entries(BOX_COLUMNS)) {
    assert.equal(columns[0].person, true, name);
    assert.ok(columns.every((c) => !("sortable" in c) && !c.stick), `${name}: every box table sorts, nothing sticks`);
  }
  let tapped = null;
  const heard = [];
  const cats = {
    passing: [{ name: "Avery Passer Jr.", playerId: "1", stats: { "C/ATT": "20/30", YDS: 250, TD: 2, INT: 0, QBR: 70.1 } }, { name: "Backup Arm", playerId: "9", stats: { "C/ATT": "2/3", YDS: 300, TD: 0, INT: 1, QBR: null } }, null, "junk"],
    rushing: [{ name: "Ron Runner", playerId: "2", stats: { CAR: 12, YDS: 80, AVG: 6.67, TD: 1 } }, { name: null, playerId: null, stats: null }],
    kicking: [],
    defensive: "x",
  };
  const host = boxTables({ categories: cats, onTap: (row) => { tapped = row; }, sort: (name) => (name === "rushing" ? { key: "CAR", dir: "ascending" } : name === "passing" ? { key: "nope", dir: "ascending" } : null), onSort: (name, order) => heard.push([name, order]), fromPlays: true });
  document.body.append(host);
  assert.ok(!RAW.test(text(host)), text(host));
  assert.ok(text(host.querySelector(".note")).includes("play-by-play"), "the play-by-play line while CFBD's box is not posted");
  const wraps = [...host.querySelectorAll(".stat-table-wrap")];
  assert.equal(wraps.length, 2, "one table per category with rows");
  assert.ok(wraps.every((w) => w.dataset.size === "large" && typeof w.measure === "function"), "sized by its own box");
  const heads = [...wraps[0].querySelectorAll("thead th")];
  assert.deepEqual(heads.map((th) => form2(th, "long")), ["Passing", "Comp-Att", "Yards", "TD", "Int", "QBR"]);
  assert.deepEqual(heads.map((th) => form2(th, "mid")), ["Passing", "Comp-Att", "Yds", "TD", "Int", "QBR"]);
  assert.ok(cls(heads[5]).includes("st__min-medium") && !heads.slice(0, 5).some((th) => cls(th).includes("st__min")), "only QBR leaves at small");
  assert.equal(heads[2].dataset.term, "Yards (box score)", "a player's yards open their own glossary entry, not the team's total yards");
  assert.equal(heads[2].getAttribute("aria-sort"), "descending", "an order naming no column falls back to yards, high to low");
  const first = wraps[0].querySelectorAll("tbody tr")[0];
  assert.equal(pnText(first.querySelector("td")), "Backup Arm");
  const passer = wraps[0].querySelectorAll("tbody tr")[1].querySelector("td");
  assert.deepEqual(["full", "initial", "last", "reduced"].map((f) => pnText(passer, f)), ["Avery Passer Jr.", "A. Passer", "Passer", "Passer"], "item 6: the name's forms, one shown per step");
  assert.ok(cls(passer).includes("st__person") && passer.querySelector(".pn").getAttribute("title") === "Avery Passer Jr." && text(passer.querySelector(".pn .sr-only")) === "Avery Passer Jr.", "the full name in its title and for a screen reader");
  assert.equal(wraps[0].dataset.pn, "full", "full names at large");
  assert.equal(text(wraps[0].querySelectorAll("tbody tr")[0].querySelectorAll("td")[5]), "–", "a missing QBR is a dash");
  const rushHeads = [...wraps[1].querySelectorAll("thead th")];
  assert.deepEqual(rushHeads.map((th) => form2(th, "long")), ["Rushing", "Carries", "Yards", "Y/C", "TD"]);
  assert.deepEqual(rushHeads.map((th) => form2(th, "short")), ["Rushing", "Car", "Yds", "Y/C", "TD"]);
  assert.equal(rushHeads[1].getAttribute("aria-sort"), "ascending", "the reader's own order for the category");
  // a row tap opens the player; a header tap tells the page which category's order changed
  wraps[0].querySelectorAll("tbody tr")[1].click();
  assert.ok(tapped && tapped.playerId === "1" && tapped.name === "Avery Passer Jr." && tapped.YDS === 250);
  rushHeads[2].querySelector("button").click();
  assert.deepEqual(heard, [["rushing", { key: "YDS", dir: "descending" }]]);
  applyStatSize(wraps[0], "small");
  assert.deepEqual([wraps[0].dataset.size, wraps[0].dataset.pn], ["small", "initial"], "a plain size on a table of players: K. Crawford below large");
  applyStatSize(wraps[0], "small/last");
  assert.deepEqual([wraps[0].dataset.size, wraps[0].dataset.pn], ["small", "last"]);
  // whole heads for the other categories, today's box words below large
  const words = (name) => BOX_COLUMNS[name].map((c) => [c.label, c.labelMid || c.label, c.labelShort || c.labelMid || c.label]);
  assert.deepEqual(words("defensive").slice(1), [["Tackles", "Tkl", "Tkl"], ["Sacks", "Sacks", "Sacks"], ["TFL", "TFL", "TFL"], ["Passes defended", "PD", "PD"]]);
  assert.deepEqual(words("punting").slice(1), [["Punts", "No", "No"], ["Average", "Avg", "Avg"], ["Long", "Long", "Long"]]);
  assert.deepEqual(words("puntReturns")[0], ["Punt returns", "Punt returns", "Punt ret"]);
  assert.deepEqual(words("interceptions")[0], ["Interceptions", "Interceptions", "Ints"]);
  // the rows: a stat never overwrites the name; junk is skipped
  assert.deepEqual(boxRows([{ name: "Xavier Young", playerId: "4", stats: { name: "evil", YDS: 3 } }, null, 7]), [{ name: "Xavier Young", playerId: "4", YDS: 3 }]);
  // nothing to show: the note, never a blank or a raw word; a throwing order hook keeps the default
  for (const junk of [undefined, null, "x", { categories: null }, { categories: { passing: "x" } }, { categories: [] }]) {
    const out = boxTables(junk);
    assert.ok(text(out).includes("No player lines yet."), text(out));
  }
  const odd = boxTables({ categories: cats, sort: () => { throw new Error("boom"); }, emptyText: "x" });
  assert.equal(odd.querySelectorAll(".stat-table-wrap")[1].querySelectorAll("thead th")[2].getAttribute("aria-sort"), "descending");
  assert.ok(!odd.querySelector(".note"), "no play-by-play line unless asked");
};

scenarios.graded = async () => {
  const { gradedTable } = await import(moduleUrl("ui/grade.js"));
  const { playerNames } = await import(moduleUrl("ui/dom.js"));
  assert.equal(playerNames(7).last, "–", "a name is words: anything else is a dash");
  assert.equal(playerNames("  ").last, "–");
  let opened = null;
  const rows = [
    { playerId: "1", name: "Avery Passer", position: "QB", team: "Swampwater Tech", teamAbbr: "SWT", grade: 88, label: "Very good", rank: 3, of: 144, groupName: "quarterbacks" },
    { playerId: "2", name: "Diner Arm", position: "QB", team: "Diner Tech", teamAbbr: "DT", grade: 91, label: "Elite", rank: 1, of: 144 },
    { playerId: "3", name: null, position: null, team: null, grade: null, rank: null, of: null },
    { playerId: "4", name: "Late Bloomer", position: "QB", team: "Waffle State", teamAbbr: null, grade: 30, label: "Below average", rank: 120, of: "x" },
  ];
  const table = gradedTable(rows, { us: "Swampwater Tech", onTap: (row) => { opened = row; }, caption: "Top graded" });
  document.body.append(table);
  assert.ok(!RAW.test(text(table)), text(table));
  assert.equal(table.dataset.size, "large", "sized by its own box");
  const heads = [...table.querySelectorAll("thead th")];
  // wave 3 (decision 1): the position is a column of its own after the name at large and medium; the team at every size
  assert.deepEqual(heads.map((th) => form2(th, "long")), ["Player", "Pos", "Grade", "Pos. rank", "Team"], "the player first, so his name always shows");
  assert.deepEqual(heads.map((th) => (cls(th).includes("st__min-large") ? "L" : cls(th).includes("st__min-medium") ? "M" : "")), ["", "M", "", "M", ""], "small keeps the player, the grade and the team");
  assert.ok(!heads.some((th) => cls(th).includes("stick")), "nothing sticks: a sized table never scrolls sideways");
  const body = [...table.querySelectorAll("tbody tr")];
  assert.deepEqual(body.map((tr) => pnText(tr.querySelector("td"))), ["Diner Arm", "Avery Passer", "Late Bloomer", "–"], "best grade first, an ungraded player last");
  assert.deepEqual([pnText(body[0].querySelector("td"), "initial"), pnText(body[0].querySelector("td"), "last"), text(body[0].querySelectorAll("td")[1])], ["D. Arm", "Arm", "QB"], "item 6: K. Crawford, then the surname; the position in its own column");
  assert.deepEqual(["Quinn Thrower Jr.", "Cher", "  ", null, "Mary Ann Long"].map((n) => playerNames(n).initial.replace(/\u00A0/g, " ")), ["Q. Thrower", "Cher", "–", "–", "M. Long"]);
  assert.equal(body[0].querySelector("td small"), null, "nothing drawn under the name");
  assert.equal(text(body[3].querySelectorAll("td")[1]), "–", "no position: a dash");
  const team = body[0].querySelectorAll("td")[4];
  assert.equal(team.querySelector("button.team-link").dataset.team, "Diner Tech");
  assert.equal(team.querySelector(".sz-t--short").textContent, "DT", "the team's abbreviation at small, still its link");
  assert.equal(text(body[2].querySelectorAll("td")[4]), "Waffle State", "no abbreviation: the school at every size");
  assert.ok(cls(body[1]).includes("is-us") && !cls(body[0]).includes("is-us"));
  const chip = body[0].querySelectorAll("td")[3].querySelector(".rank-chip");
  assert.ok(chip && text(chip) === "#1" && chip.getAttribute("title") === "1 of 144" && cls(chip).includes("rank-chip--top"), "the position rank chip is toned and says of how many");
  assert.ok(body[0].querySelectorAll("td")[2].querySelector(".grade-chip").getAttribute("title").includes("Elite"));
  assert.equal(text(body[3].querySelectorAll("td")[3]), "–", "no rank: a dash");
  assert.equal(body[2].querySelectorAll("td")[3].querySelector(".rank-chip").getAttribute("title"), "Rank 120", "a damaged field size: the rank alone");
  body[1].click();
  assert.equal(opened.playerId, "1");
  assert.equal(table.querySelector("caption").textContent, "Top graded");
  // players to watch: no team column
  const watch = gradedTable(rows, { showTeam: false });
  assert.deepEqual([...watch.querySelectorAll("thead th")].map((th) => form2(th, "long")), ["Player", "Pos", "Grade", "Pos. rank"]);
  for (const junk of [null, "x", [null, 3, { playerId: 5 }]]) assert.ok(!RAW.test(text(gradedTable(junk))));
};
// --- wave 2, step 2 (owner 2026-10-10): the Pre-Game Program's tables ---------------------------------------------

scenarios.tendencies = async () => {
  const { situationRows, tendenciesBlock } = await import(moduleUrl("ui/depth2.js"));
  const { applyStatSize } = await import(moduleUrl("ui/stat-table.js"));
  const by = [
    { label: "1st down", plays: 40, runRate: 0.575, run: { plays: 23, yardsPerPlay: 4.36, success: { made: 11, of: 23 } }, pass: { plays: 17, yardsPerPlay: 7.1, success: { made: 9, of: 17 } } },
    { label: "3rd and 7 or more", plays: 12, runRate: 0.25, run: { plays: 3, yardsPerPlay: null, success: { made: 0, of: 0 } }, pass: { plays: 9, yardsPerPlay: 5.2, success: { made: 3, of: 9 } } },
    { label: "4th down", plays: 0, runRate: null },
    null,
    "x",
  ];
  const rowsOut = situationRows(by);
  assert.equal(rowsOut.length, 2, "a situation with no plays, and junk, are left out");
  assert.deepEqual([rowsOut[0].runSuccess, rowsOut[0].runSuccessShort, rowsOut[1].runSuccess, rowsOut[1].runSuccessShort], ["11 of 23", "11-23", "–", "–"]);
  assert.equal(rowsOut[1].runYpp, null);
  const t = { plays: 52, games: 3, runRate: 0.5, bySituation: by, passZones: [{ depth: "deep", direction: "left", attempts: 4, completionPct: 0.25, successRate: 0.25 }], runLanes: [{ key: "left", carries: 12, yardsPerCarry: 4.2, successRate: 0.417 }] };
  const block = tendenciesBlock(t, "DT");
  document.body.append(block);
  assert.ok(!RAW.test(text(block)), text(block));
  const wraps = [...block.querySelectorAll(".stat-table-wrap")];
  assert.equal(wraps.length, 1, "the situations; the zones and lanes are the shot chart now (the mock, 2026-10-20)");
  assert.ok(block.querySelector(".tend__chart .shot-field--both") && block.querySelectorAll(".shot-row").length === 3, "deep, short, then the runs");
  assert.ok(wraps.every((w) => w.dataset.size === "large" && typeof w.measure === "function"), "every table sizes itself by its own box");
  const sit = wraps[0];
  const heads = [...sit.querySelectorAll("thead th")];
  assert.deepEqual(heads.map((th) => form2(th, "long")), ["Situation", "Plays", "Run rate", "Yards per carry", "Run success", "Yards per pass play", "Pass success"], "whole heads; carries say Y/C, never Run yds");
  assert.deepEqual(heads.map((th) => form2(th, "mid")), ["Situation", "Plays", "Run rate", "Yds/carry", "Run success", "Yds/pass", "Pass success"]);
  assert.deepEqual(heads.map((th) => form2(th, "short")), ["Situation", "Plays", "Run %", "Y/C", "Run succ.", "Yds/pass", "Pass succ."]);
  assert.deepEqual(heads.map((th) => (cls(th).includes("st__min-medium") ? "m" : "")), ["", "m", "", "m", "", "m", ""], "small: the situation, the run rate and the two made-of pairs");
  assert.ok(heads.every((th) => th.querySelector("button")), "the situations sort");
  const body = [...sit.querySelectorAll("tbody tr")];
  const cells = body[0].querySelectorAll("td");
  assert.deepEqual([form2(cells[0], "long"), form2(cells[0], "short")], ["1st down", "1st"], "the situation names shorten through ui/sizes.js");
  assert.equal(cells[0].dataset.term, "1st down");
  assert.equal(text(cells[2]), "57.5%", "a rate in a table shows one decimal");
  assert.deepEqual([text(cells[3]), form2(cells[4], "long"), form2(cells[4], "short")], ["4.4", "11 of 23", "11-23"]);
  assert.equal(form2(body[1].querySelector("td"), "short"), "3rd 7+");
  assert.equal(text(body[1].querySelectorAll("td")[3]), "–", "no carries to average: a dash");
  applyStatSize(sit, "small");
  assert.equal(sit.dataset.size, "small");
  // the fallback when the answer has no zones: a sized table each, with its own words
  const old = tendenciesBlock({ plays: 20, games: 2, runRate: 0.5, bySituation: [], runDirection: [{ label: "Left", plays: 8, yardsPerPlay: 3.25, success: { made: 4, of: 8 } }, null], passDepth: [{ label: "Behind the line", plays: 5, yardsPerPlay: 2, success: { made: 1, of: 5 } }] }, "DT");
  const splits = [...old.querySelectorAll(".tend__chart .stat-table-wrap")];
  assert.equal(splits.length, 2);
  assert.ok(splits.every((w) => w.dataset.size === "large"));
  assert.deepEqual([...splits[0].querySelectorAll("thead th")].map((th) => form2(th, "long")), ["Direction", "Carries", "Yards per carry", "Success"]);
  assert.deepEqual([...splits[1].querySelectorAll("thead th")].map((th) => form2(th, "long")), ["Depth", "Plays", "Yards per pass play", "Success"]);
  assert.equal(form2(splits[0].querySelectorAll("tbody td")[3], "short"), "4-8");
  assert.ok(!RAW.test(text(old)), text(old));
  for (const junk of [null, "x", { plays: 3, bySituation: "x", passZones: [null], runLanes: "y" }]) assert.ok(!RAW.test(text(tendenciesBlock(junk))));
};

scenarios.playvalue = async () => {
  const { playValueColumns, playValueRows, playValueTable } = await import(moduleUrl("ui/play-value.js"));
  const { applyStatSize } = await import(moduleUrl("ui/stat-table.js"));
  // one column list for every page; the season's plays and total PPA at large only
  assert.deepEqual(playValueColumns().map((c) => c.key), ["name", "all", "pass", "rush"]);
  const season = playValueColumns({ totals: true });
  assert.deepEqual(season.map((c) => c.key), ["name", "all", "pass", "rush", "plays", "totalAll"]);
  assert.deepEqual(season.filter((c) => c.size).map((c) => [c.key, c.size]), [["plays", "large"], ["totalAll", "large"]]);
  assert.ok(season.every((c) => !("sortable" in c)), "no dead column flags: a table of players sorts");
  let opened = null;
  const leaders = [
    { playerId: "7", name: "Avery Passer Jr.", position: "QB", team: "Diner Tech", plays: 210, all: 0.31, pass: 0.35, rush: 0.12, totalAll: 65.4 },
    { playerId: "8", name: "Ron Runner", position: "RB", all: -0.04, pass: null, rush: "x", plays: null, totalAll: null },
    null,
    7,
  ];
  assert.equal(playValueRows(leaders).length, 2);
  assert.equal(playValueRows(leaders)[1].rush, null, "a damaged number is a dash, never NaN");
  const wrap = playValueTable(leaders, { totals: true, onTap: (row) => { opened = row; }, caption: "DT season leaders" });
  document.body.append(wrap);
  assert.ok(!RAW.test(text(wrap)), text(wrap));
  assert.equal(wrap.dataset.size, "large");
  const heads = [...wrap.querySelectorAll("thead th")];
  // wave 3 (decision 1): the position is its own column at large and medium, gone at small, never a line under the name
  assert.deepEqual(heads.map((th) => form2(th, "long")), ["Player", "Pos", "PPA per play", "PPA per pass", "PPA per rush", "Plays", "Total PPA"]);
  assert.deepEqual(heads.map((th) => form2(th, "mid")), ["Player", "Pos", "PPA/play", "Pass", "Rush", "Plays", "Total PPA"]);
  assert.deepEqual(heads.map((th) => form2(th, "short")), ["Player", "Pos", "PPA", "Pass", "Rush", "Plays", "Total PPA"]);
  assert.ok(cls(heads[1]).includes("st__min-medium"), "the position from medium");
  assert.ok(cls(heads[5]).includes("st__min-large") && cls(heads[6]).includes("st__min-large") && !cls(heads[4]).includes("st__min"), "the totals at large only");
  assert.ok(heads.every((th) => th.querySelector("button")), "every column sorts");
  assert.equal(heads[2].getAttribute("aria-sort"), "descending", "the best value first, as the server sends them");
  const first = wrap.querySelectorAll("tbody tr")[0];
  const cells = first.querySelectorAll("td");
  assert.deepEqual([pnText(cells[0]), pnText(cells[0], "initial"), pnText(cells[0], "last"), cells[0].querySelector("small"), text(cells[1])], ["Avery Passer Jr.", "A. Passer", "Passer", null, "QB"], "item 6: K. Crawford from large down (the iPad's half-band keeps the position)");
  assert.deepEqual([text(cells[2]), text(cells[5]), text(cells[6])], ["+0.31", "210", "+65.4"]);
  first.click();
  assert.ok(opened && opened.playerId === "7" && opened.team === "Diner Tech", "the row opens the card with the team the card asks for");
  assert.equal(wrap.querySelector("caption").textContent, "DT season leaders");
  applyStatSize(wrap, "small");
  // a latest game's table: no totals
  const game = playValueTable([{ playerId: "1", name: "Solo", all: 0.5 }]);
  assert.equal(game.querySelectorAll("thead th").length, 5);
  for (const junk of [null, "x", [null, { name: 3 }]]) assert.ok(!RAW.test(text(playValueTable(junk, { totals: true }))));
  // the by-game table: whole heads at large (the defense says allowed), the box words at medium, two values at small
  const { PPA_GAME_COLUMNS, ppaGameRows } = await import(moduleUrl("views/program.js"));
  const { statTable } = await import(moduleUrl("ui/stat-table.js"));
  const games = ppaGameRows([{ week: 1, opponent: "Rhubarb State", opponentAbbr: "RHUB", offense: { overall: 0.21, passing: 0.3, rushing: "x" }, defense: { overall: -0.1 } }, { week: 2, opponent: "Campbell", opponentAbbr: " ", offense: null }, null]);
  assert.deepEqual(games.map((g) => [g.week, g.opponent, g.opponentAbbr]), [[2, "Campbell", null], [1, "Rhubarb State", "RHUB"]], "newest first; a blank abbreviation is none");
  assert.equal(games[1].offRush, null);
  const byGame = statTable({ compact: true, sizes: true, columns: PPA_GAME_COLUMNS, rows: games });
  document.body.append(byGame);
  assert.ok(!RAW.test(text(byGame)), text(byGame));
  const gh = [...byGame.querySelectorAll("thead th")];
  assert.deepEqual(gh.map((th) => form2(th, "long")), ["Week", "Opponent", "Offense, overall", "Offense, passing", "Offense, rushing", "Defense allowed, overall", "Defense allowed, passing", "Defense allowed, rushing"]);
  assert.deepEqual(gh.map((th) => form2(th, "mid")), ["Wk", "Opponent", "Off", "Off pass", "Off rush", "Def", "Def pass", "Def rush"]);
  assert.deepEqual(gh.map((th) => (cls(th).includes("st__min-medium") ? "m" : "")), ["", "", "", "m", "m", "", "m", "m"], "small: week, opponent, the two overall values");
  assert.ok(cls(gh[5]).includes("col-div"), "a divider sets the defense apart");
  const row1 = byGame.querySelectorAll("tbody tr")[1].querySelectorAll("td");
  assert.ok(row1[1].querySelector("button.team-link") && row1[1].querySelector(".sz-t--short").textContent === "RHUB", "the opponent's abbreviation at small, inside its team link");
  assert.deepEqual([text(row1[2]), text(row1[4]), text(row1[5])], ["+0.21", "–", "−0.10"]);
  assert.ok(!byGame.querySelectorAll("tbody tr")[0].querySelectorAll("td")[1].querySelector(".sz-t"), "no abbreviation: the school at every size");
};

scenarios.common = async () => {
  const { commonOpponentsBlock, commonOpponentRows, MARGIN_SCALE } = await import(moduleUrl("ui/offday.js"));
  const { applySize } = await import(moduleUrl("ui/two-team.js"));
  assert.equal(MARGIN_SCALE, 28);
  const raw = [
    { opponent: "Gravy Boat State", opponentAbbr: "GBS", us: [{ result: "W", score: "31-10", margin: 21 }], them: [{ result: "W", score: "24-20", margin: 4 }], usMargin: 21, themMargin: 4 },
    { opponent: "Waffle State", opponentAbbr: null, us: [{ result: "L", score: "17-20", margin: -3 }], them: [{ result: "W", score: "35-14", margin: 21 }, { result: "L", score: "10-13", margin: -3 }], usMargin: -3, themMargin: 18 },
    { opponent: null, us: [] },
    "junk",
  ];
  assert.equal(commonOpponentRows(raw).length, 2, "a row with no opponent, and junk, are left out");
  const wrap = commonOpponentsBlock(raw, { usAbbr: "SWT", themAbbr: "DT", usTeam: "Swampwater Tech", themTeam: "Diner Tech", usName: "Swampwater Tech Mudcats", themName: "Diner Tech Waffles" });
  document.body.append(wrap);
  assert.ok(!RAW.test(text(wrap)), text(wrap));
  const table = wrap.querySelector(".tt-wrap");
  assert.ok(table && table.dataset.size === "large", "the two-team kit, sized by its own box (rule 9)");
  assert.ok(table.querySelector("table").className.includes("tt--tug"), "with the tug bar");
  assert.deepEqual([...table.querySelectorAll("tr.tt__head--a th")].map((th) => form(th, "long")), ["Opponent", "Swampwater Tech Mudcats", "Edge", "Diner Tech Waffles"], "we sit first; the schools and mascots at large");
  assert.deepEqual([...table.querySelectorAll("tr.tt__head--one th")].map((th) => form(th, "short")), ["Opp", "SWT", "Edge", "DT"]);
  const body = [...table.querySelectorAll("tbody tr")];
  assert.equal(body.length, 2);
  const label = body[0].querySelector("td.tt__label");
  const link = label.querySelector("button.team-link");
  assert.ok(link && link.dataset.team === "Gravy Boat State", "the opponent opens its team page");
  assert.deepEqual([form(link, "long"), form(link, "mid"), form(link, "short")], ["Gravy Boat State", "Gravy Boat State", "GBS"], "its abbreviation at small");
  assert.ok(!body[1].querySelector("td.tt__label .tt__t"), "no abbreviation: the school at every size");
  const vals = (tr) => [...tr.querySelectorAll("td.num")].map(text);
  assert.deepEqual(vals(body[0]), ["W 31-10", "W 24-20"]);
  assert.deepEqual(vals(body[1]), ["L 17-20", "W 35-14, L 10-13"], "two meetings in one cell");
  assert.ok(cls(body[0].querySelectorAll("td.num")[0]).includes("lead") && cls(body[1].querySelectorAll("td.num")[1]).includes("lead"));
  assert.equal(body[0].querySelector(".tug__bar--us").style.width, "30%", "21 to 4 is a gap of 17 on the 28-point scale");
  assert.equal(body[1].querySelector(".tug__bar--them").style.width, "38%", "margins either side of zero lean by their gap, never their share");
  assert.equal(body[0].querySelector(".tug").getAttribute("aria-label"), "SWT has the edge, W 31-10 to W 24-20");
  applySize(table, "small");
  assert.equal(table.dataset.size, "small");
  assert.ok(text(wrap.querySelector(".note")).includes("margins"));
  // none in common: the sentence, never a blank
  for (const junk of [[], null, "x", [null, { opponent: "" }]]) {
    const none = commonOpponentsBlock(junk, { usAbbr: "SWT", themAbbr: "DT", usTeam: "Swampwater Tech", themTeam: "Diner Tech" });
    assert.equal(text(none), "Swampwater Tech and Diner Tech have no opponent in common yet this season.");
  }
  assert.ok(!RAW.test(text(commonOpponentsBlock(raw))));
  assert.ok(!RAW.test(text(commonOpponentsBlock(null))));
};

scenarios.advbox = async () => {
  const { advancedBoxBlock, advancedPlayerRows, quarterRows } = await import(moduleUrl("ui/depth2.js"));
  const { applyStatSize } = await import(moduleUrl("ui/stat-table.js"));
  const q = (total, a, b, c, d) => ({ total, quarter1: a, quarter2: b, quarter3: c, quarter4: d });
  const team = (s, line, havoc, start) => ({ success: { overall: q(s, 0.4, 0.5, null, 0.45), standardDowns: q(0.5), passingDowns: q(0.3) }, ppa: { overall: q(0.21), passing: q(0.3), rushing: q(-0.02) }, explosiveness: q(1.2), line: { lineYards: line, stuffRate: 0.12, powerSuccess: 0.5, secondLevelYards: 1.1, openFieldYards: 0.9 }, havoc: { total: havoc, frontSeven: 0.1, db: 0.05 }, fieldPosition: { averageStart: start }, scoring: { opportunities: 6, pointsPerOpportunity: 4.5 } });
  const box = {
    teams: { "Swampwater Tech": team(0.48, 3.5, 0.17, 65.8), "Diner Tech": team(0.39, 2.9, 0.04, 75.3) },
    players: [
      { player: "Avery Passer", playerId: "11", team: "Swampwater Tech", position: "QB", ppa: 0.32, passPpa: 0.31, rushPpa: 0.36, totalPpa: 9.0, usage: 0.389 },
      { player: "Diner Arm Jr.", playerId: null, team: "Diner Tech", position: "QB", ppa: -0.1, passPpa: null, rushPpa: null, totalPpa: -2.4, usage: null },
      { player: null, team: "Diner Tech" },
      "junk",
    ],
    excitement: 4.12,
  };
  // the quarter rows: one name per stat (the Season tables' names), every quarter and the game
  const qr = quarterRows(box.teams["Swampwater Tech"]);
  assert.deepEqual(qr.map((r) => r.label), ["Success rate", "Success on standard downs", "Success on passing downs", "PPA per play", "PPA per pass", "PPA per rush", "Explosiveness"]);
  assert.deepEqual([qr[0].Q1, qr[0].Q3, qr[0].Game], ["40.0%", "–", "48.0%"]);
  assert.equal(quarterRows(null).length, 7);
  let opened = null;
  const block = advancedBoxBlock(box, { us: "Swampwater Tech", them: "Diner Tech", usAbbr: "SWT", themAbbr: "DT", usName: "Swampwater Tech Mudcats", themName: "Diner Tech Waffles", onPlayer: (row) => { opened = row; } });
  document.body.append(block);
  assert.ok(!RAW.test(text(block)), text(block));
  const wraps = [...block.querySelectorAll(".stat-table-wrap")];
  assert.equal(wraps.length, 4, "two quarter tables, the two teams' table, the players");
  assert.ok(wraps.every((w) => w.dataset.size === "large" && typeof w.measure === "function"));
  // by quarter: every column at every size, the row names shorten
  const quarter = wraps[0];
  const qh = [...quarter.querySelectorAll("thead th")];
  assert.deepEqual(qh.map((th) => form2(th, "short")), ["Stat", "Q1", "Q2", "Q3", "Q4", "Game"]);
  assert.equal(form2(qh[0], "long"), "By quarter");
  assert.ok(!qh.some((th) => cls(th).includes("st__min")) && !qh.some((th) => th.querySelector("button")), "nothing drops, the stats keep their order");
  const std = [...quarter.querySelectorAll("tbody tr")][1].querySelector("td");
  assert.deepEqual([form2(std, "long"), form2(std, "mid"), form2(std, "short")], ["Success on standard downs", "Success, std downs", "Std downs"]);
  // the two teams: the kit with the bar, the schools and mascots at large, each row leaning the way its stat runs
  const both = wraps[2];
  assert.ok(cls(both).includes("tt-wrap") && both.querySelector("table").className.includes("tt--tug"));
  assert.deepEqual([...both.querySelectorAll("tr.tt__head--a th")].map((th) => form(th, "long")), ["Both teams", "Swampwater Tech Mudcats", "Edge", "Diner Tech Waffles"]);
  assert.deepEqual([...both.querySelectorAll("tr.tt__head--one th")].map((th) => form(th, "mid")), ["Both teams", "Swampwater Tech", "Edge", "Diner Tech"]);
  const bothRow = (label) => [...both.querySelectorAll("tbody tr")].find((tr) => form(tr.querySelector("td.tt__label"), "long") === label);
  assert.ok(bothRow("Line yards per rush").querySelector(".tug__bar--us"), "more line yards leads");
  assert.ok(bothRow("Average start, yards to goal").querySelector(".tug__bar--us"), "fewer yards to the goal is the better start");
  assert.ok(bothRow("Havoc (defense)").querySelector(".tug__bar--us"));
  assert.ok(!bothRow("Stuff rate").querySelector(".tug__bar"), "an even stuff rate: no lean");
  assert.equal(form(bothRow("Havoc (defense)").querySelector("td.tt__label"), "short"), "Havoc");
  // the players: Team at every size, the splits at large, usage from medium; ours marked; a row opens the card
  const players = wraps[3];
  const ph = [...players.querySelectorAll("thead th")];
  // wave 3 decision 1: the position is its own column at large and medium, gone at small
  assert.deepEqual(ph.map((th) => form2(th, "long")), ["Player", "Pos", "Team", "PPA per play", "PPA per pass", "PPA per rush", "Total PPA", "Usage"]);
  assert.deepEqual(ph.map((th) => form2(th, "short")), ["Player", "Pos", "Team", "PPA", "Pass", "Rush", "Total", "Usage"]);
  assert.deepEqual(ph.map((th) => (cls(th).includes("st__min-large") ? "l" : cls(th).includes("st__min-medium") ? "m" : "")), ["", "m", "", "", "l", "l", "", "m"]);
  const prow = [...players.querySelectorAll("tbody tr")];
  assert.equal(prow.length, 2, "a row with no name, and junk, are left out");
  assert.ok(cls(prow[0]).includes("is-us") && !cls(prow[1]).includes("is-us"));
  assert.deepEqual([pnText(prow[0].querySelector("td"), "last"), text(prow[0].querySelectorAll("td")[2]), text(prow[1].querySelectorAll("td")[2])], ["Passer", "SWT", "DT"]);
  assert.ok(!prow[0].querySelector("td").querySelector("small"), "no line under the name: the position has its column");
  assert.equal(pnText(prow[1].querySelector("td"), "last"), "Arm", "the surname, the suffix dropped");
  assert.equal(ph[6].getAttribute("aria-sort"), "descending", "the most value first");
  prow[0].click();
  assert.ok(opened && opened.playerId === "11" && opened.name === "Avery Passer" && opened.isUs === true && opened.team === "Swampwater Tech", "the row opens his card");
  opened = null;
  prow[1].click();
  assert.equal(opened, null, "wave 2 review: a player the server could not match opens nothing");
  assert.ok(prow[1].getAttribute("role") === null && prow[1].getAttribute("tabindex") === null && prow[0].getAttribute("role") === "button", "only a matched row is a button");
  applyStatSize(players, "small");
  assert.deepEqual(advancedPlayerRows([{ player: "A B", team: "X" }], { us: "Y", usAbbr: "SWT", themAbbr: "DT" })[0].side, "DT");
  // no onPlayer: the rows are not buttons
  const still = advancedBoxBlock(box, { us: "Swampwater Tech", them: "Diner Tech", usAbbr: "SWT", themAbbr: "DT" });
  assert.ok([...[...still.querySelectorAll(".stat-table-wrap")][3].querySelectorAll("tbody tr")].every((tr) => tr.getAttribute("role") !== "button" && tr.getAttribute("tabindex") === null));
  for (const junk of [null, "x", { teams: null }, { teams: { A: null }, players: "x" }]) assert.ok(!RAW.test(text(advancedBoxBlock(junk, { us: "A" }))));
};

scenarios.rowteam = async () => {
  const { twoTeamTable } = await import(moduleUrl("ui/two-team.js"));
  // a row may name a team (its label links to the team's page) and its own shorter words instead of the stat forms
  let asked = null;
  document.addEventListener("kickoff:team", (event) => { asked = event.detail; });
  const wrap = twoTeamTable({ rows: [{ label: "Waffle State", team: "Waffle State", labelShort: "WAF", us: { value: 3 }, them: { value: 1 } }, { label: "Points per game", labelMid: "Pts a game", us: { value: 30 }, them: { value: 20 } }, { label: "Yards per play", team: "  ", labelShort: 7, us: { value: 6 }, them: { value: 5 } }], usAbbr: "SWT", themAbbr: "DT", tug: true });
  document.body.append(wrap);
  assert.ok(!RAW.test(text(wrap)), text(wrap));
  const labels = [...wrap.querySelectorAll("td.tt__label")];
  labels[0].querySelector("button.team-link").click();
  assert.equal(asked, "Waffle State");
  assert.deepEqual([form(labels[0], "long"), form(labels[0], "short")], ["Waffle State", "WAF"]);
  assert.deepEqual([form(labels[1], "mid"), form(labels[1], "short")], ["Pts a game", "Pts a game"], "the row's own words win over the stat forms");
  assert.ok(!labels[2].querySelector("button") && form(labels[2], "short") === "YPP", "a blank team and a damaged short word: the stat forms");
  // a side's shorter words at small (the leader lines' conference-game line): the whole text at large and medium
  const short = twoTeamTable({ rows: [{ label: "Conference games", us: { text: "940 yds, 84/139, 7 TD", textShort: "940 yds" }, them: { text: "1,006 yds", textShort: "  " } }], usAbbr: "SWT", themAbbr: "DT", tug: true });
  const [mine, theirs] = short.querySelectorAll("td.num");
  assert.deepEqual([form(mine, "long"), form(mine, "mid"), form(mine, "short")], ["940 yds, 84/139, 7 TD", "940 yds, 84/139, 7 TD", "940 yds"]);
  assert.ok(!theirs.querySelector(".tt__t") && text(theirs) === "1,006 yds", "a blank short form: the text at every size");
};

// --- wave 2, step 3: In Game's tables ----------------------------------------------------------------------------------

const SIDES = { us: { team: "Swampwater Tech", abbr: "SWT", school: "Swampwater Tech", name: "Swampwater Tech Mudcats" }, them: { team: "Diner Tech", abbr: "DT", school: "Diner Tech" } };

scenarios.ingame = async () => {
  const t = await import(moduleUrl("ui/in-game-tables.js"));
  const { applyStatSize } = await import(moduleUrl("ui/stat-table.js"));
  // quarter by quarter: every period and the game at every size, the stat names shorten, a count's pair says "7-14" at small
  const splits = { periods: ["Q1", "Q2", "OT", null, "Game", 4, "Q1"], teams: { "Swampwater Tech": { Q1: { plays: 15, yards: 98, yardsPerPlay: 6.53, success: { made: 7, of: 14 }, epaPerPlay: 0.214, explosive: 2, turnovers: 0, thirdDown: { made: 3, of: 5 } }, Game: { plays: 30, yards: 200, yardsPerPlay: 6.67, success: { made: 13, of: 29 }, epaPerPlay: -0.05, explosive: 3, turnovers: 1, thirdDown: { made: 4, of: 9 } } } }, notes: [] };
  const sw = t.splitsTable(splits, "Swampwater Tech", { caption: "SWT by quarter" });
  document.body.append(sw);
  assert.ok(!RAW.test(text(sw)), text(sw));
  assert.ok(sw.dataset.size === "large" && typeof sw.measure === "function", "sized by its own box");
  const heads = [...sw.querySelectorAll("thead th")];
  assert.deepEqual(heads.map((th) => form2(th, "long")), ["By quarter", "Q1", "Q2", "OT", "Game"], "one column a period, repeats and junk left out, the game last");
  assert.deepEqual(heads.map((th) => form2(th, "short")), ["Stat", "Q1", "Q2", "OT", "Game"]);
  assert.ok(heads.every((th) => !cls(th).includes("st__min")), "every period and the game at every size (rule 2: only the names shorten)");
  assert.ok(!sw.querySelector("thead button"), "a table of stat names keeps its written order");
  const body = [...sw.querySelectorAll("tbody tr")];
  assert.deepEqual(body.map((tr) => form2(tr.querySelector("td"), "long")), ["Plays", "Yards", "Yards per play", "Success", "PPA per play (no TD plays)", "20+ yard plays", "Turnovers", "Third down"], "one name per stat: PPA, Third down");
  assert.deepEqual(body.map((tr) => form2(tr.querySelector("td"), "short")), ["Plays", "Yards", "YPP", "Success", "PPA", "20+ plays", "Turnovers", "3rd"]);
  const cells = (i) => [...body[i].querySelectorAll("td")];
  assert.deepEqual(cells(2).slice(1).map(text), ["6.5", "–", "–", "6.7"]);
  assert.deepEqual([form2(cells(3)[1], "long"), form2(cells(3)[1], "short"), text(cells(3)[2])], ["7 of 14", "7-14", "–"]);
  assert.deepEqual([text(cells(4)[1]), text(cells(4)[4])], ["+0.21", "−0.05"]);
  assert.deepEqual([form2(cells(7)[4], "long"), form2(cells(7)[4], "short")], ["4 of 9", "4-9"]);
  assert.ok(cells(0).slice(1).every((td) => !cls(td).includes("txt")), "the values in the stat face, right-aligned");
  assert.equal(sw.querySelector("caption").textContent, "SWT by quarter");
  applyStatSize(sw, "small");
  assert.equal(sw.dataset.size, "small");
  assert.equal(t.splitRows({}, "A")[0].Game, "–");
  for (const junk of [null, "x", { periods: "Q1", teams: [] }, { periods: ["Q1"], teams: { A: { Q1: "x" } } }]) assert.ok(!RAW.test(text(t.splitsTable(junk, "A"))));

  // tendencies by situation: the program's words, the run rate to one decimal, the plays from medium
  const tend = { "Swampwater Tech": [{ key: "standard", label: "Standard downs", plays: 20, passRate: 0.45, runSuccess: { made: 6, of: 11 }, passSuccess: { made: 4, of: 9 } }, { key: "third_long", label: "3rd and 7 or more", plays: 0, passRate: null, runSuccess: { made: 0, of: 0 }, passSuccess: null }, null, "junk"], "Diner Tech": [{ label: "Red zone", plays: 0 }] };
  const tw = t.tendencyTable(tend, "Swampwater Tech", { caption: "SWT by situation" });
  document.body.append(tw);
  assert.ok(!RAW.test(text(tw)), text(tw));
  assert.equal(tw.dataset.size, "large");
  const th2 = [...tw.querySelectorAll("thead th")];
  assert.deepEqual(th2.map((th) => form2(th, "long")), ["Situation", "Plays", "Run rate", "Run success", "Pass success"], "the Pre-Game Program's names for the same numbers");
  assert.deepEqual(th2.map((th) => form2(th, "short")), ["Situation", "Plays", "Run %", "Run succ.", "Pass succ."]);
  assert.deepEqual(th2.map((th) => (cls(th).includes("st__min-medium") ? "m" : "")), ["", "m", "", "", ""], "small: the situation, the run rate and both made-of pairs");
  assert.ok(!tw.querySelector("thead button"), "the situations keep their order");
  const tr0 = [...tw.querySelectorAll("tbody tr")[0].querySelectorAll("td")];
  assert.deepEqual([form2(tr0[0], "long"), form2(tr0[0], "short"), tr0[0].dataset.term], ["Standard downs", "Std downs", "Standard downs"]);
  assert.deepEqual([text(tr0[2]), form2(tr0[3], "long"), form2(tr0[3], "short"), form2(tr0[4], "short")], ["55.0%", "6 of 11", "6-11", "4-9"], "a rate in a table shows one decimal");
  const tr1 = [...tw.querySelectorAll("tbody tr")[1].querySelectorAll("td")];
  assert.deepEqual([form2(tr1[0], "short"), text(tr1[2]), text(tr1[4])], ["3rd 7+", "–", "–"], "a situation with no snaps yet still has its row");
  assert.equal(tw.querySelectorAll("tbody tr").length, 2);
  assert.equal(text(t.tendencyTable(tend, "Diner Tech")), "No snaps yet.");
  for (const junk of [null, "x", { A: "x" }]) assert.equal(text(t.tendencyTable(junk, "A")), "No snaps yet.");

  // fourth down: one data point per column (rule 3), no blank head, the chance from medium
  const f = { down: 4, distance: 3, yardsToGoal: 28, breakEven: 0.452, go: { success: 2.14, fail: -1.31 }, fieldGoal: { distance: 45, makeChance: 0.62, ep: 0.9 }, punt: { ep: -0.5 }, best: "fieldGoal" };
  const fw = t.fourthDownTable(f);
  document.body.append(fw);
  assert.ok(!RAW.test(text(fw)), text(fw));
  const fh = [...fw.querySelectorAll("thead th")];
  assert.deepEqual(fh.map((th) => form2(th, "long")), ["Choice", "Expected points", "If it fails", "Chance"]);
  assert.deepEqual(fh.map((th) => form2(th, "mid")), ["Choice", "Exp. points", "If it fails", "Chance"]);
  assert.deepEqual(fh.map((th) => form2(th, "short")), ["Choice", "EP", "If not", "Chance"]);
  assert.deepEqual(fh.map((th) => (cls(th).includes("st__min-medium") ? "m" : "")), ["", "", "", "m"]);
  assert.ok(fh.every((th) => text(th).trim()), "every column has a head");
  const fr = [...fw.querySelectorAll("tbody tr")].map((tr) => [...tr.querySelectorAll("td")]);
  assert.deepEqual(fr.map((r) => [form2(r[0], "long"), form2(r[0], "short")]), [["Go for it", "Go"], ["Field goal, 45 yd", "FG 45 yd"], ["Punt (40 net)", "Punt"]]);
  assert.deepEqual(fr.map((r) => r.slice(1).map(text)), [["+2.1", "−1.3", "45.2% needed"], ["+0.9", "–", "62.0% to make"], ["−0.5", "–", "–"]]);
  assert.equal(t.fourthDownRows({ breakEven: 0.5, go: {}, fieldGoal: { makeChance: "x" } })[1].optionShort, "FG");
  for (const junk of [null, "x", { breakEven: "x" }, {}]) assert.equal(t.fourthDownTable(junk), null);

  // the recruits on hand: a table of players sorts; the high school, hometown and class at large
  const vis = [{ name: "Five Star Jr.", position: "QB", stars: 5, highSchool: "IMG Academy", hometown: "Bradenton, FL", classYear: 2027, status: "confirmed" }, { name: "  ", stars: 3 }, { name: "Walk On", stars: "x", classYear: "2027" }, null, 4];
  assert.equal(t.visitorRows(vis).length, 2, "a recruit with no name, and junk, are left out");
  const vw = t.visitorsTable(vis, { caption: "Visiting SWT" });
  document.body.append(vw);
  assert.ok(!RAW.test(text(vw)), text(vw));
  const vh = [...vw.querySelectorAll("thead th")];
  // wave 3 decision 1, as on the Recruiting page: the position its own column at large and medium
  assert.deepEqual(vh.map((th) => form2(th, "long")), ["Recruit", "Pos", "Stars", "High school", "Hometown", "Class", "Status"]);
  assert.deepEqual(vh.map((th) => (cls(th).includes("st__min-large") ? "l" : cls(th).includes("st__min-medium") ? "m" : "")), ["", "m", "", "l", "l", "l", ""], "small: the recruit, his stars, his status");
  assert.ok(vh.every((th) => th.querySelector("button")), "a table of players sorts");
  const v0 = [...vw.querySelectorAll("tbody tr")[0].querySelectorAll("td")];
  assert.deepEqual([pnText(v0[0]), pnText(v0[0], "last"), v0[0].querySelector("small")], ["Five Star Jr.", "Star", null], "a notes name that reads cleanly shortens");
  assert.deepEqual(v0.slice(1).map(text), ["QB", "5-star", "IMG Academy", "Bradenton, FL", "2027", "confirmed"], "a class is a year, never 2,027");
  assert.deepEqual([...vw.querySelectorAll("tbody tr")[1].querySelectorAll("td")].slice(1).map(text), ["–", "–", "–", "–", "–", "–"]);
  assert.equal(text(t.visitorsTable([])), "No visitors listed.");
  assert.equal(text(t.visitorsTable("x")), "No visitors listed.");
  assert.equal(t.madeOf({ made: 3, of: 8 }), "3 of 8");
  assert.equal(t.madeShort({ made: 3, of: 8 }), "3-8");
  assert.deepEqual([t.madeOf(null), t.madeShort({ made: 0, of: 0 })], ["–", "–"]);
};

scenarios.ingametwo = async () => {
  const t = await import(moduleUrl("ui/in-game-tables.js"));
  const { applySize } = await import(moduleUrl("ui/two-team.js"));
  // the drive summary on the two-team kit with the bar (rule 9), leaning by the real margin
  const summary = { "Swampwater Tech": { drives: 8, points: 28, pointsPerDrive: 3.5, threeAndOuts: 1, turnovers: 0, opportunities: 5, pointsPerOpportunity: 5.6 }, "Diner Tech": { drives: 8, points: 10, pointsPerDrive: 1.25, threeAndOuts: 4, turnovers: 2, opportunities: 3, pointsPerOpportunity: "x" } };
  const dw = t.driveSummaryTable(summary, SIDES);
  document.body.append(dw);
  assert.ok(!RAW.test(text(dw)), text(dw));
  assert.ok(cls(dw).includes("tt-wrap") && dw.dataset.size === "large" && dw.querySelector("table").className.includes("tt--tug"));
  assert.deepEqual([...dw.querySelectorAll("tr.tt__head--a th")].map((th) => form(th, "long")), ["Drives", "Swampwater Tech Mudcats", "Edge", "Diner Tech"], "the school and mascot at large");
  assert.deepEqual([...dw.querySelectorAll("tr.tt__head--one th")].map((th) => form(th, "short")), ["Drives", "SWT", "Edge", "DT"]);
  const rows = [...dw.querySelectorAll("tbody tr")];
  const label = (tr) => tr.querySelector("td.tt__label");
  assert.deepEqual(rows.map((tr) => form(label(tr), "long")), t.DRIVE_ROWS.map((r) => r[0]));
  assert.deepEqual(rows.map((tr) => form(label(tr), "short")), ["Drives", "Points", "Pts/drive", "3-and-outs", "Turnovers", "Chances", "Pts/chance"]);
  const bar = (i) => rows[i].querySelector(".tug__bar");
  assert.ok(!bar(0), "finished drives are a count, not a grade: no bar");
  assert.equal(bar(1).style.width, "24%", "28 to 10 leans by its share, never a fixed amount");
  assert.ok(cls(bar(3)).includes("tug__bar--us") && bar(3).style.width === "30%", "fewer three-and-outs is better: 1 to 4");
  assert.equal(bar(4).style.width, "50%", "0 turnovers to 2 leans all the way");
  assert.deepEqual([...rows[2].querySelectorAll("td.num")].map(text), ["3.50", "1.25"]);
  assert.equal(text(rows[6].querySelectorAll("td.num")[1]), "–", "a damaged number is a dash");
  applySize(dw, "small");
  assert.equal(dw.dataset.size, "small");
  for (const junk of [null, {}, { A: { drives: "x" } }]) assert.equal(t.driveSummaryTable(junk, SIDES), null);
  assert.equal(t.driveSummaryTable(summary, null), null, "no sides: nothing to read");

  // each team's play value: the defense's rows say allowed, lower is better, leaning on the PPA scale
  const teams = { us: { offense: { overall: 0.31, passing: 0.42, rushing: 0.12 }, defense: { overall: -0.05, passing: 0.02, rushing: "x" } }, them: { offense: { overall: 0.05 }, defense: { overall: 0.2 } } };
  const vw = t.teamValueTable(teams, SIDES);
  document.body.append(vw);
  assert.ok(!RAW.test(text(vw)), text(vw));
  assert.ok(cls(vw).includes("tt-wrap") && vw.querySelector("table").className.includes("tt--tug"));
  assert.deepEqual([...vw.querySelectorAll("tr.tt__head--one th")].map((th) => form(th, "short")), ["PPA", "SWT", "Edge", "DT"]);
  const vr = [...vw.querySelectorAll("tbody tr")];
  assert.deepEqual(vr.map((tr) => form(label(tr), "long")), ["Offense, overall", "Offense, passing", "Offense, rushing", "Defense allowed, overall", "Defense allowed, passing", "Defense allowed, rushing"], "a defense's rows say allowed");
  assert.deepEqual(vr.map((tr) => form(label(tr), "mid")).slice(3), ["Def allowed, overall", "Def allowed, passing", "Def allowed, rushing"]);
  assert.deepEqual(vr.map((tr) => form(label(tr), "short")), ["Off all", "Off pass", "Off rush", "Def all", "Def pass", "Def rush"]);
  assert.equal(vr[0].querySelector(".tug__bar--us").style.width, "26%", "+0.31 to +0.05: 0.26 of the 0.5 scale");
  assert.ok(vr[3].querySelector(".tug__bar--us") && vr[3].querySelector(".tug__bar--us").style.width === "25%", "allowing -0.05 beats allowing +0.20");
  assert.deepEqual([...vr[3].querySelectorAll("td.num")].map(text), ["−0.05", "+0.20"]);
  assert.equal(text(vr[5].querySelectorAll("td.num")[0]), "–");
  for (const junk of [null, "x", {}, { us: "x", them: [] }]) assert.equal(text(t.teamValueTable(junk, SIDES)), "No team values for this game yet.");
  assert.ok(!RAW.test(text(t.teamValueTable(teams, null))), "no sides: the abbreviations are dashes, never a raw word");
};

scenarios.situation = async () => {
  const { situationGrid, situationRows, situationSkeleton, SITUATION_LABELS } = await import(moduleUrl("ui/situation.js"));
  const usBox = { thirdDown: { made: 5, of: 12 }, fourthDown: { made: 1, of: 2 }, redZone: { scores: 3, trips: 4 }, turnovers: 0, penalties: { count: 6, yards: 45 }, possessionTime: "31:10", yardsPerPlay: 6.4, totalYards: 450 };
  const themBox = { thirdDown: { made: 3, of: 11 }, turnovers: 2, penalties: { count: 4 }, possessionTime: "28:50", yardsPerPlay: 5.0, totalYards: 300 };
  assert.deepEqual(situationRows(usBox, themBox).map((r) => r.label), SITUATION_LABELS);
  assert.ok(situationRows(usBox, themBox).every((r) => r.kind === "parent"), "no indent: there is no group here");
  const wrap = situationGrid({ us: { abbr: "SWT", box: usBox, school: "Swampwater Tech", name: "Swampwater Tech Mudcats" }, them: { abbr: "DT", box: themBox, school: "Diner Tech" } });
  document.body.append(wrap);
  assert.ok(!RAW.test(text(wrap)), text(wrap));
  assert.ok(cls(wrap).includes("tt-wrap") && wrap.dataset.size === "large" && wrap.querySelector("table").className.includes("tt--tug"), "the Team stats kit with the bar");
  assert.equal(wrap.querySelectorAll("table").length, 1, "one table, not two half grids");
  assert.deepEqual([...wrap.querySelectorAll("tr.tt__head--a th")].map((th) => form(th, "long")), ["Situation", "Swampwater Tech Mudcats", "Edge", "Diner Tech"]);
  const rows = [...wrap.querySelectorAll("tbody tr")];
  assert.deepEqual(rows.map((tr) => form(tr.querySelector("td.tt__label"), "long")), SITUATION_LABELS, "Total yards is Yards, as in Team stats");
  assert.deepEqual(rows.map((tr) => form(tr.querySelector("td.tt__label"), "short")), ["3rd", "4th", "Red zone", "Turnovers", "Penalties", "Possession", "YPP", "Yards"]);
  assert.ok(rows.every((tr) => cls(tr).includes("is-parent")));
  const vals = (i) => [...rows[i].querySelectorAll("td.num")];
  assert.deepEqual([vals(0)[0].dataset.k, vals(0)[1].dataset.k], ["ts:Third down:us", "ts:Third down:them"], "the Team stats flash keys");
  assert.deepEqual(vals(4).map(text), ["6-45", "4"], "the count alone before the box score posts");
  assert.ok(cls(vals(7)[0]).includes("lead") && rows[7].querySelector(".tug__bar--us").style.width === "10%", "450 yards to 300 leans by its share");
  assert.ok(!rows[5].querySelector(".tug__bar"), "time of possession is no contest");
  assert.equal(wrap.querySelector("caption").textContent, "Situation");
  for (const junk of [undefined, null, "x", { us: "x", them: 3 }]) assert.ok(!RAW.test(text(situationGrid(junk))));
  assert.ok(cls(situationSkeleton()).includes("skel-table"));
};

scenarios.scoressize = async () => {
  const { scoresTable } = await import(moduleUrl("ui/scores.js"));
  const games = [
    { gameId: 1, status: "final", detail: "Final", away: { school: "Diner Tech", abbr: "DT", points: 21, rank: 12 }, home: { school: "Swampwater Tech", abbr: "SWT", points: 28 } },
    { gameId: 2, status: "pre", detail: "7:30 PM", away: { school: "Lowland" }, home: { school: null, abbr: "X" } },
  ];
  const wrap = scoresTable({ games });
  document.body.append(wrap);
  assert.ok(!RAW.test(text(wrap)), text(wrap));
  assert.ok(wrap.dataset.size === "large" && typeof wrap.measure === "function", "sized by its own box, in place");
  const heads = [...wrap.querySelectorAll("thead th")];
  assert.deepEqual(heads.map((th) => form2(th, "long")), ["AP rank", "Away", "Pts", "AP rank", "Home", "Pts", "Status"], "every data point its own column (rule 3), every column a head");
  assert.deepEqual(heads.map((th) => form2(th, "mid")), ["AP", "Away", "Pts", "AP", "Home", "Pts", "Status"]);
  assert.deepEqual(heads.map((th) => (cls(th).includes("st__min-medium") ? "m" : "")), ["m", "", "", "m", "", "", ""], "small: no poll columns");
  assert.equal(heads[0].dataset.term, "AP rank");
  const groups = () => [...wrap.querySelectorAll("tr.scores__group th")].map((th) => th.getAttribute("colspan"));
  assert.deepEqual(groups(), ["7", "7"]);
  const final = [...wrap.querySelectorAll("tbody tr")].find((tr) => tr.querySelector(".scores__team--win"));
  const cells = [...final.querySelectorAll("td")];
  assert.ok(cells[0].querySelector(".poll-badge") && !cells[1].querySelector(".poll-badge"), "the rank in its own column, not in the name cell");
  assert.equal(text(cells[3]), "–", "an unranked team: a dash");
  const away = cells[1].querySelector("button.team-link");
  assert.deepEqual([form2(away, "long"), form2(away, "mid"), form2(away, "short")], ["Diner Tech", "Diner Tech", "DT"], "the school at large and medium, the abbreviation at small");
  assert.equal(cells[2].dataset.k, "pts:1:away");
  const pre = [...wrap.querySelectorAll("tbody tr")].find((tr) => text(tr).includes("Lowland"));
  assert.ok(!pre.querySelectorAll("td")[4].querySelector("button") && text(pre.querySelectorAll("td")[4]) === "–", "a team with no school: a dash, never a link to nowhere");
  wrap.applySize("small");
  assert.equal(wrap.dataset.size, "small");
  assert.deepEqual(groups(), ["5", "5"], "the group rows span the columns small shows");
  wrap.update([games[0]]);
  assert.deepEqual(groups(), ["5"], "an update keeps the size's spans");
  wrap.applySize("medium");
  assert.deepEqual(groups(), ["7"]);
};

scenarios.penaltysize = async () => {
  const { penaltyBody, callRows } = await import(moduleUrl("ui/penalty-panel.js"));
  const entry = { what: "Grabbed an opponent.", calls: [{ who: "Offense", result: "10 yards from the spot of the foul", rule: "9-3-3", page: 111 }, { who: "Defense", result: "10 yards and an automatic first down", rule: "9-3-4", page: null }, null, "junk", [1]] };
  assert.equal(callRows(entry.calls).length, 2);
  assert.deepEqual(callRows(null), []);
  const body = penaltyBody(entry, { name: "Holding" }, { title: "2026 NCAA Football Rules Book", url: "https://example.org/rules.pdf" });
  document.body.append(body);
  assert.ok(!RAW.test(text(body)), text(body));
  const wrap = body.querySelector(".flag-panel__calls .stat-table-wrap");
  assert.ok(wrap && wrap.dataset.size === "large", "the calls are a sized table");
  assert.deepEqual([...wrap.querySelectorAll("thead th")].map((th) => form2(th, "long")), ["Fouled by", "Penalty", "Rulebook"]);
  assert.deepEqual([...wrap.querySelectorAll("thead th")].map((th) => form2(th, "short")), ["By", "Penalty", "Rule"], "wave 3: the heads shorten at small");
  assert.ok(!wrap.querySelector("thead button"), "the calls keep the book's order");
  const rows = [...wrap.querySelectorAll("tbody tr")].map((tr) => [...tr.querySelectorAll("td")]);
  assert.deepEqual(rows.map((r) => text(r[0])), ["Offense", "Defense"], "whole words, never the stat forms' Off or Def (allowed)");
  assert.ok(rows.every((r) => !r[0].querySelector(".sz-t")));
  assert.ok(cls(rows[0][1]).includes("st__wrap"), "the penalty is prose: the one column that wraps");
  const link = rows[0][2].querySelector("a.flag-rule");
  assert.equal(link.getAttribute("href"), "https://example.org/rules.pdf#page=111");
  const page = link.querySelector(".sz-t");
  assert.ok(page && cls(page).includes("sz-t--long") && cls(page).includes("sz-t--mid") && text(page) === " page 111", "the page line at large and medium, the link alone at small");
  assert.equal(wrap.querySelector("caption").textContent, "Holding: the penalty and the rule");
  assert.ok(!penaltyBody({ calls: [] }, { name: "x" }, null).querySelector("table"), "no calls: no table");
};

scenarios.wave3kit = async () => {
  // wave 3 (owner 2026-10-10): the stat table's shared pieces, each declared on a column of a sized table
  const { statTable, applyStatSize, ownColumns, sortValue, sortRows } = await import(moduleUrl("ui/stat-table.js"));
  const list = [
    { rank: 1, of: 136, player: "Keegan Crawford", playerShort: "Crawford", position: "QB", team: "Swampwater Tech", abbr: "SWT", conference: "Biscuit Belt", value: 1378, note: "a long note", date: "2026-09-05" },
    { rank: 3, tied: true, of: 136, player: "Troy Palmer", playerShort: "Palmer", position: "", team: "Diner Tech", abbr: "DT", conference: null, value: 1128, note: null, date: "2025-11-29" },
    { rank: null, of: 136, player: "Ned Nobody", playerShort: "Nobody", position: "RB", team: null, abbr: null, conference: "Big Pie", value: null, note: "x", date: "2026-08-30" },
  ];
  const columns = [
    { key: "rank", label: "FBS rank", labelMid: "FBS", labelShort: "#", kind: "rank", of: "of", tie: "tied", order: true, link: (row) => (row.rank === 1 ? "#national=board%3Apassing%3AYDS" : null) },
    { key: "player", label: "Player", kind: "text", shortKey: "playerShort", sub: "position", subLabel: "Pos" },
    { key: "team", label: "Team", kind: "text", team: true, renderShort: (row) => (row.team ? `${row.abbr}!` : null), sub: "conference", subLabel: "Conference", subLabelMid: "Conf", subSize: "large", subTeam: false },
    { key: "value", label: "Passing yards", labelMid: "Pass yds", labelShort: "Yds", format: "0f" },
    { key: "note", label: "Note", kind: "text", sortable: false, wrap: true, size: "medium" },
  ];
  // decision 1: a sub with a head is its own column after the name, from medium (subSize "large": large only)
  const own = ownColumns(columns);
  assert.deepEqual(own.map((c) => c.key), ["rank", "player", "position", "team", "conference", "value", "note"]);
  assert.deepEqual([own[2].label, own[2].size, own[2].kind, own[4].label, own[4].labelMid, own[4].size], ["Pos", "medium", "text", "Conference", "Conf", "large"]);
  assert.ok(own[1].sub === null && own[3].sub === null, "the name's cell loses the line under it");
  assert.deepEqual(ownColumns([{ key: "a", sub: "b" }, null, "x", { key: "c", sub: "d", subLabel: "  " }]).map((c) => c.key), ["a", "c"], "no head, no column; junk skipped");
  const wrap = statTable({ compact: true, sizes: true, columns, rows: list, sort: { key: "rank", dir: "ascending" } });
  document.body.append(wrap);
  assert.ok(!RAW.test(text(wrap)), text(wrap));
  const heads = [...wrap.querySelectorAll("thead th")];
  assert.deepEqual(heads.map((th) => form2(th, "long")), ["FBS rank", "Player", "Pos", "Team", "Conference", "Passing yards", "Note"]);
  assert.deepEqual(heads.map((th) => (cls(th).includes("st__min-large") ? "L" : cls(th).includes("st__min-medium") ? "M" : "")), ["", "", "M", "", "L", "", "M"], "the sub columns are gone at small");
  assert.equal(heads[2].dataset.term, "Pos");
  // sortable: false on a column keeps its head plain while the others sort
  assert.ok(heads[0].querySelector("button") && heads[5].querySelector("button") && !heads[6].querySelector("button"), "the note's head is plain");
  const rowsNow = () => [...wrap.querySelectorAll("tbody tr")].map((tr) => [...tr.querySelectorAll("td")]);
  let r = rowsNow();
  assert.equal(text(r[0][2]), "QB");
  assert.ok(!r[0][1].querySelector("small"), "no line under the name once the position has a column");
  assert.equal(text(r[1][2]), "–", "an empty position: a dash, never a blank or null");
  assert.equal(text(r[0][4]), "Biscuit Belt");
  // decision 2: the list's own order is the chip at large and medium and a plain number at small
  const big = r[0][0].querySelector(".sz-t--long");
  assert.ok(cls(big).includes("sz-t--mid") && big.querySelector("a.rank-chip--link"), "the chip (linked) at large and medium");
  assert.equal(big.querySelector("a.rank-chip--link").getAttribute("href"), "#national=board%3Apassing%3AYDS");
  assert.equal(r[0][0].querySelector(".sz-t--short").textContent, "1");
  assert.ok(!r[0][0].querySelector(".sz-t--short .rank-chip"), "no chip at small");
  assert.equal(r[1][0].querySelector(".sz-t--short").textContent, "T3", "a tie says so at small");
  assert.ok(r[1][0].querySelector(".sz-t--long .rank-chip:not(.rank-chip--link)"), "no list behind it: a plain chip");
  assert.equal(r[2][0].querySelector(".sz-t--short").textContent, "–");
  assert.equal(r[2][0].querySelector(".sz-t--long").textContent, "–", "no rank: a dash at every size");
  assert.equal(r[0][0].querySelectorAll(".rank-chip").length, 1, "one chip, not a second one after the cell");
  // renderShort: a team link at large and medium, the caller's own small form at small
  assert.equal(r[0][3].querySelector(".sz-t--long button.team-link").textContent, "Swampwater Tech");
  assert.equal(r[0][3].querySelector(".sz-t--short").textContent, "SWT!");
  assert.equal(text(r[2][3].querySelector(".sz-t--short")), "–", "a renderShort with nothing to draw: a dash");
  // a header tap still sorts; the plain note head does nothing
  heads[5].querySelector("button").click();
  r = rowsNow();
  assert.deepEqual(r.map((tr) => text(tr[5])), ["1,378", "1,128", "–"]);
  applyStatSize(wrap, "small");
  assert.equal(wrap.dataset.size, "small");
  // the same columns unsized: the sub stays under the name, the order column is the plain chip, no forms
  const plain = statTable({ compact: true, columns, rows: list });
  assert.ok(!plain.querySelector(".sz-t"), "unsized: no size forms");
  assert.equal(plain.querySelectorAll("thead th").length, 5, "unsized: no extra columns");
  const p0 = plain.querySelectorAll("tbody tr")[0].querySelectorAll("td");
  assert.equal(p0[1].querySelector("small").textContent, "QB");
  assert.ok(p0[0].querySelector(".rank-chip"));
  // a group row (isGroup): its rank cells stay empty, never a dash
  const grouped = statTable({ compact: true, sizes: true, sortable: false, columns: [{ key: "label", label: "Statistic", kind: "text" }, { key: "rank", label: "FBS rank", labelMid: "FBS", kind: "rank", of: 136, size: "medium" }, { key: "order", label: "#", kind: "rank", order: true }], rows: [{ isGroup: true, label: "Offense" }, { label: "Points per game", rank: 5, order: 2 }, { label: "Yards per play", rank: null, order: null }] });
  const g = [...grouped.querySelectorAll("tbody tr")].map((tr) => [...tr.querySelectorAll("td")]);
  assert.deepEqual([text(g[0][1]), text(g[0][2]), g[0][1].childNodes.length], ["", "", 0], "the group's title row carries no rank");
  assert.ok(g[1][1].querySelector(".rank-chip") && text(g[2][1]) === "–");
  assert.ok(!RAW.test(text(grouped)), text(grouped));
  // an ISO date sorts by the moment it names, not its year (2025-11-29 is before 2026-08-30 is before 2026-09-05)
  assert.deepEqual(sortValue("2026-09-05"), [Date.parse("2026-09-05"), 0]);
  assert.deepEqual(sortValue("2026-09-05T19:30:00.000Z"), [Date.parse("2026-09-05T19:30:00.000Z"), 0]);
  assert.deepEqual(sortValue("2026-10"), [2026, -10], "not a whole date: the old reading (a pair)");
  assert.deepEqual(sortRows(list, { key: "date" }, "descending").map((row) => row.date), ["2026-09-05", "2026-08-30", "2025-11-29"]);
  assert.deepEqual(sortRows(list, { key: "date" }, "ascending").map((row) => row.date), ["2025-11-29", "2026-08-30", "2026-09-05"]);
  // wave 3 review: a numeric tie key keeps its order as numbers (the road ahead's schedule order: game 10 after game 2)
  const road = Array.from({ length: 12 }, (_, order) => ({ order, record: "0-0" }));
  const ordered = Array.from({ length: 12 }, (_, i) => i);
  assert.deepEqual(sortRows(road, { key: "record", tieKey: "order" }, "ascending").map((row) => row.order), ordered);
  assert.deepEqual(sortRows(road, { key: "record", tieKey: "order" }, "descending").map((row) => row.order), ordered, "a tie never flips with the sort");
  assert.deepEqual(sortRows([{ name: "b", v: null }, { name: "a", v: null }], { key: "v" }, "ascending").map((row) => row.name), ["a", "b"], "a text tie key stays alphabetical");
  // junk never throws or prints raw words
  for (const junk of [null, "x", [null, 3, { rank: "x", player: {}, position: [], team: 5 }]]) {
    const w = statTable({ sizes: true, columns, rows: junk });
    assert.ok(!RAW.test(text(w)), text(w));
  }
  const failing = statTable({ sizes: true, columns: [{ key: "team", label: "Team", kind: "text", renderShort: () => { throw new Error("boom"); } }], rows: [{ team: "Diner Tech" }] });
  assert.equal(text(failing.querySelector("tbody td .sz-t--short")), "Diner Tech", "a failing renderShort falls back to the value");
};

scenarios.whoplayers = async () => {
  // wave 3 (owner 2026-10-10): the two-team kit's player column on each side, for Leaders' "vs opponent" boards
  const { twoTeamTable, applySize } = await import(moduleUrl("ui/two-team.js"));
  const opened = [];
  const face = (name) => { const span = document.createElement("span"); span.className = "leader-who"; span.append(name); return span; };
  const pairs = () => [
    { label: "1", format: "0f", higherIsBetter: true, us: { value: 706, rank: 66, of: 186, who: face("Keegan Crawford"), whoName: "Keegan Crawford", onWho: () => opened.push("us1") }, them: { value: 288, rank: 140, of: 186, who: "Marcus Hart", onWho: () => { throw new Error("no card"); } } },
    { label: "2", format: "0f", higherIsBetter: true, us: { value: 120, who: "Tramell Jones Jr." }, them: null },
  ];
  const wrap = twoTeamTable({ rows: pairs(), usAbbr: "SWT", themAbbr: "SD", usTeam: "Swampwater Tech", themTeam: "Silver Dollar", usName: "Swampwater Tech Mudpuppies", themName: "Silver Dollar Miners", centered: true, labelHead: "Passing yards" });
  document.body.append(wrap);
  assert.ok(!RAW.test(text(wrap)), text(wrap));
  // the large head: each team over its own columns, the player outermost under it
  const headA = [...wrap.querySelectorAll("tr.tt__head--a th")];
  assert.deepEqual(headA.map((th) => th.getAttribute("colspan")), ["3", null, "3"], "player, FBS rank and value under each team");
  assert.deepEqual([...wrap.querySelectorAll("tr.tt__head--b th")].map(text), ["Player", "FBS rank", "", "", "FBS rank", "Player"]);
  assert.deepEqual([...wrap.querySelectorAll("tr.tt__head--one th")].map((th) => form(th, "short")), ["Player", "FBS", "SWT", "Pass yds", "SD", "FBS", "Player"]);
  const [first, second] = wrap.querySelectorAll("tbody tr");
  assert.deepEqual([...first.childNodes].map((td) => cls(td).split(" ").slice(0, 2).join(".")), ["txt.tt__who", "tt__rank.tt__rank--natl", "num.tt__cell", "tt__tug.tt__mid", "num.tt__cell", "tt__rank.tt__rank--natl", "txt.tt__who"], "mirrored: the players outermost");
  assert.ok(cls(first.childNodes[0]).includes("tt__who--us") && cls(first.childNodes[6]).includes("tt__who--them"));
  assert.ok(!cls(first.childNodes[0]).includes("tt__min"), "the player shows at every size");
  const ours = first.childNodes[0].querySelector("button.tt__who-btn");
  assert.ok(ours.querySelector(".tt__t--long.tt__t--mid .leader-who"), "the drawn node at large and medium");
  assert.deepEqual(["full", "initial", "last"].map((f) => pnText(ours.querySelector(".tt__t--short"), f)), ["Keegan Crawford", "K. Crawford", "Crawford"], "item 6: at small the name alone (whoName), stepping down");
  assert.equal(ours.getAttribute("title"), "Open Keegan Crawford's card");
  ours.click();
  assert.deepEqual(opened, ["us1"]);
  first.childNodes[6].querySelector("button.tt__who-btn").click(); // a card that fails to open never breaks the page
  assert.equal(pnText(first.childNodes[6]), "Marcus Hart");
  assert.ok(!first.childNodes[6].querySelector(".tt__t"), "a name given as words: one drawing, its forms follow the steps");
  assert.ok(!second.childNodes[0].querySelector("button"), "no onWho: the name alone");
  assert.equal(pnText(second.childNodes[0], "last"), "Jones");
  assert.equal(text(second.childNodes[6]), "–", "no player on that side: a dash");
  assert.equal(text(second.childNodes[4]), "–");
  assert.equal(wrap.dataset.pn, "full", "full names at large");
  applySize(wrap, "small");
  assert.deepEqual([wrap.dataset.size, wrap.dataset.pn], ["small", "initial"], "a plain size: K. Crawford below large");
  applySize(wrap, "medium:abbr/initial");
  assert.deepEqual([wrap.dataset.size, wrap.dataset.names, wrap.dataset.pn], ["medium", "short", "initial"], "a kit step and a name form together");
  applySize(wrap, "small/reduced");
  assert.deepEqual([wrap.dataset.size, wrap.dataset.names, wrap.dataset.pn], ["small", undefined, "reduced"]);
  // beside a label column (not centered): label, then the players outermost
  const side = twoTeamTable({ rows: pairs(), usAbbr: "SWT", themAbbr: "SD", tug: true, labelHead: "#", whoHead: "Passer" });
  const row = side.querySelector("tbody tr");
  const kinds = ["tt__label", "tt__who", "tt__rank", "tt__cell", "tt__tug"];
  assert.deepEqual([...row.childNodes].map((td) => kinds.find((k) => cls(td).split(" ").includes(k))), ["tt__label", "tt__who", "tt__rank", "tt__cell", "tt__tug", "tt__cell", "tt__rank", "tt__who"]);
  assert.deepEqual([...side.querySelectorAll("tr.tt__head--one th")].map(text), ["#", "Passer", "FBS", "SWT", "Edge", "SD", "FBS", "Passer"]);
  // no player anywhere: the table is exactly as before
  const none = twoTeamTable({ rows: [{ label: "Points per game", us: { value: 30 }, them: { value: 20 } }], usAbbr: "SWT", themAbbr: "SD", tug: true });
  assert.equal(none.querySelectorAll(".tt__who").length, 0);
  assert.equal(none.querySelectorAll(".tt__pos").length, 0);
  // wave 3, step 3 (decision 1): the player's position beside him on each side, from medium, mirrored
  const withPos = twoTeamTable({ rows: [{ label: "1", us: { value: 706, rank: 66, of: 186, who: "Keegan Crawford", whoSub: "QB", conf: { rank: 2, of: 14 } }, them: { value: 288, who: "Marcus Hart" } }], usAbbr: "SWT", themAbbr: "SD", usName: "Swampwater Tech Mudpuppies", usTeam: "Swampwater Tech", centered: true, labelHead: "#", usConf: "BB" });
  assert.ok(!RAW.test(text(withPos)), text(withPos));
  assert.deepEqual([...withPos.querySelectorAll("tr.tt__head--a th")].map((th) => th.getAttribute("colspan")), ["5", null, "3"], "player, position, FBS rank, conference rank and value under ours; theirs has no ranks");
  assert.deepEqual([...withPos.querySelectorAll("tr.tt__head--b th")].map(text), ["Player", "Pos", "FBS rank", "BB rank", "", "", "Pos", "Player"]);
  assert.deepEqual([...withPos.querySelectorAll("tr.tt__head--one th")].map((th) => form(th, "short")), ["Player", "Pos", "FBS", "SWT", "#", "SD", "Pos", "Player"]);
  const posRow = [...withPos.querySelector("tbody tr").childNodes];
  assert.deepEqual([text(posRow[1]), text(posRow[7])], ["QB", "–"], "the position, a dash where the side names none");
  assert.ok(cls(posRow[1]).includes("tt__min-medium") && cls(posRow[7]).includes("tt__min-medium") && cls(posRow[1]).includes("tt__pos--us") && cls(posRow[7]).includes("tt__pos--them"), "gone at small");
  assert.ok(cls(withPos.querySelector("tr.tt__head--b th.tt__pos")).includes("tt__min-medium"));
  // junk never throws
  for (const junk of [{ us: { who: 5, whoShort: [], onWho: "x" }, them: { who: {} } }, { us: { who: null }, them: "x" }]) {
    const w = twoTeamTable({ rows: [{ label: "1", ...junk }], centered: true });
    assert.ok(!RAW.test(text(w)), text(w));
  }
};
scenarios.season3 = async () => {
  // wave 3, step 2 (owner 2026-10-10): the Season page's tables (and the team page's shared builders) size themselves
  const { standingsTable, profileTable, teamAbbrLink, formWins } = await import(moduleUrl("ui/team-page.js"));
  const { advancedPaired, resumeBlock } = await import(moduleUrl("ui/depth2.js"));
  const { lastSeasonBlock, roadAheadBlock } = await import(moduleUrl("ui/offday.js"));
  const marks = (ths) => ths.map((th) => (cls(th).includes("st__min-large") ? "L" : cls(th).includes("st__min-medium") ? "M" : ""));
  const heads = (root) => [...root.querySelectorAll("thead th")];
  const cellsOf = (root, i) => [...root.querySelectorAll("tbody tr")[i].querySelectorAll("td")];

  // the standings (Season and every team page): # | Team | conference record | Overall | AP rank | Last 5, teams sort
  const standingRows = [
    { place: 2, team: "Swampwater Tech", abbreviation: "SWT", conference: { wins: 1, losses: 0 }, overall: { wins: 2, losses: 1 }, apRank: null, isUs: true, form: [{ result: "W" }, { result: "L" }] },
    { place: 1, team: "Diner Tech", abbreviation: "DT", logo: "/media/logo/2", conference: { wins: 2, losses: 0 }, overall: { wins: 3, losses: 0 }, apRank: 8, form: [{ result: "W" }, { result: "W" }, { result: "W" }] },
    { place: "x", team: "Silver Dollar", abbreviation: null, conference: null, overall: { wins: "x" }, apRank: "y", form: "junk" },
  ];
  let kept = null;
  const standings = standingsTable(standingRows, { conference: "BB", rowClass: (row) => (row.isUs ? "is-us" : null), onSort: (sort) => { kept = sort; } });
  document.body.append(standings);
  assert.ok(!RAW.test(text(standings)), text(standings));
  assert.equal(standings.dataset.size, "large");
  const sh = heads(standings);
  assert.deepEqual(sh.map((th) => th.dataset.term), ["#", "Team", "BB", "Overall", "AP rank", "Last 5"]);
  assert.deepEqual(marks(sh), ["", "", "", "", "M", "L"], "the AP rank from medium, the last five at large (a 1080p band holds one of them)");
  assert.equal(sh[3].querySelector(".sz-t--short").textContent, "Ovr");
  assert.equal(sh[4].querySelector(".sz-t--mid").textContent, "AP");
  assert.ok(sh.every((th) => th.querySelector("button")), "teams sort");
  let s0 = cellsOf(standings, 0);
  assert.equal(text(s0[0]), "1", "place order to start");
  assert.equal(s0[1].querySelector(".sz-t--long button.team-link").dataset.team, "Diner Tech");
  assert.equal(s0[1].querySelector(".sz-t--short button.team-link").textContent, "DT", "the abbreviation at small, still its link");
  assert.equal(text(s0[2]), "2-0");
  assert.ok(s0[4].querySelector(".poll-badge--link"));
  assert.equal(s0[5].querySelector(".form").getAttribute("aria-label"), "Last 3: W W W");
  const last = cellsOf(standings, 2);
  assert.equal(last[1].querySelector(".sz-t--short button.team-link").textContent, "Silver Dollar", "no abbreviation: the school, still a link");
  assert.deepEqual([text(last[0]), text(last[2]), text(last[3]), text(last[5])], ["–", "–", "–", "–"], "a damaged row: dashes, sorted last");
  sh[5].querySelector("button").click();
  assert.deepEqual(kept, { key: "form", dir: "descending" });
  assert.deepEqual([...standings.querySelectorAll("tbody tr")].map((tr) => tr.querySelectorAll("td")[1].querySelector("button").dataset.team), ["Diner Tech", "Swampwater Tech", "Silver Dollar"], "the last five sort by wins");
  assert.equal(formWins([{ result: "W" }, null, { result: "L" }, { result: "W" }]), 2);
  assert.equal(formWins("x"), 0);
  assert.equal(teamAbbrLink(null, "X"), "–");
  assert.equal(teamAbbrLink("Diner Tech", " ").textContent, "Diner Tech");
  const sorted = standingsTable(standingRows, { sort: { key: "team", dir: "descending" } });
  assert.equal(cellsOf(sorted, 0)[1].querySelector("button").dataset.team, "Swampwater Tech", "a kept order draws first");

  // the stat profile: Statistic | Value | FBS rank (medium) | conference rank (large); the defense says allowed once
  const profile = [
    { side: "offense", label: "Points per game", key: "ppg", metric: "profile:ppg", value: 31.4, format: "1f", nationalRank: 12, nationalOf: 136, conferenceRank: 3, conferenceOf: 16 },
    { side: "defense", label: "Points allowed per game", key: "opp_ppg", value: null, format: "1f", nationalRank: null, nationalOf: 136, conferenceRank: null, conferenceOf: 16 },
  ];
  const off = profileTable(profile, "offense", { team: "Swampwater Tech", conferenceLabel: "BB" });
  const ph = heads(off);
  assert.deepEqual(ph.map((th) => th.dataset.term), ["Statistic", "Value", "FBS rank", "BB rank"]);
  assert.deepEqual(marks(ph), ["", "", "M", "L"]);
  assert.equal(ph[0].querySelector(".sz-t--short").textContent, "Stat");
  const o0 = cellsOf(off, 0);
  assert.equal(o0[0].querySelector(".sz-t--short").textContent, "PPG");
  assert.equal(text(o0[1]), "31.4");
  assert.equal(o0[1].querySelector("[data-k]").getAttribute("data-k"), "v:ppg", "the flash key stays on the value");
  assert.equal(o0[2].querySelector("a.rank-chip--link").getAttribute("href"), "#national=profile%3Appg?team=Swampwater%20Tech");
  assert.equal(o0[3].querySelector("a.rank-chip--link").getAttribute("href"), "#national=profile%3Appg?team=Swampwater%20Tech&scope=conference");
  const def = profileTable(profile, "defense", { team: "Swampwater Tech" });
  assert.equal(heads(def)[0].querySelector(".sz-t--short").textContent, "Def (allowed)");
  assert.equal(heads(def)[3].dataset.term, "Conf rank", "no conference named: Conf");
  const d0 = cellsOf(def, 0);
  assert.deepEqual([text(d0[1]), text(d0[2]), text(d0[3])], ["–", "–", "–"]);
  assert.equal(d0[0].querySelector(".sz-t--short").textContent, "PPG", "the defense's rows repeat the offense's short words");

  // the advanced table: Metric | Offense | FBS rank | conf rank | Defense | FBS rank | conf rank; group rows carry no rank
  const adv = [
    { side: "offense", key: "offense_success_rate", metric: "advanced:offense_success_rate", group: "Overall", value: 0.486, format: "pct", nationalRank: 41, nationalOf: 138, conferenceRank: 5, conferenceOf: 16 },
    { side: "defense", key: "defense_success_rate", metric: "advanced:defense_success_rate", group: "Overall", value: 0.391, format: "pct", nationalRank: 22, nationalOf: 138, conferenceRank: 2, conferenceOf: 16 },
    { side: "offense", key: "offense_passing_downs_ppa", metric: "advanced:offense_passing_downs_ppa", group: "Downs", value: 0.31, format: "2f", nationalRank: 9, nationalOf: 138 },
  ];
  const paired = advancedPaired(adv, { team: "Swampwater Tech", conferenceLabel: "BB" });
  const ah = heads(paired);
  assert.deepEqual(ah.map((th) => th.dataset.term), ["Metric", "Offense", "FBS rank", "BB rank", "Defense", "FBS rank", "BB rank"]);
  assert.deepEqual(marks(ah), ["", "", "M", "L", "", "M", "L"]);
  assert.deepEqual([ah[1].querySelector(".sz-t--short").textContent, ah[4].querySelector(".sz-t--short").textContent], ["Off", "Def"], "the Defense column mixes its own rates: never 'Def (allowed)'");
  const group = cellsOf(paired, 0);
  assert.ok(cls(group[0].parentNode).includes("is-parent") && text(group[0]) === "Overall");
  assert.deepEqual(group.slice(1).map(text), ["", "", "", "", "", ""], "a group row carries no value or rank");
  const success = cellsOf(paired, 1);
  assert.deepEqual([text(success[1]), text(success[4])], ["48.6%", "39.1%"]);
  assert.equal(success[3].querySelector("a").getAttribute("href"), "#national=advanced%3Aoffense_success_rate?team=Swampwater%20Tech&scope=conference");
  const downs = cellsOf(paired, 3);
  assert.equal(downs[0].querySelector(".sz-t--short").textContent, "PPA pass dn");
  assert.deepEqual([text(downs[3]), text(downs[4]), text(downs[5])], ["–", "–", "–"], "one side only: dashes on the other");
  assert.ok(text(paired).includes("FBS rank is the national rank") && !text(paired).includes("Nat is"));
  const noConf = advancedPaired(adv.map((row) => ({ ...row, conferenceRank: null })), { team: "Swampwater Tech" });
  assert.equal(heads(noConf).length, 5, "no conference ranks sent: no conference columns");

  // the résumé: each fact, its value and its FBS rank in a column of its own; the schedule to come a plain chip
  const resume = resumeBlock({ expectedWins: 1.98, gamesCounted: 3, wins: 2, losses: 1, luck: 0.02, sosPlayed: { rating: 12.3, rank: 41, of: 138, metric: "rating:sosPlayed" }, remaining: { averageSp: 15.6, rankAmongPlayed: 9, of: 138 }, polls: [{ week: 4, ap: 18, coaches: null }] }, "Swampwater Tech");
  const [summary, path] = resume.querySelectorAll(".stat-table-wrap");
  const rh = heads(summary);
  assert.deepEqual(rh.map((th) => th.dataset.term), ["Résumé", "Value", "FBS rank"]);
  assert.deepEqual(marks(rh), ["", "", "M"]);
  const rows = [...summary.querySelectorAll("tbody tr")].map((tr) => [...tr.querySelectorAll("td")]);
  assert.deepEqual(rows.map((r) => r[0].querySelector(".sz-t--short")?.textContent ?? text(r[0])), ["Record", "Exp wins", "Above exp", "SOS played", "SOS to come"]);
  assert.deepEqual(rows.map((r) => text(r[1])), ["2-1", "1.98 of 3", "+0.02", "12.3", "15.6"], "no prose in a value");
  assert.equal(rows[3][2].querySelector("a.rank-chip--link").getAttribute("href"), "#national=rating%3AsosPlayed?team=Swampwater%20Tech");
  assert.ok(rows[4][2].querySelector("span.rank-chip") && !rows[4][2].querySelector("a"), "the schedule to come: a plain chip");
  assert.equal(text(rows[0][2]), "–");
  assert.deepEqual(heads(path).map((th) => th.dataset.term), ["Week", "AP rank", "Coaches rank"]);
  assert.equal(heads(path)[0].querySelector(".sz-t--short").textContent, "Wk");
  assert.ok(!heads(path).some((th) => cls(th).includes("st__min")), "the poll path's badges are its values: nothing drops");
  for (const junk of [null, "x", { sosPlayed: "x", remaining: [], polls: {} }]) assert.ok(!RAW.test(text(resumeBlock(junk, "Swampwater Tech"))));

  // this season and last: Statistic | 2026 | FBS | conf | 2025 | FBS | conf | Change
  const lastRows = [
    { side: "offense", label: "Points per game", key: "ppg", metric: "profile:ppg", metricYear: 2025, format: "1f", now: { value: 31.4, rank: 12, of: 136, confRank: 3, confOf: 16 }, last: { value: 24.0, rank: 70, of: 134, confRank: 9, confOf: 16 }, better: true },
    { side: "defense", label: "Points allowed per game", key: "opp_ppg", format: "1f", now: { value: 18.2, rank: 30, of: 136 }, last: { value: 25.0, rank: 80, of: 134 }, better: true },
  ];
  const seasons = lastSeasonBlock(lastRows, 2025, 2026, { team: "Swampwater Tech", conferenceLabel: "BB" });
  const [offLast, defLast] = seasons.querySelectorAll(".stat-table-wrap");
  const lh = heads(offLast);
  assert.deepEqual(lh.map((th) => th.dataset.term), ["Statistic", "2026", "FBS rank", "BB rank", "2025", "FBS rank", "BB rank", "Change"]);
  assert.deepEqual(marks(lh), ["", "", "M", "L", "", "M", "L", ""]);
  const l0 = cellsOf(offLast, 0);
  assert.deepEqual([text(l0[1]), text(l0[4]), text(l0[7])], ["31.4", "24.0", "Better"]);
  assert.equal(l0[1].querySelector("[data-k]").getAttribute("data-k"), "now:ppg");
  assert.equal(l0[5].querySelector("a").getAttribute("href"), "#national=profile%3Appg?team=Swampwater%20Tech&year=2025");
  assert.equal(l0[6].querySelector("a").getAttribute("href"), "#national=profile%3Appg?team=Swampwater%20Tech&year=2025&scope=conference");
  assert.equal(l0[3].querySelector("a").getAttribute("href"), "#national=profile%3Appg?team=Swampwater%20Tech&scope=conference");
  assert.equal(heads(defLast)[0].querySelector(".sz-t--short").textContent, "Def (allowed)");
  assert.equal(text(cellsOf(defLast, 0)[3]), "–");
  assert.ok(text(seasons).includes("rank inside the BB"));

  // the road ahead: Wk | Date | Opponent | Site | Record | AP rank | SP+ | FBS rank | Last three (the standings' squares)
  const sorts = {};
  const logos = new Map([["Diner Tech", { school: "Diner Tech", abbreviation: "DT", logo: "/media/logo/2" }]]);
  const roadRows = [
    { week: 9, date: "2026-10-31T23:30:00.000Z", site: "Away", opponent: "Bayou Tech", record: "2-5", apRank: null, sp: -3.1, spRank: 99, spOf: 136, spMetric: "rating:sp", lastThree: [{ result: "L", score: "7-30", opponent: "Okra Valley", homeAway: "away" }] },
    { week: 8, date: "2026-10-24T23:30:00.000Z", site: "Home", opponent: "Diner Tech", record: "6-1", apRank: 8, sp: 15.2, spRank: 20, spOf: 136, spMetric: "rating:sp", lastThree: [{ result: "W", score: "41-38", opponent: "Louisville", homeAway: "away", points: 41, opponentPoints: 38 }, { result: "W", score: "24-3" }, { result: "?", score: "x" }] },
    { week: "x", date: "nope", site: 7, opponent: null, record: null, lastThree: "x" },
  ];
  const road = roadAheadBlock(roadRows, { logos, sorts });
  const ro = road.querySelector(".stat-table-wrap");
  const oh = heads(ro);
  assert.deepEqual(oh.map((th) => th.dataset.term), ["Wk", "Date", "Opponent", "Site", "Record", "AP rank", "SP+", "FBS rank", "Last three"]);
  assert.deepEqual(marks(oh), ["", "M", "", "", "", "M", "", "M", "M"]);
  const first = cellsOf(ro, 0);
  assert.equal(first[2].querySelector(".sz-t--short").textContent, "Bayou Tech", "the schedule's order to start; no abbreviation: the school");
  const dt = cellsOf(ro, 1);
  assert.equal(dt[2].querySelector(".sz-t--short button.team-link").textContent, "DT");
  assert.ok(dt[2].querySelector(".sz-t--long .tl img"), "the logo at large and medium");
  assert.equal(dt[3].querySelector(".sz-t--short").textContent, "H");
  assert.equal(dt[7].querySelector("a").getAttribute("href"), "#national=rating%3Asp?team=Diner%20Tech");
  const squares = dt[8].querySelector(".form");
  assert.equal(squares.getAttribute("aria-label"), "Last 2: W W");
  assert.equal(squares.querySelector(".form__sq").getAttribute("title"), "Won 41-38 at Louisville");
  assert.ok(!RAW.test(text(road)), text(road));
  oh[1].querySelector("button").click();
  assert.deepEqual(sorts.road, { key: "date", dir: "descending" }, "the reader's order is kept for the next draw");
  assert.equal(cellsOf(ro, 0)[2].querySelector(".sz-t--short").textContent, "Bayou Tech", "the latest date first");
  oh[8].querySelector("button").click();
  assert.equal(cellsOf(ro, 0)[2].querySelector(".sz-t--short button").textContent, "DT", "the last three sort by wins");
  const again = roadAheadBlock(roadRows, { logos, sorts });
  assert.equal(heads(again.querySelector(".stat-table-wrap")).find((th) => th.getAttribute("aria-sort")).dataset.term, "Last three", "the order survives a refresh");
  assert.ok(!RAW.test(text(roadAheadBlock("junk", {}))));
};

scenarios.availability4 = async () => {
  // wave 3, step 4 (owner decision 1): the availability table serves the Injury Report, every team's side sheet and the
  // Pre-Game Program (also In Game and the Archive): Player | Team | Pos | Status | Note
  const { availabilityTable } = await import(moduleUrl("ui/editorial.js"));
  const marks = (ths) => ths.map((th) => (cls(th).includes("st__min-large") ? "L" : cls(th).includes("st__min-medium") ? "M" : ""));
  const heads = (root) => [...root.querySelectorAll("thead th")];
  const rowsOf = (root) => [...root.querySelectorAll("tbody tr")];
  const rows = [
    { name: "Marquis Washington", team: "Diner Tech", position: "WR", status: "Out", note: "Knee, in a boot at practice" },
    { name: "T.J. Oyelaran", team: "Swampwater Tech", position: "OT", status: "Questionable", note: "Ankle" },
    { name: "Leon Abernathy", team: "swampwater tech", position: " ", status: "Game-time decision" },
    { name: "Darius Smithers", team: "Diner Tech", status: "Probable", note: "" },
    { name: "No Status", team: "Diner Tech" },
    null, "junk", [],
  ];
  const teams = [{ school: "Swampwater Tech", abbreviation: "SWT" }, { school: "Diner Tech", abbreviation: "DT" }, null, { school: "Junk", abbreviation: "–" }];
  const node = availabilityTable({ rows, source: "Conference report", updatedAt: "2026-10-09T15:00:00Z", teams });
  document.body.append(node);
  assert.ok(!RAW.test(text(node)), text(node));
  const wrap = node.querySelector(".stat-table-wrap");
  assert.equal(wrap.dataset.size, "large");
  const ah = heads(node);
  assert.deepEqual(ah.map((th) => th.dataset.term), ["Player", "Team", "Pos", "Status", "Note"]);
  assert.deepEqual(marks(ah), ["", "", "M", "", ""], "every row's team is one of the two: the team stays at small as its abbreviation");
  assert.ok(ah.slice(0, 4).every((th) => th.querySelector("button")) && !ah[4].querySelector("button"), "players sort; the note keeps a plain head");
  let r = rowsOf(node);
  assert.equal(r.length, 5, "junk rows are left out, a row with no status is kept");
  const first = [...r[0].querySelectorAll("td")];
  assert.deepEqual(["full", "initial", "last"].map((f) => pnText(first[0], f)), ["Marquis Washington", "M. Washington", "Washington"], "item 6: the name steps down with the table");
  assert.deepEqual([form2(first[1], "long"), form2(first[1], "short")], ["Diner Tech", "DT"]);
  assert.equal(text(first[2]), "WR");
  assert.equal(first[0].querySelector("small"), null, "nothing drawn under the name any more");
  assert.ok(first[3].querySelector(".sz-t--long .avail.avail--out"), "the status's color rides on the status itself");
  assert.ok(cls(first[4]).includes("st__wrap"), "the note is prose that wraps");
  const quest = [...r[1].querySelectorAll("td")][3];
  assert.equal(form2(quest, "short"), "Quest.");
  assert.equal(quest.querySelector(".sz-t--short .avail").getAttribute("title"), "Questionable", "the whole word on hover");
  const gtd = [...r[2].querySelectorAll("td")];
  assert.equal(form2(gtd[1], "short"), "SWT", "the school matches whatever its case");
  assert.equal(text(gtd[2]), "–");
  assert.equal(form2(gtd[3], "short"), "GTD");
  assert.ok(gtd[3].querySelector(".avail--questionable"), "a game-time decision reads like questionable");
  const none = [...r[4].querySelectorAll("td")][3];
  assert.equal(form2(none, "long"), "Not reported");
  assert.equal(none.querySelector(".avail"), null, "no status, no color");
  // the status sorts by how likely the player is to miss (out first on the first tap), and keeps its color through the sort
  ah[3].querySelector("button").click();
  r = rowsOf(node);
  assert.deepEqual(r.map((tr) => pnText(tr.querySelector("td"))), ["Marquis Washington", "T.J. Oyelaran", "Leon Abernathy", "Darius Smithers", "No Status"]);
  heads(node)[0].querySelector("button").click();
  r = rowsOf(node);
  assert.equal(pnText(r[0].querySelector("td")), "Darius Smithers", "A to Z");
  assert.equal(r.filter((tr) => tr.querySelector(".avail--out, .avail--questionable, .avail--probable")).length, 4, "the colors survive a header tap (they once vanished)");
  assert.ok(text(node).includes("Source: Conference report."));
  // one team (the Injury Report, a side sheet): no team column; a team the page does not know: gone at small; nobody named: none
  const one = availabilityTable({ rows: rows.slice(0, 2), showTeam: false });
  assert.deepEqual(heads(one).map((th) => th.dataset.term), ["Player", "Pos", "Status", "Note"]);
  const unknown = availabilityTable({ rows: [{ name: "A B", team: "Lake Effect", status: "Out" }, { name: "C D", team: "Diner Tech", status: "Out" }], teams });
  assert.deepEqual(marks(heads(unknown)), ["", "M", "", ""], "a team with no abbreviation: the column is gone at small, never a long name on a phone");
  const unnamed = availabilityTable({ rows: [{ name: "E F", status: "Doubtful", note: "ankle" }] });
  assert.deepEqual(heads(unnamed).map((th) => th.dataset.term), ["Player", "Status", "Note"], "no team, no position: neither column");
  for (const bad of [null, undefined, "x", 3, [null], [{}], [{ name: NaN, status: {}, team: 5, note: [] }]]) {
    const t = availabilityTable({ rows: bad, teams: bad });
    assert.ok(!RAW.test(text(t)), `${String(bad)}: ${text(t)}`);
  }
};
"""


@needs_node
@pytest.mark.parametrize("scenario", ["forms", "twoteam", "centered", "card", "stat", "tape", "matchups", "lean", "teamstats", "box", "graded", "tendencies", "playvalue", "common", "advbox", "rowteam", "ingame", "ingametwo", "situation", "scoressize", "penaltysize", "wave3kit", "whoplayers", "season3", "availability4"])
def test_tables(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)
