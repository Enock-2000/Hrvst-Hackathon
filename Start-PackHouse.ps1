<#
.SYNOPSIS
  Start the full Pack House deployment: Eufy camera bridge + live YOLO detection.

.EXAMPLE
  .\Start-PackHouse.ps1
  Starts Docker (if needed), waits for RTSP, opens live view with bounding boxes.

.EXAMPLE
  .\Start-PackHouse.ps1 -NoShow
  Headless mode - saves annotated video under packhouse-runtime/runs/live/

.EXAMPLE
  .\Start-PackHouse.ps1 -Device xpu
  Use Intel XPU for inference (requires torch+xpu in venv).

.EXAMPLE
  .\Start-PackHouse.ps1 -Camera garage
  YOLO on the garage camera (see config/cameras.yaml).
#>
param(
    [switch]$NoShow,
    [string]$Device = "cpu",
    [string]$Model = "packhouse_best.pt",
    [float]$Conf = 0.65,
    [string]$Camera = "entrance",
    [switch]$Track,
    [switch]$SkipDocker
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$BridgeDir = $Root
$VisionDir = Join-Path $Root "packhouse-runtime"
$ModelPath = Join-Path (Join-Path $VisionDir "models") $Model

function Test-Go2RtcReady {
    try {
        $r = Invoke-WebRequest -Uri "http://localhost:1984/api/streams" -UseBasicParsing -TimeoutSec 3
        return $r.StatusCode -eq 200
    } catch {
        return $false
    }
}

Write-Host "========================================"
Write-Host "  Pack House - Start"
Write-Host "========================================"
Write-Host ""

if (-not (Test-Path $ModelPath)) {
    Write-Error "Model not found: $ModelPath"
    exit 1
}

if (-not $SkipDocker) {
    Write-Host "[1/4] Starting camera bridge (Docker)..."
    if (-not (Test-Path (Join-Path $BridgeDir ".env"))) {
        Write-Error "Missing .env - copy .env.example and set Eufy credentials."
        exit 1
    }
    Push-Location $BridgeDir
    docker compose up -d --build
    if ($LASTEXITCODE -ne 0) {
        Pop-Location
        Write-Error "docker compose failed. Is Docker Desktop running?"
        exit 1
    }
    Pop-Location
} else {
    Write-Host "[1/4] Skipping Docker (-SkipDocker)"
}

Write-Host "[2/4] Waiting for camera stream..."
$ready = $false
for ($i = 1; $i -le 45; $i++) {
    if (Test-Go2RtcReady) {
        $ready = $true
        Write-Host "      go2rtc ready (${i}s)"
        break
    }
    Start-Sleep -Seconds 2
    if ($i % 5 -eq 0) { Write-Host "      still waiting... (${i}s)" }
}
if (-not $ready) {
    Write-Warning "go2rtc not responding on :1984 - continuing anyway (stream may connect slowly)"
}

Write-Host "[3/4] Python environment..."
Push-Location $VisionDir
$VenvActivate = Join-Path $VisionDir ".venv\Scripts\Activate.ps1"
if (-not (Test-Path $VenvActivate)) {
    Write-Host "      Creating .venv and installing dependencies (first run only)..."
    python -m venv .venv
    & (Join-Path $VisionDir ".venv\Scripts\pip.exe") install -r requirements.txt
}
. $VenvActivate

Write-Host "[4/4] Starting live detection..."
Write-Host "      Camera: $Camera"
Write-Host "      Model: $Model"
Write-Host "      Device: $Device"
if (-not $NoShow) {
    Write-Host "      Press Q in the video window to quit."
} else {
    Write-Host "      Headless - output under packhouse-runtime/runs/live/"
}
Write-Host ""

$pyArgs = @(
    "src\live_inference.py",
    "--camera", $Camera,
    "--model", $ModelPath,
    "--device", $Device,
    "--conf", $Conf
)
if (-not $NoShow) { $pyArgs += "--show" }
if ($Track) { $pyArgs += "--track" }

python @pyArgs
$code = $LASTEXITCODE
Pop-Location
exit $code
