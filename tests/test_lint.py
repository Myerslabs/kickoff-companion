"""Phase 15: the code passes ruff (rules in pyproject.toml). Skipped where ruff is not installed
(it is a development tool: requirements-dev.txt)."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_ruff_is_clean():
    if importlib.util.find_spec("ruff") is None:
        pytest.skip("ruff is not installed (pip install -r requirements-dev.txt)")
    result = subprocess.run([sys.executable, "-m", "ruff", "check", "app", "tools", "tests", "--output-format", "concise"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-1000:]
