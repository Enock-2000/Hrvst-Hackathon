<#
.SYNOPSIS
  Download LocateAnything-3B (~7.6 GB) into models/LocateAnything-3B for offline transfer.

.EXAMPLE
  .\scripts\Download-LocateAnythingModel.ps1
#>
$ErrorActionPreference = "Stop"
$Runtime = Split-Path $PSScriptRoot -Parent
$Python = $null
foreach ($name in @(".venv", ".venv-locateanything")) {
    $candidate = Join-Path $Runtime "$name\Scripts\python.exe"
    if (Test-Path $candidate) { $Python = $candidate; break }
}
if (-not $Python) {
    Write-Error "No venv found. Run .\scripts\Install.ps1 first."
}
& $Python "$Runtime\scripts\download_locateanything_model.py" @args
exit $LASTEXITCODE
