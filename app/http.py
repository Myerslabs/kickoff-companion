"""One TLS context for every HTTPS client the app builds (faster tests, 2026-10-13).

httpx builds a fresh SSL context, reading the whole certificate bundle, for each client that is not handed one: six of
them at every app start, 1.1 s of the 1.2 s a test spends building the app, and the same at a real start. The context
is built once per process and shared; it holds no connection state, so sharing is safe.

    shared_ssl_context() -> ssl.SSLContext
"""

from __future__ import annotations

import ssl
from functools import lru_cache

import httpx


@lru_cache(maxsize=1)
def shared_ssl_context() -> ssl.SSLContext:
    return httpx.create_ssl_context()
