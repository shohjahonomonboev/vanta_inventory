# start-vanta.ps1 — minimal, safe Windows runner (Waitress)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Go to project root
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

# Create & activate venv if needed
if (-not (Test-Path ".\venv\Scripts\Activate.ps1")) {
  Write-Host ">> Creating Python venv..." -ForegroundColor Cyan
  python -m venv venv
}
Write-Host ">> Activating venv" -ForegroundColor Cyan
. .\venv\Scripts\Activate.ps1

# Install deps (quiet)
Write-Host ">> Installing dependencies" -ForegroundColor Cyan
pip install --disable-pip-version-check -q -r requirements.txt
pip install --disable-pip-version-check -q waitress

# Minimal env defaults for local
if (-not $env:FLASK_ENV)  { $env:FLASK_ENV = "production" }
if (-not $env:SECRET_KEY) { $env:SECRET_KEY = "dev-only-secret-change-me" }

Write-Host ">> Starting app with Waitress" -ForegroundColor Green
Write-Host "   URL: http://127.0.0.1:5000"
Write-Host "   FLASK_ENV=$($env:FLASK_ENV)"

# Run the app
waitress-serve --listen="127.0.0.1:5000" app:app
