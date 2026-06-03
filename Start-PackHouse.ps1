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
  .\Start-PackHouse.ps1 -Camera sorting_1
  YOLO on the sorting 1 camera (see config/cameras.yaml).
#>
param(
    [switch]$NoShow,
    [string]$Device = "cpu",
    [string]$Model = "packhouse_best.pt",
    [float]$Conf = 0.65,
    [string]$Camera = "second_wash_dipping",
    [switch]$Track,
    [switch]$SkipDocker
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$BridgeDir = $Root
$VisionDir = Join-Path $Root "packhouse-runtime"
$ModelPath = Join-Path (Join-Path $VisionDir "models") $Model
$Go2RtcStreamByCamera = @{
    first_drying_stage   = "first_drying_stage"
    sorting_1            = "sorting_1"
    indoor_receiving     = "indoor_receiving"
    second_wash_dipping  = "second_wash_dipping"
    outdoor_receiving    = "outdoor_receiving"
    drying_dispatch      = "drying_dispatch"
    entrance             = "entrance"
}
$Go2RtcStreamSrc = $Go2RtcStreamByCamera[$Camera]
if (-not $Go2RtcStreamSrc) { $Go2RtcStreamSrc = $Camera }

function Import-DotEnv {
    param([string]$Path)
    if (-not (Test-Path $Path)) { return @{} }
    $vars = @{}
    foreach ($line in Get-Content $Path -Encoding UTF8) {
        $line = $line.Trim()
        if (-not $line -or $line.StartsWith("#")) { continue }
        $eq = $line.IndexOf("=")
        if ($eq -lt 1) { continue }
        $key = $line.Substring(0, $eq).Trim()
        $val = $line.Substring($eq + 1).Trim()
        if ($val.Length -ge 2 -and $val.StartsWith('"') -and $val.EndsWith('"')) {
            $val = $val.Substring(1, $val.Length - 2)
        }
        $vars[$key] = $val
    }
    return $vars
}

function Set-EufyComposeEnv {
    param([hashtable]$Vars)
    $required = @("EUFY_USERNAME", "EUFY_PASSWORD")
    foreach ($key in $required) {
        if (-not $Vars.ContainsKey($key) -or [string]::IsNullOrWhiteSpace($Vars[$key])) {
            throw "Missing or empty $key in .env (save the file after editing .env.example)."
        }
    }
    $env:EUFY_USERNAME = $Vars["EUFY_USERNAME"]
    $env:EUFY_PASSWORD = $Vars["EUFY_PASSWORD"]
    if ($Vars.ContainsKey("EUFY_COUNTRY") -and -not [string]::IsNullOrWhiteSpace($Vars["EUFY_COUNTRY"])) {
        $env:EUFY_COUNTRY = $Vars["EUFY_COUNTRY"]
    } elseif (-not $env:EUFY_COUNTRY) {
        $env:EUFY_COUNTRY = "US"
    }
}

function Test-DockerServiceRunning {
    param([string]$Name)
    try {
        $status = docker inspect -f "{{.State.Status}}" $Name 2>$null
        return $status -eq "running"
    } catch {
        return $false
    }
}

function Test-Go2RtcReady {
    try {
        $r = Invoke-WebRequest -Uri "http://localhost:1984/api/streams" -UseBasicParsing -TimeoutSec 3
        return $r.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Test-Go2RtcStreamFrames {
    param([string]$Src = $Go2RtcStreamSrc)
    try {
        $r = Invoke-WebRequest -Uri "http://localhost:1984/api/frame.jpeg?src=$Src" -UseBasicParsing -TimeoutSec 8
        return ($r.StatusCode -eq 200) -and ($r.RawContentLength -gt 500)
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
    $envPath = Join-Path $BridgeDir ".env"
    if (-not (Test-Path $envPath)) {
        Write-Error "Missing .env - copy .env.example to .env and set Eufy credentials."
        exit 1
    }
    if ((Get-Item $envPath).Length -eq 0) {
        Write-Error ".env is empty. Copy .env.example to .env, fill EUFY_USERNAME/EUFY_PASSWORD/EUFY_COUNTRY, and save the file."
        exit 1
    }
    try {
        $dotenv = Import-DotEnv $envPath
        Set-EufyComposeEnv $dotenv
    } catch {
        Write-Error $_.Exception.Message
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
$apiReady = $false
for ($i = 1; $i -le 30; $i++) {
    if (Test-Go2RtcReady) {
        $apiReady = $true
        break
    }
    Start-Sleep -Seconds 2
}
if (-not $apiReady) {
    Write-Warning "go2rtc not responding on :1984 - check: docker compose ps"
}

if (-not $SkipDocker) {
    $wsOk = $false
    for ($i = 1; $i -le 30; $i++) {
        if (Test-DockerServiceRunning "eufy-security-ws") {
            $wsOk = $true
            break
        }
        Start-Sleep -Seconds 2
        if ($i % 5 -eq 0) { Write-Host "      waiting for eufy-security-ws..." }
    }
    if (-not $wsOk) {
        Write-Error @"
eufy-security-ws is not running (bad/missing .env credentials or first-time login).
  1. Ensure .env has EUFY_USERNAME, EUFY_PASSWORD, EUFY_COUNTRY and is saved.
  2. docker logs eufy-security-ws
  3. docker compose up -d
"@
        exit 1
    }
}

$framesReady = $false
for ($i = 1; $i -le 90; $i++) {
    if (Test-Go2RtcStreamFrames $Go2RtcStreamSrc) {
        $framesReady = $true
        Write-Host "      camera stream ready (${i}s) - $Go2RtcStreamSrc"
        break
    }
    Start-Sleep -Seconds 2
    if ($i % 10 -eq 0) {
        Write-Host "      waiting for video frames from $Go2RtcStreamSrc..."
        if (-not $SkipDocker -and -not (Test-DockerServiceRunning "eufy-security-ws")) {
            Write-Error "eufy-security-ws stopped. Run: docker logs eufy-security-ws"
            exit 1
        }
    }
}
if (-not $framesReady) {
    Write-Error @"
No video frames on rtsp://127.0.0.1:8554/$Go2RtcStreamSrc (RTSP 404 until the bridge is healthy).
  Browser test: http://localhost:1984/stream.html?src=$Go2RtcStreamSrc
  Logs: docker logs eufyp2pstream_first_drying_stage ; docker logs go2rtc
"@
    exit 1
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
