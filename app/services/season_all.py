"""One paste for every conference (Phase 19, owner 2026-10-08: the coaches prompt and the roster salary prompt are their own
cards in Settings, each one prompt and one paste). The per-conference prompts of Phase 17 stay on the Preseason page; these
cover every FBS conference at once and split the answer by conference when it is saved.

    coaches_all_prompt(data_dir, conferences=, season=) / costs_all_prompt(data_dir, conferences=, detailed=, season=)
    read_coaches_all(text, conferences) / read_costs_all(text, conferences)  -> Reading, value {conference: batch}
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.services.answers import keys_score, read_json
from app.services.season_notes import CoachesBatch, CostsBatch
from app.services.season_prompts import MAX_ANSWER, Reading, coaches_shape, costs_shape, template


def _groups(conferences: dict[str, list[str]]) -> list[str]:
    """One line a conference, "Conference: School; School"."""
    return [f"{conference}: " + "; ".join(names) for conference, names in sorted(conferences.items())]


def _first(conferences: dict[str, list[str]]) -> str:
    return next(iter(next(iter(conferences.values()), [])), "School")


def coaches_all_prompt(data_dir: Path, *, conferences: dict[str, list[str]], season: int) -> str:
    listing = "\n".join(f"- {line}" for line in _groups(conferences))
    return template("coaches", data_dir).fill({"season": season, "conference": "every FBS conference", "schools": listing, "shape": coaches_shape("Conference name", _first(conferences))})


def costs_all_prompt(data_dir: Path, *, conferences: dict[str, list[str]], detailed: list[str], season: int) -> str:
    listing = "\n".join(f"- {line}" for line in _groups(conferences))
    detail = "\n".join(f"- {s}" for s in detailed) if detailed else "- (none)"
    return template("costs", data_dir).fill({"season": season, "conference": "every FBS conference", "schools": listing, "detailed": detail, "shape": costs_shape("Conference name", _first(conferences))})


def _split(rows: list[Any], conferences: dict[str, list[str]]) -> tuple[dict[str, list[Any]], list[str]]:
    index = {s.lower(): conference for conference, names in conferences.items() for s in names}
    by_conference: dict[str, list[Any]] = {}
    unknown: list[str] = []
    for row in rows:
        conference = index.get(str(row.school).strip().lower())
        if conference is None:
            unknown.append(str(row.school))
        else:
            by_conference.setdefault(conference, []).append(row)
    return by_conference, unknown


def _left_out(unknown: list[str]) -> str:
    return f"Not FBS teams this season, so left out: {', '.join(unknown[:6])}{'…' if len(unknown) > 6 else ''}."


def read_coaches_all(text: Any, conferences: dict[str, list[str]]) -> Reading:
    parsed = read_json(text, CoachesBatch, keys_score(("teams", "conference")), max_chars=MAX_ANSWER, what="a coaches answer", keys_text="teams")
    if parsed.value is None:
        return Reading(None, error=parsed.error)
    batch: CoachesBatch = parsed.value
    warnings = list(parsed.warnings)
    rows, unknown = _split([t for t in batch.teams if any((t.headCoach, t.offensiveCoordinator, t.defensiveCoordinator))], conferences)
    if not rows:
        return Reading(None, warnings=warnings, error="None of the teams in the answer is an FBS team with a coach named.")
    if unknown:
        warnings.append(_left_out(unknown))
    named = sum(len(v) for v in rows.values())
    total = sum(len(v) for v in conferences.values())
    if named < total:
        warnings.append(f"Coaches for {named} of {total} teams; the rest stay empty.")
    if not batch.sources:
        warnings.append("No sources are listed. Ask the chat for the pages it used.")
    out = {conference: CoachesBatch(conference=conference, season=batch.season, author=batch.author, teams=teams, sources=batch.sources) for conference, teams in rows.items()}
    return Reading(out, {"teams": named, "of": total}, warnings)


def read_costs_all(text: Any, conferences: dict[str, list[str]]) -> Reading:
    parsed = read_json(text, CostsBatch, keys_score(("teams", "conference")), max_chars=MAX_ANSWER, what="a roster-costs answer", keys_text="teams")
    if parsed.value is None:
        return Reading(None, error=parsed.error)
    batch: CostsBatch = parsed.value
    warnings = list(parsed.warnings)
    rows, unknown = _split(list(batch.teams), conferences)
    if not rows:
        return Reading(None, warnings=warnings, error="None of the teams in the answer is an FBS team.")
    if unknown:
        warnings.append(_left_out(unknown))
    figures = sum(1 for teams in rows.values() for t in teams if t.totalUsd is not None)
    if not figures:
        warnings.append("No team total was found; saved anyway, so the page shows they were looked for.")
    if not batch.sources and not any(t.sources for teams in rows.values() for t in teams):
        warnings.append("No sources are listed. Ask the chat for the pages it used.")
    out = {conference: CostsBatch(conference=conference, season=batch.season, author=batch.author, teams=teams, sources=batch.sources) for conference, teams in rows.items()}
    return Reading(out, {"teams": sum(len(v) for v in rows.values()), "totals": figures}, warnings)
