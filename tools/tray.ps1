<#
Kickoff Companion in the system tray (Phase 9, owner direction 2026-09-23: always visible, but
optionally in the tray instead of a taskbar window).

Started by start.ps1 (Tray mode is the default since 2026-10-23). Starts the server as a child process
with no window and shows a tray icon with a menu: Open the app, Status page, Show the log, Quit. Quit
stops the server. The server's own log stays in logs\app.log (or LOG_DIR in .env).

Phase 16 wave 3: the packaged program uses it too. Its Desktop icon and Startup shortcut run this script with
-Program (the program's .exe) instead of -Python; -Root is then the folder that holds .env, data and logs.
The address is http:// unless HTTPS=on in .env (plain HTTP has been the default since public release Phase 4b).

Post-freeze Wave 1 (owner 2026-10-25):
- start.ps1 and the program start this script with no console window at all (CREATE_NO_WINDOW), and this
  script starts the server the same way, so no window stays open behind the icon. Windows Terminal ignored
  the old trick of hiding a console after it opened.
- While the server starts, the icon's hover text counts the seconds ("starting, 12 s"); a notification says
  when the data is ready and how long it took. BUG-17, ENH-18 (owner 2026-10-27): ready means the opening pages have
  their data (or 30 s went by), the moment the server opens the browser on a start by hand; the note says whether it
  did (/api/health server.open_seconds, server.browser_opened).
- A start that fails opens a window with what happened, Copy the report, Show the log and, when another
  program holds the port, Use port N (saved in .env with --use-port, then started again). A copy that was
  already running is opened instead of a second one (exit code 6).
#>
param(
    [string]$Python,
    [string]$Program,
    [Parameter(Mandatory = $true)][string]$Root,
    [string]$Uv,
    [switch]$Login
)
if (-not $Python -and -not $Program) { throw "Give -Python (a checkout) or -Program (the packaged program)." }

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Net.Http
Add-Type -Name Win32Window -Namespace Kickoff -MemberDefinition @'
[DllImport("kernel32.dll")] public static extern IntPtr GetConsoleWindow();
[DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
'@

$AlreadyRunning = 6  # app/portcheck.py ALREADY_RUNNING
$Relaunch = 8  # app/restart.py RELAUNCH: start the server again, with any new code (BUG-22)
$SlowSeconds = 120

function Read-EnvValue($name, $fallback) {
    $envFile = Join-Path $Root ".env"
    if (Test-Path -LiteralPath $envFile) {
        foreach ($line in Get-Content -LiteralPath $envFile) {
            if ($line -match "^\s*$name\s*=\s*(.+?)\s*$") { return $Matches[1].Trim('"').Trim("'") }
        }
    }
    return $fallback
}

# The addresses come from .env, read again after "Use port N" changes PORT.
function Set-Address {
    $script:port = Read-EnvValue "PORT" "8642"
    $hostName = Read-EnvValue "LAN_HOSTNAME" "localhost"
    if (-not $hostName) { $hostName = "localhost" }
    $scheme = if ((Read-EnvValue "HTTPS" "off") -match "^(on|true|1|yes)$") { "https" } else { "http" }
    $script:appUrl = "$scheme`://$hostName`:$($script:port)/"
    $script:statusUrl = "$scheme`://$hostName`:$($script:port)/status"
    $script:healthUrl = "http://127.0.0.1:$($script:port)/api/health"  # the server answers plain HTTP on its own computer
}
Set-Address

# BUG-24: the data and log folders follow DATA_DIR and LOG_DIR in .env, as the server does (app/config.py): environment
# variables like %LOCALAPPDATA% expand, ~ is the home folder, and a relative path is under the project folder.
function Resolve-Folder($name, $default) {
    $value = Read-EnvValue $name ""
    if (-not $value) { return Join-Path $Root $default }
    $value = [Environment]::ExpandEnvironmentVariables($value)
    if ($value.StartsWith("~")) { $value = Join-Path $HOME $value.Substring(1).TrimStart('\', '/') }
    if (-not [IO.Path]::IsPathRooted($value)) { $value = Join-Path $Root $value }
    return $value
}
$dataDir = Resolve-Folder "DATA_DIR" "data"
$logDir = Resolve-Folder "LOG_DIR" "logs"
$logFile = Join-Path $logDir "app.log"
$reportFile = Join-Path $dataDir "startup-failure.json"
$syncFile = Join-Path $dataDir "update-sync.json"  # FEAT-13: an update from GitHub changed the packages
if (-not $Uv) {
    $found = Get-Command uv -ErrorAction SilentlyContinue
    if ($found) { $Uv = $found.Source }
    elseif (Test-Path -LiteralPath (Join-Path $env:USERPROFILE ".local\bin\uv.exe")) { $Uv = Join-Path $env:USERPROFILE ".local\bin\uv.exe" }
}

# A shortcut made before 2026-10-25 still opens a console: hide it when there is one (a start with no window has none).
$console = [Kickoff.Win32Window]::GetConsoleWindow()
if ($console -ne [IntPtr]::Zero) { [Kickoff.Win32Window]::ShowWindow($console, 0) | Out-Null }

$env:KICKOFF_NO_PAUSE = "1"  # the server never waits for an answer in a hidden window (app/portcheck.py)
$env:KICKOFF_RELAUNCH = "1"  # BUG-22: a restart exits with 8 and this tray starts the server again

# A child with no window: the server, or the program asked to save a port.
function New-Child([string[]]$Arguments) {
    $info = New-Object System.Diagnostics.ProcessStartInfo
    $all = @()
    if ($Program) {
        $info.FileName = $Program
        $info.WorkingDirectory = Split-Path -Parent $Program
    } else {
        $info.FileName = $Python
        $info.WorkingDirectory = $Root
        $all += "-m", "app"
    }
    $info.Arguments = (($all + $Arguments) -join " ")
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    return [System.Diagnostics.Process]::Start($info)
}

function Start-Server([switch]$First, [switch]$Restarted) {
    if (Test-Path -LiteralPath $reportFile) { Remove-Item -LiteralPath $reportFile -Force -ErrorAction SilentlyContinue }
    $serverArgs = @()
    if ($Login -and $First) { $serverArgs += "--login" }  # started at login: no browser unless Settings say Always
    if ($Restarted) { $serverArgs += "--restarted" }  # the same server again: no browser, and the port may need a moment
    $script:server = New-Child $serverArgs
    $script:startedAt = Get-Date
    $script:ready = $false
    $script:slowWarned = $false
    $script:pending = $null
}

$icon = New-Object System.Windows.Forms.NotifyIcon
# The Myers Labs sun (owner 2026-10-23): the packaged program carries it; a checkout has static\icons\kickoff.ico.
$icon.Icon = [System.Drawing.SystemIcons]::Application
try {
    $sun = Join-Path $Root "static\icons\kickoff.ico"
    if ($Program) { $icon.Icon = [System.Drawing.Icon]::ExtractAssociatedIcon($Program) }
    elseif (Test-Path -LiteralPath $sun) { $icon.Icon = New-Object System.Drawing.Icon($sun, 16, 16) }
} catch {
    $icon.Icon = [System.Drawing.SystemIcons]::Application
}
$icon.Text = "Kickoff Companion: starting"
$icon.Visible = $true

function Show-Note([string]$Message, [System.Windows.Forms.ToolTipIcon]$Kind = [System.Windows.Forms.ToolTipIcon]::Info) {
    $icon.ShowBalloonTip(5000, "Kickoff Companion", $Message, $Kind)
}

function Exit-Tray([int]$WaitSeconds = 0) {
    if ($WaitSeconds -gt 0) { Start-Sleep -Seconds $WaitSeconds }  # the last notification stays long enough to read
    $icon.Visible = $false
    [System.Windows.Forms.Application]::Exit()
}

$script:quitting = $false
$script:syncing = $null
$menu = New-Object System.Windows.Forms.ContextMenuStrip
$open = $menu.Items.Add("Open the app")
$open.add_Click({ Start-Process $script:appUrl })
$status = $menu.Items.Add("Status page")
$status.add_Click({ Start-Process $script:statusUrl })
$log = $menu.Items.Add("Show the log")
$log.add_Click({ if (Test-Path -LiteralPath $logFile) { Start-Process notepad.exe $logFile } })
$menu.Items.Add("-") | Out-Null
$quit = $menu.Items.Add("Quit (stops the server)")
$quit.add_Click({
    $script:quitting = $true
    $timer.Stop()
    try { if (-not $script:server.HasExited) { Stop-Process -Id $script:server.Id -Force } } catch {}
    Exit-Tray
})
$icon.ContextMenuStrip = $menu
$icon.add_DoubleClick({ Start-Process $script:appUrl })

# --- the clock: seconds while it starts, then one notification -------------------------------------------------
$http = New-Object System.Net.Http.HttpClient
$http.Timeout = [TimeSpan]::FromSeconds(3)

# The health answer is read with patterns, not ConvertFrom-Json: Windows PowerShell refuses a document whose keys differ
# only in case, and the health page is large and varied. open_seconds is null until the opening pages have their data
# (or 30 s went by); browser_opened says whether the server opened the app then (a start by hand, Settings' choice).
function Test-Ready([string]$Body, [int]$Seconds) {
    if ($Body -notmatch '"open_seconds":\s*([0-9.]+)') { return }  # listening, but the data is not ready yet
    $took = [int][Math]::Round([double]$Matches[1])
    $setup = $Body -match '"setup_needed":\s*true'
    $opened = $Body -match '"browser_opened":\s*true'
    $script:ready = $true
    $icon.Text = "Kickoff Companion (port $($script:port))"
    if ($setup) {
        $next = if ($opened) { "The setup page is open in your browser." } else { "Double-click the sun by the clock to finish the setup." }
        Show-Note "Running after $took s. $next"
    } else {
        $next = if ($opened) { "The app is open in your browser." } else { "Double-click the sun by the clock to open the app." }
        Show-Note "Ready after $took s. $next"
    }
}

# --- a start that fails: the window with the report ---------------------------------------------------------------
function Get-Report([int]$Code) {
    $report = $null
    if (Test-Path -LiteralPath $reportFile) {
        try { $report = Get-Content -LiteralPath $reportFile -Raw -Encoding UTF8 | ConvertFrom-Json } catch { $report = $null }
    }
    $lines = @()
    if ($report -and $report.message) { $lines += ($report.message -split "`n") }
    else { $lines += "The server stopped with exit code $Code." }
    $lines += ""
    $lines += "Kickoff Companion, $(Get-Date -Format 'yyyy-MM-dd HH:mm'), $([Environment]::OSVersion.VersionString)"
    if (Test-Path -LiteralPath $logFile) {
        $tail = Get-Content -LiteralPath $logFile -Tail 40 -Encoding UTF8 -ErrorAction SilentlyContinue
        if ($tail) { $lines += ""; $lines += "The last lines of $($logFile):"; $lines += $tail }
    }
    $next = $null
    if ($report -and $report.nextPort) { $next = [int]$report.nextPort }
    return @{ Text = ($lines -join "`r`n"); Next = $next }
}

function New-Button([string]$Text) {
    $button = New-Object System.Windows.Forms.Button
    $button.Text = $Text
    $button.AutoSize = $true
    $button.Padding = New-Object System.Windows.Forms.Padding(8, 4, 8, 4)
    $button.Margin = New-Object System.Windows.Forms.Padding(6, 0, 0, 0)
    return $button
}

function Show-Failure([string]$Title, [int]$Code) {
    $info = Get-Report $Code
    $form = New-Object System.Windows.Forms.Form
    $form.Text = "Kickoff Companion"
    $form.Icon = $icon.Icon
    $form.StartPosition = "CenterScreen"
    $form.Size = New-Object System.Drawing.Size(680, 480)
    $form.MinimumSize = New-Object System.Drawing.Size(480, 320)
    $form.TopMost = $true
    $form.Font = New-Object System.Drawing.Font("Segoe UI", 10)
    $form.Tag = "close"

    $box = New-Object System.Windows.Forms.TextBox
    $box.Multiline = $true
    $box.ReadOnly = $true
    $box.ScrollBars = "Vertical"
    $box.Dock = "Fill"
    $box.Font = New-Object System.Drawing.Font("Consolas", 9.5)
    $box.Text = $info.Text

    $head = New-Object System.Windows.Forms.Label
    $head.Text = $Title
    $head.Font = New-Object System.Drawing.Font("Segoe UI Semibold", 13)
    $head.Dock = "Top"
    $head.Height = 44
    $head.Padding = New-Object System.Windows.Forms.Padding(10, 10, 10, 0)

    $row = New-Object System.Windows.Forms.FlowLayoutPanel
    $row.Dock = "Bottom"
    $row.FlowDirection = "RightToLeft"
    $row.Height = 56
    $row.Padding = New-Object System.Windows.Forms.Padding(10)

    $close = New-Button "Close"
    $close.add_Click({ $form.Tag = "close"; $form.Close() })
    $copy = New-Button "Copy the report"
    $copy.add_Click({
        try { [System.Windows.Forms.Clipboard]::SetText($info.Text); $copy.Text = "Copied" } catch { $copy.Text = "Copy failed" }
    })
    $showLog = New-Button "Show the log"
    $showLog.add_Click({ if (Test-Path -LiteralPath $logFile) { Start-Process notepad.exe $logFile } })
    $row.Controls.Add($close)
    $row.Controls.Add($copy)
    $row.Controls.Add($showLog)
    if ($info.Next) {
        $next = $info.Next
        $use = New-Button "Use port $next"
        $use.add_Click({
            $use.Enabled = $false
            $saver = New-Child @("--use-port", "$next")
            $saver.WaitForExit(30000) | Out-Null
            if ($saver.HasExited -and $saver.ExitCode -eq 0) {
                $form.Tag = "retry"
                $form.Close()
            } else {
                $use.Text = "Could not save port $next"
            }
        })
        $row.Controls.Add($use)
        $form.AcceptButton = $use
    }
    # docked in reverse order of adding: the report takes what the head and the buttons leave
    $form.Controls.Add($box)
    $form.Controls.Add($row)
    $form.Controls.Add($head)
    [void]$form.ShowDialog()
    return [string]$form.Tag
}

function Start-Sync {
    $info = New-Object System.Diagnostics.ProcessStartInfo
    $info.FileName = $Uv
    $info.WorkingDirectory = $Root
    $info.Arguments = "sync --frozen --quiet --no-dev --inexact"
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    try { return [System.Diagnostics.Process]::Start($info) } catch { return $null }
}

function Receive-Exit {
    if ($script:quitting) { return }
    $code = $script:server.ExitCode
    if ($code -eq $Relaunch) {
        # a restart from the app or an update: a fresh process loads the new code; an update that changed the packages
        # gets them first, while no server holds them open
        $script:syncing = $null
        if ($Uv -and (Test-Path -LiteralPath $syncFile)) {
            $icon.Text = "Kickoff Companion: updating the packages"
            $script:syncing = Start-Sync
        }
        if (-not $script:syncing) {
            $icon.Text = "Kickoff Companion: restarting"
            Start-Server -Restarted
        }
        $timer.Start()
        return
    }
    if ($code -eq $AlreadyRunning) {
        $opened = if ($Login) { "" } else { " Your browser opens it." }  # at login the browser opens only if Settings say Always
        Show-Note "Kickoff Companion is already running, so this start stepped aside.$opened"
        Exit-Tray 5
        return
    }
    if ($code -eq 0) {
        Exit-Tray
        return
    }
    $title = if ($script:ready) { "Kickoff Companion stopped (exit code $code)" } else { "Kickoff Companion could not start" }
    $icon.Text = "Kickoff Companion: stopped"
    if ((Show-Failure $title $code) -eq "retry") {
        Set-Address
        Start-Server
        $timer.Start()
        return
    }
    Exit-Tray
}

$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 1000
$timer.add_Tick({
    if ($script:syncing) {
        if (-not $script:syncing.HasExited) { return }
        $synced = $script:syncing.ExitCode
        $script:syncing = $null
        if ($synced -eq 0) { Remove-Item -LiteralPath $syncFile -Force -ErrorAction SilentlyContinue }
        else { Show-Note "The packages did not update (uv exit code $synced). Starting anyway; the log says more." ([System.Windows.Forms.ToolTipIcon]::Warning) }
        $icon.Text = "Kickoff Companion: restarting"
        Start-Server -Restarted
        return
    }
    if ($script:server.HasExited) {
        $timer.Stop()
        Receive-Exit
        return
    }
    if ($script:ready) { return }
    $seconds = [int][Math]::Floor(((Get-Date) - $script:startedAt).TotalSeconds)
    $icon.Text = "Kickoff Companion: starting, $seconds s"
    $task = $script:pending
    if ($task -and $task.IsCompleted) {
        $script:pending = $null
        if ($task.Status -eq [System.Threading.Tasks.TaskStatus]::RanToCompletion) { Test-Ready $task.Result $seconds }
    }
    if (-not $script:ready -and -not $script:pending) {
        try { $script:pending = $http.GetStringAsync($script:healthUrl) } catch { $script:pending = $null }
    }
    if (-not $script:ready -and $seconds -ge $SlowSeconds -and -not $script:slowWarned) {
        $script:slowWarned = $true
        Show-Note "Still starting after 2 minutes. The icon's menu has Show the log." ([System.Windows.Forms.ToolTipIcon]::Warning)
    }
})

Start-Server -First
$timer.Start()

[System.Windows.Forms.Application]::Run()
$timer.Stop()
$http.Dispose()
$icon.Dispose()
exit 0
