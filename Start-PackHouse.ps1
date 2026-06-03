<#
.SYNOPSIS
  Pack House: Eufy bridge (coordinator + go2rtc) + LocateAnything-3B live detection (CUDA).

.EXAMPLE
  .\Start-PackHouse.ps1
  .\Start-PackHouse.ps1 -Camera sorting_1 -Device cuda:0
  .\Start-PackHouse.ps1 -SkipDocker
#>
param(
    [switch]$NoShow,
    [string]$Device = "cuda:0",
    [string]$Camera = "second_wash_dipping",
    [switch]$AllCameras,
    [switch]$SkipDocker,
    [int]$EveryNFrames = 0
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$VisionDir = Join-Path $Root "packhouse-runtime"
$ModelDir = Join-Path $VisionDir "models\LocateAnything-3B"

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
    foreach ($key in @("EUFY_USERNAME", "EUFY_PASSWORD")) {
        if (-not $Vars.ContainsKey($key) -or [string]::IsNullOrWhiteSpace($Vars[$key])) {
            throw "Missing or empty $key in .env"
        }
    }
    $env:EUFY_USERNAME = $Vars["EUFY_USERNAME"]
    $env:EUFY_PASSWORD = $Vars["EUFY_PASSWORD"]
    $env:EUFY_COUNTRY = if ($Vars["EUFY_COUNTRY"]) { $Vars["EUFY_COUNTRY"] } else { "US" }
}

function Test-DockerServiceRunning {
    param([string]$Name)
    try { return (docker inspect -f "{{.State.Status}}" $Name 2>$null) -eq "running" } catch { return $false }
}

function Test-Go2RtcReady {
    try {
        return (Invoke-WebRequest -Uri "http://localhost:1984/api/streams" -UseBasicParsing -TimeoutSec 3).StatusCode -eq 200
    } catch { return $false }
}

function Test-Go2RtcStreamFrames {
    param([string]$Src = $Go2RtcStreamSrc)
    try {
        $r = Invoke-WebRequest -Uri "http://localhost:1984/api/frame.jpeg?src=$Src" -UseBasicParsing -TimeoutSec 8
        return ($r.StatusCode -eq 200) -and ($r.RawContentLength -gt 500)
    } catch { return $false }
}

function Get-PackHousePython {
    param([string]$RuntimeDir)
    foreach ($name in @(".venv", ".venv-locateanything")) {
        $py = Join-Path $RuntimeDir "$name\Scripts\python.exe"
        if (Test-Path $py) { return $py }
    }
    return $null
}

Write-Host "========================================"
Write-Host "  Pack House — LocateAnything"
Write-Host "========================================"
Write-Host ""

if (-not (Test-Path (Join-Path $ModelDir "config.json"))) {
    Write-Error @"
LocateAnything weights not found at packhouse-runtime\models\LocateAnything-3B
  Run: cd packhouse-runtime ; .\scripts\Download-LocateAnythingModel.ps1
  Copy the full repo (including models\) to your NVIDIA GPU PC.
"@
    exit 1
}

if ($AllCameras) {
    Write-Warning "Eufy HomeBase allows one P2P stream at a time. Multi-camera view may show only the active stream."
}

if (-not $SkipDocker) {
    Write-Host "[1/4] Starting camera bridge (Docker)..."
    $envPath = Join-Path $Root ".env"
    if (-not (Test-Path $envPath)) { Write-Error "Missing .env — copy .env.example and set Eufy credentials." }
    if ((Get-Item $envPath).Length -eq 0) { Write-Error ".env is empty." }
    Set-EufyComposeEnv (Import-DotEnv $envPath)
    Push-Location $Root
    docker compose up -d --build
    if ($LASTEXITCODE -ne 0) { Pop-Location; Write-Error "docker compose failed."; exit 1 }
    Pop-Location
} else {
    Write-Host "[1/4] Skipping Docker (-SkipDocker)"
}

Write-Host "[2/4] Waiting for camera stream ($Go2RtcStreamSrc)..."
for ($i = 1; $i -le 30; $i++) {
    if (Test-Go2RtcReady) { break }
    Start-Sleep -Seconds 2
}

if (-not $SkipDocker) {
    for ($i = 1; $i -le 30; $i++) {
        if (Test-DockerServiceRunning "eufy-security-ws") { break }
        Start-Sleep -Seconds 2
    }
    if (-not (Test-DockerServiceRunning "eufy-security-ws")) {
        Write-Error "eufy-security-ws not running. Check .env and: docker logs eufy-security-ws"
        exit 1
    }
}

$framesReady = $false
for ($i = 1; $i -le 90; $i++) {
    if (Test-Go2RtcStreamFrames $Go2RtcStreamSrc) {
        $framesReady = $true
        Write-Host "      stream ready (${i}s) - $Go2RtcStreamSrc"
        break
    }
    Start-Sleep -Seconds 2
    if ($i % 10 -eq 0) { Write-Host "      waiting for frames from $Go2RtcStreamSrc..." }
}
if (-not $framesReady) {
    Write-Error @"
No video frames on rtsp://127.0.0.1:8554/$Go2RtcStreamSrc
  Dashboard: http://localhost:8080/dashboard.html
  Solo view: http://localhost:1984/stream.html?src=$Go2RtcStreamSrc
  Coordinator: http://localhost:8090/status
  Logs: docker logs eufyp2pstream_$Go2RtcStreamSrc ; docker logs go2rtc
"@
    exit 1
}

Write-Host "[3/4] Python environment..."
Push-Location $VisionDir
$Python = Get-PackHousePython $VisionDir
if (-not $Python) {
    Write-Host "      Installing .venv (first run)..."
    & (Join-Path $VisionDir "scripts\Install.ps1")
    $Python = Get-PackHousePython $VisionDir
}
if (-not $Python) { Write-Error "venv missing. Run packhouse-runtime\scripts\Install.ps1"; exit 1 }

Write-Host "[4/4] LocateAnything live detection..."
Write-Host "      Camera: $Camera  Device: $Device"
if (-not $NoShow) { Write-Host "      Press Q to quit." }
Write-Host ""

$pyArgs = @("src\live_inference.py", "--device", $Device)
if ($EveryNFrames -gt 0) { $pyArgs += @("--every-n-frames", $EveryNFrames) }
if ($AllCameras) { $pyArgs += "--all-cameras" } else { $pyArgs += @("--camera", $Camera) }
if (-not $NoShow) { $pyArgs += "--show" }

& $Python @pyArgs
$code = $LASTEXITCODE
Pop-Location
exit $code
