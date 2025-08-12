# --- start-vanta.ps1 ---
$ErrorActionPreference = "Stop"

# Go to this script's folder
Set-Location -Path $PSScriptRoot

# Sync with GitHub main (safe if no local changes)
git fetch origin
git reset --hard origin/main

# Free port 5000 if something is listening
# Free port 5000 if something is listening (ignore if already gone)
$procs = Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue |
         Select-Object -Expand OwningProcess -Unique
foreach ($pid in $procs) {
  Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
}
# venv bootstrap
if (!(Test-Path .\venv)) { python -m venv venv }
.\venv\Scripts\Activate.ps1

# Deps
pip install -r requirements.txt

# Env vars for local run
$env:ADMIN_USERS = "vanta:beastmode,jasur:jasur2025"
$env:DB_PATH     = (Join-Path $PWD "inventory.db")
if (-not $env:PORT) { $env:PORT = "5000" }

Write-Host ">>> Starting Vanta on http://127.0.0.1:$($env:PORT)" -ForegroundColor Cyan
python app.py
