$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $scriptDir "Env.ps1")

$script:Go2RtcStreamSrc = "living_room"

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
    param([string]$Src = $script:Go2RtcStreamSrc)
    try {
        $r = Invoke-WebRequest -Uri "http://localhost:1984/api/frame.jpeg?src=$Src" -UseBasicParsing -TimeoutSec 8
        return ($r.StatusCode -eq 200) -and ($r.RawContentLength -gt 500)
    } catch {
        return $false
    }
}

function Wait-PackHouseCameraStream {
    param(
        [switch]$SkipDockerCheck,
        [string]$StreamSrc = $script:Go2RtcStreamSrc
    )
    Write-Host "[camera] Waiting for stream..."
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

    if (-not $SkipDockerCheck) {
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
            throw @"
eufy-security-ws is not running (bad/missing .env credentials or first-time login).
  1. Ensure .env has EUFY_USERNAME, EUFY_PASSWORD, EUFY_COUNTRY and is saved.
  2. docker logs eufy-security-ws
  3. docker compose up -d
"@
        }
    }

    for ($i = 1; $i -le 90; $i++) {
        if (Test-Go2RtcStreamFrames $StreamSrc) {
            Write-Host "      camera stream ready (${i}s) - $StreamSrc"
            return
        }
        Start-Sleep -Seconds 2
        if ($i % 10 -eq 0) {
            Write-Host "      waiting for video frames from $StreamSrc..."
            if (-not $SkipDockerCheck -and -not (Test-DockerServiceRunning "eufy-security-ws")) {
                throw "eufy-security-ws stopped. Run: docker logs eufy-security-ws"
            }
        }
    }
    throw @"
No video frames on rtsp://127.0.0.1:8554/$StreamSrc.
  Browser test: http://localhost:1984/stream.html?src=$StreamSrc
  Logs: docker logs eufyp2pstream ; docker logs go2rtc
"@
}

function Start-PackHouseDockerBridge {
    param([string]$RepoRoot)
    Write-Host "[camera] Starting Docker bridge..."
    $envPath = Join-Path $RepoRoot ".env"
    if (-not (Test-Path $envPath)) {
        throw "Missing .env - copy .env.example to .env and set Eufy credentials."
    }
    if ((Get-Item $envPath).Length -eq 0) {
        throw ".env is empty. Copy .env.example to .env, fill EUFY_* values, and save the file."
    }
    $dotenv = Import-DotEnv $envPath
    Set-EufyComposeEnv $dotenv
    Push-Location $RepoRoot
    try {
        docker compose up -d --build
        if ($LASTEXITCODE -ne 0) {
            throw "docker compose failed. Is Docker Desktop running?"
        }
    } finally {
        Pop-Location
    }
}
