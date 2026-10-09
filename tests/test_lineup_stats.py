"""Season chips on the starting lineups (2026-10-02): names matched to CFBD's lines after normalising
suffixes and punctuation, the short form only when unique, chips in the impact cards' shape, and junk
in the notes file never raising."""

from __future__ import annotations

from app.services.lineup_stats import attach_lineup_stats, chips_for, index_lines, name_key, short_key
from app.services.players import Line


def line(player_id: str, name: str, category: str, **stats: float) -> tuple[tuple[str, str], Line]:
    return (player_id, category), Line(player_id, name, None, "Swampwater Tech", "Biscuit Belt", category, dict(stats))


LINES = dict([
    line("1", "Mason Hamilton", "passing", YDS=917.0, ATT=87.0, COMPLETIONS=63.0, TD=7.0, INT=2.0, PCT=0.724, YPA=10.5),
    line("1", "Mason Hamilton", "rushing", YDS=40.0, CAR=12.0, TD=2.0),
    line("2", "Lucas Griffin", "rushing", YDS=600.0, CAR=83.0, TD=11.0, YPC=7.2, LONG=75.0),
    line("2", "Lucas Griffin", "receiving", YDS=51.0, REC=6.0, TD=0.0),
    line("3", "Darnell Brooks III", "receiving", YDS=271.0, REC=17.0, TD=2.0, YPR=15.9, LONG=49.0),
    line("4", "TJ Whitfield Jr.", "defensive", TOT=0.0),
    line("5", "DJ Pruitt", "defensive", TOT=20.0, SACKS=0.0, TFL=1.0, PD=3.0),
    line("5", "DJ Pruitt", "interceptions", INT=2.0, YDS=1.0, AVG=0.5),
    line("6", "Patrick Dunmore", "kicking", FGM=6.0, FGA=7.0, PCT=85.7, LONG=48.0, XPM=28.0),
    line("7", "Alec Pryor", "punting", YPP=44.3, NO=12.0, LONG=58.0),
    line("8", "Myles Kettering", "defensive", TOT=5.0),
    line("9", "Myles Ashford", "defensive", TOT=29.0, SACKS=0.5, TFL=1.5),
])


def test_name_keys_drop_suffixes_and_punctuation():
    assert name_key("TJ Whitfield Jr.") == "tj whitfield"
    assert name_key("Darnell Brooks III") == "darnell brooks"
    assert name_key("Ke'Shaun Tillery") == "keshaun tillery"
    assert name_key("Marcus Bellamy-Rowe") == "marcus bellamy rowe"
    assert name_key(None) == "" and name_key(7) == "" and name_key("  ") == ""
    assert short_key("Tavion Merritt Jr.") == "t merritt" and short_key("Cher") == "cher" and short_key(None) == ""


def test_index_offers_the_short_form_only_when_unique():
    by_player, keys, names = index_lines(LINES)
    assert keys["mason hamilton"] == "1" and keys["m hamilton"] == "1"
    assert "m kettering" in keys and "m ashford" in keys  # different last names
    two = dict(LINES)
    two.update([line("10", "Myles Kettering", "defensive", TOT=1.0), line("11", "Mike Kettering", "defensive", TOT=2.0)])
    _, keys2, _ = index_lines(two)
    assert "m kettering" not in keys2, "two M. Ketterings: the short form is ambiguous"
    assert set(by_player["1"]) == {"passing", "rushing"} and names["5"] == "DJ Pruitt"


def test_chips_lead_with_what_the_player_does():
    by_player, _, _ = index_lines(LINES)
    assert chips_for(by_player["1"]) == ["917 passing yards", "7 TD", "2 INT", "72% completions"]
    assert chips_for(by_player["2"]) == ["600 rushing yards", "83 CAR", "11 TD", "7.2 YPC"]
    assert chips_for(by_player["3"]) == ["271 receiving yards", "17 REC", "2 TD", "15.9 YPR"]
    assert chips_for(by_player["5"]) == ["20 tackles", "1 TFL", "3 PD", "2 INT"], "zero sacks skipped, interceptions added"
    assert chips_for(by_player["9"]) == ["29 tackles", "0.5 SACKS", "1.5 TFL"]
    assert chips_for(by_player["6"]) == ["6 field goals", "7 FGA", "86% field goals", "48 LONG"]
    assert chips_for(by_player["7"]) == ["44.3 yards a punt", "12 NO", "58 LONG"]
    assert chips_for(by_player["4"]) == ["0 tackles"], "a lineman with a line but no numbers keeps his one chip"
    assert chips_for({}) == []


def test_attach_matches_names_and_leaves_the_rest_alone():
    lineups = {
        "source": "x",
        "us": {"team": "Swampwater Tech", "slots": [
            {"unit": "Offense", "slot": "QB", "players": [{"name": "Mason Hamilton", "number": 12}, {"name": "Nobody Here"}]},
            {"unit": "Offense", "slot": "RG", "players": [{"name": "T.J. Whitfield", "number": 67}]},
            {"unit": "Defense", "slot": "S", "players": [{"name": "D.J. Pruitt"}, None, "junk"]},
            {"unit": "Special teams", "slot": "PK", "players": "not a list"},
            "junk",
        ]},
        "them": {"team": "Sweet Tea State", "slots": [{"slot": "QB", "players": [{"name": "Austin Pell"}]}]},
    }
    out = attach_lineup_stats(lineups, LINES, {})
    assert out is lineups
    qb = lineups["us"]["slots"][0]["players"]
    assert qb[0]["playerId"] == "1" and qb[0]["chips"][0] == "917 passing yards" and qb[0]["number"] == 12
    assert qb[1]["playerId"] is None and qb[1]["chips"] == []
    assert lineups["us"]["slots"][1]["players"][0]["playerId"] == "4", "T.J. and TJ, with and without Jr., meet"
    assert lineups["us"]["slots"][2]["players"][0]["playerId"] == "5"
    assert lineups["them"]["slots"][0]["players"][0] == {"name": "Austin Pell", "playerId": None, "chips": []}
    # junk shapes never raise
    assert attach_lineup_stats(None, LINES, {}) is None
    assert attach_lineup_stats("x", LINES, {}) == "x"
    assert attach_lineup_stats({"us": "x", "them": {"slots": None}}, LINES, {}) == {"us": "x", "them": {"slots": None}}
