"""The live engine (Phase 6): poller, event store, delay buffer, stream, replay, raw recorder.

Poller --> normalize + dedupe --> event store (SQLite, timestamped) --> delay buffer --> SSE --> browser

Every panel on the live sheet derives from released events, so nothing leaks a spoiler.
"""
