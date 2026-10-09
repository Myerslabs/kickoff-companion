"""The per-game notes file: valid files parse, bad entries are dropped and the rest kept, and a
broken file is reported with a readable reason instead of raising."""

from __future__ import annotations

import json
from pathlib import Path

from app.services.notes import load_notes, notes_path


def write(tmp_path: Path, game_id: int, body) -> Path:
    path = notes_path(tmp_path, game_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body if isinstance(body, str) else json.dumps(body), encoding="utf-8")
    return path


def test_no_file_means_no_notes_and_no_error(tmp_path: Path):
    assert load_notes(tmp_path, 1) == (None, None)
    assert load_notes(tmp_path, None) == (None, None)


def test_full_file_parses(tmp_path: Path):
    write(tmp_path, 5, {
        "gameId": 5,
        "author": "Claude (pre-game task)",
        "writtenAt": "2026-09-24T22:00:00Z",
        "sources": [{"label": "Biscuit Belt availability report", "url": "https://example.invalid/report"}],
        "sections": [{"heading": "Line movement", "paragraphs": ["Opened at -1.5, now -3."]}],
        "availability": [{"name": "Player A", "position": "WR", "status": "Out", "note": "knee"}],
        "visitors": {"home": [{"name": "Recruit A", "stars": 4}], "away": [], "source": "example"},
    })
    notes, error = load_notes(tmp_path, 5)
    assert error is None and notes is not None
    assert notes.author.startswith("Claude") and notes.sections[0].heading == "Line movement"
    assert notes.availability[0].status == "Out" and notes.visitors.home[0].stars == 4


def test_bad_entries_are_dropped_and_the_rest_kept(tmp_path: Path):
    write(tmp_path, 6, {
        "sections": [{"heading": "Good"}, {"paragraphs": ["no heading"]}, "junk", None],
        "availability": [{"name": "A", "status": "Out"}, {"name": "B"}, {"status": "Out"}, 42],
        "visitors": {"home": [{"name": "Recruit A"}, {"stars": 5}, "x"], "away": None},
    })
    notes, error = load_notes(tmp_path, 6)
    assert error is None
    assert [s.heading for s in notes.sections] == ["Good"]
    assert [a.name for a in notes.availability] == ["A", "B"], "Phase 17: a row with no status is kept; one with no name is not"
    assert notes.availability[1].status is None
    assert [v.name for v in notes.visitors.home] == ["Recruit A"] and notes.visitors.away == []


def test_broken_files_are_reported(tmp_path: Path):
    write(tmp_path, 7, "{not json")
    notes, error = load_notes(tmp_path, 7)
    assert notes is None and "not valid JSON" in error
    write(tmp_path, 8, [1, 2, 3])
    notes, error = load_notes(tmp_path, 8)
    assert notes is None and "JSON object" in error
    write(tmp_path, 9, {"visitors": "not an object"})
    notes, error = load_notes(tmp_path, 9)
    assert notes is None and error.startswith("9.json: visitors")


def test_lineups_parse_with_bad_slots_and_names_dropped(tmp_path: Path):
    """2026-10-02: both teams' published depth charts; a slot without a label or a name without a name is dropped."""
    write(tmp_path, 11, {
        "lineups": {
            "source": "Ourlads", "updatedAt": "2026-09-26",
            "us": {"team": "Swampwater Tech", "scheme": "Spread option", "slots": [
                {"unit": "Offense", "slot": "QB", "players": [{"name": "Mason Hamilton", "number": 12, "classYear": "RS SO"}, {"name": "Tramell Jones Jr."}, {"number": 3}, "junk", None]},
                {"unit": "Defense", "players": [{"name": "no slot label"}]},
                {"slot": "PK", "players": "not a list"},
                {"slot": "P"},
                42,
            ]},
            "them": None,
        },
    })
    notes, error = load_notes(tmp_path, 11)
    assert error is None and notes.lineups is not None and notes.lineups.them is None
    assert notes.lineups.source == "Ourlads" and notes.lineups.us.scheme == "Spread option"
    assert [s.slot for s in notes.lineups.us.slots] == ["QB", "P"]
    qb = notes.lineups.us.slots[0]
    assert [p.name for p in qb.players] == ["Mason Hamilton", "Tramell Jones Jr."]
    assert qb.players[0].number == 12 and qb.players[1].number is None and qb.players[1].classYear is None
    assert notes.lineups.us.slots[1].players == []


def test_lineups_of_the_wrong_shape_are_reported(tmp_path: Path):
    write(tmp_path, 12, {"lineups": {"us": "Swampwater Tech"}})
    notes, error = load_notes(tmp_path, 12)
    assert notes is None and error.startswith("12.json: lineups.us")
    write(tmp_path, 13, {"lineups": []})
    notes, error = load_notes(tmp_path, 13)
    assert notes is None and error.startswith("13.json: lineups")


def test_bom_and_unknown_keys_are_tolerated(tmp_path: Path):
    path = write(tmp_path, 10, {"author": "hand", "somethingNew": {"x": 1}})
    path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())
    notes, error = load_notes(tmp_path, 10)
    assert error is None and notes.author == "hand" and notes.visitors is None
