"""Penalties in the play text (Phase 17 #21, owner 2026-10-07: "when a penalty is thrown, link the rule").

CFBD sends no penalty field: the foul is written into the play's sentence, in a few shapes seen in the
recordings:

    PENALTY FLA False Start (#52 H.Moore) 5 yards from AUB08 to AUB13. NO PLAY
    PENALTY AUB Pass Interference (#22 A.Jordan Jr.) 11 yard from ...
    PENALTY FLA UNR: Unnecessary Roughness (#25 C.McClain) 15 yards ...
    ... PENALTY Offside declined ...

The team token varies (an abbreviation, "U-M", a mascot), so the parser does not read it: it looks for a
known foul name in the words after each PENALTY, longest name first. The fouls, their plain-words
explanations, rule numbers and rule-book pages live in app/penalties.json (from the 2026 NCAA rules book's
Summary of Penalties); /api/rules/penalties serves it to the Live sheet's penalty panel.

    penalties_in(text)  -> [{key, name, yards, declined, offsetting}]   (empty for no penalty or no text)
    penalty_book()      -> the whole file, or an empty book when it cannot be read
"""

from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

log = logging.getLogger("kickoff.penalties")

PENALTIES_FILE = Path(__file__).resolve().parent.parent / "penalties.json"
# The words after one PENALTY, up to the next PENALTY or the end of the text.
SEGMENT = re.compile(r"\bpenalty\b(.*?)(?=\bpenalty\b|$)", re.IGNORECASE | re.DOTALL)
YARDS = re.compile(r"\b(\d{1,2})\s*(?:-\s*)?yards?\b", re.IGNORECASE)
MAX_TEXT = 2000  # a play sentence is short; anything longer is cut before matching


def _normal(words: str) -> str:
    """Lower case, hyphens and slashes as spaces, single spaces: "Face-Mask" and "face mask" match."""
    return " ".join(re.sub(r"[-/]", " ", words.lower()).split())


@lru_cache(maxsize=1)
def penalty_book() -> dict[str, Any]:
    """The penalty file. A missing or unreadable file is an empty book, logged once; a bad entry is dropped."""
    empty: dict[str, Any] = {"source": None, "penalties": []}
    try:
        raw = json.loads(PENALTIES_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        log.warning("The penalty list %s could not be read: %s", PENALTIES_FILE.name, exc)
        return empty
    if not isinstance(raw, dict) or not isinstance(raw.get("penalties"), list):
        log.warning("The penalty list %s has no penalties list", PENALTIES_FILE.name)
        return empty
    good = []
    for entry in raw["penalties"]:
        if isinstance(entry, dict) and isinstance(entry.get("key"), str) and isinstance(entry.get("name"), str) and isinstance(entry.get("aliases"), list):
            good.append(entry)
        else:
            log.warning("Skipped a bad entry in the penalty list: %r", entry if not isinstance(entry, dict) else entry.get("key"))
    return {"source": raw.get("source") if isinstance(raw.get("source"), dict) else None, "penalties": good}


@lru_cache(maxsize=1)
def _aliases() -> list[tuple[str, dict[str, Any]]]:
    """(normalised alias, entry), longest first, so "roughing the kicker" wins over "roughing"."""
    pairs = [(_normal(alias), entry) for entry in penalty_book()["penalties"] for alias in entry["aliases"] if isinstance(alias, str) and alias.strip()]
    return sorted(pairs, key=lambda pair: len(pair[0]), reverse=True)


def penalties_in(text: Any) -> list[dict[str, Any]]:
    """Every known foul named after a PENALTY in the play text, in order, at most one per PENALTY. A
    foul the book doesn't know is left out (the play text still names it)."""
    if not isinstance(text, str) or "penalty" not in text.lower():
        return []
    found: list[dict[str, Any]] = []
    for match in SEGMENT.finditer(text[:MAX_TEXT]):
        segment = match.group(1)
        words = f" {_normal(segment)} "
        hit = next(((alias, entry) for alias, entry in _aliases() if f" {alias} " in words), None)
        if hit is None:
            continue
        alias, entry = hit
        after = words.split(f" {alias} ", 1)[1]
        yards = YARDS.search(after)
        found.append({
            "key": entry["key"],
            "name": entry["name"],
            "yards": int(yards.group(1)) if yards else None,
            "declined": "declined" in words,
            "offsetting": "offsetting" in words or "off setting" in words,
        })
    return found
