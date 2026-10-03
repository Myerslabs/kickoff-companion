"""The server's own name on the home network (public release Phase 4). The server announces
`<MDNS_NAME>.local` (default kickoff.local) with multicast DNS, the way printers and speakers are found,
so a phone or tablet opens https://kickoff.local:8642 without a router DNS record. iPhone, iPad, Mac,
Linux and Windows 10 or later resolve .local names on their own. The name is on the certificate too
(app/tls.py), and the LAN IP always works as the fallback.

It also registers a `_https._tcp` service, so network browsers list the app by name. Before announcing,
it asks the network whether another device already answers to the name; if one does, it announces
nothing and says so (two installs on one network need different MDNS_NAME values).

Everything runs in the background after the server is up: announcing never delays the start, and a
failure (no LAN address, the port in use, a blocked firewall on the asking side) is logged and shown on
the status page. Stopping unregisters, so the name disappears from the network within a second."""

from __future__ import annotations

import asyncio
import logging
import socket
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from app.netinfo import lan_ip

log = logging.getLogger("kickoff.mdns")

SERVICE_TYPE = "_https._tcp.local."
CONFLICT_CHECK_MS = 1500  # how long to listen for another device that already answers to the name
STOP_TIMEOUT = 3.0


def _zeroconf_factory(ip: str) -> Any:
    from zeroconf import IPVersion
    from zeroconf.asyncio import AsyncZeroconf

    return AsyncZeroconf(interfaces=[ip], ip_version=IPVersion.V4Only)


async def _someone_else(zc: Any, host: str, ip: str) -> str | None:
    """The address of another device that answers to host, or None."""
    from zeroconf import AddressResolverIPv4

    resolver = AddressResolverIPv4(f"{host}.")
    if not await resolver.async_request(zc.zeroconf, CONFLICT_CHECK_MS):
        return None
    others = [address for address in resolver.parsed_addresses() if address != ip]
    return others[0] if others else None


class Announcer:
    """Announce `host` (for example kickoff.local) for the LAN IP while the server runs."""

    def __init__(
        self,
        host: str,
        port: int,
        *,
        title: str = "Kickoff Companion",
        ip_provider: Callable[[], str | None] = lan_ip,
        factory: Callable[[str], Any] = _zeroconf_factory,
        conflict_check: Callable[[Any, str, str], Any] = _someone_else,
    ) -> None:
        self.host = host
        self.port = port
        self.title = title
        self._ip_provider = ip_provider
        self._factory = factory
        self._conflict_check = conflict_check
        self._zc: Any = None
        self._info: Any = None
        self._task: asyncio.Task[None] | None = None
        self.state = "off" if not host else "starting"
        self.address: str | None = None
        self.error: str | None = None
        self.since: str | None = None

    def start(self) -> None:
        """Begin announcing in the background (call from inside the running event loop)."""
        if not self.host or self._task is not None:
            return
        self._task = asyncio.get_running_loop().create_task(self._announce(), name="mdns-announce")

    async def _announce(self) -> None:
        ip = self._ip_provider()
        if not ip:
            self._fail("no LAN address found, so there is nothing to announce; use the IP address or LAN_HOSTNAME")
            return
        self.address = ip
        try:
            self._zc = self._factory(ip)
            other = await self._conflict_check(self._zc, self.host, ip)
            if other:
                self.state = "conflict"
                self.error = f"{self.host} already answers from {other}; set a different MDNS_NAME in .env"
                log.warning("Did not announce %s: %s", self.host, self.error)
                await self._close()
                return
            from zeroconf import ServiceInfo

            self._info = ServiceInfo(
                SERVICE_TYPE,
                f"{self.title}.{SERVICE_TYPE}",
                addresses=[socket.inet_aton(ip)],
                port=self.port,
                server=f"{self.host}.",
                properties={"path": "/"},
            )
            await self._zc.async_register_service(self._info, allow_name_change=True)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - announcing is a convenience; the server runs on without it
            self._fail(f"{type(exc).__name__}: {exc}")
            await self._close()
            return
        self.state = "announced"
        self.error = None
        self.since = datetime.now(timezone.utc).isoformat(timespec="seconds")
        log.info("Announced %s for %s on the home network (mDNS)", self.host, ip)

    def _fail(self, message: str) -> None:
        self.state = "failed"
        self.error = message
        log.warning("Could not announce %s on the home network: %s", self.host or "the server", message)

    async def _close(self) -> None:
        zc, self._zc = self._zc, None
        if zc is None:
            return
        try:
            if self._info is not None:
                await asyncio.wait_for(zc.async_unregister_service(self._info), STOP_TIMEOUT)
            await asyncio.wait_for(zc.async_close(), STOP_TIMEOUT)
        except (TimeoutError, OSError, RuntimeError) as exc:
            log.warning("Stopping the %s announcement did not finish cleanly: %s", self.host, exc)
        finally:
            self._info = None

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001 - shutting down
                pass
        await self._close()
        if self.state == "announced":
            self.state = "stopped"

    def status(self) -> dict[str, Any]:
        return {"host": self.host or None, "state": self.state, "address": self.address, "error": self.error, "since": self.since}
