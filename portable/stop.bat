@echo off
REM ============================================================
REM  Telegram Channel Management Suite - portable stop
REM
REM  Politely asks the local server to shut down (graceful, so the
REM  database closes cleanly). Only works for the local machine.
REM ============================================================
setlocal enableextensions
cd /d "%~dp0"

set "APP_PORT=8000"
if exist ".env" (
  for /f "tokens=1,2 delims==" %%A in ('findstr /B /I "APP_PORT=" ".env"') do set "APP_PORT=%%B"
)

echo Requesting graceful shutdown on http://127.0.0.1:%APP_PORT% ...
powershell -NoProfile -Command ^
  "try { Invoke-RestMethod -Method Post -Uri ('http://127.0.0.1:' + $env:APP_PORT + '/api/v1/system/shutdown') | Out-Null; Write-Host 'Shutdown requested.' } catch { Write-Host 'The application is not running (or already stopped).' }"

endlocal
