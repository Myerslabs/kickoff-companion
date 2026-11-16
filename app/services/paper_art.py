"""Claude's drawings for the paper (FEAT-14 wave 4, owner 2026-10-27: a related photo first, "including having claude make
one"): a story placed on the front page or as page 2's lead with no photo of its own and none related gets a simple SVG
illustration drawn by Claude Code on the server, up to two a run, two runs a day.

A drawing is other people's markup until proven safe: it is parsed (no DOCTYPE or entities at all), every element and
attribute checked against a short list of plain shapes, colors and transforms, anything that could load or run something
dropped (scripts, event handlers, links, styles, foreign objects, images, outside url() references), and written back out.
The page shows it in an <img>, where a script could not run anyway, and the route serves it with a locked-down
Content-Security-Policy.

  sanitize_svg(text) -> str | None     the cleaned drawing, or None when nothing safe is left (or it is too big)
  ArtStore(data_dir, season)           data/season/<year>/paper/art/<id>.svg and art.json (captions); has(id), save(...)
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from app.services.answers import atomic_write

log = logging.getLogger("kickoff.paper_art")

SVG_NS = "http://www.w3.org/2000/svg"
MAX_SVG_BYTES = 60_000
MAX_ELEMENTS = 600
STORY_ID = re.compile(r"^[0-9a-f]{16}$")
TAGS = {"svg", "g", "path", "rect", "circle", "ellipse", "line", "polyline", "polygon", "defs", "lineargradient", "radialgradient", "stop", "title", "desc"}
ATTRIBUTES = {
    "viewbox", "width", "height", "xmlns", "d", "x", "y", "x1", "y1", "x2", "y2", "cx", "cy", "r", "rx", "ry", "points", "fill", "stroke",
    "stroke-width", "stroke-linecap", "stroke-linejoin", "stroke-dasharray", "opacity", "fill-opacity", "stroke-opacity", "transform",
    "offset", "stop-color", "stop-opacity", "id", "gradientunits", "gradienttransform", "fill-rule", "clip-rule", "fx", "fy", "spreadmethod",
    "preserveaspectratio",
}
LOCAL_URL = re.compile(r"^url\(#[A-Za-z][\w-]{0,40}\)$")
SAFE_VALUE = re.compile(r"^[\w\s#%.,()+\-/:;]*$")  # numbers, colors, path data, transforms; no quotes, angle brackets or backslashes


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower() if isinstance(tag, str) else ""


def sanitize_svg(text: Any) -> str | None:
    """The drawing with only plain shapes left, or None (not SVG, entities, too big, nothing safe in it)."""
    if not isinstance(text, str):
        return None
    raw = text.strip()
    match = re.search(r"<svg\b.*</svg>", raw, re.IGNORECASE | re.DOTALL)
    if match is None:
        return None
    raw = match.group(0)
    if len(raw.encode("utf-8")) > MAX_SVG_BYTES or re.search(r"<!(?:DOCTYPE|ENTITY)|<\?", raw, re.IGNORECASE):
        return None
    try:
        root = ElementTree.fromstring(raw)
    except ElementTree.ParseError:
        return None
    if _local(root.tag) != "svg":
        return None
    count = 0

    def clean(node: ElementTree.Element) -> None:
        nonlocal count
        for child in list(node):
            tag = _local(child.tag)
            if tag not in TAGS or count >= MAX_ELEMENTS:
                node.remove(child)
                continue
            count += 1
            clean(child)
        for name in list(node.attrib):
            key = _local(name)
            value = node.attrib[name]
            ok = key in ATTRIBUTES and isinstance(value, str) and len(value) <= 8000 and SAFE_VALUE.match(value) is not None
            if ok and "url(" in value.lower():
                ok = LOCAL_URL.match(value.strip()) is not None
            if ok and key == "xmlns":
                ok = value == SVG_NS
            if not ok:
                del node.attrib[name]
        node.tag = f"{{{SVG_NS}}}{_local(node.tag)}" if _local(node.tag) in TAGS else node.tag
        if node.text and _local(node.tag) not in ("title", "desc"):
            node.text = None
        for child in node:
            child.tail = None

    clean(root)
    if count == 0:
        return None  # an empty frame is not a drawing
    root.set("viewBox", root.get("viewBox") or "0 0 600 400")
    ElementTree.register_namespace("", SVG_NS)
    return ElementTree.tostring(root, encoding="unicode")


class ArtStore:
    def __init__(self, data_dir: Path, season: int) -> None:
        self.dir = Path(data_dir) / "season" / str(int(season)) / "paper" / "art"
        self._captions: dict[str, str] | None = None

    def _index_path(self) -> Path:
        return self.dir / "art.json"

    def captions(self) -> dict[str, str]:
        if self._captions is None:
            try:
                raw = json.loads(self._index_path().read_text(encoding="utf-8"))
            except FileNotFoundError:
                raw = {}
            except (OSError, ValueError) as exc:
                log.warning("The drawings' captions could not be read: %s", exc)
                raw = {}
            self._captions = {k: v for k, v in raw.items() if isinstance(k, str) and STORY_ID.match(k) and isinstance(v, str)} if isinstance(raw, dict) else {}
        return self._captions

    def path(self, sid: Any) -> Path | None:
        if not isinstance(sid, str) or not STORY_ID.match(sid):
            return None
        path = self.dir / f"{sid}.svg"
        return path if path.is_file() else None

    def has(self, sid: Any) -> dict[str, Any] | None:
        """{src, caption} for a story's drawing, or None."""
        if self.path(sid) is None:
            return None
        return {"src": f"/media/paper-art/{sid}.svg", "caption": self.captions().get(sid)}

    def drawn(self) -> dict[str, dict[str, Any]]:
        try:
            ids = [p.stem for p in self.dir.glob("*.svg") if STORY_ID.match(p.stem)]
        except OSError:
            return {}
        return {sid: {"src": f"/media/paper-art/{sid}.svg", "caption": self.captions().get(sid)} for sid in ids}

    def save(self, sid: Any, svg: Any, caption: Any = None) -> bool:
        """Clean and keep one drawing; False when the story id is bad or nothing safe was left."""
        if not isinstance(sid, str) or not STORY_ID.match(sid):
            return False
        cleaned = sanitize_svg(svg)
        if cleaned is None:
            log.info("Claude's drawing for story %s was refused: nothing safe was left in it", sid)
            return False
        self.dir.mkdir(parents=True, exist_ok=True)
        atomic_write(self.dir / f"{sid}.svg", cleaned)
        captions = dict(self.captions())
        if isinstance(caption, str) and caption.strip():
            captions[sid] = caption.strip()[:200]
        atomic_write(self._index_path(), json.dumps(captions, indent=1, ensure_ascii=False))
        self._captions = captions
        return True
