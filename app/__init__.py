"""Kickoff Companion: a second-screen app for following one college football team."""

APP_NAME = "Kickoff Companion"
SUPPORT_EMAIL = "jeremy@myerslabs.com"  # feedback reports go here through the sender's own mail app (public on purpose since 1.0)
PUBLISHER = "Myers Labs"  # public release Phase 8: free from Myers Labs, MIT licensed
REPO_URL = "https://github.com/Myerslabs/kickoff-companion"
REPO_IS_PUBLIC = True  # public again since 0.13.0 (2026-10-09): the invite page offers friends a copy
DATA_CREDIT = "Data provided by CollegeFootballData.com"
DATA_URL = "https://collegefootballdata.com"
__version__ = "2.0.0"  # the release number: 1.0.1 (2026-10-25), then 2.0.0 (2026-11): the new pages, the season as one line, the paper, speed; Windows only
BUILD_PHASE = 15

from app import boot as _boot  # noqa: E402, F401 - the start's clock begins with the first import of the app
