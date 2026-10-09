"""Download with a ceiling (Phase 18.1, review item S10). `client.get` reads a whole answer into memory before any size
check can run, so a server that sends gigabytes could fill it. `get_capped` streams the answer and stops at the
ceiling: the size is judged while it arrives, not after.

    await get_capped(client, url, max_bytes) -> httpx.Response     (same object shape the callers already read)
    ResponseTooLarge                                                (an httpx.TransportError, so the callers'
                                                                    existing `except httpx.HTTPError` handles it)
"""

from __future__ import annotations

import httpx


class ResponseTooLarge(httpx.TransportError):
    """The answer is larger than the caller allows."""


async def get_capped(client: httpx.AsyncClient, url: str, max_bytes: int, **kwargs: object) -> httpx.Response:
    async with client.stream("GET", url, **kwargs) as response:  # type: ignore[arg-type]
        declared = response.headers.get("content-length")
        if declared is not None and declared.isdigit() and int(declared) > max_bytes:
            raise ResponseTooLarge(f"answer declares {declared} bytes; the limit is {max_bytes}", request=response.request)
        chunks: list[bytes] = []
        total = 0
        async for chunk in response.aiter_bytes():  # decoded, so a compressed bomb is counted at its real size
            total += len(chunk)
            if total > max_bytes:
                raise ResponseTooLarge(f"answer passed {max_bytes} bytes", request=response.request)
            chunks.append(chunk)
        headers = [(k, v) for k, v in response.headers.multi_items() if k.lower() not in ("content-encoding", "content-length", "transfer-encoding")]
    return httpx.Response(response.status_code, headers=headers, content=b"".join(chunks), request=response.request)
