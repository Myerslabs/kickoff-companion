"""Phase 19: your own notes during a game."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.services.gamenotes import MAX_NOTES, MAX_TEXT, GameNotes, NoteError


def test_a_note_is_stamped_and_read_back(tmp_path):
    notes = GameNotes(tmp_path)
    assert notes.list(77) == [] and notes.count(77) == 0
    first = notes.add(77, "  Watch the left tackle.  ", {"period": 2, "clock": "8:41", "score": "AAA 7, BBB 3"}, now=datetime(2026, 10, 10, 20, 0, tzinfo=timezone.utc))
    assert first["text"] == "Watch the left tackle." and first["period"] == 2 and first["clock"] == "8:41" and first["at"] == "2026-10-10T20:00:00Z"
    notes.add(77, "Second line")
    assert [n["text"] for n in GameNotes(tmp_path).list(77)] == ["Watch the left tackle.", "Second line"], "oldest first, kept on disk"
    assert notes.list(78) == []


def test_bad_context_is_left_out_and_bad_text_refused(tmp_path):
    notes = GameNotes(tmp_path)
    note = notes.add(1, "x", {"period": 99, "clock": 5, "score": "", "extra": "ignored"})
    assert set(note) == {"id", "at", "text"}
    assert set(notes.add(1, "y", "not a dict")) == {"id", "at", "text"}
    for bad in ("", "   ", None, 5):
        with pytest.raises(NoteError):
            notes.add(1, bad)
    with pytest.raises(NoteError):
        notes.add(1, "x" * (MAX_TEXT + 1))


def test_the_limit_and_removal(tmp_path):
    notes = GameNotes(tmp_path)
    for i in range(MAX_NOTES):
        notes.add(5, f"n{i}")
    with pytest.raises(NoteError, match="already has"):
        notes.add(5, "one too many")
    first = notes.list(5)[0]["id"]
    assert notes.delete(5, first) is True and notes.delete(5, first) is False
    assert notes.count(5) == MAX_NOTES - 1


def test_a_damaged_file_reads_as_no_notes(tmp_path):
    (tmp_path / "gamenotes").mkdir()
    (tmp_path / "gamenotes" / "9.json").write_text("{broken", encoding="utf-8")
    assert GameNotes(tmp_path).list(9) == []
    (tmp_path / "gamenotes" / "9.json").write_text(json.dumps({"notes": [{"id": 1}, "junk", {"id": "a", "text": "ok"}]}), encoding="utf-8")
    assert [n["id"] for n in GameNotes(tmp_path).list(9)] == ["a"]


def test_the_routes(client: TestClient, app):
    assert client.get("/api/gamenotes/526001015").json()["data"]["notes"] == []
    added = client.post("/api/gamenotes/526001015", json={"text": "Nice drive", "period": 3, "clock": "2:00", "score": "A 14, B 10"})
    assert added.status_code == 200
    note = added.json()["data"]["note"]
    assert note["period"] == 3 and len(added.json()["data"]["notes"]) == 1
    assert client.post("/api/gamenotes/526001015", json={"text": "  "}).status_code == 422
    assert client.get("/api/gamenotes/abc").status_code == 404
    gone = client.delete(f"/api/gamenotes/526001015/{note['id']}")
    assert gone.status_code == 200 and gone.json()["data"]["notes"] == []
    assert client.delete("/api/gamenotes/526001015/nope").status_code == 404


def test_guests_can_read_but_not_write(client: TestClient, app):
    client.post("/api/gamenotes/1", json={"text": "mine"})
    app.state.host_access.set_pin("1234")
    assert client.get("/api/gamenotes/1").status_code == 200
    assert client.post("/api/gamenotes/1", json={"text": "guest"}).status_code == 403


def test_the_notes_are_in_the_backup(tmp_path):
    import zipfile

    from app.maintenance import backup_data

    GameNotes(tmp_path / "data").add(3, "keep me")
    target = backup_data(tmp_path / "data", tmp_path / "b", 3, datetime(2026, 10, 10, tzinfo=timezone.utc))
    assert "gamenotes/3.json" in zipfile.ZipFile(target).namelist()
