@echo off
REM ============================================================
REM  Telegram Channel Management Suite - portable launcher
REM  Starts the app and opens the browser.
REM  Full portable packaging is delivered in PHASE 10; this is
REM  the developer/local-runtime skeleton.
REM ============================================================
setlocal
cd /d "%~dp0.."

if not exist ".env" (
  echo [i] .env not found - copying from .env.example
  copy /Y ".env.example" ".env" >nul
)

set "PYTHON=python"
if exist "..\runtime\python.exe" set "PYTHON=..\runtime\python.exe"

echo Starting Telegram Channel Management Suite...
start "" http://127.0.0.1:8000
%PYTHON% -m backend.app.main

endlocal
