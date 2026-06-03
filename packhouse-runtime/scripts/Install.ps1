<#
.SYNOPSIS
  Create .venv (Python 3.12) with CUDA PyTorch + LocateAnything dependencies.

.EXAMPLE
  .\scripts\Install.ps1
  .\scripts\Install.ps1 -CudaIndex cu124
#>
param(
    [string]$CudaIndex = "cu124"
)

$ErrorActionPreference = "Stop"
$Runtime = Split-Path $PSScriptRoot -Parent
$Venv = Join-Path $Runtime ".venv"
$Pip = Join-Path $Venv "Scripts\pip.exe"
$Python = Join-Path $Venv "Scripts\python.exe"

$PyLauncher = "python"
if (Get-Command py -ErrorAction SilentlyContinue) {
    py -3.12 -c "pass" 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { $PyLauncher = "py -3.12" }
}

if (-not (Test-Path $Pip)) {
    Write-Host "Creating .venv with $PyLauncher ..."
    Invoke-Expression "$PyLauncher -m venv `"$Venv`""
}

Write-Host "Upgrading pip..."
& $Python -m pip install --upgrade pip wheel -q

Write-Host "Installing PyTorch CUDA ($CudaIndex)..."
& $Python -m pip install --force-reinstall torch torchvision --index-url "https://download.pytorch.org/whl/$CudaIndex"

Write-Host "Installing Pack House requirements..."
& $Python -m pip install -r (Join-Path $Runtime "requirements.txt")

Write-Host ""
& $Python (Join-Path $Runtime "scripts\test_locateanything_install.py")

Write-Host ""
Write-Host "Next: download model weights (~7.6 GB):"
Write-Host "  .\scripts\Download-LocateAnythingModel.ps1"
