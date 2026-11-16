"""BUG-19: a cancelled read's cache write still lands on its thread. The client keeps it until it does, so the shutdown
and a test's clean slate can wait for it (the newspaper's bye-Saturday test failed now and then in parallel runs)."""

from __future__ import annotations

import asyncio
import threading
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_settle_writes_waits_for_the_write_of_a_cancelled_read(app: FastAPI, client: TestClient):
    cfbd = app.state.cfbd
    landed: list[str] = []
    started = threading.Event()

    def slow_put(value: str) -> None:
        started.set()
        time.sleep(0.2)
        landed.append(value)

    async def scenario() -> list[str]:
        reader = asyncio.ensure_future(cfbd._write(slow_put, "schedule"))
        while not started.is_set():
            await asyncio.sleep(0.005)
        reader.cancel()  # the live engine stopping mid-read
        await asyncio.gather(reader, return_exceptions=True)
        before = list(landed)
        await cfbd.settle_writes()
        return before

    before = client.portal.call(scenario)
    assert before == [] and landed == ["schedule"] and not cfbd._writes
