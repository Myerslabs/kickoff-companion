"""Nothing cut off on a phone (owner 2026-11-15, after a weekend on his iPhone: "some sections and bands did not shrink down, even
though they had room on the screen to do it", "It didnt spill past it, it cut off the other player", then "I just want to avoid
cutting anything off, and instead shortening the data" and "Everything should be cut short, starting with the tug of war"). These
run without Node: the page check's --clip rule that found every case (tools/page_check.py), the stylesheet's fixes (each on a
phone only where the iPad must not change), and the full lists' per-game column, which a phone drops before a name is cut."""

from __future__ import annotations

import re
from pathlib import Path

from app.services import fullstats
from tools import page_check

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "static" / "css" / "components.css").read_text(encoding="utf-8")


def rule(selector: str, css: str = CSS) -> str:
    """The body of the first rule that starts a line with this selector."""
    at = css.index("\n" + selector + " {")
    return css[at : css.index("}", at)]


def container_block(marker: str) -> str:
    """The @container block holding a marker line."""
    at = CSS.index(marker)
    start = CSS.rindex("@container", 0, at)
    return CSS[start : CSS.index("\n}\n", at)]


def test_the_clip_rule_is_on_the_page_check() -> None:
    source = (ROOT / "tools" / "page_check.py").read_text(encoding="utf-8")
    assert '"--clip"' in source and "browser.clipped()" in source and "def clipped(self)" in source
    js = page_check.CLIP_JS
    assert "OVERLAYS" not in js, "the reader's own layers are filled in"
    for skipped in (".sr-only", ".band__summary", ".chips-row", ".rail__row", ".ticker", ".np-legbox", ".np-textbox", "svg", "canvas"):
        assert skipped in js, skipped
    assert "'auto' || v === 'scroll'" in js, "a sideways scroller between a box and its clipper lets it scroll: not a cut"
    assert "'shortened'" in js and "'cut off'" in js
    # --anchors: the phone keeps --clip, the board (drawn at a zoom) drops it
    assert '"--layout", "--labels", "--scroll", "--clip")' in source
    assert 'phone = [a for a in rest if a not in ("--layout", "--rules", "--interact", "--labels")]' in source


def test_leaders_side_by_side_gives_the_other_leader_half_the_row() -> None:
    phone = container_block("the two leaders share the row in equal halves")
    assert ".lpair__row.lpair__heads { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);" in phone
    assert ".lpair__heads > .lpair__who--us { grid-column: 1; grid-row: 2; }" in phone
    assert ".lpair__heads > .lpair__who--them { grid-column: 2; grid-row: 2; }" in phone
    assert ".lpair__heads > .lpair__title { grid-column: 1 / -1;" in phone
    # the tug of war gives way first: the bar's halves go down to 12 px, a stat name never below its own width
    assert "--lp-cols: minmax(max-content, 1fr) 64px minmax(12px, 0.4fr) minmax(12px, 0.4fr) 64px;" in phone
    assert phone.startswith("@container (max-width: 559px)"), "a phone only: the iPad's band is wider"


def test_one_column_grids_are_held_to_their_band() -> None:
    for selector in (".band__body .facts", ".results, .schools", ".pic"):
        assert "grid-template-columns: minmax(0, 1fr);" in rule(selector), selector
    # app.css loads after this sheet and has a .facts of its own (two columns, for the status pages): the band's rule outranks it
    app_css = (ROOT / "static" / "css" / "app.css").read_text(encoding="utf-8")
    assert "grid-template-columns: max-content minmax(0, 1fr);" in rule(".facts", app_css)
    assert "width: auto; max-width: 100%;" in rule(".band__body .facts > .facts__table")
    assert "overflow-wrap: anywhere" in rule(".facts__sources")
    assert "white-space: normal" in rule(".blame-evidence .blame-evidence__value")
    results = container_block(".results__table thead th, .schools__table thead th { white-space: normal; }")
    assert results.startswith("@container (max-width: 559px)")


def test_heads_and_names_shorten_instead_of_running_off() -> None:
    head = rule(".band__head")
    assert "flex-wrap: wrap" in head, "a switch too wide for the head goes under the title"
    assert "white-space: nowrap" not in head
    assert ".band__body .leaders__scope { margin: 0; }" in CSS
    blame = container_block(".blame-season__sep { display: none; }")
    assert ".blame-season__what b { display: block; }" in blame and "white-space: normal" in blame
    # the lineup picture: a chip at the field's edge stays whole on a phone, the iPad's tuned spots untouched
    formation = container_block("  .formation__man { width: 60px; min-height: 0; left: clamp(30px, var(--fx), calc(100% - 30px)); }")
    assert formation.startswith("@container (max-width: 699px)")
    assert re.search(r"\n\.formation__man \{ position: absolute; left: var\(--fx\);", CSS), "wider screens keep each spot as set"


def test_the_magazines_starters_are_held_to_their_band_on_the_ipad() -> None:
    assert "grid-template-columns: minmax(0, 1fr);" in rule(".pre-part, .pre-starters")
    assert "@container (min-width: 700px) and (max-width: 999px) { .pre-field .formation__man { width: 90px; } }" in CSS, "the iPad's chips clear each other; a phone keeps its 60"


def test_the_load_data_cards_feet_keep_to_their_card() -> None:
    assert "grid-template-columns: minmax(0, 1fr);" in rule(".prompts__end, .prompts__foot, .prompts__tools")
    assert "white-space: normal" in rule(".prompts__end .btn")


def test_a_phones_sort_buttons_are_no_wider_than_their_heads() -> None:
    assert '@media (max-width: 699px) { .stat-table-wrap[data-size="small"] .stat-table th button { min-width: 0; } }' in CSS
    assert ".stat-table th button, .seg button { min-width: 44px; }" in CSS, "the iPad keeps its press targets"


def test_a_phone_drops_the_per_game_figure_before_a_name() -> None:
    per_game = {"passing": "ypg", "rushing": "ypg", "receiving": "ypg", "defense": "tpg"}
    for key, column in per_game.items():
        columns = {c.key: c for c in fullstats.CATEGORIES[key].player_columns}
        assert columns[column].size == "medium", key
        # what a phone keeps: three numbers beside the rank, the player and the team
        assert len([c for c in columns.values() if c.size is None]) == 3, key
