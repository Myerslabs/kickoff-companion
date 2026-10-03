@echo off
rem Kickoff Companion for Windows: double-click to start.
rem The first start installs uv, Python and the app's packages for this user (no admin rights), then opens the
rem setup page in the browser. Later starts just start the server and open the app. Close this window to stop.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
