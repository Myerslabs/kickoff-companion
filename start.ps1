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

  -Tray   start behind a tray icon (Open the app, Status page, Show the log, Quit) and close this window.
          The default since 2026-10-23: every start goes behind the tray icon unless "Tray mode" is
          switched off in the app's Settings (Server Settings).
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

# BUG-24: the data and log folders follow DATA_DIR and LOG_DIR in .env, as the server does (app/config.py): environment
# variables like %LOCALAPPDATA% expand, ~ is the home folder, and a relative path is under the project folder.
function Read-EnvValue($name, $fallback) {
    $envFile = Join-Path $root ".env"
    if (Test-Path -LiteralPath $envFile) {
        foreach ($line in Get-Content -LiteralPath $envFile) {
            if ($line -match "^\s*$name\s*=\s*(.+?)\s*$") { return $Matches[1].Trim('"').Trim("'") }
        }
    }
    return $fallback
}
function Resolve-Folder($name, $default) {
    $value = Read-EnvValue $name ""
    if (-not $value) { return Join-Path $root $default }
    $value = [Environment]::ExpandEnvironmentVariables($value)
    if ($value.StartsWith("~")) { $value = Join-Path $HOME $value.Substring(1).TrimStart('\', '/') }
    if (-not [IO.Path]::IsPathRooted($value)) { $value = Join-Path $root $value }
    return $value
}
$dataDir = Resolve-Folder "DATA_DIR" "data"
$logDir = Resolve-Folder "LOG_DIR" "logs"
$syncFile = Join-Path $dataDir "update-sync.json"  # FEAT-13: an update from GitHub changed the packages

# Each start writes what it did to start.log in the log folder (public release 0.11.1), so a first start that stops or
# seems to hang on a new computer leaves a record to read or send, even after its window is closed.
$startLog = Join-Path $logDir "start.log"
try {
    New-Item -ItemType Directory -Force $logDir | Out-Null
    Set-Content -LiteralPath $startLog -Encoding utf8 -Value "Kickoff Companion start, $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), PowerShell $($PSVersionTable.PSVersion), $([Environment]::OSVersion.VersionString)"
} catch {
    $startLog = $null  # a read-only folder: the steps still show in this window
}

function Write-Step($message) {
    Write-Host $message
    if ($startLog) {
        try { Add-Content -LiteralPath $startLog -Encoding utf8 -Value "$(Get-Date -Format 'HH:mm:ss') $message" } catch { $script:startLog = $null }
    }
}

function Stop-WithMessage($message) {
    if ($startLog) {
        try { Add-Content -LiteralPath $startLog -Encoding utf8 -Value "$(Get-Date -Format 'HH:mm:ss') STOPPED: $message" } catch { $script:startLog = $null }
    }
    Write-Host ""
    Write-Host $message -ForegroundColor Yellow
    Write-Host ""
    Read-Host "Press Enter to close this window" | Out-Null
    exit 1
}

function Find-Uv {
    $command = Get-Command uv -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    # Where Astral's installer puts it: UV_INSTALL_DIR or XDG_BIN_HOME when set, else ~\.local\bin (older: ~\.cargo\bin)
    $candidates = @()
    if ($env:UV_INSTALL_DIR) { $candidates += (Join-Path $env:UV_INSTALL_DIR "uv.exe") }
    if ($env:XDG_BIN_HOME) { $candidates += (Join-Path $env:XDG_BIN_HOME "uv.exe") }
    $candidates += (Join-Path $env:USERPROFILE ".local\bin\uv.exe"), (Join-Path $env:USERPROFILE ".cargo\bin\uv.exe")
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) { return $candidate }
    }
    return $null
}

$uv = Find-Uv
if (-not $uv -and -not (Test-Path -LiteralPath $python) -and -not $Login) {
    Write-Host ""
    Write-Step "First start: installing uv, which brings Python and the app's packages (no admin rights needed)."
    Write-Step "This takes a few minutes and happens once."
    Write-Host ""
    try {
        Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    } catch {
        Stop-WithMessage ("uv could not be installed: $($_.Exception.Message)`nCheck the internet connection, or install it yourself from https://docs.astral.sh/uv/ and start again.")
    }
    $uv = Find-Uv
    Write-Host ""
    Write-Step "uv is installed. (The note above about PATH is uv's own; Kickoff Companion finds uv without it.)"
}
if ($uv) {
    if (-not (Test-Path -LiteralPath $python)) {
        # The first sync downloads Python and every package: show uv's progress instead of a silent window.
        Write-Step "Getting Python and the app's packages ready with $uv. The first time takes a few minutes; progress shows below."
        # uv's own Python only: probing for one on the system runs Windows' "python" Store stub, which pops up
        # "Get Python from the Microsoft Store" (seen on a new machine, 2026-10-04). And no developer tools.
        $env:UV_PYTHON_PREFERENCE = "only-managed"
        & $uv sync --frozen --no-dev
    } else {
        & $uv sync --frozen --quiet --no-dev --inexact  # installs what is missing; keeps developer tools a developer added
    }
    if ($LASTEXITCODE -ne 0) {
        Stop-WithMessage "uv could not prepare the Python environment (exit code $LASTEXITCODE, see above). Check the network and try again."
    }
    Write-Step "Python and the packages are ready."
    Remove-Item -LiteralPath $syncFile -Force -ErrorAction SilentlyContinue  # FEAT-13: an update's package change is in now
}

if (-not (Test-Path -LiteralPath $python)) {
    Stop-WithMessage ("No Python environment yet. Either install uv and run this script again:`n" +
        "  powershell -ExecutionPolicy ByPass -c `"irm https://astral.sh/uv/install.ps1 | iex`"`n" +
        "or make one with pip in this folder:`n" +
        "  py -3.13 -m venv .venv`n  .\.venv\Scripts\python -m pip install -r requirements.txt")
}
# No .env yet is fine: the server starts in setup mode and the browser page asks for the key and the team.

Write-Step "Checking the settings."
& $python -m app --check
if ($LASTEXITCODE -ne 0) {
    Stop-WithMessage "The configuration check failed (see above). Fix .env and try again."
}

if (-not $Tray) {
    # The tray on by default (owner 2026-10-23): behind the tray icon unless Settings say off. The setting is "auto", "on" or
    # "off"; a file from before keeps true or false, and false was the old default nobody chose, so only "off" means a window.
    $Tray = $true
    $settingsFile = Join-Path $dataDir "settings.json"
    if (Test-Path -LiteralPath $settingsFile) {
        try {
            $saved = Get-Content -LiteralPath $settingsFile -Raw | ConvertFrom-Json
            if ($saved.trayMode -is [string] -and $saved.trayMode -eq "off") { $Tray = $false }
        } catch {
            Write-Host "$settingsFile could not be read; starting behind the tray icon."
        }
    }
}

$appArgs = @()
if ($Login) { $appArgs += "--login" }

if ($Tray) {
    # Post-freeze Wave 1 (owner 2026-10-25): the tray icon runs as its own process with no console window at all, and this
    # window closes. Before, this script waited on the tray in the same window and the tray hid that window, which Windows
    # Terminal ignores, so the window stayed open behind the icon (and a Desktop icon's -NoExit kept it besides).
    $trayArgs = "-NoProfile -ExecutionPolicy Bypass -File `"$(Join-Path $root 'tools\tray.ps1')`" -Python `"$python`" -Root `"$root`""
    if ($uv) { $trayArgs += " -Uv `"$uv`"" }  # the tray syncs the packages before it starts the server again after an update
    if ($Login) { $trayArgs += " -Login" }
    $info = New-Object System.Diagnostics.ProcessStartInfo
    $info.FileName = "powershell.exe"
    $info.Arguments = $trayArgs
    $info.WorkingDirectory = $root
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    try {
        [System.Diagnostics.Process]::Start($info) | Out-Null
    } catch {
        Stop-WithMessage "The tray icon did not start: $($_.Exception.Message). Switch Tray mode off in Settings (Server Settings) to start in this window."
    }
    Write-Step "Started behind the sun icon by the clock. This window closes now."
    [Environment]::Exit(0)  # ends this window even when an older shortcut opened it with -NoExit
}

Write-Host ""
Write-Host "Kickoff Companion is starting. Keep this window open; close it or press Ctrl+C to stop." -ForegroundColor Green
Write-Host ""
$env:KICKOFF_RELAUNCH = "1"  # BUG-22: a restart exits with 8 and this window starts the server again, with any new code
& $python -m app @appArgs
$code = $LASTEXITCODE
while ($code -eq 8) {
    Write-Host ""
    if ($uv -and (Test-Path -LiteralPath $syncFile)) {
        Write-Step "The update changed the app's packages: bringing them in step."
        & $uv sync --frozen --quiet --no-dev --inexact
        if ($LASTEXITCODE -eq 0) { Remove-Item -LiteralPath $syncFile -Force -ErrorAction SilentlyContinue }
        else { Write-Step "uv could not update the packages (exit code $LASTEXITCODE); starting anyway. The log says more." }
    }
    Write-Host "Restarting with the new code." -ForegroundColor Green
    & $python -m app --restarted
    $code = $LASTEXITCODE
}
if ($code -eq 6) {
    Write-Host ""
    Write-Host "Kickoff Companion was already running, so that copy was opened." -ForegroundColor Green
    exit 0
}
if ($code -eq 4) {
    Stop-WithMessage "Another program uses Kickoff Companion's port (what holds it and the free port are above). Stop it, or set another PORT in .env, then start again."
}
if ($code -ne 0) {
    Stop-WithMessage "The server stopped with exit code $code. The log is in $(Join-Path $logDir 'app.log'); the start steps are in $(Join-Path $logDir 'start.log')."
}
