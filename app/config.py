"""Settings loaded from .env and validated at startup.

Rules (docs/02-ARCHITECTURE.md, "Configuration"):
- Every value is validated before the server starts. A bad value stops startup
  with a readable message that names the key and the fix. Never start half-configured.
- Three values may be blank since public release Phase 5a: the CFBD key, TEAM and CONFERENCE.
  Then the server starts in setup mode and the /welcome page collects them in the browser
  (`setup_needed`). A value that is present but malformed still stops startup.
- The CFBD key is a SecretStr. It never appears in repr, logs, or JSON.
"""

from __future__ import annotations

import json
import re
from ipaddress import ip_address
from pathlib import Path
from typing import Annotated, Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, PrivateAttr, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from pydantic_settings import SettingsError as _PydanticSettingsError

from app import APP_NAME

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = PROJECT_ROOT / "static"
DEFAULT_ENV_FILE = PROJECT_ROOT / ".env"
ENV_EXAMPLE_FILE = PROJECT_ROOT / ".env.example"
KEY_URL = "https://collegefootballdata.com/key"

# RFC 1123 host name: labels of letters, digits, and hyphens, joined by dots.
_HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*$",
    re.IGNORECASE,
)


def valid_hostname(value: str) -> bool:
    return bool(_HOSTNAME_RE.match(value))


class RadioSource(BaseModel):
    """One entry in RADIO_SOURCES. 'stream' plays through an audio element with play and pause,
    'embed' loads the station's own player inside the page, 'link' opens a new tab."""

    name: str = Field(min_length=1, max_length=60)
    kind: Literal["embed", "stream", "link"]
    url: str

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must not be blank")
        return value

    @field_validator("url")
    @classmethod
    def _http_url(cls, value: str) -> str:
        value = value.strip()
        if not (value.startswith("http://") or value.startswith("https://")):
            raise ValueError("url must start with http:// or https://")
        return value


# No station is built in (public release Phase 3): each install names its team's own radio in
# RADIO_SOURCES. With none, the radio control says how to add one.
DEFAULT_RADIO_SOURCES: list[RadioSource] = []


class Settings(BaseSettings):
    """All configuration. Field names match the keys in .env (case-insensitive)."""

    model_config = SettingsConfigDict(
        env_file=str(DEFAULT_ENV_FILE),
        env_file_encoding="utf-8-sig",  # tolerate a byte-order mark from Notepad
        case_sensitive=False,
        extra="ignore",
    )

    cfbd_api_key: SecretStr = Field(default=SecretStr(""), validate_default=True)
    cfbd_base_url: str = "https://api.collegefootballdata.com"
    team: str = Field(default="", validate_default=True)  # the school as CFBD spells it; the rest comes from CFBD's team list
    season: int = Field(default_factory=lambda: default_season())
    conference: str = Field(default="", validate_default=True)
    team_feed_url: str = ""  # optional: the school's own athletics news feed (RSS or Atom)
    host: str = "0.0.0.0"
    port: int = 8642
    lan_hostname: str = ""
    https: bool = False  # public release Phase 4b: plain HTTP on the home network, nothing to install on a device
    mdns_name: str = "kickoff"  # announced on the home network as <name>.local; blank or "off" turns it off
    timezone: str = "America/New_York"
    monthly_call_budget: int = 30000
    quota_hard_stop_pct: int = 90
    live_poll_seconds: int = 12
    radio_sources: Annotated[list[RadioSource], NoDecode] = Field(
        default_factory=lambda: list(DEFAULT_RADIO_SOURCES)
    )
    log_level: str = "INFO"
    log_dir: Path = PROJECT_ROOT / "logs"
    data_dir: Path = PROJECT_ROOT / "data"

    _env_file_used: Path | None = PrivateAttr(default=None)
    _env_target: Path | None = PrivateAttr(default=None)

    # --- validators -------------------------------------------------------

    @field_validator("cfbd_api_key")
    @classmethod
    def _key(cls, value: SecretStr) -> SecretStr:
        raw = value.get_secret_value().strip().strip('"').strip("'")
        if not raw:
            return SecretStr("")  # setup mode: the /welcome page asks for it (Phase 5a)
        if any(ch.isspace() for ch in raw):
            raise ValueError("contains whitespace. Paste the key exactly, with no spaces or line breaks")
        if len(raw) < 16:
            raise ValueError("is too short to be a CFBD key. Paste the full key")
        return SecretStr(raw)

    @field_validator("cfbd_base_url")
    @classmethod
    def _base_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        if not (value.startswith("http://") or value.startswith("https://")) or len(value) < 10:
            raise ValueError(f"must be an http(s) URL (got {value!r}); the default is https://api.collegefootballdata.com")
        return value

    @field_validator("team", "conference")
    @classmethod
    def _non_blank(cls, value: str, info: Any) -> str:
        return value.strip()  # blank means setup mode: the /welcome page picks the team and its conference

    @field_validator("team_feed_url")
    @classmethod
    def _feed_url(cls, value: str) -> str:
        value = value.strip()
        if value and not (value.startswith("http://") or value.startswith("https://")):
            raise ValueError(f"must be an http(s) address of an RSS or Atom feed, or blank (got {value!r})")
        return value

    @field_validator("season")
    @classmethod
    def _season(cls, value: int) -> int:
        if not 2000 <= value <= 2100:
            raise ValueError(f"must be a four-digit year between 2000 and 2100 (got {value})")
        return value

    @field_validator("host")
    @classmethod
    def _host(cls, value: str) -> str:
        value = value.strip()
        try:
            ip_address(value)
        except ValueError:
            raise ValueError(f"must be an IP address to listen on, normally 0.0.0.0 (got {value!r})") from None
        return value

    @field_validator("port")
    @classmethod
    def _port(cls, value: int) -> int:
        if not 1 <= value <= 65535:
            raise ValueError(f"must be between 1 and 65535 (got {value})")
        return value

    @field_validator("lan_hostname")
    @classmethod
    def _lan_hostname(cls, value: str) -> str:
        value = value.strip().lower().rstrip(".")
        if value and not _HOSTNAME_RE.match(value):
            raise ValueError(
                f"{value!r} is not a valid host name. Use letters, digits, hyphens, and dots "
                "(example: football.localdomain), or leave it blank"
            )
        return value

    @field_validator("mdns_name")
    @classmethod
    def _mdns_name(cls, value: str) -> str:
        value = value.strip().lower().removesuffix(".local").rstrip(".")
        if value in ("", "off", "none", "no", "false", "0"):
            return ""
        if "." in value or not _HOSTNAME_RE.match(value) or len(value) > 63:
            raise ValueError(f"{value!r} is not a valid network name. Use letters, digits and hyphens (example: kickoff), or off")
        return value

    @property
    def mdns_host(self) -> str:
        """The name announced on the home network ("kickoff.local"), or "" when announcing is off."""
        return f"{self.mdns_name}.local" if self.mdns_name else ""

    @field_validator("timezone")
    @classmethod
    def _timezone(cls, value: str) -> str:
        value = value.strip()
        try:
            ZoneInfo(value)
        except (KeyError, ValueError, OSError):
            raise ValueError(f"{value!r} is not a known IANA time zone (example: America/New_York)") from None
        return value

    @field_validator("monthly_call_budget")
    @classmethod
    def _budget(cls, value: int) -> int:
        if value <= 0:
            raise ValueError(f"must be greater than 0 (got {value})")
        return value

    @field_validator("quota_hard_stop_pct")
    @classmethod
    def _hard_stop(cls, value: int) -> int:
        if not 50 <= value <= 97:
            raise ValueError(f"must be between 50 and 97 percent (got {value})")
        return value

    @field_validator("live_poll_seconds")
    @classmethod
    def _poll(cls, value: int) -> int:
        if value < 8:
            raise ValueError(f"must be at least 8 seconds to protect the CFBD quota (got {value})")
        if value > 120:
            raise ValueError(f"must be 120 seconds or less (got {value})")
        return value

    @field_validator("radio_sources", mode="before")
    @classmethod
    def _radio_sources(cls, value: Any) -> Any:
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return list(DEFAULT_RADIO_SOURCES)
            try:
                value = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    "must be a JSON list on one line, like "
                    '[{"name": "Our station", "kind": "embed", "url": "https://..."}] '
                    f"({exc.msg} at character {exc.pos})"
                ) from None
        if not isinstance(value, list):
            raise ValueError("must be a JSON list of sources")
        return value

    @field_validator("log_level", mode="before")
    @classmethod
    def _log_level(cls, value: Any) -> str:
        level = str(value).strip().upper()
        if level not in {"DEBUG", "INFO", "WARNING", "ERROR"}:
            raise ValueError(f"must be one of DEBUG, INFO, WARNING, ERROR (got {value!r})")
        return level

    @field_validator("log_dir", "data_dir", mode="before")
    @classmethod
    def _anchor_dir(cls, value: Any) -> Path:
        path = Path(str(value).strip()).expanduser()
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return path

    # --- helpers ----------------------------------------------------------

    @property
    def env_file_used(self) -> Path | None:
        return self._env_file_used

    @property
    def api_key_configured(self) -> bool:
        return bool(self.cfbd_api_key.get_secret_value())

    @property
    def setup_needed(self) -> bool:
        """True until the key, the team and its conference are all set (public release Phase 5a)."""
        return not (self.api_key_configured and self.team and self.conference)

    @property
    def env_path(self) -> Path | None:
        """The .env file setup writes to (the one named at load, whether or not it exists yet), or None
        when the settings came from environment variables only, as in tests: then nothing is written."""
        return self._env_target

    @property
    def tzinfo(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    def public_summary(self) -> dict[str, Any]:
        """Configuration safe to show in the UI and logs. Never includes the key."""
        return {
            "team": self.team,
            "season": self.season,
            "conference": self.conference,
            "timezone": self.timezone,
            "host": self.host,
            "port": self.port,
            "lan_hostname": self.lan_hostname or None,
            "mdns_host": self.mdns_host or None,
            "https": self.https,
            "live_poll_seconds": self.live_poll_seconds,
            "monthly_call_budget": self.monthly_call_budget,
            "quota_hard_stop_pct": self.quota_hard_stop_pct,
            "radio_sources": [source.model_dump() for source in self.radio_sources],
            "api_key_configured": self.api_key_configured,
            "cfbd_base_url": self.cfbd_base_url,
            "env_file": str(self._env_file_used) if self._env_file_used else None,
            "log_level": self.log_level,
        }


class SettingsError(RuntimeError):
    """Raised when .env is missing or has bad values. str(exc) is the readable block."""

    def __init__(self, problems: list[tuple[str, str]], env_file: Path | None, env_file_exists: bool):
        self.problems = problems
        self.env_file = env_file
        self.env_file_exists = env_file_exists
        super().__init__(format_problems(problems, env_file, env_file_exists))


def format_problems(problems: list[tuple[str, str]], env_file: Path | None, env_file_exists: bool) -> str:
    width = max((len(key) for key, _ in problems), default=0)
    lines = [f"{APP_NAME} cannot start. Fix these settings:", ""]
    for key, message in problems:
        lines.append(f"  {key:<{width}}  {message}")
    lines.append("")
    if env_file is None:
        lines.append("Settings were read from environment variables only. No .env file was used.")
    elif env_file_exists:
        lines.append(f"Settings file: {env_file}")
    else:
        lines.append(f"No settings file found at {env_file}")
        lines.append(f"Copy {ENV_EXAMPLE_FILE.name} to .env in that folder, then set CFBD_API_KEY.")
    return "\n".join(lines)


_FRIENDLY_TYPES = {
    "int_parsing": "must be a whole number (got {input!r})",
    "int_from_float": "must be a whole number (got {input!r})",
    "int_type": "must be a whole number",
    "string_type": "must be text",
    "missing": "is required",
    "list_type": "must be a JSON list",
    "model_type": "each source must be an object with name, kind, and url",
    "string_too_short": "is too short",
    "string_too_long": "is too long",
}


def _describe(err: dict[str, Any]) -> tuple[str, str]:
    """Turn one pydantic error into (KEY, message). The message never repeats the key
    and never includes the API key value."""
    loc = tuple(err.get("loc") or ())
    key = str(loc[0]).upper() if loc else "SETTINGS"
    where = ""
    if len(loc) > 1:
        parts = [f"item {part + 1}" if isinstance(part, int) else str(part) for part in loc[1:]]
        where = "(" + ", ".join(parts) + ") "
    err_type = str(err.get("type", ""))
    msg = str(err.get("msg", "is invalid"))
    raw_input = err.get("input")
    if key == "CFBD_API_KEY":
        raw_input = "(hidden)"
    if msg.startswith("Value error, "):
        msg = msg[len("Value error, "):]
    elif raw_input == "":
        msg = "is blank"
    elif err_type in _FRIENDLY_TYPES:
        msg = _FRIENDLY_TYPES[err_type].format(input=raw_input)
    return key, f"{where}{msg}"


def load_settings(env_file: Path | str | None = DEFAULT_ENV_FILE, **overrides: Any) -> Settings:
    """Load and validate settings.

    env_file: the .env to read (default: the project root .env). None reads only the
    process environment. Keyword overrides win over both and use field names
    (for example cfbd_api_key="...").

    Raises SettingsError with a readable, secret-free message.
    """
    env_path = Path(env_file) if env_file else None
    env_exists = bool(env_path and env_path.is_file())
    try:
        settings = Settings(_env_file=str(env_path) if env_exists else None, **overrides)
    except ValidationError as exc:
        problems: list[tuple[str, str]] = []
        seen: set[str] = set()
        for err in exc.errors(include_url=False):
            key, message = _describe(err)
            if message not in seen:
                seen.add(message)
                problems.append((key, message))
        raise SettingsError(problems, env_path, env_exists) from None
    except _PydanticSettingsError as exc:
        raise SettingsError([("SETTINGS", f"could not be read: {exc}")], env_path, env_exists) from None
    settings._env_file_used = env_path if env_exists else None
    settings._env_target = env_path
    return settings


def default_season(today: Any = None) -> int:
    """The season to follow when SEASON is not set: this year from March on (the schedule for the
    coming season is out by then), last year in January and February (bowls and the title game)."""
    from datetime import date

    today = today or date.today()
    return today.year if today.month >= 3 else today.year - 1
