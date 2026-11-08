# Keep Large Send Offload off on the WSL network adapter, which can slow downloads in
# Ubuntu to a few KB/s. Windows turns it back on when the adapter is recreated, so the
# install option adds a scheduled task that checks at sign-in and every 5 minutes.
# Run in PowerShell as Administrator:
#
#   powershell -ExecutionPolicy Bypass -File scripts\fix-wsl-lso.ps1 -Now
#   powershell -ExecutionPolicy Bypass -File scripts\fix-wsl-lso.ps1 -Install
#   powershell -ExecutionPolicy Bypass -File scripts\fix-wsl-lso.ps1 -Uninstall
#   powershell -ExecutionPolicy Bypass -File scripts\fix-wsl-lso.ps1 -Status
param(
    [switch]$Now,
    [switch]$Install,
    [switch]$Uninstall,
    [switch]$Status
)

$ErrorActionPreference = 'Stop'
$taskName = 'Home AI Workstation - WSL LSO off'
$adapterPattern = 'vEthernet (WSL*'

# The task embeds this command instead of running a file. A file in the project folder
# can be changed without admin rights, and the task runs as SYSTEM. It changes only an
# adapter that has LSO on, so an adapter that is already fixed is not reset every 5 minutes.
$command = "Get-NetAdapterLso -Name '$adapterPattern' -IncludeHidden -ErrorAction SilentlyContinue | " +
    "Where-Object { `$_.IPv4Enabled -or `$_.IPv6Enabled } | Disable-NetAdapterLso -ErrorAction SilentlyContinue"

function Show-Status {
    $adapters = @(Get-NetAdapterLso -Name $adapterPattern -IncludeHidden -ErrorAction SilentlyContinue)
    if (-not $adapters) { Write-Host 'No WSL network adapter found. Start Ubuntu or Docker Desktop first.' }
    foreach ($adapter in $adapters) {
        Write-Host "$($adapter.Name): LSO IPv4=$($adapter.IPv4Enabled) IPv6=$($adapter.IPv6Enabled)"
    }
    # A task that runs as SYSTEM is hidden from a non-admin shell.
    $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($task) { $state = $task.State }
    elseif (Test-Admin) { $state = 'not installed' }
    else { $state = 'unknown; run as Administrator to see it' }
    Write-Host "Scheduled task: $state"
}

function Test-Admin {
    $principal = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not ($Now -or $Install -or $Uninstall -or $Status)) {
    Write-Host 'Choose one option: -Now, -Install, -Uninstall or -Status.'
    exit 2
}
if ($Status) {
    Show-Status
    exit 0
}

if (-not (Test-Admin)) {
    Write-Host 'Run this in PowerShell as Administrator.'
    exit 1
}

if ($Uninstall) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host 'Scheduled task removed. LSO stays as it is until the adapter is recreated.'
    Write-Host "To turn it back on now: Enable-NetAdapterLso -Name '$adapterPattern' -IncludeHidden"
    exit 0
}

Invoke-Expression $command

if ($Install) {
    $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($command))
    $action = New-ScheduledTaskAction -Execute 'powershell.exe' `
        -Argument "-NoProfile -NonInteractive -WindowStyle Hidden -EncodedCommand $encoded"
    $atLogon = New-ScheduledTaskTrigger -AtLogOn
    $repeat = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 5)
    $system = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 2) -MultipleInstances IgnoreNew
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger @($atLogon, $repeat) `
        -Principal $system -Settings $settings -Force | Out-Null
    Write-Host 'Scheduled task installed. It checks at sign-in and every 5 minutes.'
}

Show-Status
exit 0
