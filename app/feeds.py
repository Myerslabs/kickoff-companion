"""Headline feeds (N3): the team's own athletics feed (TEAM_FEED_URL, optional), ESPN college
football, The Athletic college football, and a Google News search for the team, fetched as RSS or
Atom, parsed with the standard library, and reduced to headlines with links. Keyless, outside the
CFBD quota. Each feed keeps its last good answer on disk so a dead site shows old headlines marked
stale instead of nothing, and a feed that fails repeatedly is paused for a while.

National feed addresses verified 2026-09-23:
  ESPN           https://www.espn.com/espn/rss/ncf/news                (25 items, all of college football)
  The Athletic   https://theathletic.com/rss/college-football/         (100 items, all of college football)
  Google News    https://news.google.com/rss/search?q="<school> <mascot>" football
The two national feeds are filtered to headlines that name our school or mascot (TeamMatcher),
leaving out schools whose names contain ours (public release Phase 3: built from the team's
identity, app/services/identity.py, instead of a fixed list).

No betting news on any feed (owner, 2026-09-23: "dont show news on betting at all. Only the game
line"). Every headline passes is_betting() when a feed is parsed and again when a stored copy is
read back, so headlines saved before the rule existed are hidden too. Each feed counts what it hid.
The game line itself comes from CFBD on the program and the slate, never from a feed.
"""

from __future__ import annotations

import asyncio
import html
import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, NamedTuple
from urllib.parse import quote_plus
from xml.etree import ElementTree

import httpx

log = logging.getLogger("kickoff.feeds")

TIMEOUT = httpx.Timeout(10.0, connect=5.0)
FRESH_SECONDS = 30 * 60
PAUSE_AFTER_FAILURES = 3
PAUSE_SECONDS = 15 * 60
MAX_BYTES = 3 * 1024 * 1024
MAX_ITEMS_PER_FEED = 40
ATOM = "{http://www.w3.org/2005/Atom}"

# --- betting news --------------------------------------------------------------------------------
# A headline is betting news when its title or its source names a sportsbook or a betting-tips
# site or uses betting language, or when the story lives on such a site. Whole words only, any
# case. Football phrases that share a word with betting talk are blanked first, so "spread
# offense", "offensive line" and "against all odds" never count, and "bet" never matches inside
# "Bethune" or "better". Staff picks with no betting term stay.

# Sportsbooks and betting-tips sites, matched anywhere in the title or the source.
BETTING_BRANDS: tuple[str, ...] = (
    r"DraftKings", r"FanDuel", r"BetMGM", r"Caesars(?!\s+Superdome)", r"bet365", r"ESPN\s*BET", r"Fanatics\s+Sportsbook",
    r"BetRivers", r"Hard\s+Rock\s+Bet", r"Bovada", r"BetOnline", r"PointsBet", r"BetUS", r"MyBookie", r"WynnBET",
    r"Barstool\s+Sportsbook", r"PrizePicks", r"Underdog\s+Fantasy",
    r"(?:The\s+)?Action\s+Network", r"SportsLine", r"Vegas\s*Insider", r"Pickswise", r"Odds\s*Shark", r"BetQL",
    r"Sportsbook\s*Review", r"BettingPros", r"Sports\s+Betting\s+Dime", r"OddsTrader", r"Dimers", r"TheLines",
    r"Legal\s+Sports\s+Report", r"WagerTalk", r"Doc'?s\s+Sports",
)
# Sources whose name is also an ordinary word, so they match only as the whole source ("Covers").
BETTING_SOURCE_NAMES: frozenset[str] = frozenset({"covers", "covers.com"})
# Story and source addresses of the same sites; a subdomain counts too.
BETTING_HOSTS: tuple[str, ...] = (
    "draftkings.com", "fanduel.com", "betmgm.com", "caesars.com", "bet365.com", "espnbet.com", "betrivers.com", "hardrock.bet",
    "bovada.lv", "betonline.ag", "pointsbet.com", "betus.com.pa", "mybookie.ag", "prizepicks.com", "underdogfantasy.com",
    "actionnetwork.com", "covers.com", "sportsline.com", "vegasinsider.com", "pickswise.com", "oddsshark.com", "betql.co",
    "sportsbookreview.com", "bettingpros.com", "sportsbettingdime.com", "oddstrader.com", "dimers.com", "thelines.com",
    "legalsportsreport.com", "wagertalk.com", "docsports.com",
)
# Betting language. "favorite" and "underdog" alone are ordinary football words; they count only
# with the size of a line ("6.5-point home underdog", "double-digit favorite", "favored by 3") or
# beside odds, a line or a spread (below).
BETTING_TERMS: tuple[str, ...] = (
    r"odds", r"betting", r"bets?", r"bettors?", r"best\s+bets?", r"wager(?:s|ing|ed)?", r"parlays?",
    r"prop\s+bets?", r"player\s+props?", r"props(?!\s+(?:to|for|up)\b)", r"money\s*-?\s*lines?",
    r"over\s*/\s*under", r"over-unders?", r"o/u", r"point\s+spreads?", r"against\s+the\s+spread", r"ATS",
    r"cover(?:s|ed|ing)?\s+the\s+spread", r"spread\s+picks?", r"promo\s+codes?", r"bonus\s+codes?",
    r"sportsbooks?", r"bookmakers?", r"bookies", r"sharp\s+(?:money|action|bettors?)", r"sports\s+gambling",
    r"handicapp(?:ing|ers?)", r"betting\s+lines?", r"opening\s+lines?", r"vegas\s+(?:lines?|odds)",
    r"lock\s+of\s+the\s+(?:week|day)",
    # A number of points then, within two words, the side: "7-point road underdogs".
    r"\d+(?:\.\d+)?\s*-?\s*(?:point|pt)s?\s+(?:[\w-]+\s+){0,2}(?:favou?rites?|underdogs?|dogs?)",
    # A line sized in words; only a venue or a strength word may sit between: "double-digit home underdog".
    r"(?:double[- ]digits?|touchdown|field[- ]goal)\s+(?:(?:home|road|neutral[- ]site|betting|early|opening|slight|heavy|big|consensus|preseason)\s+){0,2}(?:favou?rites?|underdogs?|dogs?)",
    r"favou?red\s+by\s+\d", r"(?:favou?rites?|underdogs?)\s+by\s+\d",
)
# Football phrases blanked before matching, so their words cannot pair up or match on their own.
NOT_BETTING = re.compile(
    r"\b(?:offensive|defensive|o|d)[- ]lines?(?:man|men)?\b|\bline\s+of\s+scrimmage\b|\bgoal[- ]lines?\b"
    r"|\bspread\s+(?:offenses?|attacks?|formations?|options?|systems?|schemes?|looks?|sets?|concepts?|passing|game)\b"
    r"|\bspread(?:s|ing)?\s+(?:the\s+)?(?:wealth|ball|field|love)\b|\bspread(?:s|ing)?\s+out\b"
    r"|\bagainst\s+(?:all\s+)?(?:the\s+)?odds\b|\b(?:beat|beats|beating|defy|defies|defied|defying|overcome|overcomes|overcame|overcoming)\s+(?:the\s+|long\s+)?odds\b"
    r"|\bodds\s+and\s+ends\b",
    re.IGNORECASE,
)
_BETTING_BRAND = re.compile(r"\b(?:" + "|".join(BETTING_BRANDS) + r")\b", re.IGNORECASE)
_BETTING_TERM = re.compile(r"\b(?:" + "|".join(BETTING_TERMS) + r")\b", re.IGNORECASE)
_FAVORITE = re.compile(r"\b(?:favou?rites?|favou?red|underdogs?)\b", re.IGNORECASE)
_LINE_TALK = re.compile(r"\b(?:odds|lines?|spreads?)\b", re.IGNORECASE)
# The USA Today form "Kansas vs. Iowa prediction, pick, spread": a spread or a total counts
# beside a pick or a prediction. "picks up", "picks off" and "total offense" are football.
_PICK_TALK = re.compile(r"\b(?:picks?(?!\s+(?:up|off)\b)|predictions?)\b", re.IGNORECASE)
_SPREAD_OR_TOTAL = re.compile(r"\b(?:spreads?|totals?(?!\s+(?:offen[cs]e|defen[cs]e|yards?|yardage|tackles?|of)\b))\b", re.IGNORECASE)
# A signed line: "Rebels -6.5", "Hawkeyes (+3)". Half points only when bare, so scores ("24-17"),
# records ("3-0") and dates never match.
_SIGNED_LINE = re.compile(r"(?<![\w.+-])[+-]\d{1,2}\.5\b|\([+-]\d{1,2}(?:\.5)?\)")
# Typographic apostrophes and minus signs read as their plain forms ("Doc’s Sports", "−6.5").
_PLAIN_PUNCTUATION = str.maketrans({"\u2018": "'", "\u2019": "'", "\u2212": "-", "\u2013": "-"})


@dataclass(frozen=True)
class FeedSpec:
    id: str
    name: str
    url: str
    team_only: bool = False  # national feeds keep only headlines about our team


class TeamMatcher:
    """Which headlines are about us: a whole-word mention of our school or mascot, and not one of a
    school whose name contains ours ("Michigan State" is not "Michigan")."""

    def __init__(self, names: tuple[str, ...] | list[str], exclude: tuple[str, ...] | list[str] = ()) -> None:
        self.names = tuple(n for n in names if isinstance(n, str) and n.strip())
        self.exclude = tuple(n for n in exclude if isinstance(n, str) and n.strip())
        self._yes = re.compile(r"\b(?:" + "|".join(re.escape(n) for n in self.names) + r")\b", re.IGNORECASE) if self.names else None
        ordered = sorted(self.exclude, key=len, reverse=True)
        self._no = re.compile(r"\b(?:" + "|".join(re.escape(n) for n in ordered) + r")\b", re.IGNORECASE) if ordered else None

    def matches(self, title: str) -> bool:
        if self._yes is None or not isinstance(title, str):
            return False
        if self._no is None:
            return bool(self._yes.search(title))
        # A title naming a rival may still name us ("Michigan State at Michigan"): mask the rivals first.
        return bool(self._yes.search(self._no.sub(" ", title)))


NATIONAL_FEEDS: tuple[FeedSpec, ...] = (
    FeedSpec("espn", "ESPN", "https://www.espn.com/espn/rss/ncf/news", team_only=True),
    FeedSpec("athletic", "The Athletic", "https://theathletic.com/rss/college-football/", team_only=True),
)


def google_news_url(school: str, mascot: str | None) -> str:
    phrase = f"{school} {mascot}" if mascot else school
    return f"https://news.google.com/rss/search?q={quote_plus(chr(34) + phrase + chr(34))}+football&hl=en-US&gl=US&ceid=US:en"


def team_feeds(school: str, mascot: str | None = None, team_feed_url: str | None = None) -> tuple[FeedSpec, ...]:
    """The feeds for a team: its own athletics feed when one is configured, the two national feeds
    (filtered to the team), and a Google News search for it."""
    own = (FeedSpec("team", f"{school} Athletics", team_feed_url),) if team_feed_url else ()
    return own + NATIONAL_FEEDS + (FeedSpec("google", "Google News", google_news_url(school, mascot)),)


def team_matcher(school: str, mascot: str | None = None, rivals: tuple[str, ...] | list[str] = ()) -> TeamMatcher:
    return TeamMatcher([school] + ([mascot] if mascot else []), rivals)


@dataclass
class Headline:
    title: str
    url: str | None
    source: str
    feed: str
    published_at: str | None  # ISO 8601 UTC

    def as_dict(self) -> dict[str, Any]:
        return {"title": self.title, "url": self.url, "source": self.source, "feed": self.feed, "publishedAt": self.published_at}


@dataclass
class FeedResult:
    feed: FeedSpec
    headlines: list[Headline] = field(default_factory=list)
    fetched_at: datetime | None = None
    stale: bool = False
    error: str | None = None
    skipped: int = 0
    betting: int = 0  # betting headlines hidden from this feed's current headlines

    def status(self, now: datetime) -> dict[str, Any]:
        age = round((now - self.fetched_at).total_seconds()) if self.fetched_at else None
        return {
            "status": "error" if self.fetched_at is None else "stale" if self.stale else "ok",
            "fetchedAt": self.fetched_at.isoformat(timespec="seconds").replace("+00:00", "Z") if self.fetched_at else None,
            "ageSeconds": age,
            "error": self.error,
            "skipped": self.skipped,
            "betting": self.betting,
            "count": len(self.headlines),
        }


class ParsedFeed(NamedTuple):
    headlines: list[Headline]
    skipped: int  # items that could not be read
    betting: int  # betting headlines dropped


# --- parsing --------------------------------------------------------------------------------


def _text(node: ElementTree.Element | None) -> str | None:
    if node is None:
        return None
    value = "".join(node.itertext()).strip()
    return html.unescape(value) if value else None


def _iso(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        parsed = None
    if parsed is None:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _str_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _count(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _clean_title(title: str) -> str:
    # Google News appends " - Source" to every title; keep the headline, the source is shown separately.
    return re.sub(r"\s+-\s+[^-]{2,60}$", "", title).strip() or title


def _betting_words(text: str) -> bool:
    words = NOT_BETTING.sub(" ", text.translate(_PLAIN_PUNCTUATION))
    if _BETTING_BRAND.search(words) or _BETTING_TERM.search(words) or _SIGNED_LINE.search(words):
        return True
    if _PICK_TALK.search(words) and _SPREAD_OR_TOTAL.search(words):
        return True
    return bool(_FAVORITE.search(words) and _LINE_TALK.search(words))


def _betting_host(host: str) -> bool:
    host = host.lower().strip().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    return any(host == h or host.endswith("." + h) for h in BETTING_HOSTS)


def is_betting(title: Any, source: Any = None, url: Any = None) -> bool:
    """True when a headline is betting news. Title, source and url are each optional and may be
    anything; only strings are read."""
    if isinstance(title, str) and _betting_words(title):
        return True
    if isinstance(source, str) and source.strip():
        name = source.strip()
        if name.lower() in BETTING_SOURCE_NAMES or _betting_words(name):
            return True
        if "." in name and " " not in name and _betting_host(name):
            return True  # Google News names some sources by their address
    if isinstance(url, str) and url.startswith(("http://", "https://")):
        # The host only. A story's slug is not the headline the owner reads, and matching it would
        # hide one outlet's telling of a story while another outlet's telling stays.
        try:
            host = httpx.URL(url).host or ""
        except (httpx.InvalidURL, ValueError, TypeError):
            return False
        return _betting_host(host)
    return False


def drop_betting(headlines: list[Headline]) -> tuple[list[Headline], int]:
    """(headlines that are not betting news, how many were dropped)."""
    kept = [h for h in headlines if not is_betting(h.title, h.source, h.url)]
    return kept, len(headlines) - len(kept)


def parse_feed(body: bytes, spec: FeedSpec, matcher: TeamMatcher | None = None) -> ParsedFeed:
    """Headlines from an RSS 2.0 or Atom document, betting news dropped and counted. Never raises."""
    try:
        root = ElementTree.fromstring(body)
    except ElementTree.ParseError as exc:
        log.warning("Feed %s is not XML: %s", spec.id, exc)
        return ParsedFeed([], 1, 0)
    items = root.findall(".//item")
    atom = not items
    if atom:
        items = root.findall(f".//{ATOM}entry")
    if not items and root.tag not in ("rss", "channel", f"{ATOM}feed"):
        log.warning("Feed %s is XML but not a feed (root <%s>)", spec.id, root.tag)
        return ParsedFeed([], 1, 0)  # an HTML block page or an error document, not an empty feed
    rows: list[tuple[Headline, str]] = []  # with the title as sent: Google's " - Source" suffix can name a betting site
    skipped = 0
    for item in items:
        try:
            if atom:
                title = _text(item.find(f"{ATOM}title"))
                link_node = item.find(f"{ATOM}link")
                url = link_node.get("href") if link_node is not None else None
                published = _text(item.find(f"{ATOM}published")) or _text(item.find(f"{ATOM}updated"))
                source = _text(item.find(f"{ATOM}source/{ATOM}title")) or spec.name
            else:
                title = _text(item.find("title"))
                url = _text(item.find("link")) or (item.find("guid").text.strip() if item.find("guid") is not None and (item.find("guid").text or "").startswith("http") else None)
                published = _text(item.find("pubDate")) or _text(item.find("{http://purl.org/dc/elements/1.1/}date"))
                source = _text(item.find("source")) or spec.name
        except (AttributeError, TypeError):
            skipped += 1
            continue
        if not title:
            skipped += 1
            continue
        if url and not url.startswith(("http://", "https://")):
            url = None
        rows.append((Headline(_clean_title(title), url, source or spec.name, spec.id, _iso(published)), title))
        if len(rows) >= MAX_ITEMS_PER_FEED:
            break
    if spec.team_only:
        rows = [(h, raw) for h, raw in rows if matcher is not None and matcher.matches(h.title)]
    headlines = [h for h, raw in rows if not is_betting(raw, h.source, h.url)]
    betting = len(rows) - len(headlines)
    if betting:
        log.info("Feed %s: %d betting headline%s hidden", spec.id, betting, "" if betting == 1 else "s")
    return ParsedFeed(headlines, skipped, betting)


def merge_headlines(results: list[FeedResult], limit: int = 40) -> list[dict[str, Any]]:
    """Newest first, duplicates by title removed (the same story often lands in two feeds). The
    betting filter runs once more here as the last gate before the page."""
    seen: set[str] = set()
    merged: list[Headline] = []
    for result in results:
        for headline in result.headlines:
            if is_betting(headline.title, headline.source, headline.url):
                log.warning("Feed %s passed a betting headline to the merge; hidden: %s", headline.feed, headline.title)
                continue
            key = re.sub(r"[^a-z0-9]+", " ", headline.title.lower()).strip()[:80]
            if key in seen:
                continue
            seen.add(key)
            merged.append(headline)
    merged.sort(key=lambda h: h.published_at or "", reverse=True)
    return [h.as_dict() for h in merged[:limit]]


# --- fetching -------------------------------------------------------------------------------


class FeedStore:
    def __init__(self, data_dir: Path, feeds: tuple[FeedSpec, ...] = NATIONAL_FEEDS, transport: httpx.AsyncBaseTransport | None = None, user_agent: str = "KickoffCompanion", clock=None, matcher: TeamMatcher | None = None) -> None:
        self.dir = data_dir / "feeds"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.feeds = feeds
        self.matcher = matcher
        self._http = httpx.AsyncClient(timeout=TIMEOUT, transport=transport, headers={"User-Agent": user_agent, "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml;q=0.9, */*;q=0.5"}, follow_redirects=True)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._memory: dict[str, FeedResult] = {}
        self._failures: dict[str, int] = {}
        self._paused_until: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def aclose(self) -> None:
        await self._http.aclose()

    def _disk(self, feed_id: str) -> Path:
        return self.dir / f"{feed_id}.json"

    def _load_disk(self, spec: FeedSpec) -> FeedResult | None:
        path = self._disk(spec.id)
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            fetched_at = datetime.fromisoformat(raw["fetchedAt"])
            if fetched_at.tzinfo is None:
                fetched_at = fetched_at.replace(tzinfo=timezone.utc)
            stored = raw.get("headlines")
            headlines = [
                Headline(h["title"], _str_or_none(h.get("url")), _str_or_none(h.get("source")) or spec.name, spec.id, _str_or_none(h.get("publishedAt")))
                for h in (stored if isinstance(stored, list) else [])
                if isinstance(h, dict) and isinstance(h.get("title"), str) and h["title"].strip()
            ]
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
            log.warning("Stored feed %s is unreadable, ignoring it: %s", spec.id, exc)
            return None
        # A copy saved before the betting rule (or before a newer betting term) can still hold betting news.
        headlines, hidden = drop_betting(headlines)
        if hidden:
            log.info("Stored feed %s: %d betting headline%s hidden", spec.id, hidden, "" if hidden == 1 else "s")
        return FeedResult(spec, headlines, fetched_at, False, None, _count(raw.get("skipped")), _count(raw.get("betting")) + hidden)

    def _store_disk(self, result: FeedResult) -> None:
        try:
            self._disk(result.feed.id).write_text(json.dumps({"fetchedAt": result.fetched_at.isoformat(), "skipped": result.skipped, "betting": result.betting, "headlines": [h.as_dict() for h in result.headlines]}, ensure_ascii=False), encoding="utf-8")
        except OSError as exc:
            log.warning("Could not store feed %s: %s", result.feed.id, exc)

    async def get(self, spec: FeedSpec) -> FeedResult:
        now = self._clock()
        last = self._memory.get(spec.id) or self._load_disk(spec)
        if last is not None and last.fetched_at is not None and (now - last.fetched_at).total_seconds() < FRESH_SECONDS:
            self._memory[spec.id] = last
            return last
        lock = self._locks.setdefault(spec.id, asyncio.Lock())
        async with lock:
            if time.time() < self._paused_until.get(spec.id, 0.0):
                return self._stale(spec, last, f"paused after repeated failures for {int(self._paused_until[spec.id] - time.time())} s")
            try:
                response = await self._http.get(spec.url)
            except httpx.HTTPError as exc:
                return self._failed(spec, last, f"{exc.__class__.__name__}")
            if response.status_code != 200:
                return self._failed(spec, last, f"HTTP {response.status_code}")
            body = response.content
            if not body or len(body) > MAX_BYTES:
                return self._failed(spec, last, "empty or oversized answer")
            parsed = parse_feed(body, spec, self.matcher)
            if not parsed.headlines and parsed.skipped and not parsed.betting:
                # Nothing readable. A feed whose readable headlines were all betting news is working, just empty.
                return self._failed(spec, last, "answer was not a feed")
            self._failures[spec.id] = 0
            result = FeedResult(spec, parsed.headlines, self._clock(), False, None, parsed.skipped, parsed.betting)
            self._memory[spec.id] = result
            self._store_disk(result)
            return result

    def _failed(self, spec: FeedSpec, last: FeedResult | None, reason: str) -> FeedResult:
        self._failures[spec.id] = self._failures.get(spec.id, 0) + 1
        log.warning("Feed %s failed (%s), %d in a row", spec.id, reason, self._failures[spec.id])
        if self._failures[spec.id] >= PAUSE_AFTER_FAILURES:
            self._paused_until[spec.id] = time.time() + PAUSE_SECONDS
            self._failures[spec.id] = 0
        return self._stale(spec, last, reason)

    def _stale(self, spec: FeedSpec, last: FeedResult | None, reason: str) -> FeedResult:
        if last is not None and last.fetched_at is not None:
            result = FeedResult(spec, last.headlines, last.fetched_at, True, reason, last.skipped, last.betting)
            self._memory[spec.id] = result
            return result
        return FeedResult(spec, [], None, False, reason)

    def configure(self, feeds: tuple[FeedSpec, ...], matcher: TeamMatcher | None) -> None:
        """Point the store at the team's feeds and filter (the identity resolves after start). A
        changed filter drops the remembered answers so the next read refilters a fresh copy."""
        if self.matcher is not None and matcher is not None and (matcher.names, matcher.exclude) != (self.matcher.names, self.matcher.exclude):
            self._memory.clear()
        self.feeds = feeds
        self.matcher = matcher

    async def all(self) -> list[FeedResult]:
        return list(await asyncio.gather(*(self.get(spec) for spec in self.feeds)))
