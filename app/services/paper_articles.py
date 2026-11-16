"""The paper's own article (the season line's Wave 6, second half; owner 2026-11-15: By the numbers on Thursday, "This
sounds good"; "Article replaces the box"): Claude Code writes it from the app's own numbers, never the web, and every
figure in it must be one the data handed to it holds, as it is written there or as its rank, or the article is refused
and nothing prints. A kept article goes in the paper's store as a copied story (so the reader opens it like any other)
and leads page 2 of the week's paper of the coming game.

  KICKERS, SOURCES                       what the paper calls each and the line under its headline
  article_id(kind, key)                  the story id it keeps (16 hex, the same for every run of that week or game)
  numbers_in(text)                       the figures a text writes, in order ("34.9%", "6.9", "129", "7-2" as 7 and 2)
  check(answer, packet)                  None when every figure is the packet's; else the words why it was refused
  keep(store, kind, key, answer)         the article in the paper's store, copied
  row(store, kind, key)                  the paper's row for it (copied, its kicker, `app` True), or None
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timezone
from typing import Any

from app.services.articles import Article

log = logging.getLogger("kickoff.paper")

KINDS = ("numbers",)
KICKERS = {"numbers": "By the numbers"}
SOURCES = {"numbers": "By the numbers · the app's own numbers"}
SMALL = 12  # a count in words ("three keys", "the 4th quarter") needs no source
NUMBER = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?(%?)")


def article_id(kind: str, key: str) -> str:
    return hashlib.sha1(f"app:{kind}:{key}".encode()).hexdigest()[:16]


def numbers_in(text: Any) -> list[str]:
    """The figures a text writes: each run of digits with its decimals and a percent sign; a dash or a colon between
    two (a record, a score, a time) makes two figures."""
    if not isinstance(text, str):
        return []
    return [f"{m.group(1).replace(',', '')}{m.group(2) or ''}{m.group(3)}" for m in NUMBER.finditer(text)]


def _values(packet: Any, out: list[float]) -> list[float]:
    """Every number the packet holds: its numeric fields and the figures written inside its strings."""
    if isinstance(packet, bool):
        return out
    if isinstance(packet, int | float):
        if packet == packet:  # not NaN
            out.append(abs(float(packet)))
    elif isinstance(packet, str):
        out.extend(float(n.rstrip("%")) for n in numbers_in(packet))
    elif isinstance(packet, dict):
        for value in packet.values():
            _values(value, out)
    elif isinstance(packet, list | tuple):
        for value in packet:
            _values(value, out)
    return out


def _matches(figure: str, values: list[float]) -> bool:
    raw = figure.rstrip("%")
    try:
        wanted = float(raw)
    except ValueError:
        return False
    digits = len(raw.split(".")[1]) if "." in raw else 0
    if digits == 0 and wanted <= SMALL:
        return True
    for value in values:
        if round(value, digits) == wanted or (value <= 1 and round(value * 100, digits) == wanted):
            return True
    return False


def check(answer: Any, packet: Any) -> str | None:
    """None when every figure the article writes is one of the packet's (its value as written, rounded to as many
    decimals as the article shows, a rate as a percent, or a rank); else why it was refused, naming the strays."""
    if not isinstance(answer, dict):
        return "the answer is not an article"
    texts = [answer.get("headline"), answer.get("dek"), *(answer.get("paragraphs") or [])]
    values = _values(packet, [])
    strays: list[str] = []
    for text in texts:
        for figure in numbers_in(text):
            if not _matches(figure, values) and figure not in strays:
                strays.append(figure)
    if strays:
        return f"figures not in the app's numbers: {', '.join(strays[:8])}{' and more' if len(strays) > 8 else ''}"
    return None


def keep(store: Any, kind: str, key: str, answer: dict[str, Any]) -> bool:
    """The article in the paper's store as a copied story. True when it changed."""
    paragraphs = [p.strip() for p in [answer.get("dek"), *(answer.get("paragraphs") or [])] if isinstance(p, str) and p.strip()]
    title = answer.get("headline") if isinstance(answer.get("headline"), str) else ""
    if kind not in KINDS or not title.strip() or not paragraphs:
        return False
    sid = article_id(kind, key)
    old = store.get(sid)
    if old is not None and old.title == title.strip() and old.paragraphs == paragraphs:
        return False
    now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    store.put(Article(id=sid, url=None, title=title.strip(), source=SOURCES[kind], publishedAt=now, outcome="copied", author="Claude Code", paragraphs=paragraphs, words=sum(len(p.split()) for p in paragraphs), copiedAt=now))
    log.info("The paper's %s article for %s kept", KICKERS[kind], key)
    return True


def row(store: Any, kind: str, key: Any) -> dict[str, Any] | None:
    """The paper's row for a kept article (copied, its kicker, `app` True), or None."""
    if store is None or kind not in KINDS or not isinstance(key, str) or not key:
        return None
    try:
        article = store.get(article_id(kind, key))
    except Exception:  # noqa: BLE001 - the paper never breaks over its own article; logged
        log.exception("The paper's %s article for %s could not be read", kind, key)
        return None
    if article is None or article.outcome != "copied" or not article.paragraphs:
        return None
    return {
        "id": article.id, "title": article.title, "source": article.source, "publishedAt": article.publishedAt, "url": None,
        "topic": "game", "players": [], "copied": True, "photo": None, "cutline": None, "credit": None, "author": article.author,
        "words": article.words, "opening": article.paragraphs[:3], "kicker": KICKERS[kind], "app": True,
    }
