<#
.SYNOPSIS
  Start the full Pack House deployment: Eufy camera bridge + live YOLO + truck-arrival alerts.

.EXAMPLE
  .\Start-PackHouse.ps1
  Starts Docker (if needed), waits for RTSP, then runs alerts.ps1 for vision + API alerts.

.EXAMPLE
  .\Start-PackHouse.ps1 -NoShow
  Headless mode - saves annotated video under packhouse-runtime/runs/live/

.EXAMPLE
  .\Start-PackHouse.ps1 -Device xpu
  Use Intel XPU for inference (requires torch+xpu in venv).
#>
param(
    [switch]$NoShow,
    [string]$Device = "cpu",
    [string]$Model = "packhouse_best.pt",
    [float]$Conf = 0.35,
    [switch]$Track,
    [switch]$SkipDocker
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$ScriptsDir = Join-Path $Root "scripts"
$VisionDir = Join-Path $Root "packhouse-runtime"
$ModelPath = Join-Path (Join-Path $VisionDir "models") $Model
$AlertsScript = Join-Path $Root "alerts.ps1"

. (Join-Path $ScriptsDir "CameraReady.ps1")

Write-Host "========================================"
Write-Host "  Pack House - Start"
Write-Host "========================================"
Write-Host ""

if (-not (Test-Path $ModelPath)) {
    Write-Error "Model not found: $ModelPath"
    exit 1
}

if (-not (Test-Path $AlertsScript)) {
    Write-Error "Missing alerts.ps1 at: $AlertsScript"
    exit 1
}

if (-not $SkipDocker) {
    Write-Host "[1/3] Starting camera bridge (Docker)..."
    try {
        Start-PackHouseDockerBridge $Root
    } catch {
        Write-Error $_.Exception.Message
        exit 1
    }
} else {
    Write-Host "[1/3] Skipping Docker (-SkipDocker)"
}

Write-Host "[2/3] Waiting for camera stream..."
try {
    Wait-PackHouseCameraStream -SkipDockerCheck:$SkipDocker
} catch {
    Write-Error $_.Exception.Message
    exit 1
}

Write-Host "[3/3] Starting vision + alerts (alerts.ps1)..."
Write-Host ""

$alertParams = @{
    SkipDocker = $true
    SkipCameraSetup = $true
    RequireAlertApi = $false
    Device = $Device
    Model = $Model
    Conf = $Conf
}
if ($NoShow) { $alertParams.NoShow = $true }
if ($Track) { $alertParams.Track = $true }
& $AlertsScript @alertParams
exit $LASTEXITCODE
