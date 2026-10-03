"""Fetch one endpoint through the real client and print what came back. A debugging tool.

    python -m app.cfbd.fetch /records year=2026 team=Michigan
    python -m app.cfbd.fetch /games year=2026 team=Michigan --no-cache
    python -m app.cfbd.fetch /info

Goes through the quota guard, cache, breaker, and retries exactly like the app. Point
CFBD_BASE_URL at a dead address to watch stale cache being served.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from app.cache import DataKind
from app.cfbd.client import CfbdClient, CfbdError
from app.cfbd.models import ENDPOINTS, ParseResult, normalize_endpoint, parse_endpoint
from app.cfbd.quota import QuotaBlocked
from app.config import SettingsError, load_settings
from app.db import Database, database_path
from app.logging_setup import configure_logging


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cfbd.fetch")
    parser.add_argument("endpoint", help="path such as /records")
    parser.add_argument("params", nargs="*", help="key=value pairs")
    parser.add_argument("--kind", choices=[k.value for k in DataKind], help="cache kind (default: from the endpoint)")
    parser.add_argument("--no-cache", action="store_true", help="bypass the cache for this call")
    parser.add_argument("--live", action="store_true", help="mark the call as a live-game call for the quota guard")
    parser.add_argument("--limit", type=int, default=3, help="records to print")
    args = parser.parse_args(argv)

    try:
        settings = load_settings()
    except SettingsError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    configure_logging(settings, to_file=False)

    params = {}
    for pair in args.params:
        key, _, value = pair.partition("=")
        params[key] = value
    args.endpoint = normalize_endpoint(args.endpoint)
    spec = ENDPOINTS.get(args.endpoint)
    kind = DataKind(args.kind) if args.kind else (spec.kind if spec else DataKind.REFERENCE)

    async def run() -> int:
        db = Database(database_path(settings.data_dir))
        client = CfbdClient(settings, db)
        try:
            fetched = await client.get(args.endpoint, params, kind=kind, live=args.live, use_cache=not args.no_cache)
        except QuotaBlocked as exc:
            print(f"BLOCKED by the quota guard: {exc}")
            return 3
        except CfbdError as exc:
            print(f"FAILED: {exc}")
            return 1
        finally:
            status = client.status()
            await client.aclose()
            db.close()
        print(json.dumps({"meta": fetched.meta, "age_seconds": fetched.age_seconds, "error": fetched.error}, indent=1))
        if spec and spec.model is not None:
            parsed = parse_endpoint(args.endpoint, fetched.payload)
            if isinstance(parsed, ParseResult):
                print(f"parsed {len(parsed.records)} of {parsed.total} records, skipped {parsed.skipped}")
                for record in parsed.records[: args.limit]:
                    print(json.dumps(record.model_dump(), default=str)[:400])
            elif parsed is not None:
                print(json.dumps(parsed.model_dump(), default=str)[:800])
        else:
            print(json.dumps(fetched.payload, default=str)[:800])
        print("quota:", status["quota"]["reason"])
        print("breaker:", status["breaker"])
        return 0

    return asyncio.run(run())


if __name__ == "__main__":
    raise SystemExit(main())
