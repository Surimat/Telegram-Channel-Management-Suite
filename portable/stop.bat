@echo off
REM ============================================================
REM  Telegram Channel Management Suite - portable stop helper
REM  Sends a graceful shutdown request, then stops the process.
REM  Full portable packaging is delivered in PHASE 10.
REM ============================================================
setlocal
echo Requesting graceful shutdown...
curl -s -X POST http://127.0.0.1:8000/api/v1/system/shutdown >nul 2>&1
echo.
echo The application window can now be closed.
endlocal
