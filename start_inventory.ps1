param(
  [int]$Port = 5000,
  [string]$BindAddr = "127.0.0.1"
)

# Go to project and activate venv
Set-Location $proj
& "$proj\venv\Scripts\activate.ps1" | Out-Null

# Runtime env
$env:ENV  = "prod"
$env:APP_TZ = "Asia/Tokyo"
$env:SECRET_KEY = "replace-me"
$env:ADMIN_USERS_JSON = '{"vanta":"new2025"}'
$env:ADMIN_ACTION_PASSWORD = "new2025"
$env:PYTHONIOENCODING = "utf-8"

# Use project-local SQLite
Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue

# Logs
$logDir = Join-Path $proj "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$ts   = Get-Date -Format "yyyyMMdd_HHmmss"
$log  = Join-Path $logDir "waitress_$ts.log"
$elog = Join-Path $logDir "waitress_$ts.err.log"

# Launch waitress headless
$python = Join-Path $proj "venv\Scripts\python.exe"
$args   = "-m waitress --host=$BindAddr --port=$Port app:app"

Start-Process -FilePath $python `
  -ArgumentList $args `
  -WorkingDirectory $proj `
  -RedirectStandardOutput $log `
  -RedirectStandardError  $elog `
  -WindowStyle Hidden
