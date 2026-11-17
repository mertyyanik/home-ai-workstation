# Publish the Web UI and optional SSH to your own Tailscale network. Safe to run again.
# It never uses Funnel, and it never forwards Ollama, which has no login.
#
#   powershell -ExecutionPolicy Bypass -File scripts\setup-remote.ps1 [-Ssh] [-Panel] [-Hermes] [-HermesDashboard]
param(
    [switch]$Ssh,
    [switch]$Panel,
    [switch]$Hermes,
    [switch]$HermesDashboard,
    [string]$Distro = 'Ubuntu',
    [ValidateRange(1, 65535)][int]$WebPort = 3000,
    [ValidateRange(1, 65535)][int]$SshPort = 2222,
    [ValidateRange(1, 65535)][int]$PanelPort = 8088,
    [ValidateRange(1, 65535)][int]$PanelPublicPort = 8443,
    [ValidateRange(1, 65535)][int]$HermesPort = 9120,
    [ValidateRange(1, 65535)][int]$HermesPublicPort = 9444,
    [ValidateRange(1, 65535)][int]$HermesDashboardPort = 9119,
    [ValidateRange(1, 65535)][int]$HermesDashboardPublicPort = 9445
)

$ErrorActionPreference = 'Stop'

$tailscale = (Get-Command tailscale -ErrorAction SilentlyContinue).Source
if (-not $tailscale) {
    $default = Join-Path $env:ProgramFiles 'Tailscale\tailscale.exe'
    if (Test-Path -LiteralPath $default) { $tailscale = $default }
}
if (-not $tailscale) {
    Write-Host 'Tailscale is not installed. Install it from https://tailscale.com/download, sign in, and run this again.'
    exit 1
}

$state = (& $tailscale status --json | Out-String) | ConvertFrom-Json
if ($state.BackendState -ne 'Running') {
    Write-Host 'Tailscale is not connected. Sign in from the Tailscale app, then run this again.'
    exit 1
}
$hostName = $state.Self.DNSName.TrimEnd('.')

function Get-ServeStatus {
    return (& $tailscale serve status 2>&1 | Out-String)
}

function Test-LocalPort {
    param([int]$Port)
    $client = New-Object Net.Sockets.TcpClient
    try {
        $attempt = $client.BeginConnect('127.0.0.1', $Port, $null, $null)
        return ($attempt.AsyncWaitHandle.WaitOne(3000) -and $client.Connected)
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

if ((Get-ServeStatus) -match 'Funnel on') {
    Write-Host 'WARNING: Funnel is on, which exposes a service to the internet. Turn it off.'
}

if (-not (Test-LocalPort -Port $WebPort)) {
    Write-Host "Nothing is listening on 127.0.0.1:$WebPort. Run the installation first."
    exit 1
}
if ((Get-ServeStatus) -match "proxy http://127\.0\.0\.1:$WebPort") {
    Write-Host 'Web UI is already published.'
} else {
    Write-Host 'Publishing the Web UI. If a link appears, open it and approve HTTPS.'
    & $tailscale serve --bg $WebPort
    if ($LASTEXITCODE -ne 0) { exit 1 }
}
Write-Host "Web UI: https://$hostName (only for devices in your Tailscale network)"

if ($Ssh) {
    if (-not (Test-LocalPort -Port $SshPort)) {
        Write-Host "`nSSH is not listening on 127.0.0.1:$SshPort. In Ubuntu, run:"
        Write-Host '  sudo bash scripts/setup-wsl-ssh.sh'
        exit 1
    }
    if ((Get-ServeStatus) -match "tcp://127\.0\.0\.1:$SshPort") {
        Write-Host 'SSH is already forwarded.'
    } else {
        & $tailscale serve --bg "--tcp=$SshPort" "tcp://127.0.0.1:$SshPort"
        if ($LASTEXITCODE -ne 0) { exit 1 }
    }
    Write-Host "`nAdd your client's public key to ~/.ssh/authorized_keys in Ubuntu."
    Write-Host 'Then add this to ~/.ssh/config on the client:'
    Write-Host ''
    Write-Host 'Host aiws'
    Write-Host "  HostName $hostName"
    Write-Host "  Port $SshPort"
    Write-Host '  User YOUR_UBUNTU_USER'
    Write-Host '  IdentityFile ~/.ssh/aiws_ed25519'
    Write-Host '  IdentitiesOnly yes'
}

if ($Panel) {
    if (-not (Test-LocalPort -Port $PanelPort)) {
        Write-Host "`nThe status panel is not listening on 127.0.0.1:$PanelPort. In Ubuntu, run:"
        Write-Host '  sudo bash scripts/setup-panel-service.sh'
        exit 1
    }
    # This fails unless a panel password exists, so the panel is never published without login.
    $repository = Split-Path -Parent $PSScriptRoot
    & wsl -d $Distro --cd $repository -- bash scripts/aiws.sh panel-allow $hostName
    if ($LASTEXITCODE -ne 0) { exit 1 }
    if ((Get-ServeStatus) -match "proxy http://127\.0\.0\.1:$PanelPort") {
        Write-Host 'Status panel is already published.'
    } else {
        & $tailscale serve --bg "--https=$PanelPublicPort" $PanelPort
        if ($LASTEXITCODE -ne 0) { exit 1 }
    }
    Write-Host "Status panel: https://${hostName}:$PanelPublicPort (sign-in required)"
}

if ($Hermes) {
    # Only the Hermes web app is published. Its dashboard, which manages keys and
    # settings, stays on this PC.
    if (-not (Test-LocalPort -Port $HermesPort)) {
        Write-Host "`nHermes is not listening on 127.0.0.1:$HermesPort. In Ubuntu, run:"
        Write-Host '  bash scripts/aiws.sh hermes password'
        Write-Host '  bash scripts/aiws.sh hermes up'
        exit 1
    }
    # Hermes only listens once a password exists, so it is never published without login.
    $repository = Split-Path -Parent $PSScriptRoot
    & wsl -d $Distro --cd $repository -- bash scripts/aiws.sh hermes allow "https://${hostName}:$HermesPublicPort"
    if ($LASTEXITCODE -ne 0) { exit 1 }
    if ((Get-ServeStatus) -match "proxy http://127\.0\.0\.1:$HermesPort") {
        Write-Host 'Hermes is already published.'
    } else {
        & $tailscale serve --bg "--https=$HermesPublicPort" $HermesPort
        if ($LASTEXITCODE -ne 0) { exit 1 }
    }
    Write-Host "Hermes: https://${hostName}:$HermesPublicPort (sign-in required)"
}

if ($HermesDashboard) {
    # The dashboard manages keys, settings and extensions. Hermes desktop and mobile apps
    # connect to it, so publish it only when you use one of them.
    if (-not (Test-LocalPort -Port $HermesDashboardPort)) {
        Write-Host "`nThe Hermes dashboard is not listening on 127.0.0.1:$HermesDashboardPort. In Ubuntu, run:"
        Write-Host '  bash scripts/aiws.sh hermes up'
        exit 1
    }
    $repository = Split-Path -Parent $PSScriptRoot
    & wsl -d $Distro --cd $repository -- bash scripts/aiws.sh hermes allow "https://${hostName}:$HermesDashboardPublicPort" dashboard
    if ($LASTEXITCODE -ne 0) { exit 1 }
    if ((Get-ServeStatus) -match "proxy http://127\.0\.0\.1:$HermesDashboardPort") {
        Write-Host 'The Hermes dashboard is already published.'
    } else {
        & $tailscale serve --bg "--https=$HermesDashboardPublicPort" $HermesDashboardPort
        if ($LASTEXITCODE -ne 0) { exit 1 }
    }
    Write-Host "Hermes dashboard and apps: https://${hostName}:$HermesDashboardPublicPort (sign-in required)"
}
exit 0
