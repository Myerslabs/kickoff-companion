"""Phase 18.4: four classes, a redshirt inferred and marked."""

from __future__ import annotations

import pytest

from app.services.classes import class_fields, class_label, is_redshirt


@pytest.mark.parametrize(("year", "label"), [(1, "FR"), (2, "SO"), (3, "JR"), (4, "SR"), (5, "SR"), (6, "SR"), (0, None), (None, None), ("3", None), (True, None)])
def test_there_are_four_classes(year, label):
    assert class_label(year) == label


def test_a_fifth_year_player_is_a_senior_with_a_redshirt():
    assert class_fields(5) == {"classYear": "SR", "redshirt": True}
    assert class_fields(4) == {"classYear": "SR", "redshirt": False}


def test_more_seasons_on_campus_than_the_class_means_a_redshirt():
    assert is_redshirt(2, 2024, 2026) is True  # three seasons on campus, listed a sophomore
    assert is_redshirt(3, 2024, 2026) is False  # three seasons, a junior
    assert is_redshirt(1, 2025, 2026) is True  # second season, still a freshman
    assert is_redshirt(1, 2026, 2026) is False


def test_missing_or_odd_data_never_marks_a_redshirt():
    assert is_redshirt(None, 2024, 2026) is False
    assert is_redshirt(2, None, 2026) is False
    assert is_redshirt(2, 2030, 2026) is False  # a recruit class after the season: nonsense, ignored
    assert is_redshirt(2, "2024", 2026) is False
