"""GET /api/health: the one place to see how the server is doing.

Reports the server process, configuration, logging, HTTPS, the CFBD upstream (both breaker
lanes and last calls), the cache, the quota guard, and what the key can do. Makes no upstream call
itself: the status page polls this every 15 seconds.
"""

from __future__ import annotations

import logging
import os
import platform
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Request

from app import APP_NAME, BUILD_PHASE, __version__
from app.api.envelope import envelope
from app.cfbd.client import CfbdClient
from app.cfbd.quota import QuotaMode
from app.config import Settings
from app.logging_setup import LOG_FILE_NAME
from app.netinfo import http_url, lan_ip, machine_name, other_urls, preferred_host, tablet_url
from app.tls import RENEW_BEFORE_DAYS, TlsState

router = APIRouter(tags=["health"])
log = logging.getLogger("kickoff.health")

STATUS_ORDER = {"ok": 0, "degraded": 1, "down": 2}


def format_duration(seconds: float) -> str:
    total = int(max(seconds, 0))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours} h {minutes} min"
    if minutes:
        return f"{minutes} min {secs} s"
    return f"{secs} s"


def _check(name: str, status: str, detail: str) -> dict[str, str]:
    return {"name": name, "status": status, "detail": detail}


def _logging_status(settings: Settings) -> tuple[dict[str, Any], dict[str, Any]]:
    log_file = settings.log_dir / LOG_FILE_NAME
    info: dict[str, Any] = {"file": str(log_file), "level": settings.log_level, "size_bytes": None, "writable": False}
    try:
        info["writable"] = os.access(settings.log_dir, os.W_OK)
        info["size_bytes"] = log_file.stat().st_size if log_file.exists() else 0
    except OSError as exc:
        reason = exc.strerror or str(exc)
        return info, _check("logging", "degraded", f"cannot read {log_file}: {reason}")
    if not info["writable"]:
        return info, _check("logging", "degraded", f"{settings.log_dir} is not writable")
    if not log_file.exists():
        return info, _check("logging", "degraded", f"{log_file} has not been created")
    size_kb = info["size_bytes"] / 1024
    return info, _check("logging", "ok", f"{log_file.name}, {size_kb:.0f} KB, level {settings.log_level}")


def _mdns_check(state: dict[str, Any]) -> dict[str, str]:
    """The announced name (public release Phase 4). A failure is "degraded": the IP still works."""
    host, where = state.get("host"), state.get("address")
    if state.get("state") == "announced":
        return _check("network name", "ok", f"{host} announced for {where}")
    if state.get("state") == "starting":
        return _check("network name", "ok", f"announcing {host}")
    return _check("network name", "degraded", f"{host} not announced: {state.get('error') or state.get('state')}. Devices can use the IP address.")


def _tls_check(tls: TlsState) -> dict[str, str]:
    days = tls.server.days_left()
    ca_days = tls.ca.days_left()
    if days <= 0 or ca_days <= 0:
        return _check("tls", "degraded", "certificate expired; restart the server to renew it")
    if days < RENEW_BEFORE_DAYS or ca_days < RENEW_BEFORE_DAYS:
        return _check("tls", "degraded", f"certificate renewal overdue ({days:.0f} days left)")
    return _check("tls", "ok", f"certificate valid {days:.0f} more days")


# The client's two breaker lanes: (status key, stats lane, name in a sentence, name of its last call,
# whether the lane runs only in game windows). The live lane is idle between games, so a failed last
# call there is news only inside a window or for LIVE_FAILURE_NEWS_SECONDS after it.
LANES = (
    ("breaker", "general", "CFBD", "last CFBD call", False),
    ("live_breaker", "live", "CFBD live calls", "last live CFBD call", True),
)
LIVE_FAILURE_NEWS_SECONDS = 600.0


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _number(value: Any) -> float:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0.0


def _parse_time(value: Any) -> datetime | None:
    """An ISO time from the client's status as a UTC-aware datetime, or None when it is not one."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _failure_is_news(lane_stats: dict[str, Any], now: datetime, live_window: bool) -> bool:
    """A window-only lane's failed last call counts inside the window or while it is recent.
    A failure time that cannot be read is reported rather than hidden."""
    if live_window:
        return True
    failed_at = _parse_time(lane_stats.get("last_failure_at"))
    return failed_at is None or (now - failed_at).total_seconds() <= LIVE_FAILURE_NEWS_SECONDS


def _lane_problem(
    breaker: dict[str, Any], lane_stats: dict[str, Any], label: str, last_call: str, *, report_last_failure: bool = True
) -> str | None:
    """What is wrong with one lane, as a sentence, or None when it looks healthy."""
    if breaker.get("state") == "open":
        return (
            f"{label} paused after {int(_number(breaker.get('consecutive_failures')))} failures in a row; retrying in"
            f" {_number(breaker.get('retry_in_seconds')):.0f} s. Cached data is served meanwhile."
        )
    if breaker.get("probe_stuck") is True:
        return (
            f"{label}: the test call after a pause has been out {format_duration(_number(breaker.get('probe_seconds')))}"
            " and looks stuck; every other call on this lane is refused until it ends."
        )
    if not report_last_failure:
        return None
    last_failure = lane_stats.get("last_failure_at") or ""
    last_success = lane_stats.get("last_success_at") or ""
    if isinstance(last_failure, str) and last_failure and last_failure > str(last_success):
        return f"{last_call} failed: {lane_stats.get('last_error') or 'unknown error'}."
    return None


def _upstream_check(status: dict[str, Any]) -> dict[str, str]:
    """Degraded when a breaker lane is open or its probe is stuck, or a lane's last call failed
    (for the live lane: inside a game window, or within ten minutes of the failure)."""
    stats = _dict(status.get("stats"))
    lanes = _dict(stats.get("lanes"))
    now = _parse_time(status.get("checked_at")) or datetime.now(timezone.utc)
    live_window = status.get("live_window") is True
    problems = []
    for key, lane, label, last_call, window_only in LANES:
        # Without the per-lane breakdown the totals stand in for the general lane.
        lane_stats = _dict(lanes.get(lane)) if lanes else (stats if lane == "general" else {})
        report = not window_only or _failure_is_news(lane_stats, now, live_window)
        problem = _lane_problem(_dict(status.get(key)), lane_stats, label, last_call, report_last_failure=report)
        if problem:
            problems.append(problem)
    if problems:
        return _check("upstream", "degraded", " ".join(problems))
    if not stats.get("last_success_at"):
        return _check("upstream", "ok", "no CFBD calls yet this session")
    live_calls = int(_number(_dict(lanes.get("live")).get("calls")))
    live_part = f", {live_calls} of them live" if live_calls else ""
    return _check("upstream", "ok", f"CFBD answering, {stats.get('session_calls', 0)} calls this session{live_part}")


def _quota_check(quota: dict[str, Any]) -> dict[str, str]:
    mode = quota.get("mode")
    reason = quota.get("reason", "")
    if mode == QuotaMode.EXHAUSTED.value:
        return _check("quota", "down", f"CFBD calls stopped: {reason}")
    if mode == QuotaMode.RESTRICTED.value:
        return _check("quota", "degraded", f"only live-game calls allowed: {reason}")
    if mode == QuotaMode.WARNING.value:
        return _check("quota", "degraded", f"running low: {reason}")
    return _check("quota", "ok", reason)


def _cache_check(stats: dict[str, Any], settings: Settings) -> dict[str, str]:
    if not os.access(settings.data_dir, os.W_OK):
        return _check("cache", "degraded", f"{settings.data_dir} is not writable")
    size_kb = stats.get("db_bytes", 0) / 1024
    return _check("cache", "ok", f"{stats.get('entries', 0)} entries, {stats.get('fresh', 0)} fresh, {size_kb:.0f} KB on disk")


def _live_check(engine: Any) -> dict[str, str]:
    """Phase 12: the live engine on the status page, from memory only (no upstream call)."""
    status = engine.status()
    window = _dict(status.get("window"))
    feed = _dict(status.get("feed"))
    stats = _dict(status.get("stats"))
    mode = status.get("mode")
    if mode == "replay":
        return _check("live", "ok", f"replaying game {status.get('gameId')} (a test; no calls)")
    if not window:
        return _check("live", "ok", "no game window scheduled")
    if not window.get("open"):
        return _check("live", "ok", f"next window opens {window.get('opensAt')}")
    who = f"{status.get('away') or '?'} at {status.get('home') or '?'}"
    polls = int(_number(stats.get("polls")))
    failures = int(_number(stats.get("poll_failures")))
    tally = f"{polls} polls, {failures} failed, {int(_number(stats.get('recorded_files')))} answers recorded"
    state = feed.get("state")
    if state == "stale":
        return _check("live", "degraded", f"{who}: feed stale {int(_number(feed.get('staleSeconds')))} s ({feed.get('lastError') or 'no answer'}); {tally}")
    if state == "no_live_key":
        return _check("live", "degraded", f"{who}: window open but the key has no live plays")
    if state == "waiting":
        waiting = "waiting for a viewer to open the Live sheet" if not status.get("clientsConnected") else "waiting for the first answer"
        return _check("live", "ok", f"{who}: window open, {waiting}; {tally}")
    return _check("live", "ok", f"{who}: feed answering; {tally}")


@router.get("/api/health")
def health(request: Request) -> dict[str, Any]:
    settings: Settings = request.app.state.settings
    started_at: datetime = request.app.state.started_at
    tls: TlsState | None = getattr(request.app.state, "tls", None)
    cfbd: CfbdClient | None = getattr(request.app.state, "cfbd", None)
    now = datetime.now(timezone.utc)
    uptime = (now - started_at).total_seconds()
    ip = lan_ip()
    host = preferred_host(settings, ip)

    config_detail = f"loaded from {settings.env_file_used.name}" if settings.env_file_used else "loaded from environment variables"
    checks: list[dict[str, str]] = [
        _check("server", "ok", f"up {format_duration(uptime)}, pid {os.getpid()}"),
        _check("config", "ok", config_detail),
    ]
    logging_info, logging_check = _logging_status(settings)
    checks.append(logging_check)
    if settings.setup_needed:  # public release Phase 5a: no key or team yet
        checks.append(_check("setup", "degraded", "waiting for setup: open /welcome to add a CFBD key and pick a team"))
    if settings.https and tls is not None:
        checks.append(_tls_check(tls))
    else:  # public release Phase 4b: plain HTTP on the home network is the normal case, not a problem
        detail = "off: plain HTTP on the home network, nothing to install on a device"
        checks.append(_check("tls", "ok", detail + ("; old https:// addresses are sent to http://" if tls is not None else "")))
    mdns = getattr(request.app.state, "mdns", None)
    if mdns is not None and mdns.host:
        checks.append(_mdns_check(mdns.status()))

    upstream: dict[str, Any] | None = None
    cache_stats: dict[str, Any] | None = None
    publications: list[dict[str, Any]] | None = None
    if cfbd is not None:
        upstream = cfbd.status()
        cache_stats = cfbd.cache.stats(now)
        try:
            publications = cfbd.publications.summary(now)
        except Exception:  # noqa: BLE001 - a helper table must not break the health page
            log.exception("Could not read the publication log")
            publications = None
        checks.append(_upstream_check(upstream))
        checks.append(_quota_check(upstream["quota"]))
        checks.append(_cache_check(cache_stats, settings))
    engine = getattr(request.app.state, "live", None)
    engine_status: dict[str, Any] | None = None
    if engine is not None:
        engine_status = engine.status()
        checks.append(_live_check(engine))

    worst = max((STATUS_ORDER.get(check["status"], 1) for check in checks), default=0)
    status = {0: "ok", 1: "degraded", 2: "down"}[worst]
    data = {
        "status": status,
        "app": {"name": APP_NAME, "version": __version__, "phase": BUILD_PHASE},
        "server": {
            "started_at": started_at.isoformat(timespec="seconds").replace("+00:00", "Z"),
            "uptime_seconds": round(uptime, 1),
            "host": settings.host,
            "port": settings.port,
            "hostname": machine_name() or None,
            "lan_ip": ip,
            "tablet_url": tablet_url(settings, ip),
            "other_urls": other_urls(settings, ip),
            "setup_url": f"{http_url(host, settings.port)}/setup",
            "mdns": mdns.status() if mdns is not None else None,
            "python": platform.python_version(),
            "pid": os.getpid(),
        },
        "config": settings.public_summary(),
        "setup_needed": settings.setup_needed,
        "logging": logging_info,
        "tls": tls.summary() if settings.https and tls is not None else {"enabled": False},
        "upstream": (
            {
                "base_url": upstream["base_url"],
                "breaker": upstream["breaker"],
                "live_breaker": upstream["live_breaker"],
                "settle_until": upstream["settle_until"],
                "settling": upstream["settling"],
                "stats": upstream["stats"],
                "ttl_scale": upstream["ttl_scale"],
                "live_window": upstream["live_window"],
            }
            if upstream
            else None
        ),
        "quota": upstream["quota"] if upstream else None,
        "capabilities": upstream["capabilities"] if upstream else None,
        "cache": cache_stats,
        "publications": publications,
        "engine": engine_status,
        "checks": checks,
    }
    return envelope(data)
