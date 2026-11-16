"""The Newspaper's reader (FEAT-14, owner board 2026-10-27): one copied story, whole, from this computer's own copy.

GET /api/paper/story/{id}   the story as copied: headline, source, author, date, paragraphs, photo, cutline and credit,
                            the read time and the publisher's link; 404 for a story that stayed headline only
GET /api/paper/status       what the copier has done: stories copied, headline only, waiting, sites paused or refusing

Reads of data/season/<year>/paper/articles/; no call to any site of its own."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request

from app.api.envelope import envelope, error_response
from app.services.articles import STORY_ID, ArticleCopier, ArticleStore, host_of
from app.services.paper_layout import LayoutStore

router = APIRouter(tags=["paper"])

WORDS_A_MINUTE = 230


@router.get("/api/paper/story/{sid}")
async def story(sid: str, request: Request, season: int | None = Query(None, ge=2000, le=2999)) -> Any:
    copier: ArticleCopier = request.app.state.articles
    if not STORY_ID.match(sid):
        return error_response(404, "not_found", "No story with that id.")
    past = season if season is not None and season != request.app.state.settings.season else None  # rollover R3: a past season's paper
    store = ArticleStore(request.app.state.settings.data_dir, past) if past is not None else copier.store
    article = store.get(sid)
    if article is None:
        return error_response(404, "not_found", "That story is not on this server.")
    if article.outcome != "copied" or not article.paragraphs:
        return error_response(404, "headline_only", article.reason or "Only the headline of this story is on this server.")
    return envelope(
        {
            "id": article.id,
            "title": article.title,
            "source": article.source,
            "author": article.author,
            "publishedAt": article.publishedAt,
            "url": article.url,
            "host": host_of(article.url).removeprefix("www."),
            "paragraphs": article.paragraphs,
            "photo": f"/media/paper/{article.photo}" if article.photo else None,
            "cutline": article.cutline,
            "credit": article.credit,
            "words": article.words,
            "readMinutes": max(1, round(article.words / WORDS_A_MINUTE)),
            "copiedAt": article.copiedAt,
            # FEAT-14 wave 3: where it sits in its week's paper (Story n of N, the stories either side, the same section)
            "paper": _place(request, article.id, past),
            "season": past,
        },
        source="cache",
    )


def _place(request: Request, sid: str, past: int | None) -> dict[str, Any] | None:
    if past is not None:
        return LayoutStore(request.app.state.settings.data_dir, past).place(sid)  # read only: that season's layouts as kept
    return request.app.state.rankedweek.layouts.place(sid) if getattr(request.app.state, "rankedweek", None) is not None else None


@router.get("/api/paper/status")
async def status(request: Request) -> Any:
    copier: ArticleCopier = request.app.state.articles
    return envelope(copier.status(), source="cache")
