"""The betting line as the app prints it: the spread and the over/under, never a book or a moneyline.

  spread_text(formatted, spread)       "Saddle Sore -3.5", or "Pick'em" for a spread of zero (owner 2026-10-13: the
                                       mock printed CFBD's own "Front Porch State -0"); None when there is no spread
  short_spread(text, abbreviations)    the same with the favorite's abbreviation ("SADL -3.5") for a compact card
  line_block(line, abbreviations)      {spread, formatted, short, overUnder, pickem} from a CFBD GameLine, or None
"""

from __future__ import annotations

import re
from typing import Any

PICKEM = "Pick'em"
_ZERO = re.compile(r"(?:^|\s)[-+]?0(?:\.0+)?$")


def _num(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def spread_text(formatted: Any, spread: Any) -> str | None:
    """The favorite and the points, or "Pick'em" when neither team is favored."""
    if _num(spread) == 0:
        return PICKEM
    text = formatted.strip() if isinstance(formatted, str) else ""
    if text and _ZERO.search(text):
        return PICKEM
    return text or None


def short_spread(text: Any, abbreviations: dict[str, str] | None) -> str | None:
    """'SADL -3.5' for 'Saddle Sore -3.5': the longest school the line starts with, by its abbreviation."""
    if not isinstance(text, str) or not text:
        return None
    if text == PICKEM or not abbreviations:
        return text
    for school in sorted(abbreviations, key=len, reverse=True):
        short = abbreviations.get(school)
        if school and isinstance(short, str) and short.strip() and text.startswith(school + " "):
            return f"{short.strip()}{text[len(school):]}"
    return text


def line_block(line: Any, abbreviations: dict[str, str] | None = None) -> dict[str, Any] | None:
    """The line for a card: None without a spread or an over/under."""
    if line is None:
        return None
    spread = _num(getattr(line, "spread", None))
    total = _num(getattr(line, "over_under", None))
    text = spread_text(getattr(line, "formatted_spread", None), spread)
    if text is None and total is None:
        return None
    return {"spread": spread, "formatted": text, "short": short_spread(text, abbreviations), "overUnder": total, "pickem": text == PICKEM}
