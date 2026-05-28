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

function Test-ArrivalAlertEnvConfigured {
    param([hashtable]$Vars)
    foreach ($key in @("ARRIVAL_API_BASE_URL", "ARRIVAL_API_BEARER_TOKEN")) {
        if (-not $Vars.ContainsKey($key) -or [string]::IsNullOrWhiteSpace($Vars[$key])) {
            return $false
        }
    }
    return $true
}

function Set-ArrivalAlertEnv {
    param([hashtable]$Vars)
    $required = @("ARRIVAL_API_BASE_URL", "ARRIVAL_API_BEARER_TOKEN")
    foreach ($key in $required) {
        if (-not $Vars.ContainsKey($key) -or [string]::IsNullOrWhiteSpace($Vars[$key])) {
            throw "Missing or empty $key in .env (required for alerts.ps1)."
        }
    }
    $env:ARRIVAL_API_BASE_URL = $Vars["ARRIVAL_API_BASE_URL"]
    $env:ARRIVAL_API_BEARER_TOKEN = $Vars["ARRIVAL_API_BEARER_TOKEN"]
    if ($Vars.ContainsKey("ARRIVAL_ALERT_COOLDOWN_SEC") -and -not [string]::IsNullOrWhiteSpace($Vars["ARRIVAL_ALERT_COOLDOWN_SEC"])) {
        $env:ARRIVAL_ALERT_COOLDOWN_SEC = $Vars["ARRIVAL_ALERT_COOLDOWN_SEC"]
    }
    if ($Vars.ContainsKey("ARRIVAL_ALERT_TIMEOUT_SEC") -and -not [string]::IsNullOrWhiteSpace($Vars["ARRIVAL_ALERT_TIMEOUT_SEC"])) {
        $env:ARRIVAL_ALERT_TIMEOUT_SEC = $Vars["ARRIVAL_ALERT_TIMEOUT_SEC"]
    }
}
