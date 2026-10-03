"""Phase 16 hotfix (before the 2026-10-03 game): the Live sheet's remote bar no longer hides the
radio dock, the drive bar no longer picks up the Settings field style, and a hung /api/settings
request can no longer leave the app on 'Loading'."""

from __future__ import annotations

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "static"
CSS = (STATIC / "css" / "components.css").read_text(encoding="utf-8")


def rule(selector: str) -> str:
    match = re.search(r"(?m)^" + re.escape(selector) + r"\s*\{([^}]*)\}", CSS)
    assert match, f"no rule for {selector}"
    return match.group(1)


def test_remote_bar_sits_above_the_radio_dock() -> None:
    assert "bottom: var(--dock-h, 0px)" in rule(".remote")
    assert "var(--dock-h, 0px)" in rule(".update-banner")
    radio = (STATIC / "js" / "radio.js").read_text(encoding="utf-8")
    assert '"--dock-h"' in radio and "ResizeObserver" in radio
    # hiding the dock sends no resize notice, so every redraw writes the height too
    assert re.search(r"function renderDock\(\)[\s\S]*?finally \{\s*writeDockHeight\(\);", radio)


def test_only_the_drive_bar_owns_the_field_class() -> None:
    field_rules = re.findall(r"(?m)^\.field\s*\{([^}]*)\}", CSS)
    assert len(field_rules) == 1, "a second .field rule would restyle every drive strip"
    assert not re.search(r"(?m)(^|;|\s)padding\s*:", field_rules[0])
    assert re.search(r"(?m)^\.form-field\s*\{", CSS)
    styleguide = (STATIC / "js" / "styleguide.js").read_text(encoding="utf-8")
    assert 'class: "field"' not in styleguide and 'class: "form-field"' in styleguide


def test_settings_load_has_a_timeout() -> None:
    prefs = (STATIC / "js" / "prefs.js").read_text(encoding="utf-8")
    assert "AbortController" in prefs
    assert re.search(r"SETTINGS_TIMEOUT_MS\s*=\s*5000", prefs)
    assert 'fetchJson("/api/settings", controller?.signal)' in prefs
    assert "clearTimeout(timer)" in prefs
