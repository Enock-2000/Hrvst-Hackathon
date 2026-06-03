<#
.SYNOPSIS
  Quick install check; optional model smoke test (downloads ~7.6 GB on first run).

.EXAMPLE
  .\scripts\Test-LocateAnything.ps1
  .\scripts\Test-LocateAnything.ps1 -Smoke
  .\scripts\Test-LocateAnything.ps1 -Smoke -AllowCpu
#>
param(
    [switch]$Smoke,
    [switch]$AllowCpu
)

$Runtime = Split-Path $PSScriptRoot -Parent
$Python = Join-Path $Runtime ".venv-locateanything\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    Write-Error "Run scripts\Install-LocateAnything.ps1 first."
}
$args = @("$Runtime\scripts\test_locateanything_install.py")
if ($Smoke) { $args += "--smoke" }
if ($AllowCpu) { $args += "--allow-cpu" }
& $Python @args
exit $LASTEXITCODE
