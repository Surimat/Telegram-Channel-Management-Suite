@echo off
REM ============================================================
REM  Telegram Channel Management Suite - portable launcher (v1.4)
REM
REM  Unpack the folder, double-click run.bat. The TCMS Tray Agent
REM  starts the backend HIDDEN (no console window), supervises it
REM  and puts an icon in the system tray. open_when_ready.ps1 then
REM  waits for /health and opens the browser only once the server
REM  actually answers. No Python/Node/Docker installation is
REM  required when the runtime\ folder ships with the build.
REM
REM  There is no fixed sleep: readiness is polled, never guessed.
REM ============================================================
setlocal enableextensions
cd /d "%~dp0"

REM All mutable state stays inside this folder (predictable paths).
set "TCMS_ROOT=%~dp0"
REM The application code lives in app\ ; make it importable.
set "PYTHONPATH=%~dp0app"

REM Readiness polling (consumed by open_when_ready.ps1).
if not defined STARTUP_TIMEOUT set "STARTUP_TIMEOUT=30"
if not defined STARTUP_POLL_MS set "STARTUP_POLL_MS=400"

REM Create a config file from the template on first run.
if not exist ".env" (
  if exist ".env.example" (
    echo [i] First run: creating .env from .env.example
    copy /Y ".env.example" ".env" >nul
  )
)

REM Prefer the bundled runtime; fall back to a system Python.
set "PYTHON=%~dp0runtime\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"

REM Determine the port (APP_PORT in .env, else 8000).
set "APP_PORT=8000"
if exist ".env" (
  for /f "tokens=1,2 delims==" %%A in ('findstr /B /I "APP_PORT=" ".env"') do set "APP_PORT=%%B"
)

echo Starting Telegram Channel Management Suite (tray agent) on http://127.0.0.1:%APP_PORT% ...
echo This window will close; the icon appears in the system tray.
echo To stop the app, use the tray icon menu or double-click stop.bat.

REM Start the TCMS Tray Agent hidden. It supervises the backend process and
REM shows the tray icon; the browser is opened by the readiness helper below.
start "" /min cmd /c ""%PYTHON%" -m backend.app.tray.agent --tray --no-browser"

REM Wait for the server to actually answer /health, then open the browser.
REM Uses only PowerShell (always present on Windows).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0open_when_ready.ps1" -Port %APP_PORT% -TimeoutSec %STARTUP_TIMEOUT% -PollMs %STARTUP_POLL_MS%

endlocal
exit /b 0
