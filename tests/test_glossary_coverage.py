"""Phase 17 #20: every statistic, rule and term the app shows has an explanation. Two checks keep it so:
this test reads every column header written in the front end and fails on any that is neither a glossary
term or alias nor a plain word a new fan already knows (PLAIN_LABELS in tools/page_check.py); and
tools/page_check.py --labels does the same for every label on the rendered pages, player cards included.

A new stat needs an entry (or an alias on an existing one) in static/js/glossary-data.js; a new plain
header (a name, a date) goes in PLAIN_LABELS. Runs the real glossary module in node (skipped without node)."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tools.page_check import PLAIN_LABELS

ROOT = Path(__file__).resolve().parents[1]
STATIC_JS = ROOT / "static" / "js"
NODE = shutil.which("node")

DUMP = """
import(process.argv[1]).then((m) => {
  process.stdout.write(JSON.stringify(m.GLOSSARY.map((e) => [e.term, ...(e.aliases || [])])));
}).catch((e) => { console.error(e); process.exit(1); });
"""

PLAIN = PLAIN_LABELS  # one list, shared with tools/page_check.py --labels

COLUMN = re.compile(r'\{ key: "[^"]+", label: "([^"]+)"')
TEMPLATED = re.compile(r"\$\{")


def normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().rstrip(":.").lower()


@pytest.fixture(scope="module")
def known() -> set[str]:
    if NODE is None:
        pytest.skip("node is not installed")
    module = (STATIC_JS / "glossary-data.js").resolve().as_uri()
    done = subprocess.run([NODE, "--input-type=module", "-e", DUMP, module], capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert done.returncode == 0, done.stderr
    return {normalize(name) for names in json.loads(done.stdout) for name in names if isinstance(name, str)}


def front_end_headers() -> dict[str, str]:
    """Every literal column header in the views and components: {label: file}."""
    found: dict[str, str] = {}
    for path in STATIC_JS.rglob("*.js"):
        if path.name in {"styleguide.js", "glossary-data.js"}:
            continue
        for label in COLUMN.findall(path.read_text(encoding="utf-8")):
            if not TEMPLATED.search(label):
                found.setdefault(label, path.relative_to(ROOT).as_posix())
    return found


def test_every_column_header_is_explained_or_plain(known: set[str]):
    missing = {label: where for label, where in front_end_headers().items() if normalize(label) not in known and normalize(label) not in PLAIN}
    assert not missing, "headers with no glossary entry (add one, or an alias, in static/js/glossary-data.js): " + "; ".join(f"{k!r} in {v}" for k, v in sorted(missing.items()))


def test_the_check_reads_real_headers():
    headers = front_end_headers()
    assert len(headers) > 60 and "Pos. rank" in headers and "Player" in headers
