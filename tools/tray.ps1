<#
Kickoff Companion in the system tray (Phase 9, owner direction 2026-09-23: always visible, but
optionally in the tray instead of a taskbar window).

Started by start.ps1 -Tray. Hides its own console window, starts the server as a hidden
child process, and shows a tray icon with a menu: Open the app, Status page, Show the log, Quit.
Quit stops the server. The server's own log stays in logs\app.log.

Phase 16 wave 3: the packaged program uses it too. Its Desktop icon and Startup shortcut run this script with
-Program (the program's .exe) instead of -Python; -Root is then the folder that holds .env, data and logs.
The address is http:// unless HTTPS=on in .env (plain HTTP has been the default since public release Phase 4b).
#>
param(
    [string]$Python,
    [string]$Program,
    [Parameter(Mandatory = $true)][string]$Root,
    [switch]$Login
)
if (-not $Python -and -not $Program) { throw "Give -Python (a checkout) or -Program (the packaged program)." }

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
Add-Type -Name Win32Window -Namespace Kickoff -MemberDefinition @'
[DllImport("kernel32.dll")] public static extern IntPtr GetConsoleWindow();
[DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
'@

function Read-EnvValue($name, $fallback) {
    $envFile = Join-Path $Root ".env"
    if (Test-Path -LiteralPath $envFile) {
        foreach ($line in Get-Content -LiteralPath $envFile) {
            if ($line -match "^\s*$name\s*=\s*(.+?)\s*$") { return $Matches[1].Trim('"').Trim("'") }
        }
    }
    return $fallback
}

$port = Read-EnvValue "PORT" "8642"
$hostName = Read-EnvValue "LAN_HOSTNAME" "localhost"
if (-not $hostName) { $hostName = "localhost" }
$scheme = if ((Read-EnvValue "HTTPS" "off") -match "^(on|true|1|yes)$") { "https" } else { "http" }
$appUrl = "$scheme`://$hostName`:$port/"
$statusUrl = "$scheme`://$hostName`:$port/status"
$logFile = Join-Path $Root "logs\app.log"

# Hide this console (0 = SW_HIDE). It comes back with "Show the window".
$console = [Kickoff.Win32Window]::GetConsoleWindow()
[Kickoff.Win32Window]::ShowWindow($console, 0) | Out-Null

$env:KICKOFF_NO_PAUSE = "1"  # the packaged program never waits for Enter in a hidden window
if ($Program) {
    $serverArgs = @()
    if ($Login) { $serverArgs += "--login" }  # started at login: no browser unless Settings say Always
    $startArgs = @{ FilePath = $Program; WorkingDirectory = (Split-Path -Parent $Program); WindowStyle = "Hidden"; PassThru = $true }
    if ($serverArgs.Count -gt 0) { $startArgs.ArgumentList = $serverArgs }
    $server = Start-Process @startArgs
} else {
    $serverArgs = @("-m", "app")
    if ($Login) { $serverArgs += "--login" }
    $server = Start-Process -FilePath $Python -ArgumentList $serverArgs -WorkingDirectory $Root -WindowStyle Hidden -PassThru
}

$icon = New-Object System.Windows.Forms.NotifyIcon
$icon.Icon = [System.Drawing.SystemIcons]::Application
$icon.Text = "Kickoff Companion (port $port)"
$icon.Visible = $true

$menu = New-Object System.Windows.Forms.ContextMenuStrip
$open = $menu.Items.Add("Open the app")
$open.add_Click({ Start-Process $appUrl })
$status = $menu.Items.Add("Status page")
$status.add_Click({ Start-Process $statusUrl })
$log = $menu.Items.Add("Show the log")
$log.add_Click({ if (Test-Path -LiteralPath $logFile) { Start-Process notepad.exe $logFile } })
$show = $menu.Items.Add("Show the window")
$show.add_Click({ [Kickoff.Win32Window]::ShowWindow($console, 5) | Out-Null })
$menu.Items.Add("-") | Out-Null
$quit = $menu.Items.Add("Quit (stops the server)")
$quit.add_Click({
    try { if (-not $server.HasExited) { Stop-Process -Id $server.Id -Force } } catch {}
    $icon.Visible = $false
    [System.Windows.Forms.Application]::Exit()
})
$icon.ContextMenuStrip = $menu
$icon.add_DoubleClick({ Start-Process $appUrl })
$icon.ShowBalloonTip(4000, "Kickoff Companion", "The server is running. Double-click the icon to open the app.", [System.Windows.Forms.ToolTipIcon]::Info)

# Leave the tray if the server dies on its own.
$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 5000
$timer.add_Tick({
    if ($server.HasExited) {
        $icon.ShowBalloonTip(6000, "Kickoff Companion", "The server stopped (exit code $($server.ExitCode)). See logs\app.log.", [System.Windows.Forms.ToolTipIcon]::Warning)
        Start-Sleep -Seconds 6
        $icon.Visible = $false
        [System.Windows.Forms.Application]::Exit()
    }
})
$timer.Start()

[System.Windows.Forms.Application]::Run()
$icon.Dispose()
exit 0
