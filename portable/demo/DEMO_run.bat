@echo off
REM ============================================================
REM  Telegram Channel Management Suite - DEMO launcher (Windows)
REM
REM  Double-click this file to try the program with ready-made
REM  demo data. No Python, Node.js or Docker is required when the
REM  runtime\ folder ships with the build.
REM
REM  It runs in "demo" mode:
REM    * no real Telegram connection, no tokens, no account needed;
REM    * all demo data lives inside this demo\ folder;
REM    * the Web UI shows a yellow "DEMO" banner.
REM
REM  This demo is only for trying the interface. Do NOT put real
REM  channel data here - use run.bat in the folder above for that.
REM ============================================================
setlocal enableextensions
cd /d "%~dp0"

REM All mutable demo state stays inside this demo\ folder.
set "TCMS_ROOT=%~dp0"
REM The application code lives in ..\app\ ; make it importable.
set "PYTHONPATH=%~dp0..\app"

REM Readiness polling (consumed by open_when_ready.ps1).
if not defined STARTUP_TIMEOUT set "STARTUP_TIMEOUT=45"
if not defined STARTUP_POLL_MS set "STARTUP_POLL_MS=400"

REM This launcher is always a demo, regardless of the environment.
set "APP_ENV=demo"

REM Create a config file from the demo template on first run.
if not exist ".env" (
  if exist ".env.demo" (
    echo [i] First run: creating demo .env
    copy /Y ".env.demo" ".env" >nul
  )
)

REM Prefer the bundled runtime; fall back to a system Python.
set "PYTHON=%~dp0..\runtime\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"

REM Prefer a windowless interpreter so no console window appears at all.
set "PYTHONW=%~dp0..\runtime\pythonw.exe"
if not exist "%PYTHONW%" set "PYTHONW=%PYTHON%"

REM Determine the port (APP_PORT in .env, else 8010).
set "APP_PORT=8010"
if exist ".env" (
  for /f "tokens=1,2 delims==" %%A in ('findstr /B /I "APP_PORT=" ".env"') do set "APP_PORT=%%B"
)

echo Preparing demo data ...
"%PYTHON%" "%~dp0seed_demo.py"
if errorlevel 1 (
  echo.
  echo [!] Could not prepare demo data. See the message above.
  echo     If you see "APP_ENV is not demo", the .env in this folder was edited.
  echo     Delete demo\.env and run this file again.
  pause
  exit /b 1
)

echo Starting the demo on http://127.0.0.1:%APP_PORT% ...
echo A browser window will open in a few seconds.
echo To stop the demo, double-click DEMO_stop.bat.

REM Start the backend directly (windowless, no console) and keep its log in
REM this folder. No tray supervisor is used, so DEMO_stop.bat can stop it.
if not exist "%~dp0logs" mkdir "%~dp0logs"
start "" /b "%PYTHONW%" -m backend.app.main > "%~dp0logs\demo.log" 2>&1

REM Wait for the server to actually answer /health, then open the browser.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\open_when_ready.ps1" -Port %APP_PORT% -TimeoutSec %STARTUP_TIMEOUT% -PollMs %STARTUP_POLL_MS%

endlocal
exit /b 0
