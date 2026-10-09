"""Phase 17 #36: a team's signees in the blue-chip classes counted by stars, with the average."""

from __future__ import annotations

from app.cfbd.models import Recruit
from app.services.stats_extra import star_counts


def recruit(stars):
    return Recruit.model_validate({"id": "1", "name": "A Recruit", "stars": stars, "year": 2026, "committedTo": "Swampwater Tech"})


def test_star_counts_cover_the_last_four_classes():
    classes = {2022: [recruit(5)], 2023: [recruit(4), recruit(3)], 2024: [recruit(3), recruit(None)], 2025: [recruit(2), "junk"], 2026: [recruit(4)]}
    s = star_counts(classes)
    assert s["counts"] == {"5": 0, "4": 2, "3": 2, "2": 1, "1": 0}, "2022 is outside the last four classes"
    assert s["average"] == 3.2 and s["rated"] == 5 and s["unrated"] == 1
    assert star_counts({})["average"] is None and star_counts({2026: [recruit(9), recruit(0)]})["unrated"] == 2


def signee(stars, position, rating=0.9):
    return Recruit.model_validate({"id": "1", "name": "A Recruit", "stars": stars, "position": position, "rating": rating, "year": 2026, "committedTo": "Swampwater Tech"})


def test_recruit_sides_split_offense_and_defense():
    from app.services.stats_extra import recruit_sides, side_of

    assert [side_of(p) for p in ("QB", " iol ", "EDGE", "S", "ATH", "K", "XX", None, 5)] == ["offense", "offense", "defense", "defense", "athlete", "specialist", None, None, None]
    classes = {2022: [signee(5, "QB")], 2023: [signee(4, "QB"), signee(3, "WR", 0.85)], 2024: [signee(5, "EDGE", 0.99), signee(2, "CB", None)], 2025: [signee(3, "ATH"), signee(2, "K"), signee(3, "XX"), "junk"], 2026: [signee(None, "LB", 1.5)]}
    s = recruit_sides(classes)
    assert s["offense"]["signees"] == 2 and s["offense"]["counts"]["4"] == 1 and s["offense"]["blueChipRatio"] == 0.5, "2022 is outside the window"
    assert s["offense"]["averageRating"] == 0.875
    assert s["defense"]["signees"] == 3 and s["defense"]["blueChipRatio"] == 0.333 and s["defense"]["unrated"] == 1
    assert s["defense"]["averageRating"] == 0.99, "a missing or out-of-range rating is left out"
    assert s["apart"] == {"athlete": 1, "specialist": 1, "unknown": 1}
    empty = recruit_sides({})
    assert empty["offense"]["signees"] == 0 and empty["offense"]["blueChipRatio"] is None and empty["offense"]["averageRating"] is None
