@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0alerts.ps1" %*
exit /b %ERRORLEVEL%
