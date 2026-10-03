"""Stat hints and the Glossary (owner request 2026-09-26): the server-side switch, and the shape of
the glossary data every tap and the Glossary page read. The data checks run the real ES module in
node (skipped where node is not installed); no network."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.services.prefs import Prefs

ROOT = Path(__file__).resolve().parents[1]
STATIC_JS = ROOT / "static" / "js"
NODE = shutil.which("node")

DUMP_GLOSSARY = """
import(process.argv[1]).then((m) => {
  process.stdout.write(JSON.stringify({ groups: m.GLOSSARY_GROUPS, entries: m.GLOSSARY }));
}).catch((e) => { console.error(e); process.exit(1); });
"""


def test_hints_are_on_by_default_and_switchable(client: TestClient):
    assert Prefs().hints is True
    assert client.get("/api/settings").json()["data"]["prefs"]["hints"] is True
    saved = client.put("/api/settings", json={"hints": False}).json()
    assert saved["errors"] == [] and saved["data"]["prefs"]["hints"] is False
    assert client.get("/api/settings").json()["data"]["prefs"]["hints"] is False
    refused = client.put("/api/settings", json={"hints": "sometimes"})
    assert refused.status_code == 422


@pytest.fixture(scope="module")
def glossary() -> dict:
    if NODE is None:
        pytest.skip("node is not installed")
    module = (STATIC_JS / "glossary-data.js").resolve().as_uri()
    done = subprocess.run([NODE, "--input-type=module", "-e", DUMP_GLOSSARY, module], capture_output=True, text=True, timeout=30)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def test_every_glossary_entry_is_complete(glossary: dict):
    groups = glossary["groups"]
    entries = glossary["entries"]
    assert isinstance(groups, list) and groups and len(entries) >= 40
    ids = [e["id"] for e in entries]
    assert len(ids) == len(set(ids)), "ids are unique"
    for entry in entries:
        assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", entry["id"]), entry["id"]
        assert entry["group"] in groups, entry["id"]
        assert entry["source"] in ("CFBD", "App"), entry["id"]
        for key in ("term", "text", "read"):
            assert isinstance(entry[key], str) and entry[key].strip(), (entry["id"], key)
        assert "undefined" not in entry["text"] and "NaN" not in entry["text"]
        assert isinstance(entry["aliases"], list) and all(isinstance(a, str) and a.strip() for a in entry["aliases"])


def test_aliases_point_at_one_entry_each(glossary: dict):
    """A label is matched case-insensitively after trimming; two entries claiming one label would make a tap ambiguous."""
    owner: dict[str, str] = {}
    for entry in glossary["entries"]:
        for name in [entry["term"], *entry["aliases"]]:
            key = re.sub(r"\s+", " ", name).strip().rstrip(":.").lower()
            assert owner.get(key, entry["id"]) == entry["id"], f"{name!r} is claimed by {owner.get(key)} and {entry['id']}"
            owner[key] = entry["id"]


def test_the_glossary_never_mentions_betting(glossary: dict):
    words = re.compile(r"\b(bet|bets|betting|sportsbook|odds|wager|spread)\b", re.IGNORECASE)
    for entry in glossary["entries"]:
        assert not words.search(" ".join([entry["term"], entry["text"], entry["read"]])), entry["id"]


def test_hint_class_mappings_name_real_entries(glossary: dict):
    """hints.js maps some elements (the Success / Failed verdict) to an entry by id; those ids must exist."""
    source = (STATIC_JS / "ui" / "hints.js").read_text(encoding="utf-8")
    mapped = re.findall(r'\[\s*"[^"]+"\s*,\s*"([a-z0-9-]+)"\s*\]', source)
    assert mapped, "hints.js maps at least the verdict"
    ids = {e["id"] for e in glossary["entries"]}
    assert set(mapped) <= ids, set(mapped) - ids


def test_the_glossary_is_in_the_menu_and_routed():
    assert '{ id: "glossary", label: "Glossary" }' in (STATIC_JS / "ui" / "shell.js").read_text(encoding="utf-8")
    app = (STATIC_JS / "app.js").read_text(encoding="utf-8")
    assert "glossary: (opts, arg) => createGlossaryView" in app and "enableHints(document.body)" in app
