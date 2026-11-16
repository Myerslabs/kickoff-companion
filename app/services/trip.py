"""Getting there (ENH-15, owner 2026-10-23: "driving directions to the stadium"; "Parking, tailgate and all of that, maybe
even how to get into the stadium and such. All of it should be printed on the pre-game program in case the phone doesn't
work"). The map link is a link-out, never an embedded map or a new data source: the device opens its own maps app (its
choice of Google Maps, Apple Maps or Waze is the device's own, static/js/ui/directions.js). This module gives the server's
side: where a venue is, the Google Maps link a second phone can scan from the printed program (a QR code drawn here with
segno, no network), and the stadiums researched once and shipped with the app until the install's own Claude run lands.

    destination(place) -> str | None     "lat,lon" when the venue has coordinates, else "name, city, state"
    google_directions(place) -> str | None   the universal Google Maps directions link (it opens in any browser)
    venue_block(place, venue_id) -> dict | None   the program's `trip`: the venue, its link and the QR code as a data URI
    shipped_trip(venue_id) -> dict | None   a stadium researched for the app (app/facts/trips.json), marked `shipped`
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any
from urllib.parse import quote

import segno

log = logging.getLogger("kickoff.trip")

SHIPPED_TRIPS = Path(__file__).resolve().parent.parent / "facts" / "trips.json"


def _get(place: Any, *names: str) -> Any:
    for name in names:
        value = place.get(name) if isinstance(place, dict) else getattr(place, name, None)
        if value is not None:
            return value
    return None


def _word(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _coord(value: Any, limit: float) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if -limit <= value <= limit and value != 0 else None


def destination(place: Any) -> str | None:
    lat, lon = _coord(_get(place, "latitude"), 90), _coord(_get(place, "longitude"), 180)
    if lat is not None and lon is not None:
        return f"{lat:.6f},{lon:.6f}"
    words = [w for w in (_word(_get(place, "name")), _word(_get(place, "city")), _word(_get(place, "state"))) if w]
    return ", ".join(words) if words else None


def google_directions(place: Any) -> str | None:
    where = destination(place)
    return f"https://www.google.com/maps/dir/?api=1&destination={quote(where, safe=',')}" if where else None


def venue_block(place: Any, venue_id: Any = None) -> dict[str, Any] | None:
    """The program's `trip`: the venue's name, town and coordinates, the Google Maps link and its QR code. None with no
    venue to go to."""
    url = google_directions(place)
    if url is None:
        return None
    vid = venue_id if venue_id is not None else _get(place, "id")
    try:
        qr = segno.make(url, error="m").svg_data_uri(scale=4, border=2, dark="#000000", light="#ffffff")
    except Exception:  # noqa: BLE001 - the link still works without its code; logged
        log.exception("The Getting there QR code could not be drawn")
        qr = None
    return {
        "venueId": vid if isinstance(vid, int) and not isinstance(vid, bool) else None,
        "name": _word(_get(place, "name")),
        "city": _word(_get(place, "city")),
        "state": _word(_get(place, "state")),
        "zip": _word(_get(place, "zip")),
        "latitude": _coord(_get(place, "latitude"), 90),
        "longitude": _coord(_get(place, "longitude"), 180),
        "mapUrl": url,
        "qr": qr,
    }


def shipped_trip(venue_id: Any, path: Path = SHIPPED_TRIPS) -> dict[str, Any] | None:
    """A stadium researched for the app and shipped with it, as a written record the Getting there band draws (marked
    `shipped`, with the day it was checked as its writtenAt). None when the file or the stadium is missing or damaged."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        log.warning("The shipped Getting there file could not be read", exc_info=True)
        return None
    row = raw.get(str(venue_id)) if isinstance(raw, dict) else None
    if not isinstance(row, dict):
        return None
    from app.services.writing import read

    answer, _warnings, error = read("trip", json.dumps(row))
    if answer is None:
        log.warning("The shipped Getting there row for venue %s was not usable: %s", venue_id, error)
        return None
    checked = _word(row.get("checkedAt"))
    return {**answer, "shipped": True, "writtenAt": f"{checked}T12:00:00Z" if checked else None}
