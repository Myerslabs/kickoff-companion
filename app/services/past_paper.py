"""A past season's paper, read only (rollover R3; owner 2026-11-15: "A Seasons list", "The book and its games", "Build all of
R3"). After the switch the paper's own service is the new season's: its stores, its calendar, its archive, and it saves
each edition's layout as it reads it. A past season's paper is built here instead, from that season's kept files alone:
the edition as kept (frozen at the switch), its stories as copied, Claude's layout and drawings of that week, the paper's
own article, the coach of that season. Nothing is fetched and nothing is written.

    past_paper(data_dir, season, team, key) -> {"season", "editions": [...], "edition": {...} | None}
    with_season(value, season) -> the same structure, each drawing's address carrying ?season=<year>
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.services import paper_articles
from app.services.articles import ArticleStore
from app.services.editions import Editions, is_sunday
from app.services.paper_art import ArtStore
from app.services.paper_layout import layout
from app.services.season_notes import SeasonNotes
from app.services.writing import WritingStore

log = logging.getLogger("kickoff.paper")

ART_PREFIX = "/media/paper-art/"


def with_season(value: Any, season: int) -> Any:
    """Every drawing's address in a layout made to read that season's drawings (/media/paper-art/<id>.svg?season=2026)."""
    if isinstance(value, dict):
        return {k: (f"{v}?season={int(season)}" if k == "src" and isinstance(v, str) and v.startswith(ART_PREFIX) and "?" not in v else with_season(v, season)) for k, v in value.items()}
    if isinstance(value, list):
        return [with_season(v, season) for v in value]
    return value


def past_paper(data_dir: Path, season: int, team: str, key: str | None = None) -> dict[str, Any]:
    editions = Editions(Path(data_dir), int(season))
    listed = editions.keys()
    keys = [e["key"] for e in listed]
    chosen = key if key in keys else None if key else (keys[-1] if keys else None)  # no week asked: the season's last paper; one never kept: none
    out: dict[str, Any] = {"season": int(season), "past": int(season), "editions": [{**e, "saved": True, "current": e["key"] == chosen} for e in listed], "edition": None}
    if chosen is None:
        return out
    saved = editions.load(chosen)
    if saved is None:
        return out
    store = ArticleStore(Path(data_dir), int(season))
    rows = store.annotate(saved.get("headlines"))
    try:
        coach = (SeasonNotes(Path(data_dir), int(season)).coaches_for(team) or {}).get("headCoach")
    except Exception:  # noqa: BLE001 - the coach is a courtesy on the front page; logged
        log.warning("The %s coach could not be read for the past paper", season, exc_info=True)
        coach = None
    own = None if is_sunday(chosen) else paper_articles.row(store, "numbers", chosen)  # By the numbers leads a week's page 2
    editor = WritingStore(Path(data_dir), int(season)).load("editor", chosen)
    art = ArtStore(Path(data_dir), int(season)).drawn()
    built = layout(rows + ([own] if own else []), coach=coach if isinstance(coach, str) else None, editor=editor, art=art, page2_lead=own["id"] if own else None)
    out["edition"] = {**saved, "headlines": rows, "layout": with_season(built, int(season)), "current": False, "past": int(season)}
    return out
