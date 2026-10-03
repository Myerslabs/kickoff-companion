<#
Kickoff Companion: start the server (Windows). start.sh does the same on Linux and macOS.

Double-click the Desktop icon (Settings in the app makes one), or run this file from the project
folder. It makes sure the Python environment is ready, checks the configuration, then starts the
server in this window. Close the window or press Ctrl+C to stop.

The environment: with uv installed (https://docs.astral.sh/uv/), the script runs `uv sync` first,
which installs Python and every package from uv.lock into .venv when something is missing. Without
uv, an existing .venv made with `py -3.13 -m venv .venv` and pip works the same. The first start by
hand with neither (public release Phase 8, "Kickoff Companion.cmd") installs uv with Astral's official
installer, for this user only and without admin rights; uv then brings Python and the packages.

  -Tray   hide this window behind a tray icon (Open the app, Status page, Show the log, Quit).
          Also switched on by "Tray mode" in the app's Settings.
  -Login  started at login (the Startup shortcut passes it): the browser opens only if Settings say
          "Always". A start by hand opens the app in the browser once the server is up.
#>
param(
    [switch]$Tray,
    [switch]$Login
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
Set-Location -LiteralPath $root
$python = Join-Path $root ".venv\Scripts\python.exe"

function Stop-WithMessage($message) {
    Write-Host ""
    Write-Host $message -ForegroundColor Yellow
    Write-Host ""
    Read-Host "Press Enter to close this window" | Out-Null
    exit 1
}

function Find-Uv {
    $command = Get-Command uv -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    foreach ($candidate in @((Join-Path $env:USERPROFILE ".local\bin\uv.exe"), (Join-Path $env:USERPROFILE ".cargo\bin\uv.exe"))) {
        if (Test-Path -LiteralPath $candidate) { return $candidate }
    }
    return $null
}

$uv = Find-Uv
if (-not $uv -and -not (Test-Path -LiteralPath $python) -and -not $Login) {
    Write-Host ""
    Write-Host "First start: installing uv, which brings Python and the app's packages (no admin rights needed)."
    Write-Host "This takes a minute or two and happens once."
    Write-Host ""
    try {
        Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    } catch {
        Stop-WithMessage ("uv could not be installed: $($_.Exception.Message)`nCheck the internet connection, or install it yourself from https://docs.astral.sh/uv/ and start again.")
    }
    $uv = Find-Uv
}
if ($uv) {
    & $uv sync --frozen --quiet
    if ($LASTEXITCODE -ne 0) {
        Stop-WithMessage "uv could not prepare the Python environment (see above). Check the network and try again."
    }
}

if (-not (Test-Path -LiteralPath $python)) {
    Stop-WithMessage ("No Python environment yet. Either install uv and run this script again:`n" +
        "  powershell -ExecutionPolicy ByPass -c `"irm https://astral.sh/uv/install.ps1 | iex`"`n" +
        "or make one with pip in this folder:`n" +
        "  py -3.13 -m venv .venv`n  .\.venv\Scripts\python -m pip install -r requirements.txt")
}
# No .env yet is fine: the server starts in setup mode and the browser page asks for the key and the team.

& $python -m app --check
if ($LASTEXITCODE -ne 0) {
    Stop-WithMessage "The configuration check failed (see above). Fix .env and try again."
}

if (-not $Tray) {
    $settingsFile = Join-Path $root "data\settings.json"
    if (Test-Path -LiteralPath $settingsFile) {
        try {
            $saved = Get-Content -LiteralPath $settingsFile -Raw | ConvertFrom-Json
            if ($saved.trayMode -eq $true) { $Tray = $true }
        } catch {
            Write-Host "data\settings.json could not be read; starting in a window."
        }
    }
}

$appArgs = @()
if ($Login) { $appArgs += "--login" }

if ($Tray) {
    $trayArgs = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $root "tools\tray.ps1"), "-Python", $python, "-Root", $root)
    if ($Login) { $trayArgs += "-Login" }
    & powershell.exe @trayArgs
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "Kickoff Companion is starting. Keep this window open; close it or press Ctrl+C to stop." -ForegroundColor Green
Write-Host ""
& $python -m app @appArgs
$code = $LASTEXITCODE
if ($code -eq 4) {
    Stop-WithMessage "Kickoff Companion is already running (another window, the tray icon, or start at login), or another program uses its port. Stop that copy first, then start again."
}
if ($code -ne 0) {
    Stop-WithMessage "The server stopped with exit code $code. The log is in logs\app.log."
}
