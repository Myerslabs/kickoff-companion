#!/bin/bash
# Kickoff Companion for macOS: double-click to start (Terminal opens). The first start installs uv, Python and
# the app's packages for this user, then opens the setup page in the browser. Close the window to stop.
# If macOS says it cannot open a downloaded file, right-click this file, choose Open, then Open again.
cd "$(dirname "$0")" || exit 1
exec ./start.sh "$@"
