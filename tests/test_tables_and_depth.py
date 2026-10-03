"""Owner requests after the Diner Tech game (2026-09-26): every column of a stats table sorts (tables
whose rows are stat names keep their order), text cells sort by what they mean, ranks start best
first; and the depth chart shows unit columns of position cards with the recruiting rating."""

from __future__ import annotations

import shutil
import subprocess

import pytest

from tests.conftest import PROJECT_ROOT

SCRIPT = """import assert from "node:assert/strict";
const table = await import(process.argv[2]);
const roster = await import(process.argv[3]);

// sort keys
assert.deepEqual(table.sortValue(5), [5, 0]);
assert.deepEqual(table.sortValue("3 of 8"), [0.375, 8]);
assert.deepEqual(table.sortValue("0 of 0"), [-1, 0]);
assert.deepEqual(table.sortValue("10-16"), [10, -16]);
assert.deepEqual(table.sortValue("+0.24"), [0.24, 0]);
assert.deepEqual(table.sortValue("−0.30"), [-0.3, 0]);
assert.deepEqual(table.sortValue("43%"), [43, 0]);
assert.deepEqual(table.sortValue("#12"), [12, 0]);
assert.equal(table.sortValue("Swampwater Tech"), "swampwater tech");
for (const empty of ["–", "-", "", null, undefined, true]) assert.equal(table.sortValue(empty), null, String(empty));

// rows: dashes last in both directions, words after numbers, ties by name
const rows = [{ name: "a", v: "3 of 8" }, { name: "b", v: "–" }, { name: "c", v: "5 of 6" }, { name: "d", v: "0 of 0" }, { name: "e", v: "5 of 6" }];
assert.equal(table.sortRows(rows, { key: "v", kind: "text" }, "descending").map((r) => r.name).join(""), "ceadb");
assert.equal(table.sortRows(rows, { key: "v", kind: "text" }, "ascending").map((r) => r.name).join(""), "daceb");
assert.equal(table.sortRows([{ name: "x", v: 3 }, { name: "y", v: null }, { name: "z", v: 9 }], { key: "v" }, "ascending").map((r) => r.name).join(""), "xzy");

// which tables sort
assert.equal(table.tableSorts([{ key: "label" }]), false);
assert.equal(table.tableSorts([{ key: "option" }]), false);
assert.equal(table.tableSorts([{ key: "name" }, { key: "yds", sortable: false }]), true);
assert.equal(table.tableSorts([{ key: "label" }], true), true);
assert.equal(table.tableSorts([{ key: "name" }], false), false);
assert.equal(table.tableSorts(null), true);

// the first tap
assert.equal(table.firstDirection([{ r: "#6" }, { r: "#20" }], { key: "r", kind: "text" }), "ascending");
assert.equal(table.firstDirection([{ spRank: 4 }], { key: "spRank" }), "ascending");
assert.equal(table.firstDirection([{ yds: 90 }], { key: "yds" }), "descending");
assert.equal(table.firstDirection([{ v: "3 of 8" }], { key: "v", kind: "text" }), "descending");
assert.equal(table.firstDirection([{ n: "Bob" }], { key: "n", kind: "text" }), "ascending");

// the depth chart
assert.equal(roster.ratingScore({ rating: 0.9379 }), 94);
assert.equal(roster.ratingScore({ rating: null }), null);
assert.equal(roster.ratingScore({ rating: 94 }), null);  // not a 0-1 composite
assert.equal(roster.ratingScore(null), null);
assert.equal(roster.ratingTier(94), "top");
assert.equal(roster.ratingTier(85), "good");
assert.equal(roster.ratingTier(79), "fair");
assert.equal(roster.ratingTier(null), "");
const players = ["QB", "RB", "WR", "TE", "OL", "DL", "LB", "CB", "S", "DB", "PK", "P", "LS", "XX", ""].map((position, i) => ({ position, number: i, name: `P${i}` }));
const units = roster.depthUnits([...players, null, "junk"]);
assert.deepEqual(units.map((u) => u.map((c) => c.label).join("+")), ["QB+RB", "WR+TE", "OL", "DL+LB", "CB+S+DB", "K+P+LS+XX+Other"]);
assert.equal(units.flat().reduce((n, c) => n + c.players.length, 0), players.length);
assert.deepEqual(roster.depthUnits([]), []);
console.log("ok");
"""


def test_sorting_and_depth_chart_rules_under_node(tmp_path):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    script = tmp_path / "tables.mjs"
    script.write_text(SCRIPT, encoding="utf-8")
    js = PROJECT_ROOT / "static" / "js"
    result = subprocess.run([node, str(script), (js / "ui" / "stat-table.js").as_uri(), (js / "views" / "roster.js").as_uri()], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    assert result.returncode == 0 and "ok" in result.stdout, result.stderr[-1500:]
