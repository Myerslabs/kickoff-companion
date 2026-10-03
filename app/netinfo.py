"""Find the address the tablet should use to reach this machine."""

from __future__ import annotations

import socket
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.config import Settings


def lan_ip() -> str | None:
    """The IPv4 address of the interface that carries the default route, or None."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            # A UDP "connect" sends no packets. It only picks the outbound interface.
            probe.connect(("8.8.8.8", 80))
            address = probe.getsockname()[0]
            if address and not address.startswith("127."):
                return address
    except OSError:
        pass
    try:
        address = socket.gethostbyname(socket.gethostname())
        if address and not address.startswith("127."):
            return address
    except OSError:
        pass
    return None


def machine_name() -> str:
    try:
        return socket.gethostname() or ""
    except OSError:
        return ""


def http_url(host: str, port: int, *, secure: bool = False) -> str:
    """A URL for host and port. The scheme's default port (80 or 443) is left out."""
    scheme = "https" if secure else "http"
    default_port = 443 if secure else 80
    return f"{scheme}://{host}" if port == default_port else f"{scheme}://{host}:{port}"


def preferred_host(settings: Settings, ip: str | None) -> str:
    """The name to give a device: LAN_HOSTNAME when the router knows one, else the name the server
    announces itself (kickoff.local), else the LAN IP."""
    return settings.lan_hostname or settings.mdns_host or ip or "localhost"


def tablet_url(settings: Settings, ip: str | None, *, secure: bool | None = None) -> str:
    """The URL to type on the tablet (see preferred_host); https only when HTTPS is on."""
    return http_url(preferred_host(settings, ip), settings.port, secure=settings.https if secure is None else secure)


def other_urls(settings: Settings, ip: str | None, *, secure: bool | None = None) -> list[str]:
    """Every other address that reaches the server, in the same order: the announced name, then the IP."""
    first = preferred_host(settings, ip)
    hosts = [h for h in (settings.lan_hostname, settings.mdns_host, ip) if h and h != first]
    scheme = settings.https if secure is None else secure
    return [http_url(h, settings.port, secure=scheme) for h in dict.fromkeys(hosts)]
