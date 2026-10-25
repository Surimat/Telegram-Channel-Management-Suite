@echo off
REM ============================================================
REM  Telegram Channel Management Suite - DEMO stop
REM
REM  Politely asks the local demo server to shut down (graceful,
REM  so the database closes cleanly). Only works for this machine.
REM ============================================================
setlocal enableextensions
cd /d "%~dp0"

set "APP_PORT=8010"
if exist ".env" (
  for /f "tokens=1,2 delims==" %%A in ('findstr /B /I "APP_PORT=" ".env"') do set "APP_PORT=%%B"
)

echo Requesting graceful shutdown on http://127.0.0.1:%APP_PORT% ...
powershell -NoProfile -Command ^
  "try { Invoke-RestMethod -Method Post -Uri ('http://127.0.0.1:' + $env:APP_PORT + '/api/v1/system/shutdown') | Out-Null; Write-Host 'Demo stopped.' } catch { Write-Host 'The demo is not running (or already stopped).' }"

endlocal
