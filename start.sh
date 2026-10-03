#!/usr/bin/env bash
# Kickoff Companion: start the server (Linux and macOS). start.ps1 does the same on Windows.
#
#   ./start.sh            prepare the Python environment, check the configuration, run the server here
#   ./start.sh --service  the same without questions or pauses, for the login service
#                         (systemd on Linux, launchd on macOS; Settings in the app sets it up);
#                         the browser opens only if Settings say "Always" (a start by hand opens it)
#
# The environment: with uv installed (https://docs.astral.sh/uv/), the script runs `uv sync` first,
# which installs Python and every package from uv.lock into .venv when something is missing. No admin
# rights are needed, which suits the Steam Deck's read-only system. Without uv, an existing .venv made
# with `python3 -m venv .venv` and pip works the same. The first start by hand with neither (public
# release Phase 8, "Kickoff Companion.command" and "Kickoff Companion.sh") installs uv with Astral's
# official installer, for this user only; uv then brings Python and the packages. Stop with Ctrl+C.

set -u
cd "$(dirname "$0")" || exit 1
ROOT="$(pwd)"
PYTHON="$ROOT/.venv/bin/python"
SERVICE=0
[ "${1:-}" = "--service" ] && SERVICE=1

stop_with() {
  printf '\n%s\n\n' "$1" >&2
  if [ "$SERVICE" -eq 0 ] && [ -t 0 ]; then
    read -r -p "Press Enter to close. " _
  fi
  exit 1
}

find_uv() {
  if command -v uv >/dev/null 2>&1; then command -v uv; return; fi
  # A login service starts with a short PATH, so look where the uv installer and Homebrew put it.
  for candidate in "$HOME/.local/bin/uv" "$HOME/.cargo/bin/uv" /opt/homebrew/bin/uv /usr/local/bin/uv; do
    if [ -x "$candidate" ]; then echo "$candidate"; return; fi
  done
}

UV="$(find_uv)"
if [ -z "$UV" ] && [ ! -x "$PYTHON" ] && [ "$SERVICE" -eq 0 ]; then
  printf '\nFirst start: installing uv, which brings Python and the app'"'"'s packages (no admin rights needed).\nThis takes a minute or two and happens once.\n\n'
  if command -v curl >/dev/null 2>&1; then
    curl -LsSf https://astral.sh/uv/install.sh | sh || stop_with "uv could not be installed (see above). Check the internet connection and start again."
  elif command -v wget >/dev/null 2>&1; then
    wget -qO- https://astral.sh/uv/install.sh | sh || stop_with "uv could not be installed (see above). Check the internet connection and start again."
  else
    stop_with "Neither curl nor wget is here to download uv. Install uv from https://docs.astral.sh/uv/ and start again."
  fi
  UV="$(find_uv)"
fi
if [ -n "$UV" ]; then
  "$UV" sync --frozen --quiet || stop_with "uv could not prepare the Python environment (see above). Check the network and try again."
fi

if [ ! -x "$PYTHON" ]; then
  stop_with "No Python environment yet. Either install uv and run this script again:
  curl -LsSf https://astral.sh/uv/install.sh | sh
or make one with pip in this folder:
  python3 -m venv .venv
  .venv/bin/python -m pip install -r requirements.txt"
fi
# No .env yet is fine: the server starts in setup mode and the browser page asks for the key and the team.

"$PYTHON" -m app --check || stop_with "The configuration check failed (see above). Fix .env and try again."

if [ "$SERVICE" -eq 1 ]; then
  exec "$PYTHON" -m app --login  # the service manager watches the server itself and restarts it if it fails
fi

printf '\nKickoff Companion is starting. Keep this window open; close it or press Ctrl+C to stop.\n\n'
"$PYTHON" -m app
code=$?
if [ "$code" -eq 4 ]; then
  stop_with "Kickoff Companion is already running (another window or the login service), or another program uses its port. Stop that copy first, then start again."
fi
if [ "$code" -ne 0 ] && [ "$code" -ne 130 ]; then
  stop_with "The server stopped with exit code $code. The log is in logs/app.log."
fi
