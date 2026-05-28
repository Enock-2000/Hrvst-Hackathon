<#
.SYNOPSIS
  Run live detection with truck-arrival alerts (independent entry point).

.EXAMPLE
  .\alerts.ps1
  Loads .env, starts camera bridge if needed, posts truck-arrivals and PPE/quality violations.

.EXAMPLE
  .\alerts.ps1 -SkipDocker -SkipCameraSetup
  Vision + alerts only (used by Start-PackHouse.ps1 after bridge is ready).
#>
param(
    [switch]$NoShow,
    [string]$Device = "cpu",
    [string]$Model = "packhouse_best.pt",
    [float]$Conf = 0.35,
    [switch]$Track,
    [switch]$SkipDocker,
    [switch]$SkipCameraSetup,
    [string]$Camera = $null,
    [switch]$RequireAlertApi
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$ScriptsDir = Join-Path $Root "scripts"
$VisionDir = Join-Path $Root "packhouse-runtime"
$ModelPath = Join-Path (Join-Path $VisionDir "models") $Model

. (Join-Path $ScriptsDir "Env.ps1")
. (Join-Path $ScriptsDir "CameraReady.ps1")

# Default: standalone run requires API config; Start-PackHouse passes -RequireAlertApi:$false
if (-not $PSBoundParameters.ContainsKey("RequireAlertApi")) {
    $RequireAlertApi = $true
}

Write-Host "========================================"
Write-Host "  Pack House - Alerts"
Write-Host "========================================"
Write-Host ""

$envPath = Join-Path $Root ".env"
if (-not (Test-Path $envPath)) {
    if ($RequireAlertApi) {
        Write-Error "Missing .env - copy .env.example and set ARRIVAL_API_* plus Eufy credentials."
        exit 1
    }
    Write-Warning "No .env file; running vision without arrival API alerts."
    $dotenv = @{}
} else {
    $dotenv = Import-DotEnv $envPath
}

$enableArrivalAlerts = $false
$enableViolationAlerts = $false
if (Test-ArrivalAlertEnvConfigured $dotenv) {
    Set-ArrivalAlertEnv $dotenv
    $enableArrivalAlerts = $true
    Write-Host "  Truck arrivals: $env:ARRIVAL_API_BASE_URL/api/v1/receiving/truck-arrivals"
}
if (Test-ViolationAlertEnvConfigured $dotenv) {
    Set-ViolationAlertEnv $dotenv
    $enableViolationAlerts = $true
    $vBase = if ($env:VIOLATION_API_BASE_URL) { $env:VIOLATION_API_BASE_URL } else { $env:ARRIVAL_API_BASE_URL }
    Write-Host "  Violations:     $vBase/api/v1/ppe/violations"
}
if ($RequireAlertApi -and -not $enableArrivalAlerts -and -not $enableViolationAlerts) {
    Write-Error "Missing alert API config in .env (ARRIVAL_API_* and/or VIOLATION_API_*)."
    exit 1
}
if (-not $enableArrivalAlerts -and -not $RequireAlertApi) {
    Write-Warning "ARRIVAL_API_* not set; truck-arrival POSTs disabled."
}
if (-not $enableViolationAlerts -and -not $RequireAlertApi) {
    Write-Warning "VIOLATION_API_* / ARRIVAL_API_* not set; violation POSTs disabled."
}
Write-Host ""

if (-not (Test-Path $ModelPath)) {
    Write-Error "Model not found: $ModelPath"
    exit 1
}

if (-not $SkipCameraSetup) {
    if (-not $SkipDocker) {
        Start-PackHouseDockerBridge $Root
    } else {
        Write-Host "[camera] Skipping Docker (-SkipDocker)"
    }
    try {
        Wait-PackHouseCameraStream -SkipDockerCheck:$SkipDocker
    } catch {
        Write-Error $_.Exception.Message
        exit 1
    }
}

Write-Host "[vision] Python environment..."
Push-Location $VisionDir
$VenvActivate = Join-Path $VisionDir ".venv\Scripts\Activate.ps1"
if (-not (Test-Path $VenvActivate)) {
    Write-Host "      Creating .venv (first run only)..."
    python -m venv .venv
    & (Join-Path $VisionDir ".venv\Scripts\pip.exe") install -r requirements.txt
}
. $VenvActivate

if ($enableArrivalAlerts -or $enableViolationAlerts) {
    Write-Host "[vision] Live detection + API alerts..."
} else {
    Write-Host "[vision] Live detection..."
}
$pyArgs = @(
    "src\live_inference.py",
    "--model", $ModelPath,
    "--device", $Device,
    "--conf", $Conf
)
if ($enableArrivalAlerts) { $pyArgs += "--alerts" }
if ($enableViolationAlerts) { $pyArgs += "--violation-alerts" }
if ($Camera) { $pyArgs += @("--camera", $Camera) }
if (-not $NoShow) { $pyArgs += "--show" }
if ($Track) { $pyArgs += "--track" }

python @pyArgs
$code = $LASTEXITCODE
Pop-Location
exit $code
