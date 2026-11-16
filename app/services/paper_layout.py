"""The paper's pages from the week's stories (FEAT-14 wave 3, the owner's boards of 2026-10-27): the app's own rule, used
until Claude lays the paper out (wave 4) and for whatever arrives after Claude's last run.

The front page: the lead (four columns) beside the rail (Inside today, By the numbers, the week's quote), then three
stories of two columns, photo first, head first, photo first, so no two headlines sit side by side; a headline-only
story gets an Also brief under it, so its column is never short. Page 2: its own lead beside eight briefs, then three
more stories. Page 3: the rest of the week's stories by subject, in three columns of even height, PER_PAGE at most.
"Only 3 pages of a paper" (the season line's Wave 6, owner 2026-11-15: "prefer articles we can copy locally and push out
anything headline only first unless there arent enough articles to make 3 pages"): page 3 takes the copied stories
first, then the headline-only ones by rank, and what is left is out of the paper (`left`). Every story in the paper
lands exactly once. Nothing here repeats the tabs or the menu (owner's marks: no skybox, no press box, no links to In
Game or the program).

Pictures, best first: the story's own photo, a related photo (another copied story's photo of the same player), the
player's headshot when the story names one of ours, else none (Claude draws one in wave 4). A photo is used once a
page.

  layout(stories, *, coach)        {front, page2, more, order, count}
  folded_weeks(...)                the earlier weeks' rows: week, the week of, opponent, the lead or the final, record
  LayoutStore(data_dir, season)    the last layout of each week, for the reader's Story n of N and Next in the paper
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, tzinfo
from pathlib import Path
from typing import Any

from app.services.answers import atomic_write
from app.services.editions import KEY, OFFSEASON_KEY, label_for, order_of

log = logging.getLogger("kickoff.paper_layout")

PAGE2_BRIEFS = 8
PER_PAGE = 24  # stories on page 3, the paper's last (Wave 6: three pages at most)
LINE_CHARS = 30  # a brief's headline, about 30 characters a line in a two-column cell on the iPad upright
QUOTE_WORDS = (6, 28)

KICKERS = {
    "game": "The game",
    "coach": "The coach",
    "injury": "Availability",
    "recruiting": "Recruiting",
    "rankings": "Rankings",
    "trophy": "The race",
    "scoreboard": "The last game",
    "practice": "Practice",
    "stadium": "Around the program",
    "nfl": "In the NFL",  # 2.0: the kicker names no team
    "weather": "Weather",
}
SECTIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("The game", ("game", "scoreboard")),
    ("The coach and the team", ("coach", "practice", "injury")),
    ("Rankings and bowls", ("rankings", "trophy")),
    ("Recruiting", ("recruiting",)),
    ("Around the program", ("stadium", "weather", "nfl")),
)
OTHER_SECTION = "More from the week"


def _words(text: Any) -> int:
    return len(str(text or "").split())


def _when(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _story(row: dict[str, Any]) -> dict[str, Any]:
    """What the page needs of a story (the edition's annotated headline)."""
    topic = row.get("topic") if isinstance(row.get("topic"), str) else "game"
    return {
        "id": row.get("id"),
        "title": str(row.get("title") or "").strip(),
        "source": str(row.get("source") or ""),
        "publishedAt": row.get("publishedAt") if isinstance(row.get("publishedAt"), str) else None,
        "url": row.get("url") if isinstance(row.get("url"), str) else None,
        "topic": topic,
        "kicker": row["kicker"].strip() if isinstance(row.get("kicker"), str) and row["kicker"].strip() else KICKERS.get(topic, "The week"),
        "app": row.get("app") is True,  # Wave 6: the paper's own article (By the numbers)
        "copied": row.get("copied") is True,
        "opening": [p for p in row.get("opening") or [] if isinstance(p, str)][:8],
        "author": row.get("author") if isinstance(row.get("author"), str) else None,
        "words": row.get("words") if isinstance(row.get("words"), int) else 0,
        "players": [p for p in row.get("players") or [] if isinstance(p, dict)],
        "photo": row.get("photo") if isinstance(row.get("photo"), str) else None,
        "cutline": row.get("cutline") if isinstance(row.get("cutline"), str) else None,
        "credit": row.get("credit") if isinstance(row.get("credit"), str) else None,
    }


def score(story: dict[str, Any]) -> float:
    """A story's rank on the page: a copied story with its photo first, then a copied one, then headlines; our game
    and our coach a little ahead; within those, the longer and the team's own site."""
    value = 3.0 if story["copied"] and story["photo"] else 2.0 if story["copied"] else 1.0
    if story["topic"] in ("game", "coach", "scoreboard", "injury"):
        value += 0.5
    if story["words"] >= 300:
        value += 0.2
    if "athletics" in story["source"].lower():
        value += 0.2
    return value


class _Pictures:
    """The picture each story gets, a photo used once a page."""

    def __init__(self, stories: list[dict[str, Any]], art: dict[str, dict[str, Any]] | None = None) -> None:
        self.art = art or {}
        self.by_player: dict[Any, dict[str, Any]] = {}
        for s in stories:
            if s["copied"] and s["photo"]:
                for p in s["players"]:
                    self.by_player.setdefault(p.get("playerId"), s)
        self.used: set[str] = set()

    def new_page(self) -> None:
        self.used = set()

    def for_story(self, story: dict[str, Any]) -> dict[str, Any] | None:
        if story["photo"] and story["photo"] not in self.used:
            self.used.add(story["photo"])
            return {"kind": "photo", "src": story["photo"], "cutline": story["cutline"], "credit": story["credit"]}
        for p in story["players"]:
            other = self.by_player.get(p.get("playerId"))
            if other is not None and other["id"] != story["id"] and other["photo"] not in self.used:
                self.used.add(other["photo"])
                return {"kind": "related", "src": other["photo"], "cutline": other["cutline"], "credit": other["credit"], "from": other["title"]}
        for p in story["players"]:
            pid = str(p.get("playerId") or "")
            if pid.isdigit() and len(pid) <= 12 and p.get("isUs", True) is not False:
                src = f"/media/headshot/{pid}"
                if src not in self.used:
                    self.used.add(src)
                    return {"kind": "headshot", "src": src, "cutline": p.get("name"), "credit": None}
        drawn = self.art.get(story["id"])
        if isinstance(drawn, dict) and isinstance(drawn.get("src"), str):  # wave 4: Claude's drawing, last of all
            return {"kind": "drawn", "src": drawn["src"], "cutline": drawn.get("caption"), "credit": "Illustration: Claude Code"}
        return None


def _height(story: dict[str, Any]) -> int:
    """A brief's estimated height in pixels: its headline's lines, the source line, the padding."""
    lines = max(1, -(-len(story["title"]) // LINE_CHARS))
    return lines * 19 + 17 + 25


def _section_of(story: dict[str, Any]) -> str:
    return next((name for name, topics in SECTIONS if story["topic"] in topics), OTHER_SECTION)


def _columns(stories: list[dict[str, Any]], named: dict[str, str] | None = None) -> list[list[dict[str, Any]]]:
    """Three columns of even height from stories in section order; a column starting mid-section repeats its name."""
    items: list[tuple[str, dict[str, Any]]] = [((named or {}).get(s["id"]) or _section_of(s), s) for s in stories]
    heights = [_height(s) for _, s in items]
    total = sum(heights) + 30 * len({name for name, _ in items})
    target = total / 3
    columns: list[list[dict[str, Any]]] = [[]]
    filled = 0
    current_section: str | None = None
    for (name, story), height in zip(items, heights, strict=True):
        if len(columns) < 3 and filled + height / 2 > target and columns[-1]:
            columns.append([])
            filled = 0
            current_section = None
        if name != current_section:
            columns[-1].append({"section": name})
            filled += 30
            current_section = name
        columns[-1].append(story)
        filled += height
    while len(columns) < 3:
        columns.append([])
    return columns


def find_quote(stories: list[dict[str, Any]], coach: str | None) -> dict[str, Any] | None:
    """A short quote by our head coach from this week's copied stories, newest first; None without one."""
    if not coach or not coach.strip():
        return None
    surname = coach.strip().split()[-1]
    pattern = re.compile(r"[“\"]([^”\"]{20,220})[”\"]")
    for story in stories:
        if not story["copied"]:
            continue
        for paragraph in story["opening"]:
            if surname not in paragraph or not re.search(r"\bsaid\b|\bsays\b", paragraph):
                continue
            for found in pattern.finditer(paragraph):
                text = found.group(1).strip().rstrip(",")
                if QUOTE_WORDS[0] <= _words(text) <= QUOTE_WORDS[1]:
                    return {"text": text if text.endswith((".", "!", "?")) else text + ".", "who": coach.strip(), "storyId": story["id"], "publishedAt": story["publishedAt"]}
    return None


def editor_plan(answer: Any, stories: dict[str, dict[str, Any]], coach: str | None) -> dict[str, Any] | None:
    """Claude's layout, every id checked against the week's stories (one it made up is dropped), the numbers and the quote
    checked too: a number must name a story of the week, the quote must be word for word in that story's copied text."""
    if not isinstance(answer, dict):
        return None

    def known(i: Any) -> bool:
        return isinstance(i, str) and i in stories

    lead = answer.get("lead") if known(answer.get("lead")) else None
    front = [i for i in dict.fromkeys(answer.get("front") or []) if known(i) and i != lead][:3]
    page2 = answer.get("page2Lead") if known(answer.get("page2Lead")) and answer.get("page2Lead") not in (lead, *front) else None
    named: dict[str, str] = {}
    order: list[str] = []
    for section in answer.get("sections") or []:
        if not isinstance(section, dict) or not isinstance(section.get("name"), str) or not section["name"].strip():
            continue
        name = section["name"].strip()[:40]
        for i in section.get("stories") or []:
            if known(i) and i not in named:
                named[i] = name
                if name not in order:
                    order.append(name)
    kickers = {i: w.strip()[:30] for i, w in (answer.get("kickers") or {}).items() if known(i) and isinstance(w, str) and w.strip()}
    numbers = [
        {"big": n["big"].strip()[:16], "words": n["words"].strip()[:90], "storyId": n.get("storyId")}
        for n in answer.get("numbers") or []
        if isinstance(n, dict) and isinstance(n.get("big"), str) and n["big"].strip() and isinstance(n.get("words"), str) and n["words"].strip() and (n.get("storyId") is None or known(n.get("storyId")))
    ][:4]
    quote = None
    q = answer.get("quote") if isinstance(answer.get("quote"), dict) else {}
    if known(q.get("storyId")) and isinstance(q.get("text"), str) and coach:
        source = stories[q["storyId"]]

        def flat(t: str) -> str:
            return " ".join(re.sub("[\u201c\u201d\"]", "", t).split())

        said = q["text"].strip().strip("\u201c\u201d\"")
        if source["copied"] and QUOTE_WORDS[0] <= _words(said) <= 40 and flat(said) in flat(" ".join(source["opening"])):
            quote = {"text": said if said.endswith((".", "!", "?")) else said + ".", "who": coach.strip(), "storyId": q["storyId"], "publishedAt": source["publishedAt"]}
    if not (lead or front or page2 or named):
        return None
    return {"lead": lead, "front": front, "page2": page2, "named": named, "sectionOrder": order, "kickers": kickers, "numbers": numbers, "quote": quote, "drawings": [i for i in answer.get("drawings") or [] if known(i)]}


def _row(pool: list[dict[str, Any]], pictures: _Pictures, chosen_ids: list[str] | None = None, reserved: set[str] | None = None) -> list[dict[str, Any]]:
    """Three cells, as on the board: the best two stories left outside (photo first), the best headline-only story in the
    middle (head first), so the copied stories also feed page 2's lead; a headline-only story takes an Also brief under
    it (the same subject first). Takes them out of `pool`."""
    picked = [s for i in chosen_ids or [] for s in pool if s["id"] == i][:3]  # wave 4: the editor's three, in its order
    if picked:
        for s in picked:
            pool.remove(s)
        middle = next((s for s in picked if not s["copied"]), None)
        if middle is not None and len(picked) == 3:
            picked.remove(middle)
            picked.insert(1, middle)  # the head-first story in the middle, still
        chosen = picked
    else:
        held = reserved or set()
        outer = [s for s in pool if s["id"] not in held][:2] or pool[:2]  # a story Claude put on page 3 stays there if it can
        for s in outer:
            pool.remove(s)
        middle = next((s for s in pool if not s["copied"] and s["id"] not in held), None) or next((s for s in pool if not s["copied"]), None) or (pool[0] if pool else None)
        if middle is not None:
            pool.remove(middle)
        chosen = [s for s in (outer[0] if outer else None, middle, outer[1] if len(outer) > 1 else None) if s is not None]
    cells = []
    for i, story in enumerate(chosen):
        picture = pictures.for_story(story)
        also = None
        if not story["copied"]:
            spare = sorted((s for s in pool if not s["copied"]), key=lambda s: s["id"] in (reserved or set()))  # Claude's page 3 picks last
            also = next((s for s in spare if s["topic"] == story["topic"]), None) or (spare[0] if spare else None)
            if also is not None:
                pool.remove(also)
        cells.append({"story": story, "picture": picture, "first": "photo" if picture and i != 1 else "head", "also": also})
    return cells


def layout(rows: Any, *, coach: str | None = None, editor: Any = None, art: dict[str, dict[str, Any]] | None = None, page2_lead: str | None = None) -> dict[str, Any]:
    """The week's pages from its annotated headlines (newest first); Claude's plan first when there is one (wave 4), the
    app's rule for everything it did not place (stories that arrived after its run among them). `page2_lead` (Wave 6): the
    id of the paper's own article, which leads page 2 and never the front page."""
    seen: set[str] = set()
    stories: list[dict[str, Any]] = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not str(row.get("title") or "").strip():
            continue
        if row.get("topic") == "other-sport" or row["id"] in seen:
            continue
        seen.add(row["id"])
        stories.append(_story(row))
    ranked = sorted(stories, key=lambda s: (score(s), _when(s["publishedAt"])), reverse=True)
    plan = editor_plan(editor, {s["id"]: s for s in stories}, coach)
    if plan is not None:
        for s in stories:
            if s["id"] in plan["kickers"]:
                s["kicker"] = plan["kickers"][s["id"]]
    pictures = _Pictures(stories, art)
    quote = (plan or {}).get("quote") or find_quote(sorted(stories, key=lambda s: _when(s["publishedAt"]), reverse=True), coach)
    pool = list(ranked)
    reserved = set((plan or {}).get("named") or {})
    own = next((s for s in pool if s["id"] == page2_lead), None) if page2_lead else None
    if own is not None:
        pool.remove(own)  # Wave 6: the paper's own article waits for page 2's lead

    def take_lead(wanted: str | None = None) -> dict[str, Any] | None:
        chosen = next((s for s in pool if s["id"] == wanted), None) if wanted else None
        lead = chosen or next((s for s in pool if s["copied"] and s["photo"]), None) or next((s for s in pool if s["copied"]), None) or (pool[0] if pool else None)
        if lead is not None:
            pool.remove(lead)
        return lead

    def take_briefs(n: int) -> list[dict[str, Any]]:
        """The rail's briefs: the best headline-only stories left (they have no text to run), then the best others."""
        keep_for_page3 = lambda s: s["id"] in reserved  # noqa: E731 - a story Claude put in a page 3 section stays there if it can
        out = sorted((s for s in pool if not s["copied"]), key=keep_for_page3)[:n]
        if len(out) < n:
            out += sorted((s for s in pool if s not in out), key=keep_for_page3)[: n - len(out)]
        for s in out:
            pool.remove(s)
        return sorted(out, key=lambda s: _when(s["publishedAt"]), reverse=True)

    front_lead = take_lead((plan or {}).get("lead"))
    front_picture = pictures.for_story(front_lead) if front_lead else None
    front_row = _row(pool, pictures, (plan or {}).get("front"), reserved)
    # a lead with no copied text (nothing copied yet this week): briefs run in its two columns, so the rail has no hole
    lead_briefs = take_briefs(6) if front_lead is not None and not front_lead["copied"] else []
    pictures.new_page()
    page2: dict[str, Any] | None = None
    if pool or own is not None:
        lead2 = own or take_lead((plan or {}).get("page2"))
        picture2 = pictures.for_story(lead2) if lead2 else None
        row2 = _row(pool, pictures, None, reserved) if pool else []
        briefs2 = take_briefs(PAGE2_BRIEFS)
        page2 = {"lead": lead2, "picture": picture2, "briefs": briefs2, "row": row2}
    named = (plan or {}).get("named") or {}
    names_in_order = [*((plan or {}).get("sectionOrder") or []), *[name for name, _ in SECTIONS], OTHER_SECTION]

    def section_name(s: dict[str, Any]) -> str:
        return named.get(s["id"]) or _section_of(s)  # Claude's section, else the rule's

    # Wave 6 (owner 2026-11-15): page 3 is the last; the copied stories first, then the headline-only ones by rank (those
    # Claude put in a page 3 section before the rest), and what does not fit is left out of the paper
    kept = sorted(pool, key=lambda s: (s["copied"], s["id"] in reserved, score(s), _when(s["publishedAt"])), reverse=True)[:PER_PAGE]
    left = [s for s in pool if s not in kept]
    rest = sorted(kept, key=lambda s: names_in_order.index(section_name(s)) if section_name(s) in names_in_order else len(names_in_order))
    more = [{"page": 3, "name": "The rest of the week", "count": len(rest), "columns": _columns(rest, named)}] if rest else []
    order: list[str] = []

    def add(story: dict[str, Any] | None) -> None:
        if story is not None and story["id"] not in order:
            order.append(story["id"])

    add(front_lead)
    for s in lead_briefs:
        add(s)
    for cell in front_row:
        add(cell["story"])
        add(cell["also"])
    if page2:
        add(page2["lead"])
        for cell in page2["row"]:
            add(cell["story"])
            add(cell["also"])
        for s in page2["briefs"]:
            add(s)
    for page in more:
        for column in page["columns"]:
            for item in column:
                if "id" in item:
                    add(item)
    inside = []
    if page2:
        for story in [page2["lead"], *[c["story"] for c in page2["row"]]]:
            if story is not None:
                inside.append({"page": 2, "id": story["id"], "words": story["title"]})
    if more:
        count = sum(p["count"] for p in more)
        inside.append({"page": more[0]["page"], "id": None, "words": f"{count} more of the week's {'story' if count == 1 else 'stories'}"})
    return {
        "front": {"lead": front_lead, "picture": front_picture, "leadBriefs": lead_briefs, "row": front_row, "inside": inside, "quote": quote, "numbers": (plan or {}).get("numbers") or []},
        "page2": page2,
        "more": more,
        "order": order,
        "count": len(order),
        "left": len(left),  # Wave 6: the stories past page 3, out of the paper
        "stories": {s["id"]: {"title": s["title"], "source": s["source"], "publishedAt": s["publishedAt"], "copied": s["copied"], "url": s["url"], "section": named.get(s["id"]) or _section_of(s)} for s in stories if s["id"] in order},
        "by": "Claude Code" if plan is not None else "the app",
        "drawings": (plan or {}).get("drawings") or [],
    }


# --- the earlier weeks, folded ---------------------------------------------------------------------------------


def _iso_date(value: Any, tz: tzinfo) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(tz) if parsed.tzinfo else parsed.replace(tzinfo=tz)


def folded_weeks(editions: Any, games: Any, team: str, current: str | None, *, tz: tzinfo, leads: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """The earlier weeks' rows, newest first: {key, week, label, weekOf, opponent, homeAway, final, won, record, lead}.
    The final and the record come from our schedule; a bye week's lead from its saved paper (`leads`)."""
    ours = sorted(
        (g for g in games or [] if getattr(g, "start_date", None) and team in (getattr(g, "home_team", None), getattr(g, "away_team", None))),
        key=lambda g: g.start_date,
    )
    out: list[dict[str, Any]] = []
    for e in editions if isinstance(editions, list) else []:
        if not isinstance(e, dict) or not isinstance(e.get("key"), str) or e.get("current") or e.get("future") or e["key"] == current:
            continue
        week = e.get("week") if isinstance(e.get("week"), int) else None
        if week is None:
            match = re.match(r"^week-(\d{1,2})(?:-sunday)?$", e["key"])
            week = int(match.group(1)) if match else None
        post = e["key"].startswith("postseason")
        sunday = e["key"].endswith("-sunday")  # Wave 6: a game's Sunday paper folds under its week's, with the same game
        game = next((g for g in ours if getattr(g, "week", None) == week and (getattr(g, "season_type", None) or "regular") == ("postseason" if post else "regular")), None)
        end = _iso_date(e.get("weekEnd"), tz)
        kickoff = _iso_date(getattr(game, "start_date", None), tz) if game is not None else None
        anchor = kickoff or (end - timedelta(days=2) if end else None)
        monday = (anchor - timedelta(days=anchor.weekday())).date() if anchor else None
        won = None
        final = None
        if game is not None and getattr(game, "completed", False) and isinstance(game.home_points, int) and isinstance(game.away_points, int):
            home = game.home_team == team
            us_pts, them_pts = (game.home_points, game.away_points) if home else (game.away_points, game.home_points)
            opponent = game.away_team if home else game.home_team
            won = us_pts > them_pts
            final = f"{team} {us_pts}, {opponent} {them_pts}" if won else f"{opponent} {them_pts}, {team} {us_pts}"
        cutoff = kickoff or anchor
        played = [g for g in ours if getattr(g, "completed", False) and isinstance(g.home_points, int) and isinstance(g.away_points, int) and (cutoff is None or _iso_date(g.start_date, tz) <= cutoff)]
        wins = sum(1 for g in played if (g.home_points > g.away_points) == (g.home_team == team) and g.home_points != g.away_points)
        losses = sum(1 for g in played if g.home_points != g.away_points) - wins
        out.append(
            {
                "key": e["key"],
                "week": week,
                "sunday": sunday,
                "label": e.get("label") or label_for(e["key"]),
                "weekOf": monday.isoformat() if monday else None,
                "opponent": e.get("opponent") or (game.away_team if game is not None and game.home_team == team else game.home_team if game is not None else None),
                "homeAway": e.get("homeAway"),
                "final": final,
                "won": won,
                "record": f"{wins}-{losses}" if played else None,
                "lead": ((leads or {}).get(e["key"]) or final) if sunday else (final or (leads or {}).get(e["key"])),  # a Sunday paper by its lead story
                "bye": game is None,
            }
        )
    out.sort(key=lambda r: order_of(r["key"]), reverse=True)  # newest first, a Sunday paper over its week's
    return out


def lead_title(rows: Any) -> str | None:
    """A week's lead story as the rule picks it, for a folded bye week's row."""
    built = layout(rows)
    lead = built["front"]["lead"]
    return lead["title"] if lead else None


# --- the last layout of each week, for the reader ----------------------------------------------------------------


class LayoutStore:
    def __init__(self, data_dir: Path, season: int) -> None:
        self.dir = Path(data_dir) / "season" / str(int(season)) / "paper"
        self._last: dict[str, str] = {}

    def save(self, key: Any, built: dict[str, Any]) -> None:
        if not isinstance(key, str) or not (KEY.match(key) or OFFSEASON_KEY.match(key)):
            return
        slim = {"key": key, "order": built.get("order") or [], "stories": built.get("stories") or {}}
        text = json.dumps(slim, ensure_ascii=False, sort_keys=True)
        if self._last.get(key) == text:
            return
        try:
            atomic_write(self.dir / f"layout-{key}.json", text)
            self._last[key] = text
            if OFFSEASON_KEY.match(key):  # rollover R3: the off-season paper is not kept, so the last week's order goes
                for old in self.dir.glob("layout-offseason-*.json"):
                    if old.name != f"layout-{key}.json":
                        old.unlink(missing_ok=True)
        except OSError as exc:
            log.warning("Could not keep the paper's order for %s: %s", key, exc)

    def load(self, key: str) -> dict[str, Any] | None:
        if not (KEY.match(key) or OFFSEASON_KEY.match(key)):
            return None
        path = self.dir / f"layout-{key}.json"
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return raw if isinstance(raw, dict) and isinstance(raw.get("order"), list) else None

    def keys(self) -> list[str]:
        try:
            names = [p.stem.removeprefix("layout-") for p in self.dir.glob("layout-*.json")]
        except OSError:
            return []
        return sorted((k for k in names if KEY.match(k) or OFFSEASON_KEY.match(k)), key=order_of, reverse=True)

    def place(self, sid: str) -> dict[str, Any] | None:
        """Where a story sits: its week, position and count, the stories before and after, the same section's others."""
        for key in self.keys():
            built = self.load(key)
            if built is None or sid not in built["order"]:
                continue
            order = [i for i in built["order"] if isinstance(i, str)]
            stories = built.get("stories") if isinstance(built.get("stories"), dict) else {}
            at = order.index(sid)

            def brief(i: str, stories: dict[str, Any] = stories) -> dict[str, Any]:
                s = stories.get(i) if isinstance(stories.get(i), dict) else {}
                return {"id": i, "title": s.get("title"), "source": s.get("source"), "publishedAt": s.get("publishedAt"), "copied": s.get("copied") is True, "url": s.get("url")}

            section = (stories.get(sid) or {}).get("section")
            related = [brief(i) for i in order if i != sid and (stories.get(i) or {}).get("section") == section][:6]
            return {
                "key": key,
                "label": label_for(key),
                "position": at + 1,
                "count": len(order),
                "prev": brief(order[at - 1]) if at > 0 else None,
                "next": brief(order[at + 1]) if at + 1 < len(order) else None,
                "section": section,
                "related": related,
            }
        return None


def needs_drawing(built: Any, limit: int = 2) -> list[dict[str, Any]]:
    """The stories Claude should draw for (wave 4): the front page's and page 2's placed stories with no picture of any
    kind, the editor's own picks first; at most `limit` a run."""
    if not isinstance(built, dict):
        return []
    front = built.get("front") if isinstance(built.get("front"), dict) else {}
    page2 = built.get("page2") if isinstance(built.get("page2"), dict) else {}
    placed: list[tuple[Any, Any]] = [(front.get("lead"), front.get("picture")), *((c.get("story"), c.get("picture")) for c in front.get("row") or [] if isinstance(c, dict))]
    if page2:
        placed += [(page2.get("lead"), page2.get("picture")), *((c.get("story"), c.get("picture")) for c in page2.get("row") or [] if isinstance(c, dict))]
    bare = [story for story, picture in placed if isinstance(story, dict) and story.get("id") and not picture]
    picks = set(built.get("drawings") or [])
    bare.sort(key=lambda story: story["id"] not in picks)
    return bare[:limit]
