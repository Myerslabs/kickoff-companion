"""The Newspaper's whole stories (FEAT-14, owner 2026-10-27): each story the server can read is copied once, word for
word, with its lead photo, onto this computer, so the paper and its reader never reach another site.

No Claude does this. trafilatura reads the publisher's page into a tree and keeps the article's own text; each site's
leftovers come off afterwards (the team site's leading caption becomes the cutline, bylines, dates, share buttons,
ticket notices and photo credits go). The app names itself honestly, asks each site's robots.txt first, fetches a
page once, and takes a refusal as final for that story: USA Today's 402, ESPN's bot wall, a paywall or a robots.txt
no keep the story headline only, and nothing tries around them. Google News links are never followed (they cannot
be resolved to the article). Three failures in a row from one site pause it for six hours; a site that refused is
not asked again for a week.

  data/season/<year>/paper/articles/<id>.json   one story: what was copied, or why it stayed headline only
  data/paper/photos/<id>.<ext>                  the lead photos, served at /media/paper/<file>

  story_id(url, title)             the 16-hex id a story keeps everywhere (its link, else its headline)
  extract(html, url, title)        Extracted (paragraphs, author, image, cutline, credit) or the reason there is none
  ArticleStore(data_dir, season)   get, put, all, annotate(rows) (the paper's headlines with their copy's facts)
  ArticleCopier(store, ...)        offer(rows) copies new stories in the background; run(rows) does it now (tests)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import httpx
from pydantic import BaseModel, Field, ValidationError

from app.http import shared_ssl_context
from app.httpcap import get_capped
from app.services.answers import atomic_write

log = logging.getLogger("kickoff.articles")

AGENT_TOKEN = "GatorsGameDay"  # the name robots.txt rules are read for
STORY_ID = re.compile(r"^[0-9a-f]{16}$")
PHOTO_NAME = re.compile(r"^[0-9a-f]{16}\.(?:jpg|png|webp|gif)$")
TIMEOUT = httpx.Timeout(15.0, connect=6.0)
PAGE_BYTES = 3 * 1024 * 1024
PHOTO_BYTES = 5 * 1024 * 1024
ROBOTS_BYTES = 512 * 1024
ROBOTS_TTL_SECONDS = 24 * 3600
PER_RUN = 12  # stories copied per run; the rest wait for the next refresh of the feeds
RECENT_DAYS = 9  # this week and the last; no back-fill of older weeks (owner 2026-10-27)
MAX_ATTEMPTS = 2  # a page that failed twice (timeouts, 5xx) stays headline only
RETRY_AFTER = timedelta(hours=1)
PAUSE_AFTER_FAILURES = 3
PAUSE_SECONDS = 6 * 3600
REFUSED_SECONDS = 7 * 24 * 3600
GAP_SECONDS = 0.5  # between two pages, so no site gets a burst
MIN_WORDS = 40  # less than this is not an article (a video page, a teaser); the team site's briefs run about 60
TEXT_CHARS = 1800  # how much of the opening the paper gets to cut to fit; the reader gets it all
REFUSAL = {401: "the site asks for a sign-in", 402: "the site refuses automated readers", 403: "the site refused the request", 451: "the site refuses it here"}
SKIP_HOSTS = ("news.google.com", "theathletic.com", "nytimes.com")  # links that never lead to a readable copy
PHOTO_TYPES = {"image/jpeg": "jpg", "image/jpg": "jpg", "image/png": "png", "image/webp": "webp", "image/gif": "gif"}
PHOTO_MAGIC = ((b"\xff\xd8\xff", "jpg"), (b"\x89PNG", "png"), (b"GIF8", "gif"), (b"RIFF", "webp"))


def story_id(url: Any, title: Any = None) -> str:
    """The id a story keeps in the paper, the store and the reader: from its link (scheme, query and fragment dropped,
    so a tracking parameter never makes a second story), else from its headline."""
    base = ""
    if isinstance(url, str) and url.strip():
        parts = urlsplit(url.strip())
        base = urlunsplit(("", parts.netloc.lower(), parts.path.rstrip("/"), "", ""))
        if parts.netloc.lower() == "news.google.com":
            base = url.strip()  # a Google News link is only its query
    if not base:
        base = re.sub(r"[^a-z0-9]+", " ", str(title or "").lower()).strip()
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]


def host_of(url: Any) -> str:
    if not isinstance(url, str):
        return ""
    try:
        return (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def copyable(url: Any) -> bool:
    """A direct http(s) link to a site the copier may ask; never a Google News link or a known paywall."""
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        return False
    host = host_of(url)
    return bool(host) and not any(host == s or host.endswith("." + s) for s in SKIP_HOSTS)


# --- the text ------------------------------------------------------------------------------------------------

DROP_LINE = re.compile(r"^(?:share:?|advertisement|story by|\d+\s+min(?:ute)?s?\s+read|read more|print|email|tweet|copy link|listen to this article.*)$", re.IGNORECASE)
DATE_LINE = re.compile(
    r"^(?:(?:mon|tue|wed|thu|fri|sat|sun)[a-z]*\.?,?\s+)?(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}\b.{0,60}$",
    re.IGNORECASE,
)
BYLINE = re.compile(r"^by:?\s+(.{3,90})$", re.IGNORECASE)
PHOTO_CREDIT = re.compile(r"\(\s*photos?:\s*([^)]{2,120})\)\s*$", re.IGNORECASE)
MANDATORY_CREDIT = re.compile(r"mandatory credit", re.IGNORECASE)
PAREN_CREDIT = re.compile(r"^\(.{2,120}\b(?:images?|photos?|getty|imagn|usa today|reuters|associated press)\b.{0,60}\)$", re.IGNORECASE)
STOP_AT = re.compile(r"^(?:\d{4}\s+)?(?:single-game tickets|season tickets|follow on social media|follow us @|related stories|more from|read next|recommended stories|you may also like|this (?:article|story) (?:originally )?(?:appeared|was originally published) (?:on|in))", re.IGNORECASE)
PICTURE_TAG = re.compile(r"<(?:img|source)\b[^>]*>", re.IGNORECASE)
CAPTION_AFTER = re.compile(r"<(figcaption|div|p|span)\b([^>]*)>(.*?)</\1>", re.IGNORECASE | re.DOTALL)  # <figcaption>, or the team site's <div class="s-image-caption">
IMAGE_FILE = re.compile(r"[\w\-.]+\.(?:jpe?g|png|webp|gif)", re.IGNORECASE)
HTML_BYLINE = re.compile(r">\s*By(?::\s*|\s+)([A-Z][\w.'\-]+(?:\s+[A-Z][\w.'\-]+){1,3}(?:,\s*[^<>]{2,60})?)\s*<")  # "By: Pat Writer, Senior Writer"; never "Bye week"
CREDIT_TAIL = re.compile(r"(?:\(\s*photos?:\s*([^)]{2,120})\)|mandatory credit:\s*(.{2,120})|\(([^()]{2,80}?(?:images?|photos?|getty|imagn|reuters|network)[^()]{0,40})\))\s*\.?\s*$", re.IGNORECASE)
LEADING_JUNK = re.compile(r"^(?:completed event:|final$|box score$|recap$|photo gallery$|video$)", re.IGNORECASE)
PAYWALL = re.compile(r"subscribe to (?:continue|read)|already a subscriber|this (?:article|story) is (?:for|available to) subscribers|sign in to (?:continue|read)|create a free account to continue", re.IGNORECASE)


@dataclass
class Extracted:
    paragraphs: list[str] = field(default_factory=list)
    author: str | None = None
    image: str | None = None
    cutline: str | None = None
    credit: str | None = None
    reason: str | None = None  # why there is no article; paragraphs is empty then

    @property
    def words(self) -> int:
        return sum(len(p.split()) for p in self.paragraphs)


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def clean(text: str, title: str, author: str | None = None, page_title: str | None = None) -> Extracted:
    """The article's paragraphs from trafilatura's text, each site's leftovers taken off."""
    lines = [line.strip() for line in str(text or "").split("\n") if line.strip()]
    out = Extracted(author=author.strip() if isinstance(author, str) and author.strip() else None)
    title_key = _norm(title or "")
    page_key = _norm(re.split(r"\s[-|–]\s", page_title or "")[0])  # the page's own headline ("... - Florida Gators")
    # the team site opens with the photo's caption, its credit in brackets at the end: the cutline and the credit
    for i, line in enumerate(lines[:2]):
        credit = PHOTO_CREDIT.search(line)
        if credit:
            out.cutline = line[: credit.start()].strip() or None
            out.credit = credit.group(1).strip()
            del lines[i]
            break
    started = False
    previous_credit = False
    for line in lines:
        key = _norm(line)
        if not key:
            continue
        if any(k and (key == k or key.startswith(k + " ")) and len(key) < len(k) + 40 for k in (title_key, page_key)):
            continue  # the headline again (the feed's or the page's own), sometimes with the site's name after it
        if DROP_LINE.match(line) or DATE_LINE.match(line):
            continue
        byline = BYLINE.match(line)
        if byline and len(out.paragraphs) < 2:
            out.author = out.author or byline.group(1).strip()
            continue
        if out.author and (key == _norm(out.author) or key.startswith(_norm(out.author.split(";")[0]) + " ")) and len(line) < len(out.author) + 30:
            continue  # "Adam Dubbin, Gators Wire" under Yahoo's "Story by"
        if MANDATORY_CREDIT.search(line) or PAREN_CREDIT.match(line):
            previous_credit = True
            continue
        if previous_credit and len(line.split()) < 40 and re.search(r"\(\d{1,2}\)", line):
            previous_credit = False
            continue  # a photo's caption that follows its credit ("quarterback DJ Lagway (2) runs against ...")
        previous_credit = False
        if not started:
            if LEADING_JUNK.match(line) or len(line.split()) < 5:
                continue  # a scoreboard strip or a section label above the story
            started = True
        if STOP_AT.match(line):
            break
        out.paragraphs.append(line)
    return out


def _plain(fragment: str) -> str:
    import html as htmllib

    return re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def photo_caption(page: str, image: str | None) -> tuple[str | None, str | None]:
    """(cutline, credit) of the lead photo: the caption of the <figure> that holds that very picture, its credit split
    off. A caption under another picture of the page is never borrowed (a wrong cutline is worse than none)."""
    from urllib.parse import unquote

    if not isinstance(image, str) or not isinstance(page, str):
        return None, None
    files = IMAGE_FILE.findall(unquote(unquote(image)))
    if not files:
        return None, None
    wanted = files[-1].lower()  # the picture's own file name, also inside a resizing service's address
    for tag in PICTURE_TAG.finditer(page):
        if wanted not in unquote(unquote(tag.group(0))).lower():
            continue
        tail = page[tag.end() : tag.end() + 3000].split("<img", 1)[0]  # up to the next picture
        caption = next((m for m in CAPTION_AFTER.finditer(tail) if m.group(1).lower() == "figcaption" or "caption" in m.group(2).lower()), None)
        text = _plain(caption.group(3)) if caption else ""
        if not text:
            continue  # this copy of the picture has no caption under it (a <source> in a <picture>); try the next
        credit = CREDIT_TAIL.search(text)
        if credit:
            words = text[: credit.start()].strip(" .;")
            return (words + "." if words else None), next(g for g in credit.groups() if g).strip()
        return text[:400], None
    return None, None


def extract(html: str, url: str, title: str) -> Extracted:
    """The article on a publisher's page, or an empty Extracted with the reason there is none."""
    import trafilatura  # imported here: the server starts without loading lxml until a story needs reading

    try:
        # favor_precision: the balanced setting pulls Yahoo's related-story blocks into the text (3,200 words for a 230-word
        # story) and the team site's sidebar dates (measured 2026-10-27 on the week's real pages)
        raw = trafilatura.extract(html, url=url, output_format="json", with_metadata=True, include_comments=False, include_tables=False, favor_precision=True)
    except Exception as exc:  # noqa: BLE001 - a page the extractor cannot read is one headline-only story, never a crash
        log.warning("The article at %s could not be read: %s", url, exc)
        return Extracted(reason="the page could not be read")
    if not raw:
        return Extracted(reason="no article text on the page")
    try:
        doc = json.loads(raw)
    except ValueError:
        return Extracted(reason="no article text on the page")
    if not isinstance(doc, dict):
        return Extracted(reason="no article text on the page")
    text = doc.get("text") if isinstance(doc.get("text"), str) else ""
    result = clean(text, title, doc.get("author") if isinstance(doc.get("author"), str) else None, doc.get("title") if isinstance(doc.get("title"), str) else None)
    image = doc.get("image")
    result.image = image if isinstance(image, str) and image.startswith(("http://", "https://")) else None
    if result.cutline is None and result.image:
        result.cutline, result.credit = photo_caption(html, result.image)
    if result.author is None:
        byline = HTML_BYLINE.search(html[:200_000])
        result.author = _plain(byline.group(1)) if byline else None
    if PAYWALL.search(text) and result.words < 400:
        return Extracted(reason="behind a paywall")
    if result.words < MIN_WORDS:
        return Extracted(reason="no article text on the page")
    return result


# --- the store -----------------------------------------------------------------------------------------------


class Article(BaseModel):
    """One story as the store keeps it. Every field has a safe default, so a damaged file reads as headline only."""

    id: str
    url: str | None = None
    title: str = ""
    source: str = ""
    publishedAt: str | None = None
    outcome: Literal["copied", "headline", "pending"] = "pending"
    reason: str | None = None
    author: str | None = None
    paragraphs: list[str] = Field(default_factory=list)
    photo: str | None = None
    cutline: str | None = None
    credit: str | None = None
    words: int = 0
    copiedAt: str | None = None
    attempts: int = 0
    nextTry: str | None = None


def _iso(when: datetime) -> str:
    return when.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _when(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class ArticleStore:
    def __init__(self, data_dir: Path, season: int) -> None:
        self.dir = Path(data_dir) / "season" / str(int(season)) / "paper" / "articles"
        self.photos = Path(data_dir) / "paper" / "photos"
        self._index: dict[str, Article] | None = None
        self.skipped = 0  # files that could not be read, counted and logged

    def _load(self) -> dict[str, Article]:
        if self._index is not None:
            return self._index
        index: dict[str, Article] = {}
        if self.dir.is_dir():
            for path in self.dir.glob("*.json"):
                if not STORY_ID.match(path.stem):
                    continue
                try:
                    article = Article.model_validate(json.loads(path.read_text(encoding="utf-8")))
                except (OSError, ValueError, ValidationError) as exc:
                    self.skipped += 1
                    log.warning("Skipped the unreadable story file %s: %s", path.name, exc)
                    continue
                if article.id == path.stem:
                    index[article.id] = article
        self._index = index
        return index

    def get(self, sid: Any) -> Article | None:
        if not isinstance(sid, str) or not STORY_ID.match(sid):
            return None
        return self._load().get(sid)

    def all(self) -> list[Article]:
        return list(self._load().values())

    def put(self, article: Article) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        atomic_write(self.dir / f"{article.id}.json", article.model_dump_json())
        self._load()[article.id] = article

    def photo_path(self, name: Any) -> Path | None:
        if not isinstance(name, str) or not PHOTO_NAME.match(name):
            return None
        path = self.photos / name
        return path if path.is_file() else None

    def annotate(self, rows: Any) -> list[dict[str, Any]]:
        """The paper's headlines, each with its id and what the store holds of it: copied or not, the photo's local
        address, the cutline and credit, the word count and the opening (enough text for the paper to cut to fit)."""
        out: list[dict[str, Any]] = []
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict) or not isinstance(row.get("title"), str):
                continue
            sid = story_id(row.get("url"), row.get("title"))
            article = self.get(sid)
            copied = article is not None and article.outcome == "copied" and bool(article.paragraphs)
            opening: list[str] = []
            if copied:
                total = 0
                for paragraph in article.paragraphs:
                    opening.append(paragraph)
                    total += len(paragraph)
                    if total >= TEXT_CHARS:
                        break
            out.append(
                {
                    **row,
                    "id": sid,
                    "copied": copied,
                    "photo": f"/media/paper/{article.photo}" if copied and article.photo else None,
                    "cutline": article.cutline if copied else None,
                    "credit": article.credit if copied else None,
                    "author": article.author if copied else None,
                    "words": article.words if copied else 0,
                    "opening": opening,
                }
            )
        return out

    def counts(self) -> dict[str, int]:
        index = self._load()
        return {kind: sum(1 for a in index.values() if a.outcome == kind) for kind in ("copied", "headline", "pending")}

    def newest_copy(self) -> datetime | None:
        times = [t for a in self._load().values() if a.outcome == "copied" and (t := _when(a.copiedAt)) is not None]
        return max(times) if times else None


# --- the copier ----------------------------------------------------------------------------------------------


@dataclass
class _Robots:
    rules: RobotFileParser | None  # None: allowed everywhere (no robots.txt)
    fetched: float


class ArticleCopier:
    def __init__(
        self,
        store: ArticleStore,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        user_agent: str = f"{AGENT_TOKEN} (personal reader; one copy per story)",
        clock: Callable[[], datetime] | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
        extractor: Callable[[str, str, str], Extracted] = extract,
    ) -> None:
        self.store = store
        self._http = httpx.AsyncClient(verify=shared_ssl_context(), timeout=TIMEOUT, transport=transport, headers={"User-Agent": user_agent, "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5"}, follow_redirects=True)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._sleep = sleep or asyncio.sleep
        self._extract = extractor
        self._robots: dict[str, _Robots] = {}
        self._failures: dict[str, int] = {}
        self._paused_until: dict[str, float] = {}
        self._refused_until: dict[str, float] = {}
        self._task: asyncio.Task[Any] | None = None
        self.last_run: str | None = None
        self.last_error: str | None = None

    async def aclose(self) -> None:
        task, self._task = self._task, None
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001 - shutting down
                pass
        await self._http.aclose()

    # --- what to copy ------------------------------------------------------------------------------------------

    def wanted(self, rows: Any) -> list[dict[str, Any]]:
        """The stories worth a try now: recent, a direct link, not copied or refused yet, a failed one after its wait."""
        now = self._clock()
        cutoff = now - timedelta(days=RECENT_DAYS)
        out: list[dict[str, Any]] = []
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict) or not isinstance(row.get("title"), str) or not copyable(row.get("url")):
                continue
            published = _when(row.get("publishedAt"))
            if published is None or published < cutoff:
                continue
            known = self.store.get(story_id(row["url"], row["title"]))
            if known is not None:
                if known.outcome != "pending":
                    continue
                wait = _when(known.nextTry)
                if wait is not None and wait > now:
                    continue
            out.append(row)
        out.sort(key=lambda r: r.get("publishedAt") or "", reverse=True)
        return out[:PER_RUN]

    def offer(self, rows: Any) -> None:
        """Copy the new stories in the background, one run at a time; the page never waits for it."""
        if self._task is not None and not self._task.done():
            return
        todo = self.wanted(rows)
        if not todo:
            return
        try:
            self._task = asyncio.get_running_loop().create_task(self.run(todo), name="copy articles")
        except RuntimeError:  # no running loop (a synchronous caller): the next page's refresh offers them again
            return

    async def run(self, rows: list[dict[str, Any]]) -> int:
        copied = 0
        for i, row in enumerate(rows):
            if i:
                await self._sleep(GAP_SECONDS)
            try:
                article = await self.copy_one(row)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - one bad page never stops the run; logged with the traceback
                log.exception("Copying %s failed", row.get("url"))
                self.last_error = f"{exc.__class__.__name__}: {exc}"
                continue
            copied += article.outcome == "copied"
        self.last_run = _iso(self._clock())
        if copied:
            log.info("Copied %d of %d new stories", copied, len(rows))
        return copied

    # --- one story ---------------------------------------------------------------------------------------------

    def _article(self, row: dict[str, Any]) -> Article:
        sid = story_id(row.get("url"), row.get("title"))
        known = self.store.get(sid)
        base = known.model_copy() if known is not None else Article(id=sid)
        base.url = row.get("url") if isinstance(row.get("url"), str) else base.url
        base.title = row["title"].strip()
        base.source = str(row.get("source") or base.source or "")
        base.publishedAt = row.get("publishedAt") if isinstance(row.get("publishedAt"), str) else base.publishedAt
        return base

    def _headline(self, article: Article, reason: str) -> Article:
        article.outcome, article.reason, article.nextTry = "headline", reason, None
        self.store.put(article)
        return article

    def _later(self, article: Article, reason: str) -> Article:
        article.attempts += 1
        if article.attempts >= MAX_ATTEMPTS:
            return self._headline(article, f"could not be read after {article.attempts} tries ({reason})")
        article.outcome, article.reason, article.nextTry = "pending", reason, _iso(self._clock() + RETRY_AFTER)
        self.store.put(article)
        return article

    def _site_failed(self, host: str) -> None:
        self._failures[host] = self._failures.get(host, 0) + 1
        if self._failures[host] >= PAUSE_AFTER_FAILURES:
            self._paused_until[host] = time.time() + PAUSE_SECONDS
            self._failures[host] = 0
            log.warning("Stopped asking %s for six hours after repeated failures", host)

    async def copy_one(self, row: dict[str, Any]) -> Article:
        article = self._article(row)
        url = article.url or ""
        host = host_of(url)
        if time.time() < self._refused_until.get(host, 0.0):
            return self._headline(article, "the site refused automated readers this week")
        if time.time() < self._paused_until.get(host, 0.0):
            return article  # tried again once the pause is over; nothing written
        allowed = await self.allowed(url)
        if allowed is None:
            self._site_failed(host)
            return self._later(article, "the site's robots.txt could not be read")
        if not allowed:
            return self._headline(article, "the site asks robots not to read it")
        try:
            response = await get_capped(self._http, url, PAGE_BYTES)
        except httpx.HTTPError as exc:
            self._site_failed(host)
            return self._later(article, exc.__class__.__name__)
        final_host = host_of(str(response.url))
        if final_host != host and not copyable(str(response.url)):
            return self._headline(article, f"the link leads to {final_host or 'another site'}")
        status = response.status_code
        if status in REFUSAL or (status == 202 and len(response.content) < 2048):
            self._refused_until[host] = time.time() + REFUSED_SECONDS
            return self._headline(article, f"{REFUSAL.get(status, 'the site refuses automated readers')} (HTTP {status})")
        if status in (404, 410):
            return self._headline(article, f"the story is gone (HTTP {status})")
        if status != 200:
            self._site_failed(host)
            return self._later(article, f"HTTP {status}")
        self._failures[host] = 0
        html = response.text
        found = await asyncio.to_thread(self._extract, html, str(response.url), article.title)
        if not found.paragraphs:
            return self._headline(article, found.reason or "no article text on the page")
        article.paragraphs = found.paragraphs
        article.words = found.words
        article.author = found.author
        article.cutline = found.cutline
        article.credit = found.credit
        article.photo = await self.save_photo(found.image, article.id) if found.image else None
        article.outcome, article.reason, article.nextTry = "copied", None, None
        article.copiedAt = _iso(self._clock())
        self.store.put(article)
        return article

    async def read_once(self, row: dict[str, Any]) -> tuple[Article | None, str]:
        """Batch 3 (owner 2026-11-16, "Headlines + reader"): a story from another team's paper, read when the reader opens it
        and never kept (no store, no photo), with a copy's manners (robots.txt, a refusal or a pause remembered). A story
        already copied for our paper is that copy. (article, "") or (None, why only the headline can be shown)."""
        article = self._article(row)
        if article.outcome == "copied" and article.paragraphs:
            return article, ""
        url = article.url or ""
        if not copyable(url):
            return None, "only the headline is on this server"
        host = host_of(url)
        if time.time() < self._refused_until.get(host, 0.0):
            return None, "the site refused automated readers this week"
        if time.time() < self._paused_until.get(host, 0.0):
            return None, "the site is paused after repeated failures"
        allowed = await self.allowed(url)
        if allowed is None:
            self._site_failed(host)
            return None, "the site's robots.txt could not be read"
        if not allowed:
            return None, "the site asks robots not to read it"
        try:
            response = await get_capped(self._http, url, PAGE_BYTES)
        except httpx.HTTPError as exc:
            self._site_failed(host)
            return None, f"the site did not answer ({exc.__class__.__name__})"
        status = response.status_code
        if status in REFUSAL or (status == 202 and len(response.content) < 2048):
            self._refused_until[host] = time.time() + REFUSED_SECONDS
            return None, f"{REFUSAL.get(status, 'the site refuses automated readers')} (HTTP {status})"
        if status != 200:
            if status not in (404, 410):
                self._site_failed(host)
            return None, f"the site answered HTTP {status}"
        self._failures[host] = 0
        found = await asyncio.to_thread(self._extract, response.text, str(response.url), article.title)
        if not found.paragraphs:
            return None, found.reason or "no article text on the page"
        return article.model_copy(update={"paragraphs": found.paragraphs, "words": found.words, "author": found.author, "cutline": None, "credit": None, "photo": None, "outcome": "copied", "reason": None, "nextTry": None, "copiedAt": _iso(self._clock())}), ""

    async def save_photo(self, url: str, sid: str) -> str | None:
        """The lead photo saved under the story's id: an image of a known kind, 5 MB at most; else no photo."""
        if not url.startswith(("http://", "https://")) or not await self.allowed(url):
            return None
        try:
            response = await get_capped(self._http, url, PHOTO_BYTES)
        except httpx.HTTPError as exc:
            log.info("No photo for story %s: %s", sid, exc.__class__.__name__)
            return None
        if response.status_code != 200 or not response.content:
            return None
        kind = PHOTO_TYPES.get(response.headers.get("content-type", "").split(";")[0].strip().lower())
        magic = next((ext for sig, ext in PHOTO_MAGIC if response.content.startswith(sig)), None)
        if kind is None or magic is None:
            log.info("No photo for story %s: %s is not a picture", sid, url)
            return None
        name = f"{sid}.{magic}"
        try:
            self.store.photos.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(atomic_write_bytes, self.store.photos / name, response.content)
        except OSError as exc:
            log.warning("Could not save the photo for story %s: %s", sid, exc)
            return None
        return name

    # --- robots.txt --------------------------------------------------------------------------------------------

    async def allowed(self, url: str) -> bool | None:
        """Whether the site's robots.txt lets this app read the page; None when it could not be read just now."""
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        cached = self._robots.get(origin)
        if cached is None or time.time() - cached.fetched > ROBOTS_TTL_SECONDS:
            try:
                response = await get_capped(self._http, f"{origin}/robots.txt", ROBOTS_BYTES)
            except httpx.HTTPError:
                return None
            if response.status_code in (401, 403):
                rules = RobotFileParser()
                rules.disallow_all = True
            elif response.status_code == 200:
                rules = RobotFileParser()
                rules.parse(response.text.splitlines())
            elif 400 <= response.status_code < 500:
                rules = None  # no robots.txt: nothing is asked
            else:
                return None
            cached = self._robots[origin] = _Robots(rules, time.time())
        return True if cached.rules is None else cached.rules.can_fetch(AGENT_TOKEN, url)

    def status(self) -> dict[str, Any]:
        now = time.time()
        return {
            **self.store.counts(),
            "lastRun": self.last_run,
            "lastError": self.last_error,
            "running": self._task is not None and not self._task.done(),
            "paused": sorted(h for h, until in self._paused_until.items() if until > now),
            "refusing": sorted(h for h, until in self._refused_until.items() if until > now),
        }


def atomic_write_bytes(path: Path, data: bytes) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)
