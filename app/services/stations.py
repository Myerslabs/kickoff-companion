"""Radio for any team (public release Phase 5b, owner direction 2026-10-03: no research up front; the list
grows as people ask for their team's station).

Three places a station can come from, in this order (the order sets each source's id, so ids already saved
on a device never move):
1. RADIO_SOURCES in .env (this install's own).
2. Stations added in Settings (`radioStations` in data/settings.json), each with the team it belongs to.
3. The station list in the repo (app/radio_stations.json), entries for my primary teams only. It starts
   empty; a station is added when someone asks with the "Request your team's radio" button, which opens a
   GitHub issue form in the public repo (.github/ISSUE_TEMPLATE/radio-station.yml).

For a team with no station the app offers search links to find the broadcast, and the request button.
Radio plays only through official embeds, streams or links; nothing is scraped."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any
from urllib.parse import quote, quote_plus

from pydantic import ValidationError

from app.config import Settings
from app.services.prefs import SavedStation

log = logging.getLogger("kickoff.stations")

STATIONS_FILE = Path(__file__).resolve().parent.parent / "radio_stations.json"
REPO_URL = "https://github.com/Myerslabs/kickoff-companion"
ISSUE_TEMPLATE = "radio-station.yml"


def known_stations(path: Path | None = None) -> list[SavedStation]:
    """The repo's station list. A missing file is an empty list; a bad entry is skipped and logged."""
    path = path or STATIONS_FILE
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        log.warning("The radio station list %s could not be read: %s", path.name, exc)
        return []
    entries = raw.get("stations") if isinstance(raw, dict) else None
    if not isinstance(entries, list):
        log.warning("The radio station list %s has no stations list", path.name)
        return []
    out: list[SavedStation] = []
    skipped = 0
    for entry in entries:
        try:
            station = SavedStation(**entry) if isinstance(entry, dict) else None
        except ValidationError:
            station = None
        if station is None or not station.team:
            skipped += 1
            continue
        out.append(station)
    if skipped:
        log.warning("Skipped %d bad entr%s in the radio station list %s", skipped, "y" if skipped == 1 else "ies", path.name)
    return out


def combined(settings: Settings, saved: list[SavedStation], primaries: list[str], listed: list[SavedStation] | None = None) -> list[dict[str, Any]]:
    """Every source the radio offers, in id order, as {name, kind, url, team, origin}. A station whose
    address is already offered is not offered twice."""
    listed = known_stations() if listed is None else listed
    wanted = {p.lower() for p in primaries if p}
    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(name: str, kind: str, url: str, team: str | None, origin: str) -> None:
        if url in seen:
            return
        seen.add(url)
        out.append({"name": name, "kind": kind, "url": url, "team": team, "origin": origin})

    for source in settings.radio_sources:
        add(source.name, source.kind, source.url, None, "env")
    for station in saved:
        add(station.name, station.kind, station.url, station.team, "settings")
    for station in listed:
        if station.team and station.team.lower() in wanted:
            add(station.name, station.kind, station.url, station.team, "list")
    return out


def request_url(school: str | None) -> str:
    """The GitHub issue form asking for a team's station, with the school filled in."""
    url = f"{REPO_URL}/issues/new?template={ISSUE_TEMPLATE}"
    if school:
        url += f"&title={quote('Radio station: ' + school)}&school={quote(school)}"
    return url


def search_links(school: str, mascot: str | None = None) -> list[dict[str, str]]:
    """Where to look for a team's broadcast: a web search and TuneIn's search."""
    name = f"{school} {mascot}".strip() if mascot else school
    return [
        {"label": "Search the web", "url": f"https://www.google.com/search?q={quote_plus(name + ' football radio network listen live')}"},
        {"label": "Search TuneIn", "url": f"https://tunein.com/search/?query={quote_plus(name)}"},
    ]
