"""One port, both protocols.

Every device that has trusted the local CA uses https://host:port. A device that has not
yet, or an old http:// bookmark, must still land somewhere useful, so the same port also
answers plain HTTP: the app redirects it to https, except for the certificate setup page.

How: the listening socket is ours. Each accepted connection is peeked at without consuming
any bytes. A TLS ClientHello starts with byte 0x16; anything else is treated as plain HTTP.
The connection is then handed to uvicorn's own HTTP protocol, wrapped in TLS or not.
uvicorn keeps doing everything else: keep-alive, timeouts, graceful shutdown, reload.

The TLS state (certificates and SSL context) comes from the app's lifespan state, so the
server object stays picklable for uvicorn's reload supervisor.
"""

from __future__ import annotations

import asyncio
import logging
import socket
import ssl
import sys
import time
from collections.abc import Callable
from pathlib import Path

import uvicorn
from uvicorn.config import STARTUP_FAILURE

from app import restart
from app import shutdown as shutdown_signal
from app.config import Settings
from app.tls import TlsState

log = logging.getLogger("kickoff.serving")

TLS_HANDSHAKE_BYTE = 0x16
PEEK_BYTES = 8
PEEK_TIMEOUT = 15.0  # seconds a client may stay silent before we drop the connection
PEEK_INTERVAL = 0.02
HANDSHAKE_TIMEOUT = 10.0
HANDSHAKE_WARNING_INTERVAL = 300.0  # seconds between WARNING lines per device address
GRACEFUL_SHUTDOWN_SECONDS = 5
PORT_IN_USE = 4  # exit code when another program (usually a running copy of the app) holds the port

_ALERT_HINTS = {
    "TLSV1_ALERT_UNKNOWN_CA": "the device does not trust the certificate authority yet",
    "SSLV3_ALERT_BAD_CERTIFICATE": "the device rejected the certificate",
    "SSLV3_ALERT_CERTIFICATE_UNKNOWN": "the device rejected the certificate",
    "TLSV1_ALERT_UNKNOWN_CERTIFICATE_AUTHORITY": "the device does not trust the certificate authority yet",
}


def bind_listener(host: str, port: int) -> socket.socket:
    """Bind the listening socket the way uvicorn does, but exclusive on Windows so that a
    second copy of the app fails loudly instead of silently sharing the port."""
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    sock = socket.socket(family, socket.SOCK_STREAM)
    if sys.platform == "win32":
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    else:  # Linux and macOS: reuse after a restart, but a second listener on the port still fails (EADDRINUSE)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    sock.set_inheritable(True)
    return sock


async def peek(conn: socket.socket, timeout: float | None = None) -> bytes:
    """The first bytes a client sends, without consuming them.

    Empty when the client hangs up or stays silent past the timeout.
    """
    limit = PEEK_TIMEOUT if timeout is None else timeout
    conn.setblocking(False)
    loop = asyncio.get_running_loop()
    deadline = loop.time() + limit
    while True:
        try:
            return conn.recv(PEEK_BYTES, socket.MSG_PEEK)
        except (BlockingIOError, InterruptedError):
            if loop.time() >= deadline:
                return b""
            await asyncio.sleep(PEEK_INTERVAL)
        except OSError:
            return b""


class DualProtocolServer(uvicorn.Server):
    """uvicorn's server with our own accept loop that sniffs TLS versus plain HTTP."""

    def __init__(self, config: uvicorn.Config, *, open_url: str | None = None) -> None:
        super().__init__(config)
        self.open_url = open_url  # opened in this computer's browser once the server listens (Phase 4b)
        self.tls: TlsState | None = None
        self.listeners: list[socket.socket] = []
        self.servers: list[asyncio.base_events.Server] = []  # uvicorn's shutdown() iterates this
        self._accept_tasks: list[asyncio.Task[None]] = []
        self._connection_tasks: set[asyncio.Task[None]] = set()
        self._last_handshake_warning: dict[str, float] = {}

    async def on_tick(self, counter: int) -> bool:
        """A restart asked for by the app (setup finished, the team changed) ends the serve loop the
        graceful way; run_server then returns RESTART (public release Phase 5a)."""
        if restart.requested() and not self.should_exit:
            self.should_exit = True
        return await super().on_tick(counter)

    @property
    def bound_ports(self) -> list[int]:
        return [sock.getsockname()[1] for sock in self.listeners]

    def _handshake_failed(self, peer: str, detail: str) -> None:
        """One WARNING per device address every few minutes, INFO in between, so a device
        that has not trusted the CA yet shows up in the log without flooding it."""
        address = peer.rsplit(":", 1)[0]
        now = time.monotonic()
        last = self._last_handshake_warning.get(address)
        message = "TLS handshake with %s did not complete: %s. A new device must open the setup page over http first."
        if last is None or now - last >= HANDSHAKE_WARNING_INTERVAL:
            self._last_handshake_warning[address] = now
            log.warning(message, peer, detail)
        else:
            log.info(message, peer, detail)

    async def startup(self, sockets: list[socket.socket] | None = None) -> None:
        await self.lifespan.startup()
        if self.lifespan.should_exit:
            sys.exit(STARTUP_FAILURE)

        state = getattr(self.lifespan, "state", None)
        self.tls = state.get("tls") if isinstance(state, dict) else None
        https = bool(state.get("https", self.tls is not None)) if isinstance(state, dict) else self.tls is not None

        config = self.config

        def create_protocol(_loop: asyncio.AbstractEventLoop | None = None) -> asyncio.Protocol:
            return config.http_protocol_class(  # type: ignore[call-arg]
                config=config,
                server_state=self.server_state,
                app_state=self.lifespan.state,
                _loop=_loop,
            )

        if sockets is None:
            try:
                self.listeners = [bind_listener(config.host, config.port)]
            except OSError as exc:
                code = cannot_listen(config.host, config.port, exc)
                await self.lifespan.shutdown()
                sys.exit(code)
        else:
            self.listeners = list(sockets)

        loop = asyncio.get_running_loop()
        for sock in self.listeners:
            sock.listen(config.backlog)
            sock.setblocking(False)
            self._accept_tasks.append(loop.create_task(self._accept_loop(sock, create_protocol)))
            host, port = sock.getsockname()[:2]
            if https and self.tls:
                mode = "HTTPS, with plain HTTP redirected"
            elif self.tls:
                mode = "plain HTTP; old https:// links are sent to http://"
            else:
                mode = "plain HTTP"
            log.info("Listening on %s:%s (%s). Press CTRL+C to quit.", host, port, mode)
        self.started = True
        if self.open_url:
            open_in_browser(self.open_url)

    async def shutdown(self, sockets: list[socket.socket] | None = None) -> None:
        shutdown_signal.begin()  # open event streams say goodbye now, inside the graceful timeout
        for task in self._accept_tasks + list(self._connection_tasks):
            task.cancel()
        pending = self._accept_tasks + list(self._connection_tasks)
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        self._accept_tasks.clear()
        self._connection_tasks.clear()
        for sock in self.listeners:
            try:
                sock.close()
            except OSError:
                pass
        await super().shutdown(sockets)

    async def _accept_loop(self, listener: socket.socket, create_protocol: Callable[..., asyncio.Protocol]) -> None:
        loop = asyncio.get_running_loop()
        while True:
            try:
                conn, _ = await loop.sock_accept(listener)
            except asyncio.CancelledError:
                raise
            except OSError as exc:
                log.warning("Accept failed: %s", exc)
                await asyncio.sleep(0.1)
                continue
            task = loop.create_task(self._handle_connection(conn, create_protocol))
            self._connection_tasks.add(task)
            task.add_done_callback(self._connection_tasks.discard)

    async def _handle_connection(self, conn: socket.socket, create_protocol: Callable[..., asyncio.Protocol]) -> None:
        peer = _peer(conn)
        try:
            head = await peek(conn)
        except asyncio.CancelledError:
            _close(conn)
            raise
        if not head:
            _close(conn)
            return

        wants_tls = head[0] == TLS_HANDSHAKE_BYTE
        if wants_tls and self.tls is None:
            log.info("Refused a TLS connection from %s: HTTPS is off (the browser falls back to http://)", peer)
            _close(conn)
            return

        loop = asyncio.get_running_loop()
        try:
            if wants_tls:
                assert self.tls is not None
                await loop.connect_accepted_socket(
                    create_protocol, conn, ssl=self.tls.context, ssl_handshake_timeout=HANDSHAKE_TIMEOUT
                )
            else:
                await loop.connect_accepted_socket(create_protocol, conn)
        except ssl.SSLError as exc:
            self._handshake_failed(peer, _describe_ssl_error(exc))
            _close(conn)
        except asyncio.CancelledError:
            _close(conn)
            raise
        except (TimeoutError, OSError) as exc:
            if wants_tls:
                self._handshake_failed(peer, _describe_error(exc))
            else:
                log.info("Connection from %s dropped before it was ready: %s", peer, _describe_error(exc))
            _close(conn)


def _peer(conn: socket.socket) -> str:
    try:
        host, port = conn.getpeername()[:2]
    except OSError:
        return "unknown"
    return f"{host}:{port}"


def _close(conn: socket.socket) -> None:
    try:
        conn.close()
    except OSError:
        pass


def _describe_ssl_error(exc: ssl.SSLError) -> str:
    reason = str(getattr(exc, "reason", "") or "")
    hint = _ALERT_HINTS.get(reason)
    if hint:
        return f"{hint} ({reason})"
    if isinstance(exc, ssl.SSLEOFError) or reason == "UNEXPECTED_EOF_WHILE_READING":
        return "the device hung up during the handshake, usually because it does not trust the certificate authority yet"
    return reason or _describe_error(exc)


def _describe_error(exc: BaseException) -> str:
    if isinstance(exc, (ConnectionResetError, ConnectionAbortedError, BrokenPipeError)):
        return "the device hung up during the handshake, usually because it does not trust the certificate authority yet"
    if isinstance(exc, asyncio.TimeoutError):
        return f"no handshake within {HANDSHAKE_TIMEOUT:.0f} s"
    text = str(exc).strip()
    name = type(exc).__name__
    return f"{name}: {text}" if text else name


def port_in_use(exc: OSError) -> bool:
    import errno

    return exc.errno in (errno.EADDRINUSE, errno.EACCES) or getattr(exc, "winerror", None) in (10048, 10013)


def cannot_listen(host: str, port: int, exc: OSError) -> int:
    """Log why the port cannot be had; the exit code start.ps1 and start.sh explain."""
    if port_in_use(exc):
        log.error(
            "Port %s is already in use, most often by Kickoff Companion itself still running in another window, the tray "
            "or a login service. Stop that copy first (or set another PORT in .env). Nothing was changed.", port,
        )
        return PORT_IN_USE
    log.error("Cannot listen on %s:%s: %s", host, port, exc.strerror or exc)
    return STARTUP_FAILURE


def open_in_browser(url: str) -> None:
    """Open url in the default browser without holding up the server; a failure is only logged."""
    import threading
    import webbrowser

    def go() -> None:
        try:
            if not webbrowser.open(url, new=2):
                log.info("No browser to open; the app is at %s", url)
        except Exception as exc:  # noqa: BLE001 - a missing browser must never stop the server
            log.info("Could not open the browser (%s); the app is at %s", exc, url)

    threading.Thread(target=go, name="open-browser", daemon=True).start()


RESTART_BIND_SECONDS = 20  # after a restart the old listener may need a moment to let go of the port


def run_server(settings: Settings, *, reload: bool = False, open_url: str | None = None, restarting: bool = False) -> int:
    """Run the app. Returns a process exit code, or restart.RESTART when the app asked to restart."""
    config = uvicorn.Config(
        "app.main:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        log_config=None,
        access_log=True,
        timeout_graceful_shutdown=GRACEFUL_SHUTDOWN_SECONDS,
        reload=reload,
        reload_dirs=[str(Path(__file__).resolve().parent)] if reload else None,
    )
    server = DualProtocolServer(config, open_url=open_url)

    # The port first, before the app is built: a second copy then stops before it opens the database,
    # renames a file or asks CFBD anything (found 2026-10-02).
    deadline = time.monotonic() + (RESTART_BIND_SECONDS if restarting else 0)
    while True:
        try:
            sock = bind_listener(settings.host, settings.port)
            break
        except OSError as exc:
            if time.monotonic() >= deadline or not port_in_use(exc):
                return cannot_listen(settings.host, settings.port, exc)
            time.sleep(0.25)

    if reload:
        from uvicorn.supervisors import ChangeReload

        log.info("Development mode: restarting on changes under app/.")
        ChangeReload(config, target=server.run, sockets=[sock]).run()
        return 0

    restart.reset()
    server.run(sockets=[sock])
    if restart.requested():
        return restart.RESTART
    return 0
