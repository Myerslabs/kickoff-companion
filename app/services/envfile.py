"""Writing values into .env from the app (public release Phase 5a): the CFBD key and the team from the
/welcome page, the team again from Settings.

The file keeps its comments, its order and every other line. A setting already in the file (KEY=...,
commented copies aside) gets its value replaced on that line; a new one is added at the end. A missing
.env starts as a copy of .env.example, so the comments that explain every setting come along. The write
is atomic (a temporary file, then a rename), and nothing here ever logs a value."""

from __future__ import annotations

import logging
import os
import re
import tempfile
from pathlib import Path

from app.config import ENV_EXAMPLE_FILE

log = logging.getLogger("kickoff.envfile")

NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")


class EnvFileError(RuntimeError):
    """The file could not be written. The message names the file, never a value."""


def quote(value: str) -> str:
    """A value as .env needs it: bare when it is plain, in double quotes with escapes otherwise."""
    if value == "" or re.fullmatch(r"[A-Za-z0-9_.:/@&()+,=-]+( [A-Za-z0-9_.:/@&()+,=-]+)*", value):
        return value
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def set_values(path: Path, values: dict[str, str], *, template: Path = ENV_EXAMPLE_FILE) -> None:
    """Write values (NAME -> value) into the .env at path."""
    for name, value in values.items():
        if not NAME_RE.match(name):
            raise ValueError(f"{name!r} is not a setting name")
        if any(ch in value for ch in "\r\n\x00"):
            raise ValueError(f"the value for {name} must be one line")
    if path.is_file():
        text = path.read_text(encoding="utf-8-sig")
    elif template.is_file():
        text = template.read_text(encoding="utf-8-sig")
    else:
        text = ""
    lines = text.splitlines()
    pending = dict(values)
    for i, line in enumerate(lines):
        match = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
        if match and match.group(1).upper() in pending:
            name = match.group(1).upper()
            lines[i] = f"{name}={quote(pending.pop(name))}"
    if pending:
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend(f"{name}={quote(value)}" for name, value in pending.items())
    body = "\n".join(lines) + "\n"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle, temp = tempfile.mkstemp(prefix=".env.", suffix=".tmp", dir=str(path.parent))
        try:
            with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as out:
                out.write(body)
            os.replace(temp, path)
        except BaseException:
            Path(temp).unlink(missing_ok=True)
            raise
    except OSError as exc:
        raise EnvFileError(f"could not write {path}: {exc.strerror or exc}") from None
    log.info("Updated %s in %s", ", ".join(values), path)
