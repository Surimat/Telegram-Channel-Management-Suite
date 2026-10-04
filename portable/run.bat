@echo off
REM ============================================================
REM  Telegram Channel Management Suite - portable launcher
REM
REM  Unpack the folder, double-click run.bat. The app starts and
REM  your browser opens. No Python/Node/Docker installation is
REM  required when the runtime\ folder ships with the build.
REM
REM  The browser opens only after the server answers /health
REM  (see open_when_ready.ps1). There is no fixed sleep delay.
REM ============================================================
setlocal enableextensions
cd /d "%~dp0"

REM All mutable state stays inside this folder (predictable paths).
set "TCMS_ROOT=%~dp0"
REM The application code lives in app\ ; make it importable.
set "PYTHONPATH=%~dp0app"

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
REM Startup readiness tuning (override in .env if needed).
set "STARTUP_TIMEOUT=30"
if exist ".env" (
  for /f "tokens=1,2 delims==" %%A in ('findstr /B /I "STARTUP_TIMEOUT=" ".env"') do set "STARTUP_TIMEOUT=%%B"
)
set "STARTUP_POLL_MS=400"
if exist ".env" (
  for /f "tokens=1,2 delims==" %%A in ('findstr /B /I "STARTUP_POLL_MS=" ".env"') do set "STARTUP_POLL_MS=%%B"
)

echo Starting Telegram Channel Management Suite on http://127.0.0.1:%APP_PORT% ...

REM Start the server in a background window, then wait for real readiness
REM before opening the browser. The helper exits non-zero on timeout, in
REM which case we print a plain-language message instead of a dead page.
start "TCMS server" /min cmd /c ""%PYTHON%" -m backend.app.main"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0open_when_ready.ps1" -Port %APP_PORT% -TimeoutSec %STARTUP_TIMEOUT% -PollMs %STARTUP_POLL_MS%
if errorlevel 1 (
  echo.
  echo The application did not become ready. See the messages above.
  echo Check the logs\ folder or run Diagnostika once the app is running.
  echo Press any key to close this window.
  pause >nul
  endlocal
  exit /b 1
)

echo.
echo The application is running in a separate window ("TCMS server").
echo To stop it, double-click stop.bat or close that window.
echo Press any key to close this launcher.
pause >nul
endlocal
exit /b 0

