"""Claude's prose, not a wall of text (owner 2026-11-07: "I dont want it to be amazing, I just dont want a wall of text"): a long
paragraph splits at a sentence end, a paragraph that is a list draws as bullets, the first sentence of a block is its lead, a
player named in full on the program's lineups is a tap to his card and a coach his page, the notes' sections draw as blocks,
and damaged input never prints a raw value."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fakedom import needs_node, run_scenario

SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object Object\]/;
const text = (node) => (node ? node.textContent : "");
const sentence = (i) => `Sentence number ${i} says a few plain words about the game and its players today.`; // 14 words
const long = Array.from({ length: 12 }, (_, i) => sentence(i + 1)).join(" "); // 168 words

const PROGRAM = {
  us: { school: "Florida" }, them: { school: "Georgia" },
  lineups: {
    us: { team: "Florida", slots: [{ slot: "QB", players: [{ name: "DJ Lagway", playerId: 4432 }, { name: "Aaron Philo", playerId: "4433" }] }, { slot: "RB", players: [{ name: "Jadan Baugh", playerId: null }, "junk"] }] },
    them: { team: "Georgia", slots: [{ slot: "QB", players: [{ name: "Gunner Stockton", playerId: 5001 }] }, "junk"] },
    junk: 4,
  },
  notes: { coaches: { us: { headCoach: "Jon Sumrall", offensiveCoordinator: "Buster Faulkner", defensiveCoordinator: null }, them: { headCoach: "Kirby Smart" } } },
};
const INSIDE = { ...PROGRAM, lineups: undefined, notes: { ...PROGRAM.notes, lineups: PROGRAM.lineups } }; // the program keeps the charts inside the notes block

scenarios.split = async () => {
  const { splitParagraph, asList } = await import(moduleUrl("ui/prose.js"));
  const parts = splitParagraph(long);
  assert.ok(parts.length >= 2 && parts.length <= 3, `split into ${parts.length}`);
  assert.equal(parts.join(" "), long, "nothing lost, nothing doubled");
  assert.ok(parts.every((p) => /[.!?]$/.test(p)), "each part ends at a sentence end");
  assert.ok(parts.every((p) => p.split(/\s+/).length >= 25), "no stub");
  assert.deepEqual(splitParagraph("Short one. And another."), ["Short one. And another."], "a short paragraph stays one");
  const decimals = `ESPN lists an opening spread of Georgia -12.5 and a total of 53.5; its current figures are Georgia -10.5 and 56.5. ${long}`;
  const dparts = splitParagraph(decimals);
  assert.ok(dparts[0].startsWith("ESPN lists an opening spread of Georgia -12.5 and a total of 53.5; its current figures are Georgia -10.5 and 56.5."), dparts[0]);
  assert.equal(dparts.join(" "), decimals);
  assert.deepEqual(splitParagraph("   "), []);
  assert.deepEqual(splitParagraph(42), []);
  const oneLong = Array.from({ length: 120 }, (_, i) => `word${i}`).join(" ");
  assert.deepEqual(splitParagraph(oneLong), [oneLong], "one sentence with no end never splits mid-sentence");
  assert.deepEqual(asList("- Lagway at quarterback\n- Baugh at running back\n- The line against the front"), ["Lagway at quarterback", "Baugh at running back", "The line against the front"]);
  assert.deepEqual(asList("1. First key. 2) Second key."), null, "numbers inside one line are prose");
  assert.deepEqual(asList("1. First key\n2) Second key"), ["First key", "Second key"]);
  assert.deepEqual(asList("Lagway against the Georgia secondary; Baugh against the front seven; the kickers in the wind."), ["Lagway against the Georgia secondary", "Baugh against the front seven", "the kickers in the wind"]);
  assert.equal(asList("One thing; and one more."), null, "two parts are a sentence");
  assert.equal(asList(""), null);
};

scenarios.names = async () => {
  installWindow();
  const { nameIndex, linkNames, prose } = await import(moduleUrl("ui/prose.js"));
  const index = nameIndex(PROGRAM);
  assert.deepEqual(index.names.map((n) => n.name).sort(), ["Aaron Philo", "Buster Faulkner", "DJ Lagway", "Gunner Stockton", "Jon Sumrall", "Kirby Smart"].sort(), "lineup men with a card and both staffs; a man with no id and a null coordinator left out");
  const lagway = index.names.find((n) => n.name === "DJ Lagway");
  assert.equal(lagway.playerId, "4432"); assert.equal(lagway.position, "QB"); assert.equal(lagway.isUs, true); assert.equal(lagway.team, "Florida");
  assert.ok(index.names.find((n) => n.name === "Gunner Stockton").isUs === false);
  const tapped = [];
  const nodes = linkNames("DJ Lagway found Jadan Baugh twice while Kirby Smart watched; Lagway again.", index, (e) => tapped.push(e.name));
  const host = document.createElement("p");
  host.append(...nodes);
  assert.equal(text(host), "DJ Lagway found Jadan Baugh twice while Kirby Smart watched; Lagway again.", "the words unchanged");
  const buttons = host.querySelectorAll("button.prose__name");
  assert.equal(buttons.length, 1, "the full name is a tap; a surname alone (Lagway, Baugh with no id) is not");
  buttons[0].click();
  assert.deepEqual(tapped, ["DJ Lagway"]);
  assert.equal(host.querySelectorAll("a.wiki-link").length, 1, "the coach's name is his page");
  assert.deepEqual(linkNames("No names here.", index, () => {}), ["No names here."]);
  assert.deepEqual(linkNames("DJ Lagway", null, () => {}), ["DJ Lagway"], "no index: plain words");
  assert.deepEqual(linkNames("", index, () => {}), [""]);
  assert.deepEqual(nameIndex(INSIDE).names.map((n) => n.name).sort(), index.names.map((n) => n.name).sort(), "the charts inside the notes block count the same");
  assert.deepEqual(nameIndex(null).names, []);
  assert.equal(nameIndex({ lineups: "junk", notes: 7 }).pattern, null);
  // prose: the lead bold, the list as bullets, the names inside both
  const out = prose(["DJ Lagway starts. Then the rest of the sentence goes on for a while with more words to read.", "- Aaron Philo in relief\n- the line"], { names: index, onName: () => {} });
  const root = document.createElement("div");
  root.append(...out);
  assert.equal(root.querySelectorAll("p.prose__p").length, 1);
  assert.equal(text(root.querySelector("b.prose__lead")), "DJ Lagway starts. ");
  assert.ok(root.querySelector("b.prose__lead button.prose__name"), "a name inside the lead is still a tap");
  assert.equal(root.querySelectorAll("ul.prose__list li").length, 2);
  assert.ok(root.querySelector("ul.prose__list button.prose__name"), "a name inside a bullet too");
  const none = prose(["junk", 4, null], {});
  assert.ok(none.length === 1 && !RAW.test(text(none[0])), "nothing to say draws a dash");
  const dec = prose(["ESPN lists Georgia -12.5 as the line. The rest follows here."], {});
  assert.equal(text(dec[0].querySelector("b.prose__lead")), "ESPN lists Georgia -12.5 as the line. ", "a decimal never ends the lead");
  const noLead = prose(["One. Two three four."], { lead: false });
  assert.equal(noLead[0].querySelector("b"), null);
};

scenarios.rosters = async () => {
  installWindow();
  const { indexFrom, rosterEntries, tapNamesIn, nameIndex, prose } = await import(moduleUrl("ui/prose.js"));
  const roster = { team: { school: "Florida" }, players: [{ playerId: 4432, name: "DJ Lagway", position: "QB" }, { playerId: 7, name: "Jadan Baugh", position: "RB" }, { playerId: null, name: "No Id" }, { name: "Mononym", playerId: 9 }, "junk"] };
  const entries = rosterEntries(roster, true);
  assert.deepEqual(entries.map((e) => e.name), ["DJ Lagway", "Jadan Baugh", "No Id", "Mononym"], "every row; the index decides");
  const index = indexFrom([...nameIndex(PROGRAM).names, ...entries, ...rosterEntries({ players: [{ playerId: 55, name: "Gunner Stockton" }] }, false)]);
  assert.ok(index.names.some((n) => n.name === "Jadan Baugh" && n.playerId === "7" && n.isUs === true && n.team === "Florida"), "the roster gives the man the lineup had no id for");
  assert.ok(!index.names.some((n) => n.name === "No Id" || n.name === "Mononym"), "no id or one word: no tap");
  assert.equal(index.names.filter((n) => n.name === "DJ Lagway").length, 1, "once");
  const root = document.createElement("div");
  root.append(...prose(["Jadan Baugh ran well while DJ Lagway threw; Kirby Smart saw it.", "- Jadan Baugh again\n- the line"], { names: nameIndex(PROGRAM), onName: () => {} }));
  const before = root.querySelectorAll("button.prose__name").length;
  assert.equal(before, 1, "only Lagway tapped from the lineups");
  const tapped = [];
  const made = tapNamesIn(root, index, (e) => tapped.push(e.name));
  assert.equal(made, 2, "Baugh twice from the roster pass");
  assert.equal(root.querySelectorAll("button.prose__name").length, 3);
  assert.equal(root.querySelectorAll("a.wiki-link").length, 1, "the coach stays one link");
  assert.equal(text(root), "Jadan Baugh ran well while DJ Lagway threw; Kirby Smart saw it.Jadan Baugh againthe line", "the words unchanged");
  root.querySelectorAll("button.prose__name")[0].click();
  assert.deepEqual(tapped, ["Jadan Baugh"]);
  assert.equal(tapNamesIn(root, index, () => {}), 0, "a second pass makes nothing twice");
  assert.equal(tapNamesIn(null, index, () => {}), 0);
  assert.equal(tapNamesIn(root, { pattern: null, names: [] }, () => {}), 0);
};

scenarios.blocks = async () => {
  installWindow();
  const { editorial } = await import(moduleUrl("ui/editorial.js"));
  const { nameIndex } = await import(moduleUrl("ui/prose.js"));
  const root = editorial({
    byline: { author: "Claude", writtenAt: "2026-10-27T14:08:00Z" },
    sources: [{ label: "ESPN", url: "https://www.espn.com/x" }, { label: "no link" }, "junk"],
    sections: [
      { heading: "Coaching matchup", paragraphs: [long, "DJ Lagway starts; Aaron Philo waits; Kirby Smart plans."] },
      { heading: "Key matchups", paragraphs: ["- The line against Georgia's front\n- Lagway against the secondary"] },
      { heading: "", paragraphs: ["No head on this one."] },
      { heading: "Empty", paragraphs: [] },
      "junk", null,
    ],
    names: nameIndex(PROGRAM),
    onName: () => {},
  });
  document.body.append(root);
  const t = text(root);
  assert.ok(!RAW.test(t), t);
  const blocks = root.querySelectorAll(".editorial__grid .editorial__block");
  assert.equal(blocks.length, 4, "a block a section, junk dropped");
  assert.equal(text(blocks[0].querySelector(".editorial__head")), "Coaching matchup");
  assert.ok(blocks[0].querySelectorAll("p.prose__p").length >= 2, "the long paragraph split");
  assert.ok(blocks[0].querySelector("b.prose__lead"), "the block's lead");
  assert.equal(blocks[0].querySelectorAll("ul.prose__list li").length, 3, "the semicolon list as bullets");
  assert.equal(blocks[0].querySelectorAll("button.prose__name").length, 2, "Lagway and Philo tap; Smart is a page");
  assert.equal(blocks[1].querySelectorAll("ul.prose__list li").length, 2);
  assert.equal(blocks[2].querySelector(".editorial__head"), null, "no head when the section has none");
  assert.ok(text(blocks[3]).includes("–"), "an empty section says nothing, never a raw value");
  assert.ok(t.includes("Written by Claude") && root.querySelector(".editorial__sources a").getAttribute("href") === "https://www.espn.com/x");
  const bare = editorial({});
  assert.ok(!RAW.test(text(bare)) && !bare.querySelector(".editorial__grid"));
};
"""


@needs_node
@pytest.mark.parametrize("scenario", ["split", "names", "rosters", "blocks"])
def test_prose_in_the_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)
