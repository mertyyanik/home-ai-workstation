# Read-only checks. No installations, configuration changes or restarts.
param([string]$Distro = 'Ubuntu')

$ErrorActionPreference = 'Continue'
$script:Failures = 0

function Invoke-Check {
    param([string]$Label, [string]$Command, [string[]]$Arguments = @(), [switch]$LinuxOutput)
    Write-Host "`n== $Label =="
    if (-not (Get-Command $Command -ErrorAction SilentlyContinue) -and
        -not (Test-Path -LiteralPath $Command)) {
        Write-Host "FAIL: command not found: $Command"
        $script:Failures++
        return
    }
    $info = [Diagnostics.ProcessStartInfo]::new()
    $info.FileName = if (Test-Path -LiteralPath $Command) { $Command } else { (Get-Command $Command).Source }
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    if ($Command -eq 'wsl' -and -not $LinuxOutput) {
        # Redirected output from wsl.exe itself is UTF-16LE, unlike Linux programs.
        $info.StandardOutputEncoding = [Text.Encoding]::Unicode
        $info.StandardErrorEncoding = [Text.Encoding]::Unicode
    }
    # All arguments below are fixed, space-free tokens defined by this script.
    $info.Arguments = $Arguments -join ' '
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $info
    try {
        [void]$process.Start()
        $stdout = $process.StandardOutput.ReadToEndAsync()
        $stderr = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit(15000)) {
            $process.Kill()
            Write-Host 'FAIL: read-only check timed out after 15 seconds.'
            $script:Failures++
            return
        }
        Write-Host $stdout.GetAwaiter().GetResult()
        Write-Host $stderr.GetAwaiter().GetResult()
        $resultCode = $process.ExitCode
    } catch {
        Write-Host ('FAIL: could not run check: ' + $_.Exception.Message)
        $script:Failures++
        return
    } finally { $process.Dispose() }
    if ($resultCode -ne 0) {
        Write-Host "FAIL: exit code $resultCode"
        $script:Failures++
    }
}

Write-Host 'Home AI Workstation: Windows preflight'
try {
    $cpu = Get-CimInstance Win32_Processor -ErrorAction Stop
    if (@($cpu | Where-Object { -not $_.VirtualizationFirmwareEnabled }).Count -gt 0) {
        Write-Host 'FAIL: firmware virtualization disabled. Enable AMD SVM / Intel VT-x in BIOS.'
        $script:Failures++
    }
} catch {
    Write-Host ('FAIL: unable to verify firmware virtualization: ' + $_.Exception.Message)
    $script:Failures++
}
if (Test-Path -LiteralPath 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending') {
    Write-Host 'FAIL: Windows reports a pending restart. Restart manually when ready.'
    $script:Failures++
}
$systemDrive = Get-PSDrive -Name $env:SystemDrive.TrimEnd(':') -ErrorAction SilentlyContinue
if ($systemDrive) {
    $freeGiB = [math]::Floor($systemDrive.Free / 1GB)
    Write-Host "Free space on ${env:SystemDrive}: $freeGiB GiB"
    if ($freeGiB -lt 30) {
        Write-Host 'FAIL: less than 30 GiB free. Images and models need more space.'
        $script:Failures++
    }
}
Invoke-Check -Label 'NVIDIA' -Command 'nvidia-smi' -Arguments @('--query-gpu=name,memory.total,driver_version', '--format=csv,noheader')
Invoke-Check -Label 'WSL version' -Command 'wsl' -Arguments @('--version')
Invoke-Check -Label 'WSL status (exit zero alone does not prove WSL2 works)' -Command 'wsl' -Arguments @('--status')
Invoke-Check -Label "WSL distributions: $Distro must show VERSION 2" -Command 'wsl' -Arguments @('--list', '--verbose')

$dockerCommand = 'docker'
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    foreach ($candidate in @(
        (Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin\docker.exe'),
        (Join-Path $env:ProgramFiles 'Docker\Docker\resources\bin\docker.exe')
    )) {
        if (Test-Path -LiteralPath $candidate) { $dockerCommand = $candidate; break }
    }
}
Invoke-Check -Label 'Docker client and engine' -Command $dockerCommand -Arguments @('version')
Invoke-Check -Label 'Compose' -Command $dockerCommand -Arguments @('compose', 'version')
$before = $script:Failures
Invoke-Check -Label "Docker from $Distro" -Command 'wsl' -LinuxOutput -Arguments @('-d', $Distro, '--', 'docker', 'version', '--format', '{{.Server.Version}}')
if ($script:Failures -gt $before) {
    Write-Host "Fix: Docker Desktop > Settings > Resources > WSL Integration > enable $Distro."
}
Write-Host "`nFailed or unverified checks: $script:Failures"
Write-Host "Continue only after $Distro VERSION=2, Docker engine and the WSL GPU compute test pass."
if ($script:Failures -gt 0) { exit 1 }
exit 0
