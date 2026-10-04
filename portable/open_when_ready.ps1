# ============================================================
#  Telegram Channel Management Suite - readiness helper
#
#  Waits until the local server answers /health, then opens the
#  browser. This replaces a fixed "sleep 3 seconds" delay, so the
#  page never opens before the server is actually ready.
#
#  Uses only PowerShell (always present on Windows) - no Python,
#  Node, npm or Docker is required.
#
#  Exit codes:
#    0 - server became healthy, browser opened
#    1 - timed out before the server answered
# ============================================================
param(
  [int]$Port = 8000,
  [int]$TimeoutSec = 30,
  [int]$PollMs = 400
)

$ErrorActionPreference = 'SilentlyContinue'
$url = "http://127.0.0.1:$Port"
$healthUrl = "$url/health"
$deadline = (Get-Date).AddSeconds($TimeoutSec)

Write-Host "Waiting for the application at $url ..."
$ready = $false
while ((Get-Date) -lt $deadline) {
  try {
    $resp = Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 -Uri $healthUrl
    if ($resp.StatusCode -eq 200) {
      $ready = $true
      break
    }
  } catch {
    # Server not up yet; keep polling.
  }
  Start-Sleep -Milliseconds $PollMs
}

if ($ready) {
  Write-Host "Application is ready. Opening $url ..."
  Start-Process $url | Out-Null
  exit 0
}

# Timeout: do NOT open a page that would show a connection error.
Write-Host ""
Write-Host "============================================================"
Write-Host " The application did not finish starting within $TimeoutSec seconds."
Write-Host " The browser was not opened to avoid a connection error."
Write-Host ""
Write-Host " What to do:"
Write-Host "   1. Look at the messages above this one (they contain the"
Write-Host "      real error and the application exit code)."
Write-Host "   2. Open the Diagnostics page once the app is running, or"
Write-Host "      check the logs\ folder next to this program."
Write-Host "   3. A common cause is a pending database update or a port"
Write-Host "      already in use - see docs/TROUBLESHOOTING.md."
Write-Host "============================================================"
exit 1
