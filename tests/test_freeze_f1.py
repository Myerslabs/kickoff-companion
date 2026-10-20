"""Freeze wave F1 (2026-10-20): the bug fixes from the freeze plan and the two testers' reports.

- B1: a key the local ledger wrote off (97% used, counting attempts CFBD did not bill) is corrected by the hourly /info
  check; the old order marked the attempt before the call and the guard then refused the call for ever.
- B3: the ledger keeps this month and last; older rows go at the next reconcile.
- The quota's words say whose count they are, and a key CFBD reports as out of calls says so wherever the plan shows.
- B18: the browser's ResizeObserver notice never lands in the log.
- The server window's first and ready lines (a tester closed the window and took a quiet start for a crash)."""

from __future__ import annotations

import asyncio
import logging

from fastapi.testclient import TestClient

from app.api import client_log
from app.cfbd.quota import QuotaMode
from app.cli import console_banner, ready_note, set_console_title
from app.config import load_settings
from app.services import plan
from tests.conftest import TEST_KEY
from tests.test_client import Harness
from tests.test_quota import NOW, burn, guard  # noqa: F401 - the guard fixture


def run(coro):
    return asyncio.run(coro)


# --- B1: the hourly re-check runs in EXHAUSTED mode -----------------------------------------------------------


def test_an_exhausted_ledger_is_corrected_by_the_hourly_info_check(tmp_path):
    harness = Harness(tmp_path, monthly_call_budget=100)
    try:
        for _ in range(97):  # the app's own count, CFBD never asked: 97 of 100
            harness.client.quota.record("/games", None, False, live=False, now=harness.clock())
        assert harness.client.quota.status(harness.clock()).mode is QuotaMode.EXHAUSTED
        harness.clock.advance(hours=1, seconds=1)  # the hourly allowance since the last attempt
        before = harness.upstream.count("/info")
        status = run(harness.client.reconcile())  # never raises, and /info is really asked
        assert harness.upstream.count("/info") == before + 1
        assert status.reconciled is True and status.mode is QuotaMode.NORMAL  # the fake /info says Free, 1,000 left
    finally:
        run(harness.close())


def test_a_refused_info_check_marks_the_attempt_and_waits_an_hour(tmp_path):
    harness = Harness(tmp_path, monthly_call_budget=100)
    try:
        for _ in range(97):
            harness.client.quota.record("/games", None, False, live=False, now=harness.clock())
        harness.clock.advance(minutes=30)  # too soon after the harness's own attempt
        before = harness.upstream.count("/info")
        status = run(harness.client.reconcile())  # refused by the guard: no raise, no call
        assert harness.upstream.count("/info") == before and status.mode is QuotaMode.EXHAUSTED
        harness.clock.advance(hours=1)
        run(harness.client.reconcile())
        assert harness.upstream.count("/info") == before + 1
    finally:
        run(harness.close())


# --- B3 and the words --------------------------------------------------------------------------------------------


def test_reconcile_prunes_ledger_rows_older_than_last_month(guard):  # noqa: F811
    two_months_ago = NOW.replace(month=NOW.month - 2) if NOW.month > 2 else NOW.replace(year=NOW.year - 1, month=NOW.month + 10)
    last_month = NOW.replace(month=NOW.month - 1) if NOW.month > 1 else NOW.replace(year=NOW.year - 1, month=12)
    burn(guard, 3, at=two_months_ago)
    burn(guard, 2, at=last_month)
    burn(guard, 1)
    with guard.db.read() as conn:
        assert conn.execute("SELECT COUNT(*) FROM quota_calls").fetchone()[0] == 6
    guard.reconcile(remaining=990, budget=1000, tier_level=0, tier_name="Free", raw={}, now=NOW)
    with guard.db.read() as conn:
        assert conn.execute("SELECT COUNT(*) FROM quota_calls").fetchone()[0] == 3  # this month and last stay


def test_the_quota_words_say_whose_count_it_is(guard):  # noqa: F811
    burn(guard, 4)
    assert "the app's own count" in guard.status(NOW).reason
    guard.reconcile(remaining=990, budget=1000, tier_level=0, tier_name="Free", raw={"resetAt": "2026-11-01T00:00:00.000Z"}, now=NOW)
    reason = guard.status(NOW).reason
    assert "CFBD's remaining-calls figure" in reason and "resets 2026-11-01" in reason
    status = guard.reconcile(remaining=0, budget=1000, tier_level=0, tier_name="Free", raw={"resetAt": "2026-11-01T00:00:00.000Z"}, now=NOW)
    assert status.mode is QuotaMode.EXHAUSTED
    assert status.reason.startswith("CFBD reports no calls left on this key this month") and "asks again every hour" in status.reason


def test_the_plan_warns_when_cfbd_reports_no_calls_left(tmp_path):
    harness = Harness(tmp_path)
    try:
        assert plan.summary(harness.client)["warning"] is None
        harness.client.quota.reconcile(remaining=0, budget=1000, tier_level=0, tier_name="Free", raw={"resetAt": "2026-11-01T00:00:00.000Z"}, now=harness.clock())
        warning = plan.summary(harness.client)["warning"]
        assert warning.startswith("CFBD says this key has no calls left this month.") and "2026-11-01" in warning
    finally:
        run(harness.close())


# --- B18: browser noise stays out of the log ----------------------------------------------------------------------


def test_the_resize_observer_notice_is_not_logged(client: TestClient, caplog):
    client_log.reset()
    with caplog.at_level(logging.INFO, logger="kickoff.client"):
        answer = client.post("/api/client-log", json={"level": "error", "message": "ResizeObserver loop completed with undelivered notifications."})
    assert answer.json()["data"] == {"logged": False, "reason": "noise"}
    assert not [r for r in caplog.records if "ResizeObserver" in r.getMessage()]


# --- the server window ------------------------------------------------------------------------------------------------


def test_the_window_says_what_it_is_and_when_it_is_ready(tmp_path):
    settings = load_settings(env_file=None, cfbd_api_key=TEST_KEY, team="Alpha", conference="Big Made Up", data_dir=str(tmp_path), log_dir=str(tmp_path / "logs"))
    banner = console_banner(settings, demo=True)
    assert "this window is the server" in banner and "Closing it stops the app" in banner
    assert "builds its league" in banner and "the window is not stuck" in banner
    assert "Log file:" in banner and str(tmp_path / "logs") in banner
    assert "builds its league" not in console_banner(settings, demo=False)
    ready = ready_note(settings, demo=False)
    assert "READY" in ready and f"http://localhost:{settings.port}" in ready and "on a phone or tablet" in ready
    assert "Keep this window open" in ready
    assert "The demo is" in ready_note(settings, demo=True)


def test_the_console_title_is_windows_only():
    assert set_console_title("Kickoff Companion server", system="linux") is False
    assert set_console_title("Kickoff Companion server", system="darwin") is False
