"""Kickoff Companion 2.0: what the app shows names no real team of its own. The team comes from TEAM in .env and CFBD's
team list (app/services/identity.py, static/js/identity.js). 1.0's test scanned every file; since the test league plays
the real FBS schools with invented games (app/demo/names.py), this one scans what reaches a screen: the page code's
strings outside comments, and the server's string literals outside docstrings, leaving out the test league, the shipped
facts and the styleguide's sample (which follow the test league's team)."""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERN = re.compile(r"\b(?:Florida|Gators?|Gainesville|Napier|Ben Hill Griffin|floridagators)\b|--(?:gator|swamp)\b")
STATIC_SKIP = {"styleguide.js", "sample-data.js", "styleguide.html", "us-states.js"}  # us-states: the state of Florida
APP_SKIP = ("app/demo/", "app/facts/")


def _js_code(line: str) -> str:
    code = re.sub(r"/\*.*?\*/", "", line)
    return re.sub(r"(?<![:\"'])//.*$", "", code)


def test_the_page_code_names_no_team():
    found = []
    for path in sorted((ROOT / "static").rglob("*")):
        if path.suffix not in (".js", ".html", ".css") or path.name in STATIC_SKIP:
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.strip().startswith(("//", "*", "/*", "<!--")):
                continue
            if PATTERN.search(_js_code(line) if path.suffix == ".js" else line):
                found.append(f"{path.relative_to(ROOT)}:{number}: {line.strip()[:120]}")
    assert not found, "\n".join(found)


def _docstrings(tree: ast.AST) -> set[int]:
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                ids.add(id(first.value))
    return ids


def test_the_server_names_no_team():
    found = []
    for path in sorted((ROOT / "app").rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith(APP_SKIP):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        skip = _docstrings(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skip and PATTERN.search(node.value):
                found.append(f"{rel}:{node.lineno}: {node.value[:120]!r}")
    assert not found, "\n".join(found)
