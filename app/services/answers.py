"""Reading an AI chat's answer, shared by every prompt the app writes (Phase 17 Part 3: moved out of
notes_paste.py so the game notes, the preseason load and the coaches batches read answers one way).

A chat answers with prose, code fences and a JSON block; the reader finds the JSON, forgives a trailing comma,
and validates it against the prompt's own Pydantic model. A bad row is dropped and counted (the models' DropBad
lists), and a top-level field of the wrong type is left out with a warning instead of refusing the whole answer.

    json_objects(text, score)                 every JSON object in the text, the fenced ones first
    read_json(text, model, score, ...)        -> Parsed(value, raw, problems, warnings, error)
    atomic_write(path, text)                  write through a temporary file, so a crash never leaves half a file
    Template(path, default, placeholders)     a prompt template on disk, editable in the app
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
import tempfile
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from app.cfbd import models as cfbd_models

log = logging.getLogger("kickoff.answers")

FENCE = re.compile(r"```(?:json|JSON)?\s*\n(.*?)```", re.DOTALL)
TRAILING_COMMA = re.compile(r",(\s*[}\]])")


def keys_score(keys: Iterable[str]) -> Callable[[dict[str, Any]], int]:
    """A scorer: how many of the expected top-level keys an object has (0 means it isn't the answer)."""
    wanted = set(keys)
    return lambda obj: len(wanted & set(obj))


def json_objects(text: str, score: Callable[[dict[str, Any]], int]) -> list[dict[str, Any]]:
    """Every JSON object the text holds: inside code fences first, then anywhere a "{" starts one."""
    decoder = json.JSONDecoder()
    found: list[dict[str, Any]] = []
    candidates = [m.group(1) for m in FENCE.finditer(text)] + [text]
    for chunk in candidates:
        for attempt in dict.fromkeys((chunk, TRAILING_COMMA.sub(r"\1", chunk))):
            index = attempt.find("{")
            while index != -1:
                try:
                    value, end = decoder.raw_decode(attempt, index)
                except ValueError:
                    index = attempt.find("{", index + 1)
                    continue
                if isinstance(value, dict):
                    found.append(value)
                index = attempt.find("{", end)
        if any(score(obj) for obj in found):
            return found  # a fenced block that holds the answer wins over the rest of the text
    return found


@dataclass
class Parsed:
    value: Any | None
    raw: dict[str, Any] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


def read_json(text: Any, model: type[BaseModel], score: Callable[[dict[str, Any]], int], *, max_chars: int, what: str, keys_text: str) -> Parsed:
    """The answer validated against `model`. Never raises. `what` names the answer in messages ("notes"), and
    `keys_text` lists the keys an answer must have one of ("sections, availability or sources")."""
    if not isinstance(text, str) or not text.strip():
        return Parsed(None, error="Paste the AI's answer first.")
    if len(text) > max_chars:
        return Parsed(None, error=f"That is {len(text):,} characters; the answer should be far shorter. Paste only the answer.")
    objects = json_objects(text.lstrip("﻿"), score)
    if not objects:
        return Parsed(None, error="No JSON object in the answer. Ask the chat to answer with the JSON block only, then paste it again.")
    raw = dict(max(objects, key=score))
    if score(raw) == 0:
        return Parsed(None, error=f"The JSON in the answer is not {what}: it has none of {keys_text}.")
    problems: list[str] = []
    warnings: list[str] = []
    value = None
    token = cfbd_models._dropped.set(problems)  # bad rows are dropped through the same collector as CFBD's
    try:
        for _ in range(len(raw) + 1):  # a top-level field of the wrong type is left out, never the whole answer
            problems.clear()  # each attempt notes its own dropped rows
            try:
                value = model.model_validate(raw)
                break
            except ValidationError as exc:
                first = exc.errors()[0] if exc.errors() else {}
                key = (first.get("loc") or (None,))[0]
                if not isinstance(key, str) or key not in raw:
                    return Parsed(None, raw, list(problems), warnings, f"The {what} could not be read: {first.get('msg', 'invalid')}.")
                del raw[key]
                warnings.append(f'"{key}" could not be read ({first.get("msg", "invalid")}) and was left out.')
    finally:
        cfbd_models._dropped.reset(token)
    if value is None:
        return Parsed(None, raw, list(problems), warnings, f"The {what} could not be read.")
    if problems:
        n = len(problems)
        warnings.append(f"{n} row{'s' if n != 1 else ''} or block{'s' if n != 1 else ''} could not be read and {'were' if n != 1 else 'was'} left out (first: {problems[0]}).")
    return Parsed(value, raw, list(problems), warnings)


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.stem}-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except OSError:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


class Template:
    """A prompt template: the default in the code, an edited copy on disk when the owner saves one. Placeholders
    are replaced by name only, so a stray brace in an edited prompt is harmless."""

    def __init__(self, path: Path, default: str, placeholders: tuple[str, ...], *, required: str | None = None, max_chars: int = 20_000) -> None:
        self.path = Path(path)
        self.default = default
        self.placeholders = placeholders
        self.required = required  # a placeholder the template must keep (it ties the answer to its batch)
        self.max_chars = max_chars
        self._pattern = re.compile(r"\{(" + "|".join(placeholders) + r")\}")

    def read(self) -> tuple[str, bool]:
        """(template, custom). A missing, empty or unreadable file means the default."""
        if not self.path.is_file():
            return self.default, False
        try:
            text = self.path.read_text(encoding="utf-8-sig")
        except OSError as exc:
            log.warning("Prompt %s is unreadable (%s); the default applies", self.path, exc)
            return self.default, False
        return (text, True) if text.strip() else (self.default, False)

    def write(self, text: str | None) -> None:
        """Save an edit, or remove the file (None, or the default itself) to go back to the default."""
        if text is None or text.strip() == self.default.strip():
            with contextlib.suppress(FileNotFoundError):
                self.path.unlink()
            return
        atomic_write(self.path, text)

    def fill(self, values: dict[str, Any], template: str | None = None) -> str:
        source = template if template is not None else self.read()[0]
        return self._pattern.sub(lambda m: str(values.get(m.group(1), m.group(0))), source)

    def check(self, text: str) -> str | None:
        """Why an edit can't be saved, or None."""
        if not text.strip():
            return "The prompt is empty. Use 'Back to the default' to restore it."
        if len(text) > self.max_chars:
            return f"The prompt is over {self.max_chars:,} characters."
        if self.required and f"{{{self.required}}}" not in text:
            return f"Keep {{{self.required}}} in the prompt: it ties the answer to its batch."
        return None

    def payload(self) -> dict[str, Any]:
        template, custom = self.read()
        return {"template": template, "custom": custom, "default": self.default, "placeholders": list(self.placeholders), "file": str(self.path), "maxChars": self.max_chars}
