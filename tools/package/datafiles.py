"""The app's own data files for the packaged program (Kickoff Companion 2.0, the batch review of 2026-11-16): every file
under app/ that is not Python, so a new one (the Imperialism Map's grid, the Circle of Blame's prompts) is bundled the
day it is added. Kept apart from build.py, which imports the app; kickoff.spec imports this under PyInstaller.

    app_datas(root) -> [(source file, folder in the bundle)]"""

from __future__ import annotations

from pathlib import Path

SKIP_DIRS = frozenset({"__pycache__"})
SKIP_SUFFIXES = frozenset({".py", ".pyc", ".pyo"})


def app_datas(root: Path) -> list[tuple[str, str]]:
    app = Path(root) / "app"
    found: list[tuple[str, str]] = []
    for path in sorted(app.rglob("*")):
        if not path.is_file() or path.suffix in SKIP_SUFFIXES or SKIP_DIRS & set(path.relative_to(app).parts):
            continue
        found.append((str(path), path.parent.relative_to(root).as_posix()))
    return found
