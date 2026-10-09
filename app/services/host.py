"""Who runs this server (Phase 18.6, owner 2026-10-08: guests are view-only; host actions happen on the server computer
or, on the owner's own tablet, behind a host PIN).

Until a PIN is set the app behaves as it always has: every device on the home network is the host. Setting a PIN
turns the guests on: from then on a device is a host when it is the server computer itself, or when it carries the host
cookie that /api/host/login hands out for the right PIN. Every other device can look at everything and change nothing.

The PIN is kept as a salted PBKDF2 hash in data/host.json, with a random secret that signs the cookie. A wrong PIN
five times in a row from one address locks that address out for a minute. There are no accounts and nothing here
leaves the machine.

    HostAccess(data_dir)
      .pin_set                 a PIN exists, so guests are view-only
      .set_pin(pin)            4 to 8 digits; replaces the old one and signs every host cookie out
      .clear()                 no PIN again: every device is the host
      .verify(pin, who)        True/False, and LockedOut when the address has failed too often
      .token() / .valid_token(text)   the host cookie's value
"""

from __future__ import annotations

import contextlib
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from pathlib import Path
from typing import Any

from app.services.answers import atomic_write

log = logging.getLogger("kickoff.host")

COOKIE = "kickoff_host"
COOKIE_SECONDS = 365 * 24 * 3600
PIN_DIGITS = (4, 8)
MAX_FAILS = 5
LOCKOUT_SECONDS = 60
LOCKOUT_LONG = 600  # after ten wrong in the window
LOCKOUT_WINDOW = 3600  # wrong guesses count for an hour; after twenty, the wait is the whole hour
ITERATIONS = 120_000


class LockedOut(Exception):
    def __init__(self, seconds: int) -> None:
        super().__init__(f"Too many wrong PINs. Try again in {seconds} seconds.")
        self.seconds = seconds


class PinError(ValueError):
    """A PIN that cannot be used; the message is safe to show."""


def _hash(pin: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, ITERATIONS).hex()


class HostAccess:
    def __init__(self, data_dir: Path, clock: Any = time.monotonic) -> None:
        self.path = Path(data_dir) / "host.json"
        self._clock = clock
        self._fails: dict[str, list[float]] = {}
        self._data = self._read()

    def _read(self) -> dict[str, str]:
        self.damaged = False
        if not self.path.exists():
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            # Final pass: a host file that exists but cannot be read keeps every device a guest (never silently makes
            # everyone the host); the server computer stays the host and can set the PIN again
            log.error("The host file %s cannot be read (%s): every device stays a guest until the PIN is set again from the server computer", self.path, error)
            self.damaged = True
            return {}
        if not isinstance(raw, dict) or not all(isinstance(raw.get(k), str) and raw.get(k) for k in ("salt", "hash", "secret")):
            log.error("The host file %s is not a host record: every device stays a guest until the PIN is set again from the server computer", self.path)
            self.damaged = True
            return {}
        return {k: raw[k] for k in ("salt", "hash", "secret")}

    @property
    def pin_set(self) -> bool:
        return bool(self._data) or getattr(self, "damaged", False)

    def set_pin(self, pin: Any) -> None:
        if not isinstance(pin, str) or not pin.isascii() or not pin.isdigit() or not PIN_DIGITS[0] <= len(pin) <= PIN_DIGITS[1]:
            raise PinError(f"The PIN is {PIN_DIGITS[0]} to {PIN_DIGITS[1]} digits.")
        salt = secrets.token_bytes(16)
        data = {"salt": salt.hex(), "hash": _hash(pin, salt), "secret": secrets.token_hex(32)}  # a new secret signs every old cookie out
        try:
            atomic_write(self.path, json.dumps(data))
        except OSError as exc:
            raise PinError(f"The PIN could not be saved: {exc.strerror or exc}.") from None
        self._data = data
        self._fails.clear()
        log.info("Host PIN set; other devices are now view-only.")

    def clear(self) -> None:
        with contextlib.suppress(OSError):
            os.unlink(self.path)
        self._data = {}
        self._fails.clear()
        log.info("Host PIN cleared; every device is the host again.")

    def locked_for(self, who: str) -> int:
        """Seconds this address must wait: a minute after five wrong PINs in a row, ten minutes after ten, an hour after
        twenty (final pass: a four-digit PIN with a flat minute could be walked through in a day)."""
        now = self._clock()
        recent = [t for t in self._fails.get(who, []) if now - t < LOCKOUT_WINDOW]
        self._fails[who] = recent
        if len(recent) < MAX_FAILS:
            return 0
        lock = LOCKOUT_SECONDS if len(recent) < 2 * MAX_FAILS else LOCKOUT_LONG if len(recent) < 4 * MAX_FAILS else LOCKOUT_WINDOW
        wait = lock - (now - recent[-1])
        return max(1, int(wait) + 1) if wait > 0 else 0

    def verify(self, pin: Any, who: str = "?") -> bool:
        if not self.pin_set:
            return True
        wait = self.locked_for(who)
        if wait:
            raise LockedOut(wait)
        good = bool(self._data) and isinstance(pin, str) and hmac.compare_digest(_hash(pin, bytes.fromhex(self._data["salt"])), self._data["hash"])  # a damaged file matches nothing
        if good:
            self._fails.pop(who, None)
            return True
        self._fails.setdefault(who, []).append(self._clock())
        log.warning("Wrong host PIN from %s (%d in a row).", who, len(self._fails[who]))
        return False

    def token(self) -> str:
        return hmac.new(bytes.fromhex(self._data["secret"]), b"kickoff-host", hashlib.sha256).hexdigest() if self._data else ""

    def valid_token(self, value: Any) -> bool:
        return bool(self._data) and isinstance(value, str) and hmac.compare_digest(value, self.token())
