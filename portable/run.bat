@echo off
REM ============================================================
REM  Telegram Channel Management Suite - portable launcher
REM
REM  Unpack the folder, double-click run.bat. The app starts and
REM  your browser opens. No Python/Node/Docker installation is
REM  required when the runtime\ folder ships with the build.
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

echo Starting Telegram Channel Management Suite on http://127.0.0.1:%APP_PORT% ...
REM Give the server a moment, then open the browser.
start "" /min cmd /c "timeout /t 3 /nobreak >nul & start "" http://127.0.0.1:%APP_PORT%"

"%PYTHON%" -m backend.app.main
set "EXITCODE=%ERRORLEVEL%"

echo.
echo The application has stopped (exit code %EXITCODE%).
pause
endlocal
