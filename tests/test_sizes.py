"""Every stat name the server sends a two-team table has its three forms in ui/sizes.js (owner 2026-10-10: nothing
wraps; a label the kit cannot shorten would force a narrower size or drop the table), the notes prompt asks for both
teams' schemes, and an older notes file without the opponent's still reads. Wave 2 (owner 2026-10-10): the Team stats
rows, the live feed's efficiency rows, both situation lists (the program's tendencies, In Game's) and the advanced box
score's rows have theirs too, and the Pre-Game Program's and In Game's sized heads fit a phone. Wave 3: every other page's
labels (the national lists' value heads, the grade's parts, the Season ratings and résumé, the advanced table's names and
groups, the returning measures, the player card's splits, the review's facts, the matchup sheet's groups)."""

from __future__ import annotations

import re
from pathlib import Path

from app.live import analysis
from app.services import depth2, notes_paste
from app.services.notes import NotesFile, Schemes
from app.services.profiles import ADVANCED_ROWS, PROFILE_ROWS

ROOT = Path(__file__).resolve().parents[1]
SIZES_JS = ROOT / "static" / "js" / "ui" / "sizes.js"
PROGRAM_JS = ROOT / "static" / "js" / "views" / "program.js"
TEAM_STATS_JS = ROOT / "static" / "js" / "ui" / "team-stats.js"
SMALL = 13  # a phone's word: a label this short serves every size as it is


def known_forms() -> dict[str, tuple[str, str]]:
    source = SIZES_JS.read_text(encoding="utf-8")
    block = source.split("const FORMS = {", 1)[1].split("\n};", 1)[0]
    found: dict[str, tuple[str, str]] = {}
    for match in re.finditer(r'^\s*(?:"(?P<quoted>[^"]+)"|(?P<bare>[A-Za-z]+)):\s*\["(?P<mid>[^"]*)",\s*"(?P<short>[^"]*)"\]', block, flags=re.MULTILINE):
        found[match.group("quoted") or match.group("bare")] = (match.group("mid"), match.group("short"))
    return found


def test_every_server_label_has_its_forms() -> None:
    forms = known_forms()
    assert len(forms) > 50
    labels = {row[1] for row in PROFILE_ROWS} | {row[1] for row in ADVANCED_ROWS}
    missing = sorted(label for label in labels if label not in forms)
    assert not missing, f"stat names without a short form in sizes.js: {missing}"
    for label, (mid, short) in forms.items():
        assert 0 < len(short) <= 13, f"{label}: the short form is a phone's word, not {short!r}"
        assert 0 < len(mid) <= 24, f"{label}: the middle form is one line, not {mid!r}"


def without_forms(labels: list[str], forms: dict[str, tuple[str, str]]) -> list[str]:
    """The labels too long for a phone that have no shorter forms (they would force the table narrower, rule 2)."""
    return sorted(label for label in labels if label not in forms and len(label) > SMALL)


def test_team_stats_and_feed_rows_have_their_forms() -> None:
    forms = known_forms()
    source = TEAM_STATS_JS.read_text(encoding="utf-8")
    team = re.findall(r'row\("([^"]+)", "(?:parent|sub)"', source)
    assert len(team) == 27 and "Interceptions thrown" in team
    block = source.split("export const FEED_ROWS = [", 1)[1].split("];", 1)[0]
    feed = re.findall(r'\["([^"]+)", "[A-Za-z]+", "[^"]+"(?:, false)?\]', block)
    assert len(feed) == 11 and "Average start, yards to goal" in feed
    assert not without_forms(team + feed, forms), without_forms(team + feed, forms)
    assert forms["Interceptions thrown"] == ("Ints thrown", "Ints") and forms["Time of possession"][1] == "Possession"


def test_both_situation_lists_have_their_forms() -> None:
    """The program's tendencies (app/services/depth2.py) and In Game's (app/live/analysis.py) read the same words."""
    forms = known_forms()
    labels = [label for _, label in depth2.SITUATIONS] + [label for _, label in analysis.SITUATIONS]
    assert len(labels) == 16
    assert not without_forms(labels, forms), without_forms(labels, forms)
    shared = set(label for _, label in depth2.SITUATIONS) & set(label for _, label in analysis.SITUATIONS)
    assert shared == {"3rd and 1 to 3", "3rd and 4 to 6", "3rd and 7 or more"}
    assert [forms[label] for label in sorted(shared)] == [("3rd and 1-3", "3rd 1-3"), ("3rd and 4-6", "3rd 4-6"), ("3rd and 7+", "3rd 7+")]


DEPTH2_JS = ROOT / "static" / "js" / "ui" / "depth2.js"


def test_the_advanced_box_rows_have_their_forms() -> None:
    """Wave 2, the Pre-Game Program: the advanced box score's quarter rows and its two teams' rows shorten like every
    other stat name, named as the Season tables name them (one name per stat: "Success on standard downs")."""
    forms = known_forms()
    source = DEPTH2_JS.read_text(encoding="utf-8")
    quarters = re.findall(r'line\("([^"]+)", b\.', source)
    both = re.findall(r'pair\("([^"]+)", \(t\) =>', source)
    assert len(quarters) == 7 and "Success on standard downs" in quarters and "Success, standard downs" not in quarters
    assert len(both) == 11 and "Havoc (defense)" in both
    assert not without_forms(quarters + both, forms), without_forms(quarters + both, forms)
    assert forms["Success on standard downs"] == ("Success, std downs", "Std downs")
    # the opponent-adjusted matchup beside them (its labels held a phone 4 px past its box), its head too
    adjusted = [label for _key, label, *_rest in depth2.ADJUSTED_KEYS] + ["Adjusted for opponents"]
    assert len(adjusted) == 9 and not without_forms(adjusted, forms), without_forms(adjusted, forms)


def test_the_program_tables_heads_fit_a_phone() -> None:
    """Every head the Pre-Game Program's wave 2 tables shorten names a short form a phone can hold (13 characters at most)
    and a middle form on one line (24)."""
    sources = [DEPTH2_JS, PROGRAM_JS, ROOT / "static" / "js" / "ui" / "play-value.js"]
    mids: list[str] = []
    shorts: list[str] = []
    for path in sources:
        text = path.read_text(encoding="utf-8")
        mids += re.findall(r'labelMid: "([^"]+)"', text)
        shorts += re.findall(r'labelShort: "([^"]+)"', text)
        for mid, short in re.findall(r'ppaColumn\("[^"]+", "[^"]+", "([^"]+)", "([^"]+)"', text):
            mids.append(mid)
            shorts.append(short)
    assert len(mids) > 8 and len(shorts) > 15
    assert not [word for word in shorts if len(word) > SMALL], shorts
    assert not [word for word in mids if len(word) > 24], mids


def test_the_card_rows_are_profile_rows() -> None:
    source = PROGRAM_JS.read_text(encoding="utf-8")
    block = source.split("const CARD_ROWS = [", 1)[1].split("];", 1)[0]
    labels = re.findall(r'\["(?:offense|defense)", "[a-z_]+", "([^"]+)"\]', block)
    assert len(labels) == 12
    profile = {row[1] for row in PROFILE_ROWS}
    assert all(label in profile for label in labels), [label for label in labels if label not in profile]


def test_notes_prompt_asks_for_both_teams_schemes() -> None:
    shape = notes_paste.shape_example("Swampwater Tech", "Diner Tech", "Big Pie")
    assert '"opponent": {' in shape and "Pro-style" in shape
    source = (ROOT / "app" / "services" / "notes_paste.py").read_text(encoding="utf-8")
    assert 'under "opponent" the same two labels for {opponent}' in source


def test_schemes_read_with_and_without_the_opponent() -> None:
    old = Schemes.model_validate({"offense": "Spread", "defense": "4-2-5", "source": "hand"})
    assert old.opponent is None and old.offense == "Spread"
    new = Schemes.model_validate({"offense": "Spread", "opponent": {"offense": "Pro-style", "defense": "3-4"}})
    assert new.opponent is not None and new.opponent.defense == "3-4" and new.defense is None
    junk = Schemes.model_validate({"opponent": {"offense": None}})
    assert junk.opponent is not None and junk.opponent.offense is None
    whole = NotesFile.model_validate({"gameId": 1, "schemes": {"offense": "Spread", "opponent": {"defense": "3-4"}}})
    assert whole.schemes is not None and whole.schemes.opponent is not None and whole.schemes.opponent.defense == "3-4"


def test_wiki_links_are_not_team_taps() -> None:
    """Owner bug 2026-10-10: a coach's Wikipedia link carries data-team for its lookup; the document's team-tap
    handler must leave it alone, or the link opens the team flyout instead of the coach's page."""
    app_js = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
    assert 'closest("[data-team]:not(.team-link):not(.wiki-link)")' in app_js
    assert 'if (route.id !== "board") document.body.classList.remove("board-mode", "board-awake");' in app_js  # item 6, step A: the exit chip's class too
    css = (ROOT / "static" / "css" / "components.css").read_text(encoding="utf-8")
    assert "body.board-mode { --topbar: 0px; --sticky-top: 0px; }" in css


IN_GAME_JS = ROOT / "static" / "js" / "ui" / "in-game-tables.js"


def test_in_game_rows_have_their_forms() -> None:
    """Wave 2, step 3: In Game's quarter splits, drive summary and team play value shorten like every stat name, named as
    the rest of the app names them (one name per stat: PPA, not EPA; Third down; a defense's rows say allowed)."""
    forms = known_forms()
    source = IN_GAME_JS.read_text(encoding="utf-8")

    def block(name: str) -> str:
        return source.split(f"export const {name} = [", 1)[1].split("];", 1)[0]

    splits = re.findall(r'\["([^"]+)", "[A-Za-z]+", "[^"]+"\]', block("SPLIT_ROWS"))
    drives = re.findall(r'\["([^"]+)", "[A-Za-z]+", "[^"]+", (?:true|false|undefined)\]', block("DRIVE_ROWS"))
    value = re.findall(r'\["([^"]+)", "(?:offense|defense)", "[a-z]+", (?:true|false)\]', block("TEAM_VALUE_ROWS"))
    assert len(splits) == 8 and "PPA per play (no TD plays)" in splits and "Third down" in splits
    assert not [label for label in splits if "EPA" in label or label == "3rd downs"]
    assert len(drives) == 7 and "Three-and-outs" in drives
    assert len(value) == 6 and all("allowed" in label for label in value if label.startswith("Defense"))
    assert not without_forms(splits + drives + value, forms), without_forms(splits + drives + value, forms)
    assert forms["Defense allowed, overall"] == ("Def allowed, overall", "Def all")
    # the Situation panel's rows are Team stats rows (ui/situation.js), every one with its forms
    situation = re.findall(r'"([^"]+)"', (ROOT / "static" / "js" / "ui" / "situation.js").read_text(encoding="utf-8").split("SITUATION_LABELS = [", 1)[1].split("];", 1)[0])
    team = re.findall(r'row\("([^"]+)", "(?:parent|sub)"', TEAM_STATS_JS.read_text(encoding="utf-8"))
    assert len(situation) == 8 and all(label in team for label in situation) and "Total yards" not in situation
    assert not without_forms(situation, forms)


def test_the_in_game_tables_heads_fit_a_phone() -> None:
    """Every head In Game's tables shorten (the splits, tendencies, fourth down, the scores) names a short form a phone can
    hold and a middle form on one line."""
    sources = [IN_GAME_JS, ROOT / "static" / "js" / "ui" / "scores.js"]
    mids: list[str] = []
    shorts: list[str] = []
    for path in sources:
        text = path.read_text(encoding="utf-8")
        mids += re.findall(r'labelMid: "([^"]+)"', text)
        shorts += re.findall(r'labelShort: "([^"]+)"', text)
        for _long, mid, short in re.findall(r'head\("([^"]+)", "([^"]+)", "([^"]+)"', text):
            mids.append(mid)
            shorts.append(short)
    assert len(shorts) >= 6 and "EP" in shorts and "If not" in shorts and "AP" in shorts
    assert not [word for word in shorts if len(word) > SMALL], shorts
    assert not [word for word in mids if len(word) > 24], mids


def test_the_wave_3_labels_have_their_forms() -> None:
    """Wave 3 (owner 2026-10-10): the forms every other page's tables shorten live in ui/sizes.js already, so each page only
    declares its columns. Read from the server where the labels are born and from the pages that write their own."""
    from app.services import grades, matchup, national, national_extra

    forms = known_forms()
    values = sorted({m.value_label or m.label for m in national.METRICS.values()})
    parts = sorted({c.label for spec in grades.SPECS.values() for c in spec.components})
    returning = [label for _key, label, *_rest in national_extra.RETURNING]
    groups = sorted({row[5] for row in ADVANCED_ROWS})
    sides = list(matchup.SIDE_GROUPS.values())
    js = ROOT / "static" / "js"
    pair_labels = re.findall(r'^\s+[a-z_]+: "([^"]+)",$', DEPTH2_JS.read_text(encoding="utf-8").split("const PAIR_LABELS = {", 1)[1].split("};", 1)[0], flags=re.MULTILINE)
    resume = re.findall(r'(?:\{ |^\s+)label: "([^"]+)"', DEPTH2_JS.read_text(encoding="utf-8").split("export function resumeBlock", 1)[1].split("const games", 1)[0], flags=re.MULTILINE)  # the rows, not the chip's name
    ratings = re.findall(r'add\("[A-Za-z]+", "([^"]+)"', (js / "views" / "season.js").read_text(encoding="utf-8")) + re.findall(r'key: "fpiSo[sr]", label: "([^"]+)"', (js / "views" / "season.js").read_text(encoding="utf-8"))
    splits = re.findall(r'\["[A-Za-z]+", "([^"]+)"\]', (js / "views" / "player.js").read_text(encoding="utf-8").split("const PPA_SPLITS = [", 1)[1].split("];", 1)[0])
    review = (js / "views" / "review.js").read_text(encoding="utf-8").split("const stoodOut = [", 1)[1].split("const rows", 1)[0]  # wave 3: two tables
    facts = re.findall(r'\{ label: "([^"]+)", (?:value|game):', review) + list(re.search(r'label: underWay \? "([^"]+)" : "([^"]+)"', review).groups())
    measures = re.findall(r'ret\("[A-Za-z]+", "[A-Za-z]+", "([^"]+)"\)', (js / "views" / "team.js").read_text(encoding="utf-8"))
    assert len(values) > 20 and "Strength of schedule played (average SP+ of opponents)" in values
    assert len(parts) >= 28 and "Punts inside the 20, per punt" in parts
    assert len(returning) == 9 and len(groups) == 7 and sides == ["Offense", "Defense", "Both sides"]
    assert len(pair_labels) == 14 and len(resume) == 5 and len(ratings) == 8 and len(splits) == 8 and len(facts) == 8 and len(measures) == 5
    everything = values + parts + returning + groups + sides + pair_labels + resume + ratings + splits + facts + measures
    assert not without_forms(everything, forms), without_forms(everything, forms)
    assert forms["SP+ overall"] == ("SP+ overall", "SP+") and forms["Strength of schedule"][1] == "SOS"
    assert forms["Both sides"] == ("Both sides", "Both") and forms["First down"][1] == "1st" and forms["Second down"][1] == "2nd"
    assert forms["Play value, PPA per play"] == ("PPA per play", "PPA"), "one name per stat: PPA per play"
    assert forms["Opponents played, average SP+"][1] == "SOS played"


def test_the_wave_3_heads_fit_a_phone() -> None:
    """The styleguide's sized samples (wave 3, step 1) name short forms a phone can hold and middle forms on one line. (The
    samples that draw through a page's own builder, the recruiting class and where it is from since step 4, are held to it with
    their page.)"""
    text = (ROOT / "static" / "js" / "styleguide.js").read_text(encoding="utf-8")
    mids = re.findall(r'(?:labelMid|subLabelMid): "([^"]+)"', text)
    shorts = re.findall(r'(?:labelShort|subLabelShort): "([^"]+)"', text)
    assert len(shorts) >= 8 and len(mids) >= 8
    assert not [word for word in shorts if len(word) > SMALL], shorts
    assert not [word for word in mids if len(word) > 24], mids


def test_the_people_pages_heads_fit_a_phone() -> None:
    """Wave 3, step 4: My Teams, Recruiting, the roster costs and the availability table name short forms a phone can hold
    and middle forms on one line; the roster grid's class codes and the availability's short statuses are a phone's words."""
    js = ROOT / "static" / "js"
    sources = [js / "views" / "myteams.js", js / "views" / "recruiting.js", js / "ui" / "roster-costs.js", js / "ui" / "editorial.js"]
    mids: list[str] = []
    shorts: list[str] = []
    for path in sources:
        text = path.read_text(encoding="utf-8")
        mids += re.findall(r'(?:labelMid|subLabelMid): "([^"]+)"', text)
        shorts += re.findall(r'(?:labelShort|subLabelShort): "([^"]+)"', text)
    assert {"Opp", "Nat", "Group"} <= set(shorts), shorts  # 2026-10-16: Where they're from is a pie, its table (#, Avg) gone
    assert {"Conf", "AP", "SP+", "Elo", "FPI", "Last", "Opponent", "Next", "Date"} <= set(mids), mids
    assert not [word for word in shorts if len(word) > SMALL], shorts
    assert not [word for word in mids if len(word) > 24], mids
    grid = (js / "ui" / "roster-grid.js").read_text(encoding="utf-8")
    assert 'export const CLASS_COLUMNS = [["FR", "Freshman"], ["SO", "Sophomore"], ["JR", "Junior"], ["SR", "Senior"]];' in grid
    assert 'sizedText(name, name, code)' in grid and 'sizedText("Players", "Players", "#")' in grid
    statuses = re.findall(r':\s*"([^"]+)"', (js / "ui" / "editorial.js").read_text(encoding="utf-8").split("const STATUS_SHORT = {", 1)[1].split("};", 1)[0])
    assert statuses == ["Quest.", "GTD"] and all(len(word) <= SMALL for word in statuses)


def test_the_player_card_heads_fit_a_phone() -> None:
    """Wave 3, step 5: the player card's sized heads (PPA per play and Total PPA, the History's "#", the grade's percentile,
    a punter's Inside 20 and Touchbacks) name short forms a phone can hold and middle forms on one line, and every column the
    card's two size maps name (the seasons' CATEGORY_SIZES, the game log's GAME_SIZES) is a stat its category draws."""
    js = ROOT / "static" / "js"
    mids: list[str] = []
    shorts: list[str] = []
    for path in (js / "views" / "player.js", js / "ui" / "player-card.js", js / "ui" / "grade.js", js / "ui" / "stat-labels.js"):
        text = path.read_text(encoding="utf-8")
        mids += re.findall(r'labelMid: "([^"]+)"', text)
        shorts += re.findall(r'labelShort: "([^"]+)"', text)
    assert {"PPA", "Total", "#", "Pctl", "In 20", "TB"} <= set(shorts), shorts
    assert {"PPA/play", "Percentile", "TB"} <= set(mids), mids
    assert not [word for word in shorts if len(word) > SMALL], shorts
    assert not [word for word in mids if len(word) > 24], mids
    labels = (js / "ui" / "stat-labels.js").read_text(encoding="utf-8")
    order_block = labels.split("const CATEGORY_ORDER = {", 1)[1].split("\n};", 1)[0]
    order = {cat: {k.upper() for k in re.findall(r'"([^"]+)"', body)} for cat, body in re.findall(r"^\s+(\w+): \[([^\]]*)\]", order_block, flags=re.MULTILINE)}
    assert len(order) == 10
    for name in ("CATEGORY_SIZES", "GAME_SIZES"):
        block = labels.split(f"const {name} = {{", 1)[1].split("\n};", 1)[0]
        maps = re.findall(r"^\s+(\w+): \{([^}]*)\}", block, flags=re.MULTILINE)
        assert len(maps) >= 8, name
        for category, body in maps:
            sizes = re.findall(r'(?:"([^"]+)"|([A-Z]+)):\s*"(medium|large)"', body)
            assert sizes, (name, category)
            unknown = [quoted or bare for quoted, bare, _ in sizes if (quoted or bare).upper() not in order.get(category, set())]
            assert not unknown, f"{name}.{category} sizes keys its table never draws: {unknown}"
