# Wrapper — use repo-root Start-PackHouse.ps1 for full stack startup
$Root = Split-Path $PSScriptRoot -Parent
& (Join-Path $Root "Start-PackHouse.ps1") @args
