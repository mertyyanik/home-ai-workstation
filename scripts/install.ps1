# Install Home AI Workstation from Windows PowerShell. Safe to run again.
# Run it from the project folder. Administrator rights are not needed.
#
#   powershell -ExecutionPolicy Bypass -File scripts\install.ps1
param(
    [string]$Distro = 'Ubuntu',
    [switch]$SkipGpuTest,
    [switch]$SkipModels
)

$ErrorActionPreference = 'Stop'
$repository = Split-Path -Parent $PSScriptRoot

Write-Host 'Home AI Workstation: installation'
Write-Host "Project folder: $repository"
Write-Host "Linux distribution: $Distro"

& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'windows-check.ps1') -Distro $Distro
if ($LASTEXITCODE -ne 0) {
    Write-Host "`nInstallation stopped. Fix the checks marked FAIL above, then run this again."
    exit 1
}

$arguments = @('-d', $Distro, '--cd', $repository, '--', 'bash', 'scripts/aiws.sh', 'install')
if ($SkipGpuTest) { $arguments += '--skip-gpu-test' }
if ($SkipModels) { $arguments += '--skip-models' }

Write-Host "`nContinuing inside ${Distro}..."
& wsl @arguments
if ($LASTEXITCODE -ne 0) {
    Write-Host "`nInstallation failed. Read the error above, then run this again."
    exit 1
}

Write-Host "`nOptional remote access: powershell -ExecutionPolicy Bypass -File scripts\setup-remote.ps1"
exit 0
