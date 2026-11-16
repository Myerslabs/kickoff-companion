"""Batch 1, speed (owner 2026-11-15, "Every page in ~1.5 s"): the server's side of the faster pages. No network: the feeds
and CFBD are the program tests' fakes."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from tests.conftest import FakeCfbd
from tests.test_program import pclient, program_app, route_program, set_clock, sites  # noqa: F401 - the program tests' app and fakes

ROOT = Path(__file__).resolve().parents[1]


def test_the_headlines_come_without_the_paper(pclient: TestClient, fake_cfbd: FakeCfbd, program_app):  # noqa: F811
    route_program(fake_cfbd)
    paper = pclient.get("/api/newspaper").json()["data"]
    before = len(fake_cfbd.requests)
    light = pclient.get("/api/newspaper/headlines?limit=4").json()["data"]
    assert [h["title"] for h in light["news"]] == [h["title"] for h in paper["news"][:4]], "the paper's own first headlines"
    assert len(fake_cfbd.requests) == before, "no CFBD call: the feeds as kept"
    assert set(light) == {"news", "feeds"} and "edition" not in light and "weeks" not in light
    assert pclient.get("/api/newspaper/headlines?limit=0").status_code == 422
    program = (ROOT / "static" / "js" / "views" / "program.js").read_text(encoding="utf-8")
    assert "fetchPatient(`/api/newspaper/headlines?limit=${HEADLINES_SHOWN}`)" in program and 'fetchPatient("/api/newspaper")' not in program
